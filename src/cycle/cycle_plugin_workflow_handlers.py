"""
run_cycle_demo demo 插件工作流处理器。
"""

import argparse
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Tuple

WorkflowFn = Callable[..., Dict[str, Any]]
StorageConnFn = Callable[[argparse.Namespace], Dict[str, str]]
PluginHandlerFn = Callable[..., int]
StorageKwargs = Dict[str, str]


@dataclass(frozen=True)
class PluginWorkflowDispatchConfig:
    args: argparse.Namespace
    logger: logging.Logger
    run_autorresearch_workflow_fn: WorkflowFn
    build_storage_connection_from_args_fn: StorageConnFn
    run_paper_plugin_workflow_fn: WorkflowFn
    run_arxiv_fine_translation_workflow_fn: WorkflowFn
    run_md_translate_workflow_fn: WorkflowFn
    run_pdf_translation_workflow_fn: WorkflowFn
    run_arxiv_quick_helper_workflow_fn: WorkflowFn
    run_google_scholar_helper_workflow_fn: WorkflowFn


@dataclass(frozen=True)
class PluginWorkflowStep:
    handler: PluginHandlerFn
    args: Tuple[Any, ...]


def build_plugin_workflow_steps(
    config: PluginWorkflowDispatchConfig,
) -> Tuple[PluginWorkflowStep, ...]:
    args = config.args
    logger = config.logger

    return (
        PluginWorkflowStep(
            execute_autorresearch_workflow_handler,
            (args, logger, config.run_autorresearch_workflow_fn),
        ),
        PluginWorkflowStep(
            execute_paper_plugin_workflow_handler,
            (args, logger, config.build_storage_connection_from_args_fn, config.run_paper_plugin_workflow_fn),
        ),
        PluginWorkflowStep(
            execute_arxiv_fine_translation_workflow_handler,
            (args, logger, config.build_storage_connection_from_args_fn, config.run_arxiv_fine_translation_workflow_fn),
        ),
        PluginWorkflowStep(
            execute_md_translate_workflow_handler,
            (args, logger, config.build_storage_connection_from_args_fn, config.run_md_translate_workflow_fn),
        ),
        PluginWorkflowStep(
            execute_pdf_translation_workflow_handler,
            (args, logger, config.build_storage_connection_from_args_fn, config.run_pdf_translation_workflow_fn),
        ),
        PluginWorkflowStep(
            execute_arxiv_helper_workflow_handler,
            (args, logger, config.build_storage_connection_from_args_fn, config.run_arxiv_quick_helper_workflow_fn),
        ),
        PluginWorkflowStep(
            execute_scholar_helper_workflow_handler,
            (args, logger, config.build_storage_connection_from_args_fn, config.run_google_scholar_helper_workflow_fn),
        ),
    )


def execute_plugin_workflow_steps(workflow_steps: Iterable[PluginWorkflowStep]) -> int:
    for workflow_step in workflow_steps:
        status_code = workflow_step.handler(*workflow_step.args)
        if status_code != 0:
            return status_code
    return 0


def build_storage_connection_kwargs(
    args: argparse.Namespace,
    build_storage_connection_from_args_fn: StorageConnFn,
) -> StorageKwargs:
    storage_conn = build_storage_connection_from_args_fn(args)
    return {
        "pg_url": storage_conn["pg_url"],
        "neo4j_uri": storage_conn["neo4j_uri"],
        "neo4j_user": storage_conn["neo4j_user"],
        "neo4j_password": storage_conn["neo4j_password"],
    }


def execute_autorresearch_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    run_autorresearch_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_autorresearch:
        return 0

    logger.info("\n4. AutoResearch 演示:")
    ar_result = run_autorresearch_workflow_fn(
        instruction=args.autorresearch_instruction,
        instruction_file=args.autorresearch_instruction_file,
        max_iters=args.autorresearch_iters,
        timeout_seconds=args.autorresearch_timeout,
        strategy=args.autorresearch_strategy,
        rollback_mode=args.autorresearch_rollback_mode,
        python_exe=args.autorresearch_python_exe,
    )
    if ar_result.get("status") != "completed":
        logger.error("AutoResearch 子流程失败，主流程返回非零状态")
        return 1
    return 0


def execute_paper_plugin_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_paper_plugin_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_paper_plugin:
        return 0
    if not args.paper_input:
        logger.error("启用论文插件时必须提供 --paper-input")
        return 1

    logger.info("\n5. 论文插件演示:")
    storage_kwargs = build_storage_connection_kwargs(args, build_storage_connection_from_args_fn)
    paper_result = run_paper_plugin_workflow_fn(
        source_path=args.paper_input,
        output_dir=args.paper_output_dir,
        translate_lang=args.paper_translate_lang,
        summary_lang=args.paper_summary_lang,
        use_llm=not args.paper_no_llm,
        persist_storage=args.paper_persist_storage,
        **storage_kwargs,
    )
    if paper_result.get("status") != "completed":
        logger.error("论文插件子流程失败，主流程返回非零状态")
        return 1
    return 0


def execute_arxiv_fine_translation_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_arxiv_fine_translation_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_arxiv_fine_translation:
        return 0
    if not args.arxiv_input:
        logger.error("启用 Arxiv 精细翻译时必须提供 --arxiv-input")
        return 1
    if not args.arxiv_daas_url:
        logger.error("启用 Arxiv 精细翻译时必须提供 --arxiv-daas-url 或环境变量 ARXIV_DAAS_URL")
        return 1

    logger.info("\n6. Arxiv 精细翻译（Docker）演示:")
    storage_kwargs = build_storage_connection_kwargs(args, build_storage_connection_from_args_fn)
    arxiv_result = run_arxiv_fine_translation_workflow_fn(
        arxiv_input=args.arxiv_input,
        daas_url=args.arxiv_daas_url,
        output_dir=args.arxiv_output_dir,
        advanced_arg=args.arxiv_advanced_arg,
        timeout_sec=args.arxiv_timeout,
        persist_storage=args.arxiv_persist_storage,
        **storage_kwargs,
    )
    if arxiv_result.get("status") != "completed":
        logger.error("Arxiv 精细翻译子流程失败，主流程返回非零状态")
        return 1
    return 0


def execute_md_translate_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_md_translate_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_md_translate:
        return 0
    if not args.md_input:
        logger.error("启用 Markdown 翻译时必须提供 --md-input")
        return 1

    logger.info("\n7. Markdown 中英互译演示:")
    storage_kwargs = build_storage_connection_kwargs(args, build_storage_connection_from_args_fn)
    md_result = run_md_translate_workflow_fn(
        input_path=args.md_input,
        language=args.md_lang,
        output_dir=args.md_output_dir,
        additional_prompt=args.md_additional_prompt,
        max_workers=args.md_max_workers,
        use_llm=not args.md_no_llm,
        persist_storage=args.md_persist_storage,
        **storage_kwargs,
    )
    if md_result.get("status") == "failed":
        logger.error("Markdown 翻译子流程失败，主流程返回非零状态")
        return 1
    return 0


def execute_pdf_translation_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_pdf_translation_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_pdf_translation:
        return 0
    if not args.pdf_input:
        logger.error("启用 PDF 翻译时必须提供 --pdf-input")
        return 1

    logger.info("\n8. PDF 论文全文翻译演示:")
    storage_kwargs = build_storage_connection_kwargs(args, build_storage_connection_from_args_fn)
    pdf_result = run_pdf_translation_workflow_fn(
        pdf_path=args.pdf_input,
        target_language=args.pdf_target_lang,
        output_dir=args.pdf_output_dir,
        additional_prompt=args.pdf_additional_prompt,
        max_tokens_per_fragment=args.pdf_max_tokens_per_fragment,
        max_workers=args.pdf_max_workers,
        use_llm=not args.pdf_no_llm,
        persist_storage=args.pdf_persist_storage,
        **storage_kwargs,
    )
    if pdf_result.get("status") == "failed":
        logger.error("PDF 翻译子流程失败，主流程返回非零状态")
        return 1
    return 0


def execute_arxiv_helper_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_arxiv_quick_helper_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_arxiv_helper:
        return 0
    if not args.arxiv_helper_url:
        logger.error("启用 Arxiv 快速助手时必须提供 --arxiv-helper-url")
        return 1

    logger.info("\n9. Arxiv 快速助手演示:")
    storage_kwargs = build_storage_connection_kwargs(args, build_storage_connection_from_args_fn)
    arxiv_result = run_arxiv_quick_helper_workflow_fn(
        arxiv_url=args.arxiv_helper_url,
        output_dir=args.arxiv_helper_dir,
        target_lang=args.arxiv_helper_lang,
        enable_translation=not args.arxiv_helper_no_translation,
        persist_storage=args.arxiv_helper_persist_storage,
        **storage_kwargs,
    )
    if arxiv_result.get("status") == "error":
        logger.error("Arxiv 快速助手子流程失败，主流程返回非零状态")
        return 1
    return 0


def execute_scholar_helper_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    build_storage_connection_from_args_fn: StorageConnFn,
    run_google_scholar_helper_workflow_fn: WorkflowFn,
) -> int:
    if not args.enable_scholar_helper:
        return 0
    if not args.scholar_url:
        logger.error("启用 Scholar 统合助手时必须提供 --scholar-url")
        return 1

    logger.info("\n10. Google Scholar 统合小助手演示:")
    storage_kwargs = build_storage_connection_kwargs(args, build_storage_connection_from_args_fn)
    scholar_result = run_google_scholar_helper_workflow_fn(
        scholar_url=args.scholar_url,
        output_dir=args.scholar_output_dir,
        topic_hint=args.scholar_topic_hint,
        target_lang=args.scholar_target_lang,
        max_papers=args.scholar_max_papers,
        use_llm=not args.scholar_no_llm,
        additional_prompt=args.scholar_additional_prompt,
        persist_storage=args.scholar_persist_storage,
        **storage_kwargs,
    )
    if scholar_result.get("status") == "error":
        logger.error("Scholar 统合助手子流程失败，主流程返回非零状态")
        return 1
    return 0
