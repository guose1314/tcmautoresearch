import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestResearchPipelineIngestion(unittest.TestCase):
    @patch("src.research.research_pipeline.SemanticGraphBuilder.cleanup")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.execute")
    @patch("src.research.research_pipeline.SemanticGraphBuilder.initialize")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.cleanup")
    @patch("src.research.research_pipeline.DocumentPreprocessor.cleanup")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.execute")
    @patch("src.research.research_pipeline.DocumentPreprocessor.execute")
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.initialize")
    @patch("src.research.research_pipeline.DocumentPreprocessor.initialize")
    @patch("src.research.research_pipeline.CTextCorpusCollector.cleanup")
    @patch("src.research.research_pipeline.CTextCorpusCollector.execute")
    @patch("src.research.research_pipeline.CTextCorpusCollector.initialize")
    def test_observe_phase_runs_ingestion_pipeline(
        self,
        mock_collector_initialize,
        mock_collector_execute,
        mock_collector_cleanup,
        mock_preprocessor_initialize,
        mock_extractor_initialize,
        mock_preprocessor_execute,
        mock_extractor_execute,
        mock_preprocessor_cleanup,
        mock_extractor_cleanup,
        mock_semantic_initialize,
        mock_semantic_execute,
        mock_semantic_cleanup,
    ):
        mock_collector_initialize.return_value = True
        mock_collector_cleanup.return_value = True
        mock_preprocessor_initialize.return_value = True
        mock_extractor_initialize.return_value = True
        mock_preprocessor_cleanup.return_value = True
        mock_extractor_cleanup.return_value = True
        mock_semantic_initialize.return_value = True
        mock_semantic_cleanup.return_value = True

        mock_collector_execute.return_value = {
            "source": "ctext",
            "documents": [
                {
                    "urn": "ctp:analects/xue-er",
                    "title": "学而",
                    "text": "小柴胡汤方：柴胡半斤，黄芩三两。",
                    "children": []
                }
            ],
            "stats": {
                "document_count": 1,
                "chapter_count": 1,
                "line_count": 1,
                "char_count": 16
            },
            "errors": []
        }
        mock_preprocessor_execute.return_value = {
            "processed_text": "小柴胡汤方：柴胡半斤，黄芩三两。",
            "metadata": {"token_count": 8},
            "processing_steps": ["line_break_fix"]
        }
        mock_extractor_execute.return_value = {
            "entities": [
                {"name": "小柴胡汤", "type": "formula", "confidence": 0.95},
                {"name": "柴胡", "type": "herb", "confidence": 0.95}
            ],
            "statistics": {"total_count": 2, "by_type": {"formula": 1, "herb": 1}},
            "confidence_scores": {"average_confidence": 0.95}
        }
        mock_semantic_execute.return_value = {
            "semantic_graph": {
                "nodes": [{"id": "formula:小柴胡汤", "data": {}}],
                "edges": []
            },
            "graph_statistics": {
                "nodes_count": 2,
                "edges_count": 1,
                "relationships_by_type": {"sovereign": {"count": 1}}
            }
        }

        pipeline = ResearchPipeline(
            {
                "ctext_corpus": {
                    "enabled": True,
                    "whitelist": {
                        "enabled": True,
                        "path": "data/ctext_whitelist.json",
                        "default_groups": ["four_books"]
                    }
                },
                "observe_pipeline": {
                    "enabled": True
                }
            }
        )

        cycle = pipeline.create_research_cycle(
            cycle_name="observe_ingestion_test",
            description="测试 observe 首段主流程",
            objective="验证采集 -> 清洗 -> 抽取",
            scope="pipeline_test",
            researchers=["tester"]
        )
        self.assertTrue(pipeline.start_research_cycle(cycle.cycle_id))

        result = pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_preprocess_and_extract": True,
                "max_texts": 1,
                "max_chars_per_text": 200
            }
        )

        self.assertEqual(result["phase"], "observe")
        self.assertTrue(result["metadata"]["downstream_processing"])
        self.assertEqual(result["ingestion_pipeline"]["processed_document_count"], 1)
        self.assertEqual(result["ingestion_pipeline"]["aggregate"]["total_entities"], 2)
        self.assertEqual(result["ingestion_pipeline"]["aggregate"]["entity_type_counts"]["formula"], 1)
        self.assertEqual(result["ingestion_pipeline"]["aggregate"]["semantic_graph_nodes"], 2)
        self.assertEqual(result["ingestion_pipeline"]["aggregate"]["semantic_graph_edges"], 1)
        self.assertEqual(result["ingestion_pipeline"]["documents"][0]["title"], "学而")
        self.assertEqual(result["ingestion_pipeline"]["documents"][0]["semantic_graph_nodes"], 2)
        self.assertTrue(result["metadata"]["semantic_modeling"])
        self.assertIn("关系", result["findings"][-1])


if __name__ == "__main__":
    unittest.main()
