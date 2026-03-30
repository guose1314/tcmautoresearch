import unittest
from unittest.mock import patch

from src.research.google_scholar_helper import ScholarPaperItem, run_google_scholar_related_works


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self, html: str):
        self._html = html

    def get(self, url: str, timeout: int = 30):
        return _FakeResponse(self._html)


class TestGoogleScholarHelperOptions(unittest.TestCase):
    @patch("src.research.google_scholar_helper._run_llm_prompt", return_value="")
    @patch("src.research.google_scholar_helper._parse_google_scholar_html")
    @patch("src.research.google_scholar_helper._build_session")
    def test_run_related_works_accepts_legacy_positional_options(self, mock_build_session, mock_parse, _mock_llm):
        mock_build_session.return_value = _FakeSession("<html></html>")
        mock_parse.return_value = [
            ScholarPaperItem(
                title="T",
                authors_venue="A - V, 2024",
                snippet="S",
                citations=1,
                year="2024",
                url="https://example.com",
                author_year_citation="(A, 2024)",
            )
        ]

        result = run_google_scholar_related_works(
            "https://scholar.google.com/scholar?q=tcm",
            "./output/google_scholar_helper",
            5,
            "topic",
            "Chinese",
            False,
            None,
            "extra",
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.total_papers, 1)
        self.assertEqual(mock_parse.call_args.kwargs["max_papers"], 5)


if __name__ == "__main__":
    unittest.main()
