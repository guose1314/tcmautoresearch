from __future__ import annotations

import unittest

from src.quality.citation_grounding_evaluator import (
    evaluate_citation_grounding,
    extract_citation_keys,
    extract_markdown_claim_blocks,
)


class CitationGroundingEvaluatorTest(unittest.TestCase):
    def test_complete_support_uses_publish_result_grounding_record(self) -> None:
        publish_result = {
            "report_markdown": (
                "[claim:claim-strong] 桂枝汤条文有原文、证据声明与版本 witness 支持。"
                "[@shanghanlun; @song_witness]"
            ),
            "citation_grounding_records": [
                {
                    "claim_id": "claim-strong",
                    "paragraph_id": "publish:claim:1",
                    "citation_keys": ["shanghanlun", "song_witness"],
                    "evidence_claim_ids": ["claim-strong"],
                    "witness_keys": ["song_witness"],
                    "support_level": "strong",
                    "uncertainty_note": "fully grounded",
                }
            ],
        }

        summary = evaluate_citation_grounding(publish_result=publish_result)

        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["claim_block_count"], 1)
        self.assertEqual(summary["supported_count"], 1)
        self.assertEqual(summary["unsupported_count"], 0)
        self.assertEqual(summary["strong_count"], 1)
        self.assertEqual(summary["citation_grounding_support_rate"], 1.0)
        self.assertEqual(summary["citation_keys"], ["shanghanlun", "song_witness"])

    def test_weak_support_when_markdown_claim_has_citation_only(self) -> None:
        markdown = "[claim:claim-weak] 麻仁润肠结论只给出引文键。[@bencao_maren]"

        summary = evaluate_citation_grounding(report_markdown=markdown)

        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["supported_count"], 1)
        self.assertEqual(summary["unsupported_count"], 0)
        self.assertEqual(summary["weak_count"], 1)
        self.assertEqual(
            summary["grounding_records"][0]["citation_keys"],
            ["bencao_maren"],
        )

    def test_unsupported_when_markdown_claim_has_no_citation(self) -> None:
        markdown = "[claim:claim-uncited] 湿病证治综述给出了无引用结论。"

        summary = evaluate_citation_grounding(report_markdown=markdown)

        self.assertEqual(summary["record_count"], 1)
        self.assertEqual(summary["supported_count"], 0)
        self.assertEqual(summary["unsupported_count"], 1)
        self.assertEqual(summary["uncited_claim_count"], 1)
        self.assertEqual(summary["citation_grounding_support_rate"], 0.0)
        self.assertEqual(summary["unsupported_claim_ids"], ["claim-uncited"])

    def test_extractors_accept_common_markdown_citation_forms(self) -> None:
        text = "[claim:claim-mixed] 引用支持。[@a; @b] [cite:c,d] citation_keys: e, f"

        self.assertEqual(extract_citation_keys(text), ["a", "b", "c", "d", "e", "f"])
        blocks = extract_markdown_claim_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].claim_id, "claim-mixed")


if __name__ == "__main__":
    unittest.main()
