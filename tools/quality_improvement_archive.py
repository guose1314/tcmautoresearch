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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


DEFAULT_GOVERNANCE_CONFIG = {
    "enable_phase_tracking": True,
    "persist_failed_operations": True,
    "minimum_stable_quality_score": 85.0,
    "export_contract_version": "d51.v1",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_archive_section(config_path: Path | None) -> Dict[str, Any]:
    if config_path is None or not config_path.exists():
        return {}

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    governance = data.get("governance") or {}
    section = governance.get("quality_improvement_archive") or {}
    return section if isinstance(section, dict) else {}


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
        "failed_operation_count": len(failed_operations),
        "failed_phase": runtime_metadata.get("failed_phase"),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }


def _build_report_metadata(
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    history_path: Path | None = None,
    latest_output: Path | None = None,
    dossier_path: Path | None = None,
) -> Dict[str, Any]:
    report_metadata = {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": _utc_now_iso(),
        "result_schema": "quality_improvement_archive_entry",
        "failed_operation_count": len(failed_operations),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
    }
    if history_path is not None:
        report_metadata["history_path"] = str(history_path)
    if latest_output is not None:
        report_metadata["latest_output_path"] = str(latest_output)
    if dossier_path is not None:
        report_metadata["dossier_path"] = str(dossier_path)
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
    }
    runtime_metadata["final_status"] = "completed"
    _complete_phase(
        runtime_metadata,
        "build_archive_entry",
        build_phase_started_at,
        {
            "failed_gate_count": len(failed_gates),
            "failed_dimension_count": len(entry.get("failed_dimensions", [])),
            "action_backlog_count": entry.get("action_backlog_count", 0),
        },
        final_status="completed",
    )
    return _assemble_archive_entry(entry, governance_config, runtime_metadata, failed_operations)


def _to_md_lines(entry: Dict[str, object]) -> List[str]:
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
    ]
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
            "history_path": str(history_path),
            "latest_output": str(latest_output),
            "dossier_dir": str(dossier_dir),
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
            "history_path": str(history_path),
            "latest_output": str(latest_output),
            "dossier_path": str(md_path),
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
    parser.add_argument("--history", default="output/quality-improvement-archive.jsonl", help="Path to archive JSONL")
    parser.add_argument("--dossier-dir", default="docs/quality-archive", help="Directory for markdown dossiers")
    parser.add_argument("--output", default="output/quality-improvement-archive-latest.json", help="Path to latest archive summary")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    gate_report = _safe_load_json(Path(args.gate_report).resolve())
    assessment_report = _safe_load_json(Path(args.assessment_report).resolve())
    improvement_report = _safe_load_json(Path(args.improvement_report).resolve())

    entry = build_archive_entry(gate_report, assessment_report, improvement_report, config_path)
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
