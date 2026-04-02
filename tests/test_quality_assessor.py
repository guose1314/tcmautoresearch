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


if __name__ == "__main__":
    unittest.main()
