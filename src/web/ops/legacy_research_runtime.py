"""Legacy Web research session store backed by the shared runtime service."""

from __future__ import annotations

import logging
from copy import deepcopy
from threading import RLock
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from src.orchestration.research_runtime_service import ResearchRuntimeService
from src.research.phase_result import get_phase_value

if TYPE_CHECKING:
    from src.infrastructure.research_session_repo import ResearchSessionRepository


logger = logging.getLogger(__name__)

PHASE_ORDER = (
    "observe",
    "hypothesis",
    "experiment",
    "experiment_execution",
    "analyze",
    "publish",
    "reflect",
)


def _phase_index(phase_name: str) -> int:
    normalized = str(phase_name or "").strip().lower()
    if normalized not in PHASE_ORDER:
        raise ValueError(f"未知研究阶段: {phase_name}")
    return PHASE_ORDER.index(normalized)


def _resolve_phase_result(execution: Any) -> Dict[str, Any]:
    if not isinstance(execution, dict):
        return {}
    result = execution.get("result")
    if isinstance(result, dict):
        return result
    return execution


def _build_analysis_summary(
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


def _extract_completed_phases(phase_executions: Dict[str, Dict[str, Any]]) -> list[str]:
    return [
        phase_name
        for phase_name in PHASE_ORDER
        if phase_name in phase_executions
        and _resolve_phase_status(phase_executions.get(phase_name)) == "completed"
    ]


def _resolve_phase_status(execution: Any) -> str:
    if not isinstance(execution, dict):
        return "pending"
    result = _resolve_phase_result(execution)
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


def _normalize_phase_executions(executions: Any) -> Dict[str, Dict[str, Any]]:
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


def _build_legacy_session(session_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    legacy_session = deepcopy(session_snapshot)
    phase_executions = _normalize_phase_executions(legacy_session.get("phase_executions") or {})
    metadata = deepcopy(legacy_session.get("metadata") or {})
    status = str(legacy_session.get("status") or "pending").strip().lower() or "pending"
    current_phase = str(legacy_session.get("current_phase") or "observe").strip().lower() or "observe"

    completed_phases = metadata.get("completed_phases")
    if not isinstance(completed_phases, list):
        completed_phases = _extract_completed_phases(phase_executions)
        metadata["completed_phases"] = completed_phases

    metadata.setdefault("legacy_runtime", True)
    metadata.setdefault("runtime_service", "ResearchRuntimeService")
    metadata.setdefault("phase_contexts", {})
    metadata.setdefault("phase_history", [])
    metadata.setdefault("phase_timings", {})
    metadata.setdefault("failed_phase", None)
    metadata.setdefault("final_status", status)
    metadata.setdefault(
        "last_completed_phase",
        completed_phases[-1] if completed_phases else None,
    )
    if not isinstance(metadata.get("analysis_summary"), dict):
        metadata["analysis_summary"] = _build_analysis_summary(
            current_phase=current_phase,
            completed_phases=completed_phases,
            failed_phase=metadata.get("failed_phase"),
            status=status,
        )

    publish_result = _resolve_phase_result(phase_executions.get("publish"))
    deliverables = get_phase_value(publish_result, "deliverables", []) or []
    if not isinstance(deliverables, list) or not deliverables:
        deliverables = [
            {
                "name": item.get("name"),
                "artifact_type": item.get("artifact_type"),
                "file_path": item.get("file_path"),
            }
            for item in legacy_session.get("artifacts") or []
            if isinstance(item, dict)
            and str(item.get("artifact_type") or "").strip().lower() in {"paper", "report"}
        ]

    legacy_session["phase_executions"] = phase_executions
    legacy_session["outcomes"] = deepcopy(legacy_session.get("outcomes") or [])
    legacy_session["deliverables"] = deepcopy(deliverables) if isinstance(deliverables, list) else []
    legacy_session["metadata"] = metadata
    legacy_session.setdefault("description", "")
    legacy_session.setdefault("started_at", None)
    legacy_session.setdefault("completed_at", None)
    legacy_session.setdefault("duration", 0.0)
    legacy_session.setdefault("research_objective", "")
    legacy_session.setdefault("research_scope", "")
    legacy_session.setdefault("target_audience", "")
    legacy_session.setdefault("researchers", [])
    legacy_session.setdefault("advisors", [])
    legacy_session.setdefault("resources", {})
    legacy_session.setdefault("budget", 0.0)
    legacy_session.setdefault("timeline", {})
    legacy_session.setdefault("quality_metrics", {})
    legacy_session.setdefault("risk_assessment", {})
    legacy_session.setdefault("expert_reviews", [])
    legacy_session.setdefault("tags", [])
    legacy_session.setdefault("categories", [])
    return legacy_session


class LegacyResearchRuntimeStore:
    """Keep the legacy Web cycle API while delegating execution to ResearchRuntimeService."""

    def __init__(
        self,
        orchestrator_config: Optional[Dict[str, Any]] = None,
        repository: Optional["ResearchSessionRepository"] = None,
    ):
        self._base_orchestrator_config = deepcopy(orchestrator_config or {})
        self._repository = repository
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()

    def create_session(
        self,
        *,
        cycle_name: str,
        description: str,
        objective: str,
        scope: str,
        researchers: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        cycle_id = str(uuid4())
        session = {
            "cycle_id": cycle_id,
            "cycle_name": cycle_name,
            "description": description,
            "status": "pending",
            "current_phase": "observe",
            "started_at": None,
            "completed_at": None,
            "duration": 0.0,
            "research_objective": objective,
            "research_scope": scope,
            "target_audience": "",
            "researchers": list(researchers or []),
            "advisors": [],
            "resources": {},
            "budget": 0.0,
            "timeline": {},
            "phase_executions": {},
            "outcomes": [],
            "deliverables": [],
            "quality_metrics": {},
            "risk_assessment": {},
            "expert_reviews": [],
            "tags": [],
            "categories": [],
            "metadata": {
                "legacy_runtime": True,
                "runtime_service": "ResearchRuntimeService",
                "phase_contexts": {},
                "phase_history": [],
                "phase_timings": {},
                "completed_phases": [],
                "failed_phase": None,
                "final_status": "pending",
                "last_completed_phase": None,
                "analysis_summary": _build_analysis_summary(
                    current_phase="observe",
                    completed_phases=[],
                    failed_phase=None,
                    status="pending",
                ),
            },
        }
        with self._lock:
            self._sessions[cycle_id] = session
            created = deepcopy(session)

        self._persist_session_snapshot(created)
        return created

    def get_session(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(cycle_id)
            if session is not None:
                return deepcopy(session)
        return self._load_session_from_repository(cycle_id)

    def list_sessions(self) -> list[Dict[str, Any]]:
        repository = self._repository
        if repository is not None:
            try:
                page = repository.list_sessions(limit=50)
            except Exception as exc:
                logger.warning("legacy research session list fallback to memory: %s", exc)
            else:
                items: list[Dict[str, Any]] = []
                cached_sessions: Dict[str, Dict[str, Any]] = {}
                for raw_session in page.get("items") or []:
                    if not isinstance(raw_session, dict):
                        continue
                    session = _build_legacy_session(raw_session)
                    cycle_id = str(session.get("cycle_id") or "").strip()
                    if cycle_id:
                        cached_sessions[cycle_id] = session
                    items.append(self._build_session_summary(session))
                if cached_sessions:
                    with self._lock:
                        self._sessions.update(cached_sessions)
                return items

        with self._lock:
            return [self._build_session_summary(session) for session in self._sessions.values()]

    def execute_phase(
        self,
        cycle_id: str,
        phase_name: str,
        *,
        phase_context: Optional[Dict[str, Any]] = None,
        emit: Optional[Any] = None,
    ) -> Dict[str, Any]:
        target_phase = str(phase_name or "").strip().lower()
        target_index = _phase_index(target_phase)

        with self._lock:
            session = self._sessions.get(cycle_id)
        if session is None:
            session = self._load_session_from_repository(cycle_id)
        if session is None:
            raise KeyError(cycle_id)

        stored_phase_contexts = deepcopy((session.get("metadata") or {}).get("phase_contexts") or {})
        if isinstance(phase_context, dict):
            stored_phase_contexts[target_phase] = deepcopy(phase_context)
        topic = self._resolve_topic(session)
        cycle_name = str(session.get("cycle_name") or topic).strip() or topic
        description = str(session.get("description") or topic).strip() or topic
        scope = str(session.get("research_scope") or "").strip() or None
        researchers = list(session.get("researchers") or [])

        service_config = deepcopy(self._base_orchestrator_config)
        service_config["phases"] = list(PHASE_ORDER[: target_index + 1])
        if researchers:
            service_config["researchers"] = researchers
        runtime_service = ResearchRuntimeService(service_config)
        runtime_result = runtime_service.run(
            topic,
            phase_contexts=stored_phase_contexts,
            cycle_name=cycle_name,
            description=description,
            scope=scope,
            emit=emit,
            cycle_id=cycle_id,
        )

        with self._lock:
            session = self._sessions.get(cycle_id)
            if session is None:
                session = deepcopy(session or {}) if isinstance(session, dict) else deepcopy(_build_legacy_session({"cycle_id": cycle_id}))
                self._sessions[cycle_id] = session
            self._apply_runtime_result(
                session,
                target_phase=target_phase,
                phase_contexts=stored_phase_contexts,
                runtime_result=runtime_result,
            )
            cycle_response = deepcopy(session)

        self._persist_session_snapshot(cycle_response)
        restored = self._load_session_from_repository(cycle_id)
        if restored is not None:
            cycle_response = restored

        return {
            "cycle": cycle_response,
            "phase_result": deepcopy(
                runtime_result.phase_results.get(target_phase)
                or _resolve_phase_result(
                    (runtime_result.cycle_snapshot.get("phase_executions") or {}).get(target_phase)
                )
            ),
        }

    def get_observe_graph(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        session = self.get_session(cycle_id)
        if session is None:
            return None
        observe_execution = (session.get("phase_executions") or {}).get("observe")
        observe_result = _resolve_phase_result(observe_execution)
        semantic_graph = get_phase_value(observe_result, "semantic_graph", {}) or {}
        graph_statistics = get_phase_value(observe_result, "graph_statistics", {}) or {}
        return {
            "nodes": list(semantic_graph.get("nodes") or []),
            "edges": list(semantic_graph.get("edges") or []),
            "statistics": dict(graph_statistics) if isinstance(graph_statistics, dict) else {},
        }

    @staticmethod
    def _resolve_topic(session: Dict[str, Any]) -> str:
        for key in ("research_objective", "description", "cycle_name"):
            value = str(session.get(key) or "").strip()
            if value:
                return value
        return "中医研究问题"

    @staticmethod
    def _build_session_summary(session: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "cycle_id": session["cycle_id"],
            "cycle_name": session["cycle_name"],
            "status": session["status"],
            "current_phase": session["current_phase"],
            "started_at": session.get("started_at"),
            "research_objective": session.get("research_objective", ""),
            "analysis_summary": deepcopy(
                (session.get("metadata") or {}).get("analysis_summary")
                or session.get("analysis_summary")
                or {}
            ),
        }

    def _load_session_from_repository(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        repository = self._repository
        if repository is None:
            return None

        try:
            snapshot = repository.get_full_snapshot(cycle_id) or repository.get_session(cycle_id)
        except Exception as exc:
            logger.warning("legacy research session reload failed: %s", exc)
            return None
        if not isinstance(snapshot, dict):
            return None

        session = _build_legacy_session(snapshot)
        with self._lock:
            self._sessions[cycle_id] = session
            return deepcopy(session)

    def _persist_session_snapshot(self, session: Dict[str, Any]) -> None:
        repository = self._repository
        if repository is None:
            return

        cycle_id = str(session.get("cycle_id") or "").strip()
        if not cycle_id:
            return

        payload = deepcopy(session)
        try:
            if repository.get_session(cycle_id) is None:
                repository.create_session(payload)
            else:
                repository.update_session(cycle_id, payload)
        except Exception as exc:
            logger.warning("legacy research session persistence failed: %s", exc)

    def _apply_runtime_result(
        self,
        session: Dict[str, Any],
        *,
        target_phase: str,
        phase_contexts: Dict[str, Dict[str, Any]],
        runtime_result: Any,
    ) -> None:
        cycle_snapshot = dict(runtime_result.cycle_snapshot or {})
        phase_executions = deepcopy(cycle_snapshot.get("phase_executions") or {})
        metadata = deepcopy(session.get("metadata") or {})
        metadata.update(deepcopy(cycle_snapshot.get("metadata") or {}))

        completed_phases = _extract_completed_phases(phase_executions)
        runtime_status = str(runtime_result.orchestration_result.status or "completed").strip().lower()
        if runtime_status in {"failed", "partial"}:
            session_status = "failed"
            current_phase = target_phase
        elif target_phase == PHASE_ORDER[-1]:
            session_status = "completed"
            current_phase = target_phase
        else:
            session_status = "active"
            current_phase = PHASE_ORDER[_phase_index(target_phase) + 1]

        metadata["phase_contexts"] = deepcopy(phase_contexts)
        metadata["runtime_cycle_id"] = runtime_result.orchestration_result.cycle_id
        metadata["runtime_status"] = runtime_status
        metadata["last_requested_phase"] = target_phase
        metadata["completed_phases"] = completed_phases
        metadata["failed_phase"] = target_phase if session_status == "failed" else None
        metadata["final_status"] = session_status
        metadata["last_completed_phase"] = completed_phases[-1] if completed_phases else None
        metadata["analysis_summary"] = _build_analysis_summary(
            current_phase=current_phase,
            completed_phases=completed_phases,
            failed_phase=metadata.get("failed_phase"),
            status=session_status,
        )

        session["status"] = session_status
        session["current_phase"] = current_phase
        session["started_at"] = session.get("started_at") or runtime_result.orchestration_result.started_at
        session["completed_at"] = (
            runtime_result.orchestration_result.completed_at
            if session_status in {"completed", "failed"}
            else None
        )
        session["duration"] = float(runtime_result.orchestration_result.total_duration_sec or 0.0)
        session["phase_executions"] = phase_executions
        session["outcomes"] = deepcopy(cycle_snapshot.get("outcomes") or [])
        session["quality_metrics"] = deepcopy(cycle_snapshot.get("quality_metrics") or {})
        session["risk_assessment"] = deepcopy(cycle_snapshot.get("risk_assessment") or {})
        session["metadata"] = metadata

        publish_result = _resolve_phase_result(phase_executions.get("publish"))
        deliverables = get_phase_value(publish_result, "deliverables", []) or []
        session["deliverables"] = deepcopy(deliverables) if isinstance(deliverables, list) else []


def _build_legacy_research_orchestrator_config(app: Any) -> Dict[str, Any]:
    state = getattr(app, "state", None)
    job_manager = getattr(state, "job_manager", None)
    default_orchestrator_config = getattr(job_manager, "_default_orchestrator_config", None)
    if isinstance(default_orchestrator_config, dict) and default_orchestrator_config:
        return deepcopy(default_orchestrator_config)

    runtime_config = getattr(state, "config", None)
    if isinstance(runtime_config, dict):
        return {"pipeline_config": deepcopy(runtime_config)}
    return {"pipeline_config": {}}


def get_legacy_research_store(app: Any) -> LegacyResearchRuntimeStore:
    state = getattr(app, "state", None)
    store = getattr(state, "legacy_research_store", None)
    if isinstance(store, LegacyResearchRuntimeStore):
        return store

    repository = None
    db_manager = getattr(state, "db_manager", None)
    if db_manager is not None:
        try:
            from src.infrastructure.research_session_repo import (
                ResearchSessionRepository,
            )

            repository = ResearchSessionRepository(db_manager)
        except Exception as exc:
            logger.warning("legacy research repository binding skipped: %s", exc)

    resolved_store = LegacyResearchRuntimeStore(
        _build_legacy_research_orchestrator_config(app),
        repository=repository,
    )
    state.legacy_research_store = resolved_store
    return resolved_store
