"""Tests for src/research/fragment_contract.py — 辑佚字段合同。"""

from __future__ import annotations

import unittest


class TestScoreConstants(unittest.TestCase):
    def test_score_range(self):
        from src.research.fragment_contract import SCORE_BASE, SCORE_MAX

        self.assertGreater(SCORE_BASE, 0.0)
        self.assertLessEqual(SCORE_MAX, 1.0)
        self.assertLess(SCORE_BASE, SCORE_MAX)

    def test_bonus_values_positive(self):
        from src.research.fragment_contract import (
            SCORE_BONUS_DELETE,
            SCORE_BONUS_INSERT,
            SCORE_BONUS_REPLACE,
        )

        self.assertGreater(SCORE_BONUS_INSERT, 0)
        self.assertGreater(SCORE_BONUS_REPLACE, 0)
        self.assertGreater(SCORE_BONUS_DELETE, 0)
        # insert bonus 应最高
        self.assertGreater(SCORE_BONUS_INSERT, SCORE_BONUS_REPLACE)
        self.assertGreater(SCORE_BONUS_REPLACE, SCORE_BONUS_DELETE)


class TestAssessFragmentCompleteness(unittest.TestCase):
    def test_empty_candidates(self):
        from src.research.fragment_contract import assess_fragment_completeness

        result = assess_fragment_completeness([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["avg_score"], 0.0)
        self.assertEqual(result["kind_distribution"], {})

    def test_basic_statistics(self):
        from src.research.fragment_contract import assess_fragment_completeness

        candidates = [
            {
                "candidate_kind": "fragment_candidates",
                "match_score": 0.85,
                "review_status": "pending",
                "needs_manual_review": True,
                "source_refs": ["ref1"],
                "reconstruction_basis": "test basis",
            },
            {
                "candidate_kind": "lost_text_candidates",
                "match_score": 0.60,
                "review_status": "pending",
                "needs_manual_review": True,
                "source_refs": [],
                "reconstruction_basis": "",
            },
        ]
        result = assess_fragment_completeness(candidates)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["kind_distribution"]["fragment_candidates"], 1)
        self.assertEqual(result["kind_distribution"]["lost_text_candidates"], 1)
        self.assertEqual(result["high_confidence_count"], 1)
        self.assertEqual(result["has_source_refs_count"], 1)
        self.assertEqual(result["has_reconstruction_basis_count"], 1)

    def test_avg_score_calculation(self):
        from src.research.fragment_contract import assess_fragment_completeness

        candidates = [
            {"candidate_kind": "fragment_candidates", "match_score": 0.80},
            {"candidate_kind": "fragment_candidates", "match_score": 0.60},
        ]
        result = assess_fragment_completeness(candidates)
        self.assertAlmostEqual(result["avg_score"], 0.70, places=2)


class TestBuildFragmentSummary(unittest.TestCase):
    def test_combines_three_kinds(self):
        from src.research.fragment_contract import build_fragment_summary

        frag = [{"candidate_kind": "fragment_candidates", "match_score": 0.8}]
        lost = [{"candidate_kind": "lost_text_candidates", "match_score": 0.6}]
        cite = [{"candidate_kind": "citation_source_candidates", "match_score": 0.7}]
        result = build_fragment_summary(frag, lost, cite)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["fragment_candidate_count"], 1)
        self.assertEqual(result["lost_text_candidate_count"], 1)
        self.assertEqual(result["citation_source_candidate_count"], 1)

    def test_empty_all(self):
        from src.research.fragment_contract import build_fragment_summary

        result = build_fragment_summary([], [], [])
        self.assertEqual(result["total"], 0)


class TestCandidateKindConstants(unittest.TestCase):
    def test_kinds_tuple(self):
        from src.research.fragment_contract import CANDIDATE_KINDS

        self.assertIn("fragment_candidates", CANDIDATE_KINDS)
        self.assertIn("lost_text_candidates", CANDIDATE_KINDS)
        self.assertIn("citation_source_candidates", CANDIDATE_KINDS)

    def test_kind_labels(self):
        from src.research.fragment_contract import CANDIDATE_KIND_LABELS

        self.assertEqual(CANDIDATE_KIND_LABELS["fragment_candidates"], "疑似佚文")


if __name__ == "__main__":
    unittest.main()
