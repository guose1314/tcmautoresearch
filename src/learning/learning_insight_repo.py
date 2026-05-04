from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.infrastructure.persistence import DatabaseManager, LearningInsight

STATUS_ACTIVE = "active"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"
STATUS_SUPERSEDED = "superseded"
STATUS_REVIEWED = STATUS_ACCEPTED

LEGACY_STATUS_REVIEWED = "reviewed"

PROMPT_BIAS_ELIGIBLE_STATUSES = frozenset({STATUS_ACTIVE, STATUS_ACCEPTED})
REJECTED_NEGATIVE_STATUSES = frozenset({STATUS_REJECTED})
EXPIRABLE_STATUSES = frozenset(
    {STATUS_ACTIVE, STATUS_NEEDS_REVIEW, STATUS_ACCEPTED, LEGACY_STATUS_REVIEWED}
)

_ALLOWED_STATUSES = frozenset(
    {
        STATUS_ACTIVE,
        STATUS_NEEDS_REVIEW,
        STATUS_ACCEPTED,
        STATUS_REJECTED,
        STATUS_EXPIRED,
        STATUS_SUPERSEDED,
    }
)

DEFAULT_THRESHOLD_POLICY: Dict[str, Any] = {
    "min_repeat_count": 1,
    "min_evidence_source_count": 0,
    "min_expert_vote_score": 0,
    "reject_below_expert_vote_score": -1,
    "expire_after_days": None,
}


class LearningInsightRepo:
    """Repository for reviewable, expirable unsupervised learning insights."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        *,
        threshold_policy: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if db_manager is None:
            raise ValueError("db_manager is required")
        self._db = db_manager
        self._threshold_policy = _merge_threshold_policy(threshold_policy)

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
            existing_status = row.status if row is not None else None
            if row is None:
                row = LearningInsight(insight_id=insight_id)
                session.add(row)
            evidence_refs = _normalize_evidence_refs(
                payload.get("evidence_refs_json", payload.get("evidence_refs"))
            )
            created_at = _coerce_datetime(payload.get("created_at"))
            if created_at is None and row.created_at is not None:
                created_at = row.created_at
            created_at = created_at or _now()
            expires_at = _coerce_datetime(payload.get("expires_at"))
            row.source = _required_text(payload, "source")
            row.target_phase = _required_text(payload, "target_phase")
            row.insight_type = _required_text(payload, "insight_type")
            row.description = _required_text(payload, "description")
            row.confidence = _clamp_confidence(payload.get("confidence"))
            row.evidence_refs_json = evidence_refs
            row.status = _resolve_status(
                payload,
                evidence_refs=evidence_refs,
                created_at=created_at,
                expires_at=expires_at,
                existing_status=existing_status,
                threshold_policy=self._threshold_policy,
            )
            row.expires_at = expires_at
            row.created_at = created_at
            session.flush()
            return _row_to_dict(row, threshold_policy=self._threshold_policy)

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
            return [
                _row_to_dict(row, threshold_policy=self._threshold_policy)
                for row in rows
            ]

    def list_prompt_bias_eligible(
        self,
        target_phase: Optional[str] = None,
        *,
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        effective_now = _coerce_datetime(now) or _now()
        with self._db.session_scope() as session:
            query = session.query(LearningInsight).filter(
                LearningInsight.status.in_(
                    [
                        STATUS_ACTIVE,
                        STATUS_ACCEPTED,
                        LEGACY_STATUS_REVIEWED,
                    ]
                )
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
            return [
                _row_to_dict(row, threshold_policy=self._threshold_policy)
                for row in rows
                if not _is_expired_by_policy(
                    row.created_at,
                    row.expires_at,
                    now=effective_now,
                    threshold_policy=self._threshold_policy,
                )
            ]

    def list_rejected(
        self,
        target_phase: Optional[str] = None,
        *,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with self._db.session_scope() as session:
            query = session.query(LearningInsight).filter(
                LearningInsight.status == STATUS_REJECTED
            )
            if target_phase:
                query = query.filter(LearningInsight.target_phase == str(target_phase))
            rows = (
                query.order_by(
                    LearningInsight.confidence.desc(),
                    LearningInsight.created_at.desc(),
                )
                .limit(max(int(limit or 0), 0))
                .all()
            )
            return [
                _row_to_dict(row, threshold_policy=self._threshold_policy)
                for row in rows
            ]

    def mark_reviewed(self, insight_id: str) -> Optional[Dict[str, Any]]:
        return self.transition(insight_id, STATUS_ACCEPTED)

    def transition(
        self,
        insight_id: str,
        status: str,
        *,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = normalize_status(status)
        with self._db.session_scope() as session:
            row = session.get(LearningInsight, str(insight_id))
            if row is None:
                return None
            row.status = normalized_status
            if reason:
                refs = list(row.evidence_refs_json or [])
                refs.append(
                    {
                        "type": "lifecycle_transition",
                        "status": normalized_status,
                        "reason": str(reason),
                        "created_at": _now().isoformat(),
                    }
                )
                row.evidence_refs_json = refs
            session.flush()
            return _row_to_dict(row, threshold_policy=self._threshold_policy)

    def record_review_decision(
        self,
        insight_id: str,
        status: str,
        *,
        reviewer: Optional[str] = None,
        reason: Optional[str] = None,
        decision_type: str = "expert_review",
        feedback: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = normalize_status(status)
        vote = "accepted" if normalized_status == STATUS_ACCEPTED else "rejected"
        payload: Dict[str, Any] = {
            "type": "expert_review_feedback",
            "decision_type": str(decision_type or "expert_review").strip()
            or "expert_review",
            "review_status": normalized_status,
            "expert_vote": vote,
            "created_at": _now().isoformat(),
        }
        if reviewer:
            payload["reviewer"] = str(reviewer)
        if reason:
            payload["reason"] = str(reason)
        if isinstance(feedback, Mapping):
            payload.update({str(key): value for key, value in feedback.items()})

        with self._db.session_scope() as session:
            row = session.get(LearningInsight, str(insight_id))
            if row is None:
                return None
            refs = list(row.evidence_refs_json or [])
            refs.append(payload)
            row.evidence_refs_json = refs
            row.status = normalized_status
            session.flush()
            return _row_to_dict(row, threshold_policy=self._threshold_policy)

    def migrate_legacy_statuses(self) -> int:
        with self._db.session_scope() as session:
            rows = (
                session.query(LearningInsight)
                .filter(LearningInsight.status == LEGACY_STATUS_REVIEWED)
                .all()
            )
            for row in rows:
                row.status = STATUS_ACCEPTED
            return len(rows)

    def apply_threshold_policy(
        self, *, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        effective_now = _coerce_datetime(now) or _now()
        inspected = 0
        transitioned: Dict[str, int] = {}
        with self._db.session_scope() as session:
            rows = session.query(LearningInsight).all()
            for row in rows:
                inspected += 1
                before = normalize_status(row.status)
                desired = _resolve_status(
                    _row_to_payload(row),
                    evidence_refs=list(row.evidence_refs_json or []),
                    created_at=row.created_at,
                    expires_at=row.expires_at,
                    existing_status=row.status,
                    threshold_policy=self._threshold_policy,
                    force_policy=True,
                    now=effective_now,
                )
                if desired == before:
                    continue
                row.status = desired
                transitioned[desired] = transitioned.get(desired, 0) + 1
            return {"inspected": inspected, "transitioned": transitioned}

    def expire_old(self, *, now: Optional[datetime] = None) -> int:
        effective_now = _coerce_datetime(now) or _now()
        with self._db.session_scope() as session:
            rows = (
                session.query(LearningInsight)
                .filter(LearningInsight.status.in_(list(EXPIRABLE_STATUSES)))
                .all()
            )
            expired = 0
            for row in rows:
                if not _is_expired_by_policy(
                    row.created_at,
                    row.expires_at,
                    now=effective_now,
                    threshold_policy=self._threshold_policy,
                ):
                    continue
                row.status = STATUS_EXPIRED
                expired += 1
            return expired


def _row_to_dict(
    row: LearningInsight,
    *,
    threshold_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    evidence_refs = list(row.evidence_refs_json or [])
    metrics = evaluate_threshold_policy(
        {
            **_row_to_payload(row),
            "evidence_refs_json": evidence_refs,
        },
        threshold_policy=threshold_policy,
    )["metrics"]
    return {
        "insight_id": row.insight_id,
        "source": row.source,
        "target_phase": row.target_phase,
        "insight_type": row.insight_type,
        "description": row.description,
        "confidence": float(row.confidence or 0.0),
        "evidence_refs_json": evidence_refs,
        "status": normalize_status(row.status),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "lifecycle_metrics": metrics,
    }


def _row_to_payload(row: LearningInsight) -> Dict[str, Any]:
    return {
        "insight_id": row.insight_id,
        "source": row.source,
        "target_phase": row.target_phase,
        "insight_type": row.insight_type,
        "description": row.description,
        "confidence": row.confidence,
        "evidence_refs_json": list(row.evidence_refs_json or []),
        "status": row.status,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }


def normalize_status(value: Any) -> str:
    text = str(value or STATUS_ACTIVE).strip().lower()
    if text == LEGACY_STATUS_REVIEWED:
        return STATUS_ACCEPTED
    if text in _ALLOWED_STATUSES:
        return text
    return STATUS_NEEDS_REVIEW


def evaluate_threshold_policy(
    payload: Mapping[str, Any],
    *,
    threshold_policy: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    policy = _merge_threshold_policy(threshold_policy)
    evidence_refs = _normalize_evidence_refs(
        payload.get("evidence_refs_json", payload.get("evidence_refs"))
    )
    metrics = _extract_lifecycle_metrics(payload, evidence_refs=evidence_refs)
    effective_now = _coerce_datetime(now) or _now()
    created_at = _coerce_datetime(payload.get("created_at"))
    expires_at = _coerce_datetime(payload.get("expires_at"))

    if _is_expired_by_policy(
        created_at,
        expires_at,
        now=effective_now,
        threshold_policy=policy,
    ):
        proposed_status = STATUS_EXPIRED
    elif metrics["expert_vote_score"] <= _int_policy(
        policy, "reject_below_expert_vote_score", -1
    ):
        proposed_status = STATUS_REJECTED
    elif (
        metrics["repeat_count"] < _int_policy(policy, "min_repeat_count", 1)
        or metrics["evidence_source_count"]
        < _int_policy(policy, "min_evidence_source_count", 0)
        or metrics["expert_vote_score"]
        < _int_policy(policy, "min_expert_vote_score", 0)
    ):
        proposed_status = STATUS_NEEDS_REVIEW
    else:
        proposed_status = STATUS_ACTIVE

    return {
        "status": proposed_status,
        "metrics": metrics,
        "policy": dict(policy),
    }


def _resolve_status(
    payload: Mapping[str, Any],
    *,
    evidence_refs: Sequence[Mapping[str, Any]],
    created_at: Optional[datetime],
    expires_at: Optional[datetime],
    existing_status: Optional[str],
    threshold_policy: Mapping[str, Any],
    force_policy: bool = False,
    now: Optional[datetime] = None,
) -> str:
    explicit = payload.get("status")
    if explicit not in (None, "") and not force_policy:
        status = normalize_status(explicit)
    else:
        status = normalize_status(existing_status or STATUS_ACTIVE)

    effective_now = _coerce_datetime(now) or _now()
    if status in {STATUS_REJECTED, STATUS_SUPERSEDED} and not force_policy:
        return status
    if status == STATUS_EXPIRED and not force_policy:
        return status
    if _is_expired_by_policy(
        created_at,
        expires_at,
        now=effective_now,
        threshold_policy=threshold_policy,
    ):
        return STATUS_EXPIRED
    if status == STATUS_ACCEPTED and not force_policy:
        return status

    policy_result = evaluate_threshold_policy(
        {
            **dict(payload),
            "evidence_refs_json": list(evidence_refs),
            "created_at": created_at,
            "expires_at": expires_at,
        },
        threshold_policy=threshold_policy,
        now=effective_now,
    )
    proposed = str(policy_result.get("status") or STATUS_ACTIVE)
    if force_policy:
        if status == STATUS_ACCEPTED and proposed not in {
            STATUS_EXPIRED,
            STATUS_REJECTED,
        }:
            return STATUS_ACCEPTED
        if status in {STATUS_REJECTED, STATUS_SUPERSEDED}:
            return status
        return normalize_status(proposed)
    if explicit not in (None, ""):
        return status
    return normalize_status(proposed)


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


def _merge_threshold_policy(
    threshold_policy: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    merged = dict(DEFAULT_THRESHOLD_POLICY)
    if isinstance(threshold_policy, Mapping):
        merged.update({str(key): value for key, value in threshold_policy.items()})
    return merged


def _extract_lifecycle_metrics(
    payload: Mapping[str, Any],
    *,
    evidence_refs: Sequence[Mapping[str, Any]],
) -> Dict[str, int]:
    repeat_count = _first_int(
        payload,
        (
            "repeat_count",
            "occurrence_count",
            "occurrences",
            "support_count",
            "support",
            "occurrence_freq",
            "frequency",
        ),
    )
    if repeat_count is None:
        repeat_count = max(len(evidence_refs), 1)

    evidence_source_count = _first_int(
        payload,
        ("evidence_source_count", "source_count", "document_count"),
    )
    if evidence_source_count is None:
        evidence_source_count = _count_evidence_sources(evidence_refs)

    expert_vote_score = _resolve_expert_vote_score(payload, evidence_refs)
    return {
        "repeat_count": max(int(repeat_count or 0), 0),
        "evidence_source_count": max(int(evidence_source_count or 0), 0),
        "expert_vote_score": int(expert_vote_score or 0),
    }


def _first_int(payload: Mapping[str, Any], keys: Sequence[str]) -> Optional[int]:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _count_evidence_sources(evidence_refs: Sequence[Mapping[str, Any]]) -> int:
    sources: set[str] = set()
    for ref in evidence_refs or []:
        if not isinstance(ref, Mapping):
            continue
        for key in (
            "source_id",
            "source",
            "document_id",
            "doc_id",
            "canonical_document_key",
            "cycle_id",
            "node_id",
            "relationship_id",
        ):
            value = str(ref.get(key) or "").strip()
            if value:
                sources.add(f"{key}:{value}")
                break
    return len(sources)


def _resolve_expert_vote_score(
    payload: Mapping[str, Any],
    evidence_refs: Sequence[Mapping[str, Any]],
) -> int:
    if payload.get("expert_vote_score") not in (None, ""):
        try:
            return int(float(payload.get("expert_vote_score")))
        except (TypeError, ValueError):
            pass
    expert_votes = payload.get("expert_votes")
    if isinstance(expert_votes, Mapping):
        positive = _sum_vote_keys(
            expert_votes, ("accept", "accepted", "approve", "up", "positive")
        )
        negative = _sum_vote_keys(
            expert_votes, ("reject", "rejected", "down", "negative")
        )
        return positive - negative
    if isinstance(expert_votes, list):
        return sum(_vote_value(item) for item in expert_votes)
    return sum(_vote_value(ref) for ref in evidence_refs or [])


def _sum_vote_keys(votes: Mapping[str, Any], keys: Sequence[str]) -> int:
    total = 0
    for key in keys:
        value = votes.get(key)
        if value in (None, ""):
            continue
        try:
            total += int(float(value))
        except (TypeError, ValueError):
            continue
    return total


def _vote_value(value: Any) -> int:
    payload = value if isinstance(value, Mapping) else {"vote": value}
    text = (
        str(
            payload.get("expert_vote")
            or payload.get("expert_decision")
            or payload.get("decision")
            or payload.get("vote")
            or payload.get("status")
            or ""
        )
        .strip()
        .lower()
    )
    if text in {
        "accept",
        "accepted",
        "approve",
        "approved",
        "up",
        "positive",
        "+1",
        "yes",
    }:
        return 1
    if text in {"reject", "rejected", "deny", "down", "negative", "-1", "no"}:
        return -1
    return 0


def _int_policy(policy: Mapping[str, Any], key: str, default: int) -> int:
    value = policy.get(key, default)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _is_expired_by_policy(
    created_at: Optional[datetime],
    expires_at: Optional[datetime],
    *,
    now: datetime,
    threshold_policy: Mapping[str, Any],
) -> bool:
    effective_now = _as_aware_utc(_coerce_datetime(now) or _now())
    if expires_at is not None and _as_aware_utc(expires_at) <= effective_now:
        return True
    expire_after_days = threshold_policy.get("expire_after_days")
    if expire_after_days in (None, "") or created_at is None:
        return False
    try:
        days = int(float(expire_after_days))
    except (TypeError, ValueError):
        return False
    if days <= 0:
        return False
    return _as_aware_utc(created_at) + timedelta(days=days) <= effective_now


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


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "DEFAULT_THRESHOLD_POLICY",
    "LearningInsightRepo",
    "LEGACY_STATUS_REVIEWED",
    "PROMPT_BIAS_ELIGIBLE_STATUSES",
    "REJECTED_NEGATIVE_STATUSES",
    "STATUS_ACCEPTED",
    "STATUS_ACTIVE",
    "STATUS_EXPIRED",
    "STATUS_NEEDS_REVIEW",
    "STATUS_REJECTED",
    "STATUS_REVIEWED",
    "STATUS_SUPERSEDED",
    "evaluate_threshold_policy",
    "normalize_status",
]
