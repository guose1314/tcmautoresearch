# tests/test_quality_assessor.py
"""
QualityAssessor 单元测试

覆盖：
  - QualityScore / ComplianceReport 数据结构
  - assess_quality() — 评分逻辑
  - calculate_metrics() — 指标计算（含共享字典引用）
  - validate_compliance() — GRADE 合规校验
  - build_pipeline_analysis_summary() — 流程分析摘要
  - reset() — 重置后字典对象不变
  - ResearchPipeline 组合集成（quality_assessor 持有并委托）
"""

import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.quality.quality_assessor import (
    GRADE_HIGH,
    GRADE_LOW,
    GRADE_MODERATE,
    GRADE_VERY_LOW,
    ComplianceReport,
    QualityAssessor,
    QualityScore,
    _extract_json_from_llm_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assessor() -> QualityAssessor:
    return QualityAssessor()


def _full_result(**kwargs) -> Dict[str, Any]:
    base = {
        "status": "completed",
        "phase": "analyze",
        "results": {"score": 0.9},
        "artifacts": ["paper.pdf"],
        "metadata": {"version": "1"},
        "error": None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# 1. QualityScore dataclass
# ---------------------------------------------------------------------------

class TestQualityScore(unittest.TestCase):
    def test_default_grade_very_low(self):
        qs = QualityScore()
        self.assertEqual(qs.grade_level, GRADE_VERY_LOW)

    def test_default_scores_zero(self):
        qs = QualityScore()
        self.assertEqual(qs.overall_score, 0.0)
        self.assertEqual(qs.completeness, 0.0)
        self.assertEqual(qs.consistency, 0.0)
        self.assertEqual(qs.evidence_quality, 0.0)

    def test_details_default_empty(self):
        qs = QualityScore()
        self.assertEqual(qs.details, {})


# ---------------------------------------------------------------------------
# 2. ComplianceReport dataclass
# ---------------------------------------------------------------------------

class TestComplianceReport(unittest.TestCase):
    def test_default_compliant(self):
        cr = ComplianceReport()
        self.assertTrue(cr.is_compliant)

    def test_default_empty_lists(self):
        cr = ComplianceReport()
        self.assertEqual(cr.violations, [])
        self.assertEqual(cr.warnings, [])

    def test_details_default_empty(self):
        cr = ComplianceReport()
        self.assertEqual(cr.details, {})


# ---------------------------------------------------------------------------
# 3. assess_quality
# ---------------------------------------------------------------------------

class TestAssessQuality(unittest.TestCase):
    def setUp(self):
        self.a = _assessor()

    def test_returns_quality_score_instance(self):
        self.assertIsInstance(self.a.assess_quality({}), QualityScore)

    def test_non_dict_returns_error_details(self):
        qs = self.a.assess_quality("not a dict")
        self.assertEqual(qs.overall_score, 0.0)
        self.assertIn("error", qs.details)

    def test_empty_dict_low_completeness(self):
        qs = self.a.assess_quality({})
        self.assertLessEqual(qs.completeness, 0.2)

    def test_full_result_high_completeness(self):
        qs = self.a.assess_quality(_full_result())
        self.assertGreaterEqual(qs.completeness, 0.8)

    def test_valid_status_gives_full_consistency(self):
        qs = self.a.assess_quality({"status": "completed", "phase": "observe"})
        self.assertEqual(qs.consistency, 1.0)

    def test_invalid_status_gives_partial_consistency(self):
        qs = self.a.assess_quality({"status": "in_flight", "phase": "observe"})
        self.assertEqual(qs.consistency, 0.5)

    def test_evidence_keys_raise_evidence_quality(self):
        result_with_evidence = _full_result()
        result_no_evidence = {"status": "completed", "phase": "observe"}
        score_with = self.a.assess_quality(result_with_evidence).evidence_quality
        score_without = self.a.assess_quality(result_no_evidence).evidence_quality
        self.assertGreater(score_with, score_without)

    def test_high_grade_for_rich_result(self):
        qs = self.a.assess_quality(_full_result())
        self.assertIn(qs.grade_level, [GRADE_HIGH, GRADE_MODERATE])

    def test_very_low_grade_for_empty(self):
        qs = self.a.assess_quality({})
        self.assertEqual(qs.grade_level, GRADE_VERY_LOW)

    def test_moderate_grade_threshold(self):
        # 手工制造 ~0.65 的得分
        result = {"status": "completed", "phase": "analyze", "results": {"x": 1}}
        qs = self.a.assess_quality(result)
        self.assertGreaterEqual(qs.overall_score, 0.0)
        self.assertLessEqual(qs.overall_score, 1.0)

    def test_details_present_keys_populated(self):
        qs = self.a.assess_quality({"status": "done", "phase": "publish"})
        self.assertIn("present_keys", qs.details)

    def test_overall_score_in_range(self):
        qs = self.a.assess_quality(_full_result())
        self.assertGreaterEqual(qs.overall_score, 0.0)
        self.assertLessEqual(qs.overall_score, 1.0)


# ---------------------------------------------------------------------------
# 4. _score_to_grade (static)
# ---------------------------------------------------------------------------

class TestScoreToGrade(unittest.TestCase):
    def test_high(self):
        self.assertEqual(QualityAssessor._score_to_grade(0.9), GRADE_HIGH)

    def test_moderate(self):
        self.assertEqual(QualityAssessor._score_to_grade(0.7), GRADE_MODERATE)

    def test_low(self):
        self.assertEqual(QualityAssessor._score_to_grade(0.5), GRADE_LOW)

    def test_very_low(self):
        self.assertEqual(QualityAssessor._score_to_grade(0.2), GRADE_VERY_LOW)

    def test_exact_high_boundary(self):
        self.assertEqual(QualityAssessor._score_to_grade(0.8), GRADE_HIGH)

    def test_exact_moderate_boundary(self):
        self.assertEqual(QualityAssessor._score_to_grade(0.6), GRADE_MODERATE)


# ---------------------------------------------------------------------------
# 5. calculate_metrics
# ---------------------------------------------------------------------------

class TestCalculateMetrics(unittest.TestCase):
    def setUp(self):
        self.a = _assessor()
        from src.research.study_session_manager import (
            ResearchCycle,
            ResearchCycleStatus,
        )
        self.CycleStatus = ResearchCycleStatus
        self.Cycle = ResearchCycle

    def _make_cycle(self, cid: str, completed: bool):
        from src.research.study_session_manager import ResearchCycleStatus
        c = self.Cycle(cycle_id=cid, cycle_name="T", description="")
        c.status = ResearchCycleStatus.COMPLETED if completed else ResearchCycleStatus.FAILED
        return c

    def test_returns_dict(self):
        result = self.a.calculate_metrics({})
        self.assertIsInstance(result, dict)

    def test_returns_same_dict_object(self):
        original = self.a.quality_metrics
        returned = self.a.calculate_metrics({})
        self.assertIs(returned, original)

    def test_empty_data_gives_zero_rates(self):
        self.a.calculate_metrics({})
        self.assertEqual(self.a.quality_metrics["cycle_completion_rate"], 0.0)

    def test_all_completed_gives_1_0_rate(self):
        cycles = {str(i): self._make_cycle(str(i), completed=True) for i in range(3)}
        self.a.calculate_metrics({"research_cycles": cycles})
        self.assertEqual(self.a.quality_metrics["cycle_completion_rate"], 1.0)

    def test_half_completed_gives_0_5_rate(self):
        cycles = {
            "a": self._make_cycle("a", completed=True),
            "b": self._make_cycle("b", completed=False),
        }
        self.a.calculate_metrics({"research_cycles": cycles})
        self.assertAlmostEqual(self.a.quality_metrics["cycle_completion_rate"], 0.5)

    def test_phase_efficiency_with_history(self):
        history = [{"event": "X"}, {"event": "Y"}, {"event": "Z"}]
        self.a.calculate_metrics({"execution_history": history})
        self.assertEqual(self.a.quality_metrics["phase_efficiency"], 1.0)

    def test_failed_ops_reduce_quality_assurance(self):
        history = [{"event": "A"}, {"event": "B"}]
        failed_ops = [{"operation": "observe", "error": "timeout"}]
        self.a.calculate_metrics({"execution_history": history, "failed_operations": failed_ops})
        self.assertLessEqual(self.a.quality_metrics["quality_assurance"], 1.0)

    def test_all_metric_keys_present(self):
        self.a.calculate_metrics({})
        keys = {"cycle_completion_rate", "phase_efficiency", "researcher_productivity", "quality_assurance"}
        self.assertTrue(keys.issubset(self.a.quality_metrics.keys()))


# ---------------------------------------------------------------------------
# 6. validate_compliance
# ---------------------------------------------------------------------------

class TestValidateCompliance(unittest.TestCase):
    def setUp(self):
        self.a = _assessor()

    def test_non_dict_is_non_compliant(self):
        cr = self.a.validate_compliance(42)
        self.assertFalse(cr.is_compliant)
        self.assertTrue(len(cr.violations) > 0)

    def test_returns_compliance_report(self):
        cr = self.a.validate_compliance({})
        self.assertIsInstance(cr, ComplianceReport)

    def test_missing_required_fields_produces_violations(self):
        cr = self.a.validate_compliance({})
        violation_text = " ".join(cr.violations)
        self.assertIn("status", violation_text)
        self.assertIn("phase", violation_text)

    def test_full_result_is_compliant(self):
        cr = self.a.validate_compliance(_full_result())
        self.assertTrue(cr.is_compliant)

    def test_missing_only_recommended_yields_warnings(self):
        # Has required keys but no recommended ones
        cr = self.a.validate_compliance({"status": "completed", "phase": "observe"})
        self.assertTrue(cr.is_compliant)
        self.assertTrue(len(cr.warnings) > 0)

    def test_grade_assessment_contains_grade(self):
        cr = self.a.validate_compliance(_full_result())
        self.assertIn("GRADE:", cr.grade_assessment)

    def test_details_has_grade_level(self):
        cr = self.a.validate_compliance(_full_result())
        self.assertIn("grade_level", cr.details)

    def test_non_terminal_status_produces_warning(self):
        cr = self.a.validate_compliance({"status": "running", "phase": "observe"})
        warning_text = " ".join(cr.warnings)
        self.assertIn("non-terminal", warning_text)

    def test_terminal_status_no_warning_about_status(self):
        cr = self.a.validate_compliance({"status": "completed", "phase": "observe"})
        for w in cr.warnings:
            self.assertNotIn("non-terminal", w)


# ---------------------------------------------------------------------------
# 7. build_pipeline_analysis_summary
# ---------------------------------------------------------------------------

class TestBuildPipelineAnalysisSummary(unittest.TestCase):
    def setUp(self):
        self.a = _assessor()
        from src.research.study_session_manager import (
            ResearchCycle,
            ResearchCycleStatus,
        )
        self.ResearchCycle = ResearchCycle
        self.Status = ResearchCycleStatus

    def _make_cycle(self, cid: str, status):
        c = self.ResearchCycle(cycle_id=cid, cycle_name="T", description="")
        c.status = status
        return c

    def _gov(self, min_rate=0.8):
        return {"minimum_stable_completion_rate": min_rate}

    def test_empty_cycles_status_idle(self):
        summary = self.a.build_pipeline_analysis_summary({}, [], self._gov(), {})
        self.assertEqual(summary["status"], "idle")

    def test_all_completed_stable(self):
        cycles = {str(i): self._make_cycle(str(i), self.Status.COMPLETED) for i in range(2)}
        summary = self.a.build_pipeline_analysis_summary(cycles, [], self._gov(), {})
        self.assertEqual(summary["status"], "stable")

    def test_failed_ops_triggers_needs_followup(self):
        cycles = {"c1": self._make_cycle("c1", self.Status.COMPLETED)}
        summary = self.a.build_pipeline_analysis_summary(
            cycles, [{"operation": "x", "error": "e"}], self._gov(), {}
        )
        self.assertEqual(summary["status"], "needs_followup")

    def test_failed_cycles_triggers_degraded(self):
        cycles = {
            "c1": self._make_cycle("c1", self.Status.COMPLETED),
            "c2": self._make_cycle("c2", self.Status.FAILED),
        }
        summary = self.a.build_pipeline_analysis_summary(cycles, [], self._gov(), {})
        self.assertEqual(summary["status"], "degraded")

    def test_completion_rate_calculated_correctly(self):
        cycles = {
            "c1": self._make_cycle("c1", self.Status.COMPLETED),
            "c2": self._make_cycle("c2", self.Status.COMPLETED),
            "c3": self._make_cycle("c3", self.Status.FAILED),
        }
        summary = self.a.build_pipeline_analysis_summary(cycles, [], self._gov(), {})
        self.assertAlmostEqual(summary["completion_rate"], round(2 / 3, 4))

    def test_returns_expected_keys(self):
        summary = self.a.build_pipeline_analysis_summary({}, [], self._gov(), {})
        for k in ("total_cycles", "completed_cycles", "failed_cycles",
                  "completion_rate", "failed_operation_count", "status",
                  "last_completed_phase", "failed_phase", "final_status"):
            self.assertIn(k, summary)

    def test_passes_metadata_fields(self):
        meta = {"last_completed_phase": "analyze", "failed_phase": "publish", "final_status": "failed"}
        summary = self.a.build_pipeline_analysis_summary({}, [], self._gov(), meta)
        self.assertEqual(summary["last_completed_phase"], "analyze")
        self.assertEqual(summary["final_status"], "failed")

    def test_below_min_rate_degraded(self):
        cycles = {
            "c1": self._make_cycle("c1", self.Status.COMPLETED),
            "c2": self._make_cycle("c2", self.Status.PENDING),
        }
        summary = self.a.build_pipeline_analysis_summary(
            cycles, [], self._gov(min_rate=0.9), {}
        )
        self.assertEqual(summary["status"], "degraded")


# ---------------------------------------------------------------------------
# 8. reset()
# ---------------------------------------------------------------------------

class TestReset(unittest.TestCase):
    def test_reset_preserves_dict_identity(self):
        a = _assessor()
        qm_id = id(a.quality_metrics)
        ru_id = id(a.resource_usage)
        a.reset()
        self.assertEqual(id(a.quality_metrics), qm_id)
        self.assertEqual(id(a.resource_usage), ru_id)

    def test_reset_zeros_quality_metrics(self):
        a = _assessor()
        a.quality_metrics["cycle_completion_rate"] = 0.99
        a.reset()
        self.assertEqual(a.quality_metrics["cycle_completion_rate"], 0.0)

    def test_reset_zeros_resource_usage(self):
        a = _assessor()
        a.resource_usage["cpu_usage"] = 75.0
        a.reset()
        self.assertEqual(a.resource_usage["cpu_usage"], 0.0)

    def test_alias_reflects_reset(self):
        """Simulated pipeline alias — mutation after reset must be visible."""
        a = _assessor()
        alias = a.quality_metrics  # same object
        a.quality_metrics["quality_assurance"] = 0.99
        a.reset()
        self.assertEqual(alias["quality_assurance"], 0.0)

    def test_reset_quality_metrics_all_keys(self):
        a = _assessor()
        a.reset()
        keys = {"cycle_completion_rate", "phase_efficiency", "researcher_productivity", "quality_assurance"}
        self.assertTrue(keys.issubset(a.quality_metrics.keys()))

    def test_reset_resource_usage_all_keys(self):
        a = _assessor()
        a.reset()
        keys = {"cpu_usage", "memory_usage", "storage_usage", "network_usage"}
        self.assertTrue(keys.issubset(a.resource_usage.keys()))


# ---------------------------------------------------------------------------
# 9. ResearchPipeline 集成：组合持有 QualityAssessor
# ---------------------------------------------------------------------------

class TestPipelineIntegration(unittest.TestCase):

    def setUp(self):
        with patch("src.research.research_pipeline.HypothesisEngine") as mhe, \
             patch("src.research.research_pipeline.ResearchPhaseHandlers"), \
             patch("src.research.research_pipeline.ResearchPipelineOrchestrator"), \
             patch("src.research.research_pipeline.ModuleFactory"):
            mhe.return_value.initialize.return_value = None
            from src.research.research_pipeline import ResearchPipeline
            self.pipeline = ResearchPipeline({})

    def test_pipeline_has_quality_assessor(self):
        self.assertIsInstance(self.pipeline.quality_assessor, QualityAssessor)

    def test_quality_metrics_alias_same_object(self):
        self.assertIs(
            self.pipeline.quality_metrics,
            self.pipeline.quality_assessor.quality_metrics,
        )

    def test_resource_usage_alias_same_object(self):
        self.assertIs(
            self.pipeline.resource_usage,
            self.pipeline.quality_assessor.resource_usage,
        )

    def test_build_pipeline_analysis_summary_returns_dict(self):
        summary = self.pipeline._build_pipeline_analysis_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("status", summary)

    def test_cleanup_resets_metrics_via_assessor(self):
        self.pipeline.quality_metrics["cycle_completion_rate"] = 0.99
        self.pipeline.cleanup()
        self.assertEqual(self.pipeline.quality_metrics["cycle_completion_rate"], 0.0)

    def test_cleanup_preserves_dict_identity(self):
        qm_id = id(self.pipeline.quality_metrics)
        self.pipeline.cleanup()
        # After reset(), the same dict object must still be referenced
        self.assertEqual(id(self.pipeline.quality_assessor.quality_metrics), qm_id)

    def test_delegation_assess_quality(self):
        result = {"status": "completed", "phase": "observe"}
        qs = self.pipeline.quality_assessor.assess_quality(result)
        self.assertIsInstance(qs, QualityScore)

    def test_delegation_validate_compliance(self):
        result = {"status": "completed", "phase": "analyze", "results": {}}
        cr = self.pipeline.quality_assessor.validate_compliance(result)
        self.assertIsInstance(cr, ComplianceReport)


# ---------------------------------------------------------------------------
# 10. assess_cycle_for_reflection
# ---------------------------------------------------------------------------

class TestAssessCycleForReflection(unittest.TestCase):

    def test_empty_outcomes_returns_zero_score(self):
        a = _assessor()
        result = a.assess_cycle_for_reflection([])
        self.assertEqual(result["overall_cycle_score"], 0.0)
        self.assertEqual(result["phase_assessments"], [])
        self.assertEqual(result["weaknesses"], [])
        self.assertEqual(result["strengths"], [])

    def test_full_result_classified_as_strength(self):
        a = _assessor()
        outcomes = [{"phase": "observe", "result": _full_result()}]
        result = a.assess_cycle_for_reflection(outcomes)
        self.assertEqual(len(result["phase_assessments"]), 1)
        self.assertGreaterEqual(result["overall_cycle_score"], 0.8)
        self.assertTrue(len(result["strengths"]) >= 1)

    def test_weak_result_classified_as_weakness(self):
        a = _assessor()
        outcomes = [{"phase": "analyze", "result": {"status": "pending"}}]
        result = a.assess_cycle_for_reflection(outcomes)
        self.assertTrue(len(result["weaknesses"]) >= 1)
        self.assertLess(result["weaknesses"][0]["score"], 0.6)

    def test_mixed_outcomes_both_strengths_and_weaknesses(self):
        a = _assessor()
        outcomes = [
            {"phase": "observe", "result": _full_result()},
            {"phase": "analyze", "result": {}},
        ]
        result = a.assess_cycle_for_reflection(outcomes)
        self.assertEqual(len(result["phase_assessments"]), 2)
        self.assertTrue(result["strengths"] or result["weaknesses"])

    def test_overall_score_is_average(self):
        a = _assessor()
        outcomes = [
            {"phase": "observe", "result": _full_result()},
            {"phase": "hypothesis", "result": _full_result()},
        ]
        result = a.assess_cycle_for_reflection(outcomes)
        scores = [pa["score"].overall_score for pa in result["phase_assessments"]]
        expected = round(sum(scores) / len(scores), 4)
        self.assertAlmostEqual(result["overall_cycle_score"], expected, places=3)

    def test_missing_result_key_treated_as_empty(self):
        a = _assessor()
        outcomes = [{"phase": "reflect"}]  # no "result" key
        result = a.assess_cycle_for_reflection(outcomes)
        self.assertEqual(len(result["phase_assessments"]), 1)


# ---------------------------------------------------------------------------
# 10. _extract_json_from_llm_output 工具函数
# ---------------------------------------------------------------------------

class TestExtractJsonFromLlmOutput(unittest.TestCase):
    def test_plain_json(self):
        raw = '{"methodological_rigor": 0.8, "evidence_coherence": 0.7}'
        result = _extract_json_from_llm_output(raw)
        self.assertEqual(result["methodological_rigor"], 0.8)

    def test_json_fenced(self):
        raw = '好的，以下是评估：\n```json\n{"score": 0.9}\n```\n完成。'
        result = _extract_json_from_llm_output(raw)
        self.assertEqual(result["score"], 0.9)

    def test_json_embedded_in_text(self):
        raw = '评估如下 {"a": 1, "b": 2} 以上。'
        result = _extract_json_from_llm_output(raw)
        self.assertEqual(result["a"], 1)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_extract_json_from_llm_output(""))

    def test_none_input_returns_none(self):
        self.assertIsNone(_extract_json_from_llm_output(None))

    def test_invalid_json_returns_none(self):
        self.assertIsNone(_extract_json_from_llm_output("不是JSON内容"))

    def test_json_array_returns_none(self):
        self.assertIsNone(_extract_json_from_llm_output('[1, 2, 3]'))


# ---------------------------------------------------------------------------
# 11. assess_quality_with_llm
# ---------------------------------------------------------------------------

class TestAssessQualityWithLlm(unittest.TestCase):
    def _make_llm(self, response: str) -> MagicMock:
        llm = MagicMock()
        llm.generate.return_value = response
        return llm

    def test_blends_rule_and_llm_scores(self):
        a = _assessor()
        llm = self._make_llm(
            '{"methodological_rigor": 0.9, "evidence_coherence": 0.8, '
            '"domain_relevance": 0.85, "reproducibility": 0.75, '
            '"rationale": "方法学严谨"}'
        )
        result = a.assess_quality_with_llm(_full_result(), llm)
        self.assertTrue(result.details.get("llm_enhanced"))
        self.assertAlmostEqual(result.details["llm_dimensions"]["methodological_rigor"], 0.9)
        self.assertIn("blend_weights", result.details)
        # blended = 0.4 * rule + 0.6 * llm_overall
        rule_score = a.assess_quality(_full_result()).overall_score
        llm_overall = (0.9 + 0.8 + 0.85 + 0.75) / 4
        expected = round(0.4 * rule_score + 0.6 * llm_overall, 4)
        self.assertAlmostEqual(result.overall_score, expected, places=3)

    def test_falls_back_without_llm(self):
        a = _assessor()
        result = a.assess_quality_with_llm(_full_result(), None)
        self.assertNotIn("llm_enhanced", result.details)
        self.assertEqual(result.overall_score, a.assess_quality(_full_result()).overall_score)

    def test_falls_back_on_llm_error(self):
        a = _assessor()
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("model not loaded")
        result = a.assess_quality_with_llm(_full_result(), llm)
        self.assertNotIn("llm_enhanced", result.details)

    def test_falls_back_on_invalid_llm_json(self):
        a = _assessor()
        llm = self._make_llm("这不是JSON")
        result = a.assess_quality_with_llm(_full_result(), llm)
        self.assertNotIn("llm_enhanced", result.details)

    def test_falls_back_on_missing_dimensions(self):
        a = _assessor()
        llm = self._make_llm('{"methodological_rigor": 0.9}')  # missing 3 keys
        result = a.assess_quality_with_llm(_full_result(), llm)
        self.assertNotIn("llm_enhanced", result.details)

    def test_clamps_score_to_0_1(self):
        a = _assessor()
        llm = self._make_llm(
            '{"methodological_rigor": 1.5, "evidence_coherence": -0.2, '
            '"domain_relevance": 0.8, "reproducibility": 0.7}'
        )
        result = a.assess_quality_with_llm(_full_result(), llm)
        dims = result.details["llm_dimensions"]
        self.assertEqual(dims["methodological_rigor"], 1.0)
        self.assertEqual(dims["evidence_coherence"], 0.0)

    def test_grade_level_reflects_blended(self):
        a = _assessor()
        llm = self._make_llm(
            '{"methodological_rigor": 0.95, "evidence_coherence": 0.95, '
            '"domain_relevance": 0.95, "reproducibility": 0.95}'
        )
        result = a.assess_quality_with_llm(_full_result(), llm)
        self.assertEqual(result.grade_level, GRADE_HIGH)

    def test_llm_without_generate_attr_falls_back(self):
        a = _assessor()
        llm = object()  # no generate method
        result = a.assess_quality_with_llm(_full_result(), llm)
        self.assertNotIn("llm_enhanced", result.details)


# ---------------------------------------------------------------------------
# 12. assess_cycle_for_reflection_with_llm
# ---------------------------------------------------------------------------

class TestAssessCycleForReflectionWithLlm(unittest.TestCase):
    def _make_llm(self, response: str) -> MagicMock:
        llm = MagicMock()
        llm.generate.return_value = response
        return llm

    def test_adds_llm_diagnosis_when_available(self):
        a = _assessor()
        outcomes = [
            {"phase": "observe", "result": _full_result()},
            {"phase": "analyze", "result": {"status": "failed", "phase": "analyze"}},
        ]
        llm = self._make_llm(
            '{"diagnosis": "分析阶段方法学不足", '
            '"root_causes": ["缺少统计检验"], '
            '"priority_improvements": ["接入 p 值计算"], '
            '"confidence": 0.85}'
        )
        result = a.assess_cycle_for_reflection_with_llm(outcomes, llm)
        self.assertIn("llm_diagnosis", result)
        self.assertEqual(result["llm_diagnosis"]["diagnosis"], "分析阶段方法学不足")
        self.assertEqual(result["llm_diagnosis"]["confidence"], 0.85)
        self.assertEqual(len(result["llm_diagnosis"]["root_causes"]), 1)
        self.assertIsInstance(result["llm_diagnosis"].get("planner"), dict)
        self.assertEqual(result["llm_diagnosis"]["planner"]["phase"], "reflect")

    def test_no_llm_diagnosis_without_engine(self):
        a = _assessor()
        outcomes = [{"phase": "observe", "result": _full_result()}]
        result = a.assess_cycle_for_reflection_with_llm(outcomes, None)
        self.assertNotIn("llm_diagnosis", result)
        self.assertIn("phase_assessments", result)

    def test_llm_failure_still_returns_base(self):
        a = _assessor()
        outcomes = [{"phase": "observe", "result": _full_result()}]
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("crash")
        result = a.assess_cycle_for_reflection_with_llm(outcomes, llm)
        self.assertNotIn("llm_diagnosis", result)
        self.assertIn("phase_assessments", result)

    def test_invalid_llm_output_no_diagnosis(self):
        a = _assessor()
        outcomes = [{"phase": "observe", "result": _full_result()}]
        llm = self._make_llm("无法解析")
        result = a.assess_cycle_for_reflection_with_llm(outcomes, llm)
        self.assertNotIn("llm_diagnosis", result)


# ---------------------------------------------------------------------------
# 13. _build_result_summary_for_llm
# ---------------------------------------------------------------------------

class TestBuildResultSummaryForLlm(unittest.TestCase):
    def test_includes_phase_and_status(self):
        summary = QualityAssessor._build_result_summary_for_llm(
            {"phase": "analyze", "status": "completed"}
        )
        self.assertIn("phase: analyze", summary)
        self.assertIn("status: completed", summary)

    def test_truncates_long_values(self):
        long_val = "x" * 500
        summary = QualityAssessor._build_result_summary_for_llm(
            {"phase": "test", "status": "ok", "results": {"data": long_val}}
        )
        self.assertLess(len(summary), 600)

    def test_handles_list_results(self):
        summary = QualityAssessor._build_result_summary_for_llm(
            {"phase": "test", "status": "ok", "results": [1, 2, 3]}
        )
        self.assertIn("list[3 items]", summary)


if __name__ == "__main__":
    unittest.main()
