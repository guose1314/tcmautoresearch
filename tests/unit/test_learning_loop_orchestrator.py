"""Unit tests for LearningLoopOrchestrator."""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional


class _FakeLearningEngine:
    """Minimal stub for SelfLearningEngine."""

    def __init__(self, tuned: Optional[Dict[str, Any]] = None):
        self._tuned = tuned or {"quality_threshold": 0.74, "max_concurrent_tasks": 6}
        self._called = False

    def learn_from_cycle_reflection(self, assessment: Dict[str, Any]) -> Dict[str, Any]:
        self._called = True
        return {
            "extracted_patterns": [],
            "tuned_parameters": dict(self._tuned),
            "recorded_phases": ["observe"],
            "weak_phases": [],
            "improvement_priorities": [],
            "cycle_trend": "stable",
        }

    def get_learning_strategy(self) -> Dict[str, Any]:
        return {"tuned_parameters": dict(self._tuned)}

    def build_previous_iteration_feedback(self) -> Dict[str, Any]:
        return {
            "iteration_number": 1,
            "learning_summary": {"tuned_parameters": dict(self._tuned)},
        }


class _FakePipeline:
    """Minimal pipeline stub with learning-related methods."""

    def __init__(
        self,
        *,
        engine: Optional[_FakeLearningEngine] = None,
        learning_strategy: Optional[Dict[str, Any]] = None,
    ):
        self.config: Dict[str, Any] = {}
        if engine is not None:
            self.config["self_learning_engine"] = engine
        if learning_strategy is not None:
            self.config["learning_strategy"] = learning_strategy
        self._snapshot: Dict[str, Any] = {}
        self._manifests: list = []
        self._refreshed = False

    def freeze_learning_strategy_snapshot(self) -> Dict[str, Any]:
        from src.research.learning_strategy import build_strategy_snapshot

        self._snapshot = build_strategy_snapshot(None, self.config)
        return dict(self._snapshot)

    def get_learning_strategy_snapshot(self) -> Dict[str, Any]:
        return dict(self._snapshot)

    def get_learning_strategy(self) -> Dict[str, Any]:
        return dict(self.config.get("learning_strategy") or {})

    def get_previous_iteration_feedback(self) -> Dict[str, Any]:
        return dict(self.config.get("previous_iteration_feedback") or {})

    def refresh_learning_runtime_feedback(self) -> Dict[str, Any]:
        self._refreshed = True
        engine = self.config.get("self_learning_engine")
        if engine is not None and hasattr(engine, "get_learning_strategy"):
            strategy = engine.get_learning_strategy()
            if isinstance(strategy, dict):
                self.config["learning_strategy"] = dict(strategy)
        if engine is not None and hasattr(engine, "build_previous_iteration_feedback"):
            fb = engine.build_previous_iteration_feedback()
            if isinstance(fb, dict):
                self.config["previous_iteration_feedback"] = dict(fb)
        return dict(self.config.get("learning_strategy") or {})

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._manifests.append(manifest)

    def build_learning_application_summary(self) -> Dict[str, Any]:
        return {
            "snapshot_fingerprint": self._snapshot.get("fingerprint"),
            "phases_with_strategy": [],
            "phase_count": 0,
            "total_decision_count": 0,
            "cross_phase_consistent": True,
            "distinct_fingerprints": [],
            "phase_manifests": list(self._manifests),
        }


def _cycle_assessment() -> Dict[str, Any]:
    return {
        "phase_assessments": [
            {
                "phase": "observe",
                "score": {
                    "overall_score": 0.82,
                    "completeness": 0.8,
                    "consistency": 0.78,
                    "evidence_quality": 0.84,
                    "grade_level": "high",
                },
            }
        ],
        "weaknesses": [],
        "strengths": [{"phase": "observe", "score": 0.82, "grade": "high"}],
        "overall_cycle_score": 0.82,
    }


# ======================================================================
# Tests
# ======================================================================


class TestLearningLoopOrchestratorInit(unittest.TestCase):
    def test_import_and_instantiate(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        self.assertIsNotNone(llo)
        self.assertEqual(llo._phase_manifests, [])
        self.assertIsNone(llo._reflect_learning_result)


class TestPrepareCycle(unittest.TestCase):
    def test_prepare_cycle_without_engine(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        pipeline = _FakePipeline()
        result = llo.prepare_cycle(pipeline)
        self.assertIn("snapshot", result)
        self.assertIn("learning_strategy", result)
        self.assertIn("previous_iteration_feedback", result)
        self.assertIsInstance(result["snapshot"], dict)

    def test_prepare_cycle_with_engine(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        engine = _FakeLearningEngine()
        pipeline = _FakePipeline(engine=engine)
        pipeline.refresh_learning_runtime_feedback()

        llo = LearningLoopOrchestrator()
        result = llo.prepare_cycle(pipeline)

        self.assertIn("tuned_parameters", result["learning_strategy"])
        self.assertEqual(
            result["learning_strategy"]["tuned_parameters"]["quality_threshold"], 0.74
        )
        self.assertIn("fingerprint", result["snapshot"])


class TestInjectPhaseContext(unittest.TestCase):
    def test_inject_adds_strategy(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        ctx = {"question": "麻黄"}
        strategy = {"tuned_parameters": {"quality_threshold": 0.8}}
        result = LearningLoopOrchestrator.inject_phase_context(ctx, strategy, None)
        self.assertEqual(result["learning_strategy"]["tuned_parameters"]["quality_threshold"], 0.8)
        self.assertEqual(result["question"], "麻黄")

    def test_inject_does_not_overwrite_existing(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        existing = {"tuned_parameters": {"quality_threshold": 0.9}}
        ctx = {"learning_strategy": existing}
        strategy = {"tuned_parameters": {"quality_threshold": 0.5}}
        result = LearningLoopOrchestrator.inject_phase_context(ctx, strategy, None)
        self.assertEqual(
            result["learning_strategy"]["tuned_parameters"]["quality_threshold"], 0.9
        )


class TestRecordPhaseLearning(unittest.TestCase):
    def test_record_manifests(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        llo.record_phase_learning({"phase": "observe", "applied": True, "decision_count": 2})
        llo.record_phase_learning({"phase": "hypothesis", "applied": False, "decision_count": 0})
        self.assertEqual(len(llo._phase_manifests), 2)

    def test_record_ignores_non_dict(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        llo = LearningLoopOrchestrator()
        llo.record_phase_learning("not_a_dict")  # type: ignore[arg-type]
        self.assertEqual(len(llo._phase_manifests), 0)


class TestExecuteReflectLearning(unittest.TestCase):
    def test_feeds_engine_and_computes_diff(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        engine = _FakeLearningEngine()
        pipeline = _FakePipeline(engine=engine)
        pipeline.refresh_learning_runtime_feedback()

        llo = LearningLoopOrchestrator()
        llo.prepare_cycle(pipeline)
        result = llo.execute_reflect_learning(pipeline, _cycle_assessment())

        self.assertTrue(result["fed"])
        self.assertIsInstance(result["learning_summary"], dict)
        self.assertIn("tuned_parameters", result["learning_summary"])
        self.assertIn("strategy_diff", result)
        self.assertIsInstance(result["snapshot_before"], dict)
        self.assertIsInstance(result["snapshot_after"], dict)
        self.assertTrue(engine._called)

    def test_no_engine_returns_not_fed(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        pipeline = _FakePipeline()
        llo = LearningLoopOrchestrator()
        llo.prepare_cycle(pipeline)
        result = llo.execute_reflect_learning(pipeline, _cycle_assessment())

        self.assertFalse(result["fed"])
        self.assertIsNone(result["learning_summary"])


class TestBuildCycleSummary(unittest.TestCase):
    def test_summary_includes_reflect_learning(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        engine = _FakeLearningEngine()
        pipeline = _FakePipeline(engine=engine)
        pipeline.refresh_learning_runtime_feedback()

        llo = LearningLoopOrchestrator()
        llo.prepare_cycle(pipeline)
        llo.record_phase_learning({"phase": "observe", "applied": True, "decision_count": 2})
        llo.execute_reflect_learning(pipeline, _cycle_assessment())
        summary = llo.build_cycle_summary(pipeline)

        self.assertIn("reflect_learning", summary)
        self.assertTrue(summary["reflect_learning"]["fed"])

    def test_summary_without_reflect(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        pipeline = _FakePipeline()
        llo = LearningLoopOrchestrator()
        llo.prepare_cycle(pipeline)
        summary = llo.build_cycle_summary(pipeline)
        self.assertNotIn("reflect_learning", summary)


class TestPrepareNextCycleStrategy(unittest.TestCase):
    def test_prepare_next_cycle(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        engine = _FakeLearningEngine({"quality_threshold": 0.80, "max_concurrent_tasks": 8})
        pipeline = _FakePipeline(engine=engine)
        pipeline.refresh_learning_runtime_feedback()

        llo = LearningLoopOrchestrator()
        result = llo.prepare_next_cycle_strategy(pipeline)

        self.assertIn("learning_strategy", result)
        self.assertIn("previous_iteration_feedback", result)
        self.assertTrue(pipeline._refreshed)

    def test_prepare_next_cycle_no_engine(self):
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        pipeline = _FakePipeline()
        llo = LearningLoopOrchestrator()
        result = llo.prepare_next_cycle_strategy(pipeline)

        self.assertEqual(result["learning_strategy"], {})
        self.assertEqual(result["previous_iteration_feedback"], {})


class TestFullLifecycle(unittest.TestCase):
    def test_full_cycle(self):
        """Complete learning loop lifecycle: prepare → inject → record → reflect → summary → next."""
        from src.research.learning_loop_orchestrator import LearningLoopOrchestrator

        engine = _FakeLearningEngine({"quality_threshold": 0.74})
        pipeline = _FakePipeline(engine=engine)
        pipeline.refresh_learning_runtime_feedback()

        llo = LearningLoopOrchestrator()

        # ① prepare
        prep = llo.prepare_cycle(pipeline)
        self.assertIn("fingerprint", prep["snapshot"])

        # ② inject
        ctx = llo.inject_phase_context(
            {"question": "麻黄"},
            prep["learning_strategy"],
            prep["previous_iteration_feedback"],
        )
        self.assertIn("learning_strategy", ctx)

        # ③ record
        llo.record_phase_learning({"phase": "observe", "applied": True, "decision_count": 3})

        # ④ reflect
        reflect = llo.execute_reflect_learning(pipeline, _cycle_assessment())
        self.assertTrue(reflect["fed"])

        # ⑤ summary
        summary = llo.build_cycle_summary(pipeline)
        self.assertIn("reflect_learning", summary)

        # ⑥ next
        next_strategy = llo.prepare_next_cycle_strategy(pipeline)
        self.assertIn("learning_strategy", next_strategy)


if __name__ == "__main__":
    unittest.main()
