#!/usr/bin/env python3
"""
中医古籍全自动研究系统 - 专业学术迭代循环演示
基于 T/C IATCM 098-2023 标准的完整迭代循环演示程序。
"""

import logging
import os
import signal
import sys
from typing import Any, Dict, List, Optional

from src.cycle import cycle_reporter, cycle_runner
from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_command_executor import execute_cycle_demo_command
from src.cycle.cycle_plugin_workflows import (
    build_storage_connection_from_args,
    run_arxiv_fine_translation_workflow,
    run_arxiv_quick_helper_workflow,
    run_autorresearch_workflow,
    run_google_scholar_helper_workflow,
    run_md_translate_workflow,
    run_paper_plugin_workflow,
    run_pdf_translation_workflow,
)
from src.cycle.cycle_research_session import run_research_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tcmautoresearch_demo.log', encoding='utf-8', delay=True),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

DEFAULT_CYCLE_DEMO_GOVERNANCE = dict(cycle_reporter.DEFAULT_CYCLE_DEMO_GOVERNANCE)
os.makedirs('./output', exist_ok=True)
os.makedirs('./logs', exist_ok=True)
os.makedirs('./data', exist_ok=True)

_load_cycle_demo_governance_config = cycle_reporter.load_cycle_demo_governance_config
_serialize_value = cycle_reporter.serialize_value
_start_phase = cycle_reporter.start_phase
_complete_phase = cycle_reporter.complete_phase
_record_failed_operation = cycle_reporter.record_failed_operation
_fail_phase = cycle_reporter.fail_phase
_build_runtime_metadata = cycle_reporter.build_runtime_metadata
_build_iteration_analysis_summary = cycle_reporter.build_iteration_analysis_summary
_build_cycle_demo_analysis_summary = cycle_reporter.build_cycle_demo_analysis_summary
_build_cycle_demo_report_metadata = cycle_reporter.build_report_metadata
export_cycle_demo_report = cycle_reporter.export_cycle_demo_report
export_research_session_reports = cycle_reporter.export_research_session_reports
_extract_research_phase_results = cycle_reporter.extract_research_phase_results
summarize_module_quality = cycle_reporter.summarize_module_quality

create_sample_data = cycle_runner.create_sample_data


def setup_signal_handlers() -> None:
    """设置信号处理器。"""

    def signal_handler(sig: int, frame: Any) -> None:
        logger.info('收到终止信号，正在优雅退出...')
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def run_full_cycle_demo(
    max_iterations: int = 3,
    sample_data: Optional[List[str]] = None,
    config_path: Optional[str] = 'config.yml',
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    return cycle_runner.run_full_cycle_demo(
        max_iterations=max_iterations,
        sample_data=sample_data,
        config_path=config_path,
        output_path=output_path,
        governance_config_loader=_load_cycle_demo_governance_config,
    )


def run_academic_demo() -> Dict[str, Any]:
    return cycle_runner.run_academic_demo(run_full_demo=run_full_cycle_demo)


def run_performance_demo() -> Dict[str, Any]:
    return cycle_runner.run_performance_demo(run_full_demo=run_full_cycle_demo)


def main() -> int:
    """命令行入口。"""
    parser = build_cycle_demo_arg_parser()
    args = parser.parse_args()
    return execute_cycle_demo_command(
        args=args,
        logger=logger,
        setup_signal_handlers_fn=setup_signal_handlers,
        run_research_session_fn=run_research_session,
        run_full_cycle_demo_fn=run_full_cycle_demo,
        run_academic_demo_fn=run_academic_demo,
        run_performance_demo_fn=run_performance_demo,
        run_autorresearch_workflow_fn=run_autorresearch_workflow,
        build_storage_connection_from_args_fn=build_storage_connection_from_args,
        run_paper_plugin_workflow_fn=run_paper_plugin_workflow,
        run_arxiv_fine_translation_workflow_fn=run_arxiv_fine_translation_workflow,
        run_md_translate_workflow_fn=run_md_translate_workflow,
        run_pdf_translation_workflow_fn=run_pdf_translation_workflow,
        run_arxiv_quick_helper_workflow_fn=run_arxiv_quick_helper_workflow,
        run_google_scholar_helper_workflow_fn=run_google_scholar_helper_workflow,
    )


if __name__ == "__main__":
    sys.exit(main())
