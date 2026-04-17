"""Tests for src/analysis/textual_evidence_chain.py — 考据证据链构建器。"""

from __future__ import annotations

import unittest


class TestBuildEvidenceChains(unittest.TestCase):
    def test_empty_inputs(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        result = build_evidence_chains()
        self.assertEqual(result["evidence_chain_count"], 0)
        self.assertEqual(result["conflict_count"], 0)
        self.assertEqual(result["evidence_chains"], [])
        self.assertEqual(result["conflict_claims"], [])

    def test_authorship_claims_from_catalog(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        catalog_documents = [
            {"work_title": "伤寒论", "author": "张仲景", "dynasty": "汉"},
            {"work_title": "伤寒论", "author": "张仲景", "dynasty": "汉"},
            {"work_title": "伤寒论", "author": "张仲景", "dynasty": "宋"},
        ]
        result = build_evidence_chains(catalog_documents=catalog_documents)
        chains = result["evidence_chains"]
        authorship_claims = [c for c in chains if c["claim_type"] == "authorship_attribution"]
        self.assertGreater(len(authorship_claims), 0)
        for claim in authorship_claims:
            self.assertIn("张仲景", claim["claim_statement"])
            self.assertGreaterEqual(claim["confidence"], 0.30)
            self.assertLessEqual(claim["confidence"], 0.95)
            self.assertIn(claim["judgment_type"], {"rule_based", "needs_review"})
            self.assertTrue(len(claim["basis_summary"]) > 0)

    def test_authorship_conflict_from_disagreement(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        catalog_documents = [
            {"work_title": "伤寒论", "author": "张仲景", "dynasty": "汉"},
            {"work_title": "伤寒论", "author": "王叔和", "dynasty": "晋"},
        ]
        result = build_evidence_chains(catalog_documents=catalog_documents)
        chains = result["evidence_chains"]
        authorship_claims = [c for c in chains if c["claim_type"] == "authorship_attribution"]
        self.assertGreater(len(authorship_claims), 0)
        # 应有反证信息
        claim = authorship_claims[0]
        self.assertTrue(
            claim.get("counter_evidence") or claim.get("needs_manual_review"),
            "Disagreement should produce counter_evidence or needs_manual_review",
        )

    def test_version_chronology_from_collation(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        collation_entries = [
            {
                "version_lineage_key": "songben_vs_mingben",
                "difference_type": "insert",
                "base_text": "",
                "witness_text": "增补内容",
                "document_title": "宋本",
                "witness_title": "明本",
            },
            {
                "version_lineage_key": "songben_vs_mingben",
                "difference_type": "insert",
                "base_text": "",
                "witness_text": "另一处增补",
                "document_title": "宋本",
                "witness_title": "明本",
            },
            {
                "version_lineage_key": "songben_vs_mingben",
                "difference_type": "insert",
                "base_text": "",
                "witness_text": "第三处增补",
                "document_title": "宋本",
                "witness_title": "明本",
            },
        ]
        result = build_evidence_chains(collation_entries=collation_entries)
        chains = result["evidence_chains"]
        version_claims = [c for c in chains if c["claim_type"] == "version_chronology"]
        self.assertGreater(len(version_claims), 0)
        for claim in version_claims:
            self.assertGreaterEqual(claim["confidence"], 0.30)
            self.assertLessEqual(claim["confidence"], 0.95)

    def test_citation_source_from_candidates(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        citation_source_candidates = [
            {
                "fragment_candidate_id": "cit-1",
                "document_title": "本草经",
                "witness_title": "神农本草经",
                "witness_text": "甘草味甘平",
                "match_score": 0.85,
            },
        ]
        result = build_evidence_chains(citation_source_candidates=citation_source_candidates)
        chains = result["evidence_chains"]
        citation_claims = [c for c in chains if c["claim_type"] == "citation_source"]
        self.assertGreater(len(citation_claims), 0)
        claim = citation_claims[0]
        self.assertIn("神农本草经", claim["claim_statement"])

    def test_mixed_inputs(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        result = build_evidence_chains(
            catalog_documents=[
                {"work_title": "本草纲目", "author": "李时珍", "dynasty": "明"},
            ],
            collation_entries=[
                {
                    "version_lineage_key": "v1_vs_v2",
                    "difference_type": "replace",
                    "base_text": "原文",
                    "witness_text": "改文",
                    "document_title": "版本一",
                    "witness_title": "版本二",
                },
            ],
            citation_source_candidates=[
                {
                    "fragment_candidate_id": "cit-mix-1",
                    "document_title": "本草经",
                    "witness_title": "神农本草经",
                    "witness_text": "某段",
                    "match_score": 0.75,
                },
            ],
        )
        chains = result["evidence_chains"]
        types = {c["claim_type"] for c in chains}
        self.assertIn("authorship_attribution", types)
        self.assertIn("citation_source", types)
        # version_chronology needs sufficient diff pattern; may or may not appear
        self.assertEqual(result["evidence_chain_count"], len(chains))

    def test_all_claims_have_required_fields(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains
        from src.research.evidence_chain_contract import EVIDENCE_CHAIN_FIELDS

        result = build_evidence_chains(
            catalog_documents=[
                {"work_title": "伤寒论", "author": "张仲景", "dynasty": "汉"},
            ],
            citation_source_candidates=[
                {
                    "fragment_candidate_id": "cit-fields-1",
                    "document_title": "本草经",
                    "witness_title": "神农本草经",
                    "witness_text": "某段",
                    "match_score": 0.80,
                },
            ],
        )
        for claim in result["evidence_chains"]:
            for field in EVIDENCE_CHAIN_FIELDS:
                self.assertIn(field, claim, f"Missing field: {field}")

    def test_conflict_detection(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        catalog_documents = [
            {"work_title": "伤寒论", "author": "张仲景", "dynasty": "汉"},
            {"work_title": "伤寒论", "author": "王叔和", "dynasty": "晋"},
        ]
        result = build_evidence_chains(catalog_documents=catalog_documents)
        # When there's authorship disagreement, conflict detection may or may not
        # find conflicts depending on confidence levels; we just verify the structure
        self.assertIsInstance(result["conflict_claims"], list)
        self.assertIsInstance(result["conflict_count"], int)
        self.assertEqual(result["conflict_count"], len(result["conflict_claims"]))


class TestClaimFieldIntegrity(unittest.TestCase):
    """验证每个 claim 的字段类型正确性。"""

    def test_claim_field_types(self):
        from src.analysis.textual_evidence_chain import build_evidence_chains

        result = build_evidence_chains(
            catalog_documents=[
                {"work_title": "伤寒论", "author": "张仲景", "dynasty": "汉"},
            ],
        )
        for claim in result["evidence_chains"]:
            self.assertIsInstance(claim["evidence_chain_id"], str)
            self.assertIsInstance(claim["claim_type"], str)
            self.assertIsInstance(claim["claim_statement"], str)
            self.assertIsInstance(claim["confidence"], (int, float))
            self.assertIsInstance(claim["basis_summary"], str)
            self.assertIsInstance(claim["judgment_type"], str)
            self.assertIsInstance(claim["counter_evidence"], list)
            self.assertIsInstance(claim["needs_manual_review"], bool)
            self.assertIsInstance(claim["review_status"], str)
            self.assertIsInstance(claim["review_reasons"], list)
            self.assertIsInstance(claim["source_refs"], list)


if __name__ == "__main__":
    unittest.main()
