"""Tests for src/analysis/textual_evidence_chain.py — 证据链构建器。"""

from __future__ import annotations

import unittest


class TestBuildEvidenceChains(unittest.TestCase):
    def test_empty_inputs(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        result = build_evidence_chains()
        self.assertEqual(result["evidence_chain_count"], 0)
        self.assertEqual(result["conflict_count"], 0)
        self.assertIsInstance(result["evidence_chains"], list)
        self.assertIsInstance(result["conflict_claims"], list)

    def test_authorship_from_catalog(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        docs = [
            {"work_title": "本草纲目", "author": "李时珍", "dynasty": "明"},
            {"work_title": "本草纲目", "author": "李时珍", "dynasty": "明代"},
        ]
        result = build_evidence_chains(catalog_documents=docs)
        self.assertGreaterEqual(result["evidence_chain_count"], 1)
        claims = result["evidence_chains"]
        authorship = [c for c in claims if c["claim_type"] == "authorship_attribution"]
        self.assertEqual(len(authorship), 1)
        self.assertIn("李时珍", authorship[0]["claim_statement"])

    def test_dynasty_normalization_in_authorship(self):
        """Phase 2: "明代" 和 "明" 应归一化为同一朝代。"""
        from src.analysis.textual_evidence_chain import build_evidence_chains

        docs = [
            {"work_title": "本草纲目", "author": "李时珍", "dynasty": "明代"},
            {"work_title": "本草纲目", "author": "李时珍", "dynasty": "明"},
        ]
        result = build_evidence_chains(catalog_documents=docs)
        authorship = [c for c in result["evidence_chains"] if c["claim_type"] == "authorship_attribution"]
        self.assertEqual(len(authorship), 1)
        # 归一化后应只有一个朝代值 "明"
        self.assertIn("明", authorship[0]["claim_statement"])

    def test_authorship_conflict_detection(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        docs = [
            {"work_title": "难经", "author": "扁鹊", "dynasty": "先秦"},
            {"work_title": "难经", "author": "秦越人", "dynasty": "先秦"},
            {"work_title": "难经", "author": "扁鹊", "dynasty": "先秦"},
        ]
        result = build_evidence_chains(catalog_documents=docs)
        authorship = [c for c in result["evidence_chains"] if c["claim_type"] == "authorship_attribution"]
        self.assertEqual(len(authorship), 1)
        # 有反证 (另有作者)
        claim = authorship[0]
        self.assertTrue(len(claim.get("counter_evidence", [])) > 0)

    def test_version_chronology_from_collation(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        entries = [
            {"version_lineage_key": "lin-1", "difference_type": "insert",
             "document_title": "base_doc", "witness_title": "witness_doc"},
            {"version_lineage_key": "lin-1", "difference_type": "insert",
             "document_title": "base_doc", "witness_title": "witness_doc"},
            {"version_lineage_key": "lin-1", "difference_type": "insert",
             "document_title": "base_doc", "witness_title": "witness_doc"},
        ]
        result = build_evidence_chains(collation_entries=entries)
        chronology = [c for c in result["evidence_chains"] if c["claim_type"] == "version_chronology"]
        self.assertGreaterEqual(len(chronology), 1)
        self.assertIn("增补本", chronology[0]["claim_statement"])

    def test_citation_source_from_candidates(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        candidates = [
            {
                "fragment_candidate_id": "cite-1",
                "document_title": "本草纲目",
                "witness_title": "神农本草经",
                "witness_text": "test text",
                "match_score": 0.75,
                "reconstruction_basis": "异文对比",
                "source_refs": ["ref1"],
                "needs_manual_review": True,
                "review_reasons": ["machine_generated"],
            },
        ]
        result = build_evidence_chains(citation_source_candidates=candidates)
        citation = [c for c in result["evidence_chains"] if c["claim_type"] == "citation_source"]
        self.assertEqual(len(citation), 1)
        self.assertIn("本草纲目", citation[0]["claim_statement"])
        self.assertIn("神农本草经", citation[0]["claim_statement"])

    def test_cross_work_claims_no_spurious_conflict(self):
        """Phase 2: 不同作品的 authorship claim 不应冲突。"""
        from src.analysis.textual_evidence_chain import build_evidence_chains

        docs = [
            {"work_title": "本草纲目", "author": "李时珍", "dynasty": "明"},
            {"work_title": "神农本草经", "author": "不详", "dynasty": "先秦"},
        ]
        result = build_evidence_chains(catalog_documents=docs)
        self.assertEqual(result["conflict_count"], 0)
        self.assertEqual(len(result["evidence_chains"]), 2)


class TestHelperFunctions(unittest.TestCase):
    def test_text_helper(self):
        from src.analysis.textual_evidence_chain import _text

        self.assertEqual(_text("  hello  "), "hello")
        self.assertEqual(_text(None), "")
        self.assertEqual(_text(123), "123")

    def test_safe_float_helper(self):
        from src.analysis.textual_evidence_chain import _safe_float

        self.assertEqual(_safe_float(0.5), 0.5)
        self.assertEqual(_safe_float(None), 0.0)
        self.assertEqual(_safe_float("abc"), 0.0)


if __name__ == "__main__":
    unittest.main()
