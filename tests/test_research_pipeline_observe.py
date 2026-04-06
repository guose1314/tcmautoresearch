import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestResearchPipelineObserve(unittest.TestCase):

    @patch("src.research.research_pipeline.OutputGenerator.cleanup")
    @patch("src.research.research_pipeline.OutputGenerator.execute")
    @patch("src.research.research_pipeline.OutputGenerator.initialize")
    @patch("src.research.research_pipeline.ReasoningEngine.cleanup")
    @patch("src.research.research_pipeline.ReasoningEngine.execute")
    @patch("src.research.research_pipeline.ReasoningEngine.initialize")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.cleanup")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.execute")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.initialize")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.cleanup")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.execute")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.initialize")
    @patch("src.research.research_pipeline.DocumentPreprocessor.cleanup")
    @patch("src.research.research_pipeline.DocumentPreprocessor.execute")
    @patch("src.research.research_pipeline.DocumentPreprocessor.initialize")
    def test_observe_ingestion_merges_reasoning_relationships(
        self,
        mock_pre_initialize,
        mock_pre_execute,
        mock_pre_cleanup,
        mock_ex_initialize,
        mock_ex_execute,
        mock_ex_cleanup,
        mock_sem_initialize,
        mock_sem_execute,
        mock_sem_cleanup,
        mock_reason_initialize,
        mock_reason_execute,
        mock_reason_cleanup,
        mock_out_initialize,
        mock_out_execute,
        mock_out_cleanup,
    ):
        mock_pre_initialize.return_value = True
        mock_pre_cleanup.return_value = True
        mock_pre_execute.return_value = {"processed_text": "补中益气汤 IL6 JAK-STAT"}

        mock_ex_initialize.return_value = True
        mock_ex_cleanup.return_value = True
        mock_ex_execute.return_value = {
            "entities": [
                {"name": "补中益气汤", "type": "formula", "confidence": 0.95},
                {"name": "IL6", "type": "target", "confidence": 0.92},
                {"name": "JAK-STAT", "type": "pathway", "confidence": 0.9},
            ],
            "statistics": {"by_type": {"formula": 1, "target": 1, "pathway": 1}},
            "confidence_scores": {"average_confidence": 0.9233},
        }

        mock_sem_initialize.return_value = True
        mock_sem_cleanup.return_value = True
        mock_sem_execute.return_value = {
            "semantic_graph": {
                "nodes": [
                    {"id": "formula:补中益气汤", "data": {"name": "补中益气汤", "type": "formula"}},
                    {"id": "target:IL6", "data": {"name": "IL6", "type": "target"}},
                    {"id": "pathway:JAK-STAT", "data": {"name": "JAK-STAT", "type": "pathway"}},
                ],
                "edges": [
                    {
                        "source": "target:IL6",
                        "target": "pathway:JAK-STAT",
                        "attributes": {"relationship_type": "participates_in", "confidence": 0.8},
                    }
                ],
            },
            "graph_statistics": {
                "nodes_count": 3,
                "edges_count": 1,
                "relationships_by_type": {"participates_in": {"count": 1}},
            },
        }

        mock_reason_initialize.return_value = True
        mock_reason_cleanup.return_value = True
        mock_reason_execute.return_value = {
            "reasoning_results": {
                "entity_relationships": [
                    {
                        "source": "补中益气汤",
                        "target": "IL6",
                        "type": "associated_target",
                        "confidence": 0.83,
                    }
                ]
            }
        }

        mock_out_initialize.return_value = True
        mock_out_cleanup.return_value = True
        mock_out_execute.return_value = {
            "output_data": {
                "quality_metrics": {"entities_extracted": 3, "confidence_score": 0.92},
                "recommendations": ["扩展实体词典"],
            },
            "output_format": "structured_json",
            "generated_at": "2026-04-06T00:00:00",
        }

        pipeline = ResearchPipeline({})
        result = pipeline.phase_handlers.run_observe_ingestion_pipeline(
            {
                "sources": ["local"],
                "stats": {"total_documents": 1},
                "documents": [{"text": "补中益气汤调控 IL6 并影响 JAK-STAT", "urn": "doc:1", "title": "doc1"}],
            },
            {
                "max_texts": 1,
                "max_chars_per_text": 1200,
            },
        )

        aggregate_relationships = result["aggregate"]["semantic_relationships"]
        relation_keys = {(item["source"], item["type"], item["target"]) for item in aggregate_relationships}
        self.assertIn(("补中益气汤", "associated_target", "IL6"), relation_keys)
        self.assertIn(("IL6", "participates_in", "JAK-STAT"), relation_keys)
        self.assertTrue(any(item["metadata"]["source"] == "observe_reasoning_engine" for item in aggregate_relationships))

    def test_relationship_conflict_resolution_prefers_priority_and_confidence(self):
        pipeline = ResearchPipeline({})
        phase_handlers = pipeline.phase_handlers

        merged = phase_handlers.merge_observe_relationship_sources(
            [
                {
                    "source": "黄芪",
                    "target": "IL6",
                    "type": "associated_target",
                    "source_type": "herb",
                    "target_type": "target",
                    "metadata": {"confidence": 0.91, "source": "observe_semantic_graph"},
                }
            ],
            [
                {
                    "source": "黄芪",
                    "target": "IL6",
                    "type": "associated_target",
                    "source_type": "herb",
                    "target_type": "target",
                    "metadata": {"confidence": 0.74, "source": "observe_reasoning_engine"},
                }
            ],
        )

        self.assertEqual(len(merged), 1)
        relation = merged[0]
        self.assertEqual(relation["metadata"]["source"], "observe_reasoning_engine")
        self.assertEqual(relation["metadata"]["confidence"], 0.91)
        self.assertIn("observe_semantic_graph", relation["metadata"]["merged_sources"])
        self.assertIn("observe_reasoning_engine", relation["metadata"]["merged_sources"])

    def test_relationship_conflict_resolution_can_prefer_confidence_by_relation_type(self):
        pipeline = ResearchPipeline(
            {
                "relationship_conflict_resolution": {
                    "relation_type_strategies": {
                        "associated_target": "confidence_then_source_priority",
                    }
                }
            }
        )
        phase_handlers = pipeline.phase_handlers

        merged = phase_handlers.merge_observe_relationship_sources(
            [
                {
                    "source": "黄芪",
                    "target": "IL6",
                    "type": "associated_target",
                    "source_type": "herb",
                    "target_type": "target",
                    "metadata": {"confidence": 0.91, "source": "observe_semantic_graph"},
                }
            ],
            [
                {
                    "source": "黄芪",
                    "target": "IL6",
                    "type": "associated_target",
                    "source_type": "herb",
                    "target_type": "target",
                    "metadata": {"confidence": 0.74, "source": "observe_reasoning_engine"},
                }
            ],
        )

        self.assertEqual(len(merged), 1)
        relation = merged[0]
        self.assertEqual(relation["metadata"]["source"], "observe_semantic_graph")
        self.assertEqual(
            relation["metadata"]["conflict_resolution"]["strategy"],
            "confidence_then_source_priority",
        )

    @patch("src.research.research_pipeline.CTextCorpusCollector.cleanup")
    @patch("src.research.research_pipeline.CTextCorpusCollector.execute")
    @patch("src.research.research_pipeline.CTextCorpusCollector.initialize")
    def test_observe_phase_auto_collects_ctext_whitelist(
        self,
        mock_initialize,
        mock_execute,
        mock_cleanup
    ):
        mock_initialize.return_value = True
        mock_cleanup.return_value = True
        mock_execute.return_value = {
            "source": "ctext",
            "seed_urns": ["ctp:analects", "ctp:mengzi"],
            "stats": {
                "document_count": 2,
                "chapter_count": 10,
                "line_count": 100,
                "char_count": 2000
            },
            "errors": [],
            "output_file": "data/ctext/ctext_corpus_mock.json"
        }

        pipeline = ResearchPipeline(
            {
                "ctext_corpus": {
                    "enabled": True,
                    "api_base": "https://api.ctext.org",
                    "request_interval_sec": 0.1,
                    "retry_count": 1,
                    "timeout_sec": 10,
                    "whitelist": {
                        "enabled": True,
                        "path": "data/ctext_whitelist.json",
                        "default_groups": ["four_books", "tcm_classics"]
                    }
                }
            }
        )

        cycle = pipeline.create_research_cycle(
            cycle_name="ctext_observe",
            description="测试观察阶段自动采集",
            objective="验证白名单拉取接入 observe",
            scope="语料采集",
            researchers=["tester"]
        )
        self.assertTrue(pipeline.start_research_cycle(cycle.cycle_id))

        result = pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.OBSERVE, {})

        self.assertEqual(result["phase"], "observe")
        self.assertTrue(result["metadata"]["auto_collected_ctext"])
        self.assertEqual(result["metadata"]["data_source"], "ctext_whitelist")
        self.assertEqual(result["metadata"]["ctext_groups"], ["four_books", "tcm_classics"])
        self.assertEqual(result["corpus_collection"]["stats"]["document_count"], 2)
        self.assertIn("标准语料白名单", result["findings"][0])

        mock_execute.assert_called_once()
        execute_context = mock_execute.call_args.args[0]
        self.assertTrue(execute_context["use_whitelist"])
        self.assertEqual(execute_context["whitelist_path"], "data/ctext_whitelist.json")
        self.assertEqual(execute_context["whitelist_groups"], ["four_books", "tcm_classics"])

    @patch("src.research.research_pipeline.OutputGenerator.cleanup")
    @patch("src.research.research_pipeline.OutputGenerator.execute")
    @patch("src.research.research_pipeline.OutputGenerator.initialize")
    @patch("src.research.research_pipeline.ReasoningEngine.cleanup")
    @patch("src.research.research_pipeline.ReasoningEngine.execute")
    @patch("src.research.research_pipeline.ReasoningEngine.initialize")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.cleanup")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.execute")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.initialize")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.cleanup")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.execute")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.initialize")
    @patch("src.research.research_pipeline.DocumentPreprocessor.cleanup")
    @patch("src.research.research_pipeline.DocumentPreprocessor.execute")
    @patch("src.research.research_pipeline.DocumentPreprocessor.initialize")
    def test_observe_ingestion_includes_output_generation(
        self,
        mock_pre_init, mock_pre_exec, mock_pre_clean,
        mock_ex_init, mock_ex_exec, mock_ex_clean,
        mock_sem_init, mock_sem_exec, mock_sem_clean,
        mock_reason_init, mock_reason_exec, mock_reason_clean,
        mock_out_init, mock_out_exec, mock_out_clean,
    ):
        """OutputGenerator is the 5th module — verify it runs and its output appears in results."""
        mock_pre_init.return_value = True
        mock_pre_clean.return_value = True
        mock_pre_exec.return_value = {"processed_text": "黄芪补中"}

        mock_ex_init.return_value = True
        mock_ex_clean.return_value = True
        mock_ex_exec.return_value = {
            "entities": [{"name": "黄芪", "type": "herb", "confidence": 0.93}],
            "statistics": {"by_type": {"herb": 1}},
            "confidence_scores": {"average_confidence": 0.93},
        }

        mock_sem_init.return_value = True
        mock_sem_clean.return_value = True
        mock_sem_exec.return_value = {
            "semantic_graph": {"nodes": [], "edges": []},
            "graph_statistics": {"nodes_count": 1, "edges_count": 0, "relationships_by_type": {}},
        }

        mock_reason_init.return_value = True
        mock_reason_clean.return_value = True
        mock_reason_exec.return_value = {"reasoning_results": {}}

        mock_out_init.return_value = True
        mock_out_clean.return_value = True
        mock_out_exec.return_value = {
            "output_data": {
                "quality_metrics": {"entities_extracted": 1, "confidence_score": 0.93},
                "recommendations": ["增加方剂语料覆盖"],
            },
            "output_format": "structured_json",
            "generated_at": "2026-04-06T12:00:00",
        }

        pipeline = ResearchPipeline({})
        result = pipeline.phase_handlers.run_observe_ingestion_pipeline(
            {
                "sources": ["local"],
                "stats": {"total_documents": 1},
                "documents": [{"text": "黄芪补中益气", "urn": "doc:test", "title": "test"}],
            },
            {"max_texts": 1, "max_chars_per_text": 500},
        )

        self.assertEqual(result["processed_document_count"], 1)
        doc = result["documents"][0]
        self.assertIsNotNone(doc.get("output_generation"))
        self.assertEqual(doc["output_generation"]["quality_metrics"]["entities_extracted"], 1)

        agg = result["aggregate"]
        self.assertEqual(len(agg["output_quality_metrics"]), 1)
        self.assertIn("增加方剂语料覆盖", agg["output_recommendations"])

        mock_out_exec.assert_called_once()
        out_context = mock_out_exec.call_args.args[0]
        self.assertIn("entities", out_context)
        self.assertIn("semantic_graph", out_context)

    @patch("src.research.research_pipeline.OutputGenerator.cleanup")
    @patch("src.research.research_pipeline.OutputGenerator.initialize")
    @patch("src.research.research_pipeline.ReasoningEngine.cleanup")
    @patch("src.research.research_pipeline.ReasoningEngine.initialize")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.cleanup")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.execute")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.initialize")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.cleanup")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.execute")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.initialize")
    @patch("src.research.research_pipeline.DocumentPreprocessor.cleanup")
    @patch("src.research.research_pipeline.DocumentPreprocessor.execute")
    @patch("src.research.research_pipeline.DocumentPreprocessor.initialize")
    def test_observe_ingestion_degrades_when_output_generator_init_fails(
        self,
        mock_pre_init, mock_pre_exec, mock_pre_clean,
        mock_ex_init, mock_ex_exec, mock_ex_clean,
        mock_sem_init, mock_sem_exec, mock_sem_clean,
        mock_reason_init, mock_reason_clean,
        mock_out_init, mock_out_clean,
    ):
        """Pipeline should still succeed if OutputGenerator initialization fails."""
        mock_pre_init.return_value = True
        mock_pre_clean.return_value = True
        mock_pre_exec.return_value = {"processed_text": "test"}

        mock_ex_init.return_value = True
        mock_ex_clean.return_value = True
        mock_ex_exec.return_value = {
            "entities": [{"name": "test", "type": "herb", "confidence": 0.9}],
            "statistics": {"by_type": {"herb": 1}},
            "confidence_scores": {"average_confidence": 0.9},
        }

        mock_sem_init.return_value = True
        mock_sem_clean.return_value = True
        mock_sem_exec.return_value = {
            "semantic_graph": {"nodes": [], "edges": []},
            "graph_statistics": {"nodes_count": 0, "edges_count": 0, "relationships_by_type": {}},
        }

        mock_reason_init.return_value = True
        mock_reason_clean.return_value = True

        mock_out_init.return_value = False  # <-- OutputGenerator fails
        mock_out_clean.return_value = True

        pipeline = ResearchPipeline({})
        result = pipeline.phase_handlers.run_observe_ingestion_pipeline(
            {
                "sources": ["local"],
                "stats": {"total_documents": 1},
                "documents": [{"text": "测试文本", "urn": "doc:fail", "title": "fail"}],
            },
            {"max_texts": 1, "max_chars_per_text": 500},
        )

        self.assertEqual(result["processed_document_count"], 1)
        self.assertNotIn("error", result)
        doc = result["documents"][0]
        self.assertIsNone(doc.get("output_generation"))
        self.assertEqual(result["aggregate"]["output_quality_metrics"], [])


if __name__ == "__main__":
    unittest.main()
