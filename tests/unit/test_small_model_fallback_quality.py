# tests/unit/test_small_model_fallback_quality.py
"""Phase I-4 — fallback 质量矩阵 + regression baseline 单元测试。

覆盖：
  - quality_assessor.assess_fallback_quality / build_phase_fallback_metadata
  - DynamicInvocationStrategy.record_fallback_quality + CostMetrics 字段
  - tools.small_model_phase_benchmark._build_fallback_quality_matrix
  - tools.small_model_phase_benchmark.build_regression_baseline / export_regression_baseline
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.infra.dynamic_invocation_strategy import DynamicInvocationStrategy
from src.quality.quality_assessor import (
    DEFAULT_FALLBACK_DELTA_THRESHOLD,
    FALLBACK_ACTIONS,
    assess_fallback_quality,
    build_phase_fallback_metadata,
)
from tools.small_model_phase_benchmark import (
    _build_fallback_quality_matrix,
    build_regression_baseline,
    export_regression_baseline,
)


def _case(action: str, quality: float, *, framework: str = "analytical") -> dict:
    return {
        "optimized": {"action": action, "framework_name": framework},
        "quality_score": quality,
        "score_components": {
            "action_match": True,
            "framework_match": True,
            "budget_hit": True,
            "beats_baseline": True,
        },
    }


class TestAssessFallbackQuality(unittest.TestCase):
    def test_proceed_action_always_accepted(self):
        result = assess_fallback_quality(
            action="proceed", baseline_score=1.0, optimized_score=0.5
        )
        self.assertTrue(result["fallback_acceptance"])
        self.assertEqual(result["fallback_reason"], "no_fallback")

    def test_skip_within_threshold_accepted(self):
        result = assess_fallback_quality(
            action="skip", baseline_score=0.9, optimized_score=0.85
        )
        self.assertTrue(result["fallback_acceptance"])
        self.assertEqual(result["action"], "skip")
        self.assertIn("within_threshold", result["fallback_reason"])

    def test_skip_below_threshold_rejected(self):
        result = assess_fallback_quality(
            action="skip", baseline_score=0.9, optimized_score=0.4
        )
        self.assertFalse(result["fallback_acceptance"])
        self.assertIn("below_baseline", result["fallback_reason"])

    def test_decompose_delta_calculated(self):
        result = assess_fallback_quality(
            action="decompose", baseline_score=0.8, optimized_score=0.75
        )
        self.assertAlmostEqual(result["delta"], -0.05, places=4)
        self.assertTrue(result["fallback_acceptance"])

    def test_retry_simplified_clamped_to_unit_range(self):
        result = assess_fallback_quality(
            action="retry_simplified", baseline_score=0.8, optimized_score=1.5
        )
        self.assertEqual(result["fallback_quality_score"], 1.0)
        self.assertTrue(result["fallback_acceptance"])

    def test_negative_optimized_clamped(self):
        result = assess_fallback_quality(
            action="skip", baseline_score=0.5, optimized_score=-0.2
        )
        self.assertEqual(result["fallback_quality_score"], 0.0)
        self.assertFalse(result["fallback_acceptance"])

    def test_default_threshold_constant(self):
        self.assertGreater(DEFAULT_FALLBACK_DELTA_THRESHOLD, 0.0)
        self.assertLessEqual(DEFAULT_FALLBACK_DELTA_THRESHOLD, 0.5)

    def test_fallback_actions_constant_includes_three(self):
        for action in ("skip", "decompose", "retry_simplified"):
            self.assertIn(action, FALLBACK_ACTIONS)

    def test_reason_extra_appended(self):
        result = assess_fallback_quality(
            action="skip",
            baseline_score=1.0,
            optimized_score=0.95,
            reason_extra="rules_only",
        )
        self.assertTrue(result["fallback_reason"].endswith(":rules_only"))

    def test_invalid_score_coerced_to_zero(self):
        result = assess_fallback_quality(
            action="skip", baseline_score="bad", optimized_score=None
        )
        self.assertEqual(result["baseline_score"], 0.0)
        self.assertEqual(result["fallback_quality_score"], 0.0)


class TestBuildPhaseFallbackMetadata(unittest.TestCase):
    def test_returns_three_phase_keys_plus_matrix(self):
        meta = build_phase_fallback_metadata(
            action="skip", baseline_score=1.0, optimized_score=0.6
        )
        for key in (
            "fallback_quality_score",
            "fallback_acceptance",
            "fallback_reason",
            "fallback_quality_matrix",
        ):
            self.assertIn(key, meta)

    def test_matrix_carries_action_and_delta(self):
        meta = build_phase_fallback_metadata(
            action="decompose", baseline_score=0.8, optimized_score=0.78
        )
        matrix = meta["fallback_quality_matrix"]
        self.assertEqual(matrix["action"], "decompose")
        self.assertAlmostEqual(matrix["delta"], -0.02, places=4)


class TestDynamicInvocationFallbackTracking(unittest.TestCase):
    def test_record_fallback_quality_updates_metrics(self):
        strategy = DynamicInvocationStrategy()
        strategy.record_fallback_quality(0.8, accepted=True)
        strategy.record_fallback_quality(0.4, accepted=False)
        report = strategy.get_cost_report()
        self.assertEqual(report["fallback_samples"], 2)
        self.assertEqual(report["fallback_acceptances"], 1)
        self.assertAlmostEqual(report["fallback_acceptance_rate"], 0.5, places=4)
        self.assertAlmostEqual(report["avg_fallback_quality_score"], 0.6, places=4)

    def test_record_fallback_quality_clamps_score(self):
        strategy = DynamicInvocationStrategy()
        strategy.record_fallback_quality(1.5, accepted=True)
        strategy.record_fallback_quality(-0.3, accepted=False)
        report = strategy.get_cost_report()
        self.assertEqual(report["fallback_samples"], 2)
        # 1.0 + 0.0 = 1.0 → mean 0.5
        self.assertAlmostEqual(report["avg_fallback_quality_score"], 0.5, places=4)

    def test_no_samples_returns_zero_rates(self):
        strategy = DynamicInvocationStrategy()
        report = strategy.get_cost_report()
        self.assertEqual(report["fallback_samples"], 0)
        self.assertEqual(report["fallback_acceptance_rate"], 0.0)
        self.assertEqual(report["avg_fallback_quality_score"], 0.0)


class TestBenchmarkFallbackMatrix(unittest.TestCase):
    def test_matrix_groups_by_action(self):
        results = [
            _case("proceed", 0.9),
            _case("proceed", 1.0),
            _case("skip", 0.7),
            _case("decompose", 0.8),
        ]
        matrix = _build_fallback_quality_matrix(results)
        self.assertIn("proceed", matrix["by_action"])
        self.assertIn("skip", matrix["by_action"])
        self.assertIn("decompose", matrix["by_action"])
        self.assertEqual(matrix["by_action"]["skip"]["count"], 1)

    def test_baseline_is_proceed_average(self):
        results = [
            _case("proceed", 0.8),
            _case("proceed", 1.0),
            _case("skip", 0.5),
        ]
        matrix = _build_fallback_quality_matrix(results)
        self.assertAlmostEqual(matrix["baseline_score"], 0.9, places=4)

    def test_baseline_falls_back_to_overall_when_no_proceed(self):
        results = [_case("skip", 0.4), _case("decompose", 0.8)]
        matrix = _build_fallback_quality_matrix(results)
        self.assertAlmostEqual(matrix["baseline_score"], 0.6, places=4)

    def test_fallback_acceptance_rate_computed(self):
        results = [
            _case("proceed", 1.0),
            _case("skip", 0.95),  # accepted (within 0.1)
            _case("skip", 0.5),   # rejected
        ]
        matrix = _build_fallback_quality_matrix(results)
        self.assertEqual(matrix["fallback_count"], 2)
        self.assertAlmostEqual(matrix["fallback_acceptance_rate"], 0.5, places=4)

    def test_empty_results_safe(self):
        matrix = _build_fallback_quality_matrix([])
        self.assertEqual(matrix["fallback_count"], 0)
        self.assertEqual(matrix["fallback_acceptance_rate"], 1.0)
        self.assertEqual(matrix["by_action"], {})


class TestRegressionBaseline(unittest.TestCase):
    def _sample_report(self) -> dict:
        return {
            "phase_reports": {
                "hypothesis": {
                    "summary": {
                        "average_quality_score": 0.85,
                        "fallback_quality_matrix": _build_fallback_quality_matrix(
                            [_case("proceed", 0.9), _case("skip", 0.85)]
                        ),
                        "fallback_acceptance_rate": 1.0,
                        "fallback_baseline_delta": -0.05,
                    }
                },
                "publish": {
                    "summary": {
                        "average_quality_score": 0.7,
                        "fallback_quality_matrix": _build_fallback_quality_matrix(
                            [_case("proceed", 0.8), _case("skip", 0.4)]
                        ),
                        "fallback_acceptance_rate": 0.0,
                        "fallback_baseline_delta": -0.4,
                    }
                },
            },
            "global_summary": {
                "average_quality_score": 0.78,
                "fallback_quality_matrix": _build_fallback_quality_matrix(
                    [_case("proceed", 0.9), _case("skip", 0.8), _case("skip", 0.4)]
                ),
                "fallback_acceptance_rate": 0.5,
                "fallback_baseline_delta": -0.25,
            },
        }

    def test_build_returns_per_phase_baselines(self):
        baseline = build_regression_baseline(self._sample_report())
        self.assertIn("hypothesis", baseline["phase_baselines"])
        self.assertIn("publish", baseline["phase_baselines"])
        hyp = baseline["phase_baselines"]["hypothesis"]
        self.assertIn("baseline_score", hyp)
        self.assertIn("min_acceptable_score", hyp)
        self.assertGreaterEqual(hyp["baseline_score"], hyp["min_acceptable_score"])

    def test_min_acceptable_equals_baseline_minus_threshold(self):
        baseline = build_regression_baseline(self._sample_report(), delta_threshold=0.1)
        hyp = baseline["phase_baselines"]["hypothesis"]
        self.assertAlmostEqual(
            hyp["min_acceptable_score"], hyp["baseline_score"] - 0.1, places=4
        )

    def test_global_block_present(self):
        baseline = build_regression_baseline(self._sample_report())
        self.assertIn("global", baseline)
        self.assertIn("baseline_score", baseline["global"])

    def test_export_writes_json_file(self):
        with TemporaryDirectory() as tmp:
            path = export_regression_baseline(self._sample_report(), Path(tmp))
            self.assertTrue(Path(path).exists())
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertIn("phase_baselines", payload)
            self.assertIn("delta_threshold", payload)


if __name__ == "__main__":
    unittest.main()