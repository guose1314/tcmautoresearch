import os
import unittest
from unittest.mock import patch

from src.cycle.cycle_cli import build_cycle_demo_arg_parser


class TestCycleCliParser(unittest.TestCase):
    def test_parser_defaults(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args([])

        self.assertEqual(args.mode, "demo")
        self.assertEqual(args.demo_type, "full")
        self.assertEqual(args.iterations, 3)
        self.assertEqual(args.report_output_dir, "./output/research_reports")
        self.assertEqual(args.scholar_max_papers, 20)

    def test_parser_repeated_report_format(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--report-format", "markdown", "--report-format", "docx"])

        self.assertEqual(args.report_format, ["markdown", "docx"])

    def test_parser_arxiv_daas_url_follows_env_default(self):
        with patch.dict(os.environ, {"ARXIV_DAAS_URL": "http://localhost:18000/stream"}, clear=False):
            parser = build_cycle_demo_arg_parser()
            args = parser.parse_args([])

        self.assertEqual(args.arxiv_daas_url, "http://localhost:18000/stream")


if __name__ == "__main__":
    unittest.main()
