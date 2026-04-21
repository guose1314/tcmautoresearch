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
    def test_observe_ingestion_degrades_when_reasoning_execution_fails(
        self,
        mock_pre_init, mock_pre_exec, mock_pre_clean,
        mock_ex_init, mock_ex_exec, mock_ex_clean,
        mock_sem_init, mock_sem_exec, mock_sem_clean,
        mock_reason_init, mock_reason_exec, mock_reason_clean,
        mock_out_init, mock_out_exec, mock_out_clean,
    ):
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
        mock_reason_exec.side_effect = RuntimeError("reason failed")

        mock_out_init.return_value = True
        mock_out_clean.return_value = True
        mock_out_exec.return_value = {
            "output_data": {
                "quality_metrics": {"entities_extracted": 1},
                "recommendations": ["keep going"],
            }
        }

        pipeline = ResearchPipeline({})
        result = pipeline.phase_handlers.run_observe_ingestion_pipeline(
            {
                "sources": ["local"],
                "stats": {"total_documents": 1},
                "documents": [{"text": "测试文本", "urn": "doc:reason-fail", "title": "fail"}],
            },
            {"max_texts": 1, "max_chars_per_text": 500},
        )

        self.assertEqual(result["processed_document_count"], 1)
        self.assertNotIn("error", result)
        self.assertEqual(result["aggregate"]["reasoning_summary"], {})
        self.assertEqual(result["aggregate"]["output_quality_metrics"], [{"entities_extracted": 1}])
        self.assertIn("keep going", result["aggregate"]["output_recommendations"])

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
    def test_observe_ingestion_emits_philology_outputs(
        self,
        mock_pre_init, mock_pre_exec, mock_pre_clean,
        mock_ex_init, mock_ex_exec, mock_ex_clean,
        mock_sem_init, mock_sem_exec, mock_sem_clean,
        mock_reason_init, mock_reason_clean,
        mock_out_init, mock_out_clean,
    ):
        mock_pre_init.return_value = True
        mock_pre_clean.return_value = True
        mock_pre_exec.side_effect = lambda context: {
            "processed_text": context["raw_text"],
            "metadata": context.get("metadata", {}),
            "processing_steps": ["pass_through"],
        }

        mock_ex_init.return_value = True
        mock_ex_clean.return_value = True
        mock_ex_exec.side_effect = lambda context: {
            "entities": [{"name": "黄芪", "type": "herb", "confidence": 0.95}]
            if "黄芪" in context.get("processed_text", "")
            else [],
            "statistics": {"by_type": {"herb": 1} if "黄芪" in context.get("processed_text", "") else {}},
            "confidence_scores": {"average_confidence": 0.95 if "黄芪" in context.get("processed_text", "") else 0.0},
        }

        mock_sem_init.return_value = True
        mock_sem_clean.return_value = True
        mock_sem_exec.return_value = {
            "semantic_graph": {"nodes": [], "edges": []},
            "graph_statistics": {"nodes_count": 1, "edges_count": 0, "relationships_by_type": {}},
        }

        mock_reason_init.return_value = False
        mock_reason_clean.return_value = True
        mock_out_init.return_value = False
        mock_out_clean.return_value = True

        pipeline = ResearchPipeline({})
        result = pipeline.phase_handlers.run_observe_ingestion_pipeline(
            {
                "sources": ["local"],
                "stats": {"total_documents": 2},
                "documents": [
                    {
                        "text": "黃芪當歸補血湯。",
                        "urn": "doc:1",
                        "title": "补血汤宋本",
                        "source_type": "local",
                        "metadata": {
                            "version_metadata": {
                                "work_title": "补血汤",
                                "work_key": "补血汤",
                                "fragment_title": "补血汤",
                                "fragment_key": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "宋本",
                                "witness_key": "local:doc:1",
                            }
                        },
                    },
                    {
                        "text": "黃耆當歸補血湯。",
                        "urn": "doc:2",
                        "title": "补血汤明抄本",
                        "source_type": "local",
                        "metadata": {
                            "version_metadata": {
                                "work_title": "补血汤",
                                "work_key": "补血汤",
                                "fragment_title": "补血汤",
                                "fragment_key": "补血汤",
                                "work_fragment_key": "补血汤|补血汤",
                                "version_lineage_key": "补血汤|补血汤|明|李时珍|明抄本",
                                "dynasty": "明",
                                "author": "李时珍",
                                "edition": "明抄本",
                                "witness_key": "local:doc:2",
                            }
                        },
                    },
                ],
            },
            {"max_texts": 2, "max_chars_per_text": 500},
        )

        self.assertEqual(result["processed_document_count"], 2)
        self.assertGreaterEqual(result["aggregate"]["philology_document_count"], 2)
        self.assertGreaterEqual(result["aggregate"]["recognized_term_count"], 2)
        self.assertGreaterEqual(result["aggregate"]["orthographic_variant_count"], 1)
        self.assertGreaterEqual(result["aggregate"]["terminology_standard_table_count"], 2)
        self.assertGreaterEqual(result["aggregate"]["version_collation_difference_count"], 1)
        self.assertGreaterEqual(result["aggregate"]["version_collation_witness_count"], 1)
        self.assertGreaterEqual(result["aggregate"]["collation_entry_count"], 1)
        self.assertGreaterEqual(result["aggregate"]["fragment_candidate_count"], 1)
        self.assertGreaterEqual(result["aggregate"]["citation_source_candidate_count"], 1)
        self.assertGreaterEqual(result["aggregate"]["philology_asset_count"], 5)
        self.assertTrue(any("版本对勘" in note for note in result["aggregate"]["philology_notes"]))
        self.assertTrue(any("辑佚候选" in note for note in result["aggregate"]["philology_notes"]))

        aggregate_assets = result["aggregate"]["philology_assets"]
        self.assertEqual(len(aggregate_assets["terminology_standard_table"]), result["aggregate"]["terminology_standard_table_count"])
        self.assertEqual(len(aggregate_assets["collation_entries"]), result["aggregate"]["collation_entry_count"])
        self.assertEqual(len(aggregate_assets["fragment_candidates"]), result["aggregate"]["fragment_candidate_count"])
        self.assertEqual(
            len(aggregate_assets["citation_source_candidates"]),
            result["aggregate"]["citation_source_candidate_count"],
        )
        self.assertEqual(aggregate_assets["annotation_report"]["summary"]["processed_document_count"], 2)
        self.assertGreaterEqual(aggregate_assets["annotation_report"]["summary"]["fragment_candidate_count"], 1)

        first_doc = result["documents"][0]
        self.assertIn("philology", first_doc)
        self.assertIn("philology_assets", first_doc)
        self.assertGreaterEqual(first_doc["philology"]["term_standardization"]["recognized_term_count"], 1)
        self.assertGreaterEqual(first_doc["philology"]["version_collation"]["difference_count"], 1)
        self.assertGreaterEqual(first_doc["philology"]["fragment_reconstruction"]["fragment_candidate_count"], 1)
        self.assertGreaterEqual(first_doc["philology"]["term_standardization"]["terminology_standard_table_count"], 1)
        self.assertGreaterEqual(first_doc["philology"]["version_collation"]["collation_entry_count"], 1)
        self.assertEqual(
            first_doc["philology"]["version_collation"]["witnesses"][0]["selection_strategy"],
            "work_fragment_key",
        )

        first_term_row = first_doc["philology"]["term_standardization"]["terminology_standard_table"][0]
        self.assertIn("canonical", first_term_row)
        self.assertIn("observed_forms", first_term_row)
        first_collation_entry = first_doc["philology"]["version_collation"]["collation_entries"][0]
        self.assertIn("judgement", first_collation_entry)
        self.assertIn("base_context", first_collation_entry)
        first_fragment_candidate = first_doc["philology"]["fragment_reconstruction"]["fragment_candidates"][0]
        self.assertIn("fragment_candidate_id", first_fragment_candidate)
        self.assertIn("match_score", first_fragment_candidate)
        self.assertIn("reconstruction_basis", first_fragment_candidate)

        self.assertIn("黄芪", mock_pre_exec.call_args_list[0].args[0]["raw_text"])

    def test_observe_phase_emits_philology_artifacts(self):
        pipeline = ResearchPipeline(
            {
                "philology_service": {
                    "artifact_output": {
                        "enabled": True,
                        "include_terminology_standard_table": True,
                        "include_collation_entries": True,
                        "include_annotation_report": True,
                    }
                }
            }
        )
        cycle = pipeline.create_research_cycle(
            cycle_name="observe_philology_artifacts",
            description="observe phase artifact test",
            objective="验证文献学产物",
            scope="古籍观察",
        )
        observe_handler = pipeline.phase_handlers.get_observe_handler()

        ingestion_result = {
            "processed_document_count": 1,
            "documents": [
                {
                    "urn": "doc:1",
                    "title": "补血汤宋本",
                    "source_type": "local",
                    "metadata": {
                        "version_metadata": {
                            "catalog_id": "local:catalog:1",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "work_fragment_key": "补血汤|补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "local:doc:1",
                            "dynasty": "明",
                            "author": "李时珍",
                            "edition": "宋本",
                            "lineage_source": "explicit_metadata",
                        }
                    },
                }
            ],
            "aggregate": {
                "philology_document_count": 1,
                "term_mapping_count": 1,
                "orthographic_variant_count": 1,
                "recognized_term_count": 1,
                "terminology_standard_table_count": 1,
                "version_collation_difference_count": 1,
                "version_collation_witness_count": 1,
                "collation_entry_count": 1,
                "philology_asset_count": 3,
                "philology_notes": ["输出 1 条可复用校勘条目"],
                "philology_assets": {
                    "terminology_standard_table": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:1",
                            "canonical": "黄芪",
                            "label": "本草药名",
                            "status": "standardized",
                            "observed_forms": ["黃芪"],
                            "configured_variants": ["黃耆"],
                            "sources": ["normalizer_term_mapping"],
                            "notes": ["黃芪 统一为 黄芪（本草药名）"],
                        }
                    ],
                    "collation_entries": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:1",
                            "difference_type": "replace",
                            "base_text": "黃芪",
                            "witness_text": "黃耆",
                            "judgement": "异体字通用",
                            "note": "此处属字形异写，不改义项。",
                        }
                    ],
                    "annotation_report": {
                        "summary": {"processed_document_count": 1},
                        "documents": [{"document_title": "补血汤宋本", "collation_entry_count": 1}],
                    },
                },
            },
        }

        with patch.object(observe_handler, "_collect_observe_corpus_if_enabled", return_value=None), patch.object(
            observe_handler,
            "_run_observe_literature_if_enabled",
            return_value=None,
        ), patch.object(
            observe_handler,
            "_run_observe_ingestion_if_enabled",
            return_value=ingestion_result,
        ), patch.object(
            observe_handler,
            "_build_observe_metadata",
            return_value={"philology_artifacts": True},
        ):
            result = pipeline.phase_handlers.execute_observe_phase(cycle, {})

        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["artifacts"]), 4)
        self.assertIn("graph_assets", result["results"])
        self.assertIn("philology_subgraph", result["results"]["graph_assets"])
        self.assertGreater(result["results"]["graph_assets"]["philology_subgraph"]["node_count"], 0)
        self.assertIn("philology_subgraph", result["metadata"]["graph_asset_subgraphs"])
        artifact_names = {item["name"] for item in result["artifacts"]}
        self.assertEqual(
            artifact_names,
            {
                "observe_philology_terminology_table",
                "observe_philology_collation_entries",
                "observe_philology_annotation_report",
                "observe_philology_catalog_summary",
            },
        )
        terminology_artifact = next(item for item in result["artifacts"] if item["name"] == "observe_philology_terminology_table")
        self.assertEqual(terminology_artifact["artifact_type"], "dataset")
        self.assertEqual(terminology_artifact["content"]["row_count"], 1)
        report_artifact = next(item for item in result["artifacts"] if item["name"] == "observe_philology_annotation_report")
        self.assertEqual(report_artifact["artifact_type"], "report")
        self.assertEqual(report_artifact["content"]["summary"]["processed_document_count"], 1)
        catalog_artifact = next(item for item in result["artifacts"] if item["name"] == "observe_philology_catalog_summary")
        self.assertEqual(catalog_artifact["artifact_type"], "dataset")
        self.assertEqual(catalog_artifact["content"]["summary"]["catalog_document_count"], 1)
        self.assertEqual(catalog_artifact["content"]["summary"]["version_lineage_count"], 1)
        self.assertEqual(catalog_artifact["content"]["summary"]["exegesis_entry_count"], 1)
        exegesis_entry = catalog_artifact["content"]["documents"][0]["exegesis_entries"][0]
        self.assertEqual(exegesis_entry["definition_source"], "structured_tcm_knowledge")
        self.assertIn("补气", exegesis_entry["definition"])
        self.assertIn("TCMRelationshipDefinitions.HERB_EFFICACY_MAP", exegesis_entry["source_refs"])

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
    def test_observe_ingestion_applies_learning_strategy_thresholds_and_branches(
        self,
        mock_pre_init,
        mock_pre_exec,
        mock_pre_clean,
        mock_ex_init,
        mock_ex_exec,
        mock_ex_clean,
        mock_sem_init,
        mock_sem_exec,
        mock_sem_clean,
        mock_reason_init,
        mock_reason_clean,
        mock_out_init,
        mock_out_clean,
    ):
        mock_pre_init.return_value = True
        mock_pre_clean.return_value = True
        mock_pre_exec.side_effect = lambda context: {"processed_text": context["raw_text"]}

        mock_ex_init.return_value = True
        mock_ex_clean.return_value = True
        mock_ex_exec.return_value = {
            "entities": [
                {"name": "黄芪", "type": "herb", "confidence": 0.91},
                {"name": "噪声实体", "type": "other", "confidence": 0.62},
            ],
            "statistics": {"by_type": {"herb": 1, "other": 1}},
            "confidence_scores": {"average_confidence": 0.765},
        }

        mock_sem_init.return_value = True
        mock_sem_clean.return_value = True
        mock_sem_exec.return_value = {
            "semantic_graph": {
                "nodes": [],
                "edges": [
                    {
                        "source": "herb:黄芪",
                        "target": "other:噪声实体",
                        "attributes": {"relationship_type": "related_to", "confidence": 0.61},
                    }
                ],
            },
            "graph_statistics": {"nodes_count": 2, "edges_count": 1, "relationships_by_type": {"related_to": {"count": 1}}},
        }

        mock_reason_init.return_value = True
        mock_reason_clean.return_value = True
        mock_out_init.return_value = True
        mock_out_clean.return_value = True

        pipeline = ResearchPipeline({})
        result = pipeline.phase_handlers.run_observe_ingestion_pipeline(
            {
                "sources": ["local"],
                "stats": {"total_documents": 4},
                "documents": [
                    {"text": f"文档{i} 黄芪", "urn": f"doc:{i}", "title": f"doc{i}"}
                    for i in range(1, 5)
                ],
            },
            {
                "learning_strategy": {
                    "tuned_parameters": {
                        "quality_threshold": 0.82,
                        "confidence_threshold": 0.8,
                    },
                    "observe_run_reasoning": False,
                    "observe_run_output_generation": False,
                }
            },
        )

        self.assertEqual(result["processed_document_count"], 4)
        self.assertEqual(result["aggregate"]["total_entities"], 4)
        self.assertEqual(result["aggregate"]["semantic_relationships"], [])
        self.assertEqual({entity["name"] for entity in result["aggregate"]["entities"]}, {"黄芪"})
        self.assertTrue(all(document["entity_count"] == 1 for document in result["documents"]))
        self.assertTrue(all(document["entities"][0]["name"] == "黄芪" for document in result["documents"]))
        self.assertTrue(all(document.get("output_generation") is None for document in result["documents"]))
        mock_reason_init.assert_not_called()
        mock_out_init.assert_not_called()


class TestReviewAuditTrail(unittest.TestCase):
    """Verify decision_history is preserved when a review decision is overwritten."""

    def test_catalog_review_upsert_preserves_previous_decision_in_history(self):
        from src.research.observe_philology import (
            upsert_observe_catalog_review_artifact_content,
        )

        first = upsert_observe_catalog_review_artifact_content({}, {
            "scope": "version_lineage",
            "version_lineage_key": "伤寒论|宋版",
            "review_status": "pending",
            "reviewer": "张三",
            "reviewed_at": "2026-04-15T10:00:00",
            "decision_basis": "初审",
        })
        self.assertEqual(first["decision_count"], 1)
        decision_v1 = first["decisions"][0]
        self.assertNotIn("decision_history", decision_v1)

        second = upsert_observe_catalog_review_artifact_content(first, {
            "scope": "version_lineage",
            "version_lineage_key": "伤寒论|宋版",
            "review_status": "accepted",
            "reviewer": "李四",
            "reviewed_at": "2026-04-16T12:00:00",
            "decision_basis": "复核通过",
        })
        self.assertEqual(second["decision_count"], 1)
        decision_v2 = second["decisions"][0]
        self.assertEqual(decision_v2["review_status"], "accepted")
        self.assertEqual(decision_v2["reviewer"], "李四")
        self.assertIn("decision_history", decision_v2)
        self.assertEqual(len(decision_v2["decision_history"]), 1)
        self.assertEqual(decision_v2["decision_history"][0]["reviewer"], "张三")
        self.assertEqual(decision_v2["decision_history"][0]["review_status"], "pending")

    def test_workbench_review_upsert_preserves_audit_trail_across_three_revisions(self):
        from src.research.review_workbench import (
            upsert_observe_review_workbench_artifact_content,
        )

        v1 = upsert_observe_review_workbench_artifact_content({}, {
            "asset_type": "terminology_row",
            "asset_key": "黄芪|本草药名",
            "review_status": "pending",
            "reviewer": "A",
            "reviewed_at": "2026-04-10T00:00:00",
        })
        v2 = upsert_observe_review_workbench_artifact_content(v1, {
            "asset_type": "terminology_row",
            "asset_key": "黄芪|本草药名",
            "review_status": "needs_source",
            "reviewer": "B",
            "reviewed_at": "2026-04-11T00:00:00",
        })
        v3 = upsert_observe_review_workbench_artifact_content(v2, {
            "asset_type": "terminology_row",
            "asset_key": "黄芪|本草药名",
            "review_status": "accepted",
            "reviewer": "C",
            "reviewed_at": "2026-04-12T00:00:00",
        })
        decision = v3["decisions"][0]
        self.assertEqual(decision["review_status"], "accepted")
        self.assertEqual(decision["reviewer"], "C")
        self.assertEqual(len(decision["decision_history"]), 2)
        self.assertEqual(decision["decision_history"][0]["reviewer"], "A")
        self.assertEqual(decision["decision_history"][1]["reviewer"], "B")

    def test_catalog_review_batch_preserves_audit_trail(self):
        from src.research.observe_philology import (
            upsert_observe_catalog_review_artifact_content,
            upsert_observe_catalog_review_artifact_content_batch,
        )

        existing = upsert_observe_catalog_review_artifact_content({}, {
            "scope": "version_lineage",
            "version_lineage_key": "K1",
            "review_status": "pending",
            "reviewer": "用户1",
        })
        result = upsert_observe_catalog_review_artifact_content_batch(existing, [
            {
                "scope": "version_lineage",
                "version_lineage_key": "K1",
                "review_status": "accepted",
                "reviewer": "用户2",
            },
            {
                "scope": "version_lineage",
                "version_lineage_key": "K2",
                "review_status": "rejected",
                "reviewer": "用户2",
            },
        ])
        self.assertEqual(result["decision_count"], 2)
        k1 = next(d for d in result["decisions"] if d.get("version_lineage_key") == "K1")
        k2 = next(d for d in result["decisions"] if d.get("version_lineage_key") == "K2")
        self.assertEqual(k1["review_status"], "accepted")
        self.assertIn("decision_history", k1)
        self.assertEqual(k1["decision_history"][0]["reviewer"], "用户1")
        self.assertEqual(k2["review_status"], "rejected")
        self.assertNotIn("decision_history", k2)

    def test_workbench_batch_upsert_applies_multiple_decisions(self):
        from src.research.review_workbench import (
            upsert_observe_review_workbench_artifact_content_batch,
        )

        result = upsert_observe_review_workbench_artifact_content_batch({}, [
            {
                "asset_type": "claim",
                "asset_key": "c1",
                "review_status": "accepted",
                "reviewer": "审核员",
            },
            {
                "asset_type": "collation_entry",
                "asset_key": "col1",
                "review_status": "rejected",
                "reviewer": "审核员",
            },
        ])
        self.assertEqual(result["decision_count"], 2)
        types = {d["asset_type"] for d in result["decisions"]}
        self.assertEqual(types, {"claim", "collation_entry"})


class TestExpandedExegesisAuthoritySources(unittest.TestCase):
    """Verify the new syndrome and theory exegesis sources are integrated."""

    def test_syndrome_category_produces_structured_knowledge_definition(self):
        from src.research.observe_philology import (
            _build_structured_knowledge_exegesis_definition,
        )

        result = _build_structured_knowledge_exegesis_definition(
            "气虚证", category="syndrome", label="证候术语",
        )
        self.assertEqual(result["definition_source"], "structured_tcm_knowledge")
        self.assertIn("元气不足", result["definition"])
        self.assertIn("少气懒言", result["definition"])
        self.assertIn("SYNDROME_DEFINITIONS", result["source_refs"][0])

    def test_theory_category_produces_structured_knowledge_definition(self):
        from src.research.observe_philology import (
            _build_structured_knowledge_exegesis_definition,
        )

        result = _build_structured_knowledge_exegesis_definition(
            "君臣佐使", category="theory", label="理论术语",
        )
        self.assertEqual(result["definition_source"], "structured_tcm_knowledge")
        self.assertIn("君药治主症", result["definition"])
        self.assertIn("THEORY_TERM_DEFINITIONS", result["source_refs"][0])

    def test_unknown_syndrome_returns_empty(self):
        from src.research.observe_philology import (
            _build_structured_knowledge_exegesis_definition,
        )

        result = _build_structured_knowledge_exegesis_definition(
            "不存在证", category="syndrome", label="证候术语",
        )
        self.assertEqual(result, {})

    def test_unknown_theory_returns_empty(self):
        from src.research.observe_philology import (
            _build_structured_knowledge_exegesis_definition,
        )

        result = _build_structured_knowledge_exegesis_definition(
            "不存在术语", category="theory", label="理论术语",
        )
        self.assertEqual(result, {})

    def test_resolve_exegesis_definition_prefers_structured_syndrome(self):
        from src.research.observe_philology import _resolve_exegesis_definition

        row = {
            "label": "证候术语",
            "notes": ["一般性备注"],
            "sources": [],
        }
        result = _resolve_exegesis_definition(row, canonical="血虚证", label="证候术语")
        self.assertEqual(result["definition_source"], "structured_tcm_knowledge")
        self.assertIn("血液亏虚", result["definition"])

    def test_exegesis_source_rank_covers_all_levels(self):
        from src.research.observe_philology import _exegesis_definition_source_rank

        self.assertEqual(_exegesis_definition_source_rank("config_terminology_standard"), 4)
        self.assertEqual(_exegesis_definition_source_rank("structured_tcm_knowledge"), 3)
        self.assertEqual(_exegesis_definition_source_rank("terminology_note"), 2)
        self.assertEqual(_exegesis_definition_source_rank("canonical_fallback"), 1)
        self.assertEqual(_exegesis_definition_source_rank(""), 0)

    def test_herb_exegesis_still_works_after_changes(self):
        from src.research.observe_philology import (
            _build_structured_knowledge_exegesis_definition,
        )

        result = _build_structured_knowledge_exegesis_definition(
            "黄芪", category="herb", label="本草药名",
        )
        self.assertEqual(result["definition_source"], "structured_tcm_knowledge")
        self.assertIn("补气", result["definition"])

    def test_formula_exegesis_still_works_after_changes(self):
        from src.research.observe_philology import (
            _build_structured_knowledge_exegesis_definition,
        )

        result = _build_structured_knowledge_exegesis_definition(
            "四君子汤", category="formula", label="方剂名",
        )
        self.assertEqual(result["definition_source"], "structured_tcm_knowledge")
        self.assertIn("君药", result["definition"])


class TestWorkbenchReviewWriteback(unittest.TestCase):
    """Verify workbench review decisions are merged into snapshot items."""

    def test_terminology_row_gets_review_status_from_workbench_decision(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "terminology_standard_table": [
                {"document_urn": "urn:doc:001", "document_title": "本草纲目", "canonical": "黄芪", "label": "本草术语"},
            ],
            "review_workbench_decisions": [
                {
                    "asset_type": "terminology_row",
                    "asset_key": "terminology_row::document_urn=urn:doc:001|document_title=本草纲目|canonical=黄芪|label=本草术语",
                    "review_status": "accepted",
                    "reviewer": "审核员A",
                    "reviewed_at": "2026-04-15T10:00:00",
                    "decision_basis": "权威训诂确认",
                },
            ],
        }
        result = normalize_observe_philology_assets(raw)
        rows = result["terminology_standard_table"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["review_status"], "accepted")
        self.assertEqual(rows[0]["reviewer"], "审核员A")
        self.assertEqual(rows[0]["decision_basis"], "权威训诂确认")

    def test_collation_entry_gets_review_status_from_workbench_decision(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "collation_entries": [
                {
                    "document_urn": "urn:doc:002",
                    "witness_urn": "urn:w:002",
                    "difference_type": "variant",
                    "base_text": "甘",
                    "witness_text": "苦",
                },
            ],
            "review_workbench_decisions": [
                {
                    "asset_type": "collation_entry",
                    "asset_key": "collation_entry::document_urn=urn:doc:002|witness_urn=urn:w:002|difference_type=variant|base_text=甘|witness_text=苦",
                    "review_status": "rejected",
                    "reviewer": "校勘师B",
                    "decision_basis": "底本讹误",
                },
            ],
        }
        result = normalize_observe_philology_assets(raw)
        entries = result["collation_entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["review_status"], "rejected")
        self.assertEqual(entries[0]["reviewer"], "校勘师B")

    def test_fragment_candidate_gets_review_status_from_workbench_decision(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "fragment_candidates": [
                {
                    "fragment_candidate_id": "fc-001",
                    "document_urn": "urn:doc:003",
                    "fragment_title": "佚文甲",
                },
            ],
            "review_workbench_decisions": [
                {
                    "asset_type": "fragment_candidate",
                    "asset_key": "fragment_candidate::candidate_kind=fragment_candidates|fragment_candidate_id=fc-001|document_urn=urn:doc:003|fragment_title=佚文甲",
                    "review_status": "accepted",
                    "reviewer": "辑佚师C",
                },
            ],
        }
        result = normalize_observe_philology_assets(raw)
        candidates = result["fragment_candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["review_status"], "accepted")
        self.assertEqual(candidates[0]["reviewer"], "辑佚师C")

    def test_unmatched_decision_leaves_item_unchanged(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "terminology_standard_table": [
                {"document_urn": "urn:doc:001", "canonical": "黄芪", "label": "本草术语"},
            ],
            "review_workbench_decisions": [
                {
                    "asset_type": "terminology_row",
                    "asset_key": "terminology_row::document_urn=urn:doc:999|canonical=不存在|label=不存在",
                    "review_status": "accepted",
                },
            ],
        }
        result = normalize_observe_philology_assets(raw)
        rows = result["terminology_standard_table"]
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0].get("review_status"), "accepted")

    def test_empty_decisions_returns_items_unchanged(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "terminology_standard_table": [
                {"canonical": "黄芪", "label": "本草术语"},
            ],
            "review_workbench_decisions": [],
        }
        result = normalize_observe_philology_assets(raw)
        self.assertEqual(len(result["terminology_standard_table"]), 1)


class TestPhilologyServiceExegesisEnrichment(unittest.TestCase):
    """Verify PhilologyService populates exegesis fields on terminology rows."""

    def _build_service(self, **kwargs):
        from src.analysis.philology_service import PhilologyService

        config = {
            "enable_version_collation": False,
            "enable_fragment_reconstruction": False,
            "terminology_standards": [
                {
                    "canonical": "黄芪",
                    "category": "herb",
                    "label": "本草药名",
                    "variants": ["黃芪", "黄耆"],
                    "note": "补气固表",
                    "source": "config_terminology_standard",
                },
            ],
            **kwargs,
        }
        svc = PhilologyService(config)
        svc.initialize()
        return svc

    def _get_terminology_rows(self, result):
        return result.get("philology", {}).get("term_standardization", {}).get("terminology_standard_table", [])

    def test_terminology_row_has_exegesis_fields(self):
        svc = self._build_service()
        result = svc.execute({"raw_text": "黄芪具有补气之功"})
        rows = self._get_terminology_rows(result)
        huang_qi_rows = [r for r in rows if r["canonical"] == "黄芪"]
        self.assertTrue(len(huang_qi_rows) >= 1)
        row = huang_qi_rows[0]
        self.assertIn("definition", row)
        self.assertIn("definition_source", row)
        self.assertIn("semantic_scope", row)
        self.assertIn("dynasty_usage", row)
        self.assertIn("disambiguation_basis", row)
        self.assertIn("exegesis_notes", row)
        self.assertTrue(row["definition"])
        self.assertTrue(row["definition_source"])

    def test_herb_gets_structured_definition_when_no_config(self):
        from src.analysis.philology_service import PhilologyService

        svc = PhilologyService({
            "enable_version_collation": False,
            "enable_fragment_reconstruction": False,
        })
        svc.initialize()
        result = svc.execute({"raw_text": "黄芪能补气固表"})
        rows = self._get_terminology_rows(result)
        huang_qi_rows = [r for r in rows if r["canonical"] == "黄芪"]
        if huang_qi_rows:
            row = huang_qi_rows[0]
            self.assertIn("definition", row)
            if row.get("definition_source") == "structured_tcm_knowledge":
                self.assertIn("补气", row["definition"])

    def test_config_standard_definition_preferred_over_structured(self):
        svc = self._build_service()
        result = svc.execute({"raw_text": "黄芪固表止汗"})
        rows = self._get_terminology_rows(result)
        huang_qi_rows = [r for r in rows if r["canonical"] == "黄芪"]
        if huang_qi_rows:
            row = huang_qi_rows[0]
            self.assertEqual(row["definition_source"], "config_terminology_standard")

    def test_injectable_dictionary_overrides_structured(self):
        class TestDict:
            def lookup(self, canonical, *, category=""):
                if canonical == "黄芪":
                    return {"definition": "外部字典释义", "definition_source": "external_dictionary"}
                return {}

        svc = self._build_service(
            exegesis_dictionaries=[TestDict()],
            terminology_standards=[],
        )
        result = svc.execute({"raw_text": "黄芪之效"})
        rows = self._get_terminology_rows(result)
        huang_qi_rows = [r for r in rows if r["canonical"] == "黄芪"]
        if huang_qi_rows:
            self.assertEqual(huang_qi_rows[0]["definition"], "外部字典释义")

    def test_fallback_definition_for_unknown_term(self):
        svc = self._build_service(terminology_standards=[])
        result = svc.execute({"raw_text": "此方用茯苓"})
        rows = self._get_terminology_rows(result)
        fu_ling_rows = [r for r in rows if r["canonical"] == "茯苓"]
        if fu_ling_rows:
            row = fu_ling_rows[0]
            self.assertIn("definition", row)
            self.assertTrue(row["definition"])

    def test_exegesis_notes_generated(self):
        svc = self._build_service()
        result = svc.execute({"raw_text": "黄芪补气"})
        rows = self._get_terminology_rows(result)
        huang_qi_rows = [r for r in rows if r["canonical"] == "黄芪"]
        if huang_qi_rows:
            self.assertIn("exegesis_notes", huang_qi_rows[0])
            self.assertTrue(huang_qi_rows[0]["exegesis_notes"])


class TestObserveExegesisNotesIntegration(unittest.TestCase):
    """Verify exegesis_notes flows through observe_philology normalization."""

    def test_exegesis_entry_carries_exegesis_notes(self):
        from src.research.observe_philology import _build_exegesis_entry_from_row

        row = {
            "canonical": "黄芪",
            "label": "本草药名",
            "category": "herb",
            "sources": ["config_terminology_standard"],
            "notes": ["补气固表要药"],
            "observed_forms": ["黃芪"],
            "configured_variants": [],
            "status": "standardized",
        }
        entry = _build_exegesis_entry_from_row(row, dynasty="明")
        self.assertIn("exegesis_notes", entry)
        self.assertTrue(entry["exegesis_notes"])

    def test_normalize_exegesis_entries_preserves_exegesis_notes(self):
        from src.research.observe_philology import _normalize_exegesis_entries

        entries = _normalize_exegesis_entries([
            {
                "canonical": "黄芪",
                "label": "本草药名",
                "definition": "补气固表",
                "definition_source": "structured_tcm_knowledge",
                "semantic_scope": "本草药名",
                "exegesis_notes": "「黄芪」释义来源：结构化知识库",
            },
        ])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["exegesis_notes"], "「黄芪」释义来源：结构化知识库")

    def test_terminology_columns_include_exegesis_fields(self):
        from src.research.observe_philology import _TERMINOLOGY_COLUMNS

        self.assertIn("definition", _TERMINOLOGY_COLUMNS)
        self.assertIn("definition_source", _TERMINOLOGY_COLUMNS)
        self.assertIn("semantic_scope", _TERMINOLOGY_COLUMNS)
        self.assertIn("dynasty_usage", _TERMINOLOGY_COLUMNS)
        self.assertIn("disambiguation_basis", _TERMINOLOGY_COLUMNS)
        self.assertIn("exegesis_notes", _TERMINOLOGY_COLUMNS)

    def test_exegesis_entry_prefers_row_definition_when_higher_rank(self):
        from src.research.observe_philology import _build_exegesis_entry_from_row

        row = {
            "canonical": "黄芪",
            "label": "本草药名",
            "category": "herb",
            "definition": "配置标准释义",
            "definition_source": "config_terminology_standard",
            "sources": ["config_terminology_standard"],
            "notes": [],
            "observed_forms": [],
            "configured_variants": [],
            "status": "standardized",
            "disambiguation_basis": ["config_terminology_standard"],
        }
        entry = _build_exegesis_entry_from_row(row)
        self.assertEqual(entry["definition"], "配置标准释义")
        self.assertEqual(entry["definition_source"], "config_terminology_standard")


class TestExegesisSummaryInCatalogMetrics(unittest.TestCase):
    """Verify exegesis summary metrics appear in catalog summary."""

    def test_build_catalog_summary_includes_exegesis_metrics(self):
        from src.research.observe_philology import _build_catalog_summary_metrics

        documents = [
            {
                "work_title": "本草纲目",
                "fragment_title": "卷一",
                "catalog_id": "001",
                "version_lineage_key": "vl1",
                "witness_key": "w1",
                "source_type": "local",
                "dynasty": "明",
                "exegesis_entries": [
                    {
                        "canonical": "黄芪",
                        "semantic_scope": "本草药名",
                        "definition": "补气固表",
                        "definition_source": "structured_tcm_knowledge",
                        "category": "herb",
                        "disambiguation_basis": ["src1"],
                    },
                ],
            },
        ]
        summary = _build_catalog_summary_metrics(documents, [])
        self.assertIn("exegesis_definition_coverage", summary)
        self.assertIn("exegesis_source_distribution", summary)
        self.assertIn("exegesis_category_distribution", summary)

    def test_empty_documents_no_exegesis_metrics(self):
        from src.research.observe_philology import _build_catalog_summary_metrics

        summary = _build_catalog_summary_metrics([], [])
        self.assertNotIn("exegesis_definition_coverage", summary)


if __name__ == "__main__":
    unittest.main()
