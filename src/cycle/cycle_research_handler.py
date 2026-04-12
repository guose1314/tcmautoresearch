"""
run_cycle_demo research 分支处理器。
"""

import argparse
import logging
from typing import Any, Callable, Dict

from .cycle_runtime_config import build_cycle_runtime_config


def execute_research_branch(
    args: argparse.Namespace,
    logger: logging.Logger,
    run_research_session_fn: Callable[..., Dict[str, Any]],
) -> int:
    """执行 research 模式分支。"""
    if not args.question:
        logger.error("科研闭环模式需要 --question 参数")
        return 1

    phases_str = args.research_phases.strip()
    phase_names = [p.strip() for p in phases_str.split(',') if p.strip()]
    report_formats = args.report_format or ["markdown"]
    runtime_config = build_cycle_runtime_config(
        config_path=args.config_path,
        environment=args.environment,
    )
    result = run_research_session_fn(
        question=args.question,
        config=runtime_config,
        phase_names=phase_names,
        export_report_formats=report_formats if args.export_report else None,
        report_output_dir=args.report_output_dir,
    )
    if result.get('status') != 'completed':
        return 1
    return 0
