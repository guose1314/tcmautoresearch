import unittest
from copy import deepcopy
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.orchestration.research_orchestrator import OrchestrationResult, PhaseOutcome
from src.orchestration.research_runtime_service import ResearchRuntimeResult
from src.web.auth import get_current_user
from src.web.ops.legacy_research_runtime import LegacyResearchRuntimeStore
from src.web.routes.analysis import router as analysis_router
from src.web.routes.research import router as research_router


class _FakeRuntimeService:
    instances = []
    runs = []
    next_status = "completed"

    def __init__(self, config=None):
        self.config = deepcopy(config or {})
        type(self).instances.append(self)

    def run(self, topic, **kwargs):
        phases = list(self.config.get("phases") or [])
        type(self).runs.append({
            "topic": topic,
            "config": deepcopy(self.config),
            **deepcopy(kwargs),
        })

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
                    "edges": [{"source": "node-1", "target": "node-2", "relation": "contains"}],
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
            started_at="2026-04-12T20:00:00",
            completed_at="2026-04-12T20:00:05",
            total_duration_sec=5.0,
            phases=[
                PhaseOutcome(
                    phase=phase_name,
                    status="failed" if phase_name == target_phase and type(self).next_status in {"failed", "partial"} else "completed",
                    duration_sec=1.0,
                    error="boom" if phase_name == target_phase and type(self).next_status in {"failed", "partial"} else "",
                )
                for phase_name in phases
            ],
            pipeline_metadata={"cycle_name": kwargs.get("cycle_name")},
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


class _FakeLegacyStore:
    def __init__(self):
        self.created_payload = None
        self.executed_payload = None

    def create_session(self, **kwargs):
        self.created_payload = deepcopy(kwargs)
        return {
            "cycle_id": "cycle-1",
            "cycle_name": kwargs["cycle_name"],
            "research_objective": kwargs["objective"],
            "status": "pending",
            "current_phase": "observe",
        }

    def get_session(self, cycle_id):
        if cycle_id != "cycle-1":
            return None
        return {
            "cycle_id": "cycle-1",
            "cycle_name": "测试研究",
            "phase_executions": {
                "observe": {
                    "result": {
                        "semantic_graph": {
                            "nodes": [{"id": "node-1"}],
                            "edges": [{"source": "node-1", "target": "node-2"}],
                        },
                        "graph_statistics": {"nodes_count": 1},
                    }
                }
            },
        }

    def list_sessions(self):
        return [{"cycle_id": "cycle-1", "cycle_name": "测试研究", "status": "active", "current_phase": "analyze", "started_at": None, "research_objective": "测试目标", "analysis_summary": {}}]

    def execute_phase(self, cycle_id, phase_name, **kwargs):
        self.executed_payload = {
            "cycle_id": cycle_id,
            "phase_name": phase_name,
            **deepcopy(kwargs),
        }
        return {
            "cycle": {"cycle_id": cycle_id, "status": "active", "current_phase": "analyze"},
            "phase_result": {"phase": phase_name, "status": "completed"},
        }

    def get_observe_graph(self, cycle_id):
        if cycle_id != "cycle-1":
            return None
        return {
            "nodes": [{"id": "node-1"}],
            "edges": [{"source": "node-1", "target": "node-2"}],
            "statistics": {"nodes_count": 1},
        }


class _FakeSessionRepository:
    def __init__(self):
        self.sessions = {}
        self.full_snapshots = {}
        self.created_payloads = []
        self.updated_payloads = []

    def create_session(self, payload):
        record = deepcopy(payload)
        self.created_payloads.append(record)
        self.sessions[record["cycle_id"]] = record
        return deepcopy(record)

    def get_session(self, cycle_id):
        record = self.sessions.get(cycle_id)
        return deepcopy(record) if record is not None else None

    def update_session(self, cycle_id, updates):
        record = deepcopy(self.sessions.get(cycle_id) or {"cycle_id": cycle_id})
        record.update(deepcopy(updates))
        self.sessions[cycle_id] = record
        self.updated_payloads.append((cycle_id, deepcopy(updates)))
        return deepcopy(record)

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


class TestLegacyResearchRuntimeStore(unittest.TestCase):
    def setUp(self):
        _FakeRuntimeService.instances.clear()
        _FakeRuntimeService.runs.clear()
        _FakeRuntimeService.next_status = "completed"

    def test_execute_phase_uses_cumulative_runtime_service(self):
        store = LegacyResearchRuntimeStore({"pipeline_config": {"models": {"llm": {"provider": "local"}}}})
        cycle = store.create_session(
            cycle_name="测试研究",
            description="测试描述",
            objective="测试目标",
            scope="方剂",
            researchers=["alice"],
        )

        with patch("src.web.ops.legacy_research_runtime.ResearchRuntimeService", _FakeRuntimeService):
            execution = store.execute_phase(
                cycle["cycle_id"],
                "hypothesis",
                phase_context={"max_hypotheses": 3},
            )

        self.assertEqual(len(_FakeRuntimeService.instances), 1)
        self.assertEqual(
            _FakeRuntimeService.instances[0].config["phases"],
            ["observe", "hypothesis"],
        )
        self.assertEqual(
            _FakeRuntimeService.instances[0].config["researchers"],
            ["alice"],
        )
        self.assertEqual(_FakeRuntimeService.runs[0]["topic"], "测试目标")
        self.assertEqual(_FakeRuntimeService.runs[0]["cycle_id"], cycle["cycle_id"])
        self.assertEqual(
            _FakeRuntimeService.runs[0]["phase_contexts"]["hypothesis"]["max_hypotheses"],
            3,
        )
        self.assertEqual(execution["phase_result"]["phase"], "hypothesis")

        stored = store.get_session(cycle["cycle_id"])
        self.assertEqual(stored["status"], "active")
        self.assertEqual(stored["current_phase"], "experiment")
        self.assertIn("observe", stored["phase_executions"])
        self.assertIn("hypothesis", stored["phase_executions"])
        self.assertEqual(
            stored["metadata"]["analysis_summary"]["completed_phases"],
            ["observe", "hypothesis"],
        )
        self.assertEqual(stored["metadata"]["runtime_cycle_id"], cycle["cycle_id"])

    def test_execute_final_phase_marks_session_completed(self):
        store = LegacyResearchRuntimeStore({"pipeline_config": {}})
        cycle = store.create_session(
            cycle_name="测试研究",
            description="测试描述",
            objective="测试目标",
            scope="方剂",
            researchers=None,
        )

        with patch("src.web.ops.legacy_research_runtime.ResearchRuntimeService", _FakeRuntimeService):
            store.execute_phase(cycle["cycle_id"], "reflect")

        stored = store.get_session(cycle["cycle_id"])
        self.assertEqual(stored["status"], "completed")
        self.assertEqual(stored["current_phase"], "reflect")
        self.assertEqual(stored["deliverables"], [{"name": "paper.md"}])

    def test_get_observe_graph_reads_nested_phase_result(self):
        store = LegacyResearchRuntimeStore({"pipeline_config": {}})
        cycle = store.create_session(
            cycle_name="测试研究",
            description="测试描述",
            objective="测试目标",
            scope="方剂",
            researchers=None,
        )

        with patch("src.web.ops.legacy_research_runtime.ResearchRuntimeService", _FakeRuntimeService):
            store.execute_phase(cycle["cycle_id"], "observe")

        graph = store.get_observe_graph(cycle["cycle_id"])
        self.assertEqual(graph["statistics"]["nodes_count"], 1)
        self.assertEqual(graph["nodes"][0]["id"], "node-1")

    def test_create_session_persists_pending_session_to_repository(self):
        repository = _FakeSessionRepository()
        store = LegacyResearchRuntimeStore({"pipeline_config": {}}, repository=repository)

        cycle = store.create_session(
            cycle_name="测试研究",
            description="测试描述",
            objective="测试目标",
            scope="方剂",
            researchers=["alice"],
        )

        self.assertEqual(repository.created_payloads[0]["cycle_id"], cycle["cycle_id"])
        self.assertEqual(repository.sessions[cycle["cycle_id"]]["status"], "pending")

    def test_get_session_restores_repository_snapshot(self):
        repository = _FakeSessionRepository()
        cycle_id = "repo-cycle-1"
        repository.sessions[cycle_id] = {
            "cycle_id": cycle_id,
            "cycle_name": "仓储研究",
            "description": "仓储描述",
            "status": "completed",
            "current_phase": "reflect",
            "research_objective": "仓储目标",
            "metadata": {},
        }
        repository.full_snapshots[cycle_id] = {
            "cycle_id": cycle_id,
            "cycle_name": "仓储研究",
            "description": "仓储描述",
            "status": "completed",
            "current_phase": "reflect",
            "research_objective": "仓储目标",
            "metadata": {},
            "phase_executions": [
                {
                    "phase": "observe",
                    "status": "completed",
                    "input": {},
                    "output": {
                        "semantic_graph": {
                            "nodes": [{"id": "repo-node"}],
                            "edges": [{"source": "repo-node", "target": "repo-node-2"}],
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
        store = LegacyResearchRuntimeStore({"pipeline_config": {}}, repository=repository)

        restored = store.get_session(cycle_id)

        self.assertEqual(restored["deliverables"], [{"name": "repo-paper.md"}])
        self.assertIn("observe", restored["phase_executions"])
        self.assertEqual(store.get_observe_graph(cycle_id)["nodes"][0]["id"], "repo-node")


class TestLegacyResearchRoutes(unittest.TestCase):
    def _build_app(self, router):
        app = FastAPI()
        app.state.config = {}
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        return app

    def test_research_routes_keep_legacy_contract(self):
        store = _FakeLegacyStore()
        app = self._build_app(research_router)

        with patch("src.web.routes.research.get_legacy_research_store", return_value=store):
            with TestClient(app) as client:
                create_response = client.post(
                    "/api/research/create",
                    json={
                        "cycle_name": "测试研究",
                        "description": "测试描述",
                        "objective": "测试目标",
                        "scope": "方剂",
                    },
                )
                self.assertEqual(create_response.status_code, 201)
                self.assertEqual(create_response.json()["cycle"]["cycle_id"], "cycle-1")
                self.assertEqual(store.created_payload["objective"], "测试目标")

                detail_response = client.get("/api/research/cycle-1")
                self.assertEqual(detail_response.status_code, 200)
                self.assertEqual(detail_response.json()["cycle"]["cycle_id"], "cycle-1")

                execute_response = client.post(
                    "/api/research/cycle-1/execute",
                    json={"phase": "analyze", "phase_context": {"top_k": 5}},
                )
                self.assertEqual(execute_response.status_code, 200)
                self.assertEqual(execute_response.json()["result"]["phase"], "analyze")
                self.assertEqual(store.executed_payload["phase_name"], "analyze")
                self.assertEqual(store.executed_payload["phase_context"]["top_k"], 5)
                self.assertIsNotNone(store.executed_payload["emit"])

                list_response = client.get("/api/research/list")
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(list_response.json()["total"], 1)

    def test_analysis_graph_route_reads_same_legacy_store(self):
        store = _FakeLegacyStore()
        app = self._build_app(analysis_router)

        with patch("src.web.routes.analysis.get_legacy_research_store", return_value=store):
            with TestClient(app) as client:
                response = client.get("/api/analysis/graph/cycle-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["research_id"], "cycle-1")
        self.assertEqual(payload["graph"]["statistics"]["nodes_count"], 1)


if __name__ == "__main__":
    unittest.main()
