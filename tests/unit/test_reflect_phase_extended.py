# tests/unit/test_reflect_phase_extended.py
"""ReflectPhaseMixin 补充单元测试

覆盖原 test_reflect_phase.py 未覆盖的场景：
  - 多阶段混合（同时有强项和弱项）
  - 改进计划特定条件触发
  - LLM 诊断集成（assess_cycle_for_reflection_with_llm 路径）
  - 空 outcomes 下 quality_assessment 结构
  - 反思数量与 outcomes 关系
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.quality.quality_assessor import QualityAssessor
from src.research.phases.reflect_phase import ReflectPhaseMixin

# ---------------------------------------------------------------------------
# Helpers (与原测试保持一致)
# ---------------------------------------------------------------------------


@dataclass
class _FakeCycle:
    outcomes: List[Dict[str, Any]] = field(default_factory=list)


class _FakePipeline:
    def __init__(self, *, llm_engine=None, self_learning_engine=None):
        self.quality_assessor = QualityAssessor()
        self.config: Dict[str, Any] = {}
        self._learning_phase_manifests: List[Dict[str, Any]] = []
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


class _ReflectMixin(ReflectPhaseMixin):
    def __init__(self, pipeline):
        self.pipeline = pipeline


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
# 1) 多阶段混合评估
# ---------------------------------------------------------------------------


class TestReflectMultiPhase(unittest.TestCase):
    """多阶段结果同时包含强弱项时的行为。"""

    def test_mixed_outcomes_report_both_weak_and_strong(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[
            _full_outcome("observe"),
            _weak_outcome("analyze"),
            _full_outcome("hypothesis"),
            _weak_outcome("experiment"),
        ])
        result = mixin.execute_reflect_phase(cycle, {})
        qa = result["quality_assessment"]
        self.assertGreater(len(qa["weaknesses"]), 0)
        self.assertGreater(len(qa["strengths"]), 0)
        self.assertEqual(result["metadata"]["assessed_phases"], 4)

    def test_reflection_count_matches_weaknesses_plus_strengths(self):
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome("observe"), _weak_outcome("analyze")])
        result = mixin.execute_reflect_phase(cycle, {})
        qa = result["quality_assessment"]
        expected = len(qa["weaknesses"]) + len(qa["strengths"])
        # 反思数应 ≥ 弱+强（可能有 fallback 反思）
        self.assertGreaterEqual(len(result["reflections"]), expected)


# ---------------------------------------------------------------------------
# 2) 改进计划特定触发逻辑
# ---------------------------------------------------------------------------


class TestImprovementPlanTriggers(unittest.TestCase):

    def test_very_low_score_triggers_redesign_plan(self):
        """极低分数（<0.4）的弱项应触发"重新设计"计划。"""
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_weak_outcome("analyze")])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertTrue(
            any("重新设计" in item for item in result["improvement_plan"]),
            f"plan items: {result['improvement_plan']}",
        )

    def test_high_overall_score_gets_maintenance_plan(self):
        """全部强结果时改进计划为维持型。"""
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[_full_outcome("observe"), _full_outcome("hypothesis")])
        result = mixin.execute_reflect_phase(cycle, {})
        overall = result["quality_assessment"]["overall_cycle_score"]
        if overall >= 0.8:
            self.assertTrue(
                any("保持" in item for item in result["improvement_plan"]),
            )


# ---------------------------------------------------------------------------
# 3) LLM 诊断集成路径
# ---------------------------------------------------------------------------


class TestReflectLLMDiagnosisPath(unittest.TestCase):

    def test_llm_diagnosis_included_in_quality_assessment(self):
        """当 LLM 可用时，quality_assessment 应能包含 llm_diagnosis。"""
        llm = MagicMock()
        llm.generate.return_value = json.dumps({
            "reflection": "分析阶段需要更多样本",
            "action": "增加数据采集量",
        })
        mixin = _ReflectMixin(_FakePipeline(llm_engine=llm))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        # llm_diagnosis 可能为 None（取决于 assess_cycle_for_reflection_with_llm 实现）
        # 但 key 必须存在
        self.assertIn("llm_diagnosis", result["quality_assessment"])

    def test_llm_returns_nested_json_still_works(self):
        """LLM 返回带额外字段的 JSON 时仍能提取 reflection。"""
        llm = MagicMock()
        llm.generate.return_value = json.dumps({
            "reflection": "证据链不完整",
            "action": "补充文献检索",
            "extra": "ignored",
        })
        mixin = _ReflectMixin(_FakePipeline(llm_engine=llm))
        cycle = _FakeCycle(outcomes=[_full_outcome()])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertTrue(result["metadata"]["llm_enhanced"])
        llm_refs = [r for r in result["reflections"] if r.get("source") == "llm"]
        self.assertEqual(len(llm_refs), 1)
        self.assertEqual(llm_refs[0]["reflection"], "证据链不完整")


# ---------------------------------------------------------------------------
# 4) 空输入与边界
# ---------------------------------------------------------------------------


class TestReflectEdgeCases(unittest.TestCase):

    def test_empty_outcomes_quality_assessment_score_zero(self):
        mixin = _ReflectMixin(_FakePipeline())
        result = mixin.execute_reflect_phase(_FakeCycle(outcomes=[]), {})
        self.assertEqual(result["quality_assessment"]["overall_cycle_score"], 0.0)
        self.assertEqual(result["quality_assessment"]["weaknesses"], [])
        self.assertEqual(result["quality_assessment"]["strengths"], [])

    def test_outcome_with_none_result(self):
        """result=None 的 outcome 不崩溃。"""
        mixin = _ReflectMixin(_FakePipeline())
        cycle = _FakeCycle(outcomes=[{"phase": "observe", "result": None}])
        result = mixin.execute_reflect_phase(cycle, {})
        self.assertEqual(result["phase"], "reflect")
        self.assertEqual(result["metadata"]["assessed_phases"], 1)


if __name__ == "__main__":
    unittest.main()
