from __future__ import annotations

import unittest

from src.research.evaluation.citation_grounding_evaluator import (
    CitationGroundingEvaluator,
    evaluate_citation_grounding,
)


class ResearchCitationGroundingEvaluatorTest(unittest.TestCase):
    def test_text_segment_provenance_supports_entities_relations_and_claims(
        self,
    ) -> None:
        provenance = {
            "document_id": "doc-gzt",
            "segment_id": "seg_000001",
            "char_start": 0,
            "char_end": 12,
            "line_start": 1,
            "line_end": 1,
            "quote_text": "桂枝汤主治营卫不和。",
            "normalization_hash": "a" * 64,
        }
        summary = evaluate_citation_grounding(
            llm_output={
                "entities": [
                    {"name": "桂枝汤", "type": "formula", "provenance": [provenance]}
                ],
                "relationships": [
                    {
                        "source": "桂枝汤",
                        "target": "营卫不和",
                        "relation": "treats",
                        "provenance": [provenance],
                    }
                ],
                "claims": [
                    {
                        "claim_id": "claim-gzt",
                        "claim_text": "桂枝汤主治营卫不和。",
                        "provenance": [provenance],
                    }
                ],
            },
            text_segments=[provenance],
        )

        self.assertEqual(summary["grounding_score"], 1.0)
        self.assertTrue(summary["formal_conclusion_allowed"])
        self.assertEqual(summary["unsupported_claims"], [])

    def test_unsupported_claim_and_bad_citation_are_reported(self) -> None:
        summary = CitationGroundingEvaluator(threshold=0.8).evaluate(
            llm_output={
                "claims": [
                    {
                        "claim_id": "claim-hallucinated",
                        "claim_text": "桂枝汤可直接治疗高血压。",
                        "citation_keys": ["unknown_source"],
                    }
                ]
            },
            citation_records=[{"citation_key": "shanghanlun_taiyang_12"}],
        )

        self.assertEqual(summary["grounding_score"], 0.0)
        self.assertFalse(summary["formal_conclusion_allowed"])
        self.assertEqual(
            summary["unsupported_claims"][0]["asset_id"], "claim-hallucinated"
        )
        self.assertTrue(summary["citation_mismatch"])

    def test_graph_reviewed_evidence_supports_claim_by_claim_id(self) -> None:
        summary = evaluate_citation_grounding(
            llm_output={
                "claims": [
                    {
                        "claim_id": "claim-graph",
                        "claim_text": "GraphRAG 支持桂枝汤方证关系。",
                        "citation_keys": ["claim-graph"],
                    }
                ]
            },
            graph_rag_context={
                "traces": {
                    "EvidenceClaim": [
                        {
                            "id": "claim-graph",
                            "body": "GraphRAG 支持桂枝汤方证关系。",
                            "review_status": "accepted",
                        }
                    ]
                }
            },
            citation_records=[{"citation_key": "claim-graph"}],
        )

        self.assertEqual(summary["grounding_score"], 1.0)
        self.assertEqual(summary["citation_mismatch"], [])


if __name__ == "__main__":
    unittest.main()
