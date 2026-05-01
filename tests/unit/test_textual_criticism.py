"""J-2 测试: textual_criticism 子阶段与 AuthenticityVerdict contract。"""

from __future__ import annotations

import json
import unittest

from src.research.textual_criticism import (
    AUTHENTICITY_AUTHENTIC,
    AUTHENTICITY_DOUBTFUL,
    AUTHENTICITY_FORGED,
    AUTHENTICITY_INDETERMINATE,
    AUTHENTICITY_LEVELS,
    AUTHOR_VERDICT_ANONYMOUS,
    AUTHOR_VERDICT_ATTRIBUTED,
    AUTHOR_VERDICT_CONFIRMED,
    AUTHOR_VERDICT_DISPUTED,
    DATE_VERDICT_CONFIRMED,
    DATE_VERDICT_DISPUTED,
    DATE_VERDICT_LEGENDARY,
    DATE_VERDICT_RANGE,
    DATE_VERDICT_UNKNOWN,
    VERDICT_CONTRACT_VERSION,
    AuthenticityVerdict,
    TextualCriticismService,
    VerdictEvidence,
    assess_catalog_authenticity,
    assess_catalog_batch,
    build_textual_criticism_summary,
    normalize_authenticity_verdicts,
)


class AuthenticityVerdictContractTests(unittest.TestCase):
    def test_contract_version(self) -> None:
        self.assertEqual(VERDICT_CONTRACT_VERSION, "authenticity-verdict-v1")

    def test_round_trip_preserves_fields(self) -> None:
        original = AuthenticityVerdict(
            catalog_id="catalog::sk",
            work_title="伤寒论",
            date_verdict=DATE_VERDICT_CONFIRMED,
            date_estimate="东汉",
            author_verdict=AUTHOR_VERDICT_CONFIRMED,
            author_name="张机",
            authenticity=AUTHENTICITY_AUTHENTIC,
            evidence=[
                VerdictEvidence(kind="date", source_ref="x", excerpt="y", weight=0.9)
            ],
            citation_refs=["ctext:shanghanlun"],
            witness_keys=["witness:song"],
            confidence=0.91,
            review_status="accepted",
            reviewer="复核要点",
            reviewer_decision="人工确认",
            reviewed_at="2026-05-01T00:00:00+00:00",
            needs_review=True,
            needs_review_reason="需复核宋本 witness",
        )
        text = json.dumps(original.to_dict(), ensure_ascii=False)
        rebuilt = AuthenticityVerdict.from_dict(json.loads(text))
        self.assertEqual(rebuilt.catalog_id, "catalog::sk")
        self.assertEqual(rebuilt.date_verdict, DATE_VERDICT_CONFIRMED)
        self.assertEqual(rebuilt.author_verdict, AUTHOR_VERDICT_CONFIRMED)
        self.assertEqual(rebuilt.authenticity, AUTHENTICITY_AUTHENTIC)
        self.assertEqual(len(rebuilt.evidence), 1)
        self.assertAlmostEqual(rebuilt.evidence[0].weight, 0.9, places=4)
        self.assertEqual(rebuilt.citation_refs, ["ctext:shanghanlun"])
        self.assertEqual(rebuilt.witness_keys, ["witness:song"])
        self.assertEqual(rebuilt.review_status, "accepted")
        self.assertEqual(rebuilt.reviewer_decision, "人工确认")
        self.assertEqual(rebuilt.reviewed_at, "2026-05-01T00:00:00+00:00")
        self.assertTrue(rebuilt.needs_review)
        self.assertEqual(rebuilt.needs_review_reason, "需复核宋本 witness")

    def test_unknown_enum_values_fallback(self) -> None:
        rebuilt = AuthenticityVerdict.from_dict(
            {
                "catalog_id": "x",
                "date_verdict": "make-believe",
                "author_verdict": "nope",
                "authenticity": "????",
                "confidence": 9.9,
            }
        )
        self.assertEqual(rebuilt.date_verdict, DATE_VERDICT_UNKNOWN)
        self.assertEqual(rebuilt.author_verdict, AUTHOR_VERDICT_ANONYMOUS)
        self.assertEqual(rebuilt.authenticity, AUTHENTICITY_INDETERMINATE)
        self.assertEqual(rebuilt.confidence, 1.0)

    def test_legacy_dict_infers_needs_review_reason(self) -> None:
        rebuilt = AuthenticityVerdict.from_dict(
            {
                "catalog_id": "legacy",
                "date_verdict": DATE_VERDICT_DISPUTED,
                "author_verdict": AUTHOR_VERDICT_ANONYMOUS,
                "authenticity": AUTHENTICITY_DOUBTFUL,
            }
        )
        self.assertTrue(rebuilt.needs_review)
        self.assertTrue(rebuilt.needs_review_reason)
        self.assertIn("年代", rebuilt.needs_review_reason)

    def test_normalize_accepts_dataclass_and_dict(self) -> None:
        seq = [
            AuthenticityVerdict(catalog_id="a"),
            {"catalog_id": "b", "authenticity": AUTHENTICITY_DOUBTFUL},
        ]
        out = normalize_authenticity_verdicts(seq)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["catalog_id"], "a")
        self.assertEqual(out[1]["authenticity"], AUTHENTICITY_DOUBTFUL)


class TextualCriticismServiceTests(unittest.TestCase):
    def test_confirmed_dynasty_and_author_yields_authentic(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "catalog::sk",
                "work_title": "伤寒论",
                "dynasty": "东汉",
                "author": "张机",
            }
        )
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_CONFIRMED)
        self.assertEqual(verdict.author_verdict, AUTHOR_VERDICT_CONFIRMED)
        self.assertEqual(verdict.authenticity, AUTHENTICITY_AUTHENTIC)
        self.assertGreater(verdict.confidence, 0.5)
        self.assertTrue(verdict.evidence)

    def test_legendary_attribution_yields_doubtful(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "catalog::neijing",
                "work_title": "黄帝内经",
                "dynasty": "托名上古",
                "author": "传 黄帝 撰",
            }
        )
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_LEGENDARY)
        self.assertEqual(verdict.author_verdict, AUTHOR_VERDICT_ATTRIBUTED)
        # 单维度 LEGENDARY 视为 DOUBTFUL，组合 DISPUTED 才升级为 FORGED
        self.assertEqual(verdict.authenticity, AUTHENTICITY_DOUBTFUL)
        self.assertTrue(verdict.needs_review)
        self.assertIn("托名", verdict.needs_review_reason)

    def test_legendary_and_disputed_yields_forged(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "catalog::xx",
                "work_title": "某经",
                "dynasty": "托名上古",
                "author": "疑伪 某",
            }
        )
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_LEGENDARY)
        self.assertEqual(verdict.author_verdict, AUTHOR_VERDICT_DISPUTED)
        self.assertEqual(verdict.authenticity, AUTHENTICITY_FORGED)

    def test_dynasty_range_is_classified(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "c::r",
                "dynasty": "唐宋之际",
                "author": "佚名",
            }
        )
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_RANGE)
        self.assertEqual(verdict.author_verdict, AUTHOR_VERDICT_ANONYMOUS)
        self.assertEqual(verdict.authenticity, AUTHENTICITY_INDETERMINATE)
        self.assertTrue(verdict.needs_review)
        self.assertIn("作者佚名", verdict.needs_review_reason)

    def test_unknown_yields_indeterminate(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "c::u",
                "work_title": "无题",
            }
        )
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_UNKNOWN)
        self.assertEqual(verdict.author_verdict, AUTHOR_VERDICT_ANONYMOUS)
        self.assertEqual(verdict.authenticity, AUTHENTICITY_INDETERMINATE)

    def test_disputed_dynasty_yields_doubtful(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "c::d",
                "dynasty": "明代（疑伪）",
                "author": "陶弘景",
            }
        )
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_DISPUTED)
        self.assertEqual(verdict.authenticity, AUTHENTICITY_DOUBTFUL)
        self.assertTrue(verdict.needs_review)
        self.assertIn("年代", verdict.needs_review_reason)

    def test_extracts_citation_refs_and_witness_keys(self) -> None:
        verdict = assess_catalog_authenticity(
            {
                "catalog_id": "c::refs",
                "work_title": "伤寒论",
                "dynasty": "东汉",
                "author": "张机",
                "citation_refs": ["ctext:shanghanlun"],
                "source_ref": "catalog:local",
                "witness_key": "witness:song",
                "version_lineage_key": "lineage:shanghan:song",
            }
        )
        self.assertIn("ctext:shanghanlun", verdict.citation_refs)
        self.assertIn("catalog:local", verdict.citation_refs)
        self.assertIn("catalog.dynasty", verdict.citation_refs)
        self.assertIn("witness:song", verdict.witness_keys)
        self.assertIn("lineage:shanghan:song", verdict.witness_keys)

    def test_missing_catalog_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            assess_catalog_authenticity({"work_title": "x"})

    def test_non_mapping_raises(self) -> None:
        with self.assertRaises(TypeError):
            assess_catalog_authenticity("not a mapping")  # type: ignore[arg-type]

    def test_batch_skips_invalid_entries(self) -> None:
        entries = [
            {"catalog_id": "c1", "dynasty": "唐", "author": "孙思邈"},
            {"work_title": "missing id"},  # 应被跳过
            {"catalog_id": "c2", "dynasty": "佚名"},
        ]
        verdicts = assess_catalog_batch(entries)
        ids = {v.catalog_id for v in verdicts}
        self.assertEqual(ids, {"c1", "c2"})

    def test_summary_distribution_and_review_count(self) -> None:
        entries = [
            {"catalog_id": "c1", "dynasty": "东汉", "author": "张机"},
            {"catalog_id": "c2", "dynasty": "托名上古", "author": "疑伪 某"},
            {"catalog_id": "c3", "dynasty": "明代（疑伪）", "author": "佚名"},
        ]
        verdicts = assess_catalog_batch(entries)
        summary = build_textual_criticism_summary(verdicts)
        self.assertEqual(summary["verdict_count"], 3)
        self.assertEqual(summary["contract_version"], "authenticity-verdict-v1")
        self.assertGreaterEqual(summary["needs_review_count"], 2)
        self.assertIn(AUTHENTICITY_AUTHENTIC, summary["authenticity_distribution"])
        for level in summary["authenticity_distribution"]:
            self.assertIn(level, AUTHENTICITY_LEVELS)

    def test_llm_caller_failure_does_not_break_verdict(self) -> None:
        def broken(_p: str) -> str:
            raise RuntimeError("oom")

        verdict = assess_catalog_authenticity(
            {"catalog_id": "c::x", "dynasty": "宋", "author": "佚名"},
            llm_caller=broken,
        )
        self.assertEqual(verdict.reviewer, "")
        self.assertEqual(verdict.date_verdict, DATE_VERDICT_CONFIRMED)

    def test_llm_caller_populates_reviewer_note(self) -> None:
        def fake(_p: str) -> str:
            return "复核要点：核实宋代刻本流传源流"

        verdict = assess_catalog_authenticity(
            {"catalog_id": "c::x", "dynasty": "宋", "author": "佚名"},
            llm_caller=fake,
        )
        self.assertIn("宋代", verdict.reviewer)

    def test_service_facade_assess(self) -> None:
        service = TextualCriticismService(
            catalog_entries=[
                {"catalog_id": "c1", "dynasty": "唐", "author": "孙思邈"},
            ]
        )
        verdicts = service.assess()
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0].catalog_id, "c1")


if __name__ == "__main__":
    unittest.main()
