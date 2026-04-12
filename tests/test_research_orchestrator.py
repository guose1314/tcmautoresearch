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
    if phase == "publish":
        return {
            "phase": "publish",
            "deliverables": ["Markdown 论文初稿", "DOCX 论文初稿"],
            "abstract": "这是一个摘要",
            "output_files": {
                "markdown": "C:/workspace/output/papers/demo.md",
                "docx": "C:/workspace/output/papers/demo.docx",
            },
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

    def test_experiment_accepts_explicit_protocol_inputs(self):
        ctx = topic_to_phase_context(
            "补中益气汤研究",
            ResearchPhase.EXPERIMENT,
            study_type="cohort",
            primary_outcome="复发率",
            intervention="补中益气汤颗粒",
            comparison="常规治疗",
        )
        self.assertEqual(ctx["study_type"], "cohort")
        self.assertEqual(ctx["primary_outcome"], "复发率")
        self.assertEqual(ctx["intervention"], "补中益气汤颗粒")
        self.assertEqual(ctx["comparison"], "常规治疗")

    def test_experiment_infers_protocol_inputs_when_not_provided(self):
        ctx = topic_to_phase_context("四君子汤网络药理机制研究", ResearchPhase.EXPERIMENT)
        self.assertEqual(ctx["study_type"], "network_pharmacology")
        self.assertIn("靶点", ctx["primary_outcome"])

    def test_experiment_execution_defaults_to_external_import_mode(self):
        ctx = topic_to_phase_context("四君子汤网络药理机制研究", ResearchPhase.EXPERIMENT_EXECUTION)
        self.assertEqual(ctx["execution_mode"], "external_import")
        self.assertTrue(ctx["external_execution_required"])


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
        self.assertEqual(len(result.phases), 7)
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
    def test_publish_summary_preserves_output_files(self, MockPipeline):
        MockPipeline.return_value = _mock_pipeline()
        orch = ResearchOrchestrator()
        result = orch.run("桂枝汤")
        publish_outcome = next(p for p in result.phases if p.phase == "publish")
        self.assertEqual(publish_outcome.summary["deliverable_count"], 2)
        self.assertIn("output_files", publish_outcome.summary)
        self.assertIn("markdown", publish_outcome.summary["output_files"])
        self.assertIn("docx", publish_outcome.summary["output_files"])

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
        for ph in ["hypothesis", "experiment", "experiment_execution", "analyze", "publish", "reflect"]:
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

    def test_extract_publish_result_highlights_reads_standard_results(self):
        publish_result = {
            "phase": "publish",
            "status": "completed",
            "results": {
                "analysis_results": {"statistical_analysis": {"p_value": 0.003}},
                "research_artifact": {"hypothesis": [{"title": "桂枝汤调和营卫假设"}]},
            },
            "artifacts": [],
            "metadata": {},
            "error": None,
        }
        cycle = MagicMock()
        cycle.phase_executions = {ResearchPhase.PUBLISH: {"result": publish_result}}
        pipeline = MagicMock()
        pipeline.ResearchPhase = ResearchPhase
        pipeline.research_cycles = {"cycle-1": cycle}

        highlights = ResearchOrchestrator._extract_publish_result_highlights(pipeline, "cycle-1")

        self.assertEqual(highlights["analysis_results"], publish_result["results"]["analysis_results"])
        self.assertEqual(highlights["research_artifact"], publish_result["results"]["research_artifact"])
        self.assertEqual(publish_result["metadata"].get("deprecated_field_fallbacks"), None)


class TestOrchestratorObserveHypothesisExperimentSummary(unittest.TestCase):
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_real_pipeline_three_phase_summary(self, mock_search, mock_close):
        mock_close.return_value = None
        mock_search.return_value = {
            "query": "四君子汤与脾气虚证关联",
            "sources": ["pubmed", "arxiv"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "Traditional chinese medicine formula improves efficacy and safety",
                    "authors": ["A"],
                    "year": 2023,
                    "doi": "10.1000/test1",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "abstract": "Randomized cohort study of traditional chinese medicine formula shows efficacy safety response and machine learning support.",
                },
                {
                    "source": "arxiv",
                    "title": "Machine learning network for TCM syndrome response",
                    "authors": ["B"],
                    "year": 2024,
                    "doi": "",
                    "url": "https://arxiv.org/abs/1234",
                    "abstract": "Network analysis for herb formula response with risk and effectiveness outcomes.",
                },
            ],
            "query_plans": [],
            "source_stats": {
                "pubmed": {"count": 1, "mode": "open_api", "source_name": "PubMed"},
                "arxiv": {"count": 1, "mode": "open_api", "source_name": "arXiv"},
            },
            "errors": [],
        }

        orch = ResearchOrchestrator(
            {
                "phases": ["observe", "hypothesis", "experiment"],
                "pipeline_config": {
                    "literature_retrieval": {"enabled": True, "max_results_per_source": 2},
                    "hypothesis_engine_config": {"max_hypotheses": 2, "max_validation_iterations": 1},
                },
            }
        )

        result = orch.run(
            "四君子汤与脾气虚证关联",
            phase_contexts={
                "observe": {
                    "run_literature_retrieval": True,
                    "literature_query": "四君子汤与脾气虚证关联",
                    "run_preprocess_and_extract": False,
                    "use_ctext_whitelist": False,
                },
                "hypothesis": {
                    "entities": [
                        {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                        {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                    ],
                    "contradictions": ["存在个别样本偏差"],
                },
            },
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual([phase.phase for phase in result.phases], ["observe", "hypothesis", "experiment"])

        observe_summary = next(phase.summary for phase in result.phases if phase.phase == "observe")
        hypothesis_summary = next(phase.summary for phase in result.phases if phase.phase == "hypothesis")
        experiment_summary = next(phase.summary for phase in result.phases if phase.phase == "experiment")

        self.assertEqual(observe_summary["literature_records"], 2)
        self.assertGreaterEqual(hypothesis_summary["hypothesis_count"], 1)
        self.assertEqual(experiment_summary["protocol_design_count"], 1)
        self.assertEqual(experiment_summary["design_completion_rate"], 1.0)
        self.assertTrue(experiment_summary["selected_hypothesis_id"])
        self.assertEqual(experiment_summary["evidence_record_count"], 2)
        self.assertGreater(experiment_summary["weighted_evidence_score"], 0.0)
        self.assertEqual(experiment_summary["execution_status"], "not_executed")
        self.assertEqual(experiment_summary["real_world_validation_status"], "not_started")

    @patch("src.research.research_pipeline.ResearchPipeline._run_clinical_gap_analysis")
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_experiment_summary_includes_high_priority_gap_methodology_and_sample_size(self, mock_search, mock_close, mock_gap):
        mock_close.return_value = None
        mock_search.return_value = {
            "query": "四君子汤与脾气虚证关联",
            "sources": ["pubmed", "arxiv"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "Traditional chinese medicine formula improves efficacy and safety",
                    "authors": ["A"],
                    "year": 2023,
                    "doi": "10.1000/test1",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "abstract": "Randomized cohort study of traditional chinese medicine formula shows efficacy safety response and machine learning support.",
                },
                {
                    "source": "arxiv",
                    "title": "Machine learning network for TCM syndrome response",
                    "authors": ["B"],
                    "year": 2024,
                    "doi": "",
                    "url": "https://arxiv.org/abs/1234",
                    "abstract": "Network analysis for herb formula response with risk and effectiveness outcomes.",
                },
            ],
            "query_plans": [],
            "source_stats": {
                "pubmed": {"count": 1, "mode": "open_api", "source_name": "PubMed"},
                "arxiv": {"count": 1, "mode": "open_api", "source_name": "arXiv"},
            },
            "errors": [],
        }
        mock_gap.return_value = {
            "report": "gap report",
            "gaps": [
                {"dimension": "outcome", "title": "关键结局覆盖不足", "limitation": "安全性证据弱", "priority": "高"},
                {"dimension": "method", "title": "研究设计单一", "limitation": "缺少多中心对照", "priority": "中"},
            ],
            "priority_summary": {
                "counts": {"高": 1, "中": 1, "低": 0},
                "highest_priority": "高",
                "total_gaps": 2,
            },
        }

        orch = ResearchOrchestrator(
            {
                "phases": ["observe", "hypothesis", "experiment"],
                "pipeline_config": {
                    "literature_retrieval": {"enabled": True, "max_results_per_source": 2},
                    "hypothesis_engine_config": {"max_hypotheses": 2, "max_validation_iterations": 1},
                },
            }
        )

        result = orch.run(
            "四君子汤与脾气虚证关联",
            phase_contexts={
                "observe": {
                    "run_literature_retrieval": True,
                    "run_clinical_gap_analysis": True,
                    "literature_query": "四君子汤与脾气虚证关联",
                    "run_preprocess_and_extract": False,
                    "use_ctext_whitelist": False,
                },
                "hypothesis": {
                    "entities": [
                        {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                        {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                    ],
                    "contradictions": ["存在个别样本偏差"],
                },
            },
        )

        experiment_summary = next(phase.summary for phase in result.phases if phase.phase == "experiment")

        self.assertEqual(experiment_summary["methodology"], "high_priority_gap_escalated_validation")
        self.assertGreaterEqual(experiment_summary["sample_size"], 100)
        self.assertEqual(experiment_summary["highest_gap_priority"], "高")


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

    @patch("src.orchestration.research_orchestrator.ResearchPipeline")
    def test_run_research_accepts_explicit_protocol_inputs(self, MockPipeline):
        mock_pl = _mock_pipeline()
        MockPipeline.return_value = mock_pl
        run_research(
            "黄芪颗粒临床研究",
            study_type="rct",
            primary_outcome="疲劳量表评分变化",
            intervention="黄芪颗粒",
            comparison="安慰剂",
        )

        # 默认第 3 次为 experiment 阶段
        experiment_call = mock_pl.execute_research_phase.call_args_list[2]
        experiment_ctx = experiment_call.args[2]
        self.assertEqual(experiment_ctx["study_type"], "rct")
        self.assertEqual(experiment_ctx["primary_outcome"], "疲劳量表评分变化")
        self.assertEqual(experiment_ctx["intervention"], "黄芪颗粒")
        self.assertEqual(experiment_ctx["comparison"], "安慰剂")


if __name__ == "__main__":
    unittest.main()
