# tests/unit/test_reflect_phase.py
"""
ReflectPhaseMixin 单元测试

覆盖：
  - 无 outcomes 时的回退反思
  - QualityAssessor 驱动的规则反思（强弱项分类）
  - LLM 增强反思（成功/失败/不可用）
  - 改进计划生成逻辑
  - 返回契约稳定性
"""

import json
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.quality.quality_assessor import QualityAssessor
from src.research.phases.reflect_phase import ReflectPhaseMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeCycle:
    """Minimal ResearchCycle stand-in."""
    outcomes: List[Dict[str, Any]] = field(default_factory=list)


class _FakePipeline:
    def __init__(self, *, llm_engine: Any = None, self_learning_engine: Any = None, previous_feedback: Any = None):
        self.quality_assessor = QualityAssessor()
        self.config: Dict[str, Any] = {}
        self._learning_phase_manifests: List[Dict[str, Any]] = []
        self._previous_feedback = dict(previous_feedback or {})
        if llm_engine is not None:
            self.config["llm_engine"] = llm_engine
        if self_learning_engine is not None:
            self.config["self_learning_engine"] = self_learning_engine

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._learning_phase_manifests.append(manifest)

    def get_learning_strategy_snapshot(self) -> Dict[str, Any]:
        return {}

    def build_learning_application_summary(self) -> Dict[str, Any]:
        return {"phase_manifests": list(self._learning_phase_manifests)}

    def get_previous_iteration_feedback(self) -> Dict[str, Any]:
        return dict(self._previous_feedback)


class _ReflectMixin(ReflectPhaseMixin):
    """Concrete class that satisfies the mixin's pipeline expectation."""

    def __init__(self, pipeline: _FakePipeline):
        self.pipeline = pipeline  # type: ignore[assignment]


def _full_outcome(phase: str = "observe") -> Dict[str, Any]:
    return {
        "phase": phase,
        "result": {
            "status": "completed",
            "phase": phase,
            "results": {"score": 0.9},
            "artifacts": ["paper.pdf"],
            "metadata": {"v": 1},
            "error": None,
        },
    }


def _weak_outcome(phase: str = "analyze") -> Dict[str, Any]:
    return {"phase": phase, "result": {"status": "pending"}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReflectPhaseContract(unittest.TestCase):
    """返回结构契约守护。"""

    def test_return_has_required_keys(self):
        mixin = _ReflectMixin(_FakePipeline())
        result = mixin.execute_reflect_phase(_FakeCycle(), {})
        for key in ("phase", "reflections", "improvement_plan", "metadata", "quality_assessment", "learning_feedback_library"):
            self.assertIn(key, result, f"missing key: {key}")
        self.assertEqual(result["phase"], "reflect")

    def test_metadata_has_required_fields(self):
        mixin = _ReflectMixin(_FakePipeline())
        result = mixin.execute_reflect_phase(_FakeCycle(), {})
        md = result["metadata"]
        for key in ("reflection_count", "plan_items", "cycle_quality_score", "llm_enhanced", "assessed_phases", "feedback_record_count"):
            self.assertIn(key, md, f"missing metadata key: {key}")

    def test_learning_feedback_library_contains_replay_payload(self):
        previous_feedback = {
            "status": "completed",
            "iteration_number": 4,
            "learning_summary": {"tuned_parameters": {"max_concurrent_tasks": 5}},
            "quality_assessment": {"overall_cycle_score": 0.88},
        }
        mixin = _ReflectMixin(_FakePipeline(previous_feedback=previous_feedback))
        result = mixin.execute_reflect_phase(_FakeCycle(outcomes=[_full_outcome()]), {})

        library = result["learning_feedback_library"]
        self.assertEqual(library["contract_version"], "research-feedback-library.v1")
        self.assertEqual(library["replay_feedback"]["iteration_number"], 4)
        self.assertGreaterEqual(library["summary"]["record_count"], 1)


class TestReflectNoOutcomes(unittest.TestCase):
    """cycle.outcomes 为空时仍能生成合理反思。"""

    def test_empty_outcomes_produce_fallback_reflection(self):
        mixin = _ReflectMixin(_FakePipeline())
        result = mixin.execute_reflect_phase(_FakeCycle(outcomes=[]), {})
        self.assertGreaterEqual(len(result["reflections"]), 1)
        self.assertEqual(result["metadata"]["assessed_phases"], 0)

    def test_cycle_without_outcomes_attr(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = MagicMock(spec=[])  # no 'outcomes' attribute
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertEqual(result["metadata"]["assessed_phases"], 0)


class TestReflectRuleBased(unittest.TestCase):
    """QualityAssessor 驱动的规则反思。"""

    def test_weak_outcome_generates_weakness_reflection(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_weak_outcome("analyze")])
        result = mixin.execute_reflect_phase(cycle, {})
        topics = [r["topic"] for r in result["reflections"]]
        self.assertTrue(any("质量不足" in t for t in topics))

    def test_strong_outcome_generates_strength_reflection(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome("observe")])
        result = mixin.execute_reflect_phase(cycle, {})
        topics = [r["topic"] for r in result["reflections"]]
        self.assertTrue(any("优秀" in t for t in topics))

    def test_quality_assessment_block_in_result(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome(), _weak_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        qa = result["quality_assessment"]
        self.assertIn("overall_cycle_score", qa)
        self.assertIn("weaknesses", qa)
        self.assertIn("strengths", qa)

    def test_all_reflections_have_source_field(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome(), _weak_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        for r in result["reflections"]:
            self.assertIn("source", r)


class TestReflectLLMEnhanced(unittest.TestCase):
    """LLM 增强反思路径。"""

    def test_llm_available_adds_llm_reflection(self):
        llm = MagicMock()
        llm.generate.return_value = json.dumps({
            "reflection": "需强化跨学科融合",
            "action": "引入药理学定量分析",
        })
        mixin = _ReflectMixin(_FakePipeline(llm_engine=llm))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertTrue(result["metadata"]["llm_enhanced"])
        llm_reflections = [r for r in result["reflections"] if r.get("source") == "llm"]
        self.assertEqual(len(llm_reflections), 1)
        self.assertIn("跨学科", llm_reflections[0]["reflection"])
        self.assertIsInstance(result["metadata"].get("small_model_plan"), dict)
        self.assertEqual(result["metadata"]["small_model_plan"]["phase"], "reflect")

    def test_llm_failure_falls_back_gracefully(self):
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("GPU OOM")
        mixin = _ReflectMixin(_FakePipeline(llm_engine=llm))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertFalse(result["metadata"]["llm_enhanced"])
        self.assertGreaterEqual(len(result["reflections"]), 1)

    def test_no_llm_produces_no_llm_reflection(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertFalse(result["metadata"]["llm_enhanced"])
        self.assertTrue(all(r.get("source") != "llm" for r in result["reflections"]))

    def test_llm_invalid_json_falls_back(self):
        llm = MagicMock()
        llm.generate.return_value = "这不是 JSON"
        mixin = _ReflectMixin(_FakePipeline(llm_engine=llm))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertFalse(result["metadata"]["llm_enhanced"])


class TestImprovementPlan(unittest.TestCase):
    """改进计划生成逻辑。"""

    def test_weak_outcome_triggers_improvement_items(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_weak_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertGreaterEqual(len(result["improvement_plan"]), 1)

    def test_strong_outcomes_get_maintenance_plan(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome(), _full_outcome("hypothesis")])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertGreaterEqual(len(result["improvement_plan"]), 1)

    def test_plan_items_are_strings(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_weak_outcome(), _full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        for item in result["improvement_plan"]:
            self.assertIsInstance(item, str)


# ---------------------------------------------------------------------------
# ReflectPhase → SelfLearningEngine 反馈集成
# ---------------------------------------------------------------------------


class TestReflectFeedsSelfLearning(unittest.TestCase):
    """ReflectPhase 将循环评估反馈给 SelfLearningEngine。"""

    def test_learning_engine_receives_cycle_assessment(self):
        mock_le = MagicMock()
        mock_le.learn_from_cycle_reflection.return_value = {
            "recorded_phases": ["observe"],
            "weak_phases": [],
            "improvement_priorities": [],
            "cycle_trend": "stable",
        }
        mixin = _ReflectMixin(_FakePipeline(self_learning_engine=mock_le))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        mock_le.learn_from_cycle_reflection.assert_called_once()
        self.assertIsNotNone(result["learning_summary"])
        self.assertTrue(result["metadata"]["learning_fed"])

    def test_no_learning_engine_produces_none_summary(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertIsNone(result["learning_summary"])
        self.assertFalse(result["metadata"]["learning_fed"])

    def test_learning_engine_failure_is_graceful(self):
        mock_le = MagicMock()
        mock_le.learn_from_cycle_reflection.side_effect = RuntimeError("boom")
        mixin = _ReflectMixin(_FakePipeline(self_learning_engine=mock_le))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertIsNone(result["learning_summary"])
        self.assertFalse(result["metadata"]["learning_fed"])

    def test_learning_engine_without_method_is_skipped(self):
        mock_le = MagicMock(spec=[])  # no learn_from_cycle_reflection
        mixin = _ReflectMixin(_FakePipeline(self_learning_engine=mock_le))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertIsNone(result["learning_summary"])


if __name__ == "__main__":
    unittest.main()
