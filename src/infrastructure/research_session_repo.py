"""P3.1 ResearchSession 仓储层。

提供 ResearchSession / PhaseExecution / ResearchArtifact 的 CRUD 与查询方法，
并支持从 ResearchCycle dataclass 的双向转换。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from src.infrastructure.persistence import (
    ArtifactTypeEnum,
    DatabaseManager,
    PhaseExecution,
    PhaseStatusEnum,
    ResearchArtifact,
    ResearchSession,
    SessionStatusEnum,
    _json_dumps,
    _json_loads,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助：枚举安全转换
# ---------------------------------------------------------------------------

def _to_session_status(value: Any) -> SessionStatusEnum:
    if isinstance(value, SessionStatusEnum):
        return value
    raw = str(getattr(value, "value", value)).lower()
    try:
        return SessionStatusEnum(raw)
    except ValueError:
        return SessionStatusEnum.PENDING


def _to_phase_status(value: Any) -> PhaseStatusEnum:
    if isinstance(value, PhaseStatusEnum):
        return value
    raw = str(getattr(value, "value", value)).lower()
    try:
        return PhaseStatusEnum(raw)
    except ValueError:
        return PhaseStatusEnum.PENDING


def _to_artifact_type(value: Any) -> ArtifactTypeEnum:
    if isinstance(value, ArtifactTypeEnum):
        return value
    raw = str(getattr(value, "value", value)).lower()
    try:
        return ArtifactTypeEnum(raw)
    except ValueError:
        return ArtifactTypeEnum.OTHER


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# ResearchSessionRepository
# ---------------------------------------------------------------------------

class ResearchSessionRepository:
    """ResearchSession 全生命周期仓储。"""

    def __init__(self, db_manager: DatabaseManager):
        self._db = db_manager

    # ---- 会话 CRUD -------------------------------------------------------

    def create_session(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """创建研究会话，返回序列化字典。"""
        with self._db.session_scope() as session:
            rs = ResearchSession(
                cycle_id=str(payload.get("cycle_id") or uuid.uuid4()),
                cycle_name=str(payload["cycle_name"]),
                description=str(payload.get("description") or ""),
                status=_to_session_status(payload.get("status", "pending")),
                current_phase=str(payload.get("current_phase") or ""),
                research_objective=str(payload.get("research_objective") or ""),
                research_scope=str(payload.get("research_scope") or ""),
                target_audience=str(payload.get("target_audience") or ""),
                researchers_json=_json_dumps(payload.get("researchers"), "[]"),
                advisors_json=_json_dumps(payload.get("advisors"), "[]"),
                resources_json=_json_dumps(payload.get("resources"), "{}"),
                budget=float(payload.get("budget") or 0.0),
                timeline_json=_json_dumps(payload.get("timeline"), "{}"),
                quality_metrics_json=_json_dumps(payload.get("quality_metrics"), "{}"),
                risk_assessment_json=_json_dumps(payload.get("risk_assessment"), "{}"),
                expert_reviews_json=_json_dumps(payload.get("expert_reviews"), "[]"),
                tags_json=_json_dumps(payload.get("tags"), "[]"),
                categories_json=_json_dumps(payload.get("categories"), "[]"),
                metadata_json=_json_dumps(payload.get("metadata"), "{}"),
                started_at=_parse_datetime(payload.get("started_at")),
                completed_at=_parse_datetime(payload.get("completed_at")),
                duration=float(payload.get("duration") or 0.0),
            )
            session.add(rs)
            session.flush()
            return self._session_to_dict(rs)

    def get_session(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """按 cycle_id 查询，返回 None 表示不存在。"""
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            return self._session_to_dict(rs)

    def get_session_by_id(self, session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """按主键 id 查询。"""
        with self._db.session_scope() as session:
            rs = session.get(ResearchSession, session_id)
            if rs is None:
                return None
            return self._session_to_dict(rs)

    def update_session(self, cycle_id: str, updates: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """部分更新会话字段，返回更新后的字典。"""
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            self._apply_session_updates(rs, updates)
            session.flush()
            return self._session_to_dict(rs)

    def delete_session(self, cycle_id: str) -> bool:
        """删除会话及其级联的阶段/工件记录。"""
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return False
            session.delete(rs)
            session.flush()
            return True

    def list_sessions(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """分页列出会话。"""
        with self._db.session_scope() as session:
            query = session.query(ResearchSession).order_by(ResearchSession.created_at.desc())
            if status:
                query = query.filter(ResearchSession.status == _to_session_status(status))
            total = query.count()
            items = query.offset(offset).limit(limit).all()
            return {
                "items": [self._session_to_dict(rs) for rs in items],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    # ---- 状态转换 ---------------------------------------------------------

    def start_session(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {
            "status": "active",
            "started_at": datetime.utcnow().isoformat(),
        })

    def complete_session(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
        })

    def fail_session(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {"status": "failed"})

    def suspend_session(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {"status": "suspended"})

    # ---- 阶段执行 CRUD ---------------------------------------------------

    def add_phase_execution(
        self, cycle_id: str, payload: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """为指定会话添加阶段执行记录。"""
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            pe = PhaseExecution(
                session_id=rs.id,
                phase=str(payload["phase"]),
                status=_to_phase_status(payload.get("status", "pending")),
                started_at=_parse_datetime(payload.get("started_at")),
                completed_at=_parse_datetime(payload.get("completed_at")),
                duration=float(payload.get("duration") or 0.0),
                input_json=_json_dumps(payload.get("input"), "{}"),
                output_json=_json_dumps(payload.get("output"), "{}"),
                error_detail=str(payload.get("error_detail") or "") or None,
            )
            session.add(pe)
            session.flush()
            return self._phase_to_dict(pe)

    def update_phase_execution(
        self, phase_id: uuid.UUID, updates: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        with self._db.session_scope() as session:
            pe = session.get(PhaseExecution, phase_id)
            if pe is None:
                return None
            if "status" in updates:
                pe.status = _to_phase_status(updates["status"])
            if "started_at" in updates:
                pe.started_at = _parse_datetime(updates["started_at"])
            if "completed_at" in updates:
                pe.completed_at = _parse_datetime(updates["completed_at"])
            if "duration" in updates:
                pe.duration = float(updates["duration"])
            if "output" in updates:
                pe.output_json = _json_dumps(updates["output"], "{}")
            if "error_detail" in updates:
                pe.error_detail = str(updates["error_detail"]) or None
            session.flush()
            return self._phase_to_dict(pe)

    def list_phase_executions(self, cycle_id: str) -> List[Dict[str, Any]]:
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return []
            phases = (
                session.query(PhaseExecution)
                .filter_by(session_id=rs.id)
                .order_by(PhaseExecution.created_at)
                .all()
            )
            return [self._phase_to_dict(pe) for pe in phases]

    # ---- 工件 CRUD -------------------------------------------------------

    def add_artifact(
        self, cycle_id: str, payload: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            phase_execution_id = payload.get("phase_execution_id")
            if phase_execution_id:
                phase_execution_id = (
                    phase_execution_id
                    if isinstance(phase_execution_id, uuid.UUID)
                    else uuid.UUID(str(phase_execution_id))
                )
            artifact = ResearchArtifact(
                session_id=rs.id,
                phase_execution_id=phase_execution_id,
                artifact_type=_to_artifact_type(payload.get("artifact_type", "other")),
                name=str(payload["name"]),
                description=str(payload.get("description") or ""),
                content_json=_json_dumps(payload.get("content"), "{}"),
                file_path=str(payload.get("file_path") or "") or None,
                mime_type=str(payload.get("mime_type") or "") or None,
                size_bytes=int(payload.get("size_bytes") or 0),
                metadata_json=_json_dumps(payload.get("metadata"), "{}"),
            )
            session.add(artifact)
            session.flush()
            return self._artifact_to_dict(artifact)

    def list_artifacts(
        self,
        cycle_id: str,
        *,
        artifact_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return []
            query = (
                session.query(ResearchArtifact)
                .filter_by(session_id=rs.id)
                .order_by(ResearchArtifact.created_at)
            )
            if artifact_type:
                query = query.filter(
                    ResearchArtifact.artifact_type == _to_artifact_type(artifact_type),
                )
            return [self._artifact_to_dict(a) for a in query.all()]

    def delete_artifact(self, artifact_id: uuid.UUID) -> bool:
        with self._db.session_scope() as session:
            artifact = session.get(ResearchArtifact, artifact_id)
            if artifact is None:
                return False
            session.delete(artifact)
            session.flush()
            return True

    # ---- 快照（含阶段 + 工件） -------------------------------------------

    def get_full_snapshot(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """返回完整会话快照，包含阶段执行列表与工件列表。"""
        with self._db.session_scope() as session:
            rs = session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            result = self._session_to_dict(rs)
            result["phase_executions"] = [
                self._phase_to_dict(pe) for pe in rs.phase_executions
            ]
            result["artifacts"] = [
                self._artifact_to_dict(a) for a in rs.artifacts
            ]
            return result

    # ---- ResearchCycle dataclass 互转 ------------------------------------

    def save_from_cycle(self, cycle: Any) -> Dict[str, Any]:
        """从 ResearchCycle dataclass 保存/更新会话。"""
        payload = {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "description": cycle.description,
            "status": getattr(cycle.status, "value", str(cycle.status)),
            "current_phase": getattr(cycle.current_phase, "value", str(cycle.current_phase)),
            "research_objective": cycle.research_objective,
            "research_scope": cycle.research_scope,
            "target_audience": cycle.target_audience,
            "researchers": cycle.researchers,
            "advisors": cycle.advisors,
            "resources": cycle.resources,
            "budget": cycle.budget,
            "timeline": cycle.timeline,
            "quality_metrics": cycle.quality_metrics,
            "risk_assessment": cycle.risk_assessment,
            "expert_reviews": cycle.expert_reviews,
            "tags": cycle.tags,
            "categories": cycle.categories,
            "metadata": cycle.metadata,
            "started_at": cycle.started_at,
            "completed_at": cycle.completed_at,
            "duration": cycle.duration,
        }
        existing = self.get_session(cycle.cycle_id)
        if existing:
            return self.update_session(cycle.cycle_id, payload)  # type: ignore[return-value]
        return self.create_session(payload)

    # ---- 序列化 ----------------------------------------------------------

    @staticmethod
    def _session_to_dict(rs: ResearchSession) -> Dict[str, Any]:
        return {
            "id": str(rs.id),
            "cycle_id": rs.cycle_id,
            "cycle_name": rs.cycle_name,
            "description": rs.description or "",
            "status": rs.status.value if isinstance(rs.status, SessionStatusEnum) else str(rs.status),
            "current_phase": rs.current_phase or "",
            "research_objective": rs.research_objective or "",
            "research_scope": rs.research_scope or "",
            "target_audience": rs.target_audience or "",
            "researchers": _json_loads(rs.researchers_json, []),
            "advisors": _json_loads(rs.advisors_json, []),
            "resources": _json_loads(rs.resources_json, {}),
            "budget": rs.budget,
            "timeline": _json_loads(rs.timeline_json, {}),
            "quality_metrics": _json_loads(rs.quality_metrics_json, {}),
            "risk_assessment": _json_loads(rs.risk_assessment_json, {}),
            "expert_reviews": _json_loads(rs.expert_reviews_json, []),
            "tags": _json_loads(rs.tags_json, []),
            "categories": _json_loads(rs.categories_json, []),
            "metadata": _json_loads(rs.metadata_json, {}),
            "started_at": rs.started_at.isoformat() if rs.started_at else None,
            "completed_at": rs.completed_at.isoformat() if rs.completed_at else None,
            "duration": rs.duration,
            "created_at": rs.created_at.isoformat() if rs.created_at else None,
            "updated_at": rs.updated_at.isoformat() if rs.updated_at else None,
        }

    @staticmethod
    def _phase_to_dict(pe: PhaseExecution) -> Dict[str, Any]:
        return {
            "id": str(pe.id),
            "session_id": str(pe.session_id),
            "phase": pe.phase,
            "status": pe.status.value if isinstance(pe.status, PhaseStatusEnum) else str(pe.status),
            "started_at": pe.started_at.isoformat() if pe.started_at else None,
            "completed_at": pe.completed_at.isoformat() if pe.completed_at else None,
            "duration": pe.duration,
            "input": _json_loads(pe.input_json, {}),
            "output": _json_loads(pe.output_json, {}),
            "error_detail": pe.error_detail,
            "created_at": pe.created_at.isoformat() if pe.created_at else None,
        }

    @staticmethod
    def _artifact_to_dict(a: ResearchArtifact) -> Dict[str, Any]:
        return {
            "id": str(a.id),
            "session_id": str(a.session_id),
            "phase_execution_id": str(a.phase_execution_id) if a.phase_execution_id else None,
            "artifact_type": a.artifact_type.value if isinstance(a.artifact_type, ArtifactTypeEnum) else str(a.artifact_type),
            "name": a.name,
            "description": a.description or "",
            "content": _json_loads(a.content_json, {}),
            "file_path": a.file_path,
            "mime_type": a.mime_type,
            "size_bytes": a.size_bytes,
            "metadata": _json_loads(a.metadata_json, {}),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        }

    # ---- 内部 ------------------------------------------------------------

    @staticmethod
    def _apply_session_updates(rs: ResearchSession, updates: Mapping[str, Any]) -> None:
        if "cycle_name" in updates:
            rs.cycle_name = str(updates["cycle_name"])
        if "description" in updates:
            rs.description = str(updates["description"])
        if "status" in updates:
            rs.status = _to_session_status(updates["status"])
        if "current_phase" in updates:
            rs.current_phase = str(updates["current_phase"])
        if "research_objective" in updates:
            rs.research_objective = str(updates["research_objective"])
        if "research_scope" in updates:
            rs.research_scope = str(updates["research_scope"])
        if "target_audience" in updates:
            rs.target_audience = str(updates["target_audience"])
        if "researchers" in updates:
            rs.researchers_json = _json_dumps(updates["researchers"], "[]")
        if "advisors" in updates:
            rs.advisors_json = _json_dumps(updates["advisors"], "[]")
        if "resources" in updates:
            rs.resources_json = _json_dumps(updates["resources"], "{}")
        if "budget" in updates:
            rs.budget = float(updates["budget"])
        if "timeline" in updates:
            rs.timeline_json = _json_dumps(updates["timeline"], "{}")
        if "quality_metrics" in updates:
            rs.quality_metrics_json = _json_dumps(updates["quality_metrics"], "{}")
        if "risk_assessment" in updates:
            rs.risk_assessment_json = _json_dumps(updates["risk_assessment"], "{}")
        if "expert_reviews" in updates:
            rs.expert_reviews_json = _json_dumps(updates["expert_reviews"], "[]")
        if "tags" in updates:
            rs.tags_json = _json_dumps(updates["tags"], "[]")
        if "categories" in updates:
            rs.categories_json = _json_dumps(updates["categories"], "[]")
        if "metadata" in updates:
            rs.metadata_json = _json_dumps(updates["metadata"], "{}")
        if "started_at" in updates:
            rs.started_at = _parse_datetime(updates["started_at"])
        if "completed_at" in updates:
            rs.completed_at = _parse_datetime(updates["completed_at"])
        if "duration" in updates:
            rs.duration = float(updates["duration"])
