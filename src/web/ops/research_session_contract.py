"""Shared Web-facing research session contract helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from src.research.observe_philology import resolve_observe_philology_assets
from src.research.phase_result import get_phase_value

PHASE_ORDER = (
    "observe",
    "hypothesis",
    "experiment",
    "experiment_execution",
    "analyze",
    "publish",
    "reflect",
)


def phase_index(phase_name: str) -> int:
    normalized = str(phase_name or "").strip().lower()
    if normalized not in PHASE_ORDER:
        raise ValueError(f"未知研究阶段: {phase_name}")
    return PHASE_ORDER.index(normalized)


def resolve_phase_result(execution: Any) -> Dict[str, Any]:
    if not isinstance(execution, dict):
        return {}
    result = execution.get("result")
    if isinstance(result, dict):
        return result
    return execution


def resolve_phase_status(execution: Any) -> str:
    if not isinstance(execution, dict):
        return "pending"
    result = resolve_phase_result(execution)
    raw_status = str(
        execution.get("status")
        or (result.get("status") if isinstance(result, dict) else "")
        or "completed"
    ).strip().lower() or "completed"
    if isinstance(result, dict) and result.get("error"):
        return "failed"
    if raw_status == "skipped":
        return "skipped"
    if raw_status in {"failed", "blocked", "pending", "running"}:
        return "failed"
    return "completed"


def normalize_phase_executions(executions: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(executions, dict):
        return deepcopy(executions)

    normalized: Dict[str, Dict[str, Any]] = {}
    if not isinstance(executions, list):
        return normalized

    for item in executions:
        if not isinstance(item, dict):
            continue
        phase_name = str(item.get("phase") or "").strip().lower()
        if not phase_name:
            continue
        normalized[phase_name] = {
            "phase": phase_name,
            "status": item.get("status"),
            "started_at": item.get("started_at"),
            "completed_at": item.get("completed_at"),
            "duration": item.get("duration"),
            "context": deepcopy(item.get("input") or {}),
            "result": deepcopy(item.get("output") or {}),
        }
    return normalized


def extract_completed_phases(phase_executions: Dict[str, Dict[str, Any]]) -> list[str]:
    return [
        phase_name
        for phase_name in PHASE_ORDER
        if phase_name in phase_executions and resolve_phase_status(phase_executions.get(phase_name)) == "completed"
    ]


def build_analysis_summary(
    *,
    current_phase: str,
    completed_phases: list[str],
    failed_phase: Optional[str],
    status: str,
) -> Dict[str, Any]:
    summary_status = "pending"
    if status == "failed":
        summary_status = "needs_followup"
    elif status == "completed":
        summary_status = "stable"
    elif status == "active":
        summary_status = "in_progress"

    return {
        "status": summary_status,
        "completed_phase_count": len(completed_phases),
        "completed_phases": list(completed_phases),
        "outcome_count": 0,
        "deliverable_count": 0,
        "last_phase": completed_phases[-1] if completed_phases else current_phase,
        "failed_phase": failed_phase or "",
        "failed_operation_count": 1 if failed_phase else 0,
        "final_status": status,
    }


def build_session_contract(session_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    session = deepcopy(session_snapshot)
    phase_executions = normalize_phase_executions(session.get("phase_executions") or {})
    metadata = deepcopy(session.get("metadata") or {})
    status = str(session.get("status") or "pending").strip().lower() or "pending"
    current_phase = str(session.get("current_phase") or "observe").strip().lower() or "observe"

    completed_phases = metadata.get("completed_phases")
    if not isinstance(completed_phases, list):
        completed_phases = extract_completed_phases(phase_executions)
        metadata["completed_phases"] = completed_phases

    if not isinstance(metadata.get("analysis_summary"), dict):
        metadata["analysis_summary"] = build_analysis_summary(
            current_phase=current_phase,
            completed_phases=completed_phases,
            failed_phase=metadata.get("failed_phase"),
            status=status,
        )
    metadata.setdefault("final_status", status)
    metadata.setdefault(
        "last_completed_phase",
        completed_phases[-1] if completed_phases else None,
    )

    deliverables = session.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        publish_result = resolve_phase_result(phase_executions.get("publish"))
        deliverables = get_phase_value(publish_result, "deliverables", []) or []
    if not isinstance(deliverables, list) or not deliverables:
        deliverables = [
            {
                "name": item.get("name"),
                "artifact_type": item.get("artifact_type"),
                "file_path": item.get("file_path"),
            }
            for item in session.get("artifacts") or []
            if isinstance(item, dict)
            and str(item.get("artifact_type") or "").strip().lower() in {"paper", "report"}
        ]

    contract = dict(session)
    contract["status"] = status
    contract["current_phase"] = current_phase
    contract["phase_executions"] = phase_executions
    contract["metadata"] = metadata
    contract["outcomes"] = deepcopy(session.get("outcomes") or [])
    contract["deliverables"] = deepcopy(deliverables) if isinstance(deliverables, list) else []
    contract["observe_philology"] = resolve_observe_philology_assets(
        observe_philology=session.get("observe_philology"),
        artifacts=session.get("artifacts") if isinstance(session.get("artifacts"), list) else [],
        observe_phase_result=resolve_phase_result(phase_executions.get("observe")),
        observe_documents=session.get("observe_documents") if isinstance(session.get("observe_documents"), list) else [],
    )
    contract["description"] = str(session.get("description") or "")
    contract["research_objective"] = str(session.get("research_objective") or "")
    contract["research_scope"] = str(session.get("research_scope") or "")
    contract["researchers"] = list(session.get("researchers") or [])
    contract["started_at"] = session.get("started_at")
    contract["completed_at"] = session.get("completed_at")
    contract["duration"] = float(session.get("duration") or 0.0)
    return contract


def build_session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
    contract = build_session_contract(session)
    return {
        "cycle_id": contract.get("cycle_id", ""),
        "cycle_name": contract.get("cycle_name", ""),
        "status": contract.get("status", "pending"),
        "current_phase": contract.get("current_phase", "observe"),
        "started_at": contract.get("started_at"),
        "research_objective": contract.get("research_objective", ""),
        "analysis_summary": deepcopy((contract.get("metadata") or {}).get("analysis_summary") or {}),
    }


def resolve_session_topic(session: Dict[str, Any]) -> str:
    for key in ("research_objective", "description", "cycle_name"):
        value = str(session.get(key) or "").strip()
        if value:
            return value
    return "中医研究问题"


def build_observe_graph(session: Dict[str, Any]) -> Dict[str, Any]:
    contract = build_session_contract(session)
    observe_execution = (contract.get("phase_executions") or {}).get("observe")
    observe_result = resolve_phase_result(observe_execution)
    semantic_graph = get_phase_value(observe_result, "semantic_graph", {}) or {}
    graph_statistics = get_phase_value(observe_result, "graph_statistics", {}) or {}
    return {
        "nodes": list(semantic_graph.get("nodes") or []),
        "edges": list(semantic_graph.get("edges") or []),
        "statistics": dict(graph_statistics) if isinstance(graph_statistics, dict) else {},
    }
