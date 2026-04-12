"""
run_cycle_demo core demo 处理器。
"""

import argparse
import logging
from typing import Any, Callable, Dict

WorkflowFn = Callable[..., Dict[str, Any]]


def execute_core_demo_workflow_handler(
    args: argparse.Namespace,
    logger: logging.Logger,
    run_full_cycle_demo_fn: WorkflowFn,
    run_academic_demo_fn: WorkflowFn,
    run_performance_demo_fn: WorkflowFn,
) -> int:
    runtime_args = {
        "config_path": args.config_path,
        "environment": args.environment,
    }

    if args.demo_type == 'basic':
        logger.info("运行基础演示...")
        run_full_cycle_demo_fn(max_iterations=args.iterations, **runtime_args)
        return 0

    if args.demo_type == 'academic':
        logger.info("运行学术演示...")
        run_academic_demo_fn(**runtime_args)
        return 0

    if args.demo_type == 'performance':
        logger.info("运行性能演示...")
        run_performance_demo_fn(**runtime_args)
        return 0

    if args.demo_type == 'full':
        logger.info("运行完整演示...")
        logger.info("1. 基础演示:")
        run_full_cycle_demo_fn(max_iterations=args.iterations, **runtime_args)
        logger.info("\n2. 学术演示:")
        run_academic_demo_fn(**runtime_args)
        logger.info("\n3. 性能演示:")
        run_performance_demo_fn(**runtime_args)

    return 0