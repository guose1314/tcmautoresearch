"""
中医古籍全自动研究系统 — 循环报告与阶段追踪

从 run_cycle_demo.py 提取的报告/序列化/分析汇总逻辑。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CYCLE_DEMO_GOVERNANCE = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_quality_score": 0.85,
    "export_contract_version": "d58.v1",
}


def load_cycle_demo_governance_config(
    config_path: Optional[Path] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """加载 cycle_demo 治理配置。"""
    from src.infrastructure.config_loader import load_settings_section

    section = load_settings_section(
        'governance.cycle_demo',
        config_path=config_path,
        environment=environment,
        default={},
    )
    return {
        'enable_phase_tracking': bool(section.get('enable_phase_tracking', DEFAULT_CYCLE_DEMO_GOVERNANCE['enable_phase_tracking'])),
        'persist_failed_operations': bool(section.get('persist_failed_operations', DEFAULT_CYCLE_DEMO_GOVERNANCE['persist_failed_operations'])),
        'minimum_stable_quality_score': float(section.get('minimum_stable_quality_score', DEFAULT_CYCLE_DEMO_GOVERNANCE['minimum_stable_quality_score'])),
        'export_contract_version': str(section.get('export_contract_version', DEFAULT_CYCLE_DEMO_GOVERNANCE['export_contract_version'])),
    }


# ── 序列化 ─────────────────────────────────────────────────────────


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_value(item) for item in value]
    return value


# ── 阶段追踪 ───────────────────────────────────────────────────────


def start_phase(runtime_metadata: Dict[str, Any], phase_name: str, details: Optional[Dict[str, Any]] = None) -> float:
    started_at = time.time()
    runtime_metadata.setdefault('phase_history', []).append(
        {
            'phase': phase_name,
            'status': 'in_progress',
            'started_at': datetime.now().isoformat(),
            'details': serialize_value(details or {}),
        }
    )
    return started_at


def complete_phase(
    runtime_metadata: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    details: Optional[Dict[str, Any]] = None,
    final_status: Optional[str] = None,
) -> None:
    duration = max(0.0, time.time() - phase_started_at)
    runtime_metadata.setdefault('phase_timings', {})[phase_name] = round(duration, 6)
    completed_phases = runtime_metadata.setdefault('completed_phases', [])
    if phase_name not in completed_phases:
        completed_phases.append(phase_name)
    runtime_metadata['last_completed_phase'] = phase_name
    runtime_metadata['failed_phase'] = None
    if final_status is not None:
        runtime_metadata['final_status'] = final_status

    for phase in reversed(runtime_metadata.get('phase_history', [])):
        if phase.get('phase') == phase_name and phase.get('status') == 'in_progress':
            phase['status'] = 'completed'
            phase['ended_at'] = datetime.now().isoformat()
            phase['duration_seconds'] = round(duration, 6)
            if details:
                phase['details'] = serialize_value({**phase.get('details', {}), **details})
            break


def record_failed_operation(
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    operation_name: str,
    error: str,
    details: Optional[Dict[str, Any]] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    if not governance_config.get('persist_failed_operations', True):
        return
    failed_operations.append(
        {
            'operation': operation_name,
            'error': error,
            'details': serialize_value(details or {}),
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': round(duration_seconds or 0.0, 6),
        }
    )


def fail_phase(
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    error: Exception,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    duration = max(0.0, time.time() - phase_started_at)
    runtime_metadata.setdefault('phase_timings', {})[phase_name] = round(duration, 6)
    runtime_metadata['failed_phase'] = phase_name
    runtime_metadata['final_status'] = 'failed'
    record_failed_operation(failed_operations, governance_config, phase_name, str(error), details, duration)

    for phase in reversed(runtime_metadata.get('phase_history', [])):
        if phase.get('phase') == phase_name and phase.get('status') == 'in_progress':
            phase['status'] = 'failed'
            phase['ended_at'] = datetime.now().isoformat()
            phase['duration_seconds'] = round(duration, 6)
            phase['error'] = str(error)
            if details:
                phase['details'] = serialize_value({**phase.get('details', {}), **details})
            break


# ── 元数据构建 ─────────────────────────────────────────────────────


def build_runtime_metadata(runtime_metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'phase_history': serialize_value(runtime_metadata.get('phase_history', [])),
        'phase_timings': serialize_value(runtime_metadata.get('phase_timings', {})),
        'completed_phases': list(runtime_metadata.get('completed_phases', [])),
        'failed_phase': runtime_metadata.get('failed_phase'),
        'final_status': runtime_metadata.get('final_status', 'initialized'),
        'last_completed_phase': runtime_metadata.get('last_completed_phase'),
    }


def build_iteration_analysis_summary(iteration_results: Dict[str, Any]) -> Dict[str, Any]:
    modules = iteration_results.get('modules', [])
    module_count = len(modules)
    completed_modules = sum(1 for item in modules if item.get('status') == 'completed')
    failed_modules = sum(1 for item in modules if item.get('status') != 'completed')
    quality_scores: List[float] = []
    for module in modules:
        quality_metrics = module.get('quality_metrics', {})
        if quality_metrics:
            values = [float(v) for v in quality_metrics.values() if isinstance(v, (int, float))]
            if values:
                quality_scores.append(sum(values) / len(values))
    average_quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

    return {
        'module_count': module_count,
        'completed_module_count': completed_modules,
        'failed_module_count': failed_modules,
        'average_quality_score': round(average_quality_score, 6),
        'insight_count': len(iteration_results.get('academic_insights', [])),
        'recommendation_count': len(iteration_results.get('recommendations', [])),
        'final_status': iteration_results.get('status', 'unknown'),
    }


def build_cycle_demo_analysis_summary(cycle_results: Dict[str, Any], governance_config: Dict[str, Any]) -> Dict[str, Any]:
    iterations = cycle_results.get('iterations', [])
    successful_iterations = sum(1 for item in iterations if item.get('status') == 'completed')
    failed_iterations = len(iterations) - successful_iterations
    quality_score = float(cycle_results.get('academic_analysis', {}).get('quality_assessment', {}).get('overall_quality_score', 0.0) or 0.0)
    status = 'idle'
    if iterations or cycle_results.get('failed_operations'):
        status = (
            'stable'
            if failed_iterations == 0 and quality_score >= float(governance_config.get('minimum_stable_quality_score', 0.85))
            else 'needs_followup'
        )

    return {
        'status': status,
        'iteration_count': len(iterations),
        'successful_iteration_count': successful_iterations,
        'failed_iteration_count': failed_iterations,
        'average_execution_time': float(cycle_results.get('performance_metrics', {}).get('average_execution_time', 0.0) or 0.0),
        'overall_quality_score': quality_score,
        'failed_operation_count': len(cycle_results.get('failed_operations', [])),
        'failed_phase': cycle_results.get('metadata', {}).get('failed_phase'),
        'final_status': cycle_results.get('metadata', {}).get('final_status', 'initialized'),
        'last_completed_phase': cycle_results.get('metadata', {}).get('last_completed_phase'),
    }


def build_report_metadata(
    governance_config: Dict[str, Any],
    metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    report_metadata = {
        'contract_version': governance_config['export_contract_version'],
        'generated_at': datetime.now().isoformat(),
        'result_schema': 'cycle_demo_report',
        'failed_operation_count': len(failed_operations),
        'final_status': metadata.get('final_status', 'initialized'),
        'last_completed_phase': metadata.get('last_completed_phase'),
    }
    if output_path is not None:
        report_metadata['output_path'] = str(output_path)
    return report_metadata


# ── 报告导出 ───────────────────────────────────────────────────────


def export_cycle_demo_report(cycle_results: Dict[str, Any], output_path: Path, governance_config: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.loads(json.dumps(cycle_results, ensure_ascii=False, default=str))
    metadata = payload.setdefault('metadata', build_runtime_metadata({}))
    failed_operations = payload.setdefault('failed_operations', [])
    export_started_at = start_phase(metadata, 'export_cycle_demo_report', {'output_path': str(output_path)})
    complete_phase(metadata, 'export_cycle_demo_report', export_started_at, {'output_path': str(output_path)}, final_status=metadata.get('final_status', 'completed'))
    payload['metadata'] = build_runtime_metadata(metadata)
    payload['analysis_summary'] = build_cycle_demo_analysis_summary(payload, governance_config)
    payload['report_metadata'] = build_report_metadata(governance_config, metadata, failed_operations, output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return payload


# ── 质量评估 ───────────────────────────────────────────────────────
# summarize_module_quality 及辅助函数已迁移至 src.research.module_pipeline，
# 此处保留兼容重导出。
from src.research.module_pipeline import (  # noqa: E402
    summarize_module_quality,
    _MODULE_EXPECTED_KEYS,
    _MODULE_CONTENT_KEYS,
    _compute_completeness,
    _compute_accuracy,
    _compute_consistency,
)


# ── 科研报告导出 ───────────────────────────────────────────────────

# extract_research_phase_results 已迁移至 src.research.phase_result，
# 此处保留兼容重导出。
from src.research.phase_result import extract_research_phase_results  # noqa: E402, F811


def export_research_session_reports(
    session_result: Dict[str, Any],
    report_formats: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """基于 session_result 直接导出 IMRD 报告。"""
    from src.generation.report_generator import ReportGenerator

    normalized_formats = [
        str(item).strip().lower()
        for item in (report_formats or ["markdown"])
        if str(item).strip()
    ]
    generator = ReportGenerator({"output_dir": output_dir or "./output/research_reports"})
    reports: Dict[str, Any] = {}
    output_files: Dict[str, str] = {}
    errors: List[Dict[str, str]] = []
    initialized = False

    try:
        initialized = bool(generator.initialize())
        if not initialized:
            return {
                "reports": {},
                "output_files": {},
                "errors": [{"initialize": "ReportGenerator 初始化失败"}],
            }

        for report_format in normalized_formats:
            try:
                report = generator.generate_report(session_result, report_format)
                reports[report.format] = report.to_dict()
                if report.output_path:
                    output_files[report.format] = report.output_path
            except Exception as exc:
                errors.append({report_format: str(exc)})
    finally:
        if initialized:
            generator.cleanup()

    return {
        "reports": reports,
        "output_files": output_files,
        "errors": errors,
    }
