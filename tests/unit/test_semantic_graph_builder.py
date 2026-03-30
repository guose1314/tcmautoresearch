import unittest
from unittest.mock import patch

from src.semantic_modeling.semantic_graph_builder import SemanticGraphBuilder


class TestSemanticGraphBuilderRefactor(unittest.TestCase):
    def setUp(self):
        self.builder = SemanticGraphBuilder()
        self.assertTrue(self.builder.initialize())

    def tearDown(self):
        self.builder.cleanup()

    def test_validate_entities_rejects_non_list(self):
        with self.assertRaises(ValueError):
            self.builder._validate_entities({"entities": "not-a-list"})

    def test_validate_entities_filters_non_dict_items(self):
        entities = self.builder._validate_entities(
            {"entities": [{"type": "formula", "name": "四君子汤"}, "bad", 123, None]}
        )
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["name"], "四君子汤")

    def test_collect_advanced_formula_analyses_uses_integrated_then_fallback(self):
        formulas = [{"type": "formula", "name": "A"}, {"type": "formula", "name": "B"}]
        herbs = ["人参"]
        research_perspectives = {
            "A": {
                "integrated": {
                    "network_pharmacology": {"v": 1},
                    "supramolecular_physicochemical": {"v": 2},
                    "knowledge_archaeology": {"v": 3},
                    "complexity_dynamics": {"v": 4},
                }
            }
        }

        with patch.object(self.builder, "_analyze_network_systems", return_value={"B": {"fb": "n"}}) as p1, patch.object(
            self.builder, "_analyze_supramolecular_physicochemistry", return_value={"B": {"fb": "s"}}
        ) as p2, patch.object(self.builder, "_analyze_knowledge_archaeology", return_value={"B": {"fb": "k"}}) as p3, patch.object(
            self.builder, "_analyze_complexity_dynamics", return_value={"B": {"fb": "c"}}
        ) as p4:
            out = self.builder._collect_advanced_formula_analyses(formulas, herbs, research_perspectives)

        self.assertEqual(out["network_pharmacology_systems_biology"]["A"], {"v": 1})
        self.assertEqual(out["supramolecular_physicochemistry"]["A"], {"v": 2})
        self.assertEqual(out["knowledge_archaeology"]["A"], {"v": 3})
        self.assertEqual(out["complexity_nonlinear_dynamics"]["A"], {"v": 4})
        self.assertIn("B", out["network_pharmacology_systems_biology"])
        self.assertIn("B", out["supramolecular_physicochemistry"])
        self.assertIn("B", out["knowledge_archaeology"])
        self.assertIn("B", out["complexity_nonlinear_dynamics"])
        p1.assert_called_once()
        p2.assert_called_once()
        p3.assert_called_once()
        p4.assert_called_once()

    def test_execute_accepts_none_entities_as_empty(self):
        with patch.object(self.builder, "_generate_research_perspectives", return_value={}), patch.object(
            self.builder, "_analyze_herb_properties", return_value={}
        ), patch.object(self.builder, "_analyze_formula_similarities", return_value=[]), patch.object(
            self.builder, "_collect_pharmacology_data", return_value={}
        ), patch.object(self.builder, "_collect_advanced_formula_analyses", return_value={
            "network_pharmacology_systems_biology": {},
            "supramolecular_physicochemistry": {},
            "knowledge_archaeology": {},
            "complexity_nonlinear_dynamics": {},
        }), patch("src.semantic_modeling.semantic_graph_builder.SummaryAnalysisEngine.analyze", return_value={}):
            out = self.builder.execute({"entities": None})

        self.assertIn("semantic_graph", out)
        self.assertEqual(out["graph_statistics"]["nodes_count"], 0)


if __name__ == "__main__":
    unittest.main()
