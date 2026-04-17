"""Tests for evidence chain artifact export/import in observe_philology.py."""

from __future__ import annotations

import unittest


class TestEvidenceChainArtifactConstant(unittest.TestCase):
    def test_artifact_constant_defined(self):
        from src.research.observe_philology import OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT

        self.assertEqual(OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT, "observe_philology_evidence_chain")

    def test_artifact_in_names_frozenset(self):
        from src.research.observe_philology import (
            OBSERVE_PHILOLOGY_ARTIFACT_NAMES,
            OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT,
        )

        self.assertIn(OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT, OBSERVE_PHILOLOGY_ARTIFACT_NAMES)


class TestNormalizeEvidenceChain(unittest.TestCase):
    def test_normalize_includes_evidence_chains(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "evidence_chains": [
                {
                    "evidence_chain_id": "ec-1",
                    "claim_type": "authorship_attribution",
                    "claim_statement": "张仲景为作者",
                    "confidence": 0.80,
                    "basis_summary": "多版本一致",
                    "judgment_type": "rule_based",
                    "counter_evidence": [],
                    "needs_manual_review": False,
                    "review_status": "pending",
                    "review_reasons": [],
                    "source_refs": [],
                },
            ],
            "conflict_claims": [],
            "evidence_chain_count": 1,
            "conflict_count": 0,
        }
        normalized = normalize_observe_philology_assets(raw)
        self.assertEqual(len(normalized["evidence_chains"]), 1)
        self.assertEqual(normalized["evidence_chain_count"], 1)
        self.assertEqual(normalized["conflict_count"], 0)
        self.assertIsInstance(normalized["conflict_claims"], list)

    def test_normalize_empty_evidence(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        normalized = normalize_observe_philology_assets({})
        self.assertEqual(normalized["evidence_chains"], [])
        self.assertEqual(normalized["conflict_claims"], [])
        self.assertEqual(normalized["evidence_chain_count"], 0)
        self.assertEqual(normalized["conflict_count"], 0)


class TestBuildEvidenceChainArtifact(unittest.TestCase):
    def test_artifact_emitted_when_evidence_chains_present(self):
        from src.research.observe_philology import (
            OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT,
            build_observe_philology_artifact_payloads,
        )

        assets = {
            "evidence_chains": [
                {
                    "evidence_chain_id": "ec-1",
                    "claim_type": "authorship_attribution",
                    "claim_statement": "张仲景为作者",
                    "confidence": 0.80,
                    "basis_summary": "多版本一致",
                    "judgment_type": "rule_based",
                    "counter_evidence": [],
                    "needs_manual_review": False,
                    "review_status": "pending",
                    "review_reasons": [],
                    "source_refs": [],
                },
            ],
            "conflict_claims": [],
            "evidence_chain_count": 1,
            "conflict_count": 0,
            "annotation_report": {"summary": {"processed_document_count": 1}},
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        ec_artifacts = [a for a in artifacts if a["name"] == OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT]
        self.assertEqual(len(ec_artifacts), 1)
        artifact = ec_artifacts[0]
        self.assertEqual(artifact["artifact_type"], "analysis")
        self.assertEqual(artifact["content"]["asset_kind"], "evidence_chain")
        self.assertEqual(len(artifact["content"]["evidence_chains"]), 1)
        self.assertEqual(artifact["metadata"]["evidence_chain_count"], 1)

    def test_no_artifact_when_empty(self):
        from src.research.observe_philology import (
            OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT,
            build_observe_philology_artifact_payloads,
        )

        assets = {
            "annotation_report": {"summary": {"processed_document_count": 1}},
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        ec_artifacts = [a for a in artifacts if a["name"] == OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT]
        self.assertEqual(len(ec_artifacts), 0)


class TestEvidenceChainRoundTrip(unittest.TestCase):
    def test_round_trip_through_artifacts(self):
        from src.research.observe_philology import (
            build_observe_philology_artifact_payloads,
            extract_observe_philology_assets_from_artifacts,
        )

        original_chain = {
            "evidence_chain_id": "ec-rt-1",
            "claim_type": "citation_source",
            "claim_statement": "引自《神农本草经》",
            "confidence": 0.75,
            "basis_summary": "文本匹配",
            "judgment_type": "rule_based",
            "counter_evidence": [],
            "needs_manual_review": False,
            "review_status": "pending",
            "review_reasons": [],
            "source_refs": [],
        }
        assets = {
            "evidence_chains": [original_chain],
            "conflict_claims": [],
            "evidence_chain_count": 1,
            "conflict_count": 0,
            "annotation_report": {"summary": {"processed_document_count": 1}},
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        restored = extract_observe_philology_assets_from_artifacts(artifacts)
        self.assertGreaterEqual(len(restored["evidence_chains"]), 1)
        restored_chain = restored["evidence_chains"][0]
        self.assertEqual(restored_chain["evidence_chain_id"], "ec-rt-1")
        self.assertEqual(restored_chain["claim_type"], "citation_source")


class TestEvidenceChainCatalogMetrics(unittest.TestCase):
    def test_metrics_injected_into_catalog_summary(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "catalog_summary": {
                "summary": {"catalog_document_count": 1},
                "documents": [{"title": "test"}],
                "version_lineages": [],
            },
            "evidence_chains": [
                {
                    "evidence_chain_id": "ec-m1",
                    "claim_type": "authorship_attribution",
                    "claim_statement": "test",
                    "confidence": 0.70,
                    "basis_summary": "test",
                    "judgment_type": "rule_based",
                    "counter_evidence": [],
                    "needs_manual_review": False,
                    "review_status": "pending",
                    "review_reasons": [],
                    "source_refs": [],
                },
            ],
            "conflict_claims": [],
            "annotation_report": {"summary": {}},
        }
        normalized = normalize_observe_philology_assets(raw)
        catalog_metrics = normalized["catalog_summary"]["summary"]
        self.assertEqual(catalog_metrics["evidence_chain_count"], 1)
        self.assertEqual(catalog_metrics["evidence_conflict_count"], 0)
        self.assertIn("evidence_claim_type_distribution", catalog_metrics)
        self.assertIn("evidence_confidence_avg", catalog_metrics)


if __name__ == "__main__":
    unittest.main()
