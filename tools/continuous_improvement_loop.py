"""
Continuous improvement loop.

This tool turns quality assessment outputs into an iterative improvement cycle:
1) Persist history snapshots
2) Compute trend status
3) Generate prioritized action backlog
4) Propose next-cycle targets

Usage:
    python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json
    python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --output output/continuous-improvement.json
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
    "minimum_stable_overall_score": 85.0,
    "export_contract_version": "d66.v1",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_continuous_improvement_section(config_path: Path | None) -> Dict[str, Any]:
    return load_settings_section(
        "governance.continuous_improvement",
        config_path=config_path,
        default={},
    )


def _load_governance_config(config_path: Path | None) -> Dict[str, Any]:
    section = _load_continuous_improvement_section(config_path)
    return {
        "enable_phase_tracking": bool(section.get("enable_phase_tracking", DEFAULT_GOVERNANCE_CONFIG["enable_phase_tracking"])),
        "persist_failed_operations": bool(section.get("persist_failed_operations", DEFAULT_GOVERNANCE_CONFIG["persist_failed_operations"])),
        "minimum_stable_overall_score": float(
            section.get("minimum_stable_overall_score", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_overall_score"])
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


def _reference_list_entries(
    history_path: Path | None = None,
    output_path: Path | None = None,
) -> List[tuple[str, str]]:
    entries: List[tuple[str, str]] = []
    if history_path is not None:
        entries.append(("history", _normalize_reference_path(history_path)))
    if output_path is not None:
        entries.append(("output", _normalize_reference_path(output_path)))
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
    report: Dict[str, Any],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    current_snapshot = report.get("current_snapshot", {})
    trend = report.get("trend", {})
    current_score = float(current_snapshot.get("overall_score", 0.0) or 0.0)
    passed = bool(current_snapshot.get("passed", False))
    trend_status = str(trend.get("status", "stable"))

    status = "idle"
    if runtime_metadata.get("completed_phases") or failed_operations:
        status = (
            "stable"
            if passed and trend_status != "regressing" and current_score >= float(governance_config.get("minimum_stable_overall_score", 85.0))
            else "needs_followup"
        )

    return {
        "status": status,
        "current_score": current_score,
        "trend_status": trend_status,
        "history_points": int(trend.get("history_points", 0) or 0),
        "backlog_count": len(report.get("action_backlog", [])),
        "inventory_trend_status": str((report.get("inventory_focus") or {}).get("trend_status", "none")),
        "inventory_backlog_count": len((report.get("inventory_focus") or {}).get("actions", [])),
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
    output_path: Path | None = None,
) -> Dict[str, Any]:
    artifact_entries = _reference_list_entries(history_path, output_path)
    report_metadata = {
        "contract_version": governance_config["export_contract_version"],
        "generated_at": _utc_now_iso(),
        "result_schema": "continuous_improvement_report",
        "failed_operation_count": len(failed_operations),
        "final_status": runtime_metadata.get("final_status", "initialized"),
        "last_completed_phase": runtime_metadata.get("last_completed_phase"),
        "artifact_reference_labels": [label for label, _ in artifact_entries],
        "artifact_reference_paths": [path for _, path in artifact_entries],
    }
    if history_path is not None:
        report_metadata["history_path"] = _normalize_reference_path(history_path)
    if output_path is not None:
        report_metadata["output_path"] = _normalize_reference_path(output_path)
    return report_metadata


def _assemble_cycle_report(
    report: Dict[str, Any],
    governance_config: Dict[str, Any],
    runtime_metadata: Dict[str, Any],
    failed_operations: List[Dict[str, Any]],
    history_path: Path | None = None,
    output_path: Path | None = None,
) -> Dict[str, Any]:
    payload = dict(report)
    payload["analysis_summary"] = _build_analysis_summary(payload, governance_config, runtime_metadata, failed_operations)
    payload["failed_operations"] = _serialize_value(failed_operations)
    payload["metadata"] = _build_runtime_metadata(runtime_metadata)
    payload["report_metadata"] = _build_report_metadata(governance_config, runtime_metadata, failed_operations, history_path, output_path)
    return payload


def load_assessment(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_history(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    rows: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


def append_history(path: Path, snapshot: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def _trend_status(delta: float) -> str:
    if delta > 0.5:
        return "improving"
    if delta < -0.5:
        return "regressing"
    return "stable"


def load_archive_history(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    rows: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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


def _latest_inventory_focus(archive_history: List[Dict[str, object]]) -> Dict[str, object]:
    for row in reversed(archive_history):
        inventory_trend = row.get("inventory_trend")
        inventory_summary = row.get("inventory_summary")
        if isinstance(inventory_trend, dict) or isinstance(inventory_summary, dict):
            return {
                "inventory_trend": inventory_trend if isinstance(inventory_trend, dict) else {},
                "inventory_summary": inventory_summary if isinstance(inventory_summary, dict) else {},
            }
    return {"inventory_trend": {}, "inventory_summary": {}}


def _inventory_actions(inventory_focus: Dict[str, object]) -> List[Dict[str, object]]:
    trend = inventory_focus.get("inventory_trend") or {}
    summary = inventory_focus.get("inventory_summary") or {}
    actions: List[Dict[str, object]] = []
    missing_contract_count = int(summary.get("missing_contract_count", 0) or 0)
    uncategorized_count = int(((summary.get("root_script_observation_category_counts") or {}).get("uncategorized_root_script", 0)) or 0)
    trend_status = str(trend.get("status", "stable"))
    recommended = summary.get("recommended_next_target")

    if missing_contract_count > 0:
        actions.append(
            {
                "priority": "P0",
                "dimension": "quality_consumer_inventory",
                "action": "补齐 inventory 缺失合同消费者，并优先处理 {0}。".format(recommended or "recommended_next_target=none"),
            }
        )
    if uncategorized_count > 0:
        actions.append(
            {
                "priority": "P1",
                "dimension": "quality_consumer_inventory",
                "action": "清理未归类根目录脚本，避免 inventory 观测区退化。",
            }
        )
    if trend_status == "regressing" and missing_contract_count == 0 and uncategorized_count == 0:
        actions.append(
            {
                "priority": "P1",
                "dimension": "quality_consumer_inventory",
                "action": "排查 inventory 趋势回退来源，确认扫描范围、推荐目标与历史基线是否发生异常漂移。",
            }
        )
    if bool(trend.get("recommended_next_target_changed", False)) and recommended:
        actions.append(
            {
                "priority": "P1",
                "dimension": "quality_consumer_inventory",
                "action": "评估推荐下一跳已切换到 {0} 是否意味着新的治理缺口进入主视野。".format(recommended),
            }
        )
    return actions


def _build_inventory_targets(inventory_focus: Dict[str, object]) -> Dict[str, object]:
    trend = inventory_focus.get("inventory_trend") or {}
    summary = inventory_focus.get("inventory_summary") or {}
    return {
        "target_inventory_missing_contract_count": 0,
        "target_inventory_uncategorized_root_script_count": 0,
        "inventory_trend_status": str(trend.get("status", "stable")),
        "inventory_recommended_next_target": summary.get("recommended_next_target"),
        "inventory_history_points": int(trend.get("history_points", 0) or 0),
    }


def _build_snapshot(assessment: Dict[str, object]) -> Dict[str, object]:
    return {
        "timestamp": _utc_now_iso(),
        "overall_score": float(assessment.get("overall_score", 0.0) or 0.0),
        "grade": str(assessment.get("grade", "D")),
        "passed": bool(assessment.get("passed", False)),
        "dimension_scores": assessment.get("dimension_scores", {}),
        "failed_dimensions": assessment.get("failed_dimensions", []),
    }


def _action_for_dimension(name: str) -> Dict[str, object]:
    mapping = {
        "gate_stability": ("P0", "修复阻断项并恢复所有 gate 的稳定通过率。"),
        "test_reliability": ("P0", "补充失败场景回归测试并提升测试稳定性。"),
        "logic_health": ("P1", "清理逻辑检查告警，优先处理结构性风险。"),
        "code_health": ("P1", "继续拆解高复杂函数并降低告警密度。"),
        "architecture_health": ("P1", "保障依赖关系图和架构约束持续更新。"),
    }
    priority, action = mapping.get(name, ("P2", "补充质量证据并跟踪下一轮结果。"))
    return {
        "priority": priority,
        "dimension": name,
        "action": action,
    }


def _select_lowest_dimensions(dimension_scores: Dict[str, object], count: int = 2) -> List[str]:
    pairs = []
    for name, score in dimension_scores.items():
        try:
            pairs.append((name, float(score)))
        except Exception:
            continue
    pairs.sort(key=lambda item: item[1])
    return [name for name, _ in pairs[:count]]


def build_cycle_report(
    assessment: Dict[str, object],
    history: List[Dict[str, object]],
    config_path: Path | None = None,
    archive_history: List[Dict[str, object]] | None = None,
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
        "load_continuous_improvement_config",
        {"config_path": str(config_path) if config_path is not None else "<defaults>"},
    )
    _complete_phase(
        runtime_metadata,
        "load_continuous_improvement_config",
        config_phase_started_at,
        {"config_path": str(config_path) if config_path is not None else "<defaults>"},
    )

    build_phase_started_at = _start_phase(runtime_metadata, "build_cycle_report", {"history_length": len(history)})
    snapshot = _build_snapshot(assessment)
    inventory_focus = _latest_inventory_focus(archive_history or [])

    previous_score = None
    if history:
        previous_score = float(history[-1].get("overall_score", 0.0) or 0.0)

    current_score = float(snapshot.get("overall_score", 0.0) or 0.0)
    score_delta = round(current_score - (previous_score if previous_score is not None else current_score), 2)
    status = _trend_status(score_delta)

    failed_dimensions = list(snapshot.get("failed_dimensions", []))
    dimension_scores = snapshot.get("dimension_scores", {})

    focus_dimensions = failed_dimensions or _select_lowest_dimensions(dimension_scores, count=2)
    actions = [_action_for_dimension(name) for name in focus_dimensions]
    inventory_actions = _inventory_actions(inventory_focus)
    actions.extend(inventory_actions)

    target_score = min(100.0, round(current_score + 2.0, 2))
    next_cycle_targets = {
        "target_overall_score": target_score,
        "focus_dimensions": focus_dimensions,
        "max_new_warnings": 0,
    }
    next_cycle_targets.update(_build_inventory_targets(inventory_focus))

    report = {
        "cycle_timestamp": snapshot["timestamp"],
        "current_snapshot": snapshot,
        "trend": {
            "status": status,
            "score_delta": score_delta,
            "previous_score": previous_score,
            "current_score": current_score,
            "history_points": len(history) + 1,
        },
        "action_backlog": actions,
        "inventory_focus": {
            "trend_status": str((inventory_focus.get("inventory_trend") or {}).get("status", "none")),
            "summary": inventory_focus.get("inventory_summary") or {},
            "trend": inventory_focus.get("inventory_trend") or {},
            "actions": inventory_actions,
        },
        "next_cycle_targets": next_cycle_targets,
    }
    runtime_metadata["final_status"] = "completed"
    _complete_phase(
        runtime_metadata,
        "build_cycle_report",
        build_phase_started_at,
        {
            "history_length": len(history),
            "trend_status": status,
            "backlog_count": len(actions),
        },
        final_status="completed",
    )
    return _assemble_cycle_report(report, governance_config, runtime_metadata, failed_operations)


def export_cycle_report(report: Dict[str, object], history_path: Path, output_path: Path) -> Dict[str, object]:
    payload = json.loads(json.dumps(report, ensure_ascii=False))
    metadata = payload.setdefault("metadata", _build_runtime_metadata({}))
    failed_operations = payload.setdefault("failed_operations", [])
    report_metadata = payload.setdefault("report_metadata", {})
    governance_config = {
        "export_contract_version": report_metadata.get("contract_version", DEFAULT_GOVERNANCE_CONFIG["export_contract_version"]),
        "persist_failed_operations": True,
        "minimum_stable_overall_score": payload.get("current_snapshot", {}).get("overall_score", DEFAULT_GOVERNANCE_CONFIG["minimum_stable_overall_score"]),
    }

    export_details = {
        "history_path": _normalize_reference_path(history_path),
        "output_path": _normalize_reference_path(output_path),
    }
    export_phase_started_at = _start_phase(
        metadata,
        "export_continuous_improvement_report",
        export_details,
    )
    _complete_phase(
        metadata,
        "export_continuous_improvement_report",
        export_phase_started_at,
        export_details,
        final_status="completed" if metadata.get("final_status") != "cleaned" else metadata.get("final_status"),
    )

    payload["metadata"] = _build_runtime_metadata(metadata)
    payload["analysis_summary"] = _build_analysis_summary(payload, governance_config, metadata, failed_operations)
    payload["report_metadata"] = _build_report_metadata(governance_config, metadata, failed_operations, history_path, output_path)

    append_history(history_path, payload["current_snapshot"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run continuous improvement loop")
    parser.add_argument(
        "--assessment-report",
        default="output/quality-assessment.json",
        help="Path to quality assessment report",
    )
    parser.add_argument(
        "--config",
        default="config.yml",
        help="Path to config YAML",
    )
    parser.add_argument(
        "--history",
        default="output/quality-history.jsonl",
        help="Path to historical snapshots (JSON Lines)",
    )
    parser.add_argument(
        "--archive-history",
        default="output/quality-improvement-archive.jsonl",
        help="Path to archive history used for inventory trend follow-up",
    )
    parser.add_argument(
        "--output",
        default="output/continuous-improvement.json",
        help="Path to continuous improvement report",
    )
    args = parser.parse_args()

    assessment_path = Path(args.assessment_report).resolve()
    config_path = Path(args.config).resolve()
    history_path = Path(args.history).resolve()
    archive_history_path = Path(args.archive_history).resolve()
    output_path = Path(args.output).resolve()

    assessment = load_assessment(assessment_path)
    history = load_history(history_path)
    archive_history = load_archive_history(archive_history_path)
    report = build_cycle_report(assessment, history, config_path, archive_history)
    report = export_cycle_report(report, history_path, output_path)

    print("[continuous-improvement] trend={status} delta={delta}".format(
        status=report["trend"]["status"],
        delta=report["trend"]["score_delta"],
    ))
    print("[continuous-improvement] report={path}".format(path=output_path))
    print("[continuous-improvement] history={path}".format(path=history_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())