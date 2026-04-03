import json
import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestResearchPipelineClinicalGap(unittest.TestCase):
    @patch("src.research.research_pipeline.CachedLLMService.from_gap_config")
    @patch("src.research.research_pipeline.GapAnalyzer.cleanup")
    @patch("src.research.research_pipeline.GapAnalyzer.execute")
    @patch("src.research.research_pipeline.GapAnalyzer.initialize")
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_observe_phase_runs_qwen_clinical_gap_analysis(
        self,
        mock_search,
        mock_close,
        mock_init,
        mock_execute,
        mock_cleanup,
        mock_gap_service,
    ):
        class _FakeService:
            def load(self):
                return None

            def unload(self):
                return None

            def cache_stats(self):
                return {"session_hits": 0, "session_misses": 1}

        mock_close.return_value = None
        mock_init.return_value = True
        mock_cleanup.return_value = True
        mock_execute.return_value = {
            "clinical_question": "TCM 对 COVID-19 的有效性与安全性证据缺口是什么？",
            "output_language": "zh",
            "report": """临床问题重述: ...\n关键缺口: ...\n研究建议: ...""",
            "gaps": [
                {
                    "dimension": "outcome",
                    "title": "关键结局覆盖不足",
                    "limitation": "安全性终点偏少",
                    "priority": "高",
                }
            ],
            "priority_summary": {
                "counts": {"高": 1, "中": 0, "低": 0},
                "highest_priority": "高",
                "total_gaps": 1,
            },
            "metadata": {"used_llm_refinement": True},
        }
        mock_gap_service.return_value = _FakeService()

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
        self.assertEqual(literature["clinical_gap_analysis"]["gaps"][0]["priority"], "高")
        self.assertEqual(literature["clinical_gap_analysis"]["priority_summary"]["highest_priority"], "高")

        mock_search.assert_called_once()
        mock_gap_service.assert_called_once()
        mock_init.assert_called_once()
        mock_execute.assert_called_once()
        mock_cleanup.assert_called_once()

        execute_context = mock_execute.call_args.args[0]
        self.assertEqual(execute_context["clinical_question"], "TCM 对 COVID-19 的有效性与安全性证据缺口是什么？")
        self.assertEqual(execute_context["literature_query"], "tcm covid efficacy")
        self.assertEqual(len(execute_context["literature_summaries"]), 1)

    @patch("src.research.research_pipeline.CachedLLMService.from_gap_config")
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_observe_phase_supports_clinical_gap_json_mode(self, mock_search, mock_close, mock_gap_service):
        class _FakeService:
            def load(self):
                return None

            def unload(self):
                return None

            def cache_stats(self):
                return {"session_hits": 0, "session_misses": 1}

            def generate(self, prompt, system_prompt=""):
                return (
                    '{'
                    '"clinical_question":"机器链路问题",'
                    '"coverage_overview":{"literature_count":1},'
                    '"gaps":[{"dimension":"outcome","title":"关键结局覆盖不足","limitation":"安全性终点偏少","priority":"high"}],'
                    '"priority_summary":{"counts":{"高":1,"中":0,"低":0},"highest_priority":"高","total_gaps":1},'
                    '"recommendations":[{"target_gap":"outcome","study_design":"随机对照","inclusion_criteria":"明确证候","primary_endpoint":"主要结局"}]'
                    '}'
                )

        mock_close.return_value = None
        mock_gap_service.return_value = _FakeService()
        mock_search.return_value = {
            "query": "tcm covid efficacy",
            "sources": ["pubmed"],
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
                "literature_retrieval": {"enabled": True, "max_results_per_source": 2},
                "clinical_gap_analysis": {"enabled": True, "output_mode": "json"},
            }
        )
        cycle = pipeline.create_research_cycle(
            cycle_name="clinical_gap_json_test",
            description="测试临床缺口 JSON 模式",
            objective="检索 -> 证据矩阵 -> JSON gap",
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
                "clinical_question": "机器链路问题",
                "literature_query": "tcm covid efficacy",
                "run_preprocess_and_extract": False,
            },
        )

        payload = result["literature_pipeline"]["clinical_gap_analysis"]
        report_payload = json.loads(payload["report"])
        self.assertEqual(payload["metadata"]["output_mode"], "json")
        self.assertEqual(report_payload["priority_summary"]["highest_priority"], "高")
        self.assertEqual(payload["json_payload"]["gaps"][0]["dimension"], "outcome")
        pipeline.cleanup()


if __name__ == "__main__":
    unittest.main()
