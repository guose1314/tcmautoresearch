"""run_cycle_demo research 模式执行逻辑。"""

import importlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cycle_reporter import (
    export_research_session_reports,
    extract_research_phase_results,
)

logger = logging.getLogger(__name__)


def run_research_session(
    question: str,
    config: Dict[str, Any],
    phase_names: Optional[List[str]] = None,
    export_report_formats: Optional[List[str]] = None,
    report_output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """通过 ResearchPipeline 执行完整科研闭环。"""
    research_pipeline_module = importlib.import_module("src.research.research_pipeline")
    session_manager_module = importlib.import_module("src.research.study_session_manager")
    ResearchPipeline = getattr(research_pipeline_module, "ResearchPipeline")
    ResearchPhase = getattr(session_manager_module, "ResearchPhase")

    phase_map = {phase.value: phase for phase in ResearchPhase}

    if phase_names is None:
        phase_names = ["observe"]

    pipeline_config = dict(config)
    if export_report_formats or report_output_dir:
        report_config = dict(pipeline_config.get("report_generation") or {})
        if export_report_formats:
            report_config["output_formats"] = list(export_report_formats)
        if report_output_dir:
            report_config["output_dir"] = report_output_dir
        pipeline_config["report_generation"] = report_config

    logger.info("=== 科研闭环模式启动 ===")
    logger.info("研究问题: %s", question)
    logger.info("执行阶段: %s", phase_names)

    pipeline = ResearchPipeline(config=pipeline_config)
    cycle = pipeline.create_research_cycle(
        cycle_name=f"research_{int(time.time())}",
        description=question,
        objective=question,
        scope="中医药",
    )
    logger.info("研究循环已创建: %s", cycle.cycle_id)

    started = pipeline.start_research_cycle(cycle.cycle_id)
    if not started:
        logger.error("研究循环启动失败: %s", cycle.cycle_id)
        return {"status": "failed", "cycle_id": cycle.cycle_id, "phase_results": {}}

    phase_results: Dict[str, Any] = {}
    overall_status = "completed"

    for phase_name in phase_names:
        phase_enum = phase_map.get(phase_name.lower())
        if phase_enum is None:
            logger.warning("跳过未知阶段: %s (可选: %s)", phase_name, list(phase_map.keys()))
            continue

        logger.info(">>> 开始阶段: %s", phase_enum.value)
        try:
            phase_context: Dict[str, Any] = {"question": question}

            if phase_enum.value == "observe":
                local_data_dir = (
                    (config.get("local_corpus") or {}).get("data_dir")
                    or str((Path(__file__).resolve().parents[2] / "data").resolve())
                )
                observe_config = config.get("observe_pipeline") or {}
                phase_context.update(
                    {
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
                    }
                )

            if phase_enum.value == "publish":
                phase_context["allow_pipeline_citation_fallback"] = False
                if export_report_formats:
                    phase_context["report_output_formats"] = list(export_report_formats)
                if report_output_dir:
                    phase_context["report_output_dir"] = report_output_dir

            result = pipeline.execute_research_phase(
                cycle.cycle_id,
                phase_enum,
                phase_context=phase_context,
            )
            phase_results[phase_enum.value] = result
            logger.info("<<< 阶段 %s 完成", phase_enum.value)
        except Exception as exc:
            logger.error("阶段 %s 执行失败: %s", phase_enum.value, exc)
            phase_results[phase_enum.value] = {"error": str(exc)}
            overall_status = "failed"
            break

    cycle_snapshot: Dict[str, Any] = {}
    try:
        cycle_snapshot = pipeline._serialize_cycle(cycle)
    except Exception:
        cycle_snapshot = {}

    try:
        pipeline.complete_research_cycle(cycle.cycle_id)
    except Exception:
        pass
    try:
        cycle_snapshot = pipeline._serialize_cycle(cycle)
    except Exception:
        pass
    try:
        pipeline.cleanup()
    except Exception:
        pass

    snapshot_phase_results = extract_research_phase_results(cycle_snapshot)
    if snapshot_phase_results:
        phase_results.update(snapshot_phase_results)

    summary = {
        "status": overall_status,
        "session_id": cycle.cycle_id,
        "cycle_id": cycle.cycle_id,
        "title": f"中医科研 IMRD 报告：{question}",
        "question": question,
        "research_question": question,
        "executed_phases": list(phase_results.keys()),
        "phase_results": phase_results,
        "metadata": {
            "research_question": question,
            "cycle_name": cycle.cycle_name,
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
    logger.info("=== 科研闭环模式结束 (status=%s) ===", overall_status)

    return summary
