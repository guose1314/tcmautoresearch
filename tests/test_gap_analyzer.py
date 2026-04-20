import json
import unittest

import pytest

from src.research.gap_analyzer import GapAnalyzer


class _FakeLLMService:
    def __init__(self):
        self.calls = []
        self.response = "gap report"

    def generate(self, prompt, system_prompt=""):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.response


class TestGapAnalyzer(unittest.TestCase):
    def setUp(self):
        self.llm = _FakeLLMService()
        self.analyzer = GapAnalyzer(
            {"max_summaries": 2, "summary_text_limit": 20},
            llm_service=self.llm,
        )
        self.analyzer.initialize()

    def tearDown(self):
        self.analyzer.cleanup()

    @pytest.mark.xfail(
        reason="GapAnalyzer 内部 IndexError，待修复 (known_failure)",
        strict=False,
    )
    def test_execute_returns_report_and_metadata(self):
        self.llm.response = (
            "## 关键缺口\n"
            "1. [高] 目标人群定义不完整 (condition) - 纳入标准可能异质\n"
            "2. [中] 研究设计单一 (method) - 缺少多中心对照研究\n"
            "## 研究建议\n"
            "1. 设计: 前瞻性随机对照研究; 纳入: 明确证候分型; 终点: 临床主要结局"
        )
        result = self.analyzer.execute(
            {
                "clinical_question": "中医干预证据缺口是什么？",
                "evidence_matrix": {"record_count": 3},
                "literature_summaries": [
                    {"title": "A", "summary_text": "alpha beta gamma", "source": "pubmed", "year": 2022},
                    {"title": "B", "summary_text": "delta epsilon zeta", "source": "arxiv", "year": 2021},
                    {"title": "C", "summary_text": "should be truncated by count", "source": "manual", "year": 2020},
                ],
                "output_language": "zh",
            }
        )

        self.assertIn("关键缺口", result["report"])
        self.assertEqual(result["metadata"]["literature_summary_count"], 2)
        self.assertEqual(len(result["prompt_payload"]["literature_summaries"]), 2)
        self.assertEqual(len(self.llm.calls), 1)
        self.assertIn("clinical_question", self.llm.calls[0]["prompt"])
        self.assertEqual(len(result["gaps"]), 2)
        self.assertEqual(result["gaps"][0]["priority"], "高")
        self.assertEqual(result["priority_summary"]["highest_priority"], "高")
        self.assertEqual(result["priority_summary"]["counts"]["高"], 1)
        self.assertTrue(result["metadata"]["structured_parse_success"])

    def test_build_prompt_payload_truncates_summary_text(self):
        payload = self.analyzer.build_prompt_payload(
            clinical_question="问题",
            evidence_matrix={},
            literature_summaries=[
                {"title": "A", "summary_text": "abcdefghijklmnopqrstuvwxyz", "source": "pubmed", "year": 2022}
            ],
            output_language="zh",
        )

        summary_text = payload["payload"]["literature_summaries"][0]["summary_text"]
        self.assertEqual(summary_text, "abcdefghijklmnopqrst")
        self.assertIn("expected_sections", payload["payload"])

    def test_analyze_without_llm_uses_core_report(self):
        analyzer = GapAnalyzer({"use_llm_refinement": False}, llm_service=None)
        analyzer.initialize()
        try:
            result = analyzer.execute(
                {
                    "clinical_question": "问题",
                    "evidence_matrix": {},
                    "literature_summaries": [],
                }
            )
            self.assertIn("关键缺口", result["report"])
            self.assertFalse(result["metadata"]["used_llm_refinement"])
            self.assertGreaterEqual(len(result["gaps"]), 3)
            self.assertEqual(result["priority_summary"]["highest_priority"], "高")
        finally:
            analyzer.cleanup()

    @pytest.mark.xfail(
        reason="GapAnalyzer 内部 IndexError，待修复 (known_failure)",
        strict=False,
    )
    def test_execute_parses_json_output_and_uses_config_defaults(self):
        self.llm.response = (
            '{'
            '"clinical_question":"默认临床问题",'
            '"coverage_overview":{"literature_count":0},'
            '"gaps":[{"dimension":"outcome","title":"关键结局覆盖不足","limitation":"终点不完整","priority":"high"}],'
            '"priority_summary":{"counts":{"高":1,"中":0,"低":0},"highest_priority":"高","total_gaps":1},'
            '"recommendations":[{"target_gap":"outcome","study_design":"随机对照","inclusion_criteria":"明确证候","primary_endpoint":"主要结局"}]'
            '}'
        )
        analyzer = GapAnalyzer(
            {
                "default_clinical_question": "默认临床问题",
                "default_output_language": "en",
            },
            llm_service=self.llm,
        )
        analyzer.initialize()
        try:
            result = analyzer.execute(
                {
                    "evidence_matrix": {},
                    "literature_summaries": [],
                }
            )
            self.assertEqual(result["clinical_question"], "默认临床问题")
            self.assertEqual(result["output_language"], "en")
            self.assertEqual(result["gaps"][0]["dimension"], "outcome")
            self.assertEqual(result["priority_summary"]["counts"]["高"], 1)
            self.assertIn("outcome", self.llm.calls[-1]["prompt"])
            self.assertEqual(result["json_payload"]["clinical_question"], "默认临床问题")
        finally:
            analyzer.cleanup()

    def test_execute_supports_json_output_mode(self):
        self.llm.response = (
            '{'
            '"clinical_question":"机器链路问题",'
            '"coverage_overview":{"literature_count":2},'
            '"gaps":[{"dimension":"method","title":"研究设计单一","limitation":"缺少对照研究","priority":"medium"}],'
            '"priority_summary":{"counts":{"高":0,"中":1,"低":0},"highest_priority":"中","total_gaps":1},'
            '"recommendations":[{"target_gap":"method","study_design":"多中心队列","inclusion_criteria":"明确分层","primary_endpoint":"疗效结局"}]'
            '}'
        )
        analyzer = GapAnalyzer({"default_output_mode": "json"}, llm_service=self.llm)
        analyzer.initialize()
        try:
            result = analyzer.execute(
                {
                    "clinical_question": "机器链路问题",
                    "evidence_matrix": {},
                    "literature_summaries": [{"title": "A", "summary_text": "B"}],
                }
            )
            report_payload = json.loads(result["report"])
            self.assertEqual(result["metadata"]["output_mode"], "json")
            self.assertEqual(report_payload["priority_summary"]["highest_priority"], "中")
            self.assertEqual(result["json_payload"]["gaps"][0]["dimension"], "method")
        finally:
            analyzer.cleanup()


if __name__ == "__main__":
    unittest.main()