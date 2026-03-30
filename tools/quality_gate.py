"""
Unified quality gate for the repository.

This script consolidates three baseline controls:
1) Static logic checks
2) Dependency graph regeneration
3) Code quality static checks
4) Focused quality-tool unit tests
5) Quality assessment scoring
6) Continuous improvement loop
7) Quality improvement archive
8) Quality feedback mechanism

Usage:
    python tools/quality_gate.py
    python tools/quality_gate.py --report output/quality-gate.json
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from tools.code_quality_checks import run_checks as run_code_quality_checks
from tools.continuous_improvement_loop import (
    build_cycle_report,
    export_cycle_report,
    load_archive_history,
    load_history,
)
from tools.generate_dependency_graph import build_dependency_graph, write_outputs
from tools.logic_checks import run_checks
from tools.quality_assessment import assess_from_gate_results, export_assessment_report
from tools.quality_feedback import (
    build_feedback_report,
    export_feedback_report,
)
from tools.quality_improvement_archive import build_archive_entry, write_archive

DEFAULT_TEST_MODULES = [
    "tests.unit.test_logic_checks",
    "tests.unit.test_code_quality_checks",
    "tests.unit.test_continuous_improvement_loop",
    "tests.unit.test_dependency_graph_tool",
    "tests.unit.test_quality_assessment",
    "tests.unit.test_quality_improvement_archive",
    "tests.unit.test_quality_feedback",
    "tests.unit.test_quality_consumer_inventory",
]

DEFAULT_GOVERNANCE_CONFIG = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_success_rate": 1.0,
    "export_contract_version": "d63.v1",
}


@dataclass
class GateResult:
    name: str
    success: bool
    metrics: Dict[str, object] = field(default_factory=dict)
    details: Dict[str, object] = field(default_factory=dict)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_quality_gate_section(config_path: Path | None) -> Dict[str, Any]:
    if config_path is None or not config_path.exists() or yaml is None:
        return {}

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    governance = data.get("governance") or {}
    section = governance.get("quality_gate") or {}
    return section if isinstance(section, dict) else {}


def _load_governance_config(config_path: Path | None) -> Dict[str, Any]:
    section = _load_quality_gate_section(config_path)
    return {
        "enable_phase_tracking": bool(section.get("enable_phase_tracking", DEFAULT_GOVERNANCE_CONFIG["enable_phase_tracking"])),
        "persist_failed_operations": bool(section.get("persist_failed_operations", DEFAULT_GOVERNANCE_CONFIG["persist_failed_operations"])),
        "minimum_stable_success_rate": float(
            section.get("minimum_stable_success_rate", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_success_rate"])
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


def _normalize_reference_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _result_name(result: GateResult | Dict[str, object]) -> str:
    if isinstance(result, GateResult):
        return result.name
    return str(result.get("name", "unknown"))


def _result_details(result: GateResult | Dict[str, object]) -> Dict[str, object]:
    if isinstance(result, GateResult):
        return result.details
    details = result.get("details", {})
    return details if isinstance(details, dict) else {}


def _is_artifact_reference_key(key: str) -> bool:
    lowered = key.lower()
    return lowered == "outputs" or lowered.endswith(
        ("_path", "_report", "_file", "_json", "_markdown", "_index", "_dir")
    )


def _artifact_reference_entries(results: List[GateResult | Dict[str, object]]) -> List[tuple[str, str]]:
    entries: List[tuple[str, str]] = []
    for result in results:
        gate_name = _result_name(result)
        details = _result_details(result)
        for key in sorted(details):
            value = details[key]
            if key == "outputs" and isinstance(value, dict):
                for nested_key in sorted(value):
                    nested_value = value[nested_key]
                    if isinstance(nested_value, str):
                        entries.append((f"{gate_name}.outputs.{nested_key}", _normalize_reference_path(nested_value)))
                continue
            if _is_artifact_reference_key(key) and isinstance(value, str):
                entries.append((f"{gate_name}.{key}", _normalize_reference_path(value)))
    return entries


def _start_phase(runtime_metadata: Dict[str, Any], phase_name: str, details: Dict[str, Any] | None = None) -> float:
    started_at = time.time()
    if runtime_metadata.get("phase_history") is None:
        runtime_metadata["phase_history"] = []
    runtime_metadata.setdefault("phase_history", []).append(
        {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": _utc_now_iso(),
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
            phase["ended_at"] = _utc_now_iso()
            phase["duration_seconds"] = round(duration, 6)
            if details:
                phase["details"] = _serialize_value({**phase.get("details", {}), **details})
            break


def _record_failed_operation(
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    operation_name: str,
    error: str,
    details: Dict[str, Any] | None = None,
    duration_seconds: float | None = None,
) -> None:
    if not governance_config.get("persist_failed_operations", True):
        return

    failed_operations.append(
        {
            "operation": operation_name,
            "error": error,
            "details": _serialize_value(details or {}),
            "timestamp": _utc_now_iso(),
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
    _record_failed_operation(failed_operations, governance_config, phase_name, str(error), details, duration)

    for phase in reversed(runtime_metadata.get("phase_history", [])):
        if phase.get("phase") == phase_name and phase.get("status") == "in_progress":
            phase["status"] = "failed"
            phase["ended_at"] = _utc_now_iso()
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
    results: List[GateResult],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_gate_count = len(results)
    successful_gate_count = sum(1 for result in results if result.success)
    failed_gates = [result.name for result in results if not result.success]
    success_rate = successful_gate_count / total_gate_count if total_gate_count else 0.0
    status = "idle"
    if total_gate_count or failed_operations:
        status = (
            "stable"
            if success_rate >= float(governance_config.get("minimum_stable_success_rate", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_success_rate"]))
            else "needs_followup"
        )

    return {
        "status": status,
        "total_gate_count": total_gate_count,
        "successful_gate_count": successful_gate_count,
        "failed_gate_count": len(failed_gates),
        "success_rate": round(success_rate, 6),
        "failed_gate_names": failed_gates,
        "failed_operation_count": len(failed_operations),
        "failed_phase": runtime_metadata.get("failed_phase"),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }


def _build_report_metadata(
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    results: List[GateResult | Dict[str, object]],
    report_path: Path | None = None,
) -> Dict[str, Any]:
    artifact_entries = _artifact_reference_entries(results)
    report_metadata = {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": _utc_now_iso(),
        "result_schema": "quality_gate_report",
        "failed_operation_count": len(failed_operations),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        "gate_names": [_result_name(result) for result in results],
        "artifact_reference_labels": [label for label, _ in artifact_entries],
        "artifact_reference_paths": [path for _, path in artifact_entries],
    }
    if report_path is not None:
        report_metadata["output_path"] = _normalize_reference_path(report_path)
    return report_metadata


def _run_gate_phase(
    phase_name: str,
    root: Path,
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    governance_config: Dict[str, Any],
    operation,
) -> GateResult:
    phase_started_at = _start_phase(runtime_metadata, phase_name, {"root": str(root)})
    try:
        result = operation()
    except Exception as error:
        _fail_phase(
            runtime_metadata,
            failed_operations,
            governance_config,
            phase_name,
            phase_started_at,
            error,
            {"root": str(root)},
        )
        return GateResult(name=phase_name, success=False, metrics={}, details={"error": str(error)})

    if not result.success:
        _record_failed_operation(
            failed_operations,
            governance_config,
            result.name,
            "Gate reported unsuccessful result",
            {"metrics": result.metrics, "details": result.details},
        )

    _complete_phase(
        runtime_metadata,
        phase_name,
        phase_started_at,
        {"gate_name": result.name, "success": result.success},
        final_status="failed" if not result.success else runtime_metadata.get("final_status"),
    )
    return result


def _serialize_issue(issue: object, root: Path) -> Dict[str, object]:
    file_path = getattr(issue, "file_path")
    normalized_file = (
        str(file_path.relative_to(root)).replace("\\", "/")
        if file_path.is_absolute()
        else str(file_path)
    )
    return {
        "severity": getattr(issue, "severity"),
        "file": normalized_file,
        "line": getattr(issue, "line"),
        "message": getattr(issue, "message"),
    }


def _build_issue_gate_result(name: str, issues: List[object], root: Path) -> GateResult:
    errors = [issue for issue in issues if getattr(issue, "severity") == "ERROR"]
    warnings = [issue for issue in issues if getattr(issue, "severity") != "ERROR"]
    return GateResult(
        name=name,
        success=len(errors) == 0,
        metrics={
            "issue_count": len(issues),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
        details={
            "issues": [_serialize_issue(issue, root) for issue in issues]
        },
    )


def run_logic_gate(root: Path) -> GateResult:
    issues = run_checks(root)
    return _build_issue_gate_result("logic_checks", issues, root)


def run_dependency_graph_gate(root: Path, output_dir: Path) -> GateResult:
    graph = build_dependency_graph(root)
    outputs = write_outputs(graph, output_dir)
    return GateResult(
        name="dependency_graph",
        success=True,
        metrics={
            "module_count": graph["module_count"],
            "module_edge_count": graph["module_edge_count"],
            "package_count": graph["package_count"],
            "package_edge_count": graph["package_edge_count"],
        },
        details={
            "outputs": {
                name: str(path.relative_to(root)).replace("\\", "/")
                for name, path in outputs.items()
            }
        },
    )


def run_code_quality_gate(root: Path) -> GateResult:
    issues = run_code_quality_checks(root)
    return _build_issue_gate_result("code_quality", issues, root)


def run_unit_test_gate(root: Path, test_modules: List[str]) -> GateResult:
    command = [sys.executable, "-m", "unittest", *test_modules]
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return GateResult(
        name="quality_unit_tests",
        success=completed.returncode == 0,
        metrics={
            "return_code": completed.returncode,
            "test_module_count": len(test_modules),
        },
        details={
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
    )


def run_quality_assessment_gate(root: Path, gate_results: List[GateResult]) -> GateResult:
    assessment = assess_from_gate_results([asdict(item) for item in gate_results], root / "config.yml")
    output_path = root / "output" / "quality-assessment.json"
    assessment = export_assessment_report(assessment, output_path)
    return GateResult(
        name="quality_assessment",
        success=bool(assessment.get("passed")),
        metrics={
            "overall_score": assessment.get("overall_score", 0),
            "grade": assessment.get("grade", "D"),
            "failed_dimension_count": len(assessment.get("failed_dimensions", [])),
        },
        details={
            "assessment_report": str(output_path.relative_to(root)).replace("\\", "/"),
            "failed_dimensions": assessment.get("failed_dimensions", []),
            "recommendations": assessment.get("recommendations", []),
        },
    )


def run_continuous_improvement_gate(root: Path) -> GateResult:
    assessment_path = root / "output" / "quality-assessment.json"
    history_path = root / "output" / "quality-history.jsonl"
    archive_history_path = root / "output" / "quality-improvement-archive.jsonl"
    output_path = root / "output" / "continuous-improvement.json"

    if not assessment_path.exists():
        return GateResult(
            name="continuous_improvement",
            success=False,
            metrics={"history_points": 0},
            details={"error": "quality assessment report is missing"},
        )

    try:
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        history = load_history(history_path)
        archive_history = load_archive_history(archive_history_path)
        report = build_cycle_report(assessment, history, root / "config.yml", archive_history)
        report = export_cycle_report(report, history_path, output_path)
    except Exception as error:
        return GateResult(
            name="continuous_improvement",
            success=False,
            metrics={"history_points": 0},
            details={"error": str(error)},
        )

    return GateResult(
        name="continuous_improvement",
        success=True,
        metrics={
            "history_points": report["trend"].get("history_points", 0),
            "score_delta": report["trend"].get("score_delta", 0),
            "trend_status": report["trend"].get("status", "stable"),
            "backlog_count": len(report.get("action_backlog", [])),
        },
        details={
            "continuous_report": str(output_path.relative_to(root)).replace("\\", "/"),
            "history_file": str(history_path.relative_to(root)).replace("\\", "/"),
        },
    )


def run_quality_improvement_archive_gate(root: Path, gate_report: Dict[str, object]) -> GateResult:
    assessment_path = root / "output" / "quality-assessment.json"
    improvement_path = root / "output" / "continuous-improvement.json"
    inventory_path = root / "output" / "quality-consumer-inventory.json"
    if not assessment_path.exists() or not improvement_path.exists() or not inventory_path.exists():
        return GateResult(
            name="quality_improvement_archive",
            success=False,
            metrics={"archive_entry_written": 0},
            details={"error": "assessment, improvement, or inventory report is missing"},
        )

    try:
        assessment_report = json.loads(assessment_path.read_text(encoding="utf-8"))
        improvement_report = json.loads(improvement_path.read_text(encoding="utf-8"))
        inventory_report = json.loads(inventory_path.read_text(encoding="utf-8"))
        entry = build_archive_entry(gate_report, assessment_report, improvement_report, root / "config.yml", inventory_report)

        outputs = write_archive(
            entry,
            root / "output" / "quality-improvement-archive.jsonl",
            root / "docs" / "quality-archive",
            root / "output" / "quality-improvement-archive-latest.json",
        )
    except Exception as error:
        return GateResult(
            name="quality_improvement_archive",
            success=False,
            metrics={"archive_entry_written": 0},
            details={"error": str(error)},
        )

    return GateResult(
        name="quality_improvement_archive",
        success=True,
        metrics={
            "archive_entry_written": 1,
            "quality_score": entry.get("quality_score", 0.0),
            "trend_status": entry.get("trend_status", "unknown"),
        },
        details={
            "history_file": str(outputs["history"].relative_to(root)).replace("\\", "/"),
            "dossier_file": str(outputs["dossier"].relative_to(root)).replace("\\", "/"),
            "latest_file": str(outputs["latest"].relative_to(root)).replace("\\", "/"),
        },
    )


def run_quality_feedback_gate(root: Path) -> GateResult:
    assessment_path = root / "output" / "quality-assessment.json"
    improvement_path = root / "output" / "continuous-improvement.json"
    archive_latest_path = root / "output" / "quality-improvement-archive-latest.json"
    inventory_path = root / "output" / "quality-consumer-inventory.json"
    if not assessment_path.exists() or not improvement_path.exists() or not archive_latest_path.exists() or not inventory_path.exists():
        return GateResult(
            name="quality_feedback",
            success=False,
            metrics={"priority_action_count": 0},
            details={"error": "required inputs for quality feedback are missing"},
        )

    try:
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        improvement = json.loads(improvement_path.read_text(encoding="utf-8"))
        archive_latest = json.loads(archive_latest_path.read_text(encoding="utf-8"))
        inventory_report = json.loads(inventory_path.read_text(encoding="utf-8"))
        feedback = build_feedback_report(assessment, improvement, archive_latest, root / "config.yml", inventory_report)

        json_path = root / "output" / "quality-feedback.json"
        md_path = root / "output" / "quality-feedback.md"
        issue_dir = root / "output" / "quality-feedback-issues"
        issue_index = root / "output" / "quality-feedback-issues.json"
        feedback = export_feedback_report(feedback, json_path, md_path, issue_dir, issue_index)
        issue_index_payload = json.loads(issue_index.read_text(encoding="utf-8"))
    except Exception as error:
        return GateResult(
            name="quality_feedback",
            success=False,
            metrics={"priority_action_count": 0},
            details={"error": str(error)},
        )

    priority_count = len(feedback.get("priority_actions", []))
    owner_notifications = feedback.get("owner_notifications", [])
    owner_count = len(owner_notifications)
    owner_todo_count = sum(int(item.get("todo_count", 0)) for item in owner_notifications)
    level = str(feedback.get("feedback_level", "unknown"))
    return GateResult(
        name="quality_feedback",
        success=True,
        metrics={
            "feedback_level": level,
            "priority_action_count": priority_count,
            "owner_count": owner_count,
            "owner_todo_count": owner_todo_count,
            "issue_draft_count": int(issue_index_payload.get("count", 0)),
        },
        details={
            "feedback_json": str(json_path.relative_to(root)).replace("\\", "/"),
            "feedback_markdown": str(md_path.relative_to(root)).replace("\\", "/"),
            "feedback_issue_index": str(issue_index.relative_to(root)).replace("\\", "/"),
            "feedback_issue_dir": str(issue_dir.relative_to(root)).replace("\\", "/"),
        },
    )


def run_quality_consumer_inventory_gate(root: Path) -> GateResult:
    output_path = root / "output" / "quality-consumer-inventory.json"
    inventory_tool_path = Path(__file__).resolve().with_name("quality_consumer_inventory.py")
    command = [
        sys.executable,
        str(inventory_tool_path),
        "--config",
        str(root / "config.yml"),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return GateResult(
            name="quality_consumer_inventory",
            success=False,
            metrics={"return_code": completed.returncode},
            details={
                "command": command,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "inventory_report": str(output_path.relative_to(root)).replace("\\", "/"),
            },
        )

    report = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    analysis_summary = report.get("analysis_summary") or {}
    category_counts = analysis_summary.get("root_script_observation_category_counts") or {}
    missing_contract_count = int(analysis_summary.get("missing_contract_count", 0) or 0)
    uncategorized_count = int(category_counts.get("uncategorized_root_script", 0) or 0)
    recommendation = report.get("recommendation") or {}
    return GateResult(
        name="quality_consumer_inventory",
        success=missing_contract_count == 0 and uncategorized_count == 0,
        metrics={
            "return_code": completed.returncode,
            "scanned_consumer_count": int(analysis_summary.get("scanned_consumer_count", 0) or 0),
            "missing_contract_count": missing_contract_count,
            "uncategorized_root_script_count": uncategorized_count,
        },
        details={
            "command": command,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "inventory_report": str(output_path.relative_to(root)).replace("\\", "/"),
            "recommended_next_target": recommendation.get("recommended_path") or analysis_summary.get("recommended_next_target"),
            "root_script_observation_category_counts": category_counts,
        },
    )


def build_report(
    results: List[GateResult],
    governance_config: Dict[str, Any] | None = None,
    runtime_metadata: Dict[str, Any] | None = None,
    failed_operations: List[Dict[str, Any]] | None = None,
    report_path: Path | None = None,
) -> Dict[str, object]:
    governance_config = governance_config or dict(DEFAULT_GOVERNANCE_CONFIG)
    overall_success = all(result.success for result in results)
    runtime_metadata = runtime_metadata or {
        "phase_history": [],
        "phase_timings": {},
        "completed_phases": [],
        "failed_phase": None,
        "final_status": "completed" if overall_success else "failed",
        "last_completed_phase": None,
    }
    failed_operations = failed_operations or []

    return {
        "overall_success": overall_success,
        "results": [asdict(result) for result in results],
        "analysis_summary": _build_analysis_summary(results, governance_config, runtime_metadata, failed_operations),
        "failed_operations": _serialize_value(failed_operations),
        "metadata": _build_runtime_metadata(runtime_metadata),
        "report_metadata": _build_report_metadata(governance_config, runtime_metadata, failed_operations, results, report_path),
    }


def export_quality_gate_report(report: Dict[str, object], output_path: Path) -> Dict[str, object]:
    payload = json.loads(json.dumps(report, ensure_ascii=False))
    metadata = payload.setdefault("metadata", _build_runtime_metadata({}))
    failed_operations = payload.setdefault("failed_operations", [])
    report_metadata = payload.setdefault("report_metadata", {})
    governance_config = {
        "export_contract_version": report_metadata.get("contract_version", DEFAULT_GOVERNANCE_CONFIG["export_contract_version"]),
        "persist_failed_operations": True,
        "minimum_stable_success_rate": DEFAULT_GOVERNANCE_CONFIG["minimum_stable_success_rate"],
    }

    export_details = {"output_path": _normalize_reference_path(output_path)}
    export_started_at = _start_phase(metadata, "export_quality_gate_report", export_details)
    _complete_phase(
        metadata,
        "export_quality_gate_report",
        export_started_at,
        export_details,
        final_status=metadata.get("final_status", "completed"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload["metadata"] = _build_runtime_metadata(metadata)
    payload["analysis_summary"] = _build_analysis_summary(
        [GateResult(**item) for item in payload.get("results", [])],
        governance_config,
        metadata,
        failed_operations,
    )
    payload["report_metadata"] = _build_report_metadata(
        governance_config,
        metadata,
        failed_operations,
        payload.get("results", []),
        output_path,
    )
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified quality gate")
    parser.add_argument("--root", default=".", help="Project root path")
    parser.add_argument("--report", default="output/quality-gate.json", help="Report output path")
    parser.add_argument("--graph-output", default="docs/architecture", help="Dependency graph output directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report_path = (root / args.report).resolve()
    graph_output = (root / args.graph_output).resolve()
    config_path = root / "config.yml"
    governance_config = _load_governance_config(config_path)
    runtime_metadata: Dict[str, Any] = {
        "phase_history": [],
        "phase_timings": {},
        "completed_phases": [],
        "failed_phase": None,
        "final_status": "completed",
        "last_completed_phase": None,
    }
    failed_operations: List[Dict[str, Any]] = []

    core_results = [
        _run_gate_phase("run_logic_gate", root, runtime_metadata, failed_operations, governance_config, lambda: run_logic_gate(root)),
        _run_gate_phase(
            "run_dependency_graph_gate",
            root,
            runtime_metadata,
            failed_operations,
            governance_config,
            lambda: run_dependency_graph_gate(root, graph_output),
        ),
        _run_gate_phase("run_code_quality_gate", root, runtime_metadata, failed_operations, governance_config, lambda: run_code_quality_gate(root)),
        _run_gate_phase(
            "run_unit_test_gate",
            root,
            runtime_metadata,
            failed_operations,
            governance_config,
            lambda: run_unit_test_gate(root, DEFAULT_TEST_MODULES),
        ),
    ]
    assessment_result = _run_gate_phase(
        "run_quality_assessment_gate",
        root,
        runtime_metadata,
        failed_operations,
        governance_config,
        lambda: run_quality_assessment_gate(root, core_results),
    )
    improvement_result = _run_gate_phase(
        "run_continuous_improvement_gate",
        root,
        runtime_metadata,
        failed_operations,
        governance_config,
        lambda: run_continuous_improvement_gate(root),
    )
    inventory_result = _run_gate_phase(
        "run_quality_consumer_inventory_gate",
        root,
        runtime_metadata,
        failed_operations,
        governance_config,
        lambda: run_quality_consumer_inventory_gate(root),
    )
    pre_archive_results = [*core_results, assessment_result, improvement_result, inventory_result]
    pre_archive_report = build_report(pre_archive_results, governance_config, runtime_metadata, failed_operations)
    archive_result = _run_gate_phase(
        "run_quality_improvement_archive_gate",
        root,
        runtime_metadata,
        failed_operations,
        governance_config,
        lambda: run_quality_improvement_archive_gate(root, pre_archive_report),
    )
    feedback_result = _run_gate_phase(
        "run_quality_feedback_gate",
        root,
        runtime_metadata,
        failed_operations,
        governance_config,
        lambda: run_quality_feedback_gate(root),
    )
    results = [*pre_archive_results, archive_result, feedback_result]
    assemble_started_at = _start_phase(runtime_metadata, "assemble_quality_gate_report", {"gate_count": len(results)})
    runtime_metadata["final_status"] = "completed" if all(result.success for result in results) else "failed"
    _complete_phase(
        runtime_metadata,
        "assemble_quality_gate_report",
        assemble_started_at,
        {"gate_count": len(results), "overall_success": all(result.success for result in results)},
        final_status=runtime_metadata["final_status"],
    )
    report = build_report(results, governance_config, runtime_metadata, failed_operations, report_path)
    report = export_quality_gate_report(report, report_path)

    print("[quality-gate] overall_success={status}".format(status=report["overall_success"]))
    print("[quality-gate] report={path}".format(path=report_path.relative_to(root)))
    for result in results:
        print(
            "- {name}: success={success} metrics={metrics}".format(
                name=result.name,
                success=result.success,
                metrics=result.metrics,
            )
        )

    return 0 if report["overall_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())