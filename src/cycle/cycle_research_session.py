"""run_cycle_demo research 模式执行逻辑。"""

import logging
from typing import Any, Dict, List, Optional

from src.orchestration.research_runtime_service import ResearchRuntimeService

logger = logging.getLogger(__name__)


def run_research_session(
    question: str,
    config: Dict[str, Any],
    phase_names: Optional[List[str]] = None,
    export_report_formats: Optional[List[str]] = None,
    report_output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """通过 shared runtime 执行完整科研闭环。"""
    logger.info("=== 科研闭环模式启动 ===")
    logger.info("研究问题: %s", question)

    runtime_config = dict(config or {})
    if not isinstance(runtime_config.get("pipeline_config"), dict):
        runtime_config = {"pipeline_config": dict(config or {})}
    if phase_names is not None:
        runtime_config["phases"] = list(phase_names)

    runtime_service = ResearchRuntimeService(runtime_config)
    logger.info("执行阶段: %s", runtime_service.phase_names)
    runtime_result = runtime_service.run(
        question,
        report_output_formats=export_report_formats,
        report_output_dir=report_output_dir,
    )
    logger.info("=== 科研闭环模式结束 (status=%s) ===", runtime_result.orchestration_result.status)
    return runtime_result.session_result
