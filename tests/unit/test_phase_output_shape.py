"""F-3: Phase output 形状收口 — 公约键一致性测试。"""

from __future__ import annotations

import unittest

from src.research.phase_result import (
    PHASE_RESULT_COMMON_METADATA_KEYS,
    PHASE_RESULT_COMMON_RESULT_KEYS,
    build_phase_result,
)

_ALL_PHASES = ("observe", "hypothesis", "experiment_execution", "analyze", "reflect", "publish", "synthesize")


class TestCommonKeysConstants(unittest.TestCase):
    """公约键常量可导入且非空。"""

    def test_common_result_keys_nonempty(self):
        self.assertGreater(len(PHASE_RESULT_COMMON_RESULT_KEYS), 0)

    def test_common_metadata_keys_nonempty(self):
        self.assertGreater(len(PHASE_RESULT_COMMON_METADATA_KEYS), 0)

    def test_evidence_protocol_in_result_keys(self):
        self.assertIn("evidence_protocol", PHASE_RESULT_COMMON_RESULT_KEYS)

    def test_summary_in_result_keys(self):
        self.assertIn("summary", PHASE_RESULT_COMMON_RESULT_KEYS)

    def test_learning_in_metadata_keys(self):
        self.assertIn("learning", PHASE_RESULT_COMMON_METADATA_KEYS)

    def test_contract_version_in_metadata_keys(self):
        self.assertIn("contract_version", PHASE_RESULT_COMMON_METADATA_KEYS)


class TestBuildPhaseResultInjectsCommonKeys(unittest.TestCase):
    """build_phase_result 自动注入公约键（缺省为 None）。"""

    def test_results_contain_common_keys_for_all_phases(self):
        for phase in _ALL_PHASES:
            with self.subTest(phase=phase):
                payload = build_phase_result(phase)
                results = payload["results"]
                for key in PHASE_RESULT_COMMON_RESULT_KEYS:
                    self.assertIn(key, results, f"{phase} results 缺少公约键: {key}")

    def test_metadata_contain_common_keys_for_all_phases(self):
        for phase in _ALL_PHASES:
            with self.subTest(phase=phase):
                payload = build_phase_result(phase)
                metadata = payload["metadata"]
                for key in PHASE_RESULT_COMMON_METADATA_KEYS:
                    self.assertIn(key, metadata, f"{phase} metadata 缺少公约键: {key}")

    def test_explicit_values_not_overwritten(self):
        payload = build_phase_result(
            "observe",
            results={"evidence_protocol": {"test": True}, "summary": "ok"},
            metadata={"learning": {"applied": True}},
        )
        self.assertEqual(payload["results"]["evidence_protocol"], {"test": True})
        self.assertEqual(payload["results"]["summary"], "ok")
        self.assertEqual(payload["metadata"]["learning"], {"applied": True})

    def test_default_common_value_is_none(self):
        payload = build_phase_result("observe")
        self.assertIsNone(payload["results"]["evidence_protocol"])
        self.assertIsNone(payload["results"]["summary"])
        self.assertIsNone(payload["metadata"]["learning"])


class TestExperimentExecutionBoundary(unittest.TestCase):
    """experiment_execution results 包含 execution_boundary 子对象。"""

    def test_build_with_boundary(self):
        boundary = {
            "execution_records": [{"id": 1}],
            "analysis_records": [{"id": 1}],
            "execution_relationships": [],
            "analysis_relationships": [],
            "sampling_events": [],
            "output_files": {},
            "execution_status": "completed",
            "real_world_validation_status": "pending",
        }
        payload = build_phase_result(
            "experiment_execution",
            results={
                "protocol_design": {},
                "execution_boundary": boundary,
            },
            extra_fields=boundary,
        )
        self.assertIn("execution_boundary", payload["results"])
        # 兼容旧键仍可从顶层获取
        self.assertIn("execution_records", payload)


class TestReflectExtraFieldsExtended(unittest.TestCase):
    """reflect extra_fields 包含 strategy_diff 等扩展键。"""

    def test_source_code_has_strategy_diff(self):
        import re
        from pathlib import Path
        source = (Path(__file__).resolve().parents[2] / "src" / "research" / "phases" / "reflect_phase.py").read_text(encoding="utf-8")
        extra_block = re.search(r"extra_fields=\{([^}]+)\}", source, re.DOTALL)
        self.assertIsNotNone(extra_block)
        block_text = extra_block.group(1)
        self.assertIn("strategy_diff", block_text)
        self.assertIn("learning_application_summary", block_text)


if __name__ == "__main__":
    unittest.main()
