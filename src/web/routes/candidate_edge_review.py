from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.infrastructure.persistence import DatabaseManager, LearningInsight
from src.learning.kg_node_self_learning import (
    KG_NODE_SELF_LEARNING_CONTRACT_VERSION,
    KGNodeSelfLearningEnhancer,
)
from src.learning.learning_insight_repo import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    LearningInsightRepo,
    normalize_status,
)
from src.learning.weak_edge_candidate_repo import (
    COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES,
    extract_weak_edge_candidate_payload,
)
from src.web.auth import get_current_user

router = APIRouter(prefix="/api/review/candidate-edges", tags=["candidate-edge-review"])


class CandidateEdgeReviewRequest(BaseModel):
    reviewer: Optional[str] = Field(default=None, max_length=100)
    reason: Optional[str] = Field(default=None, max_length=2000)
    decision_basis: Optional[str] = Field(default=None, max_length=4000)
    grounding_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_grade: Optional[str] = Field(default=None, max_length=16)
    graph_rag_context: Optional[Dict[str, Any]] = None
    repeated_error_type: Optional[str] = Field(default=None, max_length=120)
    corrected_relationship_type: Optional[str] = Field(default=None, max_length=120)
    merge_target_relationship_id: Optional[str] = Field(default=None, max_length=128)
    merge_target_candidate_edge_id: Optional[str] = Field(default=None, max_length=128)
    dry_run: bool = False


@router.get("")
async def list_candidate_edges(
    request: Request,
    status: str = Query(
        "needs_review", description="needs_review/active/accepted/rejected/all"
    ),
    limit: int = Query(50, ge=1, le=200),
    _current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = _get_db(request)
    normalized_status = _normalize_status_filter(status)
    with db.session_scope() as session:
        duplicate_counts = _candidate_duplicate_counts(
            session.query(LearningInsight)
            .filter(
                LearningInsight.insight_type.in_(
                    list(COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES)
                )
            )
            .all()
        )
        query = session.query(LearningInsight).filter(
            LearningInsight.insight_type.in_(list(COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES))
        )
        if normalized_status != "all":
            if normalized_status == "pending":
                query = query.filter(
                    LearningInsight.status.in_(["needs_review", "active"])
                )
            else:
                query = query.filter(LearningInsight.status == normalized_status)
        rows = (
            query.order_by(
                LearningInsight.confidence.desc(), LearningInsight.created_at.desc()
            )
            .limit(limit)
            .all()
        )
        items = [
            _format_candidate_item(
                _row_to_payload(row), duplicate_counts=duplicate_counts
            )
            for row in rows
        ]
    return {"items": items, "count": len(items), "status": normalized_status}


@router.get("/{insight_id:path}")
async def get_candidate_edge(
    request: Request,
    insight_id: str,
    _current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = _get_db(request)
    payload = _load_candidate_payload(db, insight_id)
    return _format_candidate_item(payload, duplicate_counts=_load_duplicate_counts(db))


@router.post("/{insight_id:path}/accept")
async def accept_candidate_edge(
    request: Request,
    insight_id: str,
    body: CandidateEdgeReviewRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = _get_db(request)
    payload = _load_candidate_payload(db, insight_id)
    candidate = _extract_candidate(payload)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate edge not found")
    if body.corrected_relationship_type:
        candidate["relationship_type"] = (
            body.corrected_relationship_type.strip().upper()
        )
    reviewer = _resolve_reviewer(body, current_user)
    enhancer = KGNodeSelfLearningEnhancer(
        db,
        learning_insight_repo=LearningInsightRepo(db),
        neo4j_driver=_get_neo4j_driver(request),
    )
    apply_result = enhancer.apply_reviewed_edges(
        [
            {
                "review_status": STATUS_ACCEPTED,
                "candidate_edge": candidate,
                "decision_basis": body.decision_basis or body.reason or "",
            }
        ],
        reviewer=reviewer,
        dry_run=body.dry_run,
    )
    updated = LearningInsightRepo(db).record_review_decision(
        insight_id,
        STATUS_ACCEPTED,
        reviewer=reviewer,
        reason=body.reason or body.decision_basis,
        decision_type="accept",
        feedback={
            "candidate_edge": candidate,
            "apply_result": apply_result,
            "relationship_ids": _applied_relationship_ids(apply_result),
            "node_ids": _candidate_node_ids(candidate),
            "grounding_score": body.grounding_score,
            "evidence_grade": body.evidence_grade,
            "graph_rag_context": body.graph_rag_context or {},
        },
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="candidate edge not found")
    return {
        "status": STATUS_ACCEPTED,
        "apply_result": apply_result,
        "item": _format_candidate_item(
            updated, duplicate_counts=_load_duplicate_counts(db)
        ),
    }


@router.post("/{insight_id:path}/reject")
async def reject_candidate_edge(
    request: Request,
    insight_id: str,
    body: CandidateEdgeReviewRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return _record_negative_decision(
        request,
        insight_id,
        body,
        current_user,
        decision_type="reject",
        status=STATUS_REJECTED,
    )


@router.post("/{insight_id:path}/merge")
async def merge_candidate_edge(
    request: Request,
    insight_id: str,
    body: CandidateEdgeReviewRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if (
        not body.merge_target_relationship_id
        and not body.merge_target_candidate_edge_id
    ):
        raise HTTPException(status_code=422, detail="merge target is required")
    return _record_negative_decision(
        request,
        insight_id,
        body,
        current_user,
        decision_type="merge",
        status=STATUS_SUPERSEDED,
        extra_feedback={
            "merge_target_relationship_id": body.merge_target_relationship_id,
            "merge_target_candidate_edge_id": body.merge_target_candidate_edge_id,
        },
    )


@router.post("/{insight_id:path}/relationship-type-error")
async def mark_relationship_type_error(
    request: Request,
    insight_id: str,
    body: CandidateEdgeReviewRequest,
    current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return _record_negative_decision(
        request,
        insight_id,
        body,
        current_user,
        decision_type="relationship_type_error",
        status=STATUS_REJECTED,
        extra_feedback={
            "repeated_error_type": body.repeated_error_type
            or "relationship_type_error",
            "corrected_relationship_type": body.corrected_relationship_type,
        },
    )


def _record_negative_decision(
    request: Request,
    insight_id: str,
    body: CandidateEdgeReviewRequest,
    current_user: Mapping[str, Any],
    *,
    decision_type: str,
    status: str,
    extra_feedback: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    db = _get_db(request)
    payload = _load_candidate_payload(db, insight_id)
    candidate = _extract_candidate(payload)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate edge not found")
    reviewer = _resolve_reviewer(body, current_user)
    feedback = {
        "candidate_edge": candidate,
        "node_ids": _candidate_node_ids(candidate),
        "grounding_score": body.grounding_score,
        "evidence_grade": body.evidence_grade,
        "graph_rag_context": body.graph_rag_context or {},
        "repeated_error_type": body.repeated_error_type,
    }
    if isinstance(extra_feedback, Mapping):
        feedback.update({str(key): value for key, value in extra_feedback.items()})
    updated = LearningInsightRepo(db).record_review_decision(
        insight_id,
        status,
        reviewer=reviewer,
        reason=body.reason or body.decision_basis,
        decision_type=decision_type,
        feedback=feedback,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="candidate edge not found")
    return {
        "status": normalize_status(status),
        "item": _format_candidate_item(
            updated, duplicate_counts=_load_duplicate_counts(db)
        ),
    }


def _get_db(request: Request) -> DatabaseManager:
    db = getattr(request.app.state, "db_manager", None)
    if db is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    return db


def _get_neo4j_driver(request: Request) -> Any:
    direct = getattr(request.app.state, "neo4j_driver", None)
    if direct is not None:
        return direct
    storage_factory = getattr(request.app.state, "storage_factory", None)
    if storage_factory is None:
        monitoring = getattr(request.app.state, "monitoring_service", None)
        storage_factory = getattr(monitoring, "_storage_factory", None)
    return getattr(storage_factory, "neo4j_driver", None)


def _normalize_status_filter(value: str) -> str:
    text = str(value or "needs_review").strip().lower()
    if text in {"all", "*"}:
        return "all"
    if text in {"pending", "needs_review", "active"}:
        return "pending"
    return normalize_status(text)


def _load_candidate_payload(db: DatabaseManager, insight_id: str) -> Dict[str, Any]:
    with db.session_scope() as session:
        row = session.get(LearningInsight, str(insight_id))
        if row is None or row.insight_type not in COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES:
            raise HTTPException(status_code=404, detail="candidate edge not found")
        return _row_to_payload(row)


def _load_duplicate_counts(db: DatabaseManager) -> Dict[str, int]:
    with db.session_scope() as session:
        rows = (
            session.query(LearningInsight)
            .filter(
                LearningInsight.insight_type.in_(
                    list(COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES)
                )
            )
            .all()
        )
        return _candidate_duplicate_counts(rows)


def _candidate_duplicate_counts(rows: Sequence[LearningInsight]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        candidate = _extract_candidate(_row_to_payload(row))
        key = _candidate_key(candidate)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _row_to_payload(row: LearningInsight) -> Dict[str, Any]:
    return {
        "insight_id": row.insight_id,
        "source": row.source,
        "target_phase": row.target_phase,
        "insight_type": row.insight_type,
        "description": row.description,
        "confidence": float(row.confidence or 0.0),
        "evidence_refs_json": list(row.evidence_refs_json or []),
        "status": normalize_status(row.status),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _format_candidate_item(
    payload: Mapping[str, Any],
    *,
    duplicate_counts: Optional[Mapping[str, int]] = None,
) -> Dict[str, Any]:
    candidate = _extract_candidate(payload)
    weak_edge_payload = extract_weak_edge_candidate_payload(payload)
    refs = [
        dict(item)
        for item in payload.get("evidence_refs_json") or []
        if isinstance(item, Mapping)
    ]
    review_events = [
        item for item in refs if item.get("type") == "expert_review_feedback"
    ]
    key = _candidate_key(candidate)
    return {
        "contract_version": KG_NODE_SELF_LEARNING_CONTRACT_VERSION,
        "insight_id": payload.get("insight_id"),
        "candidate_edge_id": candidate.get("candidate_edge_id"),
        "status": normalize_status(payload.get("status")),
        "source": payload.get("source"),
        "target_phase": payload.get("target_phase"),
        "created_at": payload.get("created_at"),
        "confidence": float(
            payload.get("confidence") or candidate.get("confidence") or 0.0
        ),
        "entity_pair": {
            "source_entity_id": candidate.get("source_entity_id"),
            "target_entity_id": candidate.get("target_entity_id"),
            "source_name": candidate.get("source_name"),
            "target_name": candidate.get("target_name"),
            "source_type": candidate.get("source_type"),
            "target_type": candidate.get("target_type"),
        },
        "candidate_relation": candidate.get("relationship_type"),
        "candidate_edge": candidate,
        "evidence_fragments": _extract_evidence_fragments(candidate, refs),
        "generation_reason": _generation_reason(payload, candidate),
        "signals": list(candidate.get("signals") or []),
        "historical_repeat_count": int(
            (weak_edge_payload.get("duplicate_count") or 0)
            or ((duplicate_counts or {}).get(key, 1) if key else 1)
        ),
        "graph_rag_context": _extract_graph_rag_context(candidate, refs),
        "review_events": review_events,
    }


def _extract_candidate(payload: Mapping[str, Any]) -> Dict[str, Any]:
    weak_edge_payload = extract_weak_edge_candidate_payload(payload)
    if weak_edge_payload:
        candidate = dict(weak_edge_payload.get("candidate_edge") or {})
        if str(candidate.get("candidate_edge_id") or "").strip():
            return candidate
    refs = payload.get("evidence_refs_json") or payload.get("evidence_refs") or []
    if isinstance(payload.get("candidate_edge"), Mapping):
        candidate = dict(payload["candidate_edge"])
    elif isinstance(refs, list) and refs:
        first = refs[0]
        candidate = dict(first) if isinstance(first, Mapping) else {}
        if isinstance(candidate.get("candidate_edge"), Mapping):
            candidate = dict(candidate["candidate_edge"])
    else:
        candidate = {}
    if not str(candidate.get("candidate_edge_id") or "").strip():
        return {}
    return candidate


def _candidate_key(candidate: Mapping[str, Any]) -> str:
    parts = [
        candidate.get("source_entity_id"),
        candidate.get("target_entity_id"),
        str(candidate.get("relationship_type") or "").upper(),
    ]
    text = "|".join(str(item or "").strip() for item in parts)
    return text if "||" not in text and text.strip("|") else ""


def _candidate_node_ids(candidate: Mapping[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("source_entity_id", "target_entity_id"):
        text = str(candidate.get(key) or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def _extract_evidence_fragments(
    candidate: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    fragments: List[Dict[str, Any]] = []
    evidence = (
        candidate.get("evidence")
        if isinstance(candidate.get("evidence"), Mapping)
        else {}
    )
    for key in ("snippet", "evidence_snippet", "text", "excerpt", "source_text"):
        value = str(evidence.get(key) or candidate.get(key) or "").strip()
        if value:
            fragments.append({"text": value, "source": key})
    for ref in refs:
        for key in ("snippet", "evidence_snippet", "excerpt", "text"):
            value = str(ref.get(key) or "").strip()
            if value:
                fragments.append(
                    {"text": value, "source": str(ref.get("source") or key)}
                )
    if fragments:
        return fragments[:8]
    signals = ", ".join(str(item) for item in candidate.get("signals") or [])
    if signals:
        return [{"text": signals, "source": "signals"}]
    return []


def _generation_reason(payload: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    parts = [str(payload.get("description") or "").strip()]
    parts.extend(
        str(item).strip()
        for item in candidate.get("signals") or []
        if str(item).strip()
    )
    evidence = (
        candidate.get("evidence")
        if isinstance(candidate.get("evidence"), Mapping)
        else {}
    )
    for key in (
        "middle_entity_id",
        "first_relationship_type",
        "second_relationship_type",
    ):
        if evidence.get(key):
            parts.append(f"{key}={evidence[key]}")
    return "；".join(dict.fromkeys(part for part in parts if part))


def _extract_graph_rag_context(
    candidate: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    for source in (candidate, *refs):
        graph_context = (
            source.get("graph_rag_context") if isinstance(source, Mapping) else None
        )
        if isinstance(graph_context, Mapping):
            return dict(graph_context)
    return {
        "node_ids": _candidate_node_ids(candidate),
        "relationship_type": candidate.get("relationship_type"),
        "context_status": "not_attached",
    }


def _resolve_reviewer(
    body: CandidateEdgeReviewRequest, current_user: Mapping[str, Any]
) -> str:
    explicit = str(body.reviewer or "").strip()
    if explicit:
        return explicit
    for key in ("display_name", "username", "user_id", "sub"):
        value = str(current_user.get(key) or "").strip()
        if value:
            return value
    return "expert_review"


def _applied_relationship_ids(apply_result: Mapping[str, Any]) -> List[str]:
    ids: List[str] = []
    for item in apply_result.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        relationship_id = str(item.get("relationship_id") or "").strip()
        if relationship_id and relationship_id not in ids:
            ids.append(relationship_id)
    return ids


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
