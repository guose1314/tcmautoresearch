import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestResearchPipelineClinicalGap(unittest.TestCase):
    @patch("src.research.research_pipeline.LLMEngine.unload")
    @patch("src.research.research_pipeline.LLMEngine.clinical_gap_analysis")
    @patch("src.research.research_pipeline.LLMEngine.load")
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_observe_phase_runs_qwen_clinical_gap_analysis(
        self,
        mock_search,
        mock_close,
        mock_load,
        mock_gap,
        mock_unload,
    ):
        mock_close.return_value = None
        mock_load.return_value = None
        mock_unload.return_value = None
        mock_gap.return_value = """临床问题重述: ...\n关键缺口: ...\n研究建议: ..."""

        mock_search.return_value = {
            "query": "tcm covid efficacy",
            "sources": ["pubmed", "arxiv"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "Randomized trial on TCM formula",
                    "authors": ["A"],
                    "year": 2022,
                    "doi": "10.1000/abc",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "abstract": "Randomized and cohort evidence on efficacy and safety.",
                    "citation_count": 10,
                    "external_id": "1",
                }
            ],
            "query_plans": [],
            "source_stats": {
                "pubmed": {"count": 1, "mode": "open_api", "source_name": "PubMed"}
            },
            "errors": [],
        }

        pipeline = ResearchPipeline(
            {
                "literature_retrieval": {
                    "enabled": True,
                    "max_results_per_source": 2,
                },
                "clinical_gap_analysis": {
                    "enabled": True,
                    "max_tokens": 256,
                },
            }
        )

        cycle = pipeline.create_research_cycle(
            cycle_name="clinical_gap_test",
            description="测试临床缺口分析",
            objective="检索 -> 证据矩阵 -> Qwen gap",
            scope="observe",
            researchers=["tester"],
        )
        self.assertTrue(pipeline.start_research_cycle(cycle.cycle_id))

        result = pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": True,
                "run_clinical_gap_analysis": True,
                "literature_query": "tcm covid efficacy",
                "clinical_question": "TCM 对 COVID-19 的有效性与安全性证据缺口是什么？",
                "run_preprocess_and_extract": False,
            },
        )

        self.assertEqual(result["phase"], "observe")
        self.assertTrue(result["metadata"]["clinical_gap_analysis"])

        literature = result["literature_pipeline"]
        self.assertIn("clinical_gap_analysis", literature)
        self.assertIn("report", literature["clinical_gap_analysis"])
        self.assertIn("关键缺口", literature["clinical_gap_analysis"]["report"])

        mock_search.assert_called_once()
        mock_load.assert_called_once()
        mock_gap.assert_called_once()
        mock_unload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
