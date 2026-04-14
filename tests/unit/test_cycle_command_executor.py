import logging
import unittest
from unittest.mock import patch

from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_command_executor import execute_cycle_demo_command


def _default_storage_conn(_args):
    return {
        "pg_url": "postgresql://u:p@localhost:5432/db",
        "neo4j_uri": "neo4j://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "pwd",
    }


def _completed_result(*_args, **_kwargs):
    return {"status": "completed"}


def _ok_result(*_args, **_kwargs):
    return {"status": "ok"}


class TestCycleCommandExecutor(unittest.TestCase):
    def test_research_mode_requires_question(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--mode", "research"])

        called = {"research": False}

        def fake_research(**_kwargs):
            called["research"] = True
            return {"status": "completed"}

        rc = execute_cycle_demo_command(
            args=args,
            logger=logging.getLogger("test.cycle.executor"),
            setup_signal_handlers_fn=lambda: None,
            run_research_session_fn=fake_research,
            run_full_cycle_demo_fn=_ok_result,
            run_academic_demo_fn=_ok_result,
            run_performance_demo_fn=_ok_result,
            run_autorresearch_workflow_fn=_completed_result,
            build_storage_connection_from_args_fn=_default_storage_conn,
            run_paper_plugin_workflow_fn=_completed_result,
            run_arxiv_fine_translation_workflow_fn=_completed_result,
            run_md_translate_workflow_fn=_completed_result,
            run_pdf_translation_workflow_fn=_completed_result,
            run_arxiv_quick_helper_workflow_fn=lambda *_a, **_k: {"status": "ok"},
            run_google_scholar_helper_workflow_fn=lambda *_a, **_k: {"status": "ok"},
        )

        self.assertEqual(rc, 1)
        self.assertFalse(called["research"])

    def test_research_mode_forwards_report_fields(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(
            [
                "--config",
                "./config/test.yml",
                "--environment",
                "test",
                "--mode",
                "research",
                "--question",
                "测试问题",
                "--export-report",
                "--report-format",
                "markdown",
                "--report-format",
                "docx",
                "--report-output-dir",
                "./output/research_reports_custom",
            ]
        )

        captured = {}

        def fake_research(**kwargs):
            captured.update(kwargs)
            return {"status": "completed"}

        with patch(
            "src.cycle.cycle_research_handler.build_cycle_orchestrator_config",
            return_value={
                "pipeline_config": {"runtime": {"environment": "test"}},
                "runtime_profile": "demo_research",
            },
        ) as runtime_builder:
            rc = execute_cycle_demo_command(
                args=args,
                logger=logging.getLogger("test.cycle.executor"),
                setup_signal_handlers_fn=lambda: None,
                run_research_session_fn=fake_research,
                run_full_cycle_demo_fn=_ok_result,
                run_academic_demo_fn=_ok_result,
                run_performance_demo_fn=_ok_result,
                run_autorresearch_workflow_fn=_completed_result,
                build_storage_connection_from_args_fn=_default_storage_conn,
                run_paper_plugin_workflow_fn=_completed_result,
                run_arxiv_fine_translation_workflow_fn=_completed_result,
                run_md_translate_workflow_fn=_completed_result,
                run_pdf_translation_workflow_fn=_completed_result,
                run_arxiv_quick_helper_workflow_fn=lambda *_a, **_k: {"status": "ok"},
                run_google_scholar_helper_workflow_fn=lambda *_a, **_k: {"status": "ok"},
            )

        self.assertEqual(rc, 0)
        self.assertEqual(captured["question"], "测试问题")
        self.assertEqual(
            captured["config"],
            {
                "pipeline_config": {"runtime": {"environment": "test"}},
                "runtime_profile": "demo_research",
            },
        )
        self.assertEqual(captured["phase_names"], ["observe"])
        self.assertEqual(captured["export_report_formats"], ["markdown", "docx"])
        self.assertEqual(captured["report_output_dir"], "./output/research_reports_custom")
        runtime_builder.assert_called_once_with(
            config_path="./config/test.yml",
            environment="test",
        )


if __name__ == "__main__":
    unittest.main()
