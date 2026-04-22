"""Phase M-4: Reflect 策略反馈回流测试。"""

from __future__ import annotations

import unittest

from src.research.strategy_feedback import (
    STRATEGY_FEEDBACK_CONTRACT_VERSION,
    VALID_TARGET_PHASES,
    StrategyFeedback,
    StrategyFeedbackStore,
    StrategySuggestion,
    apply_strategy_feedback_to_context,
    build_strategy_feedback_from_reflect,
)


class TestStrategyFeedback(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual(STRATEGY_FEEDBACK_CONTRACT_VERSION, "strategy-feedback-v1")

    def test_valid_target_phases(self):
        self.assertIn("topic_discovery", VALID_TARGET_PHASES)
        self.assertIn("hypothesis", VALID_TARGET_PHASES)

    def test_suggestion_validation_phase(self):
        with self.assertRaises(ValueError):
            StrategySuggestion(target_phase="unknown", suggestion="x")

    def test_suggestion_validation_empty(self):
        with self.assertRaises(ValueError):
            StrategySuggestion(target_phase="hypothesis", suggestion="")

    def test_suggestion_priority_range(self):
        with self.assertRaises(ValueError):
            StrategySuggestion(target_phase="hypothesis", suggestion="x", priority=2.0)

    def test_suggestion_roundtrip(self):
        s = StrategySuggestion(
            target_phase="hypothesis",
            suggestion="加入温病学派语料",
            priority=0.8,
            rationale="近期 quality 下降",
        )
        restored = StrategySuggestion.from_dict(s.to_dict())
        self.assertEqual(restored.suggestion, "加入温病学派语料")
        self.assertEqual(restored.priority, 0.8)

    def test_feedback_filter_by_phase(self):
        fb = StrategyFeedback(
            cycle_id="c1",
            suggestions=[
                StrategySuggestion(target_phase="hypothesis", suggestion="a"),
                StrategySuggestion(target_phase="observe", suggestion="b"),
            ],
        )
        self.assertEqual(len(fb.suggestions_for("hypothesis")), 1)
        self.assertEqual(fb.suggestions_for("hypothesis")[0].suggestion, "a")

    def test_feedback_roundtrip(self):
        fb = StrategyFeedback(
            cycle_id="c1",
            suggestions=[StrategySuggestion(target_phase="observe", suggestion="x")],
        )
        restored = StrategyFeedback.from_dict(fb.to_dict())
        self.assertEqual(restored.cycle_id, "c1")
        self.assertEqual(len(restored.suggestions), 1)

    def test_store_basic(self):
        store = StrategyFeedbackStore()
        self.assertIsNone(store.latest())
        fb1 = StrategyFeedback(cycle_id="c1")
        fb2 = StrategyFeedback(cycle_id="c2")
        store.append(fb1)
        store.append(fb2)
        self.assertEqual(store.get("c1"), fb1)
        self.assertEqual(store.latest().cycle_id, "c2")
        self.assertEqual(len(store.all()), 2)

    def test_build_from_improvement_plan(self):
        reflect = {
            "results": {
                "improvement_plan": [
                    {"target_phase": "hypothesis", "suggestion": "加入温病学派", "priority": 0.9},
                    {"phase": "observe", "action": "扩大目录范围", "priority": 0.7},
                ]
            }
        }
        fb = build_strategy_feedback_from_reflect(reflect, cycle_id="c1")
        self.assertEqual(len(fb.suggestions), 2)
        phases = {s.target_phase for s in fb.suggestions}
        self.assertEqual(phases, {"hypothesis", "observe"})

    def test_build_from_reflections_and_learning(self):
        reflect = {
            "results": {
                "reflections": [{"phase": "analyze", "suggestion": "增加同病异治对照"}],
                "learning_summary": {
                    "suggestions": [
                        {"target_phase": "publish", "suggestion": "采用 TCM 模板"}
                    ]
                },
            }
        }
        fb = build_strategy_feedback_from_reflect(reflect, cycle_id="c2")
        phases = {s.target_phase for s in fb.suggestions}
        self.assertEqual(phases, {"analyze", "publish"})

    def test_build_dedup_and_unknown_phase_skipped(self):
        reflect = {
            "results": {
                "improvement_plan": [
                    {"target_phase": "hypothesis", "suggestion": "x"},
                    {"target_phase": "hypothesis", "suggestion": "x"},
                    {"target_phase": "nope", "suggestion": "y"},
                ]
            }
        }
        fb = build_strategy_feedback_from_reflect(reflect, cycle_id="c3")
        self.assertEqual(len(fb.suggestions), 1)

    def test_build_requires_mapping(self):
        with self.assertRaises(TypeError):
            build_strategy_feedback_from_reflect("not a mapping", cycle_id="c")  # type: ignore[arg-type]

    def test_apply_to_context_appends(self):
        fb = StrategyFeedback(
            cycle_id="c1",
            suggestions=[
                StrategySuggestion(target_phase="hypothesis", suggestion="A"),
                StrategySuggestion(target_phase="observe", suggestion="B"),
            ],
        )
        ctx: dict = {}
        apply_strategy_feedback_to_context(fb, ctx, target_phase="hypothesis")
        self.assertIn("strategy_feedback", ctx)
        self.assertEqual(len(ctx["strategy_feedback"]["hypothesis"]), 1)
        # observe 没被应用
        self.assertNotIn("observe", ctx["strategy_feedback"])
        self.assertEqual(ctx["strategy_feedback"]["_source_cycle_id"], "c1")

    def test_apply_dedup_existing(self):
        fb = StrategyFeedback(
            cycle_id="c1",
            suggestions=[StrategySuggestion(target_phase="hypothesis", suggestion="A")],
        )
        ctx = {"strategy_feedback": {"hypothesis": [{"suggestion": "A", "priority": 0.5}]}}
        apply_strategy_feedback_to_context(fb, ctx, target_phase="hypothesis")
        self.assertEqual(len(ctx["strategy_feedback"]["hypothesis"]), 1)

    def test_apply_invalid_phase(self):
        fb = StrategyFeedback(cycle_id="c1")
        with self.assertRaises(ValueError):
            apply_strategy_feedback_to_context(fb, {}, target_phase="unknown")


if __name__ == "__main__":
    unittest.main()
