# tests/unit/test_analyze_phase.py
"""AnalyzePhaseMixin 单元测试

覆盖：
  - 正常路径：有记录 / 有推理引擎 / 有 chi-square 结果
  - 降级路径：ReasoningEngine 不可用或失败时回退
  - 空输入边界：无记录、无关系、无 Hypothesis 回退
  - GRADE 证据分级正常 + 失败回退
  - Hypothesis 阶段合成记录与关系
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.research.phase_result import get_phase_deprecated_fallbacks, get_phase_value
from src.research.phases.analyze_phase import AnalyzePhaseMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EXPERIMENT_EXECUTION = "experiment_execution"
    ANALYZE = "analyze"
    PUBLISH = "publish"
    REFLECT = "reflect"


@dataclass
class _FakeCycle:
    """Minimal ResearchCycle stand-in."""
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)


class _FakePipeline:
    """Minimal pipeline providing the fields AnalyzePhaseMixin expects."""

    ResearchPhase = _Phase

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.analysis_port = MagicMock()
        # Default: reasoning engine creation fails → graceful fallback
        self.analysis_port.create_reasoning_engine.side_effect = RuntimeError("no engine")


class _AnalyzeMixin(AnalyzePhaseMixin):
    """Concrete class wrapping the mixin."""

    _RELATION_SOURCE_PRIORITY = {
        "observe_reasoning_engine": 3,
        "observe_semantic_graph": 2,
        "pipeline_hypothesis_context": 1,
    }

    def __init__(self, pipeline: _FakePipeline):
        self.pipeline = pipeline  # type: ignore[assignment]


def _sample_records() -> List[Dict[str, Any]]:
    return [
        {"formula": "麻黄汤", "syndrome": "风寒", "herbs": ["麻黄", "桂枝", "杏仁", "甘草"]},
        {"formula": "桂枝汤", "syndrome": "风寒", "herbs": ["桂枝", "芍药", "甘草", "生姜", "大枣"]},
        {"formula": "小柴胡汤", "syndrome": "少阳", "herbs": ["柴胡", "黄芩", "半夏", "甘草"]},
    ]


def _sample_relationships() -> List[Dict[str, Any]]:
    return [
        {"source": "麻黄", "source_type": "herb", "target": "风寒", "target_type": "syndrome", "type": "治疗"},
        {"source": "桂枝", "source_type": "herb", "target": "风寒", "target_type": "syndrome", "type": "治疗"},
    ]


# ---------------------------------------------------------------------------
# 1) 返回契约
# ---------------------------------------------------------------------------


class TestAnalyzePhaseContract(unittest.TestCase):
    """返回结构契约守护。"""

    def test_return_has_required_keys(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        for key in ("phase", "results", "metadata"):
            self.assertIn(key, result, f"missing key: {key}")
        self.assertEqual(result["phase"], "analyze")

    def test_metadata_has_required_fields(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        md = result["metadata"]
        for key in ("analysis_type", "significance_level", "record_count", "reasoning_engine_used"):
            self.assertIn(key, md, f"missing metadata key: {key}")

    def test_results_include_reasoning_results_and_data_mining(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        self.assertIn("reasoning_results", result["results"])
        self.assertIn("data_mining_result", result["results"])
        self.assertNotIn("reasoning_results", result)
        self.assertNotIn("data_mining_result", result)

    def test_reasoning_results_read_from_standard_results_without_fallback(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        self.assertEqual(get_phase_value(result, "reasoning_results", {}), result["results"]["reasoning_results"])
        self.assertEqual(get_phase_deprecated_fallbacks(result), [])


# ---------------------------------------------------------------------------
# 2) 正常路径：有记录时产出统计分析
# ---------------------------------------------------------------------------


class TestAnalyzeWithRecords(unittest.TestCase):

    def test_records_produce_data_mining_output(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        dm = result["results"]["data_mining_result"]
        self.assertEqual(dm["record_count"], 3)
        self.assertGreater(dm["item_count"], 0)
        self.assertIn("frequency_chi_square", dm)
        self.assertIn("association_rules", dm)

    def test_statistical_analysis_present_in_results(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        sa = result["results"].get("statistical_analysis", {})
        self.assertIn("statistical_significance", sa)
        self.assertIn("confidence_level", sa)
        self.assertIn("limitations", sa)
        for legacy_key in (
            "statistical_significance",
            "confidence_level",
            "effect_size",
            "p_value",
            "interpretation",
            "limitations",
            "primary_association",
        ):
            self.assertNotIn(legacy_key, result["results"])

    def test_record_count_in_metadata(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        self.assertEqual(result["metadata"]["record_count"], 3)

    def test_document_record_prefers_middle_for_fire_hemp(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        document = {
            "title": "麻子仁丸证治片段",
            "semantic_relationships": [
                {
                    "source": "麻子仁丸",
                    "source_type": "formula",
                    "target": "火麻仁",
                    "target_type": "herb",
                },
                {
                    "source": "火麻仁",
                    "source_type": "herb",
                    "target": "伤寒",
                    "target_type": "syndrome",
                },
                {
                    "source": "火麻仁",
                    "source_type": "herb",
                    "target": "中风",
                    "target_type": "syndrome",
                },
            ],
        }

        record = mixin._build_analyze_record_from_document(document, 0)

        self.assertEqual(record["formula"], "麻子仁丸")
        self.assertEqual(record["syndrome"], "中风")
        self.assertIn("火麻仁", record["herbs"])

    def test_primary_statistical_finding_skips_zero_support_candidates(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        records = [
            {"formula": "方1", "syndrome": "中风", "herbs": ["火麻仁", "桃仁"]},
            {"formula": "方2", "syndrome": "中风", "herbs": ["火麻仁"]},
            {"formula": "方3", "syndrome": "伤寒", "herbs": ["桂枝"]},
            {"formula": "方4", "syndrome": "伤寒", "herbs": ["麻黄"]},
        ]
        chi_square_items = [
            {"herb": "桃仁", "syndrome": "伤寒", "chi2": 999.0},
            {"herb": "火麻仁", "syndrome": "中风", "chi2": 1.0},
        ]

        finding = mixin._select_primary_statistical_finding(records, chi_square_items)

        self.assertEqual(finding["herb"], "火麻仁")
        self.assertEqual(finding["syndrome"], "中风")
        self.assertEqual(finding["contingency_table"]["a"], 2)
        self.assertGreater(finding["chi2"], 0.0)


# ---------------------------------------------------------------------------
# 3) 降级路径：ReasoningEngine 不可用
# ---------------------------------------------------------------------------


class TestAnalyzeReasoningDegradation(unittest.TestCase):

    def test_reasoning_engine_unavailable_returns_empty(self):
        """analysis_port.create_reasoning_engine 抛异常时 reasoning_results 为空。"""
        pipeline = _FakePipeline()
        pipeline.analysis_port.create_reasoning_engine.side_effect = RuntimeError("boom")
        mixin = _AnalyzeMixin(pipeline)
        result = mixin.execute_analyze_phase(
            _FakeCycle(),
            {"analysis_records": _sample_records(), "relationships": _sample_relationships()},
        )
        self.assertEqual(result["results"]["reasoning_results"], {})
        self.assertFalse(result["metadata"]["reasoning_engine_used"])

    def test_reasoning_engine_init_fails_gracefully(self):
        """ReasoningEngine.initialize() 返回 False 时跳过推理。"""
        pipeline = _FakePipeline()
        mock_engine = MagicMock()
        mock_engine.initialize.return_value = False
        pipeline.analysis_port.create_reasoning_engine.side_effect = None
        pipeline.analysis_port.create_reasoning_engine.return_value = mock_engine
        mixin = _AnalyzeMixin(pipeline)
        result = mixin.execute_analyze_phase(
            _FakeCycle(),
            {"analysis_records": _sample_records(), "relationships": _sample_relationships()},
        )
        self.assertEqual(result["results"]["reasoning_results"], {})

    def test_reasoning_engine_execute_raises(self):
        """ReasoningEngine.execute() 抛异常时降级。"""
        pipeline = _FakePipeline()
        mock_engine = MagicMock()
        mock_engine.initialize.return_value = True
        mock_engine.execute.side_effect = RuntimeError("execute boom")
        pipeline.analysis_port.create_reasoning_engine.side_effect = None
        pipeline.analysis_port.create_reasoning_engine.return_value = mock_engine
        mixin = _AnalyzeMixin(pipeline)
        result = mixin.execute_analyze_phase(
            _FakeCycle(),
            {"analysis_records": _sample_records(), "relationships": _sample_relationships()},
        )
        self.assertEqual(result["results"]["reasoning_results"], {})
        mock_engine.cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# 4) 空输入边界
# ---------------------------------------------------------------------------


class TestAnalyzeEmptyInput(unittest.TestCase):

    def test_empty_records_empty_context(self):
        """完全空的 context 不崩溃。"""
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {})
        self.assertEqual(result["phase"], "analyze")
        self.assertEqual(result["metadata"]["record_count"], 0)
        self.assertEqual(result["results"]["data_mining_result"]["record_count"], 0)

    def test_none_context(self):
        """context=None 时不崩溃（内部自动 fallback）。"""
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), None)
        self.assertEqual(result["phase"], "analyze")

    def test_no_statistical_finding_with_empty_records(self):
        """无记录时 statistical_significance=False。"""
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {})
        sa = result["results"]["statistical_analysis"]
        self.assertFalse(sa["statistical_significance"])
        self.assertEqual(sa["primary_association"], {})


# ---------------------------------------------------------------------------
# 5) GRADE 证据分级
# ---------------------------------------------------------------------------


class TestAnalyzeEvidenceGrade(unittest.TestCase):

    def test_evidence_grade_not_generated_without_literature(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(_FakeCycle(), {"analysis_records": _sample_records()})
        self.assertFalse(result["metadata"]["evidence_grade_generated"])

    def test_evidence_grade_error_recorded_in_metadata(self):
        """_grade_analyze_evidence 异常时 metadata 记录错误信息。"""
        pipeline = _FakePipeline()
        mixin = _AnalyzeMixin(pipeline)
        ctx = {
            "analysis_records": _sample_records(),
            "literature_records": [{"title": "test paper"}],
        }
        # _create_evidence_grader 会因 EvidenceGrader is None 而抛异常
        result = mixin.execute_analyze_phase(_FakeCycle(), ctx)
        # 要么 generated=False 要么有 error
        if not result["metadata"]["evidence_grade_generated"]:
            # 可接受: 没有 literature_records 匹配或 grader 失败
            self.assertIn("evidence_grade_error", result["metadata"])


# ---------------------------------------------------------------------------
# 6) Hypothesis 合成回退
# ---------------------------------------------------------------------------


class TestAnalyzeHypothesisFallback(unittest.TestCase):

    def test_fallback_synthesizes_records_from_hypotheses(self):
        """无直接记录但有 Hypothesis 阶段时合成分析记录。"""
        cycle = _FakeCycle(phase_executions={
            _Phase.OBSERVE: {"result": {}},
            _Phase.HYPOTHESIS: {"result": {
                "hypotheses": [
                    {"title": "麻黄解表", "source_entities": ["麻黄", "桂枝"], "source_gap_type": "风寒"},
                ],
            }},
        })
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(cycle, {})
        self.assertGreater(result["metadata"]["record_count"], 0)

    def test_no_hypothesis_no_records(self):
        """无 Hypothesis 且无记录时 record_count=0。"""
        cycle = _FakeCycle(phase_executions={_Phase.OBSERVE: {"result": {}}})
        mixin = _AnalyzeMixin(_FakePipeline())
        result = mixin.execute_analyze_phase(cycle, {})
        self.assertEqual(result["metadata"]["record_count"], 0)


class TestAnalyzeLearningStrategy(unittest.TestCase):

    def test_learning_strategy_adjusts_significance_and_sample_threshold(self):
        mixin = _AnalyzeMixin(_FakePipeline())
        records = _sample_records() + [
            {"formula": "四逆汤", "syndrome": "少阴", "herbs": ["附子", "干姜", "甘草"]},
        ]

        result = mixin.execute_analyze_phase(
            _FakeCycle(),
            {
                "analysis_records": records,
                "learning_strategy": {"tuned_parameters": {"quality_threshold": 0.9}},
            },
        )

        self.assertEqual(result["metadata"]["significance_level"], 0.03)
        self.assertEqual(result["metadata"]["minimum_sample_size"], 6)
        self.assertTrue(
            any(
                "建议至少 6" in limitation
                for limitation in result["results"]["statistical_analysis"]["limitations"]
            )
        )

    def test_learning_strategy_filters_low_confidence_reasoning_inputs(self):
        pipeline = _FakePipeline()
        pipeline.analysis_port.create_reasoning_engine.side_effect = None
        pipeline.analysis_port.create_reasoning_engine.return_value = MagicMock()
        mixin = _AnalyzeMixin(pipeline)

        result = mixin.execute_analyze_phase(
            _FakeCycle(),
            {
                "analysis_records": _sample_records(),
                "relationships": [
                    {
                        "source": "麻黄",
                        "source_type": "herb",
                        "target": "风寒",
                        "target_type": "syndrome",
                        "type": "治疗",
                        "metadata": {"confidence": 0.6},
                    }
                ],
                "learning_strategy": {"tuned_parameters": {"confidence_threshold": 0.8}},
            },
        )

        self.assertEqual(result["results"]["reasoning_results"], {})
        pipeline.analysis_port.create_reasoning_engine.assert_not_called()

    def test_learning_strategy_can_disable_evidence_grading(self):
        mixin = _AnalyzeMixin(_FakePipeline())

        result = mixin.execute_analyze_phase(
            _FakeCycle(),
            {
                "analysis_records": _sample_records(),
                "literature_records": [{"title": "test paper"}],
                "learning_strategy": {"analyze_grade_evidence": False},
            },
        )

        self.assertFalse(result["metadata"]["evidence_grade_generated"])
        self.assertNotIn("evidence_grade_error", result["metadata"])


if __name__ == "__main__":
    unittest.main()
