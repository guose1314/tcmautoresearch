"""
run_cycle_demo 命令执行器。

该模块负责 main() 的业务分发逻辑，不处理参数定义。
"""

import argparse
import logging
import traceback
from typing import Any, Callable, Dict

from .cycle_demo_handler import execute_demo_branch
from .cycle_research_handler import execute_research_branch


def execute_cycle_demo_command(
    args: argparse.Namespace,
    logger: logging.Logger,
    setup_signal_handlers_fn: Callable[[], None],
    run_research_session_fn: Callable[..., Dict[str, Any]],
    run_full_cycle_demo_fn: Callable[..., Dict[str, Any]],
    run_academic_demo_fn: Callable[..., Dict[str, Any]],
    run_performance_demo_fn: Callable[..., Dict[str, Any]],
    run_autorresearch_workflow_fn: Callable[..., Dict[str, Any]],
    build_storage_connection_from_args_fn: Callable[[argparse.Namespace], Dict[str, str]],
    run_paper_plugin_workflow_fn: Callable[..., Dict[str, Any]],
    run_arxiv_fine_translation_workflow_fn: Callable[..., Dict[str, Any]],
    run_md_translate_workflow_fn: Callable[..., Dict[str, Any]],
    run_pdf_translation_workflow_fn: Callable[..., Dict[str, Any]],
    run_arxiv_quick_helper_workflow_fn: Callable[..., Dict[str, Any]],
    run_google_scholar_helper_workflow_fn: Callable[..., Dict[str, Any]],
) -> int:
    """执行 run_cycle_demo 命令分发逻辑。"""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("中医古籍全自动研究系统迭代循环演示启动")
    logger.info("演示类型: %s", args.demo_type)
    logger.info("迭代次数: %s", args.iterations)
    logger.info("AutoResearch 启用: %s", args.enable_autorresearch)
    logger.info("论文插件启用: %s", args.enable_paper_plugin)
    logger.info("论文插件双库存档: %s", args.paper_persist_storage)
    logger.info("Arxiv精细翻译启用: %s", args.enable_arxiv_fine_translation)
    logger.info("Markdown翻译启用: %s", args.enable_md_translate)
    logger.info("PDF全文翻译启用: %s", args.enable_pdf_translation)
    logger.info("Arxiv快速助手启用: %s", args.enable_arxiv_helper)
    logger.info("Scholar统合助手启用: %s", args.enable_scholar_helper)

    try:
        setup_signal_handlers_fn()

        if args.mode == 'research':
            return execute_research_branch(
                args=args,
                logger=logger,
                run_research_session_fn=run_research_session_fn,
            )

        return execute_demo_branch(
            args=args,
            logger=logger,
            run_full_cycle_demo_fn=run_full_cycle_demo_fn,
            run_academic_demo_fn=run_academic_demo_fn,
            run_performance_demo_fn=run_performance_demo_fn,
            run_autorresearch_workflow_fn=run_autorresearch_workflow_fn,
            build_storage_connection_from_args_fn=build_storage_connection_from_args_fn,
            run_paper_plugin_workflow_fn=run_paper_plugin_workflow_fn,
            run_arxiv_fine_translation_workflow_fn=run_arxiv_fine_translation_workflow_fn,
            run_md_translate_workflow_fn=run_md_translate_workflow_fn,
            run_pdf_translation_workflow_fn=run_pdf_translation_workflow_fn,
            run_arxiv_quick_helper_workflow_fn=run_arxiv_quick_helper_workflow_fn,
            run_google_scholar_helper_workflow_fn=run_google_scholar_helper_workflow_fn,
        )

    except KeyboardInterrupt:
        logger.info("用户中断演示")
        return 1
    except Exception as exc:
        logger.error("演示执行失败: %s", exc)
        logger.error(traceback.format_exc())
        return 1
