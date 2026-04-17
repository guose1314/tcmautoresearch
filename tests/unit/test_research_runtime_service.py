import unittest
from importlib import import_module

from src.orchestration.research_orchestrator import OrchestrationResult
from src.orchestration.research_runtime_service import (
    ResearchRuntimeResult,
    ResearchRuntimeService,
)


class _FakeCycle:
    def __init__(self):
        self.cycle_id = "cycle-runtime-1"
        self.cycle_name = "runtime-demo"
        self.phase_executions = {}


class _FakePipeline:
    def __init__(self, config=None):
        self.config = config or {}
        self.cycle = _FakeCycle()
        self.completed = False
        self.cleaned = False
        self.create_cycle_kwargs = {}

    def create_research_cycle(self, **kwargs):
        self.create_cycle_kwargs = dict(kwargs)
        cycle_id = kwargs.get("cycle_id")
        if cycle_id:
            self.cycle.cycle_id = cycle_id
        return self.cycle

    def start_research_cycle(self, _cycle_id):
        return True

    def execute_research_phase(self, cycle_id, phase, phase_context=None):
        phase_context = dict(phase_context or {})
        result = {
            "phase": phase.value,
            "status": "completed",
            "results": {},
            "artifacts": [],
            "metadata": {
                "received_question": phase_context.get("question"),
                "received_phase_context": phase_context,
            },
            "error": None,
        }
        if phase.value == "observe":
            result["results"].update(
                {
                    "observations": ["obs-1"],
                    "findings": ["finding-1"],
                    "literature_pipeline": {"record_count": 2},
                }
            )
        if phase.value == "publish":
            result["results"].update(
                {
                    "deliverables": ["Markdown 论文初稿"],
                    "abstract": "test abstract",
                    "analysis_results": {"statistical_analysis": {"p_value": 0.01}},
                    "research_artifact": {"evidence": [{"id": "ev-1"}]},
                    "output_files": {"markdown": "output/research.md"},
                }
            )
            result["artifacts"] = [{"name": "markdown", "path": "output/research.md", "type": "file"}]
            result["metadata"].update({"report_count": 1, "report_error_count": 0})
        self.cycle.phase_executions[phase] = {"result": result}
        return result

    def complete_research_cycle(self, _cycle_id):
        self.completed = True
        return True

    def cleanup(self):
        self.cleaned = True
        return True

    def get_learning_strategy(self):
        learning_strategy = self.config.get("learning_strategy")
        if isinstance(learning_strategy, dict):
            return dict(learning_strategy)
        return {}

    def get_previous_iteration_feedback(self):
        previous_feedback = self.config.get("previous_iteration_feedback")
        if isinstance(previous_feedback, dict):
            return dict(previous_feedback)
        return {}

    def _serialize_cycle(self, cycle):
        return {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "phase_executions": {
                phase.value: payload for phase, payload in cycle.phase_executions.items()
            },
        }


class _FailingObservePipeline(_FakePipeline):
    def execute_research_phase(self, cycle_id, phase, phase_context=None):
        if phase.value == "observe":
            raise RuntimeError("observe boom")
        return super().execute_research_phase(cycle_id, phase, phase_context)


class _SkippedExecutionPipeline(_FakePipeline):
    def execute_research_phase(self, cycle_id, phase, phase_context=None):
        if phase.value == "experiment_execution":
            result = {
                "phase": phase.value,
                "status": "skipped",
                "metadata": {"received_question": phase_context.get("question")},
                "execution_status": "not_executed",
                "real_world_validation_status": "not_started",
            }
            self.cycle.phase_executions[phase] = {"result": result}
            return result
        return super().execute_research_phase(cycle_id, phase, phase_context)


class TestResearchRuntimeService(unittest.TestCase):
    def test_run_returns_shared_orchestration_and_raw_phase_results(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["observe", "publish"],
            }
        )

        events = []

        def emit(event_type, payload):
            events.append((event_type, payload))

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run(
                "桂枝汤研究",
                phase_contexts={
                    "observe": {"run_literature_retrieval": True},
                    "publish": {"allow_pipeline_citation_fallback": False},
                },
                emit=emit,
            )
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        orchestration = result.orchestration_result
        self.assertEqual(orchestration.status, "completed")
        self.assertEqual(orchestration.cycle_id, "cycle-runtime-1")
        self.assertEqual(list(result.phase_results.keys()), ["observe", "publish"])
        self.assertIn("observe", result.cycle_snapshot["phase_executions"])
        self.assertEqual(result.phase_results["observe"]["metadata"]["received_question"], "桂枝汤研究")
        self.assertIn("statistical_analysis", orchestration.analysis_results)
        self.assertIn("evidence", orchestration.research_artifact)
        self.assertEqual([name for name, _payload in events][-1], "job_completed")

    def test_run_applies_publish_report_policy_through_shared_runtime(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["publish"],
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run(
                "桂枝汤研究",
                phase_contexts={
                    "publish": {"allow_pipeline_citation_fallback": False},
                },
                report_output_formats=["markdown", "docx"],
                report_output_dir="output/research_reports",
            )
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        publish_context = result.phase_results["publish"]["metadata"]["received_phase_context"]
        self.assertEqual(publish_context["report_output_formats"], ["markdown", "docx"])
        self.assertEqual(publish_context["report_output_dir"], "output/research_reports")
        self.assertFalse(publish_context["allow_pipeline_citation_fallback"])

    def test_run_result_can_build_session_result_contract(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["observe", "publish"],
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run("桂枝汤研究")
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        session_result = result.session_result
        self.assertEqual(session_result["session_id"], "cycle-runtime-1")
        self.assertEqual(session_result["cycle_id"], "cycle-runtime-1")
        self.assertEqual(session_result["question"], "桂枝汤研究")
        self.assertEqual(session_result["executed_phases"], ["observe", "publish"])
        self.assertEqual(
            session_result["metadata"]["cycle_name"],
            result.orchestration_result.pipeline_metadata["cycle_name"],
        )
        self.assertEqual(session_result["report_outputs"]["markdown"], "output/research.md")
        self.assertEqual(session_result["reports"]["output_files"]["markdown"], "output/research.md")
        self.assertEqual(session_result["reports"]["report_count"], 1)
        self.assertEqual(session_result["deliverables"], ["Markdown 论文初稿"])
        self.assertIn("statistical_analysis", session_result["analysis_results"])
        self.assertIn("evidence", session_result["research_artifact"])
        self.assertIn("observe", session_result["phase_results"])

    def test_session_result_uses_cycle_snapshot_metadata_analysis_summary(self):
        orchestration_result = OrchestrationResult(
            topic="桂枝汤研究",
            cycle_id="cycle-runtime-2",
            status="completed",
            started_at="2026-04-17T10:00:00",
            completed_at="2026-04-17T10:05:00",
            total_duration_sec=300.0,
            phases=[],
            pipeline_metadata={"cycle_name": "runtime-demo"},
        )
        runtime_result = ResearchRuntimeResult(
            orchestration_result=orchestration_result,
            phase_results={
                "publish": {
                    "phase": "publish",
                    "status": "completed",
                    "results": {
                        "deliverables": ["Markdown IMRD 报告"],
                        "analysis_results": {"statistical_analysis": {"p_value": 0.02}},
                        "research_artifact": {"evidence": [{"id": "ev-2"}]},
                        "output_files": {"imrd_markdown": "output/imrd.md"},
                    },
                    "artifacts": [{"name": "imrd_markdown", "path": "output/imrd.md", "type": "file"}],
                    "metadata": {"report_count": 1, "report_error_count": 0},
                    "error": None,
                }
            },
            cycle_snapshot={
                "cycle_id": "cycle-runtime-2",
                "deliverables": ["Markdown IMRD 报告"],
                "metadata": {
                    "analysis_summary": {
                        "status": "stable",
                        "completed_phase_count": 2,
                        "deliverable_count": 1,
                    }
                },
            },
        )

        session_result = runtime_result.session_result

        self.assertEqual(session_result["analysis_summary"]["status"], "stable")
        self.assertEqual(session_result["metadata"]["analysis_summary"]["deliverable_count"], 1)
        self.assertEqual(session_result["report_outputs"]["imrd_markdown"], "output/imrd.md")
        self.assertEqual(session_result["reports"]["report_count"], 1)
        self.assertEqual(session_result["deliverables"], ["Markdown IMRD 报告"])

    def test_runtime_profile_applies_demo_research_defaults(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "runtime_profile": "demo_research",
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run("桂枝汤研究")
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        self.assertEqual(service.phase_names, ["observe"])
        self.assertEqual(list(result.phase_results.keys()), ["observe"])
        self.assertEqual(result.orchestration_result.pipeline_metadata["scope"], "中医药")
        self.assertRegex(result.orchestration_result.pipeline_metadata["cycle_name"], r"^research_\d+$")

    def test_run_supports_timestamp_cycle_name_strategy(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["observe"],
                "default_cycle_name_mode": "timestamp",
                "default_cycle_name_prefix": "research",
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run("桂枝汤研究")
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        cycle_name = result.orchestration_result.pipeline_metadata["cycle_name"]
        self.assertRegex(cycle_name, r"^research_\d+$")

    def test_run_marks_partial_and_emits_skipped_after_failure(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["observe", "publish"],
                "stop_on_failure": True,
            }
        )

        events = []

        def emit(event_type, payload):
            events.append((event_type, payload))

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FailingObservePipeline
            result = service.run("失败测试", emit=emit)
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        orchestration = result.orchestration_result
        self.assertEqual(orchestration.status, "partial")
        self.assertEqual(orchestration.phases[0].status, "failed")
        self.assertEqual(orchestration.phases[1].status, "skipped")
        self.assertEqual(result.phase_results["observe"]["error"], "observe boom")
        self.assertIn("phase_skipped", [name for name, _payload in events])

    def test_run_preserves_explicit_cycle_id(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["observe"],
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run("桂枝汤研究", cycle_id="legacy-cycle-42")
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        self.assertEqual(result.orchestration_result.cycle_id, "legacy-cycle-42")
        self.assertEqual(result.cycle_snapshot["cycle_id"], "legacy-cycle-42")

    def test_run_preserves_skipped_phase_status_without_promoting_to_completed(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {},
                "phases": ["observe", "experiment_execution", "publish"],
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _SkippedExecutionPipeline
            result = service.run("桂枝汤研究")
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        orchestration = result.orchestration_result
        self.assertEqual(orchestration.status, "completed")
        self.assertEqual(orchestration.phases[1].phase, "experiment_execution")
        self.assertEqual(orchestration.phases[1].status, "skipped")
        self.assertEqual(result.phase_results["experiment_execution"]["status"], "skipped")

    def test_run_injects_learning_strategy_into_phase_context(self):
        service = ResearchRuntimeService(
            {
                "pipeline_config": {
                    "learning_strategy": {
                        "strategy_source": "self_learning_engine",
                        "tuned_parameters": {"quality_threshold": 0.74},
                    },
                    "previous_iteration_feedback": {
                        "iteration_number": 3,
                        "learning_summary": {"cycle_trend": "improving"},
                    },
                },
                "phases": ["observe"],
            }
        )

        research_pipeline_module = import_module("src.research.research_pipeline")

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = _FakePipeline
            result = service.run("桂枝汤研究")
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

        observe_context = result.phase_results["observe"]["metadata"]["received_phase_context"]
        self.assertEqual(
            observe_context["learning_strategy"]["tuned_parameters"]["quality_threshold"],
            0.74,
        )
        self.assertEqual(observe_context["previous_iteration_feedback"]["iteration_number"], 3)
        self.assertTrue(result.orchestration_result.pipeline_metadata["learning_strategy_active"])
