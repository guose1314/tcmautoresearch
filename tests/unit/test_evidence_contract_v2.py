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


# ═══════════════════════════════════════════════════════════════════════
# Phase F-1: phase_origin + build_phase_evidence_protocol tests
# ═══════════════════════════════════════════════════════════════════════


class TestEvidenceEnvelopePhaseOrigin(unittest.TestCase):
    """phase_origin 字段序列化与反序列化。"""

    def test_default_phase_origin_is_empty(self):
        from src.research.evidence_contract import EvidenceEnvelope
        env = EvidenceEnvelope()
        self.assertEqual(env.phase_origin, "")

    def test_phase_origin_round_trip(self):
        from src.research.evidence_contract import EvidenceEnvelope
        env = EvidenceEnvelope(phase_origin="observe")
        d = env.to_dict()
        self.assertEqual(d["phase_origin"], "observe")
        restored = EvidenceEnvelope.from_dict(d)
        self.assertEqual(restored.phase_origin, "observe")

    def test_from_dict_missing_phase_origin_defaults_empty(self):
        from src.research.evidence_contract import CONTRACT_VERSION, EvidenceEnvelope
        d = {"contract_version": CONTRACT_VERSION}
        env = EvidenceEnvelope.from_dict(d)
        self.assertEqual(env.phase_origin, "")

    def test_to_dict_includes_phase_origin_key(self):
        from src.research.evidence_contract import EvidenceEnvelope
        env = EvidenceEnvelope(phase_origin="analyze")
        self.assertIn("phase_origin", env.to_dict())


class TestBuildPhaseEvidenceProtocol(unittest.TestCase):
    """build_phase_evidence_protocol 轻量构建器。"""

    def test_returns_dict(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        self.assertIsInstance(build_phase_evidence_protocol("observe"), dict)

    def test_contract_version(self):
        from src.research.evidence_contract import (
            CONTRACT_VERSION,
            build_phase_evidence_protocol,
        )
        self.assertEqual(build_phase_evidence_protocol("observe")["contract_version"], CONTRACT_VERSION)

    def test_phase_origin_set(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        self.assertEqual(build_phase_evidence_protocol("hypothesis")["phase_origin"], "hypothesis")

    def test_empty_records_and_claims(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        r = build_phase_evidence_protocol("observe")
        self.assertIsInstance(r["evidence_records"], list)
        self.assertIsInstance(r["claims"], list)

    def test_evidence_grade_in_summary(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        r = build_phase_evidence_protocol("observe", evidence_grade="preliminary")
        self.assertIn("overall_grade", r["evidence_grade_summary"])

    def test_with_evidence_records(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        records = [{"content": "桂枝汤主治", "source_type": "classical_text"}]
        r = build_phase_evidence_protocol("observe", evidence_records=records)
        self.assertGreaterEqual(len(r["evidence_records"]), 1)

    def test_with_claims(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        claims = [{"claim_text": "桂枝解表", "claim_type": "hypothesis"}]
        r = build_phase_evidence_protocol("hypothesis", claims=claims)
        self.assertGreaterEqual(len(r["claims"]), 1)

    def test_citation_count_type(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        self.assertIsInstance(build_phase_evidence_protocol("observe")["citation_count"], int)

    def test_summary_dict(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        self.assertIsInstance(build_phase_evidence_protocol("observe")["summary"], dict)

    def test_evidence_summary_passthrough(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        es = {"phase": "observe", "finding_count": 5}
        r = build_phase_evidence_protocol("observe", evidence_summary=es)
        self.assertEqual(r["evidence_summary"]["finding_count"], 5)

    def test_research_grade_empty_by_default(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        self.assertEqual(build_phase_evidence_protocol("observe")["research_grade"], {})

    def test_non_dict_records_skipped(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        records = ["not_a_dict", 42, {"content": "ok"}]
        r = build_phase_evidence_protocol("observe", evidence_records=records)
        self.assertGreaterEqual(len(r["evidence_records"]), 1)

    def test_non_dict_claims_skipped(self):
        from src.research.evidence_contract import build_phase_evidence_protocol
        claims = [None, "string", {"claim_text": "ok"}]
        r = build_phase_evidence_protocol("hypothesis", claims=claims)
        self.assertGreaterEqual(len(r["claims"]), 1)

    def test_all_phases(self):
        from src.research.evidence_contract import (
            CONTRACT_VERSION,
            build_phase_evidence_protocol,
        )
        for phase in ("observe", "hypothesis", "experiment_execution", "reflect", "analyze"):
            r = build_phase_evidence_protocol(phase)
            self.assertEqual(r["phase_origin"], phase)
            self.assertEqual(r["contract_version"], CONTRACT_VERSION)


class TestGetEvidenceProtocolHelper(unittest.TestCase):
    """phase_result.get_evidence_protocol 帮助函数。"""

    def test_returns_none_for_empty(self):
        from src.research.phase_result import get_evidence_protocol
        self.assertIsNone(get_evidence_protocol({}))

    def test_returns_none_for_non_dict(self):
        from src.research.phase_result import get_evidence_protocol
        self.assertIsNone(get_evidence_protocol("string"))

    def test_returns_protocol_from_results(self):
        from src.research.evidence_contract import CONTRACT_VERSION
        from src.research.phase_result import get_evidence_protocol
        proto = {"contract_version": CONTRACT_VERSION, "phase_origin": "observe"}
        payload = {"results": {"evidence_protocol": proto}}
        self.assertEqual(get_evidence_protocol(payload), proto)

    def test_returns_none_if_no_contract_version(self):
        from src.research.phase_result import get_evidence_protocol
        proto = {"phase_origin": "observe"}
        payload = {"results": {"evidence_protocol": proto}}
        self.assertIsNone(get_evidence_protocol(payload))


if __name__ == "__main__":
    unittest.main()
