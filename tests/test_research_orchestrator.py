"""tests/test_research_orchestrator.py — 3.1 ResearchOrchestrator 单元测试"""

import unittest
from unittest.mock import MagicMock, patch

from src.orchestration.research_orchestrator import (
    OrchestrationResult,
    PhaseOutcome,
    ResearchOrchestrator,
    _slug_topic,
    run_research,
    topic_to_phase_context,
)
from src.research.research_pipeline import ResearchPhase

# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _phase_result(phase: str) -> dict:
    """生成各阶段的最小合法结果 dict。"""
    if phase == "observe":
        return {
            "phase": "observe",
            "observations": ["obs1", "obs2"],
            "findings": ["finding1"],
            "corpus_collection": None,
            "ingestion_pipeline": None,
            "literature_pipeline": None,
            "metadata": {"data_source": "manual", "corpus_schema": None},
        }
    if phase == "hypothesis":
        return {
            "phase": "hypothesis",
            "hypotheses": [
                {"hypothesis_id": "h1", "title": "假设A", "status": "validated", "final_score": 0.8},
            ],
            "domain": "tcm",
        }
    return {"phase": phase}


def _mock_pipeline(phases_succeed=None, phases_fail=None):
    """返回一个经过 patch 的 ResearchPipeline mock，用于隔离 Orchestrator 逻辑。"""
    phases_succeed = phases_succeed or []
    phases_fail = phases_fail or []

    mock = MagicMock()
    mock.create_research_cycle.return_value = MagicMock(cycle_id="test_cycle_001")
    mock.start_research_cycle.return_value = True
    mock.cleanup.return_value = True

    def _execute(cycle_id, phase, ctx=None):
        if phase.value in phases_fail:
            return {"phase": phase.value, "error": f"{phase.value} 故意失败"}
        return _phase_result(phase.value)

    mock.execute_research_phase.side_effect = _execute
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# topic_to_phase_context
# ─────────────────────────────────────────────────────────────────────────────

class TestTopicToPhaseContext(unittest.TestCase):
    def test_observe_defaults_disable_network(self):
        ctx = topic_to_phase_context("麻黄汤研究", ResearchPhase.OBSERVE)
        self.assertFalse(ctx["run_literature_retrieval"])
        self.assertFalse(ctx["run_preprocess_and_extract"])
        self.assertFalse(ctx["use_ctext_whitelist"])
        self.assertEqual(ctx["literature_query"], "麻黄汤研究")

    def test_hypothesis_contains_objective(self):
        ctx = topic_to_phase_context("芍药甘草汤", ResearchPhase.HYPOTHESIS)
        self.assertEqual(ctx["research_objective"], "芍药甘草汤")

    def test_all_phases_return_dict(self):
        for phase in ResearchPhase:
            ctx = topic_to_phase_context("test", phase)
            self.assertIsInstance(ctx, dict)
            self.assertIn("research_topic", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# _slug_topic
# ─────────────────────────────────────────────────────────────────────────────

class TestSlugTopic(unittest.TestCase):
    def test_basic_chinese(self):
        slug = _slug_topic("麻黄汤治疗风寒感冒研究")
        self.assertTrue(len(slug) > 0)
        self.assertLessEqual(len(slug), 40)

    def test_empty_fallback(self):
        slug = _slug_topic("!!!")
        self.assertEqual(slug, "research_cycle")

    def test_truncation(self):
        slug = _slug_topic("a" * 100, max_len=10)
        self.assertLessEqual(len(slug), 10)


# ─────────────────────────────────────────────────────────────────────────────
# PhaseOutcome / OrchestrationResult
# ─────────────────────────────────────────────────────────────────────────────

class TestDataclasses(unittest.TestCase):
    def test_phase_outcome_to_dict(self):
        po = PhaseOutcome(phase="observe", status="completed", duration_sec=1.23)
        d = po.to_dict()
        self.assertEqual(d["phase"], "observe")
        self.assertEqual(d["status"], "completed")
        self.assertAlmostEqual(d["duration_sec"], 1.23, places=2)

    def test_orchestration_result_properties(self):
        phases = [
            PhaseOutcome("observe", "completed", 1.0),
            PhaseOutcome("hypothesis", "failed", 0.5, error="err"),
            PhaseOutcome("experiment", "skipped", 0.0),
        ]
        result = OrchestrationResult(
            topic="test",
            cycle_id="c1",
            status="partial",
            started_at="2026-01-01",
            completed_at="2026-01-01",
            total_duration_sec=2.0,
            phases=phases,
            pipeline_metadata={},
        )
        self.assertEqual(result.succeeded_phases, ["observe"])
        self.assertEqual(result.failed_phases, ["hypothesis"])
        d = result.to_dict()
        self.assertEqual(len(d["phases"]), 3)


# ─────────────────────────────────────────────────────────────────────────────
# ResearchOrchestrator.run() — happy path
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorRunHappyPath(unittest.TestCase):
    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_run_returns_orchestration_result(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline()
        orch = ResearchOrchestrator()
        result = orch.run("麻黄汤研究")
        self.assertIsInstance(result, OrchestrationResult)
        self.assertEqual(result.topic, "麻黄汤研究")
        self.assertIsNotNone(result.cycle_id)

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_all_phases_completed(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline()
        orch = ResearchOrchestrator()
        result = orch.run("芍药甘草汤")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.phases), 6)
        self.assertTrue(all(p.status == "completed" for p in result.phases))

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_observe_summary_extracted(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline()
        orch = ResearchOrchestrator()
        result = orch.run("柴胡汤研究")
        obs_outcome = next(p for p in result.phases if p.phase == "observe")
        self.assertEqual(obs_outcome.summary["observation_count"], 2)
        self.assertEqual(obs_outcome.summary["finding_count"], 1)

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_hypothesis_summary_extracted(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline()
        orch = ResearchOrchestrator()
        result = orch.run("桂枝汤")
        hyp_outcome = next(p for p in result.phases if p.phase == "hypothesis")
        self.assertEqual(hyp_outcome.summary["hypothesis_count"], 1)
        self.assertEqual(hyp_outcome.summary["validated_count"], 1)

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_cleanup_called_even_on_happy_path(self, MockPipeline):
        mock_pipeline_instance = _mock_pipeline()
        MockPipeline.return_value = mock_pipeline_instance
        orch = ResearchOrchestrator()
        orch.run("test")
        mock_pipeline_instance.cleanup.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# ResearchOrchestrator.run() — 失败与 stop_on_failure
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorFailureHandling(unittest.TestCase):
    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_stop_on_failure_true_skips_remaining(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline(phases_fail=["observe"])
        orch = ResearchOrchestrator({"stop_on_failure": True})
        result = orch.run("test")
        self.assertEqual(result.status, "partial")
        statuses = {p.phase: p.status for p in result.phases}
        self.assertEqual(statuses["observe"], "failed")
        # 所有后续阶段应被跳过
        for ph in ["hypothesis", "experiment", "analyze", "publish", "reflect"]:
            self.assertEqual(statuses[ph], "skipped", f"{ph} 应为 skipped")

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_stop_on_failure_false_continues(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline(phases_fail=["observe"])
        orch = ResearchOrchestrator({"stop_on_failure": False})
        result = orch.run("test")
        self.assertEqual(result.status, "partial")
        # 其他阶段仍应执行（completed）
        statuses = {p.phase: p.status for p in result.phases}
        self.assertEqual(statuses["observe"], "failed")
        self.assertEqual(statuses["hypothesis"], "completed")

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_phase_exception_captured_as_failed(self, MockPipeline):
        mock_pl = _mock_pipeline()
        mock_pl.execute_research_phase.side_effect = RuntimeError("意外异常")
        MockPipeline.return_value = mock_pl
        orch = ResearchOrchestrator({"stop_on_failure": True})
        result = orch.run("test")
        self.assertEqual(result.phases[0].status, "failed")
        self.assertIn("意外异常", result.phases[0].error)

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_cleanup_called_even_on_failure(self, MockPipeline):
        mock_pl = _mock_pipeline(phases_fail=["observe"])
        MockPipeline.return_value = mock_pl
        orch = ResearchOrchestrator()
        orch.run("test")
        mock_pl.cleanup.assert_called_once()

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_start_cycle_failure_returns_failed(self, MockPipeline):
        mock_pl = _mock_pipeline()
        mock_pl.start_research_cycle.return_value = False
        MockPipeline.return_value = mock_pl
        orch = ResearchOrchestrator()
        result = orch.run("test")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.phases, [])


# ─────────────────────────────────────────────────────────────────────────────
# phase_contexts 覆盖机制
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorPhaseContextOverride(unittest.TestCase):
    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_phase_context_override_passed_to_pipeline(self, MockPipeline):
        mock_pl = _mock_pipeline()
        MockPipeline.return_value = mock_pl
        orch = ResearchOrchestrator()
        orch.run(
            "test",
            phase_contexts={"observe": {"run_literature_retrieval": True, "custom_flag": 42}},
        )
        # 第一次调用 execute_research_phase 应是 OBSERVE 阶段
        first_call_args = mock_pl.execute_research_phase.call_args_list[0]
        ctx_passed = first_call_args.args[2] if len(first_call_args.args) > 2 else first_call_args.kwargs.get("phase_context", {})
        self.assertTrue(ctx_passed.get("run_literature_retrieval"))
        self.assertEqual(ctx_passed.get("custom_flag"), 42)

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_config_default_context_applied(self, MockPipeline):
        mock_pl = _mock_pipeline()
        MockPipeline.return_value = mock_pl
        orch = ResearchOrchestrator({
            "default_observe_context": {"data_source": "local", "max_texts": 5}
        })
        orch.run("test")
        first_call_args = mock_pl.execute_research_phase.call_args_list[0]
        ctx_passed = first_call_args.args[2] if len(first_call_args.args) > 2 else first_call_args.kwargs.get("phase_context", {})
        self.assertEqual(ctx_passed.get("data_source"), "local")
        self.assertEqual(ctx_passed.get("max_texts"), 5)


# ─────────────────────────────────────────────────────────────────────────────
# 子集执行 & 自定义 phases
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorSubsetPhases(unittest.TestCase):
    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_only_observe_and_hypothesis(self, MockPipeline):
        mock_pl = _mock_pipeline()
        MockPipeline.return_value = mock_pl
        orch = ResearchOrchestrator({
            "phases": ["observe", "hypothesis"]
        })
        result = orch.run("test")
        self.assertEqual(len(result.phases), 2)
        self.assertEqual(result.phases[0].phase, "observe")
        self.assertEqual(result.phases[1].phase, "hypothesis")
        self.assertEqual(result.status, "completed")

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_empty_topic_raises(self, MockPipeline):
        orch = ResearchOrchestrator()
        with self.assertRaises(ValueError):
            orch.run("")

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_whitespace_topic_raises(self, MockPipeline):
        orch = ResearchOrchestrator()
        with self.assertRaises(ValueError):
            orch.run("   ")


# ─────────────────────────────────────────────────────────────────────────────
# infer_scope & to_dict roundtrip
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorMisc(unittest.TestCase):
    def test_infer_scope_with_keywords(self):
        orch = ResearchOrchestrator()
        scope = orch._infer_scope("本草纲目中的方剂组成研究")
        self.assertIn("本草", scope)
        self.assertIn("方剂", scope)

    def test_infer_scope_fallback(self):
        orch = ResearchOrchestrator()
        scope = orch._infer_scope("modern pharmacology study")
        self.assertEqual(scope, "中医古籍与现代研究")

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_result_to_dict_is_json_serializable(self, MockPipeline):
        import json
        MockPipeline.return_value = _mock_pipeline()
        orch = ResearchOrchestrator()
        result = orch.run("test")
        d = result.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)
        self.assertIn("test", serialized)


class TestRunResearchSingleEntry(unittest.TestCase):
    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_run_research_returns_orchestration_result(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline()
        result = run_research("麻黄汤研究")
        self.assertIsInstance(result, OrchestrationResult)
        self.assertEqual(result.topic, "麻黄汤研究")

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_run_research_accepts_config_and_phase_override(self, MockPipeline):
        mock_pl = _mock_pipeline()
        MockPipeline.return_value = mock_pl
        run_research(
            "test",
            config={"phases": ["observe"]},
            phase_contexts={"observe": {"run_literature_retrieval": True}},
        )
        self.assertEqual(mock_pl.execute_research_phase.call_count, 1)
        call = mock_pl.execute_research_phase.call_args_list[0]
        ctx_passed = call.args[2]
        self.assertTrue(ctx_passed["run_literature_retrieval"])


if __name__ == "__main__":
    unittest.main()
