"""Learning-strategy governance contract tests.

Validates the StrategyApplicationTracker, build_strategy_snapshot,
build_strategy_diff, and pipeline-level manifest/summary infrastructure.
"""
from __future__ import annotations

import unittest

from src.research.learning_strategy import (
    StrategyApplicationTracker,
    build_strategy_diff,
    build_strategy_snapshot,
)


class TestBuildStrategySnapshot(unittest.TestCase):
    """build_strategy_snapshot should produce a stable, reproducible fingerprint."""

    def test_snapshot_returns_fingerprint(self):
        config = {
            "learning_strategy": {"quality_threshold": 0.8, "strategy_version": "v2"},
            "learned_runtime_parameters": {"quality_threshold": 0.8},
        }
        snap = build_strategy_snapshot(None, config)
        self.assertIn("fingerprint", snap)
        self.assertIsInstance(snap["fingerprint"], str)
        self.assertGreater(len(snap["fingerprint"]), 0)

    def test_snapshot_stable_across_calls(self):
        config = {
            "learning_strategy": {"quality_threshold": 0.85},
            "learned_runtime_parameters": {"quality_threshold": 0.85},
        }
        snap1 = build_strategy_snapshot(None, config)
        snap2 = build_strategy_snapshot(None, config)
        self.assertEqual(snap1["fingerprint"], snap2["fingerprint"])

    def test_snapshot_varies_with_strategy(self):
        config_a = {
            "learning_strategy": {"quality_threshold": 0.85},
            "learned_runtime_parameters": {"quality_threshold": 0.85},
        }
        config_b = {
            "learning_strategy": {"quality_threshold": 0.50},
            "learned_runtime_parameters": {"quality_threshold": 0.50},
        }
        snap_a = build_strategy_snapshot(None, config_a)
        snap_b = build_strategy_snapshot(None, config_b)
        self.assertNotEqual(snap_a["fingerprint"], snap_b["fingerprint"])

    def test_snapshot_empty_config(self):
        snap = build_strategy_snapshot(None, {})
        self.assertIn("fingerprint", snap)
        self.assertEqual(snap["strategy"], {})

    def test_snapshot_context_overrides_config(self):
        context = {"learning_strategy": {"quality_threshold": 0.9}}
        config = {"learning_strategy": {"quality_threshold": 0.5}}
        snap = build_strategy_snapshot(context, config)
        self.assertEqual(snap["strategy"]["quality_threshold"], 0.9)


class TestStrategyApplicationTracker(unittest.TestCase):
    """StrategyApplicationTracker records per-phase decisions and outputs standard metadata."""

    def _make_tracker(self, phase="test", has_strategy=True):
        config = {}
        if has_strategy:
            config["learning_strategy"] = {
                "quality_threshold": 0.82,
                "strategy_version": "v1",
            }
            config["learned_runtime_parameters"] = {"quality_threshold": 0.82}
        return StrategyApplicationTracker(phase, None, config)

    def test_applied_true_when_strategy_present(self):
        tracker = self._make_tracker(has_strategy=True)
        self.assertTrue(tracker.applied)

    def test_applied_false_when_no_strategy(self):
        tracker = self._make_tracker(has_strategy=False)
        self.assertFalse(tracker.applied)

    def test_record_and_to_metadata(self):
        tracker = self._make_tracker()
        tracker.record(
            "sample_size", 30, 36, "quality_threshold >= 0.82",
            parameter="quality_threshold", parameter_value=0.82,
        )
        meta = tracker.to_metadata()
        self.assertTrue(meta["applied"])
        self.assertEqual(meta["decision_count"], 1)
        self.assertEqual(len(meta["decisions"]), 1)
        decision = meta["decisions"][0]
        self.assertEqual(decision["name"], "sample_size")
        self.assertEqual(decision["baseline"], 30)
        self.assertEqual(decision["adjusted"], 36)
        self.assertEqual(decision["parameter"], "quality_threshold")
        self.assertEqual(decision["parameter_value"], 0.82)

    def test_multiple_records(self):
        tracker = self._make_tracker()
        tracker.record("a", 1, 2, "r1")
        tracker.record("b", 10, 15, "r2")
        meta = tracker.to_metadata()
        self.assertEqual(meta["decision_count"], 2)
        self.assertEqual(len(meta["decisions"]), 2)

    def test_to_metadata_no_decisions(self):
        tracker = self._make_tracker()
        meta = tracker.to_metadata()
        self.assertTrue(meta["applied"])
        self.assertEqual(meta["decision_count"], 0)
        self.assertNotIn("decisions", meta)

    def test_to_metadata_not_applied(self):
        tracker = self._make_tracker(has_strategy=False)
        meta = tracker.to_metadata()
        self.assertFalse(meta["applied"])
        self.assertNotIn("strategy_fingerprint", meta)
        self.assertNotIn("decisions", meta)

    def test_fingerprint_matches_snapshot(self):
        config = {
            "learning_strategy": {"quality_threshold": 0.82, "strategy_version": "v1"},
            "learned_runtime_parameters": {"quality_threshold": 0.82},
        }
        tracker = StrategyApplicationTracker("observe", None, config)
        snap = build_strategy_snapshot(None, config)
        self.assertEqual(tracker.fingerprint, snap["fingerprint"])


class TestBuildStrategyDiff(unittest.TestCase):
    """build_strategy_diff detects changes between two snapshots."""

    def test_no_change(self):
        config = {"learning_strategy": {"quality_threshold": 0.8}}
        snap = build_strategy_snapshot(None, config)
        diff = build_strategy_diff(snap, snap)
        self.assertFalse(diff["changed"])
        self.assertEqual(diff["change_count"], 0)
        self.assertEqual(diff["before_fingerprint"], diff["after_fingerprint"])

    def test_detects_tuned_parameter_change(self):
        config_before = {
            "learning_strategy": {"quality_threshold": 0.7},
            "learned_runtime_parameters": {"quality_threshold": 0.7},
        }
        config_after = {
            "learning_strategy": {"quality_threshold": 0.9},
            "learned_runtime_parameters": {"quality_threshold": 0.9},
        }
        before = build_strategy_snapshot(None, config_before)
        after = build_strategy_snapshot(None, config_after)
        diff = build_strategy_diff(before, after)
        self.assertTrue(diff["changed"])
        self.assertGreater(diff["change_count"], 0)
        param_names = [c["parameter"] for c in diff["changes"]]
        self.assertIn("quality_threshold", param_names)

    def test_detects_strategy_field_change(self):
        before = {
            "strategy": {"strategy_version": "v1"},
            "tuned_parameters": {},
            "fingerprint": "aaa",
        }
        after = {
            "strategy": {"strategy_version": "v2"},
            "tuned_parameters": {},
            "fingerprint": "bbb",
        }
        diff = build_strategy_diff(before, after)
        self.assertTrue(diff["changed"])
        param_names = [c["parameter"] for c in diff["changes"]]
        self.assertIn("strategy_version", param_names)

    def test_empty_snapshots(self):
        diff = build_strategy_diff({}, {})
        self.assertFalse(diff["changed"])
        self.assertEqual(diff["change_count"], 0)


class TestPipelineLearningManifest(unittest.TestCase):
    """Pipeline-level manifest registry and summary builder contract."""

    def _make_pipeline_stub(self):
        """Minimal stub with the 4 learning governance methods."""
        from src.research.learning_strategy import build_strategy_snapshot as _snap

        class Stub:
            def __init__(self):
                self.config = {
                    "learning_strategy": {"quality_threshold": 0.82},
                    "learned_runtime_parameters": {"quality_threshold": 0.82},
                }
                self._learning_strategy_snapshot = {}
                self._learning_phase_manifests = []

            def freeze_learning_strategy_snapshot(self):
                self._learning_strategy_snapshot = _snap(None, self.config)
                self._learning_phase_manifests = []
                return dict(self._learning_strategy_snapshot)

            def get_learning_strategy_snapshot(self):
                return dict(self._learning_strategy_snapshot)

            def register_phase_learning_manifest(self, manifest):
                self._learning_phase_manifests.append(manifest)

            def build_learning_application_summary(self):
                snapshot_fp = self._learning_strategy_snapshot.get("fingerprint")
                phase_fps = [
                    m.get("strategy_fingerprint")
                    for m in self._learning_phase_manifests
                    if m.get("applied")
                ]
                return {
                    "snapshot_fingerprint": snapshot_fp,
                    "phases_with_strategy": len(phase_fps),
                    "total_decision_count": sum(
                        m.get("decision_count", 0) for m in self._learning_phase_manifests
                    ),
                    "cross_phase_consistent": len(set(phase_fps)) <= 1 if phase_fps else True,
                    "phase_manifests": list(self._learning_phase_manifests),
                }

        return Stub()

    def test_freeze_resets_manifests(self):
        stub = self._make_pipeline_stub()
        stub.register_phase_learning_manifest({"phase": "observe", "applied": True})
        stub.freeze_learning_strategy_snapshot()
        self.assertEqual(stub._learning_phase_manifests, [])

    def test_freeze_captures_fingerprint(self):
        stub = self._make_pipeline_stub()
        snap = stub.freeze_learning_strategy_snapshot()
        self.assertIn("fingerprint", snap)
        self.assertEqual(stub.get_learning_strategy_snapshot()["fingerprint"], snap["fingerprint"])

    def test_register_and_summary(self):
        stub = self._make_pipeline_stub()
        stub.freeze_learning_strategy_snapshot()
        fp = stub.get_learning_strategy_snapshot()["fingerprint"]

        for phase in ("observe", "hypothesis", "experiment"):
            stub.register_phase_learning_manifest({
                "phase": phase,
                "applied": True,
                "strategy_fingerprint": fp,
                "decision_count": 2,
            })

        summary = stub.build_learning_application_summary()
        self.assertEqual(summary["phases_with_strategy"], 3)
        self.assertEqual(summary["total_decision_count"], 6)
        self.assertTrue(summary["cross_phase_consistent"])

    def test_cross_phase_inconsistent(self):
        stub = self._make_pipeline_stub()
        stub.freeze_learning_strategy_snapshot()

        stub.register_phase_learning_manifest({
            "phase": "observe",
            "applied": True,
            "strategy_fingerprint": "aaaa",
            "decision_count": 1,
        })
        stub.register_phase_learning_manifest({
            "phase": "analyze",
            "applied": True,
            "strategy_fingerprint": "bbbb",
            "decision_count": 1,
        })

        summary = stub.build_learning_application_summary()
        self.assertFalse(summary["cross_phase_consistent"])


class TestBenchmarkFeedbackContract(unittest.TestCase):
    """Phase I-3 — PolicyAdjuster.apply_benchmark_summary 与
    LearningLoopOrchestrator.consume_benchmark_summary 必须把命中率回灌至策略状态。"""

    def _make_summary(self) -> dict:
        return {
            "global_summary": {
                "average_quality_score": 0.72,
                "template_default_hit_rate": 0.4,
                "budget_proceed_hit_rate": 0.6,
                "layer_top_hit_rate": 0.3,
            },
            "learning_recommendations": {
                "thresholds": {
                    "template_default_hit_rate_target": 0.7,
                    "budget_proceed_hit_rate_target": 0.8,
                    "layer_top_hit_rate_target": 0.5,
                    "skip_rate_max": 0.3,
                    "decompose_rate_max": 0.3,
                },
                "phase_signals": {
                    "analyze": {
                        "below_targets": ["template_default_hit_rate", "budget_proceed_hit_rate"],
                    },
                },
                "template_preference_adjustments": {
                    "analytical": 0.15,
                    "evidential": 0.05,
                },
                "phase_threshold_adjustments": {
                    "analyze": {"context_budget_tighten": 0.2},
                },
            },
        }

    def test_policy_adjuster_apply_benchmark_summary(self):
        from src.learning.policy_adjuster import PolicyAdjuster

        adjuster = PolicyAdjuster()
        baseline_pref = adjuster.get_active_policy()["template_preferences"]["analytical"]
        baseline_versions = adjuster.version_count

        adjustment = adjuster.apply_benchmark_summary(self._make_summary())

        # 模板偏好被强化
        self.assertGreater(adjustment.template_preferences["analytical"], baseline_pref)
        # 阶段阈值被记录
        self.assertIn("analyze.context_budget_tighten", adjustment.phase_thresholds)
        # 至少触发一项 change，且来源标记为 benchmark
        self.assertGreater(len(adjustment.changes), 0)
        self.assertTrue(any(c.get("source") == "benchmark" for c in adjustment.changes))
        # 历史版本号 +1 且 trigger=benchmark
        self.assertEqual(adjuster.version_count, baseline_versions + 1)
        history = adjuster.get_policy_history(limit=1)
        self.assertEqual(history[-1]["trigger"], "benchmark")

    def test_orchestrator_consume_benchmark_summary(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        orchestrator = LearningLoopOrchestrator()
        result = orchestrator.consume_benchmark_summary(self._make_summary())

        self.assertTrue(result["applied"])
        self.assertIsNotNone(result["policy_adjustment"])
        self.assertIn("template_preferences", result["policy_adjustment"])
        self.assertIn("phase_thresholds", result["policy_adjustment"])
        # 与 policy_adjuster 持有同一份策略状态
        active = orchestrator.policy_adjuster.get_active_policy()
        self.assertEqual(
            active["template_preferences"],
            result["policy_adjustment"]["template_preferences"],
        )

    def test_orchestrator_handles_empty_summary(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        orchestrator = LearningLoopOrchestrator()
        result = orchestrator.consume_benchmark_summary({})
        self.assertFalse(result["applied"])
        self.assertIsNone(result["policy_adjustment"])


if __name__ == "__main__":
    unittest.main()
