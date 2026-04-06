#!/usr/bin/env python3
"""
中医古籍全自动研究系统 - 专业学术迭代循环演示
基于T/C IATCM 098-2023标准的完整迭代循环演示程序
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.cycle.cycle_cli import build_cycle_demo_arg_parser
from src.cycle.cycle_command_executor import execute_cycle_demo_command
from src.cycle.cycle_reporter import (
    DEFAULT_CYCLE_DEMO_GOVERNANCE as _DEFAULT_CYCLE_DEMO_GOVERNANCE,
)
from src.cycle.cycle_reporter import (
    build_cycle_demo_analysis_summary as _build_cycle_demo_analysis_summary_impl,
)
from src.cycle.cycle_reporter import (
    build_iteration_analysis_summary as _build_iteration_analysis_summary_impl,
)
from src.cycle.cycle_reporter import (
    build_report_metadata as _build_cycle_demo_report_metadata_impl,
)
from src.cycle.cycle_reporter import (
    build_runtime_metadata as _build_runtime_metadata_impl,
)
from src.cycle.cycle_reporter import (
    complete_phase as _complete_phase_impl,
)
from src.cycle.cycle_reporter import (
    export_cycle_demo_report as _export_cycle_demo_report_impl,
)
from src.cycle.cycle_reporter import (
    export_research_session_reports as _export_research_session_reports_impl,
)
from src.cycle.cycle_reporter import (
    extract_research_phase_results as _extract_research_phase_results_impl,
)
from src.cycle.cycle_reporter import (
    fail_phase as _fail_phase_impl,
)
from src.cycle.cycle_reporter import (
    load_cycle_demo_governance_config as _load_cycle_demo_governance_config_impl,
)
from src.cycle.cycle_reporter import (
    record_failed_operation as _record_failed_operation_impl,
)
from src.cycle.cycle_reporter import (
    serialize_value as _serialize_value_impl,
)
from src.cycle.cycle_reporter import (
    start_phase as _start_phase_impl,
)
from src.cycle.cycle_reporter import (
    summarize_module_quality as _summarize_module_quality_impl,
)
from src.cycle.cycle_runner import ModuleLifecycle as _ModuleLifecycle
from src.cycle.cycle_runner import (
    build_real_modules as _build_real_modules_impl,
)
from src.cycle.cycle_runner import (
    cleanup_real_modules as _cleanup_real_modules_impl,
)
from src.cycle.cycle_runner import (
    create_sample_data as _create_sample_data_impl,
)
from src.cycle.cycle_runner import (
    execute_real_module_pipeline as _execute_real_module_pipeline_impl,
)
from src.cycle.cycle_runner import (
    initialize_real_modules as _initialize_real_modules_impl,
)
from src.cycle.cycle_runner import (
    run_academic_demo as _run_academic_demo_impl,
)
from src.cycle.cycle_runner import (
    run_full_cycle_demo as _run_full_cycle_demo_impl,
)
from src.cycle.cycle_runner import (
    run_iteration_cycle as _run_iteration_cycle_impl,
)
from src.cycle.cycle_runner import (
    run_performance_demo as _run_performance_demo_impl,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tcmautoresearch_demo.log', encoding='utf-8', delay=True),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

DEFAULT_CYCLE_DEMO_GOVERNANCE = dict(_DEFAULT_CYCLE_DEMO_GOVERNANCE)

_ORIGINAL_SUBPROCESS_RUN = subprocess.run


def _ensure_cycle_demo_governance_contract(governance_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_config = dict(DEFAULT_CYCLE_DEMO_GOVERNANCE)
    if governance_config:
        normalized_config.update(governance_config)

    normalized_config["export_contract_version"] = str(
        normalized_config.get(
            "export_contract_version",
            DEFAULT_CYCLE_DEMO_GOVERNANCE.get("export_contract_version", "d58.v1"),
        )
    )
    return normalized_config


def _safe_subprocess_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Normalize subprocess text capture outputs for CLI help integration tests."""
    capture_requested = bool(kwargs.get("capture_output")) or kwargs.get("stdout") == subprocess.PIPE
    text_requested = bool(kwargs.get("text")) or bool(kwargs.get("universal_newlines"))
    normalized_kwargs = dict(kwargs)
    if text_requested:
        normalized_kwargs.setdefault("encoding", "utf-8")
        normalized_kwargs.setdefault("errors", "replace")

    completed = _ORIGINAL_SUBPROCESS_RUN(*args, **normalized_kwargs)
    if capture_requested and text_requested and (completed.stdout is None or completed.stderr is None):
        retry_kwargs = dict(normalized_kwargs)
        retry_kwargs.pop("capture_output", None)
        retry_kwargs["stdout"] = subprocess.PIPE
        retry_kwargs["stderr"] = subprocess.PIPE
        retried = _ORIGINAL_SUBPROCESS_RUN(*args, **retry_kwargs)
        return subprocess.CompletedProcess(
            retried.args,
            retried.returncode,
            retried.stdout or "",
            retried.stderr or "",
        )
    return completed


subprocess.run = _safe_subprocess_run

# 确保必要的目录存在
os.makedirs('./output', exist_ok=True)
os.makedirs('./logs', exist_ok=True)
os.makedirs('./data', exist_ok=True)


def _load_cycle_demo_section(config_path: Optional[Path]) -> Dict[str, Any]:
    from src.infrastructure.config_loader import load_settings_section

    return load_settings_section(
        'governance.cycle_demo',
        config_path=config_path,
        default={},
    )


def _load_cycle_demo_governance_config(config_path: Optional[Path]) -> Dict[str, Any]:
    return _load_cycle_demo_governance_config_impl(config_path)


def _serialize_value(value: Any) -> Any:
    return _serialize_value_impl(value)


def _start_phase(runtime_metadata: Dict[str, Any], phase_name: str, details: Optional[Dict[str, Any]] = None) -> float:
    return _start_phase_impl(runtime_metadata, phase_name, details)


def _complete_phase(
    runtime_metadata: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    details: Optional[Dict[str, Any]] = None,
    final_status: Optional[str] = None,
) -> None:
    _complete_phase_impl(runtime_metadata, phase_name, phase_started_at, details, final_status)


def _record_failed_operation(
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    operation_name: str,
    error: str,
    details: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    _record_failed_operation_impl(
        failed_operations,
        governance_config,
        operation_name,
        error,
        details,
        duration_seconds,
    )


def _fail_phase(
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    error: Exception,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    _fail_phase_impl(
        runtime_metadata,
        failed_operations,
        governance_config,
        phase_name,
        phase_started_at,
        error,
        details,
    )


def _build_runtime_metadata(runtime_metadata: Dict[str, Any]) -> Dict[str, Any]:
    return _build_runtime_metadata_impl(runtime_metadata)


def _build_iteration_analysis_summary(iteration_results: Dict[str, Any]) -> Dict[str, Any]:
    return _build_iteration_analysis_summary_impl(iteration_results)


def _build_cycle_demo_analysis_summary(cycle_results: Dict[str, Any], governance_config: Dict[str, Any]) -> Dict[str, Any]:
    return _build_cycle_demo_analysis_summary_impl(cycle_results, governance_config)


def _build_cycle_demo_report_metadata(
    governance_config: Dict[str, Any],
    metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    normalized_governance_config = _ensure_cycle_demo_governance_contract(governance_config)
    return _build_cycle_demo_report_metadata_impl(
        normalized_governance_config,
        metadata,
        failed_operations,
        output_path,
    )


def export_cycle_demo_report(cycle_results: Dict[str, Any], output_path: Path, governance_config: Dict[str, Any]) -> Dict[str, Any]:
    normalized_governance_config = _ensure_cycle_demo_governance_contract(governance_config)
    return _export_cycle_demo_report_impl(cycle_results, output_path, normalized_governance_config)


def setup_signal_handlers():
    """设置信号处理器"""

    def signal_handler(sig, frame):
        logger.info('收到终止信号，正在优雅退出...')
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def create_sample_data() -> List[str]:
    return _create_sample_data_impl()


def build_real_modules() -> List[tuple[str, Any]]:
    return _build_real_modules_impl()


def initialize_real_modules(modules: List[tuple[str, Any]]) -> None:
    _initialize_real_modules_impl(modules)


def cleanup_real_modules(modules: List[tuple[str, Any]]) -> None:
    _cleanup_real_modules_impl(modules)


def summarize_module_quality(module_name: str, result: Dict[str, Any]) -> Dict[str, float]:
    return _summarize_module_quality_impl(module_name, result)


def execute_real_module_pipeline(
    input_data: Dict[str, Any],
    modules: Optional[List[tuple[str, Any]]] = None,
    manage_module_lifecycle: bool = False,
) -> List[Dict[str, Any]]:
    return _execute_real_module_pipeline_impl(
        input_data,
        modules=modules,
        manage_module_lifecycle=manage_module_lifecycle,
    )


def run_iteration_cycle(
    iteration_number: int,
    input_data: Dict[str, Any],
    max_iterations: int = 5,
    shared_modules: Optional[List[tuple[str, Any]]] = None,
    governance_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _run_iteration_cycle_impl(
        iteration_number,
        input_data,
        max_iterations=max_iterations,
        shared_modules=shared_modules,
        governance_config=governance_config,
        execute_pipeline=execute_real_module_pipeline,
    )


_ALL_PIPELINE_PHASES = ["observe", "hypothesis", "experiment", "analyze", "publish", "reflect"]


def _run_pipeline_iteration(
    iteration_number: int,
    input_data: Dict[str, Any],
    max_iterations: int = 5,
    shared_modules: Optional[List[tuple[str, Any]]] = None,
    governance_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """通过 6 阶段 ResearchPipeline 执行单次迭代。

    与 ``run_iteration_cycle`` 保持相同的调用签名与返回契约，
    使 ``_run_full_cycle_demo_impl`` 无需修改即可切换后端。
    """
    from datetime import datetime as _dt

    start_time = time.time()
    question = input_data.get("objective", "")
    if not question:
        raw = input_data.get("raw_text", "")
        question = (raw[:80] + "…") if len(raw) > 80 else raw
    question = question or "中医方剂组成规律分析"

    try:
        # ---- 构建 pipeline 配置，传递迭代间反馈 ----
        pipeline_config: Dict[str, Any] = {}
        previous_feedback = input_data.get("previous_feedback")
        if previous_feedback:
            pipeline_config["previous_iteration_feedback"] = previous_feedback

        session_result = run_research_session(
            question=question,
            config=pipeline_config,
            phase_names=list(_ALL_PIPELINE_PHASES),
        )
    except Exception as exc:
        logger.error("Pipeline iteration %d failed: %s", iteration_number, exc)
        return {
            "iteration_id": f"iter_{iteration_number}",
            "iteration_number": iteration_number,
            "status": "failed",
            "error": str(exc),
            "start_time": _dt.now().isoformat(),
            "end_time": _dt.now().isoformat(),
            "duration": time.time() - start_time,
            "modules": [],
            "quality_metrics": {},
            "confidence_scores": {},
            "academic_insights": [],
            "recommendations": [],
            "metadata": {"max_iterations": max_iterations, "input_data": input_data, "pipeline_mode": True},
            "failed_operations": [],
            "analysis_summary": {"module_count": 0, "failed_operation_count": 1},
        }

    duration = time.time() - start_time
    phase_results = session_result.get("phase_results", {})

    modules: List[Dict[str, Any]] = []
    for pname, presult in phase_results.items():
        modules.append({
            "module": pname,
            "status": "completed" if not (isinstance(presult, dict) and presult.get("error")) else "failed",
            "execution_time": 0.0,
            "timestamp": _dt.now().isoformat(),
            "input_data": {},
            "output_data": presult if isinstance(presult, dict) else {},
            "quality_metrics": _summarize_module_quality_impl(pname, presult if isinstance(presult, dict) else {}),
        })

    # 从 reflect 阶段提取真实质量评估作为 academic insights
    reflect_result = phase_results.get("reflect", {})
    quality_assessment = reflect_result.get("quality_assessment", {}) if isinstance(reflect_result, dict) else {}
    reflections = reflect_result.get("reflections", []) if isinstance(reflect_result, dict) else []

    academic_insights = [
        {
            "type": "quality_assessment",
            "title": f"第{iteration_number}次管道循环质量评估",
            "description": f"整体评分 {quality_assessment.get('overall_cycle_score', 0.0):.2f}",
            "confidence": quality_assessment.get("overall_cycle_score", 0.0),
            "timestamp": _dt.now().isoformat(),
        },
    ]
    for ref in reflections[:3]:
        if isinstance(ref, dict):
            academic_insights.append({
                "type": "reflection",
                "title": ref.get("topic", ""),
                "description": ref.get("reflection", ""),
                "confidence": 0.85,
                "timestamp": _dt.now().isoformat(),
            })

    improvement_plan = reflect_result.get("improvement_plan", []) if isinstance(reflect_result, dict) else []
    recommendations = [
        {
            "type": "improvement",
            "title": item,
            "description": item,
            "priority": "medium",
            "confidence": 0.80,
            "timestamp": _dt.now().isoformat(),
        }
        for item in improvement_plan[:5]
    ]

    return {
        "iteration_id": f"iter_{iteration_number}",
        "iteration_number": iteration_number,
        "status": session_result.get("status", "completed"),
        "start_time": _dt.now().isoformat(),
        "end_time": _dt.now().isoformat(),
        "duration": duration,
        "modules": modules,
        "quality_metrics": {},
        "confidence_scores": {},
        "academic_insights": academic_insights,
        "recommendations": recommendations,
        "metadata": {
            "max_iterations": max_iterations,
            "input_data": input_data,
            "pipeline_mode": True,
            "session_id": session_result.get("session_id", ""),
            "executed_phases": session_result.get("executed_phases", []),
            "last_completed_phase": "reflect" if "reflect" in phase_results else None,
        },
        "failed_operations": [],
        "analysis_summary": {
            "module_count": len(modules),
            "failed_operation_count": 0,
        },
    }


def run_full_cycle_demo(
    max_iterations: int = 3,
    sample_data: Optional[List[str]] = None,
    config_path: Optional[str] = 'config.yml',
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    return _run_full_cycle_demo_impl(
        max_iterations=max_iterations,
        sample_data=sample_data,
        config_path=config_path,
        output_path=output_path,
        governance_config_loader=_load_cycle_demo_governance_config,
        module_lifecycle=_ModuleLifecycle(
            build=lambda: [],
            initialize=lambda _modules: None,
            cleanup=lambda _modules: None,
        ),
        run_iteration=_run_pipeline_iteration,
    )


def run_academic_demo():
    return _run_academic_demo_impl(run_full_demo=run_full_cycle_demo)


def run_performance_demo():
    return _run_performance_demo_impl(run_full_demo=run_full_cycle_demo)


def run_autorresearch_workflow(
    instruction: str,
    instruction_file: str,
    max_iters: int,
    timeout_seconds: int,
    strategy: str,
    rollback_mode: str,
    python_exe: str,
) -> Dict[str, Any]:
    """在主流程后触发 AutoResearch 循环。"""
    logger.info("=== 开始 AutoResearch 研究范式循环 ===")

    repo_root = Path(__file__).resolve().parent
    runner = repo_root / "tools" / "autorresearch" / "autorresearch_runner.py"
    if not runner.exists():
        raise FileNotFoundError(f"AutoResearch runner 不存在: {runner}")

    cmd = [
        python_exe,
        str(runner),
        "--max-iters",
        str(max_iters),
        "--timeout-seconds",
        str(timeout_seconds),
        "--python-exe",
        python_exe,
        "--strategy",
        strategy,
        "--rollback-mode",
        rollback_mode,
    ]

    if instruction_file:
        cmd.extend(["--instruction-file", instruction_file])
    else:
        cmd.extend(["--instruction", instruction])

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - started

    output_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    best_val_bpb = None
    report_path = None
    for line in output_text.splitlines():
        line = line.strip()
        if line.startswith("best_val_bpb="):
            try:
                best_val_bpb = float(line.split("=", 1)[1])
            except Exception:
                best_val_bpb = None
        if line.startswith("report="):
            report_path = line.split("=", 1)[1]

    result = {
        "status": "completed" if proc.returncode == 0 else "failed",
        "return_code": proc.returncode,
        "duration": duration,
        "best_val_bpb": best_val_bpb,
        "report_path": report_path,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

    if proc.returncode == 0:
        logger.info(f"AutoResearch 完成，best_val_bpb={best_val_bpb}")
        if report_path:
            logger.info(f"AutoResearch 报告: {report_path}")
    else:
        logger.error("AutoResearch 运行失败")
        logger.error(proc.stderr)

    return result


def run_paper_plugin_workflow(
    source_path: str,
    output_dir: str,
    translate_lang: str,
    summary_lang: str,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """在主流程后触发论文读取/翻译/摘要插件。"""
    from src.research.paper_plugin import run_paper_plugin

    logger.info("=== 开始论文插件流程 ===")
    result = run_paper_plugin(
        source_path=source_path,
        output_dir=output_dir,
        summary_lang=summary_lang,
        translate_to=translate_lang,
        use_llm=use_llm,
    )

    logger.info(f"论文插件状态: {result.status}")
    if result.status == "completed":
        logger.info(f"论文来源类型: {result.source_type}")
        logger.info(f"提取字符数: {result.char_count}")
        logger.info(f"JSON 报告: {result.output_json}")
        logger.info(f"Markdown 报告: {result.output_markdown}")

        storage_result = {"status": "skipped", "document_id": "", "error": ""}
        if persist_storage:
            storage_result = persist_paper_result_to_dual_storage(
                source_path=source_path,
                result_payload={
                    "source_type": result.source_type,
                    "char_count": result.char_count,
                    "summary": result.summary,
                    "translation_excerpt": result.translation_excerpt,
                    "output_json": result.output_json,
                    "output_markdown": result.output_markdown,
                    "translated": result.translated,
                },
                pg_url=pg_url,
                neo4j_uri=neo4j_uri,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
            )
            if storage_result.get("status") == "completed":
                logger.info(f"论文插件双库存档完成，document_id={storage_result.get('document_id')}")
            else:
                logger.error(f"论文插件双库存档失败: {storage_result.get('error')}")
                return {
                    "status": "failed",
                    "source_type": result.source_type,
                    "char_count": result.char_count,
                    "translated": result.translated,
                    "output_json": result.output_json,
                    "output_markdown": result.output_markdown,
                    "error": f"storage_failed: {storage_result.get('error')}",
                    "storage": storage_result,
                }
    else:
        logger.error(f"论文插件失败: {result.error}")

    return {
        "status": result.status,
        "source_type": result.source_type,
        "char_count": result.char_count,
        "translated": result.translated,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "error": result.error,
        "storage": storage_result if result.status == "completed" else {"status": "skipped"},
    }


def run_arxiv_fine_translation_workflow(
    arxiv_input: str,
    daas_url: str,
    output_dir: str,
    advanced_arg: str,
    timeout_sec: int,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Arxiv 精细翻译（Docker/DaaS）并可选双库存档。"""
    from src.research.arxiv_fine_translation import run_arxiv_fine_translation_docker

    logger.info("=== 开始 Arxiv 精细翻译（Docker）流程 ===")
    result = run_arxiv_fine_translation_docker(
        arxiv_input=arxiv_input,
        server_url=daas_url,
        output_dir=output_dir,
        advanced_arg=advanced_arg,
        timeout_sec=timeout_sec,
    )

    logger.info(f"Arxiv 精细翻译状态: {result.status}")
    if result.status != "completed":
        logger.error(f"Arxiv 精细翻译失败: {result.error}")
        return {
            "status": "failed",
            "arxiv_id": result.arxiv_id,
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_files": result.output_files,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"arxiv:{result.arxiv_id}",
            result_payload={
                "source_type": "arxiv_docker",
                "char_count": len(result.server_message),
                "summary": result.summary,
                "translation_excerpt": result.translation_excerpt,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "translated": True,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": "completed",
        "arxiv_id": result.arxiv_id,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_files": result.output_files,
        "error": "",
        "storage": storage_result,
    }


def run_md_translate_workflow(
    input_path: str,
    language: str,
    output_dir: str,
    additional_prompt: str,
    max_workers: int,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Markdown 中英互译并可选双库存档。"""
    from src.research.markdown_translate import run_markdown_translate

    logger.info("=== 开始 Markdown 中英互译流程 ===")
    result = run_markdown_translate(
        input_path=input_path,
        language=language,
        output_dir=output_dir,
        additional_prompt=additional_prompt,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    logger.info("Markdown 翻译状态: %s | %s", result.status, result.summary)
    if result.status == "failed":
        logger.error("Markdown 翻译失败: %s", result.error)
        return {
            "status": "failed",
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_files": result.output_files,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"md_translate:{input_path}",
            result_payload={
                "source_type": "markdown_translate",
                "language": language,
                "fragment_total": result.fragment_total,
                "fragment_ok": result.fragment_ok,
                "summary": result.summary,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "translated": True,
                "char_count": sum(
                    fr.get("char_count", 0) for fr in result.file_results
                ),
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "language": language,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_files": result.output_files,
        "summary": result.summary,
        "error": "",
        "storage": storage_result,
    }


def run_pdf_translation_workflow(
    pdf_path: str,
    target_language: str,
    output_dir: str,
    additional_prompt: str,
    max_tokens_per_fragment: int,
    max_workers: int,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 PDF 论文全文翻译并可选双库存档。"""
    from src.research.pdf_translation import run_pdf_full_text_translation

    logger.info("=== 开始 PDF 论文全文翻译流程 ===")
    result = run_pdf_full_text_translation(
        pdf_path=pdf_path,
        target_language=target_language,
        output_dir=output_dir,
        additional_prompt=additional_prompt,
        max_tokens_per_fragment=max_tokens_per_fragment,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    logger.info("PDF翻译状态: %s | %s", result.status, result.summary)
    if result.status == "failed":
        logger.error("PDF翻译失败: %s", result.error)
        return {
            "status": "failed",
            "pdf_path": pdf_path,
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_html": result.output_html,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"pdf_translate:{pdf_path}",
            result_payload={
                "source_type": "pdf_full_text_translation",
                "title": result.title,
                "title_translated": result.abstract_translated,
                "abstract": result.abstract,
                "abstract_translated": result.abstract_translated,
                "fragment_total": result.fragment_total,
                "fragment_ok": result.fragment_ok,
                "summary": result.summary,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "output_html": result.output_html,
                "translated": True,
                "char_count": result.char_count,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "pdf_path": pdf_path,
        "title": result.title,
        "title_translated": result.abstract_translated,
        "char_count": result.char_count,
        "fragment_total": result.fragment_total,
        "fragment_ok": result.fragment_ok,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_html": result.output_html,
        "summary": result.summary,
        "error": "",
        "storage": storage_result,
    }


def run_arxiv_quick_helper_workflow(
    arxiv_url: str,
    output_dir: str,
    target_lang: str,
    enable_translation: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Arxiv 快速助手（下载 PDF + 翻译摘要）并可选双库存档。"""
    from src.research.arxiv_quick_helper import run_arxiv_quick_helper

    logger.info("=== 开始 Arxiv 快速助手流程 ===")
    
    # 构建 LLM 引擎（如果启用翻译）
    llm_engine = None
    if enable_translation:
        try:
            from src.llm.llm_engine import LLMEngine
            llm_engine = LLMEngine()
        except Exception as e:
            logger.warning(f"LLM 引擎初始化失败，将跳过摘要翻译: {e}")
            enable_translation = False
    
    result = run_arxiv_quick_helper(
        arxiv_url=arxiv_url,
        output_dir=output_dir,
        target_lang=target_lang,
        enable_translation=enable_translation,
        llm_engine=llm_engine,
    )

    logger.info("Arxiv 助手状态: %s | 论文 ID: %s", result.status, result.arxiv_id)
    if result.status == "error":
        logger.error("Arxiv 助手处理失败: %s", result.error)
        return {
            "status": "error",
            "arxiv_id": result.arxiv_id,
            "url": arxiv_url,
            "pdf_path": result.pdf_path,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"arxiv_helper:{result.arxiv_id}",
            result_payload={
                "source_type": "arxiv_quick_helper",
                "arxiv_id": result.arxiv_id,
                "title": result.title,
                "authors": result.authors,
                "publish_date": result.publish_date,
                "abstract_en": result.abstract_en,
                "abstract_zh": result.abstract_zh,
                "pdf_path": result.pdf_path,
                "pdf_size_mb": result.pdf_size_mb,
                "translated": enable_translation,
                "target_language": target_lang,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "arxiv_id": result.arxiv_id,
        "url": arxiv_url,
        "title": result.title,
        "authors": result.authors,
        "publish_date": result.publish_date,
        "abstract_en": result.abstract_en,
        "abstract_zh": result.abstract_zh,
        "pdf_path": result.pdf_path,
        "pdf_size_mb": result.pdf_size_mb,
        "error": result.error,
        "storage": storage_result,
    }


def run_google_scholar_helper_workflow(
    scholar_url: str,
    output_dir: str,
    topic_hint: str,
    target_lang: str,
    max_papers: int,
    use_llm: bool,
    additional_prompt: str,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Google Scholar 统合小助手并可选双库存档。"""
    from src.research.google_scholar_helper import run_google_scholar_related_works

    logger.info("=== 开始 Google Scholar 统合小助手流程 ===")

    llm_engine = None
    if use_llm:
        try:
            from src.llm.llm_engine import LLMEngine
            llm_engine = LLMEngine()
        except Exception as e:
            logger.warning(f"LLM 引擎初始化失败，将使用 fallback 相关工作草稿: {e}")
            use_llm = False

    result = run_google_scholar_related_works(
        scholar_url=scholar_url,
        output_dir=output_dir,
        max_papers=max_papers,
        topic_hint=topic_hint,
        target_lang=target_lang,
        use_llm=use_llm,
        llm_engine=llm_engine,
        additional_prompt=additional_prompt,
    )

    logger.info("Scholar 助手状态: %s | 文献条目: %d", result.status, result.total_papers)
    if result.status == "error":
        logger.error("Scholar 助手处理失败: %s", result.error)
        return {
            "status": "error",
            "url": scholar_url,
            "total_papers": result.total_papers,
            "output_markdown": result.output_markdown,
            "output_json": result.output_json,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"google_scholar_helper:{scholar_url}",
            result_payload={
                "source_type": "google_scholar_helper",
                "title": "Google Scholar Related Works",
                "authors": "",
                "publish_date": "",
                "abstract_en": "",
                "abstract_zh": result.related_works_md,
                "summary": f"parsed_papers={result.total_papers}",
                "pdf_path": "",
                "pdf_size_mb": 0,
                "translated": use_llm,
                "target_language": target_lang,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "char_count": len(result.related_works_md or ""),
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "url": scholar_url,
        "total_papers": result.total_papers,
        "output_markdown": result.output_markdown,
        "output_json": result.output_json,
        "related_works_md": result.related_works_md,
        "error": result.error,
        "storage": storage_result,
    }


def build_storage_connection_from_args(args: argparse.Namespace) -> Dict[str, str]:
    """构建论文插件持久化所需的双库连接参数。"""
    db_password = args.paper_db_password or os.getenv("DB_PASSWORD", "")
    db_host = args.paper_db_host or os.getenv("DB_HOST", "localhost")
    db_port = args.paper_db_port or os.getenv("DB_PORT", "5432")
    db_user = args.paper_db_user or os.getenv("DB_USER", "tcm_user")
    db_name = args.paper_db_name or os.getenv("DB_NAME", "tcm_autoresearch")

    neo4j_password = args.paper_neo4j_password or os.getenv("NEO4J_PASSWORD", "")
    neo4j_host = args.paper_neo4j_host or os.getenv("NEO4J_HOST", "localhost")
    neo4j_port = args.paper_neo4j_port or os.getenv("NEO4J_PORT", "7687")
    neo4j_user = args.paper_neo4j_user or os.getenv("NEO4J_USER", "neo4j")
    neo4j_scheme = args.paper_neo4j_scheme or os.getenv("NEO4J_SCHEME", "neo4j")

    pg_url = args.paper_pg_url or f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    neo4j_uri = args.paper_neo4j_uri or f"{neo4j_scheme}://{neo4j_host}:{neo4j_port}"

    return {
        "pg_url": pg_url,
        "neo4j_uri": neo4j_uri,
        "neo4j_user": neo4j_user,
        "neo4j_password": neo4j_password,
    }


def persist_paper_result_to_dual_storage(
    source_path: str,
    result_payload: Dict[str, Any],
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, str]:
    """将论文插件输出写入 PostgreSQL + Neo4j。"""
    from src.storage import UnifiedStorageDriver

    storage = None
    doc_id = None
    try:
        if not neo4j_password:
            return {
                "status": "failed",
                "document_id": "",
                "error": "NEO4J_PASSWORD 未提供，无法完成双库存档",
            }
        if "://@" in pg_url:
            return {
                "status": "failed",
                "document_id": "",
                "error": "PostgreSQL 连接字符串缺少密码",
            }

        storage = UnifiedStorageDriver(pg_url, neo4j_uri, (neo4j_user, neo4j_password))
        storage.initialize()

        doc_id = storage.save_document(
            source_file=source_path,
            objective="paper_plugin_archive",
            raw_text_size=int(result_payload.get("char_count", 0)),
        )
        if not doc_id:
            return {
                "status": "failed",
                "document_id": "",
                "error": "保存文档失败",
            }

        storage.update_document_status(doc_id, "processing")
        storage.log_module_execution(
            document_id=doc_id,
            module_name="paper_plugin",
            status="start",
            message="论文插件结果开始双库存档",
        )

        source_name = Path(source_path).name
        entities = [
            {
                "name": source_name,
                "type": "other",
                "confidence": 0.99,
                "position": 0,
                "length": len(source_name),
                "description": "论文来源文件",
                "metadata": {
                    "source_type": result_payload.get("source_type", "unknown"),
                    "source_path": source_path,
                },
            },
            {
                "name": "论文摘要",
                "type": "other",
                "confidence": 0.95,
                "position": 0,
                "length": len(result_payload.get("summary", "")),
                "description": result_payload.get("summary", ""),
                "metadata": {
                    "summary_lang": "中文",
                    "generated_by": "paper_plugin",
                },
            },
            {
                "name": "翻译节选",
                "type": "other",
                "confidence": 0.90,
                "position": 0,
                "length": len(result_payload.get("translation_excerpt", "")),
                "description": result_payload.get("translation_excerpt", ""),
                "metadata": {
                    "translated": bool(result_payload.get("translated", False)),
                    "generated_by": "paper_plugin",
                },
            },
        ]
        entity_ids = storage.save_entities(doc_id, entities)
        if len(entity_ids) < 3:
            storage.update_document_status(doc_id, "failed")
            return {
                "status": "failed",
                "document_id": str(doc_id),
                "error": "保存实体失败",
            }

        relationships = [
            {
                "source_entity_id": entity_ids[0],
                "target_entity_id": entity_ids[1],
                "relationship_type": "CONTAINS",
                "confidence": 0.95,
                "created_by_module": "paper_plugin",
                "evidence": "论文包含摘要内容",
                "metadata": {"semantic_role": "summary"},
            },
            {
                "source_entity_id": entity_ids[0],
                "target_entity_id": entity_ids[2],
                "relationship_type": "CONTAINS",
                "confidence": 0.90,
                "created_by_module": "paper_plugin",
                "evidence": "论文包含翻译节选内容",
                "metadata": {"semantic_role": "translation_excerpt"},
            },
        ]
        rel_ids = storage.save_relationships(doc_id, relationships)

        storage.save_statistics(
            doc_id,
            {
                "formulas_count": 0,
                "herbs_count": 0,
                "syndromes_count": 0,
                "efficacies_count": 0,
                "relationships_count": len(rel_ids),
                "graph_nodes_count": len(entity_ids),
                "graph_edges_count": len(rel_ids),
                "graph_density": 0.0,
                "connected_components": 1,
                "source_modules": ["paper_plugin"],
                "processing_time_ms": 0,
            },
        )

        storage.save_research_analysis(
            doc_id,
            {
                "summary_analysis": {
                    "paper_summary": result_payload.get("summary", ""),
                    "translation_excerpt": result_payload.get("translation_excerpt", ""),
                    "paper_source_type": result_payload.get("source_type", "unknown"),
                    "paper_output_json": result_payload.get("output_json", ""),
                    "paper_output_markdown": result_payload.get("output_markdown", ""),
                }
            },
        )

        storage.log_module_execution(
            document_id=doc_id,
            module_name="paper_plugin",
            status="success",
            message="论文插件结果已完成双库存档",
        )
        storage.update_document_status(doc_id, "completed")
        return {
            "status": "completed",
            "document_id": str(doc_id),
            "error": "",
        }
    except Exception as exc:
        if storage and doc_id:
            try:
                storage.log_module_execution(
                    document_id=doc_id,
                    module_name="paper_plugin",
                    status="failure",
                    message="论文插件双库存档失败",
                    error_details=str(exc),
                )
                storage.update_document_status(doc_id, "failed")
            except Exception:
                pass
        return {
            "status": "failed",
            "document_id": str(doc_id) if doc_id else "",
            "error": str(exc),
        }
    finally:
        if storage:
            storage.close()


def export_research_session_reports(
    session_result: Dict[str, Any],
    report_formats: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    return _export_research_session_reports_impl(session_result, report_formats, output_dir)


def _extract_research_phase_results(cycle_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _extract_research_phase_results_impl(cycle_snapshot)


def run_research_session(
    question: str,
    config: Dict[str, Any],
    phase_names: Optional[List[str]] = None,
    export_report_formats: Optional[List[str]] = None,
    report_output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """通过 ResearchPipeline 执行完整科研闭环。

    Parameters
    ----------
    question : str
        研究问题 / 假设陈述。
    config : dict
        传递给 ResearchPipeline 的额外配置。
    phase_names : list[str] | None
        要顺序执行的阶段名称列表，默认仅 ``["observe"]``。

    Returns
    -------
    dict
        包含 ``status``、``cycle_id`` 和各阶段执行结果的字典。
    """
    from src.research.research_pipeline import ResearchPipeline
    from src.research.study_session_manager import ResearchPhase

    PHASE_MAP = {p.value: p for p in ResearchPhase}

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

    for pname in phase_names:
        phase_enum = PHASE_MAP.get(pname.lower())
        if phase_enum is None:
            logger.warning("跳过未知阶段: %s (可选: %s)", pname, list(PHASE_MAP.keys()))
            continue
        logger.info(">>> 开始阶段: %s", phase_enum.value)
        try:
            phase_context: Dict[str, Any] = {"question": question}

            if phase_enum.value == "observe":
                local_data_dir = (
                    (config.get("local_corpus") or {}).get("data_dir")
                    or str((Path(__file__).resolve().parent / "data").resolve())
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

    snapshot_phase_results = _extract_research_phase_results(cycle_snapshot)
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

    # 持久化到 output 目录
    output_file = Path(f"./output/research_session_{int(time.time())}.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("科研闭环结果已保存: %s", output_file)
    logger.info("=== 科研闭环模式结束 (status=%s) ===", overall_status)

    return summary


def main():
    """主函数"""
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

# (已移除重复的 run_full_cycle_demo 定义)


if __name__ == "__main__":
    sys.exit(main())
