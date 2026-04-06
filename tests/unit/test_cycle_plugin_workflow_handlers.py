import logging
import unittest
from unittest.mock import Mock

from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_plugin_workflow_handlers import (
    PluginWorkflowDispatchConfig,
    PluginWorkflowStep,
    build_plugin_workflow_steps,
    build_storage_connection_kwargs,
    execute_arxiv_fine_translation_workflow_handler,
    execute_arxiv_helper_workflow_handler,
    execute_autorresearch_workflow_handler,
    execute_md_translate_workflow_handler,
    execute_paper_plugin_workflow_handler,
    execute_pdf_translation_workflow_handler,
    execute_plugin_workflow_steps,
    execute_scholar_helper_workflow_handler,
)

LOGGER = logging.getLogger("test.cycle.plugin.handlers")


def _storage_conn(_args):
    return {
        "pg_url": "postgresql://u:p@localhost:5432/db",
        "neo4j_uri": "neo4j://localhost:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "pwd",
    }


class TestCyclePluginWorkflowHandlers(unittest.TestCase):
    def test_build_storage_connection_kwargs_extracts_shared_storage_fields(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args([])

        storage_kwargs = build_storage_connection_kwargs(args, _storage_conn)

        self.assertEqual(
            storage_kwargs,
            {
                "pg_url": "postgresql://u:p@localhost:5432/db",
                "neo4j_uri": "neo4j://localhost:7687",
                "neo4j_user": "neo4j",
                "neo4j_password": "pwd",
            },
        )

    def test_build_plugin_workflow_steps_returns_all_handlers(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args([])

        workflow_config = PluginWorkflowDispatchConfig(
            args=args,
            logger=LOGGER,
            run_autorresearch_workflow_fn=lambda **_kwargs: {"status": "completed"},
            build_storage_connection_from_args_fn=_storage_conn,
            run_paper_plugin_workflow_fn=lambda **_kwargs: {"status": "completed"},
            run_arxiv_fine_translation_workflow_fn=lambda **_kwargs: {"status": "completed"},
            run_md_translate_workflow_fn=lambda **_kwargs: {"status": "completed"},
            run_pdf_translation_workflow_fn=lambda **_kwargs: {"status": "completed"},
            run_arxiv_quick_helper_workflow_fn=lambda **_kwargs: {"status": "ok"},
            run_google_scholar_helper_workflow_fn=lambda **_kwargs: {"status": "ok"},
        )
        workflow_steps = build_plugin_workflow_steps(workflow_config)

        self.assertEqual(len(workflow_steps), 7)
        self.assertIs(workflow_steps[0].args[0], args)
        self.assertIs(workflow_steps[0].args[1], LOGGER)

    def test_execute_plugin_workflow_steps_stops_on_first_failure(self):
        first_handler = Mock(return_value=1)
        second_handler = Mock(return_value=0)
        workflow_steps = (
            PluginWorkflowStep(first_handler, ("first",)),
            PluginWorkflowStep(second_handler, ("second",)),
        )

        rc = execute_plugin_workflow_steps(workflow_steps)

        self.assertEqual(rc, 1)
        first_handler.assert_called_once_with("first")
        second_handler.assert_not_called()

    def test_autorresearch_handler_forwards_args(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(
            [
                "--enable-autorresearch",
                "--autorresearch-instruction",
                "优化脚本",
                "--autorresearch-iters",
                "4",
                "--autorresearch-timeout",
                "120",
                "--autorresearch-strategy",
                "llm",
            ]
        )
        captured = {}

        def fake_workflow(**kwargs):
            captured.update(kwargs)
            return {"status": "completed"}

        rc = execute_autorresearch_workflow_handler(args, LOGGER, fake_workflow)

        self.assertEqual(rc, 0)
        self.assertEqual(captured["instruction"], "优化脚本")
        self.assertEqual(captured["max_iters"], 4)
        self.assertEqual(captured["timeout_seconds"], 120)
        self.assertEqual(captured["strategy"], "llm")

    def test_paper_plugin_handler_requires_input(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-paper-plugin"])

        rc = execute_paper_plugin_workflow_handler(args, LOGGER, _storage_conn, lambda **_kwargs: {"status": "completed"})

        self.assertEqual(rc, 1)

    def test_paper_plugin_handler_forwards_storage(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-paper-plugin", "--paper-input", "demo.pdf", "--paper-persist-storage"])
        captured = {}

        def fake_workflow(**kwargs):
            captured.update(kwargs)
            return {"status": "completed"}

        rc = execute_paper_plugin_workflow_handler(args, LOGGER, _storage_conn, fake_workflow)

        self.assertEqual(rc, 0)
        self.assertEqual(captured["source_path"], "demo.pdf")
        self.assertTrue(captured["persist_storage"])
        self.assertEqual(captured["pg_url"], "postgresql://u:p@localhost:5432/db")

    def test_arxiv_fine_translation_handler_requires_input_and_daas(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-arxiv-fine-translation"])

        rc = execute_arxiv_fine_translation_workflow_handler(args, LOGGER, _storage_conn, lambda **_kwargs: {"status": "completed"})

        self.assertEqual(rc, 1)

    def test_md_translate_handler_requires_input(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-md-translate"])

        rc = execute_md_translate_workflow_handler(args, LOGGER, _storage_conn, lambda **_kwargs: {"status": "completed"})

        self.assertEqual(rc, 1)

    def test_pdf_translation_handler_requires_input(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-pdf-translation"])

        rc = execute_pdf_translation_workflow_handler(args, LOGGER, _storage_conn, lambda **_kwargs: {"status": "completed"})

        self.assertEqual(rc, 1)

    def test_arxiv_helper_handler_requires_url(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-arxiv-helper"])

        rc = execute_arxiv_helper_workflow_handler(args, LOGGER, _storage_conn, lambda **_kwargs: {"status": "ok"})

        self.assertEqual(rc, 1)

    def test_scholar_helper_handler_requires_url(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-scholar-helper"])

        rc = execute_scholar_helper_workflow_handler(args, LOGGER, _storage_conn, lambda **_kwargs: {"status": "ok"})

        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
