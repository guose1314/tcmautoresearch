import logging
import unittest
from unittest.mock import ANY, patch

from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_demo_handler import execute_demo_branch
from src.cycle.cycle_plugin_workflow_handlers import PluginWorkflowDispatchConfig


def _storage_conn(_args):
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


class TestCycleDemoHandler(unittest.TestCase):
    def test_demo_branch_delegates_core_demo_handler(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--demo-type", "basic", "--iterations", "5"])
        with patch(
            "src.cycle.cycle_demo_handler.cycle_core_demo_handler.execute_core_demo_workflow_handler",
            return_value=0,
        ) as core_handler, patch(
            "src.cycle.cycle_demo_handler.execute_plugin_workflow_steps",
            return_value=0,
        ) as execute_steps:
            rc = execute_demo_branch(
                args=args,
                logger=logging.getLogger("test.cycle.demo"),
                run_full_cycle_demo_fn=_completed_result,
                run_academic_demo_fn=_ok_result,
                run_performance_demo_fn=_ok_result,
                run_autorresearch_workflow_fn=_completed_result,
                build_storage_connection_from_args_fn=_storage_conn,
                run_paper_plugin_workflow_fn=_completed_result,
                run_arxiv_fine_translation_workflow_fn=_completed_result,
                run_md_translate_workflow_fn=_completed_result,
                run_pdf_translation_workflow_fn=_completed_result,
                run_arxiv_quick_helper_workflow_fn=_ok_result,
                run_google_scholar_helper_workflow_fn=_ok_result,
            )

        self.assertEqual(rc, 0)
        core_handler.assert_called_once_with(
            args,
            ANY,
            _completed_result,
            _ok_result,
            _ok_result,
        )
        execute_steps.assert_called_once()

    def test_demo_branch_builds_and_executes_plugin_workflow_steps(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args([])
        workflow_steps = (object(), object())

        with patch(
            "src.cycle.cycle_demo_handler.cycle_core_demo_handler.execute_core_demo_workflow_handler",
            return_value=0,
        ), patch(
            "src.cycle.cycle_demo_handler.build_plugin_workflow_steps",
            return_value=workflow_steps,
        ) as build_steps, patch(
            "src.cycle.cycle_demo_handler.execute_plugin_workflow_steps",
            return_value=1,
        ) as execute_steps:
            rc = execute_demo_branch(
                args=args,
                logger=logging.getLogger("test.cycle.demo"),
                run_full_cycle_demo_fn=_completed_result,
                run_academic_demo_fn=_ok_result,
                run_performance_demo_fn=_ok_result,
                run_autorresearch_workflow_fn=_completed_result,
                build_storage_connection_from_args_fn=_storage_conn,
                run_paper_plugin_workflow_fn=_completed_result,
                run_arxiv_fine_translation_workflow_fn=_completed_result,
                run_md_translate_workflow_fn=_completed_result,
                run_pdf_translation_workflow_fn=_completed_result,
                run_arxiv_quick_helper_workflow_fn=_ok_result,
                run_google_scholar_helper_workflow_fn=_ok_result,
            )

        self.assertEqual(rc, 1)
        build_steps.assert_called_once()
        workflow_config = build_steps.call_args.args[0]
        self.assertIsInstance(workflow_config, PluginWorkflowDispatchConfig)
        self.assertIs(workflow_config.args, args)
        self.assertEqual(workflow_config.logger.name, "test.cycle.demo")
        self.assertIs(workflow_config.run_autorresearch_workflow_fn, _completed_result)
        self.assertIs(workflow_config.build_storage_connection_from_args_fn, _storage_conn)
        self.assertIs(workflow_config.run_paper_plugin_workflow_fn, _completed_result)
        self.assertIs(workflow_config.run_arxiv_fine_translation_workflow_fn, _completed_result)
        self.assertIs(workflow_config.run_md_translate_workflow_fn, _completed_result)
        self.assertIs(workflow_config.run_pdf_translation_workflow_fn, _completed_result)
        self.assertIs(workflow_config.run_arxiv_quick_helper_workflow_fn, _ok_result)
        self.assertIs(workflow_config.run_google_scholar_helper_workflow_fn, _ok_result)
        execute_steps.assert_called_once_with(workflow_steps)

    def test_paper_plugin_requires_input(self):
        parser = build_cycle_demo_arg_parser()
        args = parser.parse_args(["--enable-paper-plugin"])

        rc = execute_demo_branch(
            args=args,
            logger=logging.getLogger("test.cycle.demo"),
            run_full_cycle_demo_fn=_ok_result,
            run_academic_demo_fn=_ok_result,
            run_performance_demo_fn=_ok_result,
            run_autorresearch_workflow_fn=_completed_result,
            build_storage_connection_from_args_fn=_storage_conn,
            run_paper_plugin_workflow_fn=_completed_result,
            run_arxiv_fine_translation_workflow_fn=_completed_result,
            run_md_translate_workflow_fn=_completed_result,
            run_pdf_translation_workflow_fn=_completed_result,
            run_arxiv_quick_helper_workflow_fn=_ok_result,
            run_google_scholar_helper_workflow_fn=_ok_result,
        )

        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
