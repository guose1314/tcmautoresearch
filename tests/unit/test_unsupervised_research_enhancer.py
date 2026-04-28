from __future__ import annotations

import unittest

from src.analysis.unsupervised_research_enhancer import (
    apply_unsupervised_annotations,
    build_unsupervised_research_view,
)


class TestUnsupervisedResearchEnhancer(unittest.TestCase):
    def test_build_unsupervised_research_view_extracts_topics_and_bridges(self):
        entities = [
            {"name": "麻黄汤", "type": "formula", "confidence": 0.9},
            {"name": "麻黄", "type": "herb", "confidence": 0.9},
            {"name": "桂枝", "type": "herb", "confidence": 0.9},
            {"name": "发热", "type": "syndrome", "confidence": 0.8},
            {"name": "平喘", "type": "efficacy", "confidence": 0.8},
            {"name": "桂枝汤", "type": "formula", "confidence": 0.9},
            {"name": "白芍", "type": "herb", "confidence": 0.8},
            {"name": "汗出", "type": "syndrome", "confidence": 0.8},
        ]
        graph_data = {
            "edges": [
                {"source": "麻黄汤", "target": "麻黄", "relation": "contains"},
                {"source": "麻黄汤", "target": "桂枝", "relation": "contains"},
                {"source": "麻黄汤", "target": "发热", "relation": "treats"},
                {"source": "麻黄汤", "target": "平喘", "relation": "has_efficacy"},
                {"source": "桂枝汤", "target": "桂枝", "relation": "contains"},
                {"source": "桂枝汤", "target": "白芍", "relation": "contains"},
                {"source": "桂枝汤", "target": "汗出", "relation": "treats"},
            ]
        }

        result = build_unsupervised_research_view(
            "麻黄汤与桂枝汤均用于外感证候治疗。",
            entities,
            graph_data,
            source_file="test-doc.txt",
        )

        self.assertGreaterEqual(result["document_signature"]["topic_count"], 1)
        self.assertIn("community_topics", result)
        self.assertTrue(result["community_topics"])
        self.assertIn("桂枝", result["entity_annotations"])
        self.assertIn("neo4j_projection", result)
        self.assertTrue(result["neo4j_projection"]["nodes"])
        self.assertTrue(result["neo4j_projection"]["edges"])
        self.assertTrue(any(item["name"] == "桂枝" for item in result["bridge_entities"]))
        self.assertTrue(result["literature_alignment"])

    def test_apply_unsupervised_annotations_embeds_metadata(self):
        entities = [
            {"name": "麻黄汤", "type": "formula"},
            {"name": "桂枝", "type": "herb"},
        ]
        graph_data = {
            "edges": [
                {"source": "麻黄汤", "target": "桂枝", "relation": "contains"},
            ]
        }
        view = build_unsupervised_research_view(
            "麻黄汤含桂枝。",
            entities,
            graph_data,
            source_file="mini-doc.txt",
        )

        enriched_entities, enriched_graph = apply_unsupervised_annotations(entities, graph_data, view)

        self.assertIn("unsupervised_learning", enriched_entities[0])
        self.assertIn("metadata", enriched_entities[0])
        self.assertIn("unsupervised_learning", enriched_entities[0]["metadata"])
        self.assertIn("attributes", enriched_graph["edges"][0])


if __name__ == "__main__":
    unittest.main()