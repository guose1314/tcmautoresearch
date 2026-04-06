"""
run_cycle_demo demo 分支处理器。
"""

import argparse
import logging
from typing import Any, Callable, Dict

from . import cycle_core_demo_handler
from .cycle_plugin_workflow_handlers import (
    PluginWorkflowDispatchConfig,
    build_plugin_workflow_steps,
    execute_plugin_workflow_steps,
)

WorkflowFn = Callable[..., Dict[str, Any]]
StorageConnFn = Callable[[argparse.Namespace], Dict[str, str]]


def execute_demo_branch(
    args: argparse.Namespace,
    logger: logging.Logger,
    run_full_cycle_demo_fn: WorkflowFn,
    run_academic_demo_fn: WorkflowFn,
    run_performance_demo_fn: WorkflowFn,
    run_autorresearch_workflow_fn: WorkflowFn,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_paper_plugin_workflow_fn: WorkflowFn,
    run_arxiv_fine_translation_workflow_fn: WorkflowFn,
    run_md_translate_workflow_fn: WorkflowFn,
    run_pdf_translation_workflow_fn: WorkflowFn,
    run_arxiv_quick_helper_workflow_fn: WorkflowFn,
    run_google_scholar_helper_workflow_fn: WorkflowFn,
) -> int:
    """执行 demo 模式及其附加子流程。"""
    status_code = cycle_core_demo_handler.execute_core_demo_workflow_handler(
        args,
        logger,
        run_full_cycle_demo_fn,
        run_academic_demo_fn,
        run_performance_demo_fn,
    )
    if status_code != 0:
        return status_code

    plugin_workflow_config = PluginWorkflowDispatchConfig(
        args=args,
        logger=logger,
        run_autorresearch_workflow_fn=run_autorresearch_workflow_fn,
        build_storage_connection_from_args_fn=build_storage_connection_from_args_fn,
        run_paper_plugin_workflow_fn=run_paper_plugin_workflow_fn,
        run_arxiv_fine_translation_workflow_fn=run_arxiv_fine_translation_workflow_fn,
        run_md_translate_workflow_fn=run_md_translate_workflow_fn,
        run_pdf_translation_workflow_fn=run_pdf_translation_workflow_fn,
        run_arxiv_quick_helper_workflow_fn=run_arxiv_quick_helper_workflow_fn,
        run_google_scholar_helper_workflow_fn=run_google_scholar_helper_workflow_fn,
    )
    plugin_workflow_steps = build_plugin_workflow_steps(plugin_workflow_config)
    status_code = execute_plugin_workflow_steps(plugin_workflow_steps)
    if status_code != 0:
        return status_code

    logger.info("=== 演示完成 ===")
    return 0
