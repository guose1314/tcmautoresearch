import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestResearchPipelineLiterature(unittest.TestCase):
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_observe_phase_runs_literature_pipeline(self, mock_search, mock_close):
        mock_close.return_value = None
        mock_search.return_value = {
            "query": "traditional chinese medicine AND shanghan",
            "sources": ["pubmed", "arxiv"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "TCM for COVID-19 randomized trial",
                    "authors": ["A", "B"],
                    "year": 2023,
                    "doi": "10.1000/test",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "abstract": "Randomized trial shows efficacy and safety of traditional chinese medicine formula.",
                    "citation_count": 12,
                    "external_id": "1",
                },
                {
                    "source": "arxiv",
                    "title": "Machine learning for TCM formula mining",
                    "authors": ["C"],
                    "year": 2024,
                    "doi": "",
                    "url": "http://arxiv.org/abs/1234",
                    "abstract": "A machine learning cohort-like design for TCM network analysis.",
                    "citation_count": None,
                    "external_id": "1234",
                },
            ],
            "query_plans": [],
            "source_stats": {
                "pubmed": {"count": 1, "mode": "open_api", "source_name": "PubMed"},
                "arxiv": {"count": 1, "mode": "open_api", "source_name": "arXiv"},
            },
            "errors": [],
        }

        pipeline = ResearchPipeline(
            {
                "literature_retrieval": {
                    "enabled": True,
                    "max_results_per_source": 3,
                }
            }
        )

        cycle = pipeline.create_research_cycle(
            cycle_name="observe_literature_test",
            description="测试 observe 文献链路",
            objective="检索 -> 摘要 -> 证据矩阵",
            scope="literature_pipeline",
            researchers=["tester"],
        )
        self.assertTrue(pipeline.start_research_cycle(cycle.cycle_id))

        result = pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": True,
                "literature_query": "traditional chinese medicine AND shanghan",
                "run_preprocess_and_extract": False,
            },
        )

        self.assertEqual(result["phase"], "observe")
        self.assertIn("literature_pipeline", result)
        self.assertTrue(result["metadata"]["literature_retrieval"])
        self.assertTrue(result["metadata"]["evidence_matrix"])

        literature = result["literature_pipeline"]
        self.assertEqual(literature["record_count"], 2)
        self.assertEqual(literature["abstract_summary_count"], 2)
        self.assertEqual(literature["evidence_matrix"]["record_count"], 2)
        self.assertEqual(literature["evidence_matrix"]["dimension_count"], 4)

        top_record = literature["evidence_matrix"]["records"][0]
        self.assertGreaterEqual(top_record["coverage_score"], 1)

        mock_search.assert_called_once()
        search_kwargs = mock_search.call_args.kwargs
        self.assertEqual(search_kwargs["query"], "traditional chinese medicine AND shanghan")
        self.assertEqual(search_kwargs["max_results_per_source"], 3)


if __name__ == "__main__":
    unittest.main()
