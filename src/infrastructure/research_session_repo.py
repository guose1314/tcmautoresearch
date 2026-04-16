"""P3.1 ResearchSession 仓储层。

提供 ResearchSession / PhaseExecution / ResearchArtifact 的 CRUD 与查询方法，
并支持从 ResearchCycle dataclass 的双向转换。
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.collector.corpus_bundle import build_document_version_metadata
from src.infrastructure.persistence import (
    ArtifactTypeEnum,
    DatabaseManager,
    Document,
    Entity,
    EntityRelationship,
    EntityTypeEnum,
    PhaseExecution,
    PhaseStatusEnum,
    ProcessingLog,
    ProcessingStatistics,
    ProcessStatusEnum,
    QualityMetrics,
    RelationshipCategoryEnum,
    RelationshipType,
    ResearchAnalysis,
    ResearchArtifact,
    ResearchSession,
    SessionStatusEnum,
    _json_dumps,
    _json_loads,
)
from src.research.observe_philology import (
    OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT,
    build_observe_philology_artifact_payloads,
    normalize_observe_catalog_review_decision,
    resolve_observe_philology_assets,
    upsert_observe_catalog_review_artifact_content,
)
from src.research.review_workbench import (
    OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
    normalize_observe_review_workbench_decision,
    upsert_observe_review_workbench_artifact_content,
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


def _to_entity_type(value: Any) -> EntityTypeEnum:
    if isinstance(value, EntityTypeEnum):
        return value
    raw = str(getattr(value, "value", value)).strip().lower()
    try:
        return EntityTypeEnum(raw)
    except ValueError:
        return EntityTypeEnum.OTHER


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

    @contextmanager
    def _session_scope(self, session: Optional[Session] = None):
        if session is not None:
            yield session
            return
        with self._db.session_scope() as managed_session:
            yield managed_session

    # ---- 会话 CRUD -------------------------------------------------------

    def create_session(
        self,
        payload: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """创建研究会话，返回序列化字典。"""
        with self._session_scope(session) as db_session:
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
            db_session.add(rs)
            db_session.flush()
            return self._session_to_dict(rs)

    def get_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """按 cycle_id 查询，返回 None 表示不存在。"""
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            return self._session_to_dict(rs)

    def get_session_by_id(
        self,
        session_id: uuid.UUID,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """按主键 id 查询。"""
        with self._session_scope(session) as db_session:
            rs = db_session.get(ResearchSession, session_id)
            if rs is None:
                return None
            return self._session_to_dict(rs)

    def update_session(
        self,
        cycle_id: str,
        updates: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """部分更新会话字段，返回更新后的字典。"""
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None
            self._apply_session_updates(rs, updates)
            db_session.flush()
            return self._session_to_dict(rs)

    def delete_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> bool:
        """删除会话及其级联的阶段/工件记录。"""
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return False
            self._delete_observe_document_graphs(db_session, cycle_id)
            db_session.delete(rs)
            db_session.flush()
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

    def start_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {
            "status": "active",
            "started_at": datetime.utcnow().isoformat(),
        }, session=session)

    def complete_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
        }, session=session)

    def fail_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {"status": "failed"}, session=session)

    def suspend_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.update_session(cycle_id, {"status": "suspended"}, session=session)

    # ---- 阶段执行 CRUD ---------------------------------------------------

    def add_phase_execution(
        self,
        cycle_id: str,
        payload: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """为指定会话添加阶段执行记录。"""
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
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
            db_session.add(pe)
            db_session.flush()
            return self._phase_to_dict(pe)

    def update_phase_execution(
        self,
        phase_id: uuid.UUID,
        updates: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            pe = db_session.get(PhaseExecution, phase_id)
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
            db_session.flush()
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
        self,
        cycle_id: str,
        payload: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
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
            db_session.add(artifact)
            db_session.flush()
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

    def upsert_observe_catalog_review(
        self,
        cycle_id: str,
        payload: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None

            phase_execution = (
                db_session.query(PhaseExecution)
                .filter(
                    PhaseExecution.session_id == rs.id,
                    PhaseExecution.phase == "observe",
                )
                .order_by(PhaseExecution.created_at.desc())
                .first()
            )
            if phase_execution is None:
                return None

            normalized_decision = normalize_observe_catalog_review_decision(payload)
            if not normalized_decision:
                raise ValueError("无效的目录学 review 写回 payload")

            artifact = (
                db_session.query(ResearchArtifact)
                .filter(
                    ResearchArtifact.phase_execution_id == phase_execution.id,
                    ResearchArtifact.name == OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT,
                )
                .one_or_none()
            )
            existing_content = _json_loads(artifact.content_json, {}) if artifact is not None else {}
            content = upsert_observe_catalog_review_artifact_content(existing_content, normalized_decision)
            metadata = {
                "asset_kind": "catalog_review_decisions",
                "decision_count": int(content.get("decision_count") or 0),
                "last_reviewer": content.get("last_reviewer"),
                "updated_at": content.get("updated_at"),
            }
            size_bytes = self._estimate_artifact_size(content, None)

            if artifact is None:
                artifact = ResearchArtifact(
                    session_id=rs.id,
                    phase_execution_id=phase_execution.id,
                    artifact_type=ArtifactTypeEnum.ANALYSIS,
                    name=OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT,
                    description="Observe 阶段目录学校核写回记录",
                    content_json=_json_dumps(content, "{}"),
                    file_path=None,
                    mime_type="application/json",
                    size_bytes=size_bytes,
                    metadata_json=_json_dumps(metadata, "{}"),
                )
                db_session.add(artifact)
            else:
                artifact.artifact_type = ArtifactTypeEnum.ANALYSIS
                artifact.description = "Observe 阶段目录学校核写回记录"
                artifact.content_json = _json_dumps(content, "{}")
                artifact.mime_type = "application/json"
                artifact.size_bytes = size_bytes
                artifact.metadata_json = _json_dumps(metadata, "{}")

            db_session.flush()
            return self._artifact_to_dict(artifact)

    def upsert_observe_workbench_review(
        self,
        cycle_id: str,
        payload: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return None

            phase_execution = (
                db_session.query(PhaseExecution)
                .filter(
                    PhaseExecution.session_id == rs.id,
                    PhaseExecution.phase == "observe",
                )
                .order_by(PhaseExecution.created_at.desc())
                .first()
            )
            if phase_execution is None:
                return None

            normalized_decision = normalize_observe_review_workbench_decision(payload)
            if not normalized_decision:
                raise ValueError("无效的文献学 review 写回 payload")

            artifact = (
                db_session.query(ResearchArtifact)
                .filter(
                    ResearchArtifact.phase_execution_id == phase_execution.id,
                    ResearchArtifact.name == OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
                )
                .one_or_none()
            )
            existing_content = _json_loads(artifact.content_json, {}) if artifact is not None else {}
            content = upsert_observe_review_workbench_artifact_content(existing_content, normalized_decision)
            metadata = {
                "asset_kind": "review_workbench_decisions",
                "decision_count": int(content.get("decision_count") or 0),
                "last_reviewer": content.get("last_reviewer"),
                "updated_at": content.get("updated_at"),
            }
            size_bytes = self._estimate_artifact_size(content, None)

            if artifact is None:
                artifact = ResearchArtifact(
                    session_id=rs.id,
                    phase_execution_id=phase_execution.id,
                    artifact_type=ArtifactTypeEnum.ANALYSIS,
                    name=OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
                    description="Observe 阶段文献学工作台审核写回记录",
                    content_json=_json_dumps(content, "{}"),
                    file_path=None,
                    mime_type="application/json",
                    size_bytes=size_bytes,
                    metadata_json=_json_dumps(metadata, "{}"),
                )
                db_session.add(artifact)
            else:
                artifact.artifact_type = ArtifactTypeEnum.ANALYSIS
                artifact.description = "Observe 阶段文献学工作台审核写回记录"
                artifact.content_json = _json_dumps(content, "{}")
                artifact.mime_type = "application/json"
                artifact.size_bytes = size_bytes
                artifact.metadata_json = _json_dumps(metadata, "{}")

            db_session.flush()
            return self._artifact_to_dict(artifact)

    # ---- Observe 文档图谱 CRUD ------------------------------------------

    def replace_observe_document_graphs(
        self,
        cycle_id: str,
        phase_execution_id: Optional[str],
        payloads: Sequence[Mapping[str, Any]],
        *,
        session: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = db_session.query(ResearchSession).filter_by(cycle_id=cycle_id).one_or_none()
            if rs is None:
                return []

            DatabaseManager.create_default_relationships(db_session)
            self._delete_observe_document_graphs(db_session, cycle_id)
            relationship_type_cache = self._relationship_type_cache(db_session)
            snapshots: List[Dict[str, Any]] = []

            for document_index, payload in enumerate(payloads):
                if not isinstance(payload, Mapping):
                    continue
                document = self._create_observe_document(
                    db_session,
                    rs,
                    cycle_id,
                    phase_execution_id,
                    document_index,
                    payload,
                )
                entities = self._persist_observe_entities(
                    db_session,
                    document,
                    cycle_id,
                    phase_execution_id,
                    payload,
                )
                relationships = self._persist_observe_relationships(
                    db_session,
                    relationship_type_cache,
                    document,
                    cycle_id,
                    phase_execution_id,
                    payload,
                    entities,
                )
                document.entities_extracted_count = len(entities)
                document.process_status = ProcessStatusEnum.COMPLETED
                quality_metrics = ((payload.get("output_generation") or {}) if isinstance(payload.get("output_generation"), dict) else {}).get("quality_metrics") or {}
                document.quality_score = float(
                    (quality_metrics.get("confidence_score") if isinstance(quality_metrics, dict) else 0.0)
                    or payload.get("average_confidence")
                    or document.quality_score
                    or 0.0
                )
                db_session.flush()
                snapshots.append(self._observe_document_to_dict(document, entities, relationships))

            return snapshots

    def list_observe_document_graphs(self, cycle_id: str) -> List[Dict[str, Any]]:
        with self._db.session_scope() as session:
            return self._list_observe_document_graphs(session, cycle_id)

    def list_observe_version_lineages(self, cycle_id: str) -> List[Dict[str, Any]]:
        with self._db.session_scope() as session:
            documents = self._list_observe_document_graphs(session, cycle_id)
            return self._group_observe_version_lineages(documents)

    def backfill_observe_document_version_metadata(
        self,
        cycle_id: Optional[str] = None,
        *,
        batch_size: int = 500,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        with self._session_scope(session) as db_session:
            query = (
                self._observe_document_query(db_session, cycle_id)
                .order_by(Document.processing_timestamp.asc(), Document.created_at.asc())
            )
            effective_batch_size = max(int(batch_size or 0), 1)
            scanned_document_count = 0
            updated_document_count = 0

            for document in query.yield_per(effective_batch_size):
                scanned_document_count += 1
                if self._writeback_observe_document_version_metadata(document):
                    updated_document_count += 1

            db_session.flush()
            return {
                "cycle_id": cycle_id,
                "batch_size": effective_batch_size,
                "scanned_document_count": scanned_document_count,
                "updated_document_count": updated_document_count,
                "skipped_document_count": scanned_document_count - updated_document_count,
            }

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
            result["observe_documents"] = self._list_observe_document_graphs(session, cycle_id)
            result["version_lineages"] = self._group_observe_version_lineages(result["observe_documents"])
            result["observe_philology"] = resolve_observe_philology_assets(
                artifacts=result["artifacts"],
                observe_phase_result=self._phase_output_by_name(result["phase_executions"], "observe"),
                observe_documents=result["observe_documents"],
            )
            return result

    def backfill_observe_philology_artifacts(
        self,
        cycle_id: Optional[str] = None,
        *,
        batch_size: int = 200,
        artifact_output: Optional[Mapping[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        with self._session_scope(session) as db_session:
            query = (
                db_session.query(PhaseExecution, ResearchSession.cycle_id)
                .join(ResearchSession, PhaseExecution.session_id == ResearchSession.id)
                .filter(PhaseExecution.phase == "observe")
                .order_by(PhaseExecution.created_at.asc())
            )
            if cycle_id:
                query = query.filter(ResearchSession.cycle_id == cycle_id)

            effective_batch_size = max(int(batch_size or 0), 1)
            scanned_phase_count = 0
            updated_phase_count = 0
            created_artifact_count = 0
            observe_documents_cache: Dict[str, List[Dict[str, Any]]] = {}

            for phase_execution, phase_cycle_id in query.yield_per(effective_batch_size):
                scanned_phase_count += 1
                normalized_cycle_id = str(phase_cycle_id or "").strip()
                if not normalized_cycle_id:
                    continue

                existing_artifacts = (
                    db_session.query(ResearchArtifact)
                    .filter(ResearchArtifact.phase_execution_id == phase_execution.id)
                    .order_by(ResearchArtifact.created_at.asc())
                    .all()
                )
                existing_artifact_records = [self._artifact_to_dict(artifact) for artifact in existing_artifacts]
                existing_artifact_names = {
                    str(record.get("name") or "").strip()
                    for record in existing_artifact_records
                    if str(record.get("name") or "").strip()
                }

                if normalized_cycle_id not in observe_documents_cache:
                    observe_documents_cache[normalized_cycle_id] = self._list_observe_document_graphs(
                        db_session,
                        normalized_cycle_id,
                    )

                observe_philology = resolve_observe_philology_assets(
                    artifacts=existing_artifact_records,
                    observe_phase_result=_json_loads(phase_execution.output_json, {}),
                    observe_documents=observe_documents_cache[normalized_cycle_id],
                )
                artifact_payloads = [
                    payload
                    for payload in build_observe_philology_artifact_payloads(observe_philology, artifact_output)
                    if str(payload.get("name") or "").strip() not in existing_artifact_names
                ]
                if not artifact_payloads:
                    continue

                for payload in artifact_payloads:
                    saved = self.add_artifact(
                        normalized_cycle_id,
                        {
                            **dict(payload),
                            "phase_execution_id": str(phase_execution.id),
                            "size_bytes": self._estimate_artifact_size(
                                payload.get("content"),
                                payload.get("file_path"),
                            ),
                        },
                        session=db_session,
                    )
                    if isinstance(saved, dict):
                        created_artifact_count += 1
                updated_phase_count += 1

            db_session.flush()
            return {
                "cycle_id": cycle_id,
                "batch_size": effective_batch_size,
                "scanned_phase_count": scanned_phase_count,
                "updated_phase_count": updated_phase_count,
                "created_artifact_count": created_artifact_count,
                "skipped_phase_count": scanned_phase_count - updated_phase_count,
            }

    # ---- ResearchCycle dataclass 互转 ------------------------------------

    def save_from_cycle(
        self,
        cycle: Any,
        *,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
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
        existing = self.get_session(cycle.cycle_id, session=session)
        if existing:
            return self.update_session(cycle.cycle_id, payload, session=session)  # type: ignore[return-value]
        return self.create_session(payload, session=session)

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
    def _phase_output_by_name(
        phase_executions: Sequence[Mapping[str, Any]],
        phase_name: str,
    ) -> Dict[str, Any]:
        normalized_phase_name = str(phase_name or "").strip().lower()
        for phase_execution in phase_executions:
            if not isinstance(phase_execution, Mapping):
                continue
            current_phase = str(phase_execution.get("phase") or "").strip().lower()
            if current_phase != normalized_phase_name:
                continue
            return dict(phase_execution.get("output") or {}) if isinstance(phase_execution.get("output"), Mapping) else {}
        return {}

    @staticmethod
    def _estimate_artifact_size(content: Any, file_path: Any = None) -> int:
        file_path_text = str(file_path or "").strip()
        if file_path_text:
            return 0
        if content in (None, "", [], {}):
            return 0
        return len(_json_dumps(content, "{}").encode("utf-8"))

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

    @staticmethod
    def _entity_to_dict(entity: Entity) -> Dict[str, Any]:
        return {
            "id": str(entity.id),
            "document_id": str(entity.document_id),
            "name": entity.name,
            "type": entity.type.value if isinstance(entity.type, EntityTypeEnum) else str(entity.type),
            "confidence": entity.confidence,
            "position": entity.position,
            "length": entity.length,
            "alternative_names": list(entity.alternative_names or []),
            "description": entity.description or "",
            "entity_metadata": dict(entity.entity_metadata or {}),
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    @staticmethod
    def _relationship_to_dict(relationship: EntityRelationship) -> Dict[str, Any]:
        source_entity = relationship.source_entity
        target_entity = relationship.target_entity
        source_metadata = dict(getattr(source_entity, "entity_metadata", {}) or {}) if source_entity is not None else {}
        target_metadata = dict(getattr(target_entity, "entity_metadata", {}) or {}) if target_entity is not None else {}
        return {
            "id": str(relationship.id),
            "source_entity_id": str(relationship.source_entity_id),
            "target_entity_id": str(relationship.target_entity_id),
            "source_entity_name": getattr(source_entity, "name", "") if source_entity is not None else "",
            "target_entity_name": getattr(target_entity, "name", "") if target_entity is not None else "",
            "source_entity_type": str(source_metadata.get("raw_type") or getattr(getattr(source_entity, "type", None), "value", getattr(source_entity, "type", "other")) or "other"),
            "target_entity_type": str(target_metadata.get("raw_type") or getattr(getattr(target_entity, "type", None), "value", getattr(target_entity, "type", "other")) or "other"),
            "relationship_type": relationship.type.relationship_type if relationship.type else None,
            "relationship_name": relationship.type.relationship_name if relationship.type else None,
            "confidence": relationship.confidence,
            "created_by_module": relationship.created_by_module,
            "evidence": relationship.evidence,
            "relationship_metadata": dict(relationship.relationship_metadata or {}),
            "created_at": relationship.created_at.isoformat() if relationship.created_at else None,
        }

    # ---- 内部 ------------------------------------------------------------

    @staticmethod
    def _observe_document_source_prefix(cycle_id: str) -> str:
        return f"research://{cycle_id}/observe/"

    @staticmethod
    def _observe_document_source_file(cycle_id: str, document_index: int, payload: Mapping[str, Any]) -> str:
        source_ref = str(payload.get("urn") or payload.get("title") or f"document_{document_index + 1}").strip()
        stable_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{cycle_id}:observe:{document_index}:{source_ref}")
        return f"{ResearchSessionRepository._observe_document_source_prefix(cycle_id)}{stable_id}"

    @staticmethod
    def _build_observe_document_notes(
        cycle_id: str,
        phase_execution_id: Optional[str],
        document_index: int,
        payload: Mapping[str, Any],
        *,
        source_type: str,
        document_metadata: Mapping[str, Any],
        version_metadata: Mapping[str, Any],
    ) -> str:
        note_payload = {
            "cycle_id": cycle_id,
            "phase": "observe",
            "phase_execution_id": str(phase_execution_id or "").strip() or None,
            "document_index": document_index,
            "urn": str(payload.get("urn") or "").strip(),
            "title": str(payload.get("title") or "").strip(),
            "source_type": source_type,
            "catalog_id": str(version_metadata.get("catalog_id") or document_metadata.get("catalog_id") or "").strip(),
            "raw_text_preview": str(payload.get("raw_text_preview") or "")[:240],
            "processed_text_preview": str(payload.get("processed_text_preview") or "")[:240],
            "processed_text_size": int(payload.get("processed_text_size") or 0),
            "metadata": dict(document_metadata or {}),
            "version_metadata": dict(version_metadata or {}),
            "philology": payload.get("philology") if isinstance(payload.get("philology"), dict) else {},
            "philology_notes": [
                str(note)
                for note in (payload.get("philology_notes") or [])
                if str(note).strip()
            ] if isinstance(payload.get("philology_notes"), list) else [],
            "philology_assets": payload.get("philology_assets") if isinstance(payload.get("philology_assets"), dict) else {},
            "output_generation": payload.get("output_generation") if isinstance(payload.get("output_generation"), dict) else {},
        }
        return _json_dumps(note_payload, "{}")

    @staticmethod
    def _parse_observe_document_notes(notes: Optional[str]) -> Dict[str, Any]:
        parsed = _json_loads(notes, {})
        return parsed if isinstance(parsed, dict) else {}

    def _create_observe_document(
        self,
        session: Session,
        research_session: ResearchSession,
        cycle_id: str,
        phase_execution_id: Optional[str],
        document_index: int,
        payload: Mapping[str, Any],
    ) -> Document:
        document_metadata = self._extract_observe_document_metadata(payload)
        version_metadata = self._extract_observe_document_version_metadata(payload, document_metadata)
        document_metadata["version_metadata"] = version_metadata
        source_type = str(
            payload.get("source_type")
            or document_metadata.get("source_type")
            or version_metadata.get("source_type")
            or "observe"
        ).strip() or "observe"
        document = Document(
            source_file=self._observe_document_source_file(cycle_id, document_index, payload),
            document_urn=str(payload.get("urn") or "").strip() or None,
            document_title=str(payload.get("title") or "").strip() or None,
            source_type=source_type or None,
            catalog_id=str(version_metadata.get("catalog_id") or "").strip() or None,
            work_title=str(version_metadata.get("work_title") or "").strip() or None,
            fragment_title=str(version_metadata.get("fragment_title") or "").strip() or None,
            work_fragment_key=str(version_metadata.get("work_fragment_key") or "").strip() or None,
            version_lineage_key=str(version_metadata.get("version_lineage_key") or "").strip() or None,
            witness_key=str(version_metadata.get("witness_key") or "").strip() or None,
            dynasty=str(version_metadata.get("dynasty") or "").strip() or None,
            author=str(version_metadata.get("author") or "").strip() or None,
            edition=str(version_metadata.get("edition") or "").strip() or None,
            version_metadata_json=version_metadata,
            processing_timestamp=_parse_datetime(payload.get("processing_timestamp")) or datetime.utcnow(),
            objective=research_session.research_objective or research_session.description or None,
            raw_text_size=int(payload.get("raw_text_size") or 0),
            entities_extracted_count=int(payload.get("entity_count") or 0),
            process_status=ProcessStatusEnum.COMPLETED,
            quality_score=0.0,
            notes=self._build_observe_document_notes(
                cycle_id,
                phase_execution_id,
                document_index,
                payload,
                source_type=source_type,
                document_metadata=document_metadata,
                version_metadata=version_metadata,
            ),
        )
        session.add(document)
        session.flush()
        return document

    @staticmethod
    def _extract_observe_document_metadata(payload: Mapping[str, Any]) -> Dict[str, Any]:
        metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {}
        version_metadata = payload.get("version_metadata") if isinstance(payload.get("version_metadata"), Mapping) else {}
        if version_metadata and not isinstance(metadata.get("version_metadata"), dict):
            metadata["version_metadata"] = dict(version_metadata)
        return metadata

    def _extract_observe_document_version_metadata(
        self,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> Dict[str, Any]:
        existing_version_metadata = metadata.get("version_metadata") if isinstance(metadata.get("version_metadata"), Mapping) else {}
        source_type = str(payload.get("source_type") or metadata.get("source_type") or "observe").strip() or "observe"
        source_ref = str(payload.get("urn") or metadata.get("source_file") or payload.get("title") or "observe").strip()
        enriched_metadata = build_document_version_metadata(
            title=str(payload.get("title") or "").strip(),
            source_type=source_type,
            source_ref=source_ref,
            metadata={
                **dict(metadata),
                "version_metadata": dict(existing_version_metadata or {}),
                "catalog_id": metadata.get("catalog_id") or existing_version_metadata.get("catalog_id"),
            },
        )
        return dict(enriched_metadata.get("version_metadata") or {})

    def _persist_observe_entities(
        self,
        session: Session,
        document: Document,
        cycle_id: str,
        phase_execution_id: Optional[str],
        payload: Mapping[str, Any],
    ) -> List[Entity]:
        document_notes = self._parse_observe_document_notes(document.notes)
        entities: List[Entity] = []
        for entity_payload in payload.get("entities") or []:
            if not isinstance(entity_payload, Mapping):
                continue
            name = str(entity_payload.get("name") or "").strip()
            if not name:
                continue
            raw_type = str(entity_payload.get("type") or entity_payload.get("entity_type") or "other").strip().lower()
            metadata = dict(entity_payload.get("metadata") or entity_payload.get("entity_metadata") or {})
            metadata.update(
                {
                    "cycle_id": cycle_id,
                    "phase": "observe",
                    "phase_execution_id": str(phase_execution_id or "").strip() or None,
                    "document_urn": document_notes.get("urn"),
                    "document_title": document_notes.get("title"),
                    "document_index": document_notes.get("document_index"),
                    "raw_type": raw_type or "other",
                }
            )
            entity = Entity(
                document_id=document.id,
                name=name,
                type=_to_entity_type(raw_type),
                confidence=float(entity_payload.get("confidence") or 0.5),
                position=int(entity_payload.get("position") or 0),
                length=int(entity_payload.get("length") or len(name)),
                alternative_names=list(entity_payload.get("alternative_names") or entity_payload.get("aliases") or []),
                description=str(entity_payload.get("description") or "").strip() or None,
                entity_metadata=metadata,
            )
            session.add(entity)
            entities.append(entity)
        session.flush()
        return entities

    def _persist_observe_relationships(
        self,
        session: Session,
        relationship_type_cache: Dict[str, Dict[str, Any]],
        document: Document,
        cycle_id: str,
        phase_execution_id: Optional[str],
        payload: Mapping[str, Any],
        entities: Sequence[Entity],
    ) -> List[EntityRelationship]:
        document_notes = self._parse_observe_document_notes(document.notes)
        entity_lookup = self._build_observe_entity_lookup(entities)
        relationships: List[EntityRelationship] = []
        for relationship_payload in payload.get("semantic_relationships") or []:
            if not isinstance(relationship_payload, Mapping):
                continue
            source_entity = self._resolve_observe_entity(relationship_payload, entity_lookup, "source")
            target_entity = self._resolve_observe_entity(relationship_payload, entity_lookup, "target")
            if source_entity is None or target_entity is None:
                continue
            relationship_type = self._resolve_relationship_type(
                session,
                relationship_type_cache,
                str(
                    relationship_payload.get("relationship_type")
                    or relationship_payload.get("type")
                    or relationship_payload.get("relationship_name")
                    or ""
                ).strip(),
            )
            relationship_metadata = dict(relationship_payload.get("metadata") or relationship_payload.get("relationship_metadata") or {})
            relationship_metadata.update(
                {
                    "cycle_id": cycle_id,
                    "phase": "observe",
                    "phase_execution_id": str(phase_execution_id or "").strip() or None,
                    "document_id": str(document.id),
                    "document_urn": document_notes.get("urn"),
                    "document_title": document_notes.get("title"),
                    "source_type": str(relationship_payload.get("source_type") or self._entity_raw_type(source_entity) or "entity"),
                    "target_type": str(relationship_payload.get("target_type") or self._entity_raw_type(target_entity) or "entity"),
                }
            )
            relationship = EntityRelationship(
                source_entity_id=source_entity.id,
                target_entity_id=target_entity.id,
                relationship_type_id=relationship_type["id"],
                confidence=float(relationship_payload.get("confidence") or relationship_metadata.get("confidence") or 0.5),
                created_by_module=str(relationship_payload.get("created_by_module") or relationship_metadata.get("source") or "observe_phase").strip() or None,
                evidence=str(relationship_payload.get("evidence") or relationship_metadata.get("description") or "").strip() or None,
                relationship_metadata=relationship_metadata,
            )
            session.add(relationship)
            relationships.append(relationship)
        session.flush()
        return relationships

    def _list_observe_document_graphs(self, session: Session, cycle_id: str) -> List[Dict[str, Any]]:
        documents = (
            self._observe_document_query(session, cycle_id)
            .order_by(Document.processing_timestamp.asc(), Document.created_at.asc())
            .all()
        )
        snapshots: List[Dict[str, Any]] = []
        for document in documents:
            entities = session.query(Entity).filter_by(document_id=document.id).order_by(Entity.created_at.asc()).all()
            entity_ids = [entity.id for entity in entities]
            relationships: List[EntityRelationship] = []
            if entity_ids:
                relationships = (
                    session.query(EntityRelationship)
                    .filter(EntityRelationship.source_entity_id.in_(entity_ids))
                    .order_by(EntityRelationship.created_at.asc())
                    .all()
                )
            snapshots.append(self._observe_document_to_dict(document, entities, relationships))
        return snapshots

    def _observe_document_to_dict(
        self,
        document: Document,
        entities: Sequence[Entity],
        relationships: Sequence[EntityRelationship],
    ) -> Dict[str, Any]:
        notes = self._parse_observe_document_notes(document.notes)
        version_metadata = self._document_version_metadata(document, notes)
        metadata = dict(notes.get("metadata") or {}) if isinstance(notes.get("metadata"), dict) else {}
        metadata["version_metadata"] = version_metadata
        if document.source_type and not metadata.get("source_type"):
            metadata["source_type"] = document.source_type
        if document.catalog_id and not metadata.get("catalog_id"):
            metadata["catalog_id"] = document.catalog_id
        entity_dicts = [self._entity_to_dict(entity) for entity in entities]
        relationship_dicts = [self._relationship_to_dict(relationship) for relationship in relationships]
        return {
            "id": str(document.id),
            "source_file": document.source_file,
            "processing_timestamp": document.processing_timestamp.isoformat() if document.processing_timestamp else None,
            "objective": document.objective,
            "raw_text_size": document.raw_text_size,
            "entities_extracted_count": document.entities_extracted_count,
            "process_status": document.process_status.value if isinstance(document.process_status, ProcessStatusEnum) else str(document.process_status),
            "quality_score": document.quality_score,
            "cycle_id": notes.get("cycle_id"),
            "phase": notes.get("phase"),
            "phase_execution_id": notes.get("phase_execution_id"),
            "document_index": notes.get("document_index"),
            "urn": document.document_urn or notes.get("urn"),
            "title": document.document_title or notes.get("title"),
            "source_type": document.source_type or notes.get("source_type") or version_metadata.get("source_type"),
            "catalog_id": document.catalog_id or notes.get("catalog_id") or version_metadata.get("catalog_id"),
            "work_title": document.work_title or version_metadata.get("work_title"),
            "fragment_title": document.fragment_title or version_metadata.get("fragment_title"),
            "work_fragment_key": document.work_fragment_key or version_metadata.get("work_fragment_key"),
            "version_lineage_key": document.version_lineage_key or version_metadata.get("version_lineage_key"),
            "witness_key": document.witness_key or version_metadata.get("witness_key"),
            "dynasty": document.dynasty or version_metadata.get("dynasty"),
            "author": document.author or version_metadata.get("author"),
            "edition": document.edition or version_metadata.get("edition"),
            "raw_text_preview": notes.get("raw_text_preview"),
            "processed_text_preview": notes.get("processed_text_preview"),
            "processed_text_size": notes.get("processed_text_size"),
            "metadata": metadata,
            "version_metadata": version_metadata,
            "philology": notes.get("philology") if isinstance(notes.get("philology"), dict) else {},
            "philology_notes": notes.get("philology_notes") if isinstance(notes.get("philology_notes"), list) else [],
            "philology_assets": notes.get("philology_assets") if isinstance(notes.get("philology_assets"), dict) else {},
            "output_generation": notes.get("output_generation") if isinstance(notes.get("output_generation"), dict) else {},
            "entities": entity_dicts,
            "semantic_relationships": relationship_dicts,
            "entity_count": len(entity_dicts),
            "relationship_count": len(relationship_dicts),
        }

    def _writeback_observe_document_version_metadata(self, document: Document) -> bool:
        notes = self._parse_observe_document_notes(document.notes)
        version_metadata = self._document_version_metadata(document, notes)

        document_urn = str(
            document.document_urn
            or notes.get("urn")
            or version_metadata.get("source_ref")
            or ""
        ).strip() or None
        document_title = str(
            document.document_title
            or notes.get("title")
            or version_metadata.get("fragment_title")
            or version_metadata.get("work_title")
            or ""
        ).strip() or None
        source_type = str(
            document.source_type
            or notes.get("source_type")
            or version_metadata.get("source_type")
            or self._infer_legacy_observe_source_type(document_urn or document.source_file)
            or "observe"
        ).strip() or None

        updated = False
        updated |= self._assign_if_changed(document, "document_urn", document_urn)
        updated |= self._assign_if_changed(document, "document_title", document_title)
        updated |= self._assign_if_changed(document, "source_type", source_type)
        updated |= self._assign_if_changed(document, "catalog_id", self._optional_version_value(version_metadata, "catalog_id"))
        updated |= self._assign_if_changed(document, "work_title", self._optional_version_value(version_metadata, "work_title"))
        updated |= self._assign_if_changed(document, "fragment_title", self._optional_version_value(version_metadata, "fragment_title"))
        updated |= self._assign_if_changed(document, "work_fragment_key", self._optional_version_value(version_metadata, "work_fragment_key"))
        updated |= self._assign_if_changed(document, "version_lineage_key", self._optional_version_value(version_metadata, "version_lineage_key"))
        updated |= self._assign_if_changed(document, "witness_key", self._optional_version_value(version_metadata, "witness_key"))
        updated |= self._assign_if_changed(document, "dynasty", self._optional_version_value(version_metadata, "dynasty"))
        updated |= self._assign_if_changed(document, "author", self._optional_version_value(version_metadata, "author"))
        updated |= self._assign_if_changed(document, "edition", self._optional_version_value(version_metadata, "edition"))
        updated |= self._assign_if_changed(document, "version_metadata_json", dict(version_metadata))

        note_payload = dict(notes)
        if document_urn:
            note_payload["urn"] = document_urn
        if document_title:
            note_payload["title"] = document_title
        if source_type:
            note_payload["source_type"] = source_type
        catalog_id = str(version_metadata.get("catalog_id") or "").strip()
        if catalog_id:
            note_payload["catalog_id"] = catalog_id

        note_metadata = dict(note_payload.get("metadata") or {}) if isinstance(note_payload.get("metadata"), dict) else {}
        if source_type:
            note_metadata["source_type"] = source_type
        if catalog_id:
            note_metadata["catalog_id"] = catalog_id
        note_metadata["version_metadata"] = dict(version_metadata)
        note_payload["metadata"] = note_metadata
        note_payload["version_metadata"] = dict(version_metadata)

        serialized_notes = _json_dumps(note_payload, "{}")
        if document.notes != serialized_notes:
            document.notes = serialized_notes
            updated = True
        return updated

    @staticmethod
    def _assign_if_changed(document: Document, field_name: str, value: Any) -> bool:
        if getattr(document, field_name) == value:
            return False
        setattr(document, field_name, value)
        return True

    @staticmethod
    def _optional_version_value(version_metadata: Mapping[str, Any], key: str) -> Optional[str]:
        value = str(version_metadata.get(key) or "").strip()
        return value or None

    @staticmethod
    def _document_version_metadata(document: Document, notes: Mapping[str, Any]) -> Dict[str, Any]:
        version_metadata = dict(document.version_metadata_json or {})
        note_version_metadata = notes.get("version_metadata") if isinstance(notes.get("version_metadata"), dict) else {}
        if not version_metadata and note_version_metadata:
            version_metadata = dict(note_version_metadata)

        note_metadata = dict(notes.get("metadata") or {}) if isinstance(notes.get("metadata"), dict) else {}
        if note_version_metadata:
            note_metadata["version_metadata"] = {
                **dict(note_metadata.get("version_metadata") or {}),
                **note_version_metadata,
                **version_metadata,
            }

        column_mapping = {
            "source_ref": document.document_urn,
            "source_type": document.source_type,
            "catalog_id": document.catalog_id,
            "work_title": document.work_title,
            "fragment_title": document.fragment_title,
            "work_fragment_key": document.work_fragment_key,
            "version_lineage_key": document.version_lineage_key,
            "witness_key": document.witness_key,
            "dynasty": document.dynasty,
            "author": document.author,
            "edition": document.edition,
        }
        for key, value in column_mapping.items():
            if value not in (None, ""):
                version_metadata[key] = value

        source_ref = str(
            version_metadata.get("source_ref")
            or document.document_urn
            or notes.get("urn")
            or document.source_file
            or ""
        ).strip()
        source_type = str(
            version_metadata.get("source_type")
            or document.source_type
            or notes.get("source_type")
            or ResearchSessionRepository._infer_legacy_observe_source_type(source_ref)
            or "observe"
        ).strip() or "observe"
        title = str(
            version_metadata.get("fragment_title")
            or document.document_title
            or notes.get("title")
            or ""
        ).strip()
        catalog_id = str(version_metadata.get("catalog_id") or notes.get("catalog_id") or note_metadata.get("catalog_id") or "").strip()
        if catalog_id:
            note_metadata["catalog_id"] = catalog_id

        normalized_metadata = build_document_version_metadata(
            title=title,
            source_type=source_type,
            source_ref=source_ref or title or document.source_file,
            metadata={
                **note_metadata,
                "version_metadata": version_metadata,
            },
        )
        return dict(normalized_metadata.get("version_metadata") or version_metadata)

    @staticmethod
    def _infer_legacy_observe_source_type(source_ref: str) -> str:
        normalized = str(source_ref or "").strip().lower()
        if not normalized:
            return "observe"
        if normalized.startswith("ctp:") or "ctext.org" in normalized:
            return "ctext"
        if normalized.endswith(".pdf"):
            return "pdf"
        if normalized.endswith((".txt", ".md", ".markdown", ".json", ".xml", ".html", ".htm")):
            return "local"
        if "\\" in normalized or "/" in normalized:
            return "local"
        return "observe"

    @staticmethod
    def _group_observe_version_lineages(documents: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        seen_witnesses: set[tuple[str, str]] = set()

        for document in documents:
            if not isinstance(document, Mapping):
                continue
            version_metadata = document.get("version_metadata") if isinstance(document.get("version_metadata"), Mapping) else {}
            lineage_key = str(
                version_metadata.get("version_lineage_key")
                or version_metadata.get("work_fragment_key")
                or version_metadata.get("witness_key")
                or document.get("id")
                or ""
            ).strip()
            if not lineage_key:
                continue

            witness_key = str(version_metadata.get("witness_key") or document.get("id") or document.get("urn") or "").strip()
            if witness_key:
                seen_key = (lineage_key, witness_key)
                if seen_key in seen_witnesses:
                    continue
                seen_witnesses.add(seen_key)

            group = grouped.setdefault(
                lineage_key,
                {
                    "cycle_id": document.get("cycle_id"),
                    "version_lineage_key": str(version_metadata.get("version_lineage_key") or lineage_key).strip(),
                    "work_fragment_key": str(version_metadata.get("work_fragment_key") or "").strip(),
                    "work_title": str(version_metadata.get("work_title") or document.get("work_title") or "").strip(),
                    "fragment_title": str(version_metadata.get("fragment_title") or document.get("fragment_title") or "").strip(),
                    "dynasty": str(version_metadata.get("dynasty") or document.get("dynasty") or "").strip(),
                    "author": str(version_metadata.get("author") or document.get("author") or "").strip(),
                    "edition": str(version_metadata.get("edition") or document.get("edition") or "").strip(),
                    "witnesses": [],
                },
            )
            group["witnesses"].append(
                {
                    "document_id": document.get("id"),
                    "urn": document.get("urn"),
                    "title": document.get("title"),
                    "source_type": document.get("source_type"),
                    "catalog_id": version_metadata.get("catalog_id") or document.get("catalog_id"),
                    "witness_key": witness_key,
                    "dynasty": version_metadata.get("dynasty") or document.get("dynasty"),
                    "author": version_metadata.get("author") or document.get("author"),
                    "edition": version_metadata.get("edition") or document.get("edition"),
                }
            )

        ordered = sorted(grouped.values(), key=lambda item: str(item.get("version_lineage_key") or item.get("work_fragment_key") or ""))
        for item in ordered:
            item["witness_count"] = len(item.get("witnesses") or [])
        return ordered

    @classmethod
    def _observe_document_query(
        cls,
        session: Session,
        cycle_id: Optional[str] = None,
    ):
        source_pattern = f"{cls._observe_document_source_prefix(cycle_id)}%" if cycle_id else "research://%/observe/%"
        return session.query(Document).filter(Document.source_file.like(source_pattern))

    def _delete_observe_document_graphs(self, session: Session, cycle_id: str) -> None:
        document_ids = [row[0] for row in self._observe_document_query(session, cycle_id).with_entities(Document.id).all()]
        if not document_ids:
            return

        entity_ids = [row[0] for row in session.query(Entity.id).filter(Entity.document_id.in_(document_ids)).all()]
        if entity_ids:
            session.query(EntityRelationship).filter(
                (EntityRelationship.source_entity_id.in_(entity_ids))
                | (EntityRelationship.target_entity_id.in_(entity_ids))
            ).delete(synchronize_session=False)
        session.query(Entity).filter(Entity.document_id.in_(document_ids)).delete(synchronize_session=False)
        session.query(ProcessingLog).filter(ProcessingLog.document_id.in_(document_ids)).delete(synchronize_session=False)
        session.query(ProcessingStatistics).filter(ProcessingStatistics.document_id.in_(document_ids)).delete(synchronize_session=False)
        session.query(QualityMetrics).filter(QualityMetrics.document_id.in_(document_ids)).delete(synchronize_session=False)
        session.query(ResearchAnalysis).filter(ResearchAnalysis.document_id.in_(document_ids)).delete(synchronize_session=False)
        session.query(Document).filter(Document.id.in_(document_ids)).delete(synchronize_session=False)
        session.flush()

    def _relationship_type_cache(self, session: Session) -> Dict[str, Dict[str, Any]]:
        cache: Dict[str, Dict[str, Any]] = {}
        rows = session.execute(
            text(
                """
                SELECT id, relationship_name, relationship_type
                FROM relationship_types
                """
            )
        ).fetchall()
        for row in rows:
            entry = {
                "id": row[0],
                "relationship_name": str(row[1] or "").strip(),
                "relationship_type": str(row[2] or "").strip(),
            }
            if entry["relationship_type"]:
                cache[entry["relationship_type"].upper()] = entry
            if entry["relationship_name"]:
                cache[entry["relationship_name"]] = entry
        return cache

    def _resolve_relationship_type(
        self,
        session: Session,
        cache: Dict[str, Dict[str, Any]],
        raw_value: str,
    ) -> Dict[str, Any]:
        normalized = raw_value.strip()
        if not normalized:
            normalized = "RELATED"
        cached = cache.get(normalized) or cache.get(normalized.upper())
        if cached is not None:
            return cached
        relationship_type = RelationshipType(
            relationship_name=normalized,
            relationship_type=normalized.upper().replace(" ", "_"),
            description=f"自定义关系: {normalized}",
            category=None,
            confidence_baseline=0.5,
        )
        session.add(relationship_type)
        session.flush()
        entry = {
            "id": relationship_type.id,
            "relationship_name": relationship_type.relationship_name,
            "relationship_type": relationship_type.relationship_type,
        }
        cache[normalized] = entry
        cache[relationship_type.relationship_type] = entry
        return entry

    def _build_observe_entity_lookup(self, entities: Sequence[Entity]) -> Dict[str, Entity]:
        lookup: Dict[str, Entity] = {}
        for entity in entities:
            lookup[str(entity.id)] = entity
            if entity.name not in lookup:
                lookup[entity.name] = entity
            raw_type = self._entity_raw_type(entity)
            if raw_type:
                lookup[f"{entity.name}::{raw_type.lower()}"] = entity
        return lookup

    def _resolve_observe_entity(
        self,
        payload: Mapping[str, Any],
        lookup: Mapping[str, Entity],
        prefix: str,
    ) -> Optional[Entity]:
        direct_id = str(payload.get(f"{prefix}_entity_id") or payload.get(f"{prefix}_id") or "").strip()
        if direct_id and direct_id in lookup:
            return lookup[direct_id]
        entity_name = str(
            payload.get(f"{prefix}_entity_name")
            or payload.get(f"{prefix}_name")
            or payload.get(prefix)
            or ""
        ).strip()
        entity_type = str(payload.get(f"{prefix}_type") or "").strip().lower()
        if entity_name and entity_type:
            typed_key = f"{entity_name}::{entity_type}"
            if typed_key in lookup:
                return lookup[typed_key]
        if entity_name:
            return lookup.get(entity_name)
        return None

    @staticmethod
    def _entity_raw_type(entity: Entity) -> str:
        metadata = dict(entity.entity_metadata or {})
        return str(metadata.get("raw_type") or (entity.type.value if isinstance(entity.type, EntityTypeEnum) else str(entity.type)) or "other")

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
