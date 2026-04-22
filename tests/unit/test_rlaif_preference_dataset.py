"""Phase M-3: RLAIF-lite 偏好数据集测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.research.rlaif import (
    RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION,
    LoRADatasetSpec,
    PreferenceDataset,
    PreferencePair,
    build_dataset_from_fallback_records,
    build_preference_pair,
    export_dataset_to_jsonl,
)


class TestPreferenceDataset(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual(
            RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION, "rlaif-preference-dataset-v1"
        )

    def test_build_pair_basic(self):
        pair = build_preference_pair(
            prompt="p", chosen="A", rejected="B", score_chosen=0.9, score_rejected=0.5
        )
        self.assertEqual(pair.score_delta, 0.4)

    def test_build_pair_empty_prompt(self):
        with self.assertRaises(ValueError):
            build_preference_pair(prompt="", chosen="A", rejected="B", score_chosen=1, score_rejected=0)

    def test_build_pair_same_text(self):
        with self.assertRaises(ValueError):
            build_preference_pair(prompt="p", chosen="A", rejected="A", score_chosen=1, score_rejected=0)

    def test_build_pair_invalid_score_order(self):
        with self.assertRaises(ValueError):
            build_preference_pair(prompt="p", chosen="A", rejected="B", score_chosen=0.1, score_rejected=0.5)

    def test_pair_to_dict(self):
        pair = PreferencePair("p", "A", "B", 0.9, 0.5)
        d = pair.to_dict()
        self.assertEqual(d["score_delta"], 0.4)
        self.assertEqual(d["chosen"], "A")

    def test_lora_spec_to_dict(self):
        spec = LoRADatasetSpec(name="qwen-tcm-v1", base_model="qwen1.5-7b", pair_count=10)
        d = spec.to_dict()
        self.assertEqual(d["base_model"], "qwen1.5-7b")
        self.assertEqual(d["pair_count"], 10)

    def test_dataset_len(self):
        ds = PreferenceDataset(pairs=[PreferencePair("p", "A", "B", 1, 0)])
        self.assertEqual(len(ds), 1)

    def test_build_from_fallback_records(self):
        records = [
            {
                "prompt": "题目1",
                "baseline_output": "答案A",
                "optimized_output": "答案B",
                "baseline_score": 0.4,
                "optimized_score": 0.8,
                "acceptance": True,
                "action": "self_refine",
            },
            {
                "prompt": "题目2",
                "baseline_output": "X",
                "optimized_output": "Y",
                "baseline_score": 0.7,
                "optimized_score": 0.3,
            },
        ]
        ds = build_dataset_from_fallback_records(records)
        self.assertEqual(len(ds), 2)
        # 第一条 optimized 胜出
        self.assertEqual(ds.pairs[0].chosen, "答案B")
        # 第二条 baseline 胜出（分数更高）
        self.assertEqual(ds.pairs[1].chosen, "X")

    def test_build_from_records_filters_min_delta(self):
        records = [
            {"prompt": "p", "baseline_output": "A", "optimized_output": "B",
             "baseline_score": 0.5, "optimized_score": 0.55},
        ]
        ds = build_dataset_from_fallback_records(records, min_score_delta=0.1)
        self.assertEqual(len(ds), 0)

    def test_build_from_records_skips_invalid(self):
        records = [
            {"prompt": "", "baseline_output": "A", "optimized_output": "B",
             "baseline_score": 0.5, "optimized_score": 0.9},
            {"prompt": "p", "baseline_output": "A", "optimized_output": "A",
             "baseline_score": 0.5, "optimized_score": 0.9},
            {"prompt": "p", "baseline_output": "A", "optimized_output": "B",
             "baseline_score": "bad", "optimized_score": 0.9},
        ]
        ds = build_dataset_from_fallback_records(records)
        self.assertEqual(len(ds), 0)

    def test_build_from_records_extract_text_from_dict_output(self):
        records = [
            {
                "prompt": "p",
                "baseline_output": {"text": "A"},
                "optimized_output": {"text": "B"},
                "baseline_score": 0.4,
                "optimized_score": 0.9,
            }
        ]
        ds = build_dataset_from_fallback_records(records)
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds.pairs[0].chosen, "B")

    def test_build_from_records_with_spec_updates_pair_count(self):
        records = [
            {"prompt": "p", "baseline_output": "A", "optimized_output": "B",
             "baseline_score": 0.4, "optimized_score": 0.9},
        ]
        spec = LoRADatasetSpec(name="qwen-tcm", base_model="qwen1.5-7b", pair_count=0)
        ds = build_dataset_from_fallback_records(records, spec=spec)
        self.assertIsNotNone(ds.spec)
        self.assertEqual(ds.spec.pair_count, 1)

    def test_export_jsonl_roundtrip(self):
        pair = PreferencePair("p", "A", "B", 0.9, 0.4, metadata={"k": "v"})
        ds = PreferenceDataset(pairs=[pair])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sub" / "out.jsonl"
            written = export_dataset_to_jsonl(ds, target)
            self.assertTrue(written.exists())
            lines = written.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["chosen"], "A")
            self.assertEqual(row["metadata"], {"k": "v"})

    def test_dataset_to_dict(self):
        spec = LoRADatasetSpec(name="x", base_model="y", pair_count=1)
        ds = PreferenceDataset(pairs=[PreferencePair("p", "A", "B", 1, 0)], spec=spec)
        d = ds.to_dict()
        self.assertEqual(d["pair_count"], 1)
        self.assertIsNotNone(d["spec"])


if __name__ == "__main__":
    unittest.main()
