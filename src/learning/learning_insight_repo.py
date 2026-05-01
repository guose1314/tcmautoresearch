from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from src.infrastructure.persistence import DatabaseManager, LearningInsight

STATUS_ACTIVE = "active"
STATUS_REVIEWED = "reviewed"
STATUS_EXPIRED = "expired"


class LearningInsightRepo:
    """Repository for reviewable, expirable unsupervised learning insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        if db_manager is None:
            raise ValueError("db_manager is required")
        self._db = db_manager

    def upsert(
        self,
        insight: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        payload = {**dict(insight or {}), **kwargs}
        insight_id = str(payload.get("insight_id") or "").strip()
        if not insight_id:
            raise ValueError("insight_id is required")

        with self._db.session_scope() as session:
            row = session.get(LearningInsight, insight_id)
            if row is None:
                row = LearningInsight(insight_id=insight_id)
                session.add(row)
            row.source = _required_text(payload, "source")
            row.target_phase = _required_text(payload, "target_phase")
            row.insight_type = _required_text(payload, "insight_type")
            row.description = _required_text(payload, "description")
            row.confidence = _clamp_confidence(payload.get("confidence"))
            row.evidence_refs_json = _normalize_evidence_refs(
                payload.get("evidence_refs_json", payload.get("evidence_refs"))
            )
            row.status = str(payload.get("status") or STATUS_ACTIVE).strip().lower()
            row.expires_at = _coerce_datetime(payload.get("expires_at"))
            if payload.get("created_at") is not None:
                row.created_at = _coerce_datetime(payload.get("created_at")) or _now()
            session.flush()
            return _row_to_dict(row)

    def list_active(
        self,
        target_phase: Optional[str] = None,
        *,
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        effective_now = _coerce_datetime(now) or _now()
        with self._db.session_scope() as session:
            query = session.query(LearningInsight).filter(
                LearningInsight.status == STATUS_ACTIVE
            )
            if target_phase:
                query = query.filter(LearningInsight.target_phase == str(target_phase))
            query = query.filter(
                (LearningInsight.expires_at.is_(None))
                | (LearningInsight.expires_at > effective_now)
            )
            rows = (
                query.order_by(
                    LearningInsight.confidence.desc(),
                    LearningInsight.created_at.desc(),
                )
                .limit(max(int(limit or 0), 0))
                .all()
            )
            return [_row_to_dict(row) for row in rows]

    def mark_reviewed(self, insight_id: str) -> Optional[Dict[str, Any]]:
        with self._db.session_scope() as session:
            row = session.get(LearningInsight, str(insight_id))
            if row is None:
                return None
            row.status = STATUS_REVIEWED
            session.flush()
            return _row_to_dict(row)

    def expire_old(self, *, now: Optional[datetime] = None) -> int:
        effective_now = _coerce_datetime(now) or _now()
        with self._db.session_scope() as session:
            rows = (
                session.query(LearningInsight)
                .filter(LearningInsight.status == STATUS_ACTIVE)
                .filter(LearningInsight.expires_at.isnot(None))
                .filter(LearningInsight.expires_at <= effective_now)
                .all()
            )
            for row in rows:
                row.status = STATUS_EXPIRED
            return len(rows)


def _row_to_dict(row: LearningInsight) -> Dict[str, Any]:
    return {
        "insight_id": row.insight_id,
        "source": row.source,
        "target_phase": row.target_phase,
        "insight_type": row.insight_type,
        "description": row.description,
        "confidence": float(row.confidence or 0.0),
        "evidence_refs_json": list(row.evidence_refs_json or []),
        "status": row.status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _normalize_evidence_refs(value: Any) -> List[Dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return [{"ref": str(value)}]


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "LearningInsightRepo",
    "STATUS_ACTIVE",
    "STATUS_EXPIRED",
    "STATUS_REVIEWED",
]
