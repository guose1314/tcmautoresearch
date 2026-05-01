import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI

from src.orchestration.orchestration_contract import OrchestrationResult, PhaseOutcome
from src.orchestration.research_runtime_service import ResearchRuntimeResult
from src.web.ops import research_session_service


class _FakeSessionRepository:
    def __init__(self):
        self.sessions = {}
        self.full_snapshots = {}
        self.created_payloads = []

    def create_session(self, payload):
        record = deepcopy(payload)
        if not record.get("cycle_id"):
            record["cycle_id"] = f"service-cycle-{len(self.created_payloads) + 1}"
        self.created_payloads.append(deepcopy(record))
        self.sessions[record["cycle_id"]] = deepcopy(record)
        return deepcopy(record)

    def get_session(self, cycle_id):
        record = self.sessions.get(cycle_id)
        return deepcopy(record) if record is not None else None

    def list_sessions(self, limit=50, offset=0):
        items = list(self.sessions.values())[offset : offset + limit]
        return {
            "items": deepcopy(items),
            "total": len(self.sessions),
            "limit": limit,
            "offset": offset,
        }

    def get_full_snapshot(self, cycle_id):
        snapshot = self.full_snapshots.get(cycle_id)
        return deepcopy(snapshot) if snapshot is not None else None


class _FakeRuntimeService:
    instances = []
    runs = []
    next_status = "completed"

    def __init__(self, config=None):
        self.config = deepcopy(config or {})
        type(self).instances.append(self)

    def run(self, topic, **kwargs):
        phases = list(self.config.get("phases") or [])
        type(self).runs.append(
            {
                "topic": topic,
                "config": deepcopy(self.config),
                **deepcopy(kwargs),
            }
        )

        phase_results = {}
        phase_executions = {}
        outcomes = []
        for phase_name in phases:
            result = {
                "phase": phase_name,
                "status": "completed",
            }
            if phase_name == "observe":
                result["semantic_graph"] = {
                    "nodes": [{"id": "node-1", "name": "桂枝汤"}],
                    "edges": [
                        {"source": "node-1", "target": "node-2", "relation": "contains"}
                    ],
                }
                result["graph_statistics"] = {"nodes_count": 1, "edges_count": 1}
            if phase_name == "publish":
                result["deliverables"] = [{"name": "paper.md"}]
                outcomes.append({"name": "paper.md"})
            phase_results[phase_name] = deepcopy(result)
            phase_executions[phase_name] = {"result": deepcopy(result)}

        target_phase = phases[-1] if phases else "observe"
        if type(self).next_status in {"failed", "partial"}:
            phase_results[target_phase]["error"] = "boom"
            phase_executions[target_phase]["result"]["error"] = "boom"

        orchestration_result = OrchestrationResult(
            topic=topic,
            cycle_id=kwargs.get("cycle_id") or "runtime-cycle-1",
            status=type(self).next_status,
            started_at="2026-04-14T10:00:00",
            completed_at="2026-04-14T10:00:05",
            total_duration_sec=5.0,
            phases=[
                PhaseOutcome(
                    phase=phase_name,
                    status="failed"
                    if phase_name == target_phase
                    and type(self).next_status in {"failed", "partial"}
                    else "completed",
                    duration_sec=1.0,
                    error="boom"
                    if phase_name == target_phase
                    and type(self).next_status in {"failed", "partial"}
                    else "",
                )
                for phase_name in phases
            ],
            pipeline_metadata={
                "cycle_name": kwargs.get("cycle_name"),
                "description": kwargs.get("description"),
                "scope": kwargs.get("scope"),
            },
        )
        return ResearchRuntimeResult(
            orchestration_result=orchestration_result,
            phase_results=phase_results,
            cycle_snapshot={
                "phase_executions": phase_executions,
                "metadata": {"phase_history": phases},
                "outcomes": outcomes,
            },
        )


class TestResearchSessionService(unittest.TestCase):
    def setUp(self):
        _FakeRuntimeService.instances.clear()
        _FakeRuntimeService.runs.clear()
        _FakeRuntimeService.next_status = "completed"

    @staticmethod
    def _build_app():
        app = FastAPI()
        app.state.config = {"models": {"llm": {"provider": "local"}}}
        app.state.job_manager = SimpleNamespace(
            _default_orchestrator_config={
                "pipeline_config": {"models": {"llm": {"provider": "local"}}},
                "runtime_profile": "web_research",
            }
        )
        return app

    def test_build_orchestrator_config_uses_runtime_assembly_when_job_manager_missing(
        self,
    ):
        app = FastAPI()
        app.state.runtime_assembly = SimpleNamespace(
            orchestrator_config={
                "pipeline_config": {"models": {"llm": {"provider": "local"}}},
                "runtime_profile": "web_research",
            }
        )

        config = research_session_service._build_orchestrator_config(app)

        self.assertEqual(config["runtime_profile"], "web_research")
        self.assertEqual(
            config["pipeline_config"]["models"]["llm"]["provider"], "local"
        )

    def test_create_research_session_persists_repository_backed_payload(self):
        repository = _FakeSessionRepository()
        app = self._build_app()

        with patch(
            "src.web.ops.research_session_service._get_repository",
            return_value=repository,
        ):
            created = research_session_service.create_research_session(
                app,
                cycle_name="测试研究",
                description="测试描述",
                objective="测试目标",
                scope="方剂",
                researchers=["alice"],
            )

        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["current_phase"], "observe")
        self.assertEqual(created["researchers"], ["alice"])
        self.assertEqual(
            repository.created_payloads[0]["research_objective"], "测试目标"
        )
        self.assertEqual(
            repository.created_payloads[0]["metadata"]["completed_phases"], []
        )
        self.assertEqual(created["metadata"]["analysis_summary"]["status"], "pending")

    def test_list_research_sessions_reads_repository_summaries(self):
        repository = _FakeSessionRepository()
        repository.sessions["cycle-1"] = {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "description": "测试描述",
            "status": "active",
            "current_phase": "analyze",
            "research_objective": "测试目标",
            "metadata": {"analysis_summary": {"status": "in_progress"}},
        }
        app = self._build_app()

        with patch(
            "src.web.ops.research_session_service._get_repository",
            return_value=repository,
        ):
            summaries = research_session_service.list_research_sessions(app)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["cycle_id"], "cycle-1")
        self.assertEqual(summaries[0]["current_phase"], "analyze")
        self.assertEqual(summaries[0]["analysis_summary"]["status"], "in_progress")

    def test_get_research_session_builds_contract_from_full_snapshot(self):
        repository = _FakeSessionRepository()
        repository.full_snapshots["cycle-1"] = {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "description": "测试描述",
            "status": "completed",
            "current_phase": "reflect",
            "research_objective": "测试目标",
            "metadata": {},
            "phase_executions": [
                {
                    "phase": "observe",
                    "status": "completed",
                    "input": {},
                    "output": {
                        "semantic_graph": {
                            "nodes": [{"id": "node-1"}],
                            "edges": [{"source": "node-1", "target": "node-2"}],
                        },
                        "graph_statistics": {"nodes_count": 1},
                    },
                },
                {
                    "phase": "publish",
                    "status": "completed",
                    "input": {},
                    "output": {
                        "deliverables": [{"name": "repo-paper.md"}],
                    },
                },
            ],
            "artifacts": [
                {
                    "artifact_type": "report",
                    "name": "repo-paper.md",
                    "file_path": "output/repo-paper.md",
                }
            ],
        }
        app = self._build_app()

        with patch(
            "src.web.ops.research_session_service._get_repository",
            return_value=repository,
        ):
            session = research_session_service.get_research_session(app, "cycle-1")

        self.assertIn("observe", session["phase_executions"])
        self.assertEqual(session["deliverables"], [{"name": "repo-paper.md"}])
        self.assertEqual(session["metadata"]["analysis_summary"]["status"], "stable")

    def test_get_research_observe_graph_reads_contract_graph(self):
        repository = _FakeSessionRepository()
        repository.full_snapshots["cycle-graph"] = {
            "cycle_id": "cycle-graph",
            "cycle_name": "图谱研究",
            "description": "图谱描述",
            "status": "completed",
            "current_phase": "reflect",
            "research_objective": "图谱目标",
            "metadata": {},
            "phase_executions": [
                {
                    "phase": "observe",
                    "status": "completed",
                    "input": {},
                    "output": {
                        "semantic_graph": {
                            "nodes": [{"id": "node-1"}],
                            "edges": [
                                {
                                    "source": "node-1",
                                    "target": "node-2",
                                    "relation": "contains",
                                }
                            ],
                        },
                        "graph_statistics": {"nodes_count": 1, "edges_count": 1},
                    },
                }
            ],
        }
        app = self._build_app()

        with patch(
            "src.web.ops.research_session_service._get_repository",
            return_value=repository,
        ):
            graph = research_session_service.get_research_observe_graph(
                app, "cycle-graph"
            )

        self.assertEqual(graph["statistics"]["nodes_count"], 1)
        self.assertEqual(graph["nodes"][0]["id"], "node-1")
        self.assertEqual(graph["edges"][0]["relation"], "contains")

    def test_execute_research_phase_returns_runtime_fallback_when_snapshot_stale(self):
        repository = _FakeSessionRepository()
        repository.sessions["cycle-1"] = {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "description": "测试描述",
            "status": "pending",
            "current_phase": "observe",
            "research_objective": "测试目标",
            "research_scope": "方剂",
            "researchers": ["alice"],
            "metadata": {"phase_contexts": {}, "completed_phases": []},
            "outcomes": [],
            "deliverables": [],
        }
        app = self._build_app()

        with (
            patch(
                "src.web.ops.research_session_service._get_repository",
                return_value=repository,
            ),
            patch(
                "src.web.ops.research_session_service.ResearchRuntimeService",
                _FakeRuntimeService,
            ),
        ):
            execution = research_session_service.execute_research_phase(
                app,
                "cycle-1",
                "hypothesis",
                phase_context={"max_hypotheses": 3},
            )

        self.assertEqual(len(_FakeRuntimeService.instances), 1)
        self.assertEqual(
            _FakeRuntimeService.instances[0].config["runtime_profile"], "web_research"
        )
        self.assertEqual(
            _FakeRuntimeService.instances[0].config["phases"], ["observe", "hypothesis"]
        )
        self.assertEqual(
            _FakeRuntimeService.instances[0].config["researchers"], ["alice"]
        )
        self.assertEqual(_FakeRuntimeService.runs[0]["cycle_id"], "cycle-1")
        self.assertEqual(
            _FakeRuntimeService.runs[0]["phase_contexts"]["hypothesis"][
                "max_hypotheses"
            ],
            3,
        )

        cycle = execution["cycle"]
        self.assertEqual(cycle["status"], "active")
        self.assertEqual(cycle["current_phase"], "experiment")
        self.assertIn("observe", cycle["phase_executions"])
        self.assertIn("hypothesis", cycle["phase_executions"])
        self.assertEqual(
            cycle["metadata"]["analysis_summary"]["completed_phases"],
            ["observe", "hypothesis"],
        )
        self.assertEqual(
            cycle["metadata"]["phase_contexts"]["hypothesis"]["max_hypotheses"], 3
        )
        self.assertEqual(execution["phase_result"]["phase"], "hypothesis")

    def test_execute_research_phase_state_config_fallback_does_not_inject_local_runtime_profile(
        self,
    ):
        repository = _FakeSessionRepository()
        repository.sessions["cycle-1"] = {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "description": "测试描述",
            "status": "pending",
            "current_phase": "observe",
            "research_objective": "测试目标",
            "research_scope": "方剂",
            "researchers": [],
            "metadata": {"phase_contexts": {}, "completed_phases": []},
            "outcomes": [],
            "deliverables": [],
        }
        app = FastAPI()
        app.state.config = {"models": {"llm": {"provider": "local"}}}

        with (
            patch(
                "src.web.ops.research_session_service._get_repository",
                return_value=repository,
            ),
            patch(
                "src.web.ops.research_session_service.ResearchRuntimeService",
                _FakeRuntimeService,
            ),
        ):
            execution = research_session_service.execute_research_phase(
                app, "cycle-1", "observe"
            )

        self.assertEqual(len(_FakeRuntimeService.instances), 1)
        self.assertEqual(
            _FakeRuntimeService.instances[0].config["pipeline_config"]["models"]["llm"][
                "provider"
            ],
            "local",
        )
        self.assertNotIn("runtime_profile", _FakeRuntimeService.instances[0].config)
        self.assertEqual(execution["phase_result"]["phase"], "observe")

    def test_execute_research_phase_injects_learning_feedback_replay(self):
        repository = _FakeSessionRepository()
        repository.sessions["cycle-1"] = {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "description": "测试描述",
            "status": "pending",
            "current_phase": "observe",
            "research_objective": "测试目标",
            "research_scope": "方剂",
            "researchers": ["alice"],
            "metadata": {"phase_contexts": {}, "completed_phases": []},
            "outcomes": [],
            "deliverables": [],
            "learning_feedback_library": {
                "contract_version": "research-feedback-library.v1",
                "summary": {"record_count": 3},
                "replay_feedback": {
                    "status": "completed",
                    "iteration_number": 4,
                    "learning_summary": {
                        "cycle_trend": "improving",
                        "tuned_parameters": {
                            "max_concurrent_tasks": 5,
                            "quality_threshold": 0.76,
                        },
                    },
                    "quality_assessment": {"overall_cycle_score": 0.88},
                },
                "records": [],
            },
        }
        app = self._build_app()

        with (
            patch(
                "src.web.ops.research_session_service._get_repository",
                return_value=repository,
            ),
            patch(
                "src.web.ops.research_session_service.ResearchRuntimeService",
                _FakeRuntimeService,
            ),
        ):
            research_session_service.execute_research_phase(app, "cycle-1", "observe")

        pipeline_config = _FakeRuntimeService.instances[0].config["pipeline_config"]
        self.assertEqual(
            pipeline_config["previous_iteration_feedback"]["iteration_number"], 4
        )
        self.assertEqual(
            pipeline_config["learned_runtime_parameters"]["max_concurrent_tasks"], 5
        )


if __name__ == "__main__":
    unittest.main()
