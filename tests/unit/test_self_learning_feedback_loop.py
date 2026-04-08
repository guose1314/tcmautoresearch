# tests/unit/test_self_learning_feedback_loop.py
"""SelfLearningEngine 反馈闭环专项测试

验证 learn_from_cycle_reflection() 在接收 ReflectPhase 质量评估后:
1. 调用 PatternRecognizer 提取模式
2. 将反思评分 + 维度趋势反馈给 AdaptiveTuner 进行调参
3. 返回 extracted_patterns 与 tuned_parameters
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.learning.self_learning_engine import SelfLearningEngine


class _AssessmentFactory:
    """测试用循环评估数据构建器。"""

    @staticmethod
    def make(overall=0.65, weak_score=0.35, strong_score=0.9):
        from src.quality.quality_assessor import QualityScore

        return {
            "phase_assessments": [
                {
                    "phase": "observe",
                    "score": QualityScore(
                        overall_score=strong_score,
                        completeness=0.9,
                        consistency=0.8,
                        evidence_quality=0.85,
                        grade_level="high",
                    ),
                },
                {
                    "phase": "analyze",
                    "score": QualityScore(
                        overall_score=weak_score,
                        completeness=0.3,
                        consistency=0.4,
                        evidence_quality=0.2,
                        grade_level="very_low",
                    ),
                },
            ],
            "weaknesses": [
                {
                    "phase": "analyze",
                    "score": weak_score,
                    "grade": "very_low",
                    "issues": ["missing required: status"],
                }
            ],
            "strengths": [
                {"phase": "observe", "score": strong_score, "grade": "high"}
            ],
            "overall_cycle_score": overall,
        }


def _make_engine(tmp_dir: str) -> SelfLearningEngine:
    data_file = str(Path(tmp_dir) / "test_fb.pkl")
    engine = SelfLearningEngine({"learning_data_file": data_file})
    engine.initialize({})
    return engine


# ---------------------------------------------------------------------------
# 1) 反思后 summary 包含 extracted_patterns 和 tuned_parameters
# ---------------------------------------------------------------------------


class TestReflectionFeedbackSummaryKeys(unittest.TestCase):
    """learn_from_cycle_reflection 应返回 extracted_patterns / tuned_parameters。"""

    def test_summary_contains_extracted_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            self.assertIn("extracted_patterns", summary)
            self.assertIsInstance(summary["extracted_patterns"], list)

    def test_summary_contains_tuned_parameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            self.assertIn("tuned_parameters", summary)
            self.assertIsInstance(summary["tuned_parameters"], dict)

    def test_tuned_parameters_has_known_keys(self):
        """AdaptiveTuner 默认参数应出现在 tuned_parameters 中。"""
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            tp = summary["tuned_parameters"]
            if tp:  # tuner 可用时
                self.assertIn("confidence_threshold", tp)
                self.assertIn("quality_threshold", tp)


# ---------------------------------------------------------------------------
# 2) PatternRecognizer 在反思阶段被调用
# ---------------------------------------------------------------------------


class TestPatternRecognizerCalledDuringReflection(unittest.TestCase):

    def test_pattern_recognizer_analyze_invoked(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_pr = MagicMock()
            mock_pr.analyze.return_value = []
            engine._pattern_recognizer = mock_pr

            engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            mock_pr.analyze.assert_called_once()

    def test_pattern_recognizer_receives_phase_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_pr = MagicMock()
            mock_pr.analyze.return_value = []
            engine._pattern_recognizer = mock_pr

            engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            ctx = mock_pr.analyze.call_args[0][0]
            self.assertIn("phase_scores", ctx)
            self.assertIn("observe", ctx["phase_scores"])
            self.assertIn("analyze", ctx["phase_scores"])

    def test_pattern_recognizer_receives_dimension_trends(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            engine._dimension_trends = {"completeness": [0.5, 0.6, 0.7]}
            mock_pr = MagicMock()
            mock_pr.analyze.return_value = []
            engine._pattern_recognizer = mock_pr

            engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            ctx = mock_pr.analyze.call_args[0][0]
            self.assertIn("dimension_trends", ctx)
            # learn_from_quality_assessment 会先追加当前循环各阶段的维度值
            trends = ctx["dimension_trends"]["completeness"]
            self.assertTrue(trends[:3] == [0.5, 0.6, 0.7])
            self.assertGreater(len(trends), 3)

    def test_discovered_patterns_serialized_in_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            fake_pattern = MagicMock()
            fake_pattern.pattern_id = "p1"
            fake_pattern.type = "FREQUENCY"
            fake_pattern.description = "低质量 analyze 阶段反复出现"
            fake_pattern.confidence = 0.88
            mock_pr = MagicMock()
            mock_pr.analyze.return_value = [fake_pattern]
            engine._pattern_recognizer = mock_pr

            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            patterns = summary["extracted_patterns"]
            self.assertEqual(len(patterns), 1)
            self.assertEqual(patterns[0]["pattern_id"], "p1")
            self.assertAlmostEqual(patterns[0]["confidence"], 0.88)


# ---------------------------------------------------------------------------
# 3) AdaptiveTuner 在反思阶段被调用
# ---------------------------------------------------------------------------


class TestAdaptiveTunerCalledDuringReflection(unittest.TestCase):

    def test_adaptive_tuner_step_invoked(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_at = MagicMock()
            mock_at.step.return_value = None
            mock_at.current_values.return_value = {"quality_threshold": 0.72}
            engine._adaptive_tuner = mock_at

            engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            mock_at.step.assert_called_once()

    def test_adaptive_tuner_receives_performance(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_at = MagicMock()
            mock_at.current_values.return_value = {}
            engine._adaptive_tuner = mock_at

            engine.learn_from_cycle_reflection(_AssessmentFactory.make(overall=0.72))
            metrics = mock_at.step.call_args[0][0]
            self.assertAlmostEqual(metrics["performance"], 0.72)

    def test_adaptive_tuner_receives_min_phase_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_at = MagicMock()
            mock_at.current_values.return_value = {}
            engine._adaptive_tuner = mock_at

            engine.learn_from_cycle_reflection(
                _AssessmentFactory.make(weak_score=0.25)
            )
            metrics = mock_at.step.call_args[0][0]
            self.assertAlmostEqual(metrics["min_phase_score"], 0.25)

    def test_adaptive_tuner_receives_dimension_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            engine._dimension_trends = {
                "completeness": [0.4, 0.5],
                "evidence_quality": [0.3],
            }
            mock_at = MagicMock()
            mock_at.current_values.return_value = {}
            engine._adaptive_tuner = mock_at

            engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            metrics = mock_at.step.call_args[0][0]
            # learn_from_quality_assessment 追加当前阶段维度值后，取最新值
            self.assertIn("completeness", metrics)
            self.assertIn("evidence_quality", metrics)


# ---------------------------------------------------------------------------
# 4) 容错：子模块不可用时不崩溃
# ---------------------------------------------------------------------------


class TestFeedbackLoopResilienceWhenSubmodulesUnavailable(unittest.TestCase):

    def test_no_pattern_recognizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            engine._pattern_recognizer = None
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            self.assertEqual(summary["extracted_patterns"], [])

    def test_no_adaptive_tuner(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            engine._adaptive_tuner = None
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            self.assertEqual(summary["tuned_parameters"], {})

    def test_pattern_recognizer_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_pr = MagicMock()
            mock_pr.analyze.side_effect = RuntimeError("boom")
            engine._pattern_recognizer = mock_pr
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            self.assertEqual(summary["extracted_patterns"], [])

    def test_adaptive_tuner_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _make_engine(tmp)
            mock_at = MagicMock()
            mock_at.step.side_effect = RuntimeError("boom")
            engine._adaptive_tuner = mock_at
            summary = engine.learn_from_cycle_reflection(_AssessmentFactory.make())
            self.assertEqual(summary["tuned_parameters"], {})


if __name__ == "__main__":
    unittest.main()
