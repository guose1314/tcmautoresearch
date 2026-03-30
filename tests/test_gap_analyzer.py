import unittest

from src.research.gap_analyzer import GapAnalyzer


class _FakeLLMService:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, system_prompt=""):
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return "gap report"


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

    def test_execute_returns_report_and_metadata(self):
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

        self.assertEqual(result["report"], "gap report")
        self.assertEqual(result["metadata"]["literature_summary_count"], 2)
        self.assertEqual(len(result["prompt_payload"]["literature_summaries"]), 2)
        self.assertEqual(len(self.llm.calls), 1)
        self.assertIn("clinical_question", self.llm.calls[0]["prompt"])

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
        finally:
            analyzer.cleanup()


if __name__ == "__main__":
    unittest.main()