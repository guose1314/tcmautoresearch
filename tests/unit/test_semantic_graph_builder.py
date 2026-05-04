import tempfile
import unittest
from unittest.mock import patch

from src.analysis.semantic_graph import SemanticGraphBuilder, SemanticGraphService
from src.knowledge.embedding_service import SearchResult


class _StubEmbeddingService:
    def __init__(self, results):
        self._results = results

    def search_similar_formulas(
        self, query, top_k=5, min_score=0.0, exclude_formula_id=None
    ):
        del query, top_k, min_score, exclude_formula_id
        return list(self._results)


class _StubNeo4jDriver:
    def collect_formula_similarity_evidence(self, formula_name, similar_formula_name):
        return {
            "source": "neo4j",
            "shared_herbs": [
                {
                    "herb": "人参",
                    "formula_role": "sovereign",
                    "similar_formula_role": "minister",
                }
            ],
            "shared_syndromes": ["脾气虚证"],
            "direct_relationships": [
                {"relationship_type": "SIMILAR_TO", "properties": {"confidence": 0.92}}
            ],
            "evidence_score": 0.92,
        }


class _CountingEncoder:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = 0

    def encode(self, texts, normalize_embeddings=False, convert_to_numpy=True):
        del normalize_embeddings, convert_to_numpy
        self.calls += 1
        return [self.mapping[text] for text in texts]


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

        with (
            patch.object(
                self.builder,
                "_analyze_network_systems",
                return_value={"B": {"fb": "n"}},
            ) as p1,
            patch.object(
                self.builder,
                "_analyze_supramolecular_physicochemistry",
                return_value={"B": {"fb": "s"}},
            ) as p2,
            patch.object(
                self.builder,
                "_analyze_knowledge_archaeology",
                return_value={"B": {"fb": "k"}},
            ) as p3,
            patch.object(
                self.builder,
                "_analyze_complexity_dynamics",
                return_value={"B": {"fb": "c"}},
            ) as p4,
        ):
            out = self.builder._collect_advanced_formula_analyses(
                formulas, herbs, research_perspectives
            )

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
        with (
            patch.object(
                self.builder, "_generate_research_perspectives", return_value={}
            ),
            patch.object(self.builder, "_analyze_herb_properties", return_value={}),
            patch.object(
                self.builder, "_analyze_formula_similarities", return_value=[]
            ),
            patch.object(self.builder, "_collect_pharmacology_data", return_value={}),
            patch.object(
                self.builder,
                "_collect_advanced_formula_analyses",
                return_value={
                    "network_pharmacology_systems_biology": {},
                    "supramolecular_physicochemistry": {},
                    "knowledge_archaeology": {},
                    "complexity_nonlinear_dynamics": {},
                },
            ),
            patch(
                "src.semantic_modeling.semantic_graph_builder.SummaryAnalysisEngine.analyze",
                return_value={},
            ),
        ):
            out = self.builder.execute({"entities": None})

        self.assertIn("semantic_graph", out)
        self.assertEqual(out["graph_statistics"]["nodes_count"], 0)

    def test_execute_includes_rule_relation_quality_tiers(self):
        with (
            patch.object(
                self.builder, "_generate_research_perspectives", return_value={}
            ),
            patch.object(self.builder, "_analyze_herb_properties", return_value={}),
            patch.object(
                self.builder, "_analyze_formula_similarities", return_value=[]
            ),
            patch.object(self.builder, "_collect_pharmacology_data", return_value={}),
            patch.object(
                self.builder,
                "_collect_advanced_formula_analyses",
                return_value={
                    "network_pharmacology_systems_biology": {},
                    "supramolecular_physicochemistry": {},
                    "knowledge_archaeology": {},
                    "complexity_nonlinear_dynamics": {},
                },
            ),
            patch(
                "src.semantic_modeling.semantic_graph_builder.SummaryAnalysisEngine.analyze",
                return_value={},
            ),
        ):
            out = self.builder.execute(
                {
                    "raw_text": "桂枝汤主治营卫不和。",
                    "entities": [
                        {"type": "formula", "name": "桂枝汤", "position": 0},
                        {"type": "syndrome", "name": "营卫不和", "position": 6},
                    ],
                }
            )

        edges = out["semantic_graph"]["edges"]
        tier_counts = out["graph_statistics"]["relationships_by_type"]["quality_tiers"]
        self.assertGreaterEqual(sum(tier_counts.values()), 1)
        self.assertIn("rule_quality", edges[0]["attributes"])
        self.assertIn(
            edges[0]["attributes"]["rule_quality"]["tier"],
            {"strong_rule", "weak_rule", "candidate_rule", "rejected_rule"},
        )

    def test_generate_research_perspectives_adds_similar_formula_matches_with_graph_evidence(
        self,
    ):
        builder = SemanticGraphBuilder({"neo4j_driver": _StubNeo4jDriver()})
        self.assertTrue(builder.initialize())
        try:
            stub_service = _StubEmbeddingService(
                [
                    SearchResult(
                        item_id="六君子汤",
                        text="六君子汤",
                        item_type="formula",
                        score=0.91,
                        rank=1,
                        metadata={"name": "六君子汤"},
                    )
                ]
            )
            with patch.object(
                builder, "_get_formula_embedding_service", return_value=stub_service
            ):
                perspectives = builder._generate_research_perspectives(
                    [{"type": "formula", "name": "四君子汤"}]
                )

            integrated = perspectives["四君子汤"]["integrated"]
            self.assertIn("similar_formula_matches", integrated)
            self.assertEqual(
                integrated["similar_formula_matches"][0]["formula_name"], "六君子汤"
            )
            self.assertIn(
                "embedding",
                integrated["similar_formula_matches"][0]["retrieval_sources"],
            )
            self.assertEqual(
                integrated["similar_formula_matches"][0]["graph_evidence"][
                    "shared_syndromes"
                ],
                ["脾气虚证"],
            )
            self.assertEqual(
                integrated["similar_formula_matches"][0]["graph_evidence"]["source"],
                "neo4j+relationship_reasoning",
            )
        finally:
            builder.cleanup()

    def test_generate_research_perspectives_falls_back_to_relationship_reasoning_without_embedding_service(
        self,
    ):
        with patch.object(
            self.builder, "_get_formula_embedding_service", return_value=None
        ):
            perspectives = self.builder._generate_research_perspectives(
                [{"type": "formula", "name": "四君子汤"}]
            )

        integrated = perspectives["四君子汤"]["integrated"]
        self.assertIn("六君子汤", integrated["similar_formulas"])
        self.assertEqual(
            integrated["similar_formula_matches"][0]["retrieval_sources"],
            ["relationship_reasoning"],
        )
        self.assertEqual(
            integrated["similar_formula_matches"][0]["graph_evidence"]["source"],
            "relationship_reasoning",
        )
        self.assertGreater(
            integrated["similar_formula_matches"][0]["graph_evidence"][
                "shared_herb_count"
            ],
            0,
        )

    def test_build_local_formula_graph_evidence_merges_role_overlaps_and_comparison_herbs(
        self,
    ):
        with (
            patch(
                "src.analysis.semantic_graph.FormulaStructureAnalyzer.get_formula_composition",
                side_effect=[
                    {"sovereign": ["黄芪", "人参"], "minister": ["白术"]},
                    {"sovereign": ["黄芪"], "assistant": ["白术", "甘草"]},
                ],
            ),
            patch(
                "src.analysis.semantic_graph.FormulaComparator.compare_formulas",
                return_value={"common_herbs": ["黄芪", "白术", "茯苓"]},
            ),
        ):
            evidence = self.builder._build_local_formula_graph_evidence("方A", "方B")

        self.assertEqual(evidence["source"], "relationship_reasoning")
        self.assertEqual(evidence["shared_herb_count"], 3)
        self.assertEqual(len(evidence["role_overlaps"]), 2)
        self.assertIn(
            {
                "formula_role": "sovereign",
                "similar_formula_role": "sovereign",
                "herbs": ["黄芪"],
            },
            evidence["role_overlaps"],
        )
        self.assertIn(
            {
                "formula_role": "minister",
                "similar_formula_role": "assistant",
                "herbs": ["白术"],
            },
            evidence["role_overlaps"],
        )
        self.assertIn(
            {
                "herb": "茯苓",
                "formula_role": "unknown",
                "similar_formula_role": "unknown",
            },
            evidence["shared_herbs"],
        )
        self.assertGreater(evidence["evidence_score"], 0.0)

    def test_restarting_semantic_graph_builder_reuses_persisted_formula_index(self):
        catalog = [
            {
                "formula_id": "四君子汤",
                "name": "四君子汤",
                "herbs": ["人参", "白术", "茯苓", "甘草"],
                "indications": ["脾虚", "气虚"],
                "description": "补气健脾",
            },
            {
                "formula_id": "六君子汤",
                "name": "六君子汤",
                "herbs": ["人参", "白术", "茯苓", "甘草", "陈皮", "半夏"],
                "indications": ["脾虚", "痰湿"],
                "description": "补气化痰",
            },
        ]
        query_text = "四君子汤；药物:人参 白术 茯苓 甘草；证候:脾虚 气虚；补气健脾"
        six_gentlemen_text = (
            "六君子汤；药物:人参 白术 茯苓 甘草 陈皮 半夏；证候:脾虚 痰湿；补气化痰"
        )
        encoder = _CountingEncoder(
            {
                query_text: [1.0, 0.0, 0.0],
                six_gentlemen_text: [0.9, 0.1, 0.0],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            first_builder = SemanticGraphBuilder(
                {
                    "embedding_encoder": encoder,
                    "formula_index_persist_directory": tmp,
                    "formula_index_corpus_version": "catalog-v1",
                }
            )
            self.assertTrue(first_builder.initialize())
            try:
                with patch.object(
                    first_builder,
                    "_build_formula_embedding_catalog",
                    return_value=catalog,
                ):
                    first_builder._generate_research_perspectives(
                        [{"type": "formula", "name": "四君子汤"}]
                    )
            finally:
                first_builder.cleanup()

            self.assertEqual(encoder.calls, 1)

            second_builder = SemanticGraphBuilder(
                {
                    "embedding_encoder": encoder,
                    "formula_index_persist_directory": tmp,
                    "formula_index_corpus_version": "catalog-v1",
                }
            )
            self.assertTrue(second_builder.initialize())
            try:
                with patch.object(
                    second_builder,
                    "_build_formula_embedding_catalog",
                    return_value=catalog,
                ):
                    second_builder._generate_research_perspectives(
                        [{"type": "formula", "name": "四君子汤"}]
                    )
            finally:
                second_builder.cleanup()

        self.assertEqual(
            encoder.calls,
            1,
            "重启后应直接复用持久化索引与已缓存查询向量，不应再次编码",
        )


class TestSemanticGraphServiceFacade(unittest.TestCase):
    def test_service_is_canonical_facade_with_builder_output_contract(self):
        service = SemanticGraphService()
        self.assertTrue(service.initialize())
        try:
            with (
                patch.object(
                    service, "_generate_research_perspectives", return_value={}
                ),
                patch.object(service, "_analyze_herb_properties", return_value={}),
                patch.object(service, "_analyze_formula_similarities", return_value=[]),
                patch.object(service, "_collect_pharmacology_data", return_value={}),
                patch.object(
                    service,
                    "_collect_advanced_formula_analyses",
                    return_value={
                        "network_pharmacology_systems_biology": {},
                        "supramolecular_physicochemistry": {},
                        "knowledge_archaeology": {},
                        "complexity_nonlinear_dynamics": {},
                    },
                ),
                patch(
                    "src.analysis.semantic_graph.SummaryAnalysisEngine.analyze",
                    return_value={},
                ),
            ):
                output = service.execute(
                    {"entities": [{"type": "herb", "name": "柴胡"}]}
                )

            self.assertEqual(service.contract_version, "semantic-graph-service-v1")
            self.assertIn("semantic_graph", output)
            self.assertIn("graph_statistics", output)
            self.assertGreaterEqual(output["graph_statistics"]["nodes_count"], 1)
        finally:
            service.cleanup()


if __name__ == "__main__":
    unittest.main()
