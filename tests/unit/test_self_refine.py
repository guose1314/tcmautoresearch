"""J-4 测试: src.research.self_refine 自修订原语 + 默认 scorer/refiner。"""

from __future__ import annotations

import unittest

from src.research.self_refine import (
    DEFAULT_MAX_ROUNDS,
    SELF_REFINE_CONTRACT_VERSION,
    SelfRefineResult,
    SelfRefineRound,
    build_self_refine_metadata,
    default_structural_refiner,
    default_text_quality_scorer,
    run_self_refine,
)


class DefaultScorerTests(unittest.TestCase):
    def test_empty_text_yields_zero(self) -> None:
        self.assertEqual(default_text_quality_scorer(""), 0.0)
        self.assertEqual(default_text_quality_scorer("   "), 0.0)

    def test_score_in_unit_range(self) -> None:
        score = default_text_quality_scorer("张某某湿病案。证据：舌苔白腻。结论：宜温化。")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_long_structured_text_scores_higher_than_short(self) -> None:
        short = "湿病。"
        long = (
            "本研究围绕湿病证候展开。证据来自多部医经，结论指向温化方剂。"
            "理由在于病机为湿阻中焦，治法以芳香化湿为主，方义与三仁汤接近。"
            "依据《温病条辨》出处，对照各家学说，证候演变明确。"
        )
        self.assertGreater(
            default_text_quality_scorer(long),
            default_text_quality_scorer(short),
        )


class DefaultRefinerTests(unittest.TestCase):
    def test_appends_evidence_block_when_missing(self) -> None:
        out = default_structural_refiner("湿病初论。", 0.1, 0)
        self.assertIn("【证据补充】", out)

    def test_idempotent_when_text_already_complete(self) -> None:
        rich = "证据齐备。结论清晰。理由充分。"
        out = default_structural_refiner(rich, 0.95, 0)
        self.assertIn("【自修订】", out)
        # 已有结构关键词的不该再追加补充段
        self.assertNotIn("【证据补充】", out)
        self.assertNotIn("【结论收束】", out)


class RunSelfRefineTests(unittest.TestCase):
    def test_empty_input_with_zero_rounds_yields_zero_score(self) -> None:
        # 空输入 + 0 轮：不调用 refiner，分数恒为 0
        result = run_self_refine("", max_rounds=0)
        self.assertEqual(result.initial_score, 0.0)
        self.assertEqual(result.final_score, 0.0)
        self.assertEqual(result.quality_delta, 0.0)
        self.assertTrue(result.accepted)
        self.assertEqual(result.final_text, "")

    def test_default_pipeline_improves_short_text(self) -> None:
        result = run_self_refine("湿病初论。")
        self.assertGreaterEqual(result.final_score, result.initial_score)
        self.assertGreaterEqual(result.quality_delta, 0.0)
        self.assertTrue(result.accepted)
        self.assertGreaterEqual(len(result.rounds), 1)
        self.assertIsInstance(result.rounds[0], SelfRefineRound)

    def test_max_rounds_zero_yields_no_extra_rounds(self) -> None:
        result = run_self_refine("湿病案", max_rounds=0)
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.final_score, result.initial_score)

    def test_custom_scorer_and_refiner_invoked(self) -> None:
        calls = {"score": 0, "refine": 0}

        def scorer(text: str) -> float:
            calls["score"] += 1
            return float(len(text)) / 100.0

        def refiner(text: str, score: float, idx: int) -> str:
            calls["refine"] += 1
            return text + "X" * 50

        result = run_self_refine("seed", scorer=scorer, refiner=refiner, max_rounds=2)
        self.assertGreater(calls["score"], 1)
        self.assertGreaterEqual(calls["refine"], 1)
        self.assertGreater(result.final_score, result.initial_score)
        self.assertTrue(result.accepted)

    def test_refiner_failure_does_not_raise(self) -> None:
        def bad_refiner(text: str, score: float, idx: int) -> str:
            raise RuntimeError("oom")

        result = run_self_refine("湿病案", refiner=bad_refiner, max_rounds=2)
        self.assertTrue(result.reason.startswith("refiner_failed"))
        self.assertTrue(result.accepted)  # 没有变差
        self.assertEqual(result.final_text, "湿病案")

    def test_scorer_failure_returns_zero_result(self) -> None:
        def bad_scorer(text: str) -> float:
            raise RuntimeError("nan")

        result = run_self_refine("湿病案", scorer=bad_scorer)
        self.assertEqual(result.reason, "scorer_failed")
        self.assertEqual(result.initial_score, 0.0)
        self.assertEqual(result.rounds, [])

    def test_plateau_stops_iteration_early(self) -> None:
        def scorer(text: str) -> float:
            return 0.5

        def refiner(text: str, score: float, idx: int) -> str:
            return text + "noise"

        result = run_self_refine("seed", scorer=scorer, refiner=refiner, max_rounds=5)
        # 第一次迭代后没有提升即停止
        self.assertLessEqual(len(result.rounds), 2)
        self.assertTrue(result.reason.startswith("plateau_round_"))


class BuildMetadataTests(unittest.TestCase):
    def test_metadata_keys_present(self) -> None:
        result = run_self_refine("湿病初论。")
        meta = build_self_refine_metadata(result)
        for key in (
            "self_refine_initial_score",
            "self_refine_final_score",
            "self_refine_quality_delta",
            "self_refine_round_count",
            "self_refine_accepted",
            "self_refine_reason",
            "self_refine_trace",
            "self_refine_contract_version",
        ):
            self.assertIn(key, meta)
        self.assertEqual(meta["self_refine_contract_version"], SELF_REFINE_CONTRACT_VERSION)

    def test_round_count_excludes_baseline(self) -> None:
        # 强制 0 轮：round_count 应为 0
        meta = build_self_refine_metadata(run_self_refine("湿病案", max_rounds=0))
        self.assertEqual(meta["self_refine_round_count"], 0)

    def test_default_max_rounds_constant(self) -> None:
        self.assertGreaterEqual(DEFAULT_MAX_ROUNDS, 1)

    def test_to_dict_round_trip_friendly(self) -> None:
        result = run_self_refine("湿病初论。")
        as_dict = result.to_dict()
        self.assertEqual(as_dict["contract_version"], SELF_REFINE_CONTRACT_VERSION)
        self.assertIn("rounds", as_dict)
        self.assertIsInstance(as_dict["rounds"], list)


if __name__ == "__main__":
    unittest.main()
