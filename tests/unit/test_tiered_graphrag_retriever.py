from __future__ import annotations

import unittest
from typing import Any, Dict

from src.knowledge.graphrag.tiered_retriever import TieredGraphRAGRetriever


class _FakeBaseRetriever:
    def retrieve(self, scope: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        asset_type = kwargs.get("asset_type") or "entity_relation"
        payloads = {
            "catalog": {
                "body": "文献层：《伤寒论》相关目录与版本线索",
                "citations": [{"type": "Catalog", "id": "cat-1", "confidence": 0.61}],
                "traceability": {"node_ids": ["cat-1"], "relationship_ids": []},
            },
            "evidence": {
                "body": "片段层：麻仁润肠通便，可用于便秘证。",
                "citations": [{"type": "Evidence", "id": "ev-1", "confidence": 0.74}],
                "traceability": {"node_ids": ["ev-1"], "relationship_ids": ["rel-ev"]},
            },
            "entity_relation": {
                "body": "实体关系层：(Herb:麻仁)-[TREATS]->(Symptom:便秘)",
                "citations": [{"type": "Entity", "id": "麻仁", "confidence": 0.82}],
                "traceability": {"node_ids": ["麻仁"], "relationship_ids": ["rel-kg"]},
            },
            "claim": {
                "body": "专家审核 insight 层：麻仁润肠证据已复核。",
                "citations": [
                    {
                        "type": "EvidenceClaim",
                        "id": "cl-1",
                        "review_status": "accepted",
                        "confidence": 0.95,
                    }
                ],
                "traceability": {"node_ids": ["cl-1"], "relationship_ids": ["rel-cl"]},
            },
        }
        result = payloads[asset_type]
        return {"scope": scope, "asset_type": asset_type, **result, "token_count": 10}


class TestTieredGraphRAGRetriever(unittest.TestCase):
    def test_returns_four_tiers_with_persistable_trace(self) -> None:
        result = (
            TieredGraphRAGRetriever(base_retriever=_FakeBaseRetriever())
            .retrieve("麻仁润肠", entity_ids=["麻仁"], cycle_id="cycle-1")
            .to_dict()
        )

        tiers = [item["tier"] for item in result["items"]]
        self.assertEqual(
            tiers, ["literature", "segment", "entity_relation", "expert_insight"]
        )
        for item in result["items"]:
            self.assertIn("tier", item)
            self.assertIn("source", item)
            self.assertIn("confidence", item)
            self.assertIn("expert_reviewed", item)
        self.assertTrue(result["traceability"]["persistable"])
        self.assertIn("rel-cl", result["traceability"]["relationship_ids"])

    def test_prompt_body_prioritizes_reviewed_and_high_confidence_evidence(
        self,
    ) -> None:
        result = (
            TieredGraphRAGRetriever(base_retriever=_FakeBaseRetriever())
            .retrieve("麻仁润肠", entity_ids=["麻仁"], cycle_id="cycle-1")
            .to_dict()
        )

        first_line = result["body"].splitlines()[0]
        self.assertIn("[expert_insight]", first_line)
        self.assertLess(
            result["body"].find("[entity_relation]"), result["body"].find("[segment]")
        )


if __name__ == "__main__":
    unittest.main()
