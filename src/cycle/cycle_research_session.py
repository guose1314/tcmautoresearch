"""run_cycle_demo research 模式执行逻辑。"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.orchestration.research_runtime_service import ResearchRuntimeService

from .cycle_reporter import export_research_session_reports

logger = logging.getLogger(__name__)


def _build_cycle_research_phase_contexts(
    question: str,
    config: Dict[str, Any],
    export_report_formats: Optional[List[str]],
    report_output_dir: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    local_data_dir = (
        (config.get("local_corpus") or {}).get("data_dir")
        or str((Path(__file__).resolve().parents[2] / "data").resolve())
    )
    observe_config = config.get("observe_pipeline") or {}

    phase_contexts: Dict[str, Dict[str, Any]] = {
        "observe": {
            "question": question,
            "research_question": question,
            "data_source": "local",
            "use_local_corpus": True,
            "collect_local_corpus": True,
            "local_data_dir": local_data_dir,
            "use_ctext_whitelist": False,
            "run_preprocess_and_extract": True,
            "run_reasoning": True,
            "run_literature_retrieval": bool(
                (config.get("literature_retrieval") or {}).get("enabled", False)
            ),
            "max_texts": int(observe_config.get("max_texts", 12)),
            "max_chars_per_text": int(observe_config.get("max_chars_per_text", 2000)),
        },
        "publish": {
            "question": question,
            "research_question": question,
            "allow_pipeline_citation_fallback": False,
        },
    }
    if export_report_formats:
        phase_contexts["publish"]["report_output_formats"] = list(export_report_formats)
    if report_output_dir:
        phase_contexts["publish"]["report_output_dir"] = report_output_dir
    return phase_contexts


def run_research_session(
    question: str,
    config: Dict[str, Any],
    phase_names: Optional[List[str]] = None,
    export_report_formats: Optional[List[str]] = None,
    report_output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """通过 ResearchPipeline 执行完整科研闭环。"""
    if phase_names is None:
        phase_names = ["observe"]

    logger.info("=== 科研闭环模式启动 ===")
    logger.info("研究问题: %s", question)
    logger.info("执行阶段: %s", phase_names)

    phase_contexts = _build_cycle_research_phase_contexts(
        question,
        config,
        export_report_formats,
        report_output_dir,
    )
    runtime_service = ResearchRuntimeService(
        {
            "pipeline_config": dict(config),
            "phases": list(phase_names),
            "stop_on_failure": True,
        }
    )
    runtime_result = runtime_service.run(
        question,
        phase_contexts=phase_contexts,
        cycle_name=f"research_{int(time.time())}",
        description=question,
        scope="中医药",
    )

    orchestration_result = runtime_result.orchestration_result
    phase_results = dict(runtime_result.phase_results)
    cycle_snapshot = dict(runtime_result.cycle_snapshot)

    summary = {
        "status": orchestration_result.status,
        "session_id": orchestration_result.cycle_id,
        "cycle_id": orchestration_result.cycle_id,
        "title": f"中医科研 IMRD 报告：{question}",
        "question": question,
        "research_question": question,
        "executed_phases": list(phase_results.keys()),
        "phase_results": phase_results,
        "metadata": {
            "research_question": question,
            "cycle_name": orchestration_result.pipeline_metadata.get("cycle_name"),
            "generated_by": "run_cycle_demo.research_mode",
        },
        "cycle_snapshot": cycle_snapshot,
    }

    if export_report_formats:
        report_export_result = export_research_session_reports(
            summary,
            report_formats=export_report_formats,
            output_dir=report_output_dir,
        )
        summary["reports"] = report_export_result.get("reports", {})
        summary["report_outputs"] = report_export_result.get("output_files", {})
        summary["report_export_errors"] = report_export_result.get("errors", [])

    output_file = Path(f"./output/research_session_{int(time.time())}.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("科研闭环结果已保存: %s", output_file)
    logger.info("=== 科研闭环模式结束 (status=%s) ===", orchestration_result.status)

    return summary
