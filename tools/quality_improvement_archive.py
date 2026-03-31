"""
Quality improvement archive.

This tool archives each quality cycle by combining:
1) quality gate report
2) quality assessment report
3) continuous improvement report

It writes:
- JSONL timeline for machine tracking
- Markdown dossier for human review
- latest JSON summary

Usage:
    python tools/quality_improvement_archive.py
    python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_LOADER_REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src" / "infrastructure" / "config_loader.py").exists()),
    None,
)
if _CONFIG_LOADER_REPO_ROOT is not None and str(_CONFIG_LOADER_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONFIG_LOADER_REPO_ROOT))

from src.infrastructure.config_loader import load_settings_section

DEFAULT_GOVERNANCE_CONFIG = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_quality_score": 85.0,
    "export_contract_version": "d65.v1",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_archive_section(config_path: Path | None) -> Dict[str, Any]:
    return load_settings_section(
        "governance.quality_improvement_archive",
        config_path=config_path,
        default={},
    )


def _load_governance_config(config_path: Path | None) -> Dict[str, Any]:
    section = _load_archive_section(config_path)
    return {
        "enable_phase_tracking": bool(section.get("enable_phase_tracking", DEFAULT_GOVERNANCE_CONFIG["enable_phase_tracking"])),
        "persist_failed_operations": bool(section.get("persist_failed_operations", DEFAULT_GOVERNANCE_CONFIG["persist_failed_operations"])),
        "minimum_stable_quality_score": float(section.get("minimum_stable_quality_score", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_quality_score"])),
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


def _looks_like_clinical_gap_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(key in value for key in ("clinical_question", "gaps", "priority_summary", "coverage_overview"))


def _extract_clinical_gap_json_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        clinical_gap = value.get("clinical_gap_analysis")
        if isinstance(clinical_gap, dict):
            json_payload = clinical_gap.get("json_payload")
            if _looks_like_clinical_gap_payload(json_payload):
                return _serialize_value(json_payload)
            if _looks_like_clinical_gap_payload(clinical_gap):
                return _serialize_value(clinical_gap)

        json_payload = value.get("json_payload")
        if _looks_like_clinical_gap_payload(json_payload):
            return _serialize_value(json_payload)

        for item in value.values():
            extracted = _extract_clinical_gap_json_payload(item)
            if extracted:
                return extracted

    if isinstance(value, list):
        for item in value:
            extracted = _extract_clinical_gap_json_payload(item)
            if extracted:
                return extracted

    return {}


def _resolve_clinical_gap_archive_payload(*reports: Any) -> Dict[str, Any]:
    for report in reports:
        extracted = _extract_clinical_gap_json_payload(report)
        if extracted:
            return extracted
    return {}


def _reference_list_entries(
    history_path: Path | None = None,
    latest_output: Path | None = None,
    dossier_path: Path | None = None,
) -> List[tuple[str, str]]:
    entries: List[tuple[str, str]] = []
    if history_path is not None:
        entries.append(("history", _normalize_reference_path(history_path)))
    if latest_output is not None:
        entries.append(("latest_output", _normalize_reference_path(latest_output)))
    if dossier_path is not None:
        entries.append(("dossier", _normalize_reference_path(dossier_path)))
    return entries


def _start_phase(runtime_metadata: Dict[str, Any], phase_name: str, details: Dict[str, Any] | None = None) -> float:
    started_at = time.time()
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
            "timestamp": _utc_now_iso(),
            "duration_seconds": round(duration_seconds or 0.0, 6),
        }
    )


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
    entry: Dict[str, Any],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    quality_score = float(entry.get("quality_score", 0.0) or 0.0)
    overall_success = bool(entry.get("overall_success", False))
    trend_status = str(entry.get("trend_status", "unknown"))
    status = "idle"
    if runtime_metadata.get("completed_phases") or failed_operations:
        status = (
            "stable"
            if overall_success and trend_status != "regressing" and quality_score >= float(governance_config.get("minimum_stable_quality_score", 85.0))
            else "needs_followup"
        )

    return {
        "status": status,
        "quality_score": quality_score,
        "overall_success": overall_success,
        "trend_status": trend_status,
        "failed_gate_count": len(entry.get("failed_gates", [])),
        "failed_dimension_count": len(entry.get("failed_dimensions", [])),
        "action_backlog_count": int(entry.get("action_backlog_count", 0) or 0),
        "inventory_missing_contract_count": int(((entry.get("inventory_summary") or {}).get("missing_contract_count", 0)) or 0),
        "inventory_uncategorized_root_script_count": int((((entry.get("inventory_summary") or {}).get("root_script_observation_category_counts") or {}).get("uncategorized_root_script", 0)) or 0),
        "inventory_trend_status": str((entry.get("inventory_trend") or {}).get("status", "stable")),
        "inventory_history_points": int((entry.get("inventory_trend") or {}).get("history_points", 1) or 1),
        "failed_operation_count": len(failed_operations),
        "failed_phase": runtime_metadata.get("failed_phase"),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }


def _build_inventory_summary(inventory_report: Dict[str, object] | None) -> Dict[str, object]:
    report = inventory_report or {}
    analysis_summary = report.get("analysis_summary") or {}
    recommendation = report.get("recommendation") or {}
    category_counts = analysis_summary.get("root_script_observation_category_counts") or {}
    return {
        "status": "healthy"
        if int(analysis_summary.get("missing_contract_count", 0) or 0) == 0
        and int(category_counts.get("uncategorized_root_script", 0) or 0) == 0
        else "needs_followup",
        "scanned_consumer_count": int(analysis_summary.get("scanned_consumer_count", 0) or 0),
        "missing_contract_count": int(analysis_summary.get("missing_contract_count", 0) or 0),
        "eligible_missing_contract_count": int(analysis_summary.get("eligible_missing_contract_count", 0) or 0),
        "root_script_observation_count": int(analysis_summary.get("root_script_observation_count", 0) or 0),
        "root_script_observation_category_counts": _serialize_value(category_counts),
        "recommended_next_target": recommendation.get("recommended_path") or analysis_summary.get("recommended_next_target"),
    }


def _load_archive_history(history_path: Path) -> List[Dict[str, object]]:
    if not history_path.exists():
        return []
    rows: List[Dict[str, object]] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _select_previous_inventory_summary(history_rows: List[Dict[str, object]]) -> Dict[str, object] | None:
    for row in reversed(history_rows):
        summary = row.get("inventory_summary")
        if isinstance(summary, dict):
            return summary
    return None


def _count_inventory_history_points(history_rows: List[Dict[str, object]]) -> int:
    return sum(1 for row in history_rows if isinstance(row.get("inventory_summary"), dict))


def _inventory_trend_status(
    current_missing_contract_count: int,
    previous_missing_contract_count: int | None,
    current_uncategorized_count: int,
    previous_uncategorized_count: int | None,
) -> str:
    if previous_missing_contract_count is None or previous_uncategorized_count is None:
        return "baseline"
    current_tuple = (current_missing_contract_count, current_uncategorized_count)
    previous_tuple = (previous_missing_contract_count, previous_uncategorized_count)
    if current_tuple < previous_tuple:
        return "improving"
    if current_tuple > previous_tuple:
        return "regressing"
    return "stable"


def _build_inventory_trend(history_rows: List[Dict[str, object]], inventory_summary: Dict[str, object]) -> Dict[str, object]:
    previous_summary = _select_previous_inventory_summary(history_rows)
    previous_missing_contract_count = None
    previous_uncategorized_count = None
    previous_scanned_consumer_count = None
    previous_recommended_next_target = None
    if previous_summary is not None:
        previous_missing_contract_count = int(previous_summary.get("missing_contract_count", 0) or 0)
        previous_uncategorized_count = int(((previous_summary.get("root_script_observation_category_counts") or {}).get("uncategorized_root_script", 0)) or 0)
        previous_scanned_consumer_count = int(previous_summary.get("scanned_consumer_count", 0) or 0)
        previous_recommended_next_target = previous_summary.get("recommended_next_target")
    current_missing_contract_count = int(inventory_summary.get("missing_contract_count", 0) or 0)
    current_uncategorized_count = int(((inventory_summary.get("root_script_observation_category_counts") or {}).get("uncategorized_root_script", 0)) or 0)
    current_scanned_consumer_count = int(inventory_summary.get("scanned_consumer_count", 0) or 0)
    current_recommended_next_target = inventory_summary.get("recommended_next_target")
    return {
        "status": _inventory_trend_status(
            current_missing_contract_count,
            previous_missing_contract_count,
            current_uncategorized_count,
            previous_uncategorized_count,
        ),
        "history_points": _count_inventory_history_points(history_rows) + 1,
        "previous_missing_contract_count": previous_missing_contract_count,
        "current_missing_contract_count": current_missing_contract_count,
        "missing_contract_delta": (
            current_missing_contract_count - previous_missing_contract_count
            if previous_missing_contract_count is not None
            else 0
        ),
        "previous_uncategorized_root_script_count": previous_uncategorized_count,
        "current_uncategorized_root_script_count": current_uncategorized_count,
        "uncategorized_root_script_delta": (
            current_uncategorized_count - previous_uncategorized_count
            if previous_uncategorized_count is not None
            else 0
        ),
        "previous_scanned_consumer_count": previous_scanned_consumer_count,
        "current_scanned_consumer_count": current_scanned_consumer_count,
        "scanned_consumer_delta": (
            current_scanned_consumer_count - previous_scanned_consumer_count
            if previous_scanned_consumer_count is not None
            else 0
        ),
        "previous_recommended_next_target": previous_recommended_next_target,
        "current_recommended_next_target": current_recommended_next_target,
        "recommended_next_target_changed": previous_recommended_next_target != current_recommended_next_target,
    }


def _build_report_metadata(
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    history_path: Path | None = None,
    latest_output: Path | None = None,
    dossier_path: Path | None = None,
) -> Dict[str, Any]:
    artifact_entries = _reference_list_entries(history_path, latest_output, dossier_path)
    report_metadata = {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": _utc_now_iso(),
        "result_schema": "quality_improvement_archive_entry",
        "failed_operation_count": len(failed_operations),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        "artifact_reference_labels": [label for label, _ in artifact_entries],
        "artifact_reference_paths": [path for _, path in artifact_entries],
    }
    if history_path is not None:
        report_metadata["history_path"] = _normalize_reference_path(history_path)
    if latest_output is not None:
        report_metadata["latest_output_path"] = _normalize_reference_path(latest_output)
    if dossier_path is not None:
        report_metadata["dossier_path"] = _normalize_reference_path(dossier_path)
    return report_metadata


def _assemble_archive_entry(
    entry: Dict[str, Any],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    history_path: Path | None = None,
    latest_output: Path | None = None,
    dossier_path: Path | None = None,
) -> Dict[str, Any]:
    payload = dict(entry)
    payload["analysis_summary"] = _build_analysis_summary(payload, governance_config, runtime_metadata, failed_operations)
    payload["failed_operations"] = _serialize_value(failed_operations)
    payload["metadata"] = _build_runtime_metadata(runtime_metadata)
    payload["report_metadata"] = _build_report_metadata(
        governance_config,
        runtime_metadata,
        failed_operations,
        history_path,
        latest_output,
        dossier_path,
    )
    return payload


def _safe_load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def build_archive_entry(
    gate_report: Dict[str, object],
    assessment_report: Dict[str, object],
    improvement_report: Dict[str, object],
    config_path: Path | None = None,
    inventory_report: Dict[str, object] | None = None,
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

    config_phase_started_at = _start_phase(
        runtime_metadata,
        "load_quality_archive_config",
        {"config_path": str(config_path) if config_path is not None else "<defaults>"},
    )
    _complete_phase(
        runtime_metadata,
        "load_quality_archive_config",
        config_phase_started_at,
        {"config_path": str(config_path) if config_path is not None else "<defaults>"},
    )

    build_phase_started_at = _start_phase(
        runtime_metadata,
        "build_archive_entry",
        {"gate_result_count": len(gate_report.get("results", [])) if isinstance(gate_report.get("results", []), list) else 0},
    )
    gate_results = gate_report.get("results", [])
    failed_gates = []
    if isinstance(gate_results, list):
        failed_gates = [
            str(item.get("name"))
            for item in gate_results
            if isinstance(item, dict) and not bool(item.get("success"))
        ]

    action_backlog = improvement_report.get("action_backlog", [])
    inventory_summary = _build_inventory_summary(inventory_report)
    clinical_gap_analysis = _resolve_clinical_gap_archive_payload(
        gate_report,
        assessment_report,
        improvement_report,
        inventory_report,
    )
    entry = {
        "timestamp": _utc_now_iso(),
        "overall_success": bool(gate_report.get("overall_success", False)),
        "quality_score": float(assessment_report.get("overall_score", 0.0) or 0.0),
        "quality_grade": str(assessment_report.get("grade", "D")),
        "trend_status": str((improvement_report.get("trend") or {}).get("status", "unknown")),
        "trend_delta": float((improvement_report.get("trend") or {}).get("score_delta", 0.0) or 0.0),
        "failed_gates": failed_gates,
        "failed_dimensions": assessment_report.get("failed_dimensions", []),
        "action_backlog_count": len(action_backlog) if isinstance(action_backlog, list) else 0,
        "next_cycle_targets": improvement_report.get("next_cycle_targets", {}),
        "inventory_summary": inventory_summary,
    }
    if clinical_gap_analysis:
        entry["clinical_gap_analysis"] = clinical_gap_analysis
    runtime_metadata["final_status"] = "completed"
    _complete_phase(
        runtime_metadata,
        "build_archive_entry",
        build_phase_started_at,
        {
            "failed_gate_count": len(failed_gates),
            "failed_dimension_count": len(entry.get("failed_dimensions", [])),
            "action_backlog_count": entry.get("action_backlog_count", 0),
            "inventory_missing_contract_count": inventory_summary.get("missing_contract_count", 0),
        },
        final_status="completed",
    )
    return _assemble_archive_entry(entry, governance_config, runtime_metadata, failed_operations)


def _to_md_lines(entry: Dict[str, object]) -> List[str]:
    inventory_summary = entry.get("inventory_summary") or {}
    inventory_trend = entry.get("inventory_trend") or {}
    clinical_gap_analysis = entry.get("clinical_gap_analysis") or {}
    report_metadata = entry.get("report_metadata") or {}
    lines = [
        "# Quality Improvement Archive Entry",
        "",
        "## Snapshot",
        "",
        "- Timestamp: {0}".format(entry.get("timestamp", "")),
        "- Overall Success: {0}".format(entry.get("overall_success", False)),
        "- Quality Score: {0}".format(entry.get("quality_score", 0.0)),
        "- Quality Grade: {0}".format(entry.get("quality_grade", "D")),
        "- Trend Status: {0}".format(entry.get("trend_status", "unknown")),
        "- Trend Delta: {0}".format(entry.get("trend_delta", 0.0)),
        "",
        "## Risks",
        "",
        "- Failed Gates: {0}".format(", ".join(entry.get("failed_gates", [])) or "None"),
        "- Failed Dimensions: {0}".format(", ".join(entry.get("failed_dimensions", [])) or "None"),
        "",
        "## Improvement Backlog",
        "",
        "- Backlog Count: {0}".format(entry.get("action_backlog_count", 0)),
        "- Next Cycle Targets: {0}".format(json.dumps(entry.get("next_cycle_targets", {}), ensure_ascii=False)),
        "",
        "## Inventory Governance",
        "",
        "- Status: {0}".format(inventory_summary.get("status", "unknown")),
        "- Scanned Consumers: {0}".format(inventory_summary.get("scanned_consumer_count", 0)),
        "- Missing Contracts: {0}".format(inventory_summary.get("missing_contract_count", 0)),
        "- Root Script Observations: {0}".format(inventory_summary.get("root_script_observation_count", 0)),
        "- Recommended Next Target: {0}".format(inventory_summary.get("recommended_next_target") or "none"),
        "- Root Script Observation Categories: {0}".format(json.dumps(inventory_summary.get("root_script_observation_category_counts", {}), ensure_ascii=False)),
        "",
        "## Inventory Trend",
        "",
        "- Trend Status: {0}".format(inventory_trend.get("status", "stable")),
        "- History Points: {0}".format(inventory_trend.get("history_points", 1)),
        "- Missing Contract Delta: {0}".format(inventory_trend.get("missing_contract_delta", 0)),
        "- Uncategorized Root Script Delta: {0}".format(inventory_trend.get("uncategorized_root_script_delta", 0)),
        "- Recommended Next Target Changed: {0}".format(inventory_trend.get("recommended_next_target_changed", False)),
        "",
    ]

    if clinical_gap_analysis:
        priority_summary = clinical_gap_analysis.get("priority_summary") or {}
        lines.extend(
            [
                "## Clinical Gap Analysis",
                "",
                "- Clinical Question: {0}".format(clinical_gap_analysis.get("clinical_question", "")),
                "- Highest Priority: {0}".format(priority_summary.get("highest_priority", "低")),
                "- Total Gaps: {0}".format(priority_summary.get("total_gaps", len(clinical_gap_analysis.get("gaps", [])))),
                "",
                "```json",
                json.dumps(clinical_gap_analysis, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )

    lines.extend(
        [
        "## Artifact References",
        "",
        "- History Path: {0}".format(report_metadata.get("history_path", "")),
        "- Latest Output Path: {0}".format(report_metadata.get("latest_output_path", "")),
        "- Dossier Path: {0}".format(report_metadata.get("dossier_path", "")),
        "",
        ]
    )
    return lines


def write_archive(
    entry: Dict[str, object],
    history_path: Path,
    dossier_dir: Path,
    latest_output: Path,
) -> Dict[str, Path]:
    payload = json.loads(json.dumps(entry, ensure_ascii=False))
    metadata = payload.setdefault("metadata", _build_runtime_metadata({}))
    failed_operations = payload.setdefault("failed_operations", [])
    report_metadata = payload.setdefault("report_metadata", {})
    history_rows = _load_archive_history(history_path)
    payload["inventory_trend"] = _build_inventory_trend(history_rows, payload.get("inventory_summary") or {})
    governance_config = {
        "export_contract_version": report_metadata.get("contract_version", DEFAULT_GOVERNANCE_CONFIG["export_contract_version"]),
        "persist_failed_operations": True,
        "minimum_stable_quality_score": payload.get("quality_score", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_quality_score"]),
    }

    history_path.parent.mkdir(parents=True, exist_ok=True)
    dossier_dir.mkdir(parents=True, exist_ok=True)
    latest_output.parent.mkdir(parents=True, exist_ok=True)

    export_phase_started_at = _start_phase(
        metadata,
        "export_quality_improvement_archive",
        {
            "history_path": _normalize_reference_path(history_path),
            "latest_output": _normalize_reference_path(latest_output),
            "dossier_dir": _normalize_reference_path(dossier_dir),
        },
    )

    ts = str(payload.get("timestamp", "")).replace(":", "-")
    safe_ts = ts.replace("+00-00", "Z").replace(" ", "_")
    md_path = dossier_dir / "quality-improvement-{0}.md".format(safe_ts)
    _complete_phase(
        metadata,
        "export_quality_improvement_archive",
        export_phase_started_at,
        {
            "history_path": _normalize_reference_path(history_path),
            "latest_output": _normalize_reference_path(latest_output),
            "dossier_path": _normalize_reference_path(md_path),
        },
        final_status="completed" if metadata.get("final_status") != "cleaned" else metadata.get("final_status"),
    )

    payload["metadata"] = _build_runtime_metadata(metadata)
    payload["analysis_summary"] = _build_analysis_summary(payload, governance_config, metadata, failed_operations)
    payload["report_metadata"] = _build_report_metadata(
        governance_config,
        metadata,
        failed_operations,
        history_path,
        latest_output,
        md_path,
    )

    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    md_path.write_text("\n".join(_to_md_lines(payload)), encoding="utf-8")

    latest_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "history": history_path,
        "dossier": md_path,
        "latest": latest_output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive quality improvement outputs")
    parser.add_argument("--config", default="config.yml", help="Path to config YAML")
    parser.add_argument("--gate-report", default="output/quality-gate.json", help="Path to quality gate report")
    parser.add_argument("--assessment-report", default="output/quality-assessment.json", help="Path to quality assessment report")
    parser.add_argument("--improvement-report", default="output/continuous-improvement.json", help="Path to continuous improvement report")
    parser.add_argument("--inventory-report", default="output/quality-consumer-inventory.json", help="Path to quality consumer inventory report")
    parser.add_argument("--history", default="output/quality-improvement-archive.jsonl", help="Path to archive JSONL")
    parser.add_argument("--dossier-dir", default="docs/quality-archive", help="Directory for markdown dossiers")
    parser.add_argument("--output", default="output/quality-improvement-archive-latest.json", help="Path to latest archive summary")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    gate_report = _safe_load_json(Path(args.gate_report).resolve())
    assessment_report = _safe_load_json(Path(args.assessment_report).resolve())
    improvement_report = _safe_load_json(Path(args.improvement_report).resolve())
    inventory_report = _safe_load_json(Path(args.inventory_report).resolve())

    entry = build_archive_entry(gate_report, assessment_report, improvement_report, config_path, inventory_report)
    outputs = write_archive(
        entry,
        Path(args.history).resolve(),
        Path(args.dossier_dir).resolve(),
        Path(args.output).resolve(),
    )

    print("[quality-archive] score={score} grade={grade}".format(
        score=entry.get("quality_score", 0.0),
        grade=entry.get("quality_grade", "D"),
    ))
    print("[quality-archive] history={path}".format(path=outputs["history"]))
    print("[quality-archive] dossier={path}".format(path=outputs["dossier"]))
    print("[quality-archive] latest={path}".format(path=outputs["latest"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
