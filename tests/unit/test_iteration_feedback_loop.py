# tests/unit/test_iteration_feedback_loop.py
"""
IterationCycle 真实迭代闭环单元测试

覆盖：
  - _extract_iteration_feedback: 从迭代结果提取反馈
  - _check_convergence: 多迭代质量收敛检测
  - _aggregate_iteration_quality: 真实质量分聚合（替代硬编码）
  - run_full_cycle_demo 反馈传播集成
"""

import unittest
from unittest.mock import patch

from src.cycle.cycle_runner import (
    _aggregate_iteration_quality,
    _check_convergence,
    _extract_iteration_feedback,
)

# ---------------------------------------------------------------------------
# _extract_iteration_feedback
# ---------------------------------------------------------------------------


class TestExtractIterationFeedback(unittest.TestCase):

    def test_extracts_quality_from_reflect_module(self):
        result = {
            "iteration_number": 1,
            "status": "completed",
            "modules": [
                {"module": "observe", "output_data": {}},
                {
                    "module": "reflect",
                    "output_data": {
                        "quality_assessment": {
                            "overall_cycle_score": 0.72,
                            "weaknesses": [{"phase": "analyze"}],
                        },
                        "improvement_plan": ["提升 analyze 阶段完整性"],
                        "learning_summary": {"recorded_phases": ["observe"]},
                    },
                },
            ],
            "academic_insights": [
                {"type": "quality_assessment", "confidence": 0.72},
            ],
            "recommendations": [
                {"type": "improvement", "title": "优化 analyze 阶段"},
            ],
        }
        fb = _extract_iteration_feedback(result)
        self.assertAlmostEqual(fb["quality_assessment"]["overall_cycle_score"], 0.72)
        self.assertEqual(fb["improvement_plan"], ["提升 analyze 阶段完整性"])
        self.assertIsNotNone(fb["learning_summary"])
        self.assertAlmostEqual(fb["cycle_quality_score"], 0.72)
        self.assertEqual(fb["previous_recommendations"], ["优化 analyze 阶段"])
        self.assertEqual(fb["iteration_number"], 1)
        self.assertEqual(fb["status"], "completed")

    def test_empty_result_gives_minimal_feedback(self):
        fb = _extract_iteration_feedback({"status": "failed"})
        self.assertEqual(fb["status"], "failed")
        self.assertEqual(fb["iteration_number"], 0)
        self.assertNotIn("quality_assessment", fb)
        self.assertNotIn("improvement_plan", fb)

    def test_no_reflect_module_skips_quality(self):
        result = {
            "modules": [{"module": "observe", "output_data": {}}],
            "academic_insights": [],
            "recommendations": [],
        }
        fb = _extract_iteration_feedback(result)
        self.assertNotIn("quality_assessment", fb)


# ---------------------------------------------------------------------------
# _check_convergence
# ---------------------------------------------------------------------------


class TestCheckConvergence(unittest.TestCase):

    def _make_iteration(self, quality_score: float) -> dict:
        return {
            "academic_insights": [
                {"type": "quality_assessment", "confidence": quality_score},
            ],
        }

    def test_single_iteration_never_converges(self):
        self.assertFalse(_check_convergence([self._make_iteration(0.9)]))

    def test_two_stable_high_iterations_converge(self):
        iters = [self._make_iteration(0.85), self._make_iteration(0.86)]
        self.assertTrue(_check_convergence(iters))

    def test_two_low_iterations_do_not_converge(self):
        iters = [self._make_iteration(0.5), self._make_iteration(0.5)]
        self.assertFalse(_check_convergence(iters))

    def test_unstable_iterations_do_not_converge(self):
        iters = [self._make_iteration(0.9), self._make_iteration(0.82)]
        self.assertFalse(_check_convergence(iters))

    def test_custom_threshold(self):
        iters = [self._make_iteration(0.6), self._make_iteration(0.62)]
        self.assertFalse(_check_convergence(iters, {"minimum_stable_quality_score": 0.8}))
        self.assertTrue(_check_convergence(iters, {"minimum_stable_quality_score": 0.5}))

    def test_no_insights_do_not_converge(self):
        iters = [{"academic_insights": []}, {"academic_insights": []}]
        self.assertFalse(_check_convergence(iters))


# ---------------------------------------------------------------------------
# _aggregate_iteration_quality
# ---------------------------------------------------------------------------


class TestAggregateIterationQuality(unittest.TestCase):

    def _make_iteration(self, quality_score: float) -> dict:
        return {
            "academic_insights": [
                {"type": "quality_assessment", "confidence": quality_score},
            ],
        }

    def test_empty_iterations_return_zero(self):
        result = _aggregate_iteration_quality([])
        self.assertEqual(result["overall_quality_score"], 0.0)
        self.assertEqual(result["source"], "no_data")

    def test_single_iteration(self):
        result = _aggregate_iteration_quality([self._make_iteration(0.78)])
        self.assertAlmostEqual(result["overall_quality_score"], 0.78, places=2)
        self.assertAlmostEqual(result["average_quality_score"], 0.78, places=2)
        self.assertEqual(result["iteration_count"], 1)
        self.assertEqual(result["source"], "aggregated_from_reflect")

    def test_multiple_iterations(self):
        iters = [self._make_iteration(0.6), self._make_iteration(0.7), self._make_iteration(0.8)]
        result = _aggregate_iteration_quality(iters)
        self.assertAlmostEqual(result["overall_quality_score"], 0.8, places=2)
        self.assertAlmostEqual(result["average_quality_score"], 0.7, places=2)
        self.assertAlmostEqual(result["best_quality_score"], 0.8, places=2)
        self.assertEqual(result["quality_trend"], "improving")
        self.assertEqual(result["iteration_count"], 3)

    def test_declining_trend(self):
        iters = [self._make_iteration(0.9), self._make_iteration(0.7)]
        result = _aggregate_iteration_quality(iters)
        self.assertEqual(result["quality_trend"], "stable")  # last < first → stable

    def test_no_insights_returns_no_data(self):
        iters = [{"academic_insights": []}]
        result = _aggregate_iteration_quality(iters)
        self.assertEqual(result["source"], "no_data")

    def test_derived_fields_are_proportional(self):
        iters = [self._make_iteration(0.85)]
        result = _aggregate_iteration_quality(iters)
        self.assertAlmostEqual(result["scientific_validity"], 0.85 * 0.95, places=3)
        self.assertAlmostEqual(result["methodological_quality"], 0.85 * 0.90, places=3)
        self.assertAlmostEqual(result["reproducibility"], 0.85 * 0.98, places=3)
        self.assertLessEqual(result["standard_compliance"], 1.0)


# ---------------------------------------------------------------------------
# run_full_cycle_demo: 反馈传播验证
# ---------------------------------------------------------------------------


class TestFeedbackPropagation(unittest.TestCase):
    """验证 run_full_cycle_demo 将反馈传递给下一次迭代。"""

    def test_feedback_passed_to_second_iteration(self):
        """Mock run_iteration，验证第二次调用包含 previous_feedback。"""
        captured_inputs = []

        def fake_iteration(iteration_number, input_data, max_iterations=5,
                           shared_modules=None, governance_config=None):
            captured_inputs.append(dict(input_data))
            return {
                "iteration_id": f"iter_{iteration_number}",
                "iteration_number": iteration_number,
                "status": "completed",
                "duration": 0.1,
                "modules": [
                    {
                        "module": "reflect",
                        "output_data": {
                            "quality_assessment": {"overall_cycle_score": 0.7},
                            "improvement_plan": ["improve X"],
                        },
                    }
                ],
                "academic_insights": [
                    {"type": "quality_assessment", "confidence": 0.7},
                ],
                "recommendations": [],
                "failed_operations": [],
                "analysis_summary": {"module_count": 1, "failed_operation_count": 0},
                "metadata": {"max_iterations": max_iterations, "pipeline_mode": True},
            }

        from src.cycle.cycle_runner import ModuleLifecycle, run_full_cycle_demo

        with patch("src.cycle.cycle_runner.time.sleep"):
            result = run_full_cycle_demo(
                max_iterations=2,
                sample_data=["测试方剂"],
                config_path=None,
                run_iteration=fake_iteration,
                module_lifecycle=ModuleLifecycle(
                    build=lambda: [],
                    initialize=lambda _: None,
                    cleanup=lambda _: None,
                ),
            )

        self.assertEqual(len(captured_inputs), 2)
        # 第一次没有 previous_feedback
        self.assertNotIn("previous_feedback", captured_inputs[0])
        # 第二次有 previous_feedback
        self.assertIn("previous_feedback", captured_inputs[1])
        fb = captured_inputs[1]["previous_feedback"]
        self.assertEqual(fb["iteration_number"], 1)
        self.assertEqual(fb["improvement_plan"], ["improve X"])

    def test_convergence_stops_early(self):
        """质量稳定达标时应提前终止。"""
        call_count = [0]

        def fake_iteration(iteration_number, input_data, max_iterations=5,
                           shared_modules=None, governance_config=None):
            call_count[0] += 1
            return {
                "iteration_id": f"iter_{iteration_number}",
                "iteration_number": iteration_number,
                "status": "completed",
                "duration": 0.1,
                "modules": [],
                "academic_insights": [
                    {"type": "quality_assessment", "confidence": 0.92},
                ],
                "recommendations": [],
                "failed_operations": [],
                "analysis_summary": {"module_count": 0, "failed_operation_count": 0},
                "metadata": {"max_iterations": max_iterations},
            }

        from src.cycle.cycle_runner import ModuleLifecycle, run_full_cycle_demo

        with patch("src.cycle.cycle_runner.time.sleep"):
            result = run_full_cycle_demo(
                max_iterations=5,
                sample_data=["测试方剂"],
                config_path=None,
                run_iteration=fake_iteration,
                module_lifecycle=ModuleLifecycle(
                    build=lambda: [],
                    initialize=lambda _: None,
                    cleanup=lambda _: None,
                ),
            )

        # 应在第 2 轮收敛，不会跑满 5 轮
        self.assertEqual(call_count[0], 2)
        self.assertEqual(result["performance_metrics"]["total_iterations"], 2)

    def test_quality_assessment_uses_real_scores(self):
        """quality_assessment 应使用真实聚合分，非硬编码。"""
        def fake_iteration(iteration_number, input_data, max_iterations=5,
                           shared_modules=None, governance_config=None):
            return {
                "iteration_id": f"iter_{iteration_number}",
                "iteration_number": iteration_number,
                "status": "completed",
                "duration": 0.1,
                "modules": [],
                "academic_insights": [
                    {"type": "quality_assessment", "confidence": 0.65},
                ],
                "recommendations": [],
                "failed_operations": [],
                "analysis_summary": {"module_count": 0, "failed_operation_count": 0},
                "metadata": {"max_iterations": max_iterations},
            }

        from src.cycle.cycle_runner import ModuleLifecycle, run_full_cycle_demo

        with patch("src.cycle.cycle_runner.time.sleep"):
            result = run_full_cycle_demo(
                max_iterations=1,
                sample_data=["测试方剂"],
                config_path=None,
                run_iteration=fake_iteration,
                module_lifecycle=ModuleLifecycle(
                    build=lambda: [],
                    initialize=lambda _: None,
                    cleanup=lambda _: None,
                ),
            )

        qa = result["academic_analysis"]["quality_assessment"]
        # 应反映真实分数 0.65，而非硬编码 0.92
        self.assertAlmostEqual(qa["overall_quality_score"], 0.65, places=2)
        self.assertEqual(qa["source"], "aggregated_from_reflect")


if __name__ == "__main__":
    unittest.main()
