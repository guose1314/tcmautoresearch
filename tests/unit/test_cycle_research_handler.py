import logging
import unittest
from unittest.mock import patch

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
                "--config",
                "./config/production.yml",
                "--environment",
                "production",
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

        with patch(
            "src.cycle.cycle_research_handler.build_cycle_orchestrator_config",
            return_value={
                "pipeline_config": {"runtime": {"environment": "production"}},
                "runtime_profile": "demo_research",
            },
        ) as runtime_builder:
            rc = execute_research_branch(
                args=args,
                logger=logging.getLogger("test.cycle.research"),
                run_research_session_fn=fake_research,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(captured["question"], "测试问题")
        self.assertEqual(
            captured["config"],
            {
                "pipeline_config": {"runtime": {"environment": "production"}},
                "runtime_profile": "demo_research",
            },
        )
        self.assertEqual(captured["phase_names"], ["observe", "publish"])
        self.assertEqual(captured["export_report_formats"], ["markdown", "docx"])
        runtime_builder.assert_called_once_with(
            config_path="./config/production.yml",
            environment="production",
        )

    def test_partial_status_returns_non_zero(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(
            [
                "--mode",
                "research",
                "--question",
                "测试问题",
            ]
        )

        rc = execute_research_branch(
            args=args,
            logger=logging.getLogger("test.cycle.research"),
            run_research_session_fn=lambda **_kwargs: {"status": "partial"},
        )

        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
