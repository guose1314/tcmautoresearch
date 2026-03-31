"""
Quality assessment system.

This tool evaluates engineering quality by converting gate results into
dimension scores, overall score, grade, and actionable recommendations.

Usage:
    python tools/quality_assessment.py --gates-report output/quality-gate.json
    python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_LOADER_REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src" / "infrastructure" / "config_loader.py").exists()),
    None,
)
if _CONFIG_LOADER_REPO_ROOT is not None and str(_CONFIG_LOADER_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONFIG_LOADER_REPO_ROOT))

from src.infrastructure.config_loader import load_settings_section

DEFAULT_WEIGHTS = {
    "gate_stability": 0.25,
    "test_reliability": 0.20,
    "logic_health": 0.20,
    "code_health": 0.20,
    "architecture_health": 0.15,
}

DEFAULT_GOVERNANCE_CONFIG = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_overall_score": 85.0,
    "export_contract_version": "d49.v1",
}


@dataclass(frozen=True)
class AssessmentThresholds:
    min_overall_score: float = 85.0
    min_dimension_score: float = 70.0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    merged = dict(DEFAULT_WEIGHTS)
    for key, value in (weights or {}).items():
        if key in merged:
            merged[key] = max(0.0, float(value))
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in merged.items()}


def _load_quality_assessment_section(config_path: Path | None) -> Dict[str, Any]:
    # Backward compatible with historical top-level quality_assessment,
    # while preferring the centralized governance namespace.
    return load_settings_section(
        "quality_assessment",
        "governance.quality_assessment",
        config_path=config_path,
        default={},
    )


def _load_thresholds_from_config(config_path: Path) -> AssessmentThresholds:
    section = _load_quality_assessment_section(config_path)
    return AssessmentThresholds(
        min_overall_score=float(section.get("min_overall_score", 85.0)),
        min_dimension_score=float(section.get("min_dimension_score", 70.0)),
    )


def _load_governance_config(config_path: Path) -> Dict[str, Any]:
    section = _load_quality_assessment_section(config_path)
    return {
        "enable_phase_tracking": bool(section.get("enable_phase_tracking", DEFAULT_GOVERNANCE_CONFIG["enable_phase_tracking"])),
        "persist_failed_operations": bool(section.get("persist_failed_operations", DEFAULT_GOVERNANCE_CONFIG["persist_failed_operations"])),
        "minimum_stable_overall_score": float(
            section.get("minimum_stable_overall_score", section.get("min_overall_score", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_overall_score"]))
        ),
        "export_contract_version": str(section.get("export_contract_version", DEFAULT_GOVERNANCE_CONFIG["export_contract_version"])),
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value


def _start_phase(runtime_metadata: Dict[str, Any], phase_name: str, details: Dict[str, Any] | None = None) -> float:
    started_at = time.time()
    runtime_metadata.setdefault("phase_history", []).append(
        {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "details": _serialize_value(details or {}),
        }
    )
    return started_at


def _complete_phase(
    runtime_metadata: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    details: Dict[str, Any] | None = None,
    final_status: str | None = None,
) -> None:
    duration = max(0.0, time.time() - phase_started_at)
    runtime_metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
    completed_phases = runtime_metadata.setdefault("completed_phases", [])
    if phase_name not in completed_phases:
        completed_phases.append(phase_name)
    runtime_metadata["last_completed_phase"] = phase_name
    runtime_metadata["failed_phase"] = None
    if final_status is not None:
        runtime_metadata["final_status"] = final_status

    for phase in reversed(runtime_metadata.get("phase_history", [])):
        if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
            phase["status"] = "completed"
            phase["ended_at"] = datetime.now().isoformat()
            phase["duration_seconds"] = round(duration, 6)
            if details:
                phase["details"] = _serialize_value({**phase.get("details", {}), **details})
            break


def _record_failed_operation(
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    operation_name: str,
    error: Exception,
    details: Dict[str, Any] | None = None,
    duration_seconds: float | None = None,
) -> None:
    if not governance_config.get("persist_failed_operations", True):
        return

    failed_operations.append(
        {
            "operation": operation_name,
            "error": str(error),
            "details": _serialize_value(details or {}),
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(duration_seconds or 0.0, 6),
        }
    )


def _fail_phase(
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    phase_name: str,
    phase_started_at: float,
    error: Exception,
    details: Dict[str, Any] | None = None,
) -> None:
    duration = max(0.0, time.time() - phase_started_at)
    runtime_metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
    runtime_metadata["failed_phase"] = phase_name
    runtime_metadata["final_status"] = "failed"
    _record_failed_operation(failed_operations, governance_config, phase_name, error, details, duration)

    for phase in reversed(runtime_metadata.get("phase_history", [])):
        if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
            phase["status"] = "failed"
            phase["ended_at"] = datetime.now().isoformat()
            phase["duration_seconds"] = round(duration, 6)
            phase["error"] = str(error)
            if details:
                phase["details"] = _serialize_value({**phase.get("details", {}), **details})
            break


def _build_runtime_metadata(runtime_metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase_history": _serialize_value(runtime_metadata.get("phase_history", [])),
        "phase_timings": _serialize_value(runtime_metadata.get("phase_timings", {})),
        "completed_phases": list(runtime_metadata.get("completed_phases", [])),
        "failed_phase": runtime_metadata.get("failed_phase"),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }


def _build_analysis_summary(
    assessment: Dict[str, Any],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    overall_score = float(assessment.get("overall_score", 0.0) or 0.0)
    passed = bool(assessment.get("passed", False))
    status = "idle"
    if runtime_metadata.get("completed_phases") or failed_operations:
        status = (
            "stable"
            if passed and overall_score >= float(governance_config.get("minimum_stable_overall_score", 85.0))
            else "needs_followup"
        )

    return {
        "status": status,
        "overall_score": overall_score,
        "passed": passed,
        "failed_dimension_count": len(assessment.get("failed_dimensions", [])),
        "failed_operation_count": len(failed_operations),
        "failed_phase": runtime_metadata.get("failed_phase"),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }


def _build_report_metadata(
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    output_path: Path | None = None,
) -> Dict[str, Any]:
    report_metadata = {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": datetime.now().isoformat(),
        "result_schema": "quality_assessment_report",
        "failed_operation_count": len(failed_operations),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }
    if output_path is not None:
        report_metadata["output_path"] = str(output_path).replace("\\", "/")
    return report_metadata


def _assemble_assessment_report(
    assessment: Dict[str, Any],
    metrics: Dict[str, float],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    output_path: Path | None = None,
) -> Dict[str, Any]:
    report = dict(assessment)
    report["derived_metrics"] = metrics
    report["analysis_summary"] = _build_analysis_summary(report, governance_config, runtime_metadata, failed_operations)
    report["failed_operations"] = _serialize_value(failed_operations)
    report["metadata"] = _build_runtime_metadata(runtime_metadata)
    report["report_metadata"] = _build_report_metadata(governance_config, runtime_metadata, failed_operations, output_path)
    return report


def _index_gates(gate_results: List[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    return {str(item.get("name")): item for item in gate_results}


def metrics_from_gate_results(gate_results: List[Dict[str, object]]) -> Dict[str, float]:
    indexed = _index_gates(gate_results)
    total_gates = max(1, len(gate_results))
    passed_gates = sum(1 for item in gate_results if bool(item.get("success")))

    logic_gate = indexed.get("logic_checks", {})
    logic_metrics = logic_gate.get("metrics", {}) if isinstance(logic_gate.get("metrics", {}), dict) else {}
    logic_issues = float(logic_metrics.get("issue_count", 0) or 0)
    logic_errors = float(logic_metrics.get("error_count", 0) or 0)
    logic_health = 1.0 if logic_issues == 0 else _clamp(1.0 - (logic_errors / logic_issues))

    code_gate = indexed.get("code_quality", {})
    code_metrics = code_gate.get("metrics", {}) if isinstance(code_gate.get("metrics", {}), dict) else {}
    code_issues = float(code_metrics.get("issue_count", 0) or 0)
    code_errors = float(code_metrics.get("error_count", 0) or 0)
    code_warnings = float(code_metrics.get("warning_count", 0) or 0)
    if code_issues == 0:
        code_health = 1.0
    else:
        error_penalty = code_errors / code_issues
        warning_density = code_warnings / code_issues
        warning_penalty = min(0.25, warning_density * 0.25)
        code_health = _clamp(1.0 - error_penalty - warning_penalty)

    test_gate = indexed.get("quality_unit_tests", {})
    test_reliability = 1.0 if bool(test_gate.get("success")) else 0.0

    dependency_gate = indexed.get("dependency_graph", {})
    architecture_health = 1.0 if bool(dependency_gate.get("success")) else 0.0

    return {
        "gate_stability": _clamp(passed_gates / total_gates),
        "test_reliability": test_reliability,
        "logic_health": logic_health,
        "code_health": code_health,
        "architecture_health": architecture_health,
    }


def _grade(overall_score: float) -> str:
    if overall_score >= 90:
        return "A"
    if overall_score >= 80:
        return "B"
    if overall_score >= 70:
        return "C"
    return "D"


def _recommendations(failed_dimensions: List[str]) -> List[str]:
    mapping = {
        "gate_stability": "提升门禁稳定性，优先修复导致 gate 失败的阻断项。",
        "test_reliability": "补强单元测试稳定性与失败重现路径，减少不确定性。",
        "logic_health": "优先处理逻辑检查中的 ERROR，避免结构性回归。",
        "code_health": "持续降低复杂度与告警密度，分批重构高复杂函数。",
        "architecture_health": "保障依赖图生成与架构约束检查持续通过。",
    }
    if not failed_dimensions:
        return ["当前质量评估达标，建议维持小步迭代与持续监控。"]
    return [mapping[name] for name in failed_dimensions if name in mapping]


def assess_quality_metrics(
    metrics: Dict[str, float],
    thresholds: AssessmentThresholds,
    weights: Dict[str, float] | None = None,
) -> Dict[str, object]:
    normalized_weights = _normalize_weights(weights or DEFAULT_WEIGHTS)

    dimension_scores = {
        name: round(_clamp(float(value)) * 100.0, 2)
        for name, value in metrics.items()
    }

    overall_score = round(
        sum(dimension_scores.get(name, 0.0) * normalized_weights.get(name, 0.0) for name in normalized_weights),
        2,
    )

    failed_dimensions = [
        name
        for name, score in dimension_scores.items()
        if score < thresholds.min_dimension_score
    ]

    passed = overall_score >= thresholds.min_overall_score and not failed_dimensions
    return {
        "passed": passed,
        "overall_score": overall_score,
        "grade": _grade(overall_score),
        "dimension_scores": dimension_scores,
        "failed_dimensions": failed_dimensions,
        "thresholds": asdict(thresholds),
        "weights": normalized_weights,
        "recommendations": _recommendations(failed_dimensions),
    }


def assess_from_gate_results(
    gate_results: List[Dict[str, object]],
    config_path: Path,
) -> Dict[str, object]:
    governance_config = _load_governance_config(config_path)
    runtime_metadata: Dict[str, Any] = {
        "phase_history": [],
        "phase_timings": {},
        "completed_phases": [],
        "failed_phase": None,
        "final_status": "initialized",
        "last_completed_phase": None,
    }
    failed_operations: List[Dict[str, Any]] = []

    config_phase_started_at = _start_phase(runtime_metadata, "load_quality_assessment_config", {"config_path": str(config_path)})
    thresholds = _load_thresholds_from_config(config_path)
    _complete_phase(
        runtime_metadata,
        "load_quality_assessment_config",
        config_phase_started_at,
        {
            "config_path": str(config_path),
            "min_overall_score": thresholds.min_overall_score,
            "min_dimension_score": thresholds.min_dimension_score,
        },
    )

    metrics_phase_started_at = _start_phase(runtime_metadata, "derive_quality_metrics", {"gate_count": len(gate_results)})
    try:
        metrics = metrics_from_gate_results(gate_results)
        _complete_phase(
            runtime_metadata,
            "derive_quality_metrics",
            metrics_phase_started_at,
            {"gate_count": len(gate_results)},
        )

        assessment_phase_started_at = _start_phase(runtime_metadata, "assess_quality_metrics", {"dimension_count": len(metrics)})
        assessment = assess_quality_metrics(metrics, thresholds)
        runtime_metadata["final_status"] = "completed"
        _complete_phase(
            runtime_metadata,
            "assess_quality_metrics",
            assessment_phase_started_at,
            {
                "overall_score": assessment.get("overall_score", 0.0),
                "passed": assessment.get("passed", False),
            },
            final_status="completed",
        )
        return _assemble_assessment_report(assessment, metrics, governance_config, runtime_metadata, failed_operations)
    except Exception as error:
        _fail_phase(
            runtime_metadata,
            failed_operations,
            governance_config,
            "derive_quality_metrics",
            metrics_phase_started_at,
            error,
            {"gate_count": len(gate_results)},
        )
        assessment = {
            "passed": False,
            "overall_score": 0.0,
            "grade": "D",
            "dimension_scores": {},
            "failed_dimensions": ["gate_stability"],
            "thresholds": asdict(thresholds),
            "weights": _normalize_weights(DEFAULT_WEIGHTS),
            "recommendations": ["质量评估执行失败，需优先修复评估链路后再继续治理。"],
            "error": str(error),
        }
        return _assemble_assessment_report(assessment, {}, governance_config, runtime_metadata, failed_operations)


def export_assessment_report(assessment: Dict[str, object], output_path: Path) -> Dict[str, object]:
    report = json.loads(json.dumps(assessment, ensure_ascii=False))
    metadata = report.setdefault("metadata", _build_runtime_metadata({}))
    report_metadata = report.setdefault("report_metadata", {})
    failed_operations = report.setdefault("failed_operations", [])
    governance_config = {
        "export_contract_version": report_metadata.get("contract_version", DEFAULT_GOVERNANCE_CONFIG["export_contract_version"]),
        "persist_failed_operations": True,
        "minimum_stable_overall_score": report.get("thresholds", {}).get("min_overall_score", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_overall_score"]),
    }

    export_details = {"output_path": str(output_path).replace("\\", "/")}
    export_started_at = _start_phase(metadata, "export_assessment_report", export_details)
    _complete_phase(
        metadata,
        "export_assessment_report",
        export_started_at,
        export_details,
        final_status="completed" if metadata.get("final_status") != "cleaned" else metadata.get("final_status"),
    )
    report["metadata"] = _build_runtime_metadata(metadata)
    report["analysis_summary"] = _build_analysis_summary(report, governance_config, metadata, failed_operations)
    report["report_metadata"] = _build_report_metadata(governance_config, metadata, failed_operations, output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quality assessment system")
    parser.add_argument("--gates-report", default="output/quality-gate.json", help="Path to quality gate report JSON")
    parser.add_argument("--config", default="config.yml", help="Path to config YAML")
    parser.add_argument("--output", default="output/quality-assessment.json", help="Path to quality assessment report")
    args = parser.parse_args()

    gate_report_path = Path(args.gates_report).resolve()
    config_path = Path(args.config).resolve()
    output_path = Path(args.output).resolve()

    gate_report = json.loads(gate_report_path.read_text(encoding="utf-8"))
    gate_results = gate_report.get("results", [])
    assessment = assess_from_gate_results(gate_results, config_path)
    assessment = export_assessment_report(assessment, output_path)

    print("[quality-assessment] passed={passed}".format(passed=assessment["passed"]))
    print("[quality-assessment] overall_score={score} grade={grade}".format(score=assessment["overall_score"], grade=assessment["grade"]))
    print("[quality-assessment] report={path}".format(path=output_path))
    return 0 if assessment["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())