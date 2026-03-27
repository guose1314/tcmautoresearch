import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestResearchPipelineObserve(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
