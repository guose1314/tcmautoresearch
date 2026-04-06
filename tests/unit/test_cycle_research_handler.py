import logging
import unittest

from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_research_handler import execute_research_branch


class TestCycleResearchHandler(unittest.TestCase):
    def test_requires_question(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--mode", "research"])

        called = {"research": False}

        def fake_research(**_kwargs):
            called["research"] = True
            return {"status": "completed"}

        rc = execute_research_branch(
            args=args,
            logger=logging.getLogger("test.cycle.research"),
            run_research_session_fn=fake_research,
        )

        self.assertEqual(rc, 1)
        self.assertFalse(called["research"])

    def test_forwards_report_fields(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(
            [
                "--mode",
                "research",
                "--question",
                "测试问题",
                "--research-phases",
                "observe,publish",
                "--export-report",
                "--report-format",
                "markdown",
                "--report-format",
                "docx",
            ]
        )

        captured = {}

        def fake_research(**kwargs):
            captured.update(kwargs)
            return {"status": "completed"}

        rc = execute_research_branch(
            args=args,
            logger=logging.getLogger("test.cycle.research"),
            run_research_session_fn=fake_research,
        )

        self.assertEqual(rc, 0)
        self.assertEqual(captured["question"], "测试问题")
        self.assertEqual(captured["phase_names"], ["observe", "publish"])
        self.assertEqual(captured["export_report_formats"], ["markdown", "docx"])


if __name__ == "__main__":
    unittest.main()
