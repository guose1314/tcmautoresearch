"""tests/test_ontology_manager.py - 本体管理器约束测试"""

import unittest

from src.knowledge.ontology_manager import OntologyManager


class TestOntologyManager(unittest.TestCase):
    def setUp(self):
        self.ontology = OntologyManager()

    def test_normalize_node_type_alias(self):
        self.assertEqual(self.ontology.normalize_node_type("formulas"), "formula")
        self.assertEqual(self.ontology.normalize_node_type("unknown"), "generic")

    def test_make_and_parse_node_id(self):
        node_id = self.ontology.make_node_id("herbs", "人参")
        self.assertEqual(node_id, "herb:人参")
        node_type, name = self.ontology.parse_node_id(node_id)
        self.assertEqual(node_type, "herb")
        self.assertEqual(name, "人参")

    def test_validate_relationship_with_constraints(self):
        self.assertTrue(self.ontology.validate_relationship("treats", "formula", "syndrome"))
        self.assertFalse(self.ontology.validate_relationship("treats", "formula", "herb"))

    def test_validate_embedding_item_type(self):
        self.assertTrue(self.ontology.validate_embedding_item_type("formula"))
        self.assertFalse(self.ontology.validate_embedding_item_type("efficacy"))


if __name__ == "__main__":
    unittest.main()