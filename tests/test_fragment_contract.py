"""Tests for src/research/fragment_contract.py — 辑佚字段合同。"""

from __future__ import annotations

import unittest


class TestCandidateKindConstants(unittest.TestCase):
    def test_candidate_kinds_tuple(self):
        from src.research.fragment_contract import CANDIDATE_KINDS

        self.assertEqual(len(CANDIDATE_KINDS), 3)
        self.assertIn("fragment_candidates", CANDIDATE_KINDS)
        self.assertIn("lost_text_candidates", CANDIDATE_KINDS)
        self.assertIn("citation_source_candidates", CANDIDATE_KINDS)

    def test_candidate_kind_labels(self):
        from src.research.fragment_contract import CANDIDATE_KIND_LABELS

        self.assertEqual(CANDIDATE_KIND_LABELS["fragment_candidates"], "疑似佚文")
        self.assertEqual(CANDIDATE_KIND_LABELS["lost_text_candidates"], "疑似佚失")
        self.assertEqual(CANDIDATE_KIND_LABELS["citation_source_candidates"], "引文来源")


class TestFragmentMetadataFields(unittest.TestCase):
    def test_metadata_fields_frozenset(self):
        from src.research.fragment_contract import FRAGMENT_METADATA_FIELDS

        self.assertIsInstance(FRAGMENT_METADATA_FIELDS, frozenset)
        self.assertIn("fragment_candidate_id", FRAGMENT_METADATA_FIELDS)
        self.assertIn("match_score", FRAGMENT_METADATA_FIELDS)
        self.assertIn("source_refs", FRAGMENT_METADATA_FIELDS)
        self.assertIn("reconstruction_basis", FRAGMENT_METADATA_FIELDS)
        self.assertIn("needs_manual_review", FRAGMENT_METADATA_FIELDS)
        self.assertIn("review_status", FRAGMENT_METADATA_FIELDS)
        self.assertIn("review_reasons", FRAGMENT_METADATA_FIELDS)


class TestReviewStatusConstants(unittest.TestCase):
    def test_review_statuses(self):
        from src.research.fragment_contract import REVIEW_STATUSES

        self.assertIn("pending", REVIEW_STATUSES)
        self.assertIn("accepted", REVIEW_STATUSES)
        self.assertIn("rejected", REVIEW_STATUSES)
        self.assertEqual(len(REVIEW_STATUSES), 3)


class TestScoreConstants(unittest.TestCase):
    def test_score_range(self):
        from src.research.fragment_contract import SCORE_BASE, SCORE_MAX

        self.assertEqual(SCORE_BASE, 0.46)
        self.assertEqual(SCORE_MAX, 0.98)


class TestAssessFragmentCompleteness(unittest.TestCase):
    def test_empty_candidates(self):
        from src.research.fragment_contract import assess_fragment_completeness

        result = assess_fragment_completeness([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["kind_distribution"], {})
        self.assertEqual(result["review_status_distribution"], {})
        self.assertEqual(result["needs_review_count"], 0)
        self.assertEqual(result["high_confidence_count"], 0)
        self.assertEqual(result["avg_score"], 0.0)
        self.assertEqual(result["has_source_refs_count"], 0)
        self.assertEqual(result["has_reconstruction_basis_count"], 0)

    def test_single_high_confidence_candidate(self):
        from src.research.fragment_contract import assess_fragment_completeness

        candidates = [
            {
                "candidate_kind": "fragment_candidates",
                "match_score": 0.92,
                "source_refs": ["ref1", "ref2"],
                "reconstruction_basis": "异文比对：基础本无此段，见证本新增",
                "needs_manual_review": True,
                "review_status": "pending",
            }
        ]
        result = assess_fragment_completeness(candidates)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["kind_distribution"], {"fragment_candidates": 1})
        self.assertEqual(result["review_status_distribution"], {"pending": 1})
        self.assertEqual(result["needs_review_count"], 1)
        self.assertEqual(result["high_confidence_count"], 1)
        self.assertAlmostEqual(result["avg_score"], 0.92, places=2)
        self.assertEqual(result["has_source_refs_count"], 1)
        self.assertEqual(result["has_reconstruction_basis_count"], 1)

    def test_mixed_candidates(self):
        from src.research.fragment_contract import assess_fragment_completeness

        candidates = [
            {
                "candidate_kind": "fragment_candidates",
                "match_score": 0.85,
                "source_refs": ["ref1"],
                "reconstruction_basis": "basis1",
                "needs_manual_review": True,
                "review_status": "pending",
            },
            {
                "candidate_kind": "lost_text_candidates",
                "match_score": 0.52,
                "source_refs": [],
                "reconstruction_basis": "",
                "needs_manual_review": False,
                "review_status": "rejected",
            },
            {
                "candidate_kind": "citation_source_candidates",
                "match_score": 0.78,
                "source_refs": ["ref2", "ref3"],
                "reconstruction_basis": "basis3",
                "needs_manual_review": True,
                "review_status": "pending",
            },
        ]
        result = assess_fragment_completeness(candidates)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["kind_distribution"]["fragment_candidates"], 1)
        self.assertEqual(result["kind_distribution"]["lost_text_candidates"], 1)
        self.assertEqual(result["kind_distribution"]["citation_source_candidates"], 1)
        self.assertEqual(result["needs_review_count"], 2)
        self.assertEqual(result["high_confidence_count"], 1)  # only 0.85 >= 0.80
        self.assertAlmostEqual(result["avg_score"], (0.85 + 0.52 + 0.78) / 3, places=4)
        self.assertEqual(result["has_source_refs_count"], 2)
        self.assertEqual(result["has_reconstruction_basis_count"], 2)
        self.assertEqual(result["review_status_distribution"]["pending"], 2)
        self.assertEqual(result["review_status_distribution"]["rejected"], 1)

    def test_missing_fields_handled_gracefully(self):
        from src.research.fragment_contract import assess_fragment_completeness

        candidates = [
            {},
            {"candidate_kind": None, "match_score": None},
        ]
        result = assess_fragment_completeness(candidates)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["kind_distribution"], {})
        self.assertEqual(result["avg_score"], 0.0)
        self.assertEqual(result["high_confidence_count"], 0)


class TestBuildFragmentSummary(unittest.TestCase):
    def test_all_three_types(self):
        from src.research.fragment_contract import build_fragment_summary

        fragments = [
            {"candidate_kind": "fragment_candidates", "match_score": 0.80, "review_status": "pending", "needs_manual_review": True, "source_refs": ["r1"], "reconstruction_basis": "b1"},
        ]
        lost = [
            {"candidate_kind": "lost_text_candidates", "match_score": 0.60, "review_status": "accepted", "needs_manual_review": False, "source_refs": [], "reconstruction_basis": ""},
        ]
        citation = [
            {"candidate_kind": "citation_source_candidates", "match_score": 0.90, "review_status": "pending", "needs_manual_review": True, "source_refs": ["r2"], "reconstruction_basis": "b3"},
        ]
        result = build_fragment_summary(fragments, lost, citation)
        self.assertEqual(result["fragment_candidate_count"], 1)
        self.assertEqual(result["lost_text_candidate_count"], 1)
        self.assertEqual(result["citation_source_candidate_count"], 1)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["needs_review_count"], 2)
        self.assertEqual(result["high_confidence_count"], 2)  # 0.80 and 0.90

    def test_empty_all(self):
        from src.research.fragment_contract import build_fragment_summary

        result = build_fragment_summary([], [], [])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["fragment_candidate_count"], 0)
        self.assertEqual(result["lost_text_candidate_count"], 0)
        self.assertEqual(result["citation_source_candidate_count"], 0)


class TestSafeFloat(unittest.TestCase):
    def test_valid_values(self):
        from src.research.fragment_contract import _safe_float

        self.assertEqual(_safe_float(0.5), 0.5)
        self.assertEqual(_safe_float(1), 1.0)
        self.assertEqual(_safe_float("0.8"), 0.8)

    def test_invalid_values(self):
        from src.research.fragment_contract import _safe_float

        self.assertEqual(_safe_float(None), 0.0)
        self.assertEqual(_safe_float("abc"), 0.0)
        self.assertEqual(_safe_float({}), 0.0)


if __name__ == "__main__":
    unittest.main()
