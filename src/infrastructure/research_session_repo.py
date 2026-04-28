"""P3.1 ResearchSession 仓储层。

提供 ResearchSession / PhaseExecution / ResearchArtifact 的 CRUD 与查询方法，
并支持从 ResearchCycle dataclass 的双向转换。
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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
    ResearchLearningFeedback,
    ResearchSession,
    ReviewAssignment,
    ReviewDispute,
    SessionStatusEnum,
    _json_dumps,
    _json_loads,
)
from src.research.graph_assets import (
    build_evidence_subgraph,
    build_graph_assets_payload,
    build_hypothesis_subgraph,
    get_phase_graph_assets,
)
from src.research.learning_feedback_contract import (
    CONTRACT_VERSION as LEARNING_FEEDBACK_CONTRACT_VERSION,
)
from src.research.learning_feedback_contract import (
    normalize_learning_feedback_record,
)
from src.research.observe_philology import (
    OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT,
    build_observe_philology_artifact_payloads,
    build_observe_philology_graph_assets,
    normalize_observe_catalog_review_decision,
    resolve_observe_philology_assets,
    upsert_observe_catalog_review_artifact_content,
    upsert_observe_catalog_review_artifact_content_batch,
)
from src.research.review_workbench import (
    OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
    normalize_observe_review_workbench_decision,
    upsert_observe_review_workbench_artifact_content,
    upsert_observe_review_workbench_artifact_content_batch,
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


def _graph_asset_subgraphs(graph_assets: Mapping[str, Any] | None) -> List[str]:
    if not isinstance(graph_assets, Mapping):
        return []
    return sorted(
        key
        for key, value in graph_assets.items()
        if key != "summary" and isinstance(value, Mapping)
    )


def _graph_asset_counts(graph_assets: Mapping[str, Any] | None) -> Dict[str, Any]:
    subgraphs = _graph_asset_subgraphs(graph_assets)
    node_count = 0
    edge_count = 0
    for subgraph_name in subgraphs:
        subgraph = (
            graph_assets.get(subgraph_name) if isinstance(graph_assets, Mapping) else {}
        )
        if not isinstance(subgraph, Mapping):
            continue
        node_count += int(subgraph.get("node_count") or 0)
        edge_count += int(subgraph.get("edge_count") or 0)
    return {
        "subgraphs": subgraphs,
        "node_count": node_count,
        "edge_count": edge_count,
    }


def _normalize_phase_output_for_graph_assets(
    output: Mapping[str, Any] | None, phase_name: str, phase_status: Any
) -> Dict[str, Any]:
    payload = dict(output or {})
    payload.setdefault("phase", str(phase_name or "").strip())
    payload.setdefault(
        "status", getattr(phase_status, "value", phase_status) or "completed"
    )
    payload["results"] = dict(payload.get("results") or {})
    payload["metadata"] = dict(payload.get("metadata") or {})
    payload["artifacts"] = list(payload.get("artifacts") or [])
    payload.setdefault("error", payload.get("error"))
    return payload


def _build_inferred_phase_graph_assets(
    phase_name: str,
    cycle_id: str,
    phase_output: Mapping[str, Any],
    *,
    phase_artifacts: Sequence[Mapping[str, Any]] | None = None,
    observe_documents: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    normalized_phase = str(phase_name or "").strip().lower()
    results = (
        dict(phase_output.get("results") or {})
        if isinstance(phase_output.get("results"), Mapping)
        else {}
    )

    if normalized_phase == "observe":
        observe_philology = resolve_observe_philology_assets(
            artifacts=phase_artifacts,
            observe_phase_result=phase_output,
            observe_documents=observe_documents,
        )
        # If resolve produced no terminology (legacy entity-extraction format), derive
        # terminology_standard_table from Entity table rows stored in observe_documents.
        # Each observe document has an `entities` list with {"name": ..., "entity_type": ...}.
        existing_terms: List[Mapping[str, Any]] = list(
            (observe_philology or {}).get("terminology_standard_table") or []
        )
        if not existing_terms and observe_documents:
            seen_term_keys: set[tuple[str, str, str]] = set()
            legacy_terms: List[Dict[str, Any]] = []
            for doc in observe_documents:
                if not isinstance(doc, Mapping):
                    continue
                doc_urn = str(doc.get("urn") or doc.get("document_urn") or "").strip()
                doc_title = str(
                    doc.get("title")
                    or doc.get("document_title")
                    or doc.get("work_title")
                    or ""
                ).strip()
                for entity in doc.get("entities") or []:
                    if not isinstance(entity, Mapping):
                        continue
                    canonical = str(
                        entity.get("name") or entity.get("canonical") or ""
                    ).strip()
                    semantic_scope = str(
                        entity.get("entity_type")
                        or entity.get("semantic_scope")
                        or "common"
                    ).strip()
                    if not canonical:
                        continue
                    term_key = (doc_urn or doc_title, canonical, semantic_scope)
                    if term_key in seen_term_keys:
                        continue
                    seen_term_keys.add(term_key)
                    legacy_terms.append(
                        {
                            "canonical": canonical,
                            "semantic_scope": semantic_scope,
                            "label": semantic_scope,
                            "document_urn": doc_urn,
                            "document_title": doc_title,
                            "review_status": "inferred",
                            "needs_manual_review": True,
                            "decision_basis": "legacy_entity_extraction",
                        }
                    )
            if legacy_terms:
                observe_philology = dict(observe_philology or {})
                observe_philology["terminology_standard_table"] = legacy_terms
        return build_observe_philology_graph_assets(
            cycle_id, observe_philology, phase="observe"
        )

    if normalized_phase == "hypothesis":
        hypotheses = results.get("hypotheses")
        if not isinstance(hypotheses, list) or not hypotheses:
            hypotheses = (
                phase_output.get("hypotheses")
                if isinstance(phase_output.get("hypotheses"), list)
                else []
            )
        if not hypotheses:
            return {}
        hypothesis_subgraph = build_hypothesis_subgraph(cycle_id, hypotheses)
        if not hypothesis_subgraph.get("node_count") and not hypothesis_subgraph.get(
            "edge_count"
        ):
            return {}
        return build_graph_assets_payload(hypothesis_subgraph=hypothesis_subgraph)

    if normalized_phase == "analyze":
        evidence_protocol = results.get("evidence_protocol")
        if not isinstance(evidence_protocol, Mapping):
            evidence_protocol = (
                phase_output.get("evidence_protocol")
                if isinstance(phase_output.get("evidence_protocol"), Mapping)
                else {}
            )
        if not evidence_protocol:
            return {}
        evidence_subgraph = build_evidence_subgraph(
            cycle_id, evidence_protocol, phase="analyze"
        )
        if not evidence_subgraph.get("node_count") and not evidence_subgraph.get(
            "edge_count"
        ):
            return {}
        return build_graph_assets_payload(evidence_subgraph=evidence_subgraph)

    return {}


# ---------------------------------------------------------------------------
# ResearchSessionRepository
# ---------------------------------------------------------------------------


class ResearchSessionRepository:
    """ResearchSession 全生命周期仓储。"""

    def __init__(self, db_manager: DatabaseManager):
        self._db = db_manager
        # T5.4: 供 ExpertFeedbackLoop 等评论裁决关闭后的订阅点。
        # 每个 hook 签名：``hook(cycle_id: str, dispute: dict) -> None``。
        self._dispute_resolution_hooks: List[Any] = []

    def register_dispute_resolution_hook(self, hook: Any) -> None:
        """T5.4: 订阅 ``resolve_review_dispute`` 关闭事件。"""
        if callable(hook) and hook not in self._dispute_resolution_hooks:
            self._dispute_resolution_hooks.append(hook)

    def _emit_dispute_resolved(self, cycle_id: str, payload: Dict[str, Any]) -> None:
        for hook in list(self._dispute_resolution_hooks):
            try:
                hook(cycle_id, payload)
            except Exception:  # pragma: no cover - hook 不得中断主流程
                logger.exception("dispute resolution hook failed")

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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            query = session.query(ResearchSession).order_by(
                ResearchSession.created_at.desc()
            )
            if status:
                query = query.filter(
                    ResearchSession.status == _to_session_status(status)
                )
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
        return self.update_session(
            cycle_id,
            {
                "status": "active",
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            session=session,
        )

    def complete_session(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.update_session(
            cycle_id,
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            session=session,
        )

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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            rs = (
                session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            rs = (
                session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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

    # ---- 学习反馈库 -----------------------------------------------------

    def replace_learning_feedback_library(
        self,
        cycle_id: str,
        payload: Mapping[str, Any],
        *,
        phase_execution_id: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
            if rs is None:
                return None

            raw_records = (
                payload.get("records")
                if isinstance(payload.get("records"), list)
                else []
            )
            normalized_records = [
                normalize_learning_feedback_record(item)
                for item in raw_records
                if isinstance(item, Mapping)
            ]
            db_session.query(ResearchLearningFeedback).filter_by(
                session_id=rs.id
            ).delete(
                synchronize_session=False,
            )

            default_phase_execution_id: Optional[uuid.UUID] = None
            if phase_execution_id:
                default_phase_execution_id = uuid.UUID(str(phase_execution_id))

            for record in normalized_records:
                record_phase_execution_id = default_phase_execution_id
                raw_phase_execution_id = record.get("phase_execution_id")
                if raw_phase_execution_id:
                    record_phase_execution_id = uuid.UUID(str(raw_phase_execution_id))
                metadata = dict(record.get("metadata") or {})
                metadata.setdefault(
                    "contract_version",
                    str(
                        payload.get("contract_version")
                        or LEARNING_FEEDBACK_CONTRACT_VERSION
                    ),
                )

                db_session.add(
                    ResearchLearningFeedback(
                        session_id=rs.id,
                        cycle_id=cycle_id,
                        phase_execution_id=record_phase_execution_id,
                        feedback_scope=str(
                            record.get("feedback_scope") or "phase_assessment"
                        ),
                        source_phase=str(record.get("source_phase") or "reflect"),
                        target_phase=str(record.get("target_phase") or "").strip()
                        or None,
                        feedback_status=str(record.get("feedback_status") or "tracked"),
                        overall_score=record.get("overall_score"),
                        grade_level=str(record.get("grade_level") or "").strip()
                        or None,
                        cycle_trend=str(record.get("cycle_trend") or "").strip()
                        or None,
                        issue_count=max(int(record.get("issue_count") or 0), 0),
                        weakness_count=max(int(record.get("weakness_count") or 0), 0),
                        strength_count=max(int(record.get("strength_count") or 0), 0),
                        strategy_changed=bool(record.get("strategy_changed")),
                        strategy_before_fingerprint=str(
                            record.get("strategy_before_fingerprint") or ""
                        ).strip()
                        or None,
                        strategy_after_fingerprint=str(
                            record.get("strategy_after_fingerprint") or ""
                        ).strip()
                        or None,
                        recorded_phase_names=list(
                            record.get("recorded_phase_names") or []
                        ),
                        weak_phase_names=list(record.get("weak_phase_names") or []),
                        quality_dimensions_json=_json_dumps(
                            record.get("quality_dimensions"), "{}"
                        ),
                        issues_json=_json_dumps(record.get("issues"), "[]"),
                        improvement_priorities_json=_json_dumps(
                            record.get("improvement_priorities"), "[]"
                        ),
                        replay_feedback_json=_json_dumps(
                            record.get("replay_feedback"), "{}"
                        ),
                        details_json=_json_dumps(record.get("details"), "{}"),
                        metadata_json=_json_dumps(metadata, "{}"),
                        prompt_version=(
                            str(record.get("prompt_version") or "").strip() or None
                        ),
                        schema_version=(
                            str(record.get("schema_version") or "").strip() or None
                        ),
                    )
                )

            db_session.flush()
            stored_records = self._list_learning_feedback_records(db_session, cycle_id)
            return self._build_learning_feedback_library_snapshot(stored_records)

    def append_learning_feedback_record(
        self,
        cycle_id: str,
        record: Mapping[str, Any],
        *,
        phase_execution_id: Optional[str] = None,
        contract_version: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """T5.4: 追加单条 ``research_learning_feedback`` 记录。

        与 :meth:`replace_learning_feedback_library` 互补：后者会清空再写，
        本方法只在末尾插入一条，供 ExpertFeedbackLoop 等"事件驱动"路径使用。
        """
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
            if rs is None:
                return None
            normalized = normalize_learning_feedback_record(dict(record or {}))
            metadata = dict(normalized.get("metadata") or {})
            metadata.setdefault(
                "contract_version",
                str(contract_version or LEARNING_FEEDBACK_CONTRACT_VERSION),
            )
            record_phase_execution_id: Optional[uuid.UUID] = None
            raw_phase_execution_id = (
                normalized.get("phase_execution_id") or phase_execution_id
            )
            if raw_phase_execution_id:
                record_phase_execution_id = uuid.UUID(str(raw_phase_execution_id))

            db_session.add(
                ResearchLearningFeedback(
                    session_id=rs.id,
                    cycle_id=cycle_id,
                    phase_execution_id=record_phase_execution_id,
                    feedback_scope=str(
                        normalized.get("feedback_scope") or "phase_assessment"
                    ),
                    source_phase=str(normalized.get("source_phase") or "reflect"),
                    target_phase=str(normalized.get("target_phase") or "").strip()
                    or None,
                    feedback_status=str(normalized.get("feedback_status") or "tracked"),
                    overall_score=normalized.get("overall_score"),
                    grade_level=str(normalized.get("grade_level") or "").strip()
                    or None,
                    cycle_trend=str(normalized.get("cycle_trend") or "").strip()
                    or None,
                    issue_count=max(int(normalized.get("issue_count") or 0), 0),
                    weakness_count=max(int(normalized.get("weakness_count") or 0), 0),
                    strength_count=max(int(normalized.get("strength_count") or 0), 0),
                    strategy_changed=bool(normalized.get("strategy_changed")),
                    strategy_before_fingerprint=str(
                        normalized.get("strategy_before_fingerprint") or ""
                    ).strip()
                    or None,
                    strategy_after_fingerprint=str(
                        normalized.get("strategy_after_fingerprint") or ""
                    ).strip()
                    or None,
                    recorded_phase_names=list(
                        normalized.get("recorded_phase_names") or []
                    ),
                    weak_phase_names=list(normalized.get("weak_phase_names") or []),
                    quality_dimensions_json=_json_dumps(
                        normalized.get("quality_dimensions"), "{}"
                    ),
                    issues_json=_json_dumps(normalized.get("issues"), "[]"),
                    improvement_priorities_json=_json_dumps(
                        normalized.get("improvement_priorities"), "[]"
                    ),
                    replay_feedback_json=_json_dumps(
                        normalized.get("replay_feedback"), "{}"
                    ),
                    details_json=_json_dumps(normalized.get("details"), "{}"),
                    metadata_json=_json_dumps(metadata, "{}"),
                    prompt_version=(
                        str(normalized.get("prompt_version") or "").strip() or None
                    ),
                    schema_version=(
                        str(normalized.get("schema_version") or "").strip() or None
                    ),
                )
            )
            db_session.flush()
            stored_records = self._list_learning_feedback_records(db_session, cycle_id)
            return self._build_learning_feedback_library_snapshot(stored_records)

    def get_learning_feedback_library(
        self,
        cycle_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
            if rs is None:
                return None
            return self._build_learning_feedback_library_snapshot(
                self._list_learning_feedback_records(db_session, cycle_id),
            )

    def list_learning_feedback(
        self,
        cycle_id: Optional[str] = None,
        *,
        feedback_scope: Optional[str] = None,
        target_phase: Optional[str] = None,
        cycle_trend: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        with self._db.session_scope() as session:
            query = session.query(ResearchLearningFeedback).order_by(
                ResearchLearningFeedback.created_at.desc()
            )
            if cycle_id:
                query = query.filter(ResearchLearningFeedback.cycle_id == cycle_id)
            if feedback_scope:
                query = query.filter(
                    ResearchLearningFeedback.feedback_scope
                    == str(feedback_scope).strip().lower(),
                )
            if target_phase:
                query = query.filter(
                    ResearchLearningFeedback.target_phase
                    == str(target_phase).strip().lower()
                )
            if cycle_trend:
                query = query.filter(
                    ResearchLearningFeedback.cycle_trend
                    == str(cycle_trend).strip().lower()
                )

            total = query.count()
            items = query.offset(offset).limit(limit).all()
            return {
                "items": [self._learning_feedback_to_dict(item) for item in items],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    # ---- Phase H / H-2: Review assignments ------------------------------

    _REVIEW_ASSIGNMENT_QUEUE_STATUSES = (
        "unassigned",
        "claimed",
        "in_progress",
        "completed",
        "expired",
    )
    _REVIEW_ASSIGNMENT_PRIORITY_BUCKETS = ("high", "medium", "low")

    def claim_review_assignment(
        self,
        cycle_id: str,
        asset_type: str,
        asset_key: str,
        assignee: str,
        *,
        priority_bucket: Optional[str] = None,
        due_at: Any = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Upsert an assignment row marking ``assignee`` as claimer.

        Returns the persisted assignment dict, or ``None`` when ``cycle_id``
        does not resolve to a session.
        """

        normalized_assignee = (assignee or "").strip()
        if not normalized_assignee:
            raise ValueError("assignee is required to claim a review assignment")
        return self._upsert_review_assignment(
            cycle_id=cycle_id,
            asset_type=asset_type,
            asset_key=asset_key,
            assignee=normalized_assignee,
            queue_status="claimed",
            priority_bucket=priority_bucket,
            due_at=due_at,
            notes=notes,
            metadata=metadata,
            mark_claimed_at=True,
            session=session,
        )

    def release_review_assignment(
        self,
        cycle_id: str,
        asset_type: str,
        asset_key: str,
        *,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Release the current assignee, returning the row to ``unassigned``.

        Returns ``None`` when no assignment exists for the target.
        """

        with self._session_scope(session) as db_session:
            row = (
                db_session.query(ReviewAssignment)
                .filter_by(
                    cycle_id=cycle_id,
                    asset_type=str(asset_type or "").strip(),
                    asset_key=str(asset_key or "").strip(),
                )
                .one_or_none()
            )
            if row is None:
                return None
            row.assignee = None
            row.queue_status = "unassigned"
            row.released_at = datetime.now(timezone.utc)
            if notes is not None:
                row.notes = str(notes)
            if metadata is not None:
                row.metadata_json = _json_dumps(dict(metadata), "{}")
            db_session.flush()
            return self._review_assignment_to_dict(row)

    def reassign_review_assignment(
        self,
        cycle_id: str,
        asset_type: str,
        asset_key: str,
        new_assignee: str,
        *,
        priority_bucket: Optional[str] = None,
        due_at: Any = None,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Reassign an existing review assignment to ``new_assignee``."""

        normalized_assignee = (new_assignee or "").strip()
        if not normalized_assignee:
            raise ValueError("new_assignee is required to reassign a review assignment")
        return self._upsert_review_assignment(
            cycle_id=cycle_id,
            asset_type=asset_type,
            asset_key=asset_key,
            assignee=normalized_assignee,
            queue_status="claimed",
            priority_bucket=priority_bucket,
            due_at=due_at,
            notes=notes,
            metadata=metadata,
            mark_claimed_at=True,
            session=session,
        )

    def complete_review_assignment(
        self,
        cycle_id: str,
        asset_type: str,
        asset_key: str,
        *,
        notes: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark an assignment as completed (used after review write-back)."""

        with self._session_scope(session) as db_session:
            row = (
                db_session.query(ReviewAssignment)
                .filter_by(
                    cycle_id=cycle_id,
                    asset_type=str(asset_type or "").strip(),
                    asset_key=str(asset_key or "").strip(),
                )
                .one_or_none()
            )
            if row is None:
                return None
            row.queue_status = "completed"
            row.completed_at = datetime.now(timezone.utc)
            if notes is not None:
                row.notes = str(notes)
            if metadata is not None:
                row.metadata_json = _json_dumps(dict(metadata), "{}")
            db_session.flush()
            return self._review_assignment_to_dict(row)

    def list_review_queue(
        self,
        *,
        cycle_id: Optional[str] = None,
        assignee: Optional[str] = None,
        queue_status: Optional[str] = None,
        priority_bucket: Optional[str] = None,
        asset_type: Optional[str] = None,
        only_overdue: bool = False,
        unassigned_only: bool = False,
        now: Optional[datetime] = None,
        limit: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Return the review queue with the requested filters applied."""

        reference_now = now or datetime.now(timezone.utc)
        with self._session_scope(session) as db_session:
            query = db_session.query(ReviewAssignment)
            if cycle_id:
                query = query.filter(ReviewAssignment.cycle_id == cycle_id)
            if assignee:
                query = query.filter(ReviewAssignment.assignee == assignee)
            if unassigned_only:
                query = query.filter(ReviewAssignment.assignee.is_(None))
            if queue_status:
                query = query.filter(
                    ReviewAssignment.queue_status == str(queue_status).strip().lower()
                )
            if priority_bucket:
                query = query.filter(
                    ReviewAssignment.priority_bucket
                    == str(priority_bucket).strip().lower()
                )
            if asset_type:
                query = query.filter(
                    ReviewAssignment.asset_type == str(asset_type).strip().lower()
                )
            if only_overdue:
                query = query.filter(
                    ReviewAssignment.due_at.isnot(None),
                    ReviewAssignment.due_at < reference_now,
                    ReviewAssignment.queue_status != "completed",
                )
            query = query.order_by(
                ReviewAssignment.priority_bucket.asc(),
                ReviewAssignment.created_at.asc(),
            )
            if limit is not None and int(limit) > 0:
                query = query.limit(int(limit))
            return [
                self._review_assignment_to_dict(row, now=reference_now)
                for row in query.all()
            ]

    def aggregate_reviewer_workload(
        self,
        *,
        cycle_id: Optional[str] = None,
        now: Optional[datetime] = None,
        session: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Aggregate workload per reviewer (including the unassigned bucket)."""

        reference_now = now or datetime.now(timezone.utc)
        rows = self.list_review_queue(
            cycle_id=cycle_id, now=reference_now, session=session
        )
        buckets: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            reviewer_label = row.get("reviewer_label") or "未认领"
            bucket = buckets.setdefault(
                reviewer_label,
                {
                    "reviewer": "" if reviewer_label == "未认领" else reviewer_label,
                    "reviewer_label": reviewer_label,
                    "total": 0,
                    "unassigned": 0,
                    "claimed": 0,
                    "in_progress": 0,
                    "completed": 0,
                    "expired": 0,
                    "overdue": 0,
                    "high_priority": 0,
                    "medium_priority": 0,
                    "low_priority": 0,
                },
            )
            bucket["total"] += 1
            queue_status = row.get("queue_status") or "unassigned"
            if queue_status in bucket:
                bucket[queue_status] += 1
            priority = row.get("priority_bucket") or "medium"
            priority_key = f"{priority}_priority"
            if priority_key in bucket:
                bucket[priority_key] += 1
            if row.get("is_overdue"):
                bucket["overdue"] += 1
        ordered_keys = sorted(
            buckets.keys(),
            key=lambda label: (label == "未认领", label),
        )
        return [buckets[label] for label in ordered_keys]

    def aggregate_review_quality_summary(
        self,
        *,
        cycle_id: Optional[str] = None,
        reviewer: Optional[str] = None,
        asset_type: Optional[str] = None,
        now: Optional[datetime] = None,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Phase H / H-4: aggregate review QC metrics for a cycle.

        Pulls assignments + dispute archive once and delegates to
        :func:`src.research.review_sampling.compute_review_quality_summary`
        for the math. Filters are applied during aggregation, not at the SQL
        layer, so the same call serves dashboard and ad-hoc reports.
        """

        # Local import keeps this module import-graph clean.
        from src.research.review_sampling import compute_review_quality_summary

        reference_now = now or datetime.now(timezone.utc)
        assignments = self.list_review_queue(
            cycle_id=cycle_id,
            now=reference_now,
            session=session,
        )
        disputes = self.list_review_disputes(cycle_id=cycle_id, session=session)
        return compute_review_quality_summary(
            review_assignments=assignments,
            review_disputes=disputes,
            reviewer=reviewer,
            asset_type=asset_type,
        )

    def _upsert_review_assignment(
        self,
        *,
        cycle_id: str,
        asset_type: str,
        asset_key: str,
        assignee: Optional[str],
        queue_status: str,
        priority_bucket: Optional[str],
        due_at: Any,
        notes: Optional[str],
        metadata: Optional[Mapping[str, Any]],
        mark_claimed_at: bool,
        session: Optional[Session],
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
            if rs is None:
                return None

            normalized_asset_type = str(asset_type or "").strip()
            normalized_asset_key = str(asset_key or "").strip()
            if not normalized_asset_type or not normalized_asset_key:
                raise ValueError("asset_type and asset_key are required")

            normalized_status = (queue_status or "unassigned").strip().lower()
            if normalized_status not in self._REVIEW_ASSIGNMENT_QUEUE_STATUSES:
                normalized_status = "unassigned"

            normalized_priority = (priority_bucket or "").strip().lower() or None
            if (
                normalized_priority
                and normalized_priority not in self._REVIEW_ASSIGNMENT_PRIORITY_BUCKETS
            ):
                normalized_priority = None

            row = (
                db_session.query(ReviewAssignment)
                .filter_by(
                    cycle_id=cycle_id,
                    asset_type=normalized_asset_type,
                    asset_key=normalized_asset_key,
                )
                .one_or_none()
            )
            if row is None:
                row = ReviewAssignment(
                    session_id=rs.id,
                    cycle_id=cycle_id,
                    asset_type=normalized_asset_type,
                    asset_key=normalized_asset_key,
                    assignee=assignee,
                    queue_status=normalized_status,
                    priority_bucket=normalized_priority or "medium",
                    notes=notes,
                    metadata_json=_json_dumps(dict(metadata or {}), "{}"),
                    due_at=_parse_datetime(due_at) if due_at is not None else None,
                )
                if mark_claimed_at:
                    row.claimed_at = datetime.now(timezone.utc)
                db_session.add(row)
            else:
                row.assignee = assignee
                row.queue_status = normalized_status
                if normalized_priority is not None:
                    row.priority_bucket = normalized_priority
                if due_at is not None:
                    row.due_at = _parse_datetime(due_at)
                if notes is not None:
                    row.notes = str(notes)
                if metadata is not None:
                    row.metadata_json = _json_dumps(dict(metadata), "{}")
                if mark_claimed_at:
                    row.claimed_at = datetime.now(timezone.utc)
                    row.released_at = None
            db_session.flush()
            return self._review_assignment_to_dict(row)

    @staticmethod
    def _review_assignment_to_dict(
        row: ReviewAssignment,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        reference_now = now or datetime.now(timezone.utc)
        claimed_at = row.claimed_at
        backlog_age_seconds = None
        if claimed_at is not None:
            backlog_age_seconds = max(0.0, (reference_now - claimed_at).total_seconds())
        elif row.created_at is not None:
            backlog_age_seconds = max(
                0.0, (reference_now - row.created_at).total_seconds()
            )
        is_overdue = bool(
            row.due_at is not None
            and row.queue_status != "completed"
            and row.due_at < reference_now
        )
        reviewer_label = row.assignee or "未认领"
        return {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "cycle_id": row.cycle_id,
            "asset_type": row.asset_type,
            "asset_key": row.asset_key,
            "assignee": row.assignee,
            "reviewer_label": reviewer_label,
            "queue_status": row.queue_status,
            "priority_bucket": row.priority_bucket,
            "notes": row.notes,
            "metadata": _json_loads(row.metadata_json, {}),
            "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
            "released_at": row.released_at.isoformat() if row.released_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "backlog_age_seconds": backlog_age_seconds,
            "is_overdue": is_overdue,
        }

    # ---- Phase H / H-3: Review disputes ---------------------------------

    _REVIEW_DISPUTE_STATUSES = ("open", "assigned", "resolved", "withdrawn")
    _REVIEW_DISPUTE_RESOLUTIONS = (
        "accepted",
        "rejected",
        "needs_source",
        "no_change",
    )

    def open_review_dispute(
        self,
        cycle_id: str,
        asset_type: str,
        asset_key: str,
        opened_by: str,
        summary: str,
        *,
        case_id: Optional[str] = None,
        arbitrator: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new dispute case for a workbench item.

        Returns ``None`` when ``cycle_id`` does not resolve to a session.
        Raises ``ValueError`` when required fields are missing.
        """

        normalized_opened_by = (opened_by or "").strip()
        if not normalized_opened_by:
            raise ValueError("opened_by is required to open a review dispute")
        normalized_asset_type = str(asset_type or "").strip()
        normalized_asset_key = str(asset_key or "").strip()
        if not normalized_asset_type or not normalized_asset_key:
            raise ValueError("asset_type and asset_key are required")
        normalized_summary = str(summary or "").strip()
        if not normalized_summary:
            raise ValueError("summary is required to open a review dispute")

        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
            if rs is None:
                return None

            resolved_case_id = (
                case_id or ""
            ).strip() or self._generate_dispute_case_id(db_session, cycle_id)
            now = datetime.now(timezone.utc)
            arbitrator_value = (arbitrator or "").strip() or None
            initial_status = "assigned" if arbitrator_value else "open"
            opened_event = {
                "event": "opened",
                "actor": normalized_opened_by,
                "at": now.isoformat(),
                "summary": normalized_summary,
            }
            events: list[Dict[str, Any]] = [opened_event]
            if arbitrator_value:
                events.append(
                    {
                        "event": "assigned",
                        "actor": normalized_opened_by,
                        "arbitrator": arbitrator_value,
                        "at": now.isoformat(),
                    }
                )
            row = ReviewDispute(
                session_id=rs.id,
                cycle_id=cycle_id,
                case_id=resolved_case_id,
                asset_type=normalized_asset_type,
                asset_key=normalized_asset_key,
                dispute_status=initial_status,
                opened_by=normalized_opened_by,
                arbitrator=arbitrator_value,
                summary=normalized_summary,
                events_json=_json_dumps(events, "[]"),
                metadata_json=_json_dumps(dict(metadata or {}), "{}"),
                opened_at=now,
                assigned_at=now if arbitrator_value else None,
            )
            db_session.add(row)
            db_session.flush()
            return self._review_dispute_to_dict(row)

    def assign_review_dispute(
        self,
        cycle_id: str,
        case_id: str,
        arbitrator: str,
        *,
        actor: Optional[str] = None,
        notes: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_arbitrator = (arbitrator or "").strip()
        if not normalized_arbitrator:
            raise ValueError("arbitrator is required to assign a review dispute")
        with self._session_scope(session) as db_session:
            row = self._find_review_dispute(db_session, cycle_id, case_id)
            if row is None:
                return None
            if row.dispute_status not in {"open", "assigned"}:
                raise ValueError(
                    f"dispute case {case_id} 已是终态 {row.dispute_status}, 不可改派"
                )
            now = datetime.now(timezone.utc)
            row.arbitrator = normalized_arbitrator
            row.dispute_status = "assigned"
            row.assigned_at = now
            self._append_dispute_event(
                row,
                {
                    "event": "assigned",
                    "actor": (actor or normalized_arbitrator).strip(),
                    "arbitrator": normalized_arbitrator,
                    "at": now.isoformat(),
                    "notes": notes,
                },
            )
            db_session.flush()
            return self._review_dispute_to_dict(row)

    def resolve_review_dispute(
        self,
        cycle_id: str,
        case_id: str,
        resolution: str,
        *,
        resolved_by: str,
        resolution_notes: Optional[str] = None,
        writeback_review_status: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        """Close a dispute and (optionally) write back the final review status
        onto the matching workbench item.
        """

        normalized_resolved_by = (resolved_by or "").strip()
        if not normalized_resolved_by:
            raise ValueError("resolved_by is required to resolve a review dispute")
        normalized_resolution = (resolution or "").strip().lower()
        if normalized_resolution not in self._REVIEW_DISPUTE_RESOLUTIONS:
            raise ValueError(
                f"invalid resolution {resolution!r}; expected one of "
                f"{self._REVIEW_DISPUTE_RESOLUTIONS}"
            )
        with self._session_scope(session) as db_session:
            row = self._find_review_dispute(db_session, cycle_id, case_id)
            if row is None:
                return None
            if row.dispute_status in {"resolved", "withdrawn"}:
                raise ValueError(
                    f"dispute case {case_id} 已是终态 {row.dispute_status}, 不可重复关闭"
                )
            now = datetime.now(timezone.utc)
            row.dispute_status = "resolved"
            row.resolution = normalized_resolution
            row.resolved_at = now
            if resolution_notes is not None:
                row.resolution_notes = str(resolution_notes)
            self._append_dispute_event(
                row,
                {
                    "event": "resolved",
                    "actor": normalized_resolved_by,
                    "resolution": normalized_resolution,
                    "at": now.isoformat(),
                    "notes": resolution_notes,
                    "writeback_review_status": writeback_review_status,
                },
            )
            db_session.flush()
            payload = self._review_dispute_to_dict(row)

        # Optional write-back to workbench item — runs in a fresh session
        # so the dispute row commits even if writeback fails downstream.
        writeback_status = (writeback_review_status or "").strip().lower()
        if writeback_status in {"accepted", "rejected", "needs_source", "pending"}:
            try:
                self.upsert_observe_workbench_review_batch(
                    cycle_id,
                    {
                        "decisions": [
                            {
                                "asset_type": payload["asset_type"],
                                "asset_key": payload["asset_key"],
                                "review_status": writeback_status,
                                "reviewer": normalized_resolved_by,
                                "decision_basis": (
                                    f"裁决关闭 dispute {payload['case_id']}: "
                                    f"{normalized_resolution}"
                                ),
                                "review_reasons": [
                                    f"dispute_resolution:{normalized_resolution}",
                                    f"dispute_case:{payload['case_id']}",
                                ],
                            }
                        ],
                        "reviewer": normalized_resolved_by,
                        "shared_decision_basis": (
                            f"H-3 dispute {payload['case_id']} 裁决关闭"
                        ),
                    },
                )
                payload["writeback_applied"] = True
                payload["writeback_review_status"] = writeback_status
            except Exception:  # pragma: no cover — best-effort
                payload["writeback_applied"] = False
                payload["writeback_review_status"] = writeback_status
        else:
            payload["writeback_applied"] = False
            payload["writeback_review_status"] = None
        # T5.4: 召唭订阅者（ExpertFeedbackLoop 会在这里往 research_learning_feedback 插行）
        self._emit_dispute_resolved(cycle_id, payload)
        return payload

    def withdraw_review_dispute(
        self,
        cycle_id: str,
        case_id: str,
        *,
        actor: str,
        notes: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_actor = (actor or "").strip()
        if not normalized_actor:
            raise ValueError("actor is required to withdraw a review dispute")
        with self._session_scope(session) as db_session:
            row = self._find_review_dispute(db_session, cycle_id, case_id)
            if row is None:
                return None
            if row.dispute_status in {"resolved", "withdrawn"}:
                raise ValueError(
                    f"dispute case {case_id} 已是终态 {row.dispute_status}, 不可撤销"
                )
            now = datetime.now(timezone.utc)
            row.dispute_status = "withdrawn"
            row.resolved_at = now
            if notes is not None:
                row.resolution_notes = str(notes)
            self._append_dispute_event(
                row,
                {
                    "event": "withdrawn",
                    "actor": normalized_actor,
                    "at": now.isoformat(),
                    "notes": notes,
                },
            )
            db_session.flush()
            return self._review_dispute_to_dict(row)

    def list_review_disputes(
        self,
        *,
        cycle_id: Optional[str] = None,
        dispute_status: Optional[str] = None,
        arbitrator: Optional[str] = None,
        opened_by: Optional[str] = None,
        asset_type: Optional[str] = None,
        case_id: Optional[str] = None,
        limit: Optional[int] = None,
        session: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            query = db_session.query(ReviewDispute)
            if cycle_id:
                query = query.filter(ReviewDispute.cycle_id == cycle_id)
            if dispute_status:
                normalized_status = str(dispute_status).strip().lower()
                if normalized_status in self._REVIEW_DISPUTE_STATUSES:
                    query = query.filter(
                        ReviewDispute.dispute_status == normalized_status
                    )
            if arbitrator:
                query = query.filter(
                    ReviewDispute.arbitrator == str(arbitrator).strip()
                )
            if opened_by:
                query = query.filter(ReviewDispute.opened_by == str(opened_by).strip())
            if asset_type:
                query = query.filter(
                    ReviewDispute.asset_type == str(asset_type).strip()
                )
            if case_id:
                query = query.filter(ReviewDispute.case_id == str(case_id).strip())
            query = query.order_by(
                ReviewDispute.dispute_status.asc(), ReviewDispute.created_at.asc()
            )
            if limit is not None and limit > 0:
                query = query.limit(int(limit))
            return [self._review_dispute_to_dict(r) for r in query.all()]

    def get_review_dispute(
        self,
        cycle_id: str,
        case_id: str,
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            row = self._find_review_dispute(db_session, cycle_id, case_id)
            return self._review_dispute_to_dict(row) if row else None

    @staticmethod
    def _find_review_dispute(
        db_session: Session, cycle_id: str, case_id: str
    ) -> Optional[ReviewDispute]:
        return (
            db_session.query(ReviewDispute)
            .filter_by(cycle_id=cycle_id, case_id=str(case_id).strip())
            .one_or_none()
        )

    @staticmethod
    def _append_dispute_event(row: ReviewDispute, event: Dict[str, Any]) -> None:
        events = _json_loads(row.events_json, []) or []
        if not isinstance(events, list):
            events = []
        events.append({k: v for k, v in event.items() if v is not None})
        row.events_json = _json_dumps(events, "[]")

    @staticmethod
    def _generate_dispute_case_id(db_session: Session, cycle_id: str) -> str:
        existing = (
            db_session.query(ReviewDispute)
            .filter(ReviewDispute.cycle_id == cycle_id)
            .count()
        )
        suffix = uuid.uuid4().hex[:6].upper()
        return f"DISP-{existing + 1:04d}-{suffix}"

    @staticmethod
    def _review_dispute_to_dict(row: ReviewDispute) -> Dict[str, Any]:
        events = _json_loads(row.events_json, [])
        if not isinstance(events, list):
            events = []
        return {
            "id": str(row.id),
            "session_id": str(row.session_id),
            "cycle_id": row.cycle_id,
            "case_id": row.case_id,
            "asset_type": row.asset_type,
            "asset_key": row.asset_key,
            "dispute_status": row.dispute_status,
            "resolution": row.resolution,
            "opened_by": row.opened_by,
            "arbitrator": row.arbitrator,
            "summary": row.summary,
            "resolution_notes": row.resolution_notes,
            "events": events,
            "metadata": _json_loads(row.metadata_json, {}),
            "opened_at": row.opened_at.isoformat() if row.opened_at else None,
            "assigned_at": row.assigned_at.isoformat() if row.assigned_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def upsert_observe_catalog_review(
        self,
        cycle_id: str,
        payload: Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
            existing_content = (
                _json_loads(artifact.content_json, {}) if artifact is not None else {}
            )
            content = upsert_observe_catalog_review_artifact_content(
                existing_content, normalized_decision
            )
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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
                    ResearchArtifact.name
                    == OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
                )
                .one_or_none()
            )
            existing_content = (
                _json_loads(artifact.content_json, {}) if artifact is not None else {}
            )
            content = upsert_observe_review_workbench_artifact_content(
                existing_content, normalized_decision
            )
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

    def upsert_observe_catalog_review_batch(
        self,
        cycle_id: str,
        decisions: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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

            artifact = (
                db_session.query(ResearchArtifact)
                .filter(
                    ResearchArtifact.phase_execution_id == phase_execution.id,
                    ResearchArtifact.name == OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT,
                )
                .one_or_none()
            )
            existing_content = (
                _json_loads(artifact.content_json, {}) if artifact is not None else {}
            )
            content = upsert_observe_catalog_review_artifact_content_batch(
                existing_content, decisions
            )
            if not content:
                return None
            metadata = {
                "asset_kind": "catalog_review_decisions",
                "decision_count": int(content.get("decision_count") or 0),
                "batch_operation_count": int(content.get("batch_operation_count") or 0),
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
                    description="Observe 阶段目录学校核写回记录（批量）",
                    content_json=_json_dumps(content, "{}"),
                    file_path=None,
                    mime_type="application/json",
                    size_bytes=size_bytes,
                    metadata_json=_json_dumps(metadata, "{}"),
                )
                db_session.add(artifact)
            else:
                artifact.content_json = _json_dumps(content, "{}")
                artifact.size_bytes = size_bytes
                artifact.metadata_json = _json_dumps(metadata, "{}")

            db_session.flush()
            return self._artifact_to_dict(artifact)

    def upsert_observe_workbench_review_batch(
        self,
        cycle_id: str,
        decisions: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        *,
        session: Optional[Session] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._session_scope(session) as db_session:
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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

            artifact = (
                db_session.query(ResearchArtifact)
                .filter(
                    ResearchArtifact.phase_execution_id == phase_execution.id,
                    ResearchArtifact.name
                    == OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
                )
                .one_or_none()
            )
            existing_content = (
                _json_loads(artifact.content_json, {}) if artifact is not None else {}
            )
            content = upsert_observe_review_workbench_artifact_content_batch(
                existing_content, decisions
            )
            if not content:
                return None
            metadata = {
                "asset_kind": "review_workbench_decisions",
                "decision_count": int(content.get("decision_count") or 0),
                "batch_operation_count": int(content.get("batch_operation_count") or 0),
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
                    description="Observe 阶段文献学工作台审核写回记录（批量）",
                    content_json=_json_dumps(content, "{}"),
                    file_path=None,
                    mime_type="application/json",
                    size_bytes=size_bytes,
                    metadata_json=_json_dumps(metadata, "{}"),
                )
                db_session.add(artifact)
            else:
                artifact.content_json = _json_dumps(content, "{}")
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
            rs = (
                db_session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
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
                quality_metrics = (
                    (payload.get("output_generation") or {})
                    if isinstance(payload.get("output_generation"), dict)
                    else {}
                ).get("quality_metrics") or {}
                document.quality_score = float(
                    (
                        quality_metrics.get("confidence_score")
                        if isinstance(quality_metrics, dict)
                        else 0.0
                    )
                    or payload.get("average_confidence")
                    or document.quality_score
                    or 0.0
                )
                db_session.flush()
                snapshots.append(
                    self._observe_document_to_dict(document, entities, relationships)
                )

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
            query = self._observe_document_query(db_session, cycle_id).order_by(
                Document.processing_timestamp.asc(), Document.created_at.asc()
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
                "skipped_document_count": scanned_document_count
                - updated_document_count,
            }

    # ---- 快照（含阶段 + 工件） -------------------------------------------

    def get_full_snapshot(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """返回完整会话快照，包含阶段执行列表与工件列表。"""
        with self._db.session_scope() as session:
            rs = (
                session.query(ResearchSession)
                .filter_by(cycle_id=cycle_id)
                .one_or_none()
            )
            if rs is None:
                return None
            result = self._session_to_dict(rs)
            result["phase_executions"] = [
                self._phase_to_dict(pe) for pe in rs.phase_executions
            ]
            result["artifacts"] = [self._artifact_to_dict(a) for a in rs.artifacts]
            result["observe_documents"] = self._list_observe_document_graphs(
                session, cycle_id
            )
            result["version_lineages"] = self._group_observe_version_lineages(
                result["observe_documents"]
            )
            result["learning_feedback_library"] = (
                self._build_learning_feedback_library_snapshot(
                    self._list_learning_feedback_records(session, cycle_id),
                )
            )
            result["observe_philology"] = resolve_observe_philology_assets(
                artifacts=result["artifacts"],
                observe_phase_result=self._phase_output_by_name(
                    result["phase_executions"], "observe"
                ),
                observe_documents=result["observe_documents"],
            )
            result["backfill_dependency"] = self._classify_backfill_dependency(result)
            return result

    @staticmethod
    def _classify_backfill_dependency(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """标注快照中依赖 backfill/writeback 才完整的字段。

        返回各字段组的完整性判定，让消费方（dashboard / API / 运维）
        一眼识别当前快照中哪些数据可能不完整。
        """
        storage_meta = (snapshot.get("metadata") or {}).get("storage_persistence") or {}
        ec = storage_meta.get("eventual_consistency") or {}
        graph_pending = ec.get("graph_backfill_pending", False)

        # observe_philology: 由 artifacts + observe_documents 组合计算，
        # 历史会话可能需要 backfill_observe_philology_artifacts 补齐
        philology = snapshot.get("observe_philology") or {}
        philology_populated = bool(philology) and any(
            bool(v) for v in philology.values() if isinstance(v, (list, dict))
        )

        # version_lineages: 由 observe_documents.version_metadata 分组，
        # 历史会话可能需要 backfill_observe_document_version_metadata 补齐
        lineages = snapshot.get("version_lineages") or []
        lineages_populated = bool(lineages)

        return {
            "observe_philology": {
                "populated": philology_populated,
                "depends_on": ["backfill_observe_philology_artifacts"],
                "note": "历史会话需执行 backfill 才完整"
                if not philology_populated
                else None,
            },
            "version_lineages": {
                "populated": lineages_populated,
                "depends_on": ["backfill_observe_document_version_metadata"],
                "note": "历史会话需执行 backfill 才完整"
                if not lineages_populated
                else None,
            },
            "graph_projection": {
                "backfill_pending": graph_pending,
                "depends_on": ["backfill_structured_research_graph"],
                "reason": ec.get("reason"),
            },
        }

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

            for phase_execution, phase_cycle_id in query.yield_per(
                effective_batch_size
            ):
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
                existing_artifact_records = [
                    self._artifact_to_dict(artifact) for artifact in existing_artifacts
                ]
                existing_artifact_names = {
                    str(record.get("name") or "").strip()
                    for record in existing_artifact_records
                    if str(record.get("name") or "").strip()
                }

                if normalized_cycle_id not in observe_documents_cache:
                    observe_documents_cache[normalized_cycle_id] = (
                        self._list_observe_document_graphs(
                            db_session,
                            normalized_cycle_id,
                        )
                    )

                observe_philology = resolve_observe_philology_assets(
                    artifacts=existing_artifact_records,
                    observe_phase_result=_json_loads(phase_execution.output_json, {}),
                    observe_documents=observe_documents_cache[normalized_cycle_id],
                )
                artifact_payloads = [
                    payload
                    for payload in build_observe_philology_artifact_payloads(
                        observe_philology, artifact_output
                    )
                    if str(payload.get("name") or "").strip()
                    not in existing_artifact_names
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

    def backfill_phase_graph_assets(
        self,
        cycle_id: Optional[str] = None,
        *,
        batch_size: int = 200,
        dry_run: bool = False,
        force: bool = False,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        with self._session_scope(session) as db_session:
            query = (
                db_session.query(PhaseExecution, ResearchSession.cycle_id)
                .join(ResearchSession, PhaseExecution.session_id == ResearchSession.id)
                .filter(PhaseExecution.phase.in_(("observe", "hypothesis", "analyze")))
                .order_by(PhaseExecution.created_at.asc())
            )
            if cycle_id:
                query = query.filter(ResearchSession.cycle_id == cycle_id)

            effective_batch_size = max(int(batch_size or 0), 1)
            scanned_phase_count = 0
            updated_phase_count = 0
            graph_assets_written_phase_count = 0
            metadata_updated_phase_count = 0
            graph_asset_subgraph_count = 0
            phase_counts = {
                "observe": 0,
                "hypothesis": 0,
                "analyze": 0,
            }
            observe_documents_cache: Dict[str, List[Dict[str, Any]]] = {}

            for phase_execution, phase_cycle_id in query.yield_per(
                effective_batch_size
            ):
                scanned_phase_count += 1
                normalized_cycle_id = str(phase_cycle_id or "").strip()
                normalized_phase = (
                    str(
                        getattr(phase_execution.phase, "value", phase_execution.phase)
                        or ""
                    )
                    .strip()
                    .lower()
                )
                if not normalized_cycle_id or normalized_phase not in phase_counts:
                    continue

                output = _normalize_phase_output_for_graph_assets(
                    _json_loads(phase_execution.output_json, {}),
                    normalized_phase,
                    phase_execution.status,
                )
                results = dict(output.get("results") or {})
                metadata = dict(output.get("metadata") or {})
                existing_graph_assets = get_phase_graph_assets(output)
                existing_counts = _graph_asset_counts(existing_graph_assets)

                inferred_graph_assets = existing_graph_assets
                wrote_graph_assets = False
                if not existing_counts["subgraphs"] or force:
                    phase_artifacts = [
                        self._artifact_to_dict(artifact)
                        for artifact in (
                            db_session.query(ResearchArtifact)
                            .filter(
                                ResearchArtifact.phase_execution_id
                                == phase_execution.id
                            )
                            .order_by(ResearchArtifact.created_at.asc())
                            .all()
                        )
                    ]
                    if normalized_phase == "observe":
                        if normalized_cycle_id not in observe_documents_cache:
                            observe_documents_cache[normalized_cycle_id] = (
                                self._list_observe_document_graphs(
                                    db_session,
                                    normalized_cycle_id,
                                )
                            )
                        inferred_graph_assets = _build_inferred_phase_graph_assets(
                            normalized_phase,
                            normalized_cycle_id,
                            output,
                            phase_artifacts=phase_artifacts,
                            observe_documents=observe_documents_cache[
                                normalized_cycle_id
                            ],
                        )
                    else:
                        inferred_graph_assets = _build_inferred_phase_graph_assets(
                            normalized_phase,
                            normalized_cycle_id,
                            output,
                            phase_artifacts=phase_artifacts,
                        )
                    inferred_counts = _graph_asset_counts(inferred_graph_assets)
                    if inferred_counts["subgraphs"]:
                        results["graph_assets"] = inferred_graph_assets
                        wrote_graph_assets = True
                        graph_assets_written_phase_count += 1
                        graph_asset_subgraph_count += len(inferred_counts["subgraphs"])
                        active_counts = inferred_counts
                    else:
                        active_counts = existing_counts
                else:
                    graph_asset_subgraph_count += len(existing_counts["subgraphs"])
                    active_counts = existing_counts

                metadata_changed = False
                if (
                    active_counts["subgraphs"]
                    and metadata.get("graph_asset_subgraphs")
                    != active_counts["subgraphs"]
                ):
                    metadata["graph_asset_subgraphs"] = list(active_counts["subgraphs"])
                    metadata_changed = True
                if int(metadata.get("graph_asset_node_count") or 0) != int(
                    active_counts["node_count"] or 0
                ):
                    metadata["graph_asset_node_count"] = int(
                        active_counts["node_count"] or 0
                    )
                    metadata_changed = True
                if int(metadata.get("graph_asset_edge_count") or 0) != int(
                    active_counts["edge_count"] or 0
                ):
                    metadata["graph_asset_edge_count"] = int(
                        active_counts["edge_count"] or 0
                    )
                    metadata_changed = True

                if not wrote_graph_assets and not metadata_changed:
                    continue

                output["results"] = results
                output["metadata"] = metadata
                updated_phase_count += 1
                phase_counts[normalized_phase] += 1
                if metadata_changed:
                    metadata_updated_phase_count += 1
                if not dry_run:
                    phase_execution.output_json = _json_dumps(output, "{}")

            if not dry_run:
                db_session.flush()

            return {
                "cycle_id": cycle_id,
                "batch_size": effective_batch_size,
                "status": "dry_run" if dry_run else "active",
                "dry_run": bool(dry_run),
                "scanned_phase_count": scanned_phase_count,
                "updated_phase_count": updated_phase_count,
                "graph_assets_written_phase_count": graph_assets_written_phase_count,
                "metadata_updated_phase_count": metadata_updated_phase_count,
                "graph_asset_subgraph_count": graph_asset_subgraph_count,
                "updated_observe_phase_count": phase_counts["observe"],
                "updated_hypothesis_phase_count": phase_counts["hypothesis"],
                "updated_analyze_phase_count": phase_counts["analyze"],
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
            "current_phase": getattr(
                cycle.current_phase, "value", str(cycle.current_phase)
            ),
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
            "status": rs.status.value
            if isinstance(rs.status, SessionStatusEnum)
            else str(rs.status),
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
            "status": pe.status.value
            if isinstance(pe.status, PhaseStatusEnum)
            else str(pe.status),
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
            return (
                dict(phase_execution.get("output") or {})
                if isinstance(phase_execution.get("output"), Mapping)
                else {}
            )
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
            "phase_execution_id": str(a.phase_execution_id)
            if a.phase_execution_id
            else None,
            "artifact_type": a.artifact_type.value
            if isinstance(a.artifact_type, ArtifactTypeEnum)
            else str(a.artifact_type),
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
    def _learning_feedback_to_dict(
        feedback: ResearchLearningFeedback,
    ) -> Dict[str, Any]:
        details = _json_loads(feedback.details_json, {})
        record = {
            "id": str(feedback.id),
            "session_id": str(feedback.session_id),
            "cycle_id": feedback.cycle_id,
            "phase_execution_id": str(feedback.phase_execution_id)
            if feedback.phase_execution_id
            else None,
            "feedback_scope": feedback.feedback_scope,
            "source_phase": feedback.source_phase,
            "target_phase": feedback.target_phase,
            "feedback_status": feedback.feedback_status,
            "overall_score": feedback.overall_score,
            "grade_level": feedback.grade_level,
            "cycle_trend": feedback.cycle_trend,
            "issue_count": feedback.issue_count,
            "weakness_count": feedback.weakness_count,
            "strength_count": feedback.strength_count,
            "strategy_changed": bool(feedback.strategy_changed),
            "strategy_before_fingerprint": feedback.strategy_before_fingerprint,
            "strategy_after_fingerprint": feedback.strategy_after_fingerprint,
            "recorded_phase_names": list(feedback.recorded_phase_names or []),
            "weak_phase_names": list(feedback.weak_phase_names or []),
            "quality_dimensions": _json_loads(feedback.quality_dimensions_json, {}),
            "issues": _json_loads(feedback.issues_json, []),
            "improvement_priorities": _json_loads(
                feedback.improvement_priorities_json, []
            ),
            "replay_feedback": _json_loads(feedback.replay_feedback_json, {}),
            "details": details if isinstance(details, dict) else {},
            "metadata": _json_loads(feedback.metadata_json, {}),
            "prompt_version": feedback.prompt_version or "unknown",
            "schema_version": feedback.schema_version or "unknown",
            "created_at": feedback.created_at.isoformat()
            if feedback.created_at
            else None,
        }
        if isinstance(details, dict):
            for key in (
                "reflections",
                "improvement_plan",
                "learning_summary",
                "quality_assessment",
                "strategy_diff",
                "tuned_parameters",
                "learning_application_summary",
            ):
                value = details.get(key)
                if value not in (None, "", [], {}):
                    record[key] = value
        return record

    @staticmethod
    def _build_learning_feedback_library_summary(
        records: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        cycle_summary = next(
            (
                record
                for record in records
                if str(record.get("feedback_scope") or "") == "cycle_summary"
            ),
            {},
        )
        return {
            "record_count": len(records),
            "phase_record_count": sum(
                1
                for record in records
                if str(record.get("feedback_scope") or "") == "phase_assessment"
            ),
            "latest_cycle_score": cycle_summary.get("overall_score"),
            "cycle_trend": cycle_summary.get("cycle_trend"),
            "weak_phase_names": list(cycle_summary.get("weak_phase_names") or []),
            "recorded_phase_names": list(
                cycle_summary.get("recorded_phase_names") or []
            ),
            "strategy_changed": bool(cycle_summary.get("strategy_changed")),
            "latest_feedback_at": cycle_summary.get("created_at"),
        }

    @classmethod
    def _build_learning_feedback_library_snapshot(
        cls,
        records: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        normalized_records = [
            dict(record) for record in records if isinstance(record, Mapping)
        ]
        contract_version = LEARNING_FEEDBACK_CONTRACT_VERSION
        for record in normalized_records:
            metadata = (
                record.get("metadata")
                if isinstance(record.get("metadata"), Mapping)
                else {}
            )
            version = str(metadata.get("contract_version") or "").strip()
            if version:
                contract_version = version
                break
        cycle_summary = next(
            (
                record
                for record in normalized_records
                if str(record.get("feedback_scope") or "") == "cycle_summary"
            ),
            {},
        )
        replay_feedback = (
            cycle_summary.get("replay_feedback")
            if isinstance(cycle_summary, Mapping)
            else {}
        )
        if not isinstance(replay_feedback, Mapping):
            replay_feedback = {}
        return {
            "contract_version": contract_version,
            "summary": cls._build_learning_feedback_library_summary(normalized_records),
            "replay_feedback": dict(replay_feedback),
            "records": normalized_records,
        }

    def _list_learning_feedback_records(
        self,
        session: Session,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        items = (
            session.query(ResearchLearningFeedback)
            .filter(ResearchLearningFeedback.cycle_id == cycle_id)
            .order_by(ResearchLearningFeedback.created_at.asc())
            .all()
        )
        return [self._learning_feedback_to_dict(item) for item in items]

    @staticmethod
    def _entity_to_dict(entity: Entity) -> Dict[str, Any]:
        return {
            "id": str(entity.id),
            "document_id": str(entity.document_id),
            "name": entity.name,
            "type": entity.type.value
            if isinstance(entity.type, EntityTypeEnum)
            else str(entity.type),
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
        source_metadata = (
            dict(getattr(source_entity, "entity_metadata", {}) or {})
            if source_entity is not None
            else {}
        )
        target_metadata = (
            dict(getattr(target_entity, "entity_metadata", {}) or {})
            if target_entity is not None
            else {}
        )
        return {
            "id": str(relationship.id),
            "source_entity_id": str(relationship.source_entity_id),
            "target_entity_id": str(relationship.target_entity_id),
            "source_entity_name": getattr(source_entity, "name", "")
            if source_entity is not None
            else "",
            "target_entity_name": getattr(target_entity, "name", "")
            if target_entity is not None
            else "",
            "source_entity_type": str(
                source_metadata.get("raw_type")
                or getattr(
                    getattr(source_entity, "type", None),
                    "value",
                    getattr(source_entity, "type", "other"),
                )
                or "other"
            ),
            "target_entity_type": str(
                target_metadata.get("raw_type")
                or getattr(
                    getattr(target_entity, "type", None),
                    "value",
                    getattr(target_entity, "type", "other"),
                )
                or "other"
            ),
            "relationship_type": relationship.type.relationship_type
            if relationship.type
            else None,
            "relationship_name": relationship.type.relationship_name
            if relationship.type
            else None,
            "confidence": relationship.confidence,
            "created_by_module": relationship.created_by_module,
            "evidence": relationship.evidence,
            "relationship_metadata": dict(relationship.relationship_metadata or {}),
            "created_at": relationship.created_at.isoformat()
            if relationship.created_at
            else None,
        }

    # ---- 内部 ------------------------------------------------------------

    @staticmethod
    def _observe_document_source_prefix(cycle_id: str) -> str:
        return f"research://{cycle_id}/observe/"

    @staticmethod
    def _observe_document_source_file(
        cycle_id: str, document_index: int, payload: Mapping[str, Any]
    ) -> str:
        source_ref = str(
            payload.get("urn")
            or payload.get("title")
            or f"document_{document_index + 1}"
        ).strip()
        stable_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"{cycle_id}:observe:{document_index}:{source_ref}"
        )
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
            "catalog_id": str(
                version_metadata.get("catalog_id")
                or document_metadata.get("catalog_id")
                or ""
            ).strip(),
            "raw_text_preview": str(payload.get("raw_text_preview") or "")[:240],
            "processed_text_preview": str(payload.get("processed_text_preview") or "")[
                :240
            ],
            "processed_text_size": int(payload.get("processed_text_size") or 0),
            "metadata": dict(document_metadata or {}),
            "version_metadata": dict(version_metadata or {}),
            "philology": payload.get("philology")
            if isinstance(payload.get("philology"), dict)
            else {},
            "philology_notes": [
                str(note)
                for note in (payload.get("philology_notes") or [])
                if str(note).strip()
            ]
            if isinstance(payload.get("philology_notes"), list)
            else [],
            "philology_assets": payload.get("philology_assets")
            if isinstance(payload.get("philology_assets"), dict)
            else {},
            "output_generation": payload.get("output_generation")
            if isinstance(payload.get("output_generation"), dict)
            else {},
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
        version_metadata = self._extract_observe_document_version_metadata(
            payload, document_metadata
        )
        document_metadata["version_metadata"] = version_metadata
        source_type = (
            str(
                payload.get("source_type")
                or document_metadata.get("source_type")
                or version_metadata.get("source_type")
                or "observe"
            ).strip()
            or "observe"
        )
        document = Document(
            source_file=self._observe_document_source_file(
                cycle_id, document_index, payload
            ),
            document_urn=str(payload.get("urn") or "").strip() or None,
            document_title=str(payload.get("title") or "").strip() or None,
            source_type=source_type or None,
            catalog_id=str(version_metadata.get("catalog_id") or "").strip() or None,
            work_title=str(version_metadata.get("work_title") or "").strip() or None,
            fragment_title=str(version_metadata.get("fragment_title") or "").strip()
            or None,
            work_fragment_key=str(
                version_metadata.get("work_fragment_key") or ""
            ).strip()
            or None,
            version_lineage_key=str(
                version_metadata.get("version_lineage_key") or ""
            ).strip()
            or None,
            witness_key=str(version_metadata.get("witness_key") or "").strip() or None,
            dynasty=str(version_metadata.get("dynasty") or "").strip() or None,
            author=str(version_metadata.get("author") or "").strip() or None,
            edition=str(version_metadata.get("edition") or "").strip() or None,
            version_metadata_json=version_metadata,
            processing_timestamp=_parse_datetime(payload.get("processing_timestamp"))
            or datetime.now(timezone.utc),
            objective=research_session.research_objective
            or research_session.description
            or None,
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
    def _extract_observe_document_metadata(
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        metadata = (
            dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), Mapping)
            else {}
        )
        version_metadata = (
            payload.get("version_metadata")
            if isinstance(payload.get("version_metadata"), Mapping)
            else {}
        )
        if version_metadata and not isinstance(metadata.get("version_metadata"), dict):
            metadata["version_metadata"] = dict(version_metadata)
        return metadata

    def _extract_observe_document_version_metadata(
        self,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> Dict[str, Any]:
        existing_version_metadata = (
            metadata.get("version_metadata")
            if isinstance(metadata.get("version_metadata"), Mapping)
            else {}
        )
        source_type = (
            str(
                payload.get("source_type") or metadata.get("source_type") or "observe"
            ).strip()
            or "observe"
        )
        source_ref = str(
            payload.get("urn")
            or metadata.get("source_file")
            or payload.get("title")
            or "observe"
        ).strip()
        enriched_metadata = build_document_version_metadata(
            title=str(payload.get("title") or "").strip(),
            source_type=source_type,
            source_ref=source_ref,
            metadata={
                **dict(metadata),
                "version_metadata": dict(existing_version_metadata or {}),
                "catalog_id": metadata.get("catalog_id")
                or existing_version_metadata.get("catalog_id"),
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
            raw_type = (
                str(
                    entity_payload.get("type")
                    or entity_payload.get("entity_type")
                    or "other"
                )
                .strip()
                .lower()
            )
            metadata = dict(
                entity_payload.get("metadata")
                or entity_payload.get("entity_metadata")
                or {}
            )
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
                alternative_names=list(
                    entity_payload.get("alternative_names")
                    or entity_payload.get("aliases")
                    or []
                ),
                description=str(entity_payload.get("description") or "").strip()
                or None,
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
            source_entity = self._resolve_observe_entity(
                relationship_payload, entity_lookup, "source"
            )
            target_entity = self._resolve_observe_entity(
                relationship_payload, entity_lookup, "target"
            )
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
            relationship_metadata = dict(
                relationship_payload.get("metadata")
                or relationship_payload.get("relationship_metadata")
                or {}
            )
            relationship_metadata.update(
                {
                    "cycle_id": cycle_id,
                    "phase": "observe",
                    "phase_execution_id": str(phase_execution_id or "").strip() or None,
                    "document_id": str(document.id),
                    "document_urn": document_notes.get("urn"),
                    "document_title": document_notes.get("title"),
                    "source_type": str(
                        relationship_payload.get("source_type")
                        or self._entity_raw_type(source_entity)
                        or "entity"
                    ),
                    "target_type": str(
                        relationship_payload.get("target_type")
                        or self._entity_raw_type(target_entity)
                        or "entity"
                    ),
                }
            )
            relationship = EntityRelationship(
                source_entity_id=source_entity.id,
                target_entity_id=target_entity.id,
                relationship_type_id=relationship_type["id"],
                confidence=float(
                    relationship_payload.get("confidence")
                    or relationship_metadata.get("confidence")
                    or 0.5
                ),
                created_by_module=str(
                    relationship_payload.get("created_by_module")
                    or relationship_metadata.get("source")
                    or "observe_phase"
                ).strip()
                or None,
                evidence=str(
                    relationship_payload.get("evidence")
                    or relationship_metadata.get("description")
                    or ""
                ).strip()
                or None,
                relationship_metadata=relationship_metadata,
            )
            session.add(relationship)
            relationships.append(relationship)
        session.flush()
        return relationships

    def _list_observe_document_graphs(
        self, session: Session, cycle_id: str
    ) -> List[Dict[str, Any]]:
        documents = (
            self._observe_document_query(session, cycle_id)
            .order_by(Document.processing_timestamp.asc(), Document.created_at.asc())
            .all()
        )
        snapshots: List[Dict[str, Any]] = []
        for document in documents:
            entities = (
                session.query(Entity)
                .filter_by(document_id=document.id)
                .order_by(Entity.created_at.asc())
                .all()
            )
            entity_ids = [entity.id for entity in entities]
            relationships: List[EntityRelationship] = []
            if entity_ids:
                relationships = (
                    session.query(EntityRelationship)
                    .filter(EntityRelationship.source_entity_id.in_(entity_ids))
                    .order_by(EntityRelationship.created_at.asc())
                    .all()
                )
            snapshots.append(
                self._observe_document_to_dict(document, entities, relationships)
            )
        return snapshots

    def _observe_document_to_dict(
        self,
        document: Document,
        entities: Sequence[Entity],
        relationships: Sequence[EntityRelationship],
    ) -> Dict[str, Any]:
        notes = self._parse_observe_document_notes(document.notes)
        version_metadata = self._document_version_metadata(document, notes)
        metadata = (
            dict(notes.get("metadata") or {})
            if isinstance(notes.get("metadata"), dict)
            else {}
        )
        metadata["version_metadata"] = version_metadata
        if document.source_type and not metadata.get("source_type"):
            metadata["source_type"] = document.source_type
        if document.catalog_id and not metadata.get("catalog_id"):
            metadata["catalog_id"] = document.catalog_id
        entity_dicts = [self._entity_to_dict(entity) for entity in entities]
        relationship_dicts = [
            self._relationship_to_dict(relationship) for relationship in relationships
        ]
        return {
            "id": str(document.id),
            "source_file": document.source_file,
            "processing_timestamp": document.processing_timestamp.isoformat()
            if document.processing_timestamp
            else None,
            "objective": document.objective,
            "raw_text_size": document.raw_text_size,
            "entities_extracted_count": document.entities_extracted_count,
            "process_status": document.process_status.value
            if isinstance(document.process_status, ProcessStatusEnum)
            else str(document.process_status),
            "quality_score": document.quality_score,
            "cycle_id": notes.get("cycle_id"),
            "phase": notes.get("phase"),
            "phase_execution_id": notes.get("phase_execution_id"),
            "document_index": notes.get("document_index"),
            "urn": document.document_urn or notes.get("urn"),
            "title": document.document_title or notes.get("title"),
            "source_type": document.source_type
            or notes.get("source_type")
            or version_metadata.get("source_type"),
            "catalog_id": document.catalog_id
            or notes.get("catalog_id")
            or version_metadata.get("catalog_id"),
            "work_title": document.work_title or version_metadata.get("work_title"),
            "fragment_title": document.fragment_title
            or version_metadata.get("fragment_title"),
            "work_fragment_key": document.work_fragment_key
            or version_metadata.get("work_fragment_key"),
            "version_lineage_key": document.version_lineage_key
            or version_metadata.get("version_lineage_key"),
            "witness_key": document.witness_key or version_metadata.get("witness_key"),
            "dynasty": document.dynasty or version_metadata.get("dynasty"),
            "author": document.author or version_metadata.get("author"),
            "edition": document.edition or version_metadata.get("edition"),
            "raw_text_preview": notes.get("raw_text_preview"),
            "processed_text_preview": notes.get("processed_text_preview"),
            "processed_text_size": notes.get("processed_text_size"),
            "metadata": metadata,
            "version_metadata": version_metadata,
            "philology": notes.get("philology")
            if isinstance(notes.get("philology"), dict)
            else {},
            "philology_notes": notes.get("philology_notes")
            if isinstance(notes.get("philology_notes"), list)
            else [],
            "philology_assets": notes.get("philology_assets")
            if isinstance(notes.get("philology_assets"), dict)
            else {},
            "output_generation": notes.get("output_generation")
            if isinstance(notes.get("output_generation"), dict)
            else {},
            "entities": entity_dicts,
            "semantic_relationships": relationship_dicts,
            "entity_count": len(entity_dicts),
            "relationship_count": len(relationship_dicts),
        }

    def _writeback_observe_document_version_metadata(self, document: Document) -> bool:
        notes = self._parse_observe_document_notes(document.notes)
        version_metadata = self._document_version_metadata(document, notes)

        document_urn = (
            str(
                document.document_urn
                or notes.get("urn")
                or version_metadata.get("source_ref")
                or ""
            ).strip()
            or None
        )
        document_title = (
            str(
                document.document_title
                or notes.get("title")
                or version_metadata.get("fragment_title")
                or version_metadata.get("work_title")
                or ""
            ).strip()
            or None
        )
        source_type = (
            str(
                document.source_type
                or notes.get("source_type")
                or version_metadata.get("source_type")
                or self._infer_legacy_observe_source_type(
                    document_urn or document.source_file
                )
                or "observe"
            ).strip()
            or None
        )

        updated = False
        updated |= self._assign_if_changed(document, "document_urn", document_urn)
        updated |= self._assign_if_changed(document, "document_title", document_title)
        updated |= self._assign_if_changed(document, "source_type", source_type)
        updated |= self._assign_if_changed(
            document,
            "catalog_id",
            self._optional_version_value(version_metadata, "catalog_id"),
        )
        updated |= self._assign_if_changed(
            document,
            "work_title",
            self._optional_version_value(version_metadata, "work_title"),
        )
        updated |= self._assign_if_changed(
            document,
            "fragment_title",
            self._optional_version_value(version_metadata, "fragment_title"),
        )
        updated |= self._assign_if_changed(
            document,
            "work_fragment_key",
            self._optional_version_value(version_metadata, "work_fragment_key"),
        )
        updated |= self._assign_if_changed(
            document,
            "version_lineage_key",
            self._optional_version_value(version_metadata, "version_lineage_key"),
        )
        updated |= self._assign_if_changed(
            document,
            "witness_key",
            self._optional_version_value(version_metadata, "witness_key"),
        )
        updated |= self._assign_if_changed(
            document,
            "dynasty",
            self._optional_version_value(version_metadata, "dynasty"),
        )
        updated |= self._assign_if_changed(
            document, "author", self._optional_version_value(version_metadata, "author")
        )
        updated |= self._assign_if_changed(
            document,
            "edition",
            self._optional_version_value(version_metadata, "edition"),
        )
        updated |= self._assign_if_changed(
            document, "version_metadata_json", dict(version_metadata)
        )

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

        note_metadata = (
            dict(note_payload.get("metadata") or {})
            if isinstance(note_payload.get("metadata"), dict)
            else {}
        )
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
    def _optional_version_value(
        version_metadata: Mapping[str, Any], key: str
    ) -> Optional[str]:
        value = str(version_metadata.get(key) or "").strip()
        return value or None

    @staticmethod
    def _document_version_metadata(
        document: Document, notes: Mapping[str, Any]
    ) -> Dict[str, Any]:
        version_metadata = dict(document.version_metadata_json or {})
        note_version_metadata = (
            notes.get("version_metadata")
            if isinstance(notes.get("version_metadata"), dict)
            else {}
        )
        if not version_metadata and note_version_metadata:
            version_metadata = dict(note_version_metadata)

        note_metadata = (
            dict(notes.get("metadata") or {})
            if isinstance(notes.get("metadata"), dict)
            else {}
        )
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
        source_type = (
            str(
                version_metadata.get("source_type")
                or document.source_type
                or notes.get("source_type")
                or ResearchSessionRepository._infer_legacy_observe_source_type(
                    source_ref
                )
                or "observe"
            ).strip()
            or "observe"
        )
        title = str(
            version_metadata.get("fragment_title")
            or document.document_title
            or notes.get("title")
            or ""
        ).strip()
        catalog_id = str(
            version_metadata.get("catalog_id")
            or notes.get("catalog_id")
            or note_metadata.get("catalog_id")
            or ""
        ).strip()
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
        if normalized.endswith(
            (".txt", ".md", ".markdown", ".json", ".xml", ".html", ".htm")
        ):
            return "local"
        if "\\" in normalized or "/" in normalized:
            return "local"
        return "observe"

    @staticmethod
    def _group_observe_version_lineages(
        documents: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        seen_witnesses: set[tuple[str, str]] = set()

        for document in documents:
            if not isinstance(document, Mapping):
                continue
            version_metadata = (
                document.get("version_metadata")
                if isinstance(document.get("version_metadata"), Mapping)
                else {}
            )
            lineage_key = str(
                version_metadata.get("version_lineage_key")
                or version_metadata.get("work_fragment_key")
                or version_metadata.get("witness_key")
                or document.get("id")
                or ""
            ).strip()
            if not lineage_key:
                continue

            witness_key = str(
                version_metadata.get("witness_key")
                or document.get("id")
                or document.get("urn")
                or ""
            ).strip()
            if witness_key:
                seen_key = (lineage_key, witness_key)
                if seen_key in seen_witnesses:
                    continue
                seen_witnesses.add(seen_key)

            group = grouped.setdefault(
                lineage_key,
                {
                    "cycle_id": document.get("cycle_id"),
                    "version_lineage_key": str(
                        version_metadata.get("version_lineage_key") or lineage_key
                    ).strip(),
                    "work_fragment_key": str(
                        version_metadata.get("work_fragment_key") or ""
                    ).strip(),
                    "work_title": str(
                        version_metadata.get("work_title")
                        or document.get("work_title")
                        or ""
                    ).strip(),
                    "fragment_title": str(
                        version_metadata.get("fragment_title")
                        or document.get("fragment_title")
                        or ""
                    ).strip(),
                    "dynasty": str(
                        version_metadata.get("dynasty") or document.get("dynasty") or ""
                    ).strip(),
                    "author": str(
                        version_metadata.get("author") or document.get("author") or ""
                    ).strip(),
                    "edition": str(
                        version_metadata.get("edition") or document.get("edition") or ""
                    ).strip(),
                    "witnesses": [],
                },
            )
            group["witnesses"].append(
                {
                    "document_id": document.get("id"),
                    "urn": document.get("urn"),
                    "title": document.get("title"),
                    "source_type": document.get("source_type"),
                    "catalog_id": version_metadata.get("catalog_id")
                    or document.get("catalog_id"),
                    "witness_key": witness_key,
                    "dynasty": version_metadata.get("dynasty")
                    or document.get("dynasty"),
                    "author": version_metadata.get("author") or document.get("author"),
                    "edition": version_metadata.get("edition")
                    or document.get("edition"),
                }
            )

        ordered = sorted(
            grouped.values(),
            key=lambda item: str(
                item.get("version_lineage_key") or item.get("work_fragment_key") or ""
            ),
        )
        for item in ordered:
            item["witness_count"] = len(item.get("witnesses") or [])
        return ordered

    @classmethod
    def _observe_document_query(
        cls,
        session: Session,
        cycle_id: Optional[str] = None,
    ):
        source_pattern = (
            f"{cls._observe_document_source_prefix(cycle_id)}%"
            if cycle_id
            else "research://%/observe/%"
        )
        return session.query(Document).filter(Document.source_file.like(source_pattern))

    def _delete_observe_document_graphs(self, session: Session, cycle_id: str) -> None:
        document_ids = [
            row[0]
            for row in self._observe_document_query(session, cycle_id)
            .with_entities(Document.id)
            .all()
        ]
        if not document_ids:
            return

        entity_ids = [
            row[0]
            for row in session.query(Entity.id)
            .filter(Entity.document_id.in_(document_ids))
            .all()
        ]
        if entity_ids:
            session.query(EntityRelationship).filter(
                (EntityRelationship.source_entity_id.in_(entity_ids))
                | (EntityRelationship.target_entity_id.in_(entity_ids))
            ).delete(synchronize_session=False)
        session.query(Entity).filter(Entity.document_id.in_(document_ids)).delete(
            synchronize_session=False
        )
        session.query(ProcessingLog).filter(
            ProcessingLog.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        session.query(ProcessingStatistics).filter(
            ProcessingStatistics.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        session.query(QualityMetrics).filter(
            QualityMetrics.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        session.query(ResearchAnalysis).filter(
            ResearchAnalysis.document_id.in_(document_ids)
        ).delete(synchronize_session=False)
        session.query(Document).filter(Document.id.in_(document_ids)).delete(
            synchronize_session=False
        )
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

    def _build_observe_entity_lookup(
        self, entities: Sequence[Entity]
    ) -> Dict[str, Entity]:
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
        direct_id = str(
            payload.get(f"{prefix}_entity_id") or payload.get(f"{prefix}_id") or ""
        ).strip()
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
        return str(
            metadata.get("raw_type")
            or (
                entity.type.value
                if isinstance(entity.type, EntityTypeEnum)
                else str(entity.type)
            )
            or "other"
        )

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
