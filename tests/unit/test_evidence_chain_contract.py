"""Tests for src/research/evidence_chain_contract.py — 考据字段合同。"""

from __future__ import annotations

import unittest


class TestBuildClaim(unittest.TestCase):
    def test_basic_claim(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-001",
            claim_type="authorship_attribution",
            claim_statement="「本草纲目」作者为李时珍",
            confidence=0.85,
            basis_summary="基于 5 条目录学记录",
        )
        self.assertEqual(claim["evidence_chain_id"], "test-001")
        self.assertEqual(claim["claim_type"], "authorship_attribution")
        self.assertAlmostEqual(claim["confidence"], 0.85, places=2)
        self.assertEqual(claim["judgment_type"], "rule_based")
        self.assertFalse(claim["needs_manual_review"])

    def test_low_confidence_triggers_review(self):
        from src.research.evidence_chain_contract import build_claim, CONFIDENCE_REVIEW_THRESHOLD

        claim = build_claim(
            evidence_chain_id="test-002",
            claim_type="version_chronology",
            claim_statement="test",
            confidence=CONFIDENCE_REVIEW_THRESHOLD - 0.01,
            basis_summary="test",
        )
        self.assertTrue(claim["needs_manual_review"])
        self.assertEqual(claim["judgment_type"], "needs_review")
        self.assertEqual(claim["review_status"], "pending")

    def test_counter_evidence_triggers_review(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="test-003",
            claim_type="authorship_attribution",
            claim_statement="test",
            confidence=0.90,
            basis_summary="test",
            counter_evidence=["另有记录标注不同作者"],
        )
        self.assertTrue(claim["needs_manual_review"])
        self.assertIn("另有记录标注不同作者", claim["counter_evidence"])

    def test_confidence_clamped(self):
        from src.research.evidence_chain_contract import (
            build_claim, CONFIDENCE_MIN, CONFIDENCE_MAX,
        )

        claim_low = build_claim(
            evidence_chain_id="c1", claim_type="x", claim_statement="s",
            confidence=0.01, basis_summary="b",
        )
        claim_high = build_claim(
            evidence_chain_id="c2", claim_type="x", claim_statement="s",
            confidence=1.5, basis_summary="b",
        )
        self.assertAlmostEqual(claim_low["confidence"], CONFIDENCE_MIN, places=2)
        self.assertAlmostEqual(claim_high["confidence"], CONFIDENCE_MAX, places=2)

    def test_extra_fields_merged(self):
        from src.research.evidence_chain_contract import build_claim

        claim = build_claim(
            evidence_chain_id="c", claim_type="x", claim_statement="s",
            confidence=0.7, basis_summary="b",
            extra={"work_title": "本草纲目", "author": "李时珍"},
        )
        self.assertEqual(claim["work_title"], "本草纲目")
        self.assertEqual(claim["author"], "李时珍")


class TestDetectClaimConflicts(unittest.TestCase):
    def test_no_conflict_single_claim(self):
        from src.research.evidence_chain_contract import detect_claim_conflicts

        claims = [{"claim_type": "authorship_attribution", "claim_statement": "A", "confidence": 0.8}]
        self.assertEqual(detect_claim_conflicts(claims), [])

    def test_same_statement_no_conflict(self):
        from src.research.evidence_chain_contract import detect_claim_conflicts

        claims = [
            {"claim_type": "authorship_attribution", "claim_statement": "A", "confidence": 0.8,
             "evidence_chain_id": "c1"},
            {"claim_type": "authorship_attribution", "claim_statement": "A", "confidence": 0.7,
             "evidence_chain_id": "c2"},
        ]
        self.assertEqual(detect_claim_conflicts(claims), [])

    def test_different_statement_same_type_conflict(self):
        from src.research.evidence_chain_contract import detect_claim_conflicts

        claims = [
            {"claim_type": "authorship_attribution", "claim_statement": "作者为A",
             "confidence": 0.8, "evidence_chain_id": "c1"},
            {"claim_type": "authorship_attribution", "claim_statement": "作者为B",
             "confidence": 0.7, "evidence_chain_id": "c2"},
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["claim_type"], "authorship_attribution")

    def test_different_works_no_conflict(self):
        """Phase 2: 不同 work_title 的 claim 不应互相冲突。"""
        from src.research.evidence_chain_contract import detect_claim_conflicts

        claims = [
            {"claim_type": "authorship_attribution", "claim_statement": "作者为A",
             "confidence": 0.8, "evidence_chain_id": "c1", "work_title": "本草纲目"},
            {"claim_type": "authorship_attribution", "claim_statement": "作者为B",
             "confidence": 0.7, "evidence_chain_id": "c2", "work_title": "神农本草经"},
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertEqual(len(conflicts), 0)

    def test_same_work_still_conflicts(self):
        """Phase 2: 同一 work_title 内不同 statement 仍应冲突。"""
        from src.research.evidence_chain_contract import detect_claim_conflicts

        claims = [
            {"claim_type": "authorship_attribution", "claim_statement": "作者为A",
             "confidence": 0.8, "evidence_chain_id": "c1", "work_title": "本草纲目"},
            {"claim_type": "authorship_attribution", "claim_statement": "作者为B",
             "confidence": 0.7, "evidence_chain_id": "c2", "work_title": "本草纲目"},
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertEqual(len(conflicts), 1)

    def test_low_confidence_no_conflict(self):
        from src.research.evidence_chain_contract import detect_claim_conflicts

        claims = [
            {"claim_type": "authorship_attribution", "claim_statement": "A",
             "confidence": 0.8, "evidence_chain_id": "c1"},
            {"claim_type": "authorship_attribution", "claim_statement": "B",
             "confidence": 0.2, "evidence_chain_id": "c2"},
        ]
        conflicts = detect_claim_conflicts(claims)
        self.assertEqual(len(conflicts), 0)


class TestAssessEvidenceChainCompleteness(unittest.TestCase):
    def test_empty(self):
        from src.research.evidence_chain_contract import assess_evidence_chain_completeness

        result = assess_evidence_chain_completeness([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["avg_confidence"], 0.0)

    def test_basic_statistics(self):
        from src.research.evidence_chain_contract import assess_evidence_chain_completeness

        claims = [
            {"claim_type": "authorship_attribution", "judgment_type": "rule_based",
             "review_status": "accepted", "confidence": 0.85, "basis_summary": "test",
             "needs_manual_review": False},
            {"claim_type": "version_chronology", "judgment_type": "needs_review",
             "review_status": "pending", "confidence": 0.45, "basis_summary": "test",
             "needs_manual_review": True, "counter_evidence": ["反证"]},
        ]
        result = assess_evidence_chain_completeness(claims)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["high_confidence_count"], 1)
        self.assertEqual(result["needs_review_count"], 1)
        self.assertEqual(result["has_counter_evidence_count"], 1)
        self.assertEqual(result["has_basis_summary_count"], 2)


class TestBuildEvidenceChainSummary(unittest.TestCase):
    def test_delegates_to_completeness(self):
        from src.research.evidence_chain_contract import build_evidence_chain_summary

        result = build_evidence_chain_summary([])
        self.assertEqual(result["total"], 0)


if __name__ == "__main__":
    unittest.main()
