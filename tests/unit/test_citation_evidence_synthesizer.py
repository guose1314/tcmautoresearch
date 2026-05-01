from __future__ import annotations

import unittest

from src.generation.citation_evidence_synthesizer import (
    SUPPORT_LEVEL_STRONG,
    SUPPORT_LEVEL_UNSUPPORTED,
    SUPPORT_LEVEL_WEAK,
    CitationEvidenceSynthesizer,
    summarize_citation_grounding,
)


class TestCitationEvidenceSynthesizer(unittest.TestCase):
    def test_evidence_claim_with_citation_and_witness_is_strong(self):
        records = CitationEvidenceSynthesizer().synthesize(
            evidence_protocol={
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "source_entity": "桂枝汤",
                        "target_entity": "营卫不和",
                        "relation_type": "treats",
                        "evidence_ids": ["ev-1"],
                    }
                ],
                "evidence_records": [
                    {
                        "evidence_id": "ev-1",
                        "title": "伤寒论",
                        "source_ref": "urn:shanghanlun",
                        "witness_key": "witness-1",
                    }
                ],
            },
            citation_records=[
                {
                    "title": "伤寒论",
                    "source_ref": "urn:shanghanlun",
                    "source_type": "classical_text",
                }
            ],
            observe_philology={
                "textual_criticism": {
                    "verdicts": [{"witness_key": "witness-1"}],
                }
            },
            graph_rag_context={
                "traces": {
                    "EvidenceClaim": [
                        {
                            "id": "claim-1",
                            "traceability": {"node_ids": ["claim-1"]},
                        }
                    ],
                    "VersionWitness": [
                        {
                            "id": "witness-1",
                            "traceability": {"node_ids": ["witness-1"]},
                        }
                    ],
                    "CitationRecord": [
                        {
                            "id": "urn:shanghanlun",
                            "source_ref": "urn:shanghanlun",
                        }
                    ],
                }
            },
        )

        self.assertEqual(len(records), 1)
        payload = records[0].to_dict()
        self.assertEqual(payload["support_level"], SUPPORT_LEVEL_STRONG)
        self.assertIn("claim-1", payload["evidence_claim_ids"])
        self.assertIn("urn:shanghanlun", payload["citation_keys"])
        self.assertIn("witness-1", payload["witness_keys"])

    def test_citation_record_without_claim_is_weak(self):
        records = CitationEvidenceSynthesizer().synthesize(
            evidence_protocol={},
            citation_records=[{"title": "本草纲目", "source_ref": "urn:bencao"}],
            observe_philology={},
            graph_rag_context={},
        )

        self.assertEqual(len(records), 1)
        payload = records[0].to_dict()
        self.assertEqual(payload["support_level"], SUPPORT_LEVEL_WEAK)
        self.assertEqual(payload["citation_keys"], ["urn:bencao"])

    def test_empty_inputs_return_unsupported_record(self):
        records = CitationEvidenceSynthesizer().synthesize(
            evidence_protocol={},
            citation_records=[],
            observe_philology={},
            graph_rag_context={},
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].support_level, SUPPORT_LEVEL_UNSUPPORTED)
        summary = summarize_citation_grounding(records)
        self.assertEqual(summary["unsupported_count"], 1)


if __name__ == "__main__":
    unittest.main()
