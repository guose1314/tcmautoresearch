"""Phase I-3 — SmallModelOptimizer telemetry & benchmark hit-rate metrics."""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from src.infra.small_model_optimizer import CallPlan, SmallModelOptimizer
from tools.small_model_phase_benchmark import (
    _summarize_results,
    build_learning_recommendations,
)


def _make_dossier(payload_size: int = 200) -> Dict[str, str]:
    return {
        "objective": "评估黄芪汤对气虚的疗效",
        "evidence": "证据：" + ("黄芪补气改善疲劳；多项 RCT 显示有效。" * payload_size),
    }


class TestCallPlanTelemetry(unittest.TestCase):
    """CallPlan 新增的 template_hit / budget_hit / layer_hit 字段。"""

    def test_proceed_path_populates_telemetry(self):
        optimizer = SmallModelOptimizer()
        plan = optimizer.prepare_call(
            phase="analyze",
            task_type="summarization",
            dossier_sections=_make_dossier(payload_size=4),
        )
        self.assertEqual(plan.action, "proceed")
        # analyze 阶段默认框架是 analytical
        self.assertEqual(plan.framework_name, "analytical")
        self.assertTrue(plan.template_hit)
        self.assertTrue(plan.budget_hit)
        self.assertGreaterEqual(plan.max_layer_available, 0)
        # telemetry_dict 必须包含全部新字段
        td = plan.telemetry_dict()
        for key in ("template_hit", "budget_hit", "layer_hit", "max_layer_available", "complexity_tier"):
            self.assertIn(key, td)

    def test_decompose_marks_budget_miss(self):
        # 选小窗口、再灌入超大上下文 → 必然 decompose
        optimizer = SmallModelOptimizer(model_context_window=512, output_reserve=128)
        big_dossier = {
            "evidence": "证据片段：" + ("黄芪补气改善气虚相关疲劳症状。" * 800),
            "objective": "评估假说" + ("，包含多个证据来源" * 60),
        }
        plan = optimizer.prepare_call(
            phase="hypothesis",
            task_type="hypothesis_generation",
            dossier_sections=big_dossier,
        )
        self.assertEqual(plan.action, "decompose")
        self.assertFalse(plan.budget_hit)
        # hypothesis 默认框架仍是 analytical
        self.assertEqual(plan.framework_name, "analytical")
        self.assertTrue(plan.template_hit)

    def test_skip_marks_budget_and_layer_miss(self):
        optimizer = SmallModelOptimizer()
        plan = optimizer.prepare_call(
            phase="observe",
            task_type="entity_extraction",
            dossier_sections=_make_dossier(payload_size=2),
            cache_hit_likelihood=0.95,
        )
        self.assertEqual(plan.action, "skip")
        self.assertFalse(plan.budget_hit)
        self.assertFalse(plan.layer_hit)


class TestBenchmarkSummaryHitRates(unittest.TestCase):
    """_summarize_results 必须输出 Phase I-3 命中率字段。"""

    def _make_case(self, *, action: str, template_hit: bool, budget_hit: bool, layer_hit: bool) -> Dict[str, Any]:
        return {
            "score_components": {
                "framework_match": template_hit,
                "action_match": True,
                "budget_hit": budget_hit,
                "beats_baseline": True,
            },
            "telemetry": {
                "action": action,
                "template_hit": template_hit,
                "budget_hit": budget_hit,
                "layer_hit": layer_hit,
            },
            "optimized": {"action": action, "framework_name": "analytical"},
            "quality_score": 1.0,
            "token_delta": 100,
        }

    def test_summary_emits_phase_i3_rates(self):
        results = [
            self._make_case(action="proceed", template_hit=True, budget_hit=True, layer_hit=True),
            self._make_case(action="decompose", template_hit=True, budget_hit=False, layer_hit=False),
            self._make_case(action="skip", template_hit=False, budget_hit=False, layer_hit=False),
            self._make_case(action="proceed", template_hit=False, budget_hit=True, layer_hit=True),
        ]
        summary = _summarize_results(results)
        self.assertEqual(summary["case_count"], 4)
        self.assertAlmostEqual(summary["template_default_hit_rate"], 0.5, places=4)
        self.assertAlmostEqual(summary["budget_proceed_hit_rate"], 0.5, places=4)
        self.assertAlmostEqual(summary["layer_top_hit_rate"], 0.5, places=4)
        self.assertAlmostEqual(summary["decompose_rate"], 0.25, places=4)
        self.assertAlmostEqual(summary["skip_rate"], 0.25, places=4)

    def test_empty_summary_has_phase_i3_keys(self):
        summary = _summarize_results([])
        for key in (
            "template_default_hit_rate",
            "budget_proceed_hit_rate",
            "layer_top_hit_rate",
            "decompose_rate",
            "skip_rate",
        ):
            self.assertIn(key, summary)
            self.assertEqual(summary[key], 0.0)


class TestLearningRecommendations(unittest.TestCase):
    """build_learning_recommendations 输出可被 PolicyAdjuster 消费。"""

    def _phase_summary(self, *, template: float, budget: float, layer: float, skip: float, decompose: float) -> Dict[str, Any]:
        return {
            "summary": {
                "template_default_hit_rate": template,
                "budget_proceed_hit_rate": budget,
                "layer_top_hit_rate": layer,
                "skip_rate": skip,
                "decompose_rate": decompose,
            }
        }

    def test_low_template_rate_boosts_default_framework(self):
        thresholds = {
            "template_default_hit_rate_target": 0.7,
            "budget_proceed_hit_rate_target": 0.8,
            "layer_top_hit_rate_target": 0.5,
            "skip_rate_max": 0.3,
            "decompose_rate_max": 0.3,
        }
        phase_reports = {
            "analyze": self._phase_summary(template=0.2, budget=0.9, layer=0.9, skip=0.0, decompose=0.0),
        }
        recs = build_learning_recommendations(phase_reports, thresholds=thresholds)
        # analyze 默认框架是 analytical
        self.assertIn("analytical", recs["template_preference_adjustments"])
        self.assertGreater(recs["template_preference_adjustments"]["analytical"], 0.0)
        self.assertIn("template_default_hit_rate", recs["phase_signals"]["analyze"]["below_targets"])

    def test_high_decompose_rate_emits_threshold_signal(self):
        thresholds = {
            "template_default_hit_rate_target": 0.0,
            "budget_proceed_hit_rate_target": 0.0,
            "layer_top_hit_rate_target": 0.0,
            "skip_rate_max": 1.0,
            "decompose_rate_max": 0.1,
        }
        phase_reports = {
            "hypothesis": self._phase_summary(template=1.0, budget=0.5, layer=1.0, skip=0.0, decompose=0.5),
        }
        recs = build_learning_recommendations(phase_reports, thresholds=thresholds)
        self.assertIn("hypothesis", recs["phase_threshold_adjustments"])
        self.assertIn("context_budget_tighten", recs["phase_threshold_adjustments"]["hypothesis"])


if __name__ == "__main__":
    unittest.main()
