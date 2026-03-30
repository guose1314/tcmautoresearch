"""tests/test_relation_extractor.py — 独立关系抽取模块测试"""

import unittest

from src.extraction.relation_extractor import RelationExtractor
from src.semantic_modeling.semantic_graph_builder import SemanticGraphBuilder


class TestRelationExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = RelationExtractor()

    def _sample_entities(self):
        return [
            {"type": "formula", "name": "四君子汤", "confidence": 0.95},
            {"type": "herb", "name": "人参", "confidence": 0.9},
            {"type": "herb", "name": "白术", "confidence": 0.9},
            {"type": "syndrome", "name": "脾虚证", "confidence": 0.88},
        ]

    def test_extract_returns_edges(self):
        edges = self.extractor.extract(self._sample_entities())
        self.assertGreater(len(edges), 0)
        self.assertIn("source", edges[0])
        self.assertIn("target", edges[0])
        self.assertIn("attributes", edges[0])

    def test_extract_composition_relations(self):
        edges = self.extractor.extract(self._sample_entities())
        rel_types = [e["attributes"]["relationship_type"] for e in edges]
        self.assertIn("sovereign", rel_types)
        self.assertIn("minister", rel_types)

    def test_extract_efficacy_relations(self):
        entities = [
            {"type": "herb", "name": "人参", "confidence": 0.9},
        ]
        edges = self.extractor.extract(entities)
        rel_types = [e["attributes"]["relationship_type"] for e in edges]
        self.assertIn("efficacy", rel_types)

    def test_extract_treats_relations(self):
        edges = self.extractor.extract(self._sample_entities())
        treats_edges = [e for e in edges if e["attributes"]["relationship_type"] == "treats"]
        self.assertGreaterEqual(len(treats_edges), 2)

    def test_extract_ignores_non_dict_items(self):
        entities = self._sample_entities() + ["bad-item", 123, None]
        edges = self.extractor.extract(entities)
        self.assertGreater(len(edges), 0)

    def test_relationship_statistics(self):
        self.extractor.extract(self._sample_entities())
        stats = self.extractor.relationship_statistics()
        self.assertIn("treats", stats)
        self.assertIn("count", stats["treats"])
        self.assertIn("description", stats["treats"])


class TestSemanticGraphBuilderDecoupling(unittest.TestCase):
    def test_builder_uses_relation_extractor_compatibly(self):
        builder = SemanticGraphBuilder()
        self.assertTrue(builder.initialize())
        result = builder.execute(
            {
                "entities": [
                    {"type": "formula", "name": "四君子汤", "confidence": 0.95},
                    {"type": "herb", "name": "人参", "confidence": 0.9},
                    {"type": "herb", "name": "白术", "confidence": 0.9},
                    {"type": "syndrome", "name": "脾虚证", "confidence": 0.88},
                ]
            }
        )
        stats = result["graph_statistics"]
        self.assertGreater(stats["edges_count"], 0)
        self.assertIn("relationships_by_type", stats)
        self.assertIn("treats", stats["relationships_by_type"])
        builder.cleanup()


if __name__ == "__main__":
    unittest.main()
