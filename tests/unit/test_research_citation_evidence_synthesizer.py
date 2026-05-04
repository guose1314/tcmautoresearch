from __future__ import annotations

import unittest

from src.research.evidence.citation_evidence_synthesizer import (
    CitationEvidenceSynthesizer,
)


class TestResearchCitationEvidenceSynthesizer(unittest.TestCase):
    def test_relation_with_text_provenance_becomes_formal_conclusion(self) -> None:
        package = (
            CitationEvidenceSynthesizer()
            .synthesize(
                {"source": "麻仁", "relation_type": "润肠", "target": "便秘"},
                text_segments=[
                    {
                        "segment_id": "seg-1",
                        "quote_text": "麻仁润肠通便，可用于便秘证。",
                        "confidence": 0.88,
                    }
                ],
            )
            .to_dict()
        )

        self.assertEqual(package["conclusion_status"], "formal_conclusion")
        self.assertEqual(package["evidence_status"], "supported")
        self.assertEqual(len(package["supporting_evidence"]), 1)
        self.assertEqual(package["missing_evidence"], [])

    def test_rejected_expert_feedback_downgrades_to_candidate_observation(self) -> None:
        package = (
            CitationEvidenceSynthesizer()
            .synthesize(
                {"source": "麻仁", "relation_type": "润肠", "target": "便秘"},
                expert_feedback=[
                    {
                        "id": "review-1",
                        "review_status": "rejected",
                        "body": "专家复核认为麻仁与便秘的关系证据不足。",
                    }
                ],
            )
            .to_dict()
        )

        self.assertEqual(package["conclusion_status"], "candidate_observation")
        self.assertEqual(package["evidence_status"], "contested")
        self.assertEqual(len(package["contradicting_evidence"]), 1)

    def test_missing_evidence_records_missing_bucket(self) -> None:
        package = (
            CitationEvidenceSynthesizer()
            .synthesize({"claim_id": "cl-1", "claim_text": "桂枝调和营卫"})
            .to_dict()
        )

        self.assertEqual(package["conclusion_status"], "candidate_observation")
        self.assertEqual(package["evidence_status"], "insufficient")
        self.assertEqual(
            package["missing_evidence"][0]["reason"], "no_supporting_evidence"
        )


if __name__ == "__main__":
    unittest.main()
