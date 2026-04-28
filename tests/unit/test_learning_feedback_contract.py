"""learning_feedback_contract v2 回归（T2.2）。

覆盖：
1. CONTRACT_VERSION 已升级到 ``research-feedback-library.v2``，且保留 v1 常量供兼容引用。
2. ``build_learning_feedback_library`` 输出的 records 携带 ``prompt_version`` /
   ``schema_version`` / ``source_phase``，未传时退回 ``"unknown"``。
3. 显式传入 prompt_version + schema_version 时正确写入 record 与 metadata。
4. 旧记录（无 prompt_version 字段）经 ``normalize_learning_feedback_record``
   归一化后默认 ``"unknown"``，与 v1 行为兼容。
"""

from __future__ import annotations

import unittest

from src.research.learning_feedback_contract import (
    CONTRACT_VERSION,
    CONTRACT_VERSION_V1,
    LEGACY_PROMPT_VERSION_DEFAULT,
    build_learning_feedback_library,
    normalize_learning_feedback_record,
)


def _make_cycle_assessment() -> dict:
    return {
        "overall_cycle_score": 0.72,
        "phase_assessments": [
            {
                "phase": "observe",
                "score": {"overall_score": 0.85, "grade_level": "B"},
            },
            {
                "phase": "analyze",
                "score": {"overall_score": 0.40, "grade_level": "D"},
            },
        ],
        "weaknesses": [{"phase": "analyze", "issues": ["数据不足"]}],
        "strengths": [{"phase": "observe"}],
    }


class TestLearningFeedbackContractV2(unittest.TestCase):
    def test_contract_version_is_v2(self) -> None:
        self.assertEqual(CONTRACT_VERSION, "research-feedback-library.v2")
        self.assertEqual(CONTRACT_VERSION_V1, "research-feedback-library.v1")

    def test_default_prompt_version_is_unknown(self) -> None:
        library = build_learning_feedback_library(
            cycle_assessment=_make_cycle_assessment(),
            learning_summary={"recorded_phases": ["observe", "analyze"]},
        )
        self.assertEqual(library["contract_version"], CONTRACT_VERSION)
        for record in library["records"]:
            self.assertEqual(record["prompt_version"], LEGACY_PROMPT_VERSION_DEFAULT)
            self.assertEqual(record["schema_version"], LEGACY_PROMPT_VERSION_DEFAULT)
            self.assertEqual(
                record["metadata"]["contract_version"],
                CONTRACT_VERSION,
            )
            self.assertEqual(
                record["metadata"]["prompt_version"], LEGACY_PROMPT_VERSION_DEFAULT
            )

    def test_explicit_prompt_version_propagated(self) -> None:
        library = build_learning_feedback_library(
            cycle_assessment=_make_cycle_assessment(),
            prompt_version="hypothesis_engine.default_hypothesis@v2",
            schema_version="v2",
            source_phase="reflect",
        )
        for record in library["records"]:
            self.assertEqual(
                record["prompt_version"], "hypothesis_engine.default_hypothesis@v2"
            )
            self.assertEqual(record["schema_version"], "v2")
            self.assertEqual(record["source_phase"], "reflect")
            self.assertEqual(
                record["metadata"]["prompt_version"],
                "hypothesis_engine.default_hypothesis@v2",
            )
            self.assertEqual(record["metadata"]["schema_version"], "v2")

    def test_normalize_legacy_record_defaults_unknown(self) -> None:
        legacy = {
            "feedback_scope": "phase_assessment",
            "target_phase": "analyze",
            "feedback_status": "weakness",
            # 旧记录字面量不带 prompt_version / schema_version
        }
        normalized = normalize_learning_feedback_record(legacy)
        self.assertEqual(normalized["prompt_version"], "unknown")
        self.assertEqual(normalized["schema_version"], "unknown")
        # 其余字段仍正常归一化
        self.assertEqual(normalized["target_phase"], "analyze")
        self.assertEqual(normalized["feedback_status"], "weakness")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
