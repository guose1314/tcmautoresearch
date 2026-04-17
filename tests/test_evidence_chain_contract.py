"""Tests for src/research/evidence_chain_contract.py — 考据证据链合同。"""

from __future__ import annotations

import unittest


class TestClaimTypeConstants(unittest.TestCase):
    def test_claim_types_tuple(self):
        from src.research.evidence_chain_contract import CLAIM_TYPES

        self.assertEqual(len(CLAIM_TYPES), 3)
        self.assertIn("authorship_attribution", CLAIM_TYPES)
        self.assertIn("version_chronology", CLAIM_TYPES)
        self.assertIn("citation_source", CLAIM_TYPES)

    def test_claim_type_labels(self):
        from src.research.evidence_chain_contract import CLAIM_TYPE_LABELS

        self.assertEqual(CLAIM_TYPE_LABELS["authorship_attribution"], "作者归属")
        self.assertEqual(CLAIM_TYPE_LABELS["version_chronology"], "版本先后")
        self.assertEqual(CLAIM_TYPE_LABELS["citation_source"], "引文来源")

    def test_individual_claim_type_constants(self):
        from src.research.evidence_chain_contract import (
            CLAIM_TYPE_AUTHORSHIP,
            CLAIM_TYPE_CITATION_SOURCE,
            CLAIM_TYPE_VERSION_CHRONOLOGY,
        )

        self.assertEqual(CLAIM_TYPE_AUTHORSHIP, "authorship_attribution")
        self.assertEqual(CLAIM_TYPE_VERSION_CHRONOLOGY, "version_chronology")
        self.assertEqual(CLAIM_TYPE_CITATION_SOURCE, "citation_source")


class TestJudgmentTypes(unittest.TestCase):
    def test_judgment_types_frozenset(self):
        from src.research.evidence_chain_contract import JUDGMENT_TYPES

        self.assertIsInstance(JUDGMENT_TYPES, frozenset)
        self.assertEqual(len(JUDGMENT_TYPES), 2)
        self.assertIn("rule_based", JUDGMENT_TYPES)
        self.assertIn("needs_review", JUDGMENT_TYPES)

    def test_individual_judgment_constants(self):
        from src.research.evidence_chain_contract import (
            JUDGMENT_NEEDS_REVIEW,
            JUDGMENT_RULE_BASED,
        )

        self.assertEqual(JUDGMENT_RULE_BASED, "rule_based")
        self.assertEqual(JUDGMENT_NEEDS_REVIEW, "needs_review")


class TestReviewStatuses(unittest.TestCase):
    def test_review_statuses(self):
        from src.research.evidence_chain_contract import REVIEW_STATUSES

        self.assertIn("pending", REVIEW_STATUSES)
        self.assertIn("accepted", REVIEW_STATUSES)
        self.assertIn("rejected", REVIEW_STATUSES)
        self.assertEqual(len(REVIEW_STATUSES), 3)


class TestEvidenceChainFields(unittest.TestCase):
    def test_fields_frozenset(self):
        from src.research.evidence_chain_contract import EVIDENCE_CHAIN_FIELDS

        self.assertIsInstance(EVIDENCE_CHAIN_FIELDS, frozenset)
        self.assertIn("evidence_chain_id", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("claim_type", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("claim_statement", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("confidence", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("basis_summary", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("judgment_type", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("counter_evidence", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("needs_manual_review", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("review_status", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("review_reasons", EVIDENCE_CHAIN_FIELDS)
        self.assertIn("source_refs", EVIDENCE_CHAIN_FIELDS)


class TestConfidenceConstants(unittest.TestCase):
    def test_confidence_bounds(self):
        from src.research.evidence_chain_contract import (
            CONFIDENCE_MAX,
            CONFIDENCE_MIN,
            CONFIDENCE_REVIEW_THRESHOLD,
        )

        self.assertAlmostEqual(CONFIDENCE_MIN, 0.30)
        self.assertAlmostEqual(CONFIDENCE_MAX, 0.95)
        self.assertAlmostEqual(CONFIDENCE_REVIEW_THRESHOLD, 0.60)


class TestBuildClaim(unittest.TestCase):
    def test_basic_claim(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-basic-1",
            claim_type="authorship_attribution",
            claim_statement="张仲景为《伤寒论》作者",
            confidence=0.85,
            basis_summary="多版本作者字段一致",
        )
        self.assertEqual(claim["claim_type"], "authorship_attribution")
        self.assertEqual(claim["claim_statement"], "张仲景为《伤寒论》作者")
        self.assertAlmostEqual(claim["confidence"], 0.85)
        self.assertEqual(claim["basis_summary"], "多版本作者字段一致")
        self.assertEqual(claim["judgment_type"], "rule_based")
        self.assertFalse(claim["needs_manual_review"])
        self.assertEqual(claim["review_status"], "accepted")
        self.assertIsInstance(claim["evidence_chain_id"], str)
        self.assertEqual(claim["evidence_chain_id"], "test-basic-1")

    def test_low_confidence_triggers_review(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-low-1",
            claim_type="version_chronology",
            claim_statement="宋本先于明本",
            confidence=0.45,
            basis_summary="增补模式推断",
        )
        self.assertTrue(claim["needs_manual_review"])
        self.assertEqual(claim["judgment_type"], "needs_review")

    def test_counter_evidence_triggers_review(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-counter-1",
            claim_type="authorship_attribution",
            claim_statement="张仲景为《伤寒论》作者",
            confidence=0.80,
            basis_summary="多版本一致",
            counter_evidence=["某版本标注为王叔和"],
        )
        self.assertTrue(claim["needs_manual_review"])

    def test_confidence_clamped(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-clamp-low",
            claim_type="citation_source",
            claim_statement="引自《神农本草经》",
            confidence=0.10,
            basis_summary="匹配分偏低",
        )
        self.assertAlmostEqual(claim["confidence"], 0.30)

        claim2 = build_claim(
            evidence_chain_id="test-clamp-high",
            claim_type="citation_source",
            claim_statement="引自《神农本草经》",
            confidence=0.99,
            basis_summary="精确匹配",
        )
        self.assertAlmostEqual(claim2["confidence"], 0.95)

    def test_invalid_claim_type(self):
        from src.research.evidence_chain_contract import build_claim

        # build_claim does not validate claim_type — it's a lightweight factory
        claim = build_claim(
            evidence_chain_id="test-invalid",
            claim_type="invalid_type",
            claim_statement="test",
            confidence=0.5,
            basis_summary="test",
        )
        self.assertEqual(claim["claim_type"], "invalid_type")

    def test_source_refs_default(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-refs-1",
            claim_type="citation_source",
            claim_statement="引自某书",
            confidence=0.7,
            basis_summary="文本匹配",
            source_refs=["ref1", "ref2"],
        )
        self.assertEqual(claim["source_refs"], ["ref1", "ref2"])


class TestDetectClaimConflicts(unittest.TestCase):
    def test_no_conflicts(self):
        from src.research.evidence_chain_contract import (
            build_claim,
            detect_claim_conflicts,
        )

        claims = [
            build_claim(
                evidence_chain_id="test-noconflict-1",
                claim_type="authorship_attribution",
                claim_statement="张仲景为作者",
                confidence=0.85,
                basis_summary="一致",
            ),
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertEqual(len(conflicts), 0)

    def test_detects_conflicts(self):
        from src.research.evidence_chain_contract import (
            build_claim,
            detect_claim_conflicts,
        )

        claims = [
            build_claim(
                evidence_chain_id="test-conflict-a",
                claim_type="authorship_attribution",
                claim_statement="张仲景为作者",
                confidence=0.70,
                basis_summary="多数一致",
            ),
            build_claim(
                evidence_chain_id="test-conflict-b",
                claim_type="authorship_attribution",
                claim_statement="王叔和为作者",
                confidence=0.55,
                basis_summary="少数版本标注",
            ),
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertGreater(len(conflicts), 0)

    def test_low_confidence_not_conflicting(self):
        from src.research.evidence_chain_contract import (
            build_claim,
            detect_claim_conflicts,
        )

        claims = [
            build_claim(
                evidence_chain_id="test-lowconf-a",
                claim_type="authorship_attribution",
                claim_statement="张仲景为作者",
                confidence=0.70,
                basis_summary="多数一致",
            ),
            build_claim(
                evidence_chain_id="test-lowconf-b",
                claim_type="authorship_attribution",
                claim_statement="王叔和为作者",
                confidence=0.35,
                basis_summary="单一孤证",
            ),
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertEqual(len(conflicts), 0)


class TestAssessEvidenceChainCompleteness(unittest.TestCase):
    def test_empty_claims(self):
        from src.research.evidence_chain_contract import (
            assess_evidence_chain_completeness,
        )

        result = assess_evidence_chain_completeness([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["claim_type_distribution"], {})
        self.assertEqual(result["conflict_count"], 0)

    def test_with_claims(self):
        from src.research.evidence_chain_contract import (
            assess_evidence_chain_completeness,
            build_claim,
        )

        claims = [
            build_claim(
                evidence_chain_id="test-assess-1",
                claim_type="authorship_attribution",
                claim_statement="张仲景为作者",
                confidence=0.80,
                basis_summary="多版本一致",
            ),
            build_claim(
                evidence_chain_id="test-assess-2",
                claim_type="version_chronology",
                claim_statement="宋本先于明本",
                confidence=0.55,
                basis_summary="增补模式",
            ),
            build_claim(
                evidence_chain_id="test-assess-3",
                claim_type="citation_source",
                claim_statement="引自某书",
                confidence=0.70,
                basis_summary="匹配",
            ),
        ]
        result = assess_evidence_chain_completeness(claims)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["claim_type_distribution"]["authorship_attribution"], 1)
        self.assertEqual(result["claim_type_distribution"]["version_chronology"], 1)
        self.assertEqual(result["claim_type_distribution"]["citation_source"], 1)
        self.assertIn("avg_confidence", result)
        self.assertIn("needs_review_count", result)


class TestBuildEvidenceChainSummary(unittest.TestCase):
    def test_summary_delegates_to_assess(self):
        from src.research.evidence_chain_contract import (
            build_claim,
            build_evidence_chain_summary,
        )

        claims = [
            build_claim(
                evidence_chain_id="test-summary-1",
                claim_type="authorship_attribution",
                claim_statement="test",
                confidence=0.80,
                basis_summary="test",
            ),
        ]
        summary = build_evidence_chain_summary(claims)
        self.assertEqual(summary["total"], 1)
        self.assertIn("claim_type_distribution", summary)

    def test_summary_empty(self):
        from src.research.evidence_chain_contract import build_evidence_chain_summary

        summary = build_evidence_chain_summary([])
        self.assertEqual(summary["total"], 0)


if __name__ == "__main__":
    unittest.main()
