"""Unit tests for EvidenceContract v2 typed dataclasses."""

from __future__ import annotations

import json
import tempfile
import unittest
from typing import Any, Dict
from unittest.mock import patch

from src.infra.layered_cache import LayeredTaskCache


class TestEvidenceProvenance(unittest.TestCase):
    def test_from_dict_round_trip(self):
        from src.research.evidence_contract import EvidenceProvenance

        data = {
            "source": "pubmed",
            "source_type": "pubmed",
            "source_ref": "PMID:12345",
            "doi": "10.1000/test",
            "title": "麻黄研究",
            "authors": ["张三", "李四"],
            "year": 2024,
        }
        prov = EvidenceProvenance.from_dict(data)
        self.assertEqual(prov.source, "pubmed")
        self.assertEqual(prov.doi, "10.1000/test")
        self.assertEqual(prov.authors, ["张三", "李四"])

        d = prov.to_dict()
        self.assertEqual(d["source"], "pubmed")
        self.assertEqual(d["doi"], "10.1000/test")

    def test_defaults(self):
        from src.research.evidence_contract import EvidenceProvenance

        prov = EvidenceProvenance()
        self.assertEqual(prov.source, "")
        self.assertEqual(prov.authors, [])
        d = prov.to_dict()
        self.assertIsInstance(d, dict)


class TestEvidenceRecord(unittest.TestCase):
    def test_from_normalized_dict(self):
        from src.research.evidence_contract import (
            EvidenceRecord,
            normalize_evidence_record,
        )

        raw = {
            "source_entity": "麻黄",
            "target_entity": "发汗",
            "relation_type": "功效",
            "confidence": 0.85,
            "excerpt": "麻黄辛温，主发汗",
            "evidence_grade": "moderate",
            "title": "本草纲目",
            "source_type": "classic_text",
            "source_ref": "bencao:013",
        }
        normalized = normalize_evidence_record(raw)
        record = EvidenceRecord.from_dict(normalized)

        self.assertEqual(record.source_entity, "麻黄")
        self.assertEqual(record.target_entity, "发汗")
        self.assertEqual(record.confidence, 0.85)
        self.assertEqual(record.evidence_grade, "moderate")
        self.assertIsNotNone(record.evidence_id)

    def test_to_dict_has_provenance(self):
        from src.research.evidence_contract import EvidenceRecord

        record = EvidenceRecord(
            evidence_id="test:001",
            source_entity="麻黄",
            target_entity="发汗",
            confidence=0.9,
        )
        d = record.to_dict()
        self.assertIn("provenance", d)
        self.assertIsInstance(d["provenance"], dict)
        self.assertEqual(d["evidence_id"], "test:001")


class TestEvidenceClaim(unittest.TestCase):
    def test_from_dict_round_trip(self):
        from src.research.evidence_contract import EvidenceClaim

        data = {
            "claim_id": "claim:001",
            "source_entity": "麻黄",
            "target_entity": "发汗",
            "relation_type": "功效",
            "confidence": 0.88,
            "support_count": 3,
            "evidence_ids": ["ev:1", "ev:2", "ev:3"],
            "review_status": "pending",
            "needs_manual_review": True,
            "review_reasons": ["低置信度"],
        }
        claim = EvidenceClaim.from_dict(data)
        self.assertEqual(claim.claim_id, "claim:001")
        self.assertEqual(claim.support_count, 3)
        self.assertTrue(claim.needs_manual_review)
        self.assertEqual(len(claim.evidence_ids), 3)

        d = claim.to_dict()
        self.assertEqual(d["claim_id"], "claim:001")

    def test_defaults(self):
        from src.research.evidence_contract import EvidenceClaim

        claim = EvidenceClaim()
        self.assertEqual(claim.confidence, 0.0)
        self.assertFalse(claim.needs_manual_review)
        self.assertEqual(claim.evidence_ids, [])


class TestEvidenceGradeSummary(unittest.TestCase):
    def test_from_dict(self):
        from src.research.evidence_contract import EvidenceGradeSummary

        data = {
            "overall_grade": "moderate",
            "overall_score": 0.72,
            "study_count": 5,
            "factor_averages": {"design": 0.8, "consistency": 0.65},
            "bias_risk_distribution": {"low": 3, "moderate": 2},
            "summary": ["综合证据质量中等"],
        }
        gs = EvidenceGradeSummary.from_dict(data)
        self.assertEqual(gs.overall_grade, "moderate")
        self.assertEqual(gs.overall_score, 0.72)
        self.assertEqual(gs.study_count, 5)
        self.assertEqual(len(gs.summary), 1)


class TestEvidenceEnvelope(unittest.TestCase):
    def _build_sample_protocol(self) -> Dict[str, Any]:
        from src.research.evidence_contract import build_evidence_protocol

        reasoning = {
            "evidence_records": [
                {
                    "source_entity": "麻黄",
                    "target_entity": "发汗",
                    "relation_type": "功效",
                    "confidence": 0.85,
                    "excerpt": "辛温发汗",
                    "title": "本草纲目",
                    "source_type": "classic_text",
                    "source_ref": "bencao:013",
                },
                {
                    "source_entity": "麻黄",
                    "target_entity": "平喘",
                    "relation_type": "功效",
                    "confidence": 0.78,
                    "excerpt": "宣肺平喘",
                    "title": "伤寒论",
                    "source_type": "classic_text",
                    "source_ref": "shanghanlun:001",
                },
            ],
            "entity_relationships": [
                {
                    "source_entity": "麻黄",
                    "target_entity": "发汗",
                    "relation_type": "功效",
                    "confidence": 0.85,
                    "evidence_ids": [],
                }
            ],
        }
        return build_evidence_protocol(reasoning)

    def test_from_protocol_round_trip(self):
        from src.research.evidence_contract import CONTRACT_VERSION, EvidenceEnvelope

        protocol = self._build_sample_protocol()
        self.assertIn("contract_version", protocol)

        envelope = EvidenceEnvelope.from_protocol(protocol)
        self.assertEqual(envelope.contract_version, CONTRACT_VERSION)
        self.assertEqual(envelope.record_count, 2)
        self.assertEqual(envelope.claim_count, 1)
        self.assertGreaterEqual(envelope.citation_count, 0)

        # Round-trip: to_dict should be compatible with original protocol keys
        d = envelope.to_dict()
        self.assertEqual(d["contract_version"], CONTRACT_VERSION)
        self.assertEqual(len(d["evidence_records"]), 2)
        self.assertEqual(len(d["claims"]), 1)
        self.assertIn("summary", d)
        self.assertIn("contract", d)

    def test_from_dict_alias(self):
        from src.research.evidence_contract import EvidenceEnvelope

        protocol = self._build_sample_protocol()
        env1 = EvidenceEnvelope.from_dict(protocol)
        env2 = EvidenceEnvelope.from_protocol(protocol)
        self.assertEqual(env1.record_count, env2.record_count)

    def test_to_json(self):
        from src.research.evidence_contract import EvidenceEnvelope

        protocol = self._build_sample_protocol()
        envelope = EvidenceEnvelope.from_protocol(protocol)
        json_str = envelope.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["contract_version"], "evidence-claim-v2")
        self.assertIsInstance(parsed["evidence_records"], list)

    def test_empty_envelope(self):
        from src.research.evidence_contract import EvidenceEnvelope

        envelope = EvidenceEnvelope()
        self.assertEqual(envelope.record_count, 0)
        self.assertEqual(envelope.claim_count, 0)
        self.assertEqual(envelope.citation_count, 0)
        self.assertEqual(envelope.linked_claim_count, 0)
        d = envelope.to_dict()
        self.assertEqual(d["contract_version"], "evidence-claim-v2")

    def test_linked_claim_count(self):
        from src.research.evidence_contract import EvidenceClaim, EvidenceEnvelope

        envelope = EvidenceEnvelope(
            claims=[
                EvidenceClaim(claim_id="c1", evidence_ids=["e1"]),
                EvidenceClaim(claim_id="c2", evidence_ids=[]),
                EvidenceClaim(claim_id="c3", evidence_ids=["e2", "e3"]),
            ]
        )
        self.assertEqual(envelope.linked_claim_count, 2)

    def test_grade_summary_preserved(self):
        from src.research.evidence_contract import EvidenceEnvelope

        protocol = {
            "contract_version": "evidence-claim-v2",
            "evidence_records": [],
            "claims": [],
            "evidence_grade_summary": {
                "overall_grade": "high",
                "overall_score": 0.88,
                "study_count": 10,
            },
        }
        envelope = EvidenceEnvelope.from_dict(protocol)
        self.assertEqual(envelope.grade_summary.overall_grade, "high")
        self.assertEqual(envelope.grade_summary.overall_score, 0.88)
        self.assertEqual(envelope.grade_summary.study_count, 10)


class TestContractVersionConstant(unittest.TestCase):
    def test_contract_version_is_v2(self):
        from src.research.evidence_contract import CONTRACT_VERSION

        self.assertEqual(CONTRACT_VERSION, "evidence-claim-v2")

    def test_build_evidence_protocol_uses_constant(self):
        """build_evidence_protocol should use CONTRACT_VERSION constant."""
        from src.research.evidence_contract import (
            CONTRACT_VERSION,
            build_evidence_protocol,
        )

        protocol = build_evidence_protocol(
            {"evidence_records": [{"source_entity": "A", "target_entity": "B"}]}
        )
        if protocol:
            self.assertEqual(protocol["contract_version"], CONTRACT_VERSION)


class TestEvidenceProtocolCache(unittest.TestCase):
    def test_build_evidence_protocol_uses_layered_cache(self):
        from src.research.evidence_contract import (
            _build_evidence_protocol_uncached,
            build_evidence_protocol,
        )

        reasoning = {
            "evidence_records": [
                {
                    "source_entity": "黄芪",
                    "target_entity": "补气",
                    "relation_type": "功效",
                    "confidence": 0.91,
                    "excerpt": "黄芪补气升阳",
                    "title": "本草备要",
                    "source_type": "classic_text",
                    "source_ref": "bencao:001",
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = LayeredTaskCache(
                settings={
                    "enabled": True,
                    "cache_dir": tmp_dir,
                    "prompt": {"enabled": False},
                    "evidence": {"enabled": True, "namespace": "evidence", "ttl_seconds": None},
                    "artifact": {"enabled": False},
                }
            )
            try:
                with patch("src.research.evidence_contract.get_layered_task_cache", return_value=cache):
                    with patch(
                        "src.research.evidence_contract._build_evidence_protocol_uncached",
                        wraps=_build_evidence_protocol_uncached,
                    ) as wrapped:
                        first = build_evidence_protocol(reasoning)
                        second = build_evidence_protocol(reasoning)
            finally:
                cache.close()

        self.assertEqual(first, second)
        self.assertEqual(wrapped.call_count, 1)


if __name__ == "__main__":
    unittest.main()
