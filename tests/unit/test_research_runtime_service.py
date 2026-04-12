import unittest
from importlib import import_module

from src.orchestration.research_runtime_service import ResearchRuntimeService


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
        result = {
            "phase": phase.value,
            "metadata": {"received_question": phase_context.get("question")},
        }
        if phase.value == "observe":
            result.update(
                {
                    "observations": ["obs-1"],
                    "findings": ["finding-1"],
                    "literature_pipeline": {"record_count": 2},
                }
            )
        if phase.value == "publish":
            result.update(
                {
                    "deliverables": [{"name": "markdown"}],
                    "abstract": "test abstract",
                    "analysis_results": {"statistical_analysis": {"p_value": 0.01}},
                    "research_artifact": {"evidence": [{"id": "ev-1"}]},
                }
            )
        self.cycle.phase_executions[phase] = {"result": result}
        return result

    def complete_research_cycle(self, _cycle_id):
        self.completed = True
        return True

    def cleanup(self):
        self.cleaned = True
        return True

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