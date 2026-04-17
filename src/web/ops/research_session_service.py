"""Repository-backed Web research session operations."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.orchestration.research_runtime_service import (
    ResearchRuntimeResult,
    ResearchRuntimeService,
)
from src.web.ops.research_session_contract import (
    PHASE_ORDER,
    build_analysis_summary,
    build_observe_graph,
    build_session_contract,
    build_session_summary,
    phase_index,
    resolve_phase_result,
    resolve_session_topic,
)

logger = logging.getLogger(__name__)


def _get_repository(app: Any) -> ResearchSessionRepository:
    state = getattr(app, "state", None)
    db_manager = getattr(state, "db_manager", None)
    if db_manager is None:
        raise RuntimeError("数据库未初始化，无法访问研究会话")
    return ResearchSessionRepository(db_manager)


def _build_orchestrator_config(app: Any) -> Dict[str, Any]:
    state = getattr(app, "state", None)
    job_manager = getattr(state, "job_manager", None)
    default_orchestrator_config = getattr(job_manager, "_default_orchestrator_config", None)
    if isinstance(default_orchestrator_config, dict) and default_orchestrator_config:
        return deepcopy(default_orchestrator_config)

    runtime_assembly = getattr(state, "runtime_assembly", None)
    default_orchestrator_config = getattr(runtime_assembly, "orchestrator_config", None)
    if isinstance(default_orchestrator_config, dict) and default_orchestrator_config:
        return deepcopy(default_orchestrator_config)

    runtime_config = getattr(state, "config", None)
    if isinstance(runtime_config, dict):
        return {"pipeline_config": deepcopy(runtime_config)}
    return {"pipeline_config": {}}


def _load_session_snapshot(repository: ResearchSessionRepository, cycle_id: str) -> Optional[Dict[str, Any]]:
    snapshot = repository.get_full_snapshot(cycle_id)
    if isinstance(snapshot, dict):
        return snapshot
    snapshot = repository.get_session(cycle_id)
    if isinstance(snapshot, dict):
        return snapshot
    return None


def create_research_session(
    app: Any,
    *,
    cycle_name: str,
    description: str,
    objective: str,
    scope: str,
    researchers: Optional[list[str]] = None,
) -> Dict[str, Any]:
    repository = _get_repository(app)
    payload = {
        "cycle_name": cycle_name,
        "description": description,
        "status": "pending",
        "current_phase": "observe",
        "research_objective": objective,
        "research_scope": scope,
        "researchers": list(researchers or []),
        "metadata": {
            "phase_contexts": {},
            "completed_phases": [],
            "failed_phase": None,
            "final_status": "pending",
            "last_completed_phase": None,
            "analysis_summary": build_analysis_summary(
                current_phase="observe",
                completed_phases=[],
                failed_phase=None,
                status="pending",
            ),
        },
        "outcomes": [],
        "deliverables": [],
    }
    created = repository.create_session(payload)
    return build_session_contract(created)


def list_research_sessions(app: Any) -> list[Dict[str, Any]]:
    repository = _get_repository(app)
    page = repository.list_sessions(limit=50)
    items = page.get("items") if isinstance(page, dict) else []
    return [build_session_summary(item) for item in items if isinstance(item, dict)]


def get_research_session(app: Any, cycle_id: str) -> Optional[Dict[str, Any]]:
    repository = _get_repository(app)
    snapshot = _load_session_snapshot(repository, cycle_id)
    if snapshot is None:
        return None
    return build_session_contract(snapshot)


def apply_catalog_review(
    app: Any,
    cycle_id: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    repository = _get_repository(app)
    saved = repository.upsert_observe_catalog_review(cycle_id, payload)
    if saved is None:
        return None

    snapshot = _load_session_snapshot(repository, cycle_id)
    if snapshot is None:
        return None
    return build_session_contract(snapshot)


def apply_philology_review(
    app: Any,
    cycle_id: str,
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    repository = _get_repository(app)
    saved = repository.upsert_observe_workbench_review(cycle_id, payload)
    if saved is None:
        return None

    snapshot = _load_session_snapshot(repository, cycle_id)
    if snapshot is None:
        return None
    return build_session_contract(snapshot)


def apply_catalog_review_batch(
    app: Any,
    cycle_id: str,
    decisions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    repository = _get_repository(app)
    saved = repository.upsert_observe_catalog_review_batch(cycle_id, decisions)
    if saved is None:
        return None
    snapshot = _load_session_snapshot(repository, cycle_id)
    if snapshot is None:
        return None
    return build_session_contract(snapshot)


def apply_philology_review_batch(
    app: Any,
    cycle_id: str,
    decisions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    repository = _get_repository(app)
    saved = repository.upsert_observe_workbench_review_batch(cycle_id, decisions)
    if saved is None:
        return None
    snapshot = _load_session_snapshot(repository, cycle_id)
    if snapshot is None:
        return None
    return build_session_contract(snapshot)


def _build_runtime_result_contract(
    existing_session: Dict[str, Any],
    runtime_result: ResearchRuntimeResult,
    *,
    target_phase: str,
    phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    snapshot = dict(runtime_result.cycle_snapshot or {})
    phase_executions = deepcopy(snapshot.get("phase_executions") or {})
    completed_phases = [
        phase.phase
        for phase in runtime_result.orchestration_result.phases
        if phase.status == "completed"
    ]
    runtime_status = str(runtime_result.orchestration_result.status or "completed").strip().lower() or "completed"
    target_index = phase_index(target_phase)
    if runtime_status in {"failed", "partial"}:
        session_status = "failed"
        current_phase = target_phase
    elif target_index >= len(PHASE_ORDER) - 1:
        session_status = "completed"
        current_phase = target_phase
    else:
        session_status = "active"
        current_phase = PHASE_ORDER[target_index + 1]

    metadata = deepcopy(existing_session.get("metadata") or {})
    metadata.update(deepcopy(snapshot.get("metadata") or {}))
    if isinstance(phase_contexts, dict):
        metadata["phase_contexts"] = deepcopy(phase_contexts)
    metadata["runtime_cycle_id"] = runtime_result.orchestration_result.cycle_id
    metadata["runtime_status"] = runtime_status
    metadata["last_requested_phase"] = target_phase
    metadata["completed_phases"] = completed_phases
    metadata["failed_phase"] = target_phase if session_status == "failed" else None
    metadata["final_status"] = session_status
    metadata["last_completed_phase"] = completed_phases[-1] if completed_phases else None
    metadata["analysis_summary"] = build_analysis_summary(
        current_phase=current_phase,
        completed_phases=completed_phases,
        failed_phase=metadata.get("failed_phase"),
        status=session_status,
    )

    snapshot.setdefault("cycle_id", runtime_result.orchestration_result.cycle_id)
    snapshot.setdefault("cycle_name", existing_session.get("cycle_name") or runtime_result.orchestration_result.pipeline_metadata.get("cycle_name"))
    snapshot.setdefault("description", existing_session.get("description") or runtime_result.orchestration_result.pipeline_metadata.get("description"))
    snapshot.setdefault("research_objective", existing_session.get("research_objective") or runtime_result.orchestration_result.topic)
    snapshot.setdefault("research_scope", existing_session.get("research_scope") or runtime_result.orchestration_result.pipeline_metadata.get("scope"))
    snapshot.setdefault("researchers", existing_session.get("researchers") or [])
    snapshot["status"] = session_status
    snapshot["current_phase"] = current_phase
    snapshot["started_at"] = existing_session.get("started_at") or runtime_result.orchestration_result.started_at
    snapshot["completed_at"] = (
        runtime_result.orchestration_result.completed_at
        if session_status in {"completed", "failed"}
        else None
    )
    snapshot["duration"] = float(runtime_result.orchestration_result.total_duration_sec or 0.0)
    snapshot["phase_executions"] = phase_executions
    snapshot["outcomes"] = deepcopy(snapshot.get("outcomes") or existing_session.get("outcomes") or [])
    snapshot["metadata"] = metadata
    return build_session_contract(snapshot)


def build_runtime_cycle_response(
    existing_session: Dict[str, Any],
    refreshed_snapshot: Optional[Dict[str, Any]],
    runtime_result: ResearchRuntimeResult,
    *,
    target_phase: str,
    phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if isinstance(refreshed_snapshot, dict):
        refreshed_contract = build_session_contract(refreshed_snapshot)
        refreshed_phase_executions = refreshed_contract.get("phase_executions") or {}
        if target_phase in refreshed_phase_executions:
            return refreshed_contract
        if str(refreshed_contract.get("status") or "") != str(existing_session.get("status") or ""):
            return refreshed_contract
        if str(refreshed_contract.get("current_phase") or "") != str(existing_session.get("current_phase") or ""):
            return refreshed_contract

    return _build_runtime_result_contract(
        existing_session,
        runtime_result,
        target_phase=target_phase,
        phase_contexts=phase_contexts,
    )


def execute_research_phase(
    app: Any,
    cycle_id: str,
    phase_name: str,
    *,
    phase_context: Optional[Dict[str, Any]] = None,
    emit: Optional[Any] = None,
) -> Dict[str, Any]:
    repository = _get_repository(app)
    snapshot = _load_session_snapshot(repository, cycle_id)
    if snapshot is None:
        raise KeyError(cycle_id)

    session = build_session_contract(snapshot)
    target_phase = str(phase_name or "").strip().lower()
    target_index = phase_index(target_phase)
    stored_phase_contexts = deepcopy((session.get("metadata") or {}).get("phase_contexts") or {})
    if isinstance(phase_context, dict):
        stored_phase_contexts[target_phase] = deepcopy(phase_context)

    service_config = _build_orchestrator_config(app)
    service_config["phases"] = list(PHASE_ORDER[: target_index + 1])
    researchers = list(session.get("researchers") or [])
    if researchers:
        service_config["researchers"] = researchers

    runtime_service = ResearchRuntimeService(service_config)
    runtime_result = runtime_service.run(
        resolve_session_topic(session),
        phase_contexts=stored_phase_contexts,
        cycle_name=str(session.get("cycle_name") or "").strip() or None,
        description=str(session.get("description") or "").strip() or None,
        scope=str(session.get("research_scope") or "").strip() or None,
        emit=emit,
        cycle_id=cycle_id,
    )

    refreshed = _load_session_snapshot(repository, cycle_id)
    cycle_response = build_runtime_cycle_response(
        session,
        refreshed,
        runtime_result,
        target_phase=target_phase,
        phase_contexts=stored_phase_contexts,
    )
    phase_result = deepcopy(
        runtime_result.phase_results.get(target_phase)
        or resolve_phase_result((cycle_response.get("phase_executions") or {}).get(target_phase))
    )
    return {
        "cycle": cycle_response,
        "phase_result": phase_result,
    }


def get_research_observe_graph(app: Any, cycle_id: str) -> Optional[Dict[str, Any]]:
    session = get_research_session(app, cycle_id)
    if session is None:
        return None
    return build_observe_graph(session)
