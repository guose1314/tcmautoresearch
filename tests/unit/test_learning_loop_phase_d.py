"""Phase D 测试 — PolicyAdjuster + ImportQualityValidator + LearningLoop 集成。"""

import unittest
from unittest.mock import MagicMock, patch

from src.learning.policy_adjuster import (
    _DEFAULT_EVIDENCE_POLICY,
    PolicyAdjuster,
    PolicyAdjustment,
)
from src.research.import_quality_validator import (
    ImportQualityValidator,
    Strictness,
    ValidationReport,
    ValidationSeverity,
)

# ══════════════════════════════════════════════════════════════════════════
# PolicyAdjuster Tests
# ══════════════════════════════════════════════════════════════════════════


class TestPolicyAdjusterInit(unittest.TestCase):
    """初始化与默认值。"""

    def test_default_evidence_policy(self):
        pa = PolicyAdjuster()
        policy = pa.get_evidence_policy()
        self.assertEqual(policy["min_confidence"], 0.60)
        self.assertEqual(policy["min_evidence_grade"], "low")
        self.assertEqual(policy["claim_support_threshold"], 1)

    def test_custom_initial_policy(self):
        pa = PolicyAdjuster(initial_evidence_policy={"min_confidence": 0.80, "min_evidence_grade": "moderate"})
        self.assertEqual(pa.get_evidence_policy()["min_confidence"], 0.80)

    def test_initial_version_recorded(self):
        pa = PolicyAdjuster()
        self.assertEqual(pa.version_count, 1)
        history = pa.get_policy_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["trigger"], "initial")


class TestPolicyAdjusterAdjust(unittest.TestCase):
    """reflect 产出驱动策略调整。"""

    def _make_cycle_assessment(self, score: float, dimensions: dict = None):
        return {
            "overall_score": score,
            "dimensions": dimensions or {},
            "improvement_plan": [],
        }

    def test_high_score_tightens_evidence(self):
        pa = PolicyAdjuster()
        old_conf = pa.get_evidence_policy()["min_confidence"]
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.90),
            improvement_plan=[],
        )
        self.assertGreater(result.evidence_policy["min_confidence"], old_conf)
        self.assertTrue(any(c["direction"] == "tighten" for c in result.changes))

    def test_low_score_loosens_evidence(self):
        pa = PolicyAdjuster(initial_evidence_policy={"min_confidence": 0.70, "min_evidence_grade": "moderate"})
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.50),
            improvement_plan=[],
        )
        self.assertLess(result.evidence_policy["min_confidence"], 0.70)
        self.assertTrue(any(c["direction"] == "loosen" for c in result.changes))

    def test_mid_score_no_change(self):
        pa = PolicyAdjuster()
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.75),
            improvement_plan=[],
        )
        # No evidence_policy changes (only mid-score)
        evidence_changes = [c for c in result.changes if c["field"].startswith("evidence_policy")]
        self.assertEqual(len(evidence_changes), 0)

    def test_evidence_mention_triggers_tighten(self):
        pa = PolicyAdjuster()
        old_conf = pa.get_evidence_policy()["min_confidence"]
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.75),
            improvement_plan=[{"suggestion": "提升 evidence 证据质量"}],
        )
        self.assertGreater(result.evidence_policy["min_confidence"], old_conf)

    def test_tuned_parameters_synced(self):
        pa = PolicyAdjuster()
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.75),
            improvement_plan=[],
            current_tuned_parameters={"confidence_threshold": 0.72, "quality_threshold": 0.68},
        )
        self.assertEqual(result.phase_thresholds["confidence_threshold"], 0.72)
        self.assertEqual(result.phase_thresholds["quality_threshold"], 0.68)

    def test_template_preferences_adjusted_by_dimensions(self):
        pa = PolicyAdjuster()
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.80, {"analytical_depth": 0.90, "evidence_quality": 0.40}),
            improvement_plan=[],
        )
        # analytical_depth high → analytical strengthened
        analytical_changes = [c for c in result.changes if "analytical" in c["field"]]
        evidential_changes = [c for c in result.changes if "evidential" in c["field"]]
        self.assertTrue(any(c["direction"] == "strengthen" for c in analytical_changes))
        self.assertTrue(any(c["direction"] == "weaken" for c in evidential_changes))

    def test_version_increments_on_adjust(self):
        pa = PolicyAdjuster()
        self.assertEqual(pa.version_count, 1)
        pa.adjust(cycle_assessment=self._make_cycle_assessment(0.90), improvement_plan=[])
        self.assertEqual(pa.version_count, 2)

    def test_confidence_respects_bounds(self):
        pa = PolicyAdjuster(initial_evidence_policy={"min_confidence": 0.94, "min_evidence_grade": "high"})
        result = pa.adjust(
            cycle_assessment=self._make_cycle_assessment(0.99),
            improvement_plan=[],
        )
        self.assertLessEqual(result.evidence_policy["min_confidence"], 0.95)

    def test_get_active_policy_structure(self):
        pa = PolicyAdjuster()
        policy = pa.get_active_policy()
        self.assertIn("evidence_policy", policy)
        self.assertIn("phase_thresholds", policy)
        self.assertIn("template_preferences", policy)
        self.assertIn("version_id", policy)


class TestPolicyAdjusterHistory(unittest.TestCase):
    """版本历史管理。"""

    def test_history_limit(self):
        pa = PolicyAdjuster()
        for i in range(60):
            pa.adjust(
                cycle_assessment={"overall_score": 0.5 + i * 0.005},
                improvement_plan=[],
            )
        history = pa.get_policy_history(limit=100)
        # 50 max + 1 initial = capped at 50
        self.assertLessEqual(len(history), 50)


# ══════════════════════════════════════════════════════════════════════════
# ImportQualityValidator Tests
# ══════════════════════════════════════════════════════════════════════════


class TestImportQualityValidatorRecords(unittest.TestCase):
    """记录验证。"""

    def _valid_record(self, **overrides):
        base = {
            "source_entity": "黄芪",
            "target_entity": "补气",
            "relation_type": "treats",
            "confidence": 0.85,
            "evidence_grade": "high",
        }
        base.update(overrides)
        return base

    def test_valid_records_pass(self):
        validator = ImportQualityValidator(strictness="standard")
        report = validator.validate_records([self._valid_record(), self._valid_record()])
        self.assertEqual(report.total_records, 2)
        self.assertEqual(report.passed, 2)
        self.assertEqual(report.rejected, 0)
        self.assertFalse(report.has_rejections)

    def test_missing_required_field_rejects(self):
        validator = ImportQualityValidator(strictness="standard")
        report = validator.validate_records([{"source_entity": "黄芪"}])
        self.assertEqual(report.rejected, 1)
        self.assertTrue(report.has_rejections)

    def test_lenient_mode_warns_instead_of_reject(self):
        validator = ImportQualityValidator(strictness="lenient")
        report = validator.validate_records([{"source_entity": "黄芪"}])
        # lenient: missing required → warn, not reject
        self.assertEqual(report.rejected, 0)
        self.assertGreater(report.warned, 0)

    def test_confidence_below_threshold_warns(self):
        validator = ImportQualityValidator(strictness="standard", min_confidence=0.7)
        report = validator.validate_records([self._valid_record(confidence=0.5)])
        issues = [i for i in report.issues if "低于最低阈值" in i.message]
        self.assertTrue(issues)

    def test_strict_confidence_below_threshold_rejects(self):
        validator = ImportQualityValidator(strictness="strict", min_confidence=0.7)
        report = validator.validate_records([self._valid_record(confidence=0.5)])
        self.assertEqual(report.rejected, 1)

    def test_invalid_evidence_grade_warns(self):
        validator = ImportQualityValidator()
        report = validator.validate_records([self._valid_record(evidence_grade="unknown")])
        issues = [i for i in report.issues if "evidence_grade" in i.field]
        self.assertTrue(issues)

    def test_non_dict_record_rejected(self):
        validator = ImportQualityValidator()
        report = validator.validate_records(["not a dict", 123])
        self.assertEqual(report.rejected, 2)

    def test_confidence_out_of_range_warns(self):
        validator = ImportQualityValidator()
        report = validator.validate_records([self._valid_record(confidence=1.5)])
        issues = [i for i in report.issues if "超出" in i.message]
        self.assertTrue(issues)

    def test_empty_records_report(self):
        validator = ImportQualityValidator()
        report = validator.validate_records([])
        self.assertEqual(report.total_records, 0)
        self.assertEqual(report.acceptance_rate, 1.0)

    def test_acceptance_rate_calculation(self):
        validator = ImportQualityValidator(strictness="standard")
        report = validator.validate_records([
            self._valid_record(),
            {"not_valid": True},  # rejected
        ])
        self.assertAlmostEqual(report.acceptance_rate, 0.5)


class TestImportQualityValidatorRelationships(unittest.TestCase):
    """关系验证。"""

    def test_valid_relationship_passes(self):
        validator = ImportQualityValidator()
        report = validator.validate_relationships([
            {"source": "黄芪", "target": "补气", "type": "treats", "metadata": {"confidence": 0.9}}
        ])
        self.assertEqual(report.passed, 1)
        self.assertEqual(report.rejected, 0)

    def test_missing_source_rejects(self):
        validator = ImportQualityValidator(strictness="standard")
        report = validator.validate_relationships([
            {"target": "补气", "type": "treats"}
        ])
        self.assertEqual(report.rejected, 1)

    def test_metadata_confidence_range_warns(self):
        validator = ImportQualityValidator()
        report = validator.validate_relationships([
            {"source": "A", "target": "B", "type": "X", "metadata": {"confidence": 2.0}}
        ])
        issues = [i for i in report.issues if "超出" in i.message]
        self.assertTrue(issues)


# ══════════════════════════════════════════════════════════════════════════
# LearningLoopOrchestrator Integration
# ══════════════════════════════════════════════════════════════════════════


class TestLearningLoopOrchestratorPolicyIntegration(unittest.TestCase):
    """验证 LearningLoopOrchestrator 集成 PolicyAdjuster。"""

    def _make_pipeline(self, tuned_params=None):
        pipeline = MagicMock()
        pipeline.config = {
            "learning_strategy": {"strategy_version": "test"},
            "self_learning_engine": MagicMock(),
        }
        learn_mock = pipeline.config["self_learning_engine"].learn_from_cycle_reflection
        learn_mock.return_value = {
            "recorded_phases": ["observe"],
            "tuned_parameters": tuned_params or {"confidence_threshold": 0.72},
            "cycle_trend": "improving",
        }
        pipeline.config["self_learning_engine"].get_learning_strategy.return_value = {
            "strategy_version": "self_learning.v1",
            "tuned_parameters": tuned_params or {"confidence_threshold": 0.72},
        }
        pipeline.config["self_learning_engine"].build_previous_iteration_feedback.return_value = {}
        pipeline.get_learning_strategy = MagicMock(return_value={"strategy_version": "test"})
        pipeline.get_previous_iteration_feedback = MagicMock(return_value={})
        pipeline.freeze_learning_strategy_snapshot = MagicMock(return_value={
            "strategy": {}, "tuned_parameters": {}, "fingerprint": "abc123"
        })
        pipeline.refresh_learning_runtime_feedback = MagicMock(return_value={})
        return pipeline

    def test_execute_reflect_learning_includes_policy_adjustment(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        pipeline = self._make_pipeline()
        llo.prepare_cycle(pipeline)

        result = llo.execute_reflect_learning(
            pipeline,
            {"overall_score": 0.90, "dimensions": {}, "improvement_plan": []},
        )
        self.assertIn("policy_adjustment", result)
        pa = result["policy_adjustment"]
        self.assertIn("evidence_policy", pa)
        self.assertIn("phase_thresholds", pa)
        self.assertIn("template_preferences", pa)
        self.assertIn("changes", pa)
        self.assertIn("rationale", pa)

    def test_high_score_tightens_via_orchestrator(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        pipeline = self._make_pipeline()
        llo.prepare_cycle(pipeline)

        result = llo.execute_reflect_learning(
            pipeline,
            {"overall_score": 0.92, "dimensions": {}, "improvement_plan": []},
        )
        pa = result["policy_adjustment"]
        # High score should tighten evidence
        tighten_changes = [c for c in pa["changes"] if c.get("direction") == "tighten"]
        self.assertTrue(tighten_changes)

    def test_prepare_next_cycle_includes_evidence_policy(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        pipeline = self._make_pipeline()
        llo.prepare_cycle(pipeline)
        llo.execute_reflect_learning(
            pipeline,
            {"overall_score": 0.80, "dimensions": {}, "improvement_plan": []},
        )

        next_strategy = llo.prepare_next_cycle_strategy(pipeline)
        self.assertIn("evidence_policy", next_strategy)
        self.assertIn("template_preferences", next_strategy)

    def test_policy_adjuster_property_accessible(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        self.assertIsInstance(llo.policy_adjuster, PolicyAdjuster)

    def test_orchestrator_syncs_tuned_parameters_to_phase_thresholds(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        pipeline = self._make_pipeline(tuned_params={"confidence_threshold": 0.75, "quality_threshold": 0.80})
        llo.prepare_cycle(pipeline)

        result = llo.execute_reflect_learning(
            pipeline,
            {"overall_score": 0.78, "dimensions": {}, "improvement_plan": []},
        )
        self.assertEqual(result["policy_adjustment"]["phase_thresholds"]["confidence_threshold"], 0.75)
        self.assertEqual(result["policy_adjustment"]["phase_thresholds"]["quality_threshold"], 0.80)


# ══════════════════════════════════════════════════════════════════════════
# ExperimentExecutionPhase Validation Integration
# ══════════════════════════════════════════════════════════════════════════


class TestExperimentExecutionImportValidation(unittest.TestCase):
    """验证 ExperimentExecutionPhase 集成 ImportQualityValidator。"""

    def test_import_quality_validator_importable(self):
        from src.research.import_quality_validator import ImportQualityValidator
        v = ImportQualityValidator()
        self.assertEqual(v.strictness, "standard")

    def test_validate_method_on_mixin_exists(self):
        from src.research.phases.experiment_execution_phase import (
            ExperimentExecutionPhaseMixin,
        )
        self.assertTrue(hasattr(ExperimentExecutionPhaseMixin, "_validate_import_quality"))


if __name__ == "__main__":
    unittest.main()
