from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.infrastructure.persistence import DatabaseManager, LearningInsight
from src.learning.learning_insight_repo import (
    STATUS_ACCEPTED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    LearningInsightRepo,
    normalize_status,
)

WEAK_EDGE_CANDIDATE_REPO_VERSION = "weak-edge-candidate-repo-v1"
WEAK_EDGE_CANDIDATE_INSIGHT_TYPE = "weak_edge_candidate"
LEGACY_WEAK_EDGE_INSIGHT_TYPES = frozenset(
    {"candidate_edge", "candidate_rule_relation"}
)
COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES = frozenset(
    {WEAK_EDGE_CANDIDATE_INSIGHT_TYPE, *LEGACY_WEAK_EDGE_INSIGHT_TYPES}
)

_TERMINAL_REVIEW_STATUSES = frozenset(
    {STATUS_ACCEPTED, STATUS_REJECTED, STATUS_SUPERSEDED}
)


def weak_edge_candidate_key(candidate: Mapping[str, Any]) -> str:
    normalized = _normalize_candidate_edge(candidate)
    left = str(
        normalized.get("source_entity_id") or normalized.get("source_name") or ""
    ).strip()
    right = str(
        normalized.get("target_entity_id") or normalized.get("target_name") or ""
    ).strip()
    relationship_type = str(normalized.get("relationship_type") or "").strip().upper()
    if not left or not right or not relationship_type:
        return ""
    return "|".join((left.lower(), right.lower(), relationship_type))


def weak_edge_candidate_insight_id(candidate: Mapping[str, Any]) -> str:
    key = weak_edge_candidate_key(candidate)
    if not key:
        raise ValueError("weak edge candidate key is required")
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]
    return f"weak-edge:{digest}"


def extract_weak_edge_candidate_payload(item: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, Mapping):
        return {}
    direct = item.get("weak_edge_candidate")
    if isinstance(direct, Mapping):
        payload = dict(direct)
        if payload:
            normalized = _normalize_payload(payload)
            runtime_reject_reason = _extract_reject_reason(item)
            if runtime_reject_reason:
                normalized["reject_reason"] = runtime_reject_reason
            runtime_status = _normalize_review_status(item.get("status"))
            if runtime_status in _TERMINAL_REVIEW_STATUSES:
                normalized["review_status"] = runtime_status
                normalized["candidate_edge"]["review_status"] = runtime_status
            return normalized

    refs = item.get("evidence_refs_json") or item.get("evidence_refs") or []
    if isinstance(refs, Mapping):
        refs = [refs]
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            if str(ref.get("type") or "").strip() == "weak_edge_candidate":
                normalized = _normalize_payload(dict(ref))
                runtime_reject_reason = _extract_reject_reason(item)
                if runtime_reject_reason:
                    normalized["reject_reason"] = runtime_reject_reason
                runtime_status = _normalize_review_status(item.get("status"))
                if runtime_status in _TERMINAL_REVIEW_STATUSES:
                    normalized["review_status"] = runtime_status
                    normalized["candidate_edge"]["review_status"] = runtime_status
                return normalized
            if isinstance(ref.get("candidate_edge"), Mapping) and (
                ref.get("weak_edge_key") or ref.get("source_algorithm")
            ):
                normalized = _normalize_payload(dict(ref))
                runtime_reject_reason = _extract_reject_reason(item)
                if runtime_reject_reason:
                    normalized["reject_reason"] = runtime_reject_reason
                runtime_status = _normalize_review_status(item.get("status"))
                if runtime_status in _TERMINAL_REVIEW_STATUSES:
                    normalized["review_status"] = runtime_status
                    normalized["candidate_edge"]["review_status"] = runtime_status
                return normalized

    insight_type = str(item.get("insight_type") or "").strip().lower()
    if insight_type in COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES:
        return build_weak_edge_payload(
            item,
            source_algorithm=str(item.get("source") or "legacy"),
            review_status=item.get("status"),
            reject_reason=_extract_reject_reason(item),
            discovered_at=item.get("created_at"),
            legacy_insight_types=[insight_type] if insight_type else [],
        )
    return {}


def merge_weak_edge_payloads(
    existing: Optional[Mapping[str, Any]],
    incoming: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    left = _normalize_payload(existing or {}) if existing else {}
    right = _normalize_payload(incoming or {}) if incoming else {}
    if not left:
        return right
    if not right:
        return left

    merged_candidate = _normalize_candidate_edge(left.get("candidate_edge") or {})
    incoming_candidate = _normalize_candidate_edge(right.get("candidate_edge") or {})
    for key in (
        "source_entity_id",
        "target_entity_id",
        "source_name",
        "target_name",
        "source_type",
        "target_type",
        "relationship_type",
        "evidence_snippet",
        "source_algorithm",
        "raw_candidate_edge_id",
    ):
        if str(incoming_candidate.get(key) or "").strip():
            merged_candidate[key] = incoming_candidate.get(key)
    merged_candidate["candidate_edge_id"] = str(
        right.get("candidate_edge_id")
        or left.get("candidate_edge_id")
        or merged_candidate.get("candidate_edge_id")
        or weak_edge_candidate_insight_id(incoming_candidate or merged_candidate)
    )
    merged_candidate["confidence"] = max(
        _clamp_confidence(merged_candidate.get("confidence")),
        _clamp_confidence(incoming_candidate.get("confidence")),
        _as_score(left.get("score")),
        _as_score(right.get("score")),
    )
    merged_candidate["signals"] = _merge_text_lists(
        merged_candidate.get("signals"), incoming_candidate.get("signals")
    )
    merged_candidate["review_status"] = _merge_review_status(
        left.get("review_status"), right.get("review_status")
    )

    observations = list(left.get("observations") or [])
    observations.extend(
        item for item in right.get("observations") or [] if isinstance(item, Mapping)
    )
    fragments = _merge_fragments(
        left.get("evidence_fragments"), right.get("evidence_fragments")
    )
    algorithms = _merge_text_lists(
        left.get("source_algorithms"), right.get("source_algorithms")
    )
    legacy_types = _merge_text_lists(
        left.get("legacy_insight_types"), right.get("legacy_insight_types")
    )

    duplicate_count = max(
        int(left.get("duplicate_count") or 0)
        + max(int(right.get("duplicate_count") or 0), 1),
        len(observations),
        1,
    )
    first_discovered_at = _min_iso_datetime(
        left.get("first_discovered_at"), right.get("first_discovered_at")
    )
    last_discovered_at = _max_iso_datetime(
        left.get("last_discovered_at"), right.get("last_discovered_at")
    )
    review_status = _merge_review_status(
        left.get("review_status"), right.get("review_status")
    )
    reject_reason = (
        str(right.get("reject_reason") or "").strip()
        or str(left.get("reject_reason") or "").strip()
    )
    source_algorithm = (
        str(right.get("source_algorithm") or "").strip()
        or str(left.get("source_algorithm") or "").strip()
        or (algorithms[-1] if algorithms else "")
    )

    payload = {
        "type": "weak_edge_candidate",
        "contract_version": WEAK_EDGE_CANDIDATE_REPO_VERSION,
        "weak_edge_key": str(
            left.get("weak_edge_key") or right.get("weak_edge_key") or ""
        ),
        "candidate_edge_id": merged_candidate["candidate_edge_id"],
        "candidate_edge": merged_candidate,
        "entity_pair": {
            "source_entity_id": merged_candidate.get("source_entity_id"),
            "target_entity_id": merged_candidate.get("target_entity_id"),
            "source_name": merged_candidate.get("source_name"),
            "target_name": merged_candidate.get("target_name"),
            "source_type": merged_candidate.get("source_type"),
            "target_type": merged_candidate.get("target_type"),
        },
        "relationship_type": merged_candidate.get("relationship_type"),
        "score": max(_as_score(left.get("score")), _as_score(right.get("score"))),
        "source_algorithm": source_algorithm,
        "source_algorithms": algorithms,
        "evidence_snippet": _pick_text(
            right.get("evidence_snippet"),
            left.get("evidence_snippet"),
            merged_candidate.get("evidence_snippet"),
        ),
        "evidence_fragments": fragments,
        "reject_reason": reject_reason,
        "review_status": review_status,
        "first_discovered_at": first_discovered_at,
        "last_discovered_at": last_discovered_at,
        "duplicate_count": duplicate_count,
        "observations": observations,
        "legacy_insight_types": legacy_types,
    }
    return _normalize_payload(payload)


def build_weak_edge_payload(
    candidate: Mapping[str, Any],
    *,
    source_algorithm: str,
    review_status: Any = None,
    reject_reason: Optional[str] = None,
    discovered_at: Any = None,
    legacy_insight_types: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    normalized_candidate = _normalize_candidate_edge(candidate)
    weak_edge_key = weak_edge_candidate_key(normalized_candidate)
    if not weak_edge_key:
        raise ValueError("weak edge candidate key is required")
    canonical_id = weak_edge_candidate_insight_id(normalized_candidate)
    discovered_iso = _coerce_iso_datetime(discovered_at) or _now_iso()
    source_algorithm_text = (
        str(
            source_algorithm
            or normalized_candidate.get("source")
            or "weak_edge_candidate_repo"
        ).strip()
        or "weak_edge_candidate_repo"
    )
    snippet = _extract_evidence_snippet(candidate)
    fragments = _collect_evidence_fragments(candidate)
    row_review_status = _normalize_review_status(review_status)
    payload = {
        "type": "weak_edge_candidate",
        "contract_version": WEAK_EDGE_CANDIDATE_REPO_VERSION,
        "weak_edge_key": weak_edge_key,
        "candidate_edge_id": canonical_id,
        "candidate_edge": {
            **normalized_candidate,
            "candidate_edge_id": canonical_id,
            "raw_candidate_edge_id": str(
                normalized_candidate.get("candidate_edge_id") or ""
            ).strip(),
            "confidence": max(
                _clamp_confidence(normalized_candidate.get("confidence")),
                _as_score(candidate.get("score")),
            ),
            "review_status": row_review_status,
            "source": source_algorithm_text,
            "evidence_snippet": snippet,
        },
        "entity_pair": {
            "source_entity_id": normalized_candidate.get("source_entity_id"),
            "target_entity_id": normalized_candidate.get("target_entity_id"),
            "source_name": normalized_candidate.get("source_name"),
            "target_name": normalized_candidate.get("target_name"),
            "source_type": normalized_candidate.get("source_type"),
            "target_type": normalized_candidate.get("target_type"),
        },
        "relationship_type": normalized_candidate.get("relationship_type"),
        "score": max(
            _as_score(candidate.get("score")),
            _clamp_confidence(normalized_candidate.get("confidence")),
        ),
        "source_algorithm": source_algorithm_text,
        "source_algorithms": [source_algorithm_text],
        "evidence_snippet": snippet,
        "evidence_fragments": fragments,
        "reject_reason": str(reject_reason or "").strip(),
        "review_status": row_review_status,
        "first_discovered_at": discovered_iso,
        "last_discovered_at": discovered_iso,
        "duplicate_count": max(int(candidate.get("duplicate_count") or 1), 1),
        "observations": [
            {
                "source_algorithm": source_algorithm_text,
                "score": max(
                    _as_score(candidate.get("score")),
                    _clamp_confidence(normalized_candidate.get("confidence")),
                ),
                "evidence_snippet": snippet,
                "discovered_at": discovered_iso,
            }
        ],
        "legacy_insight_types": [
            str(item).strip()
            for item in legacy_insight_types or []
            if str(item).strip()
        ],
    }
    return _normalize_payload(payload)


def build_weak_edge_learning_insight(
    candidate: Mapping[str, Any],
    *,
    target_phase: str,
    source_algorithm: str,
    existing_payload: Optional[Mapping[str, Any]] = None,
    existing_status: Optional[str] = None,
    created_at: Any = None,
    discovered_at: Any = None,
    legacy_insight_types: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    incoming_payload = build_weak_edge_payload(
        candidate,
        source_algorithm=source_algorithm,
        review_status=existing_status or candidate.get("review_status"),
        reject_reason=_extract_reject_reason(candidate),
        discovered_at=discovered_at or created_at or candidate.get("created_at"),
        legacy_insight_types=legacy_insight_types,
    )
    merged_payload = merge_weak_edge_payloads(existing_payload, incoming_payload)
    confidence = max(
        _as_score(merged_payload.get("score")),
        _clamp_confidence(
            (merged_payload.get("candidate_edge") or {}).get("confidence")
        ),
    )
    return {
        "insight_id": str(
            merged_payload.get("candidate_edge_id")
            or weak_edge_candidate_insight_id(candidate)
        )[:128],
        "source": "weak_edge_candidate_repo",
        "target_phase": str(target_phase or "analyze").strip() or "analyze",
        "insight_type": WEAK_EDGE_CANDIDATE_INSIGHT_TYPE,
        "description": _build_candidate_description(merged_payload),
        "confidence": confidence,
        "evidence_refs_json": [merged_payload],
        "status": _row_status_from_review_status(
            merged_payload.get("review_status") or existing_status
        ),
        "created_at": merged_payload.get("first_discovered_at") or _now_iso(),
    }


class WeakEdgeCandidateRepository:
    def __init__(
        self,
        db_manager: DatabaseManager,
        *,
        learning_insight_repo: Optional[LearningInsightRepo] = None,
    ) -> None:
        if db_manager is None:
            raise ValueError("db_manager is required")
        self._db = db_manager
        self._insight_repo = learning_insight_repo or LearningInsightRepo(db_manager)

    def prepare_upsert_mapping(
        self,
        candidate: Mapping[str, Any],
        *,
        target_phase: str,
        source_algorithm: str,
        discovered_at: Any = None,
        legacy_insight_types: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        insight_id = weak_edge_candidate_insight_id(candidate)
        with self._db.session_scope() as session:
            row = session.get(LearningInsight, insight_id)
            existing_payload = extract_weak_edge_candidate_payload(
                _row_to_payload(row) if row is not None else {}
            )
            existing_status = row.status if row is not None else None
            existing_created_at = row.created_at if row is not None else None
        return build_weak_edge_learning_insight(
            candidate,
            target_phase=target_phase,
            source_algorithm=source_algorithm,
            existing_payload=existing_payload,
            existing_status=existing_status,
            created_at=existing_created_at,
            discovered_at=discovered_at,
            legacy_insight_types=legacy_insight_types,
        )

    def upsert_candidate(
        self,
        candidate: Mapping[str, Any],
        *,
        target_phase: str,
        source_algorithm: str,
        discovered_at: Any = None,
        legacy_insight_types: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        payload = self.prepare_upsert_mapping(
            candidate,
            target_phase=target_phase,
            source_algorithm=source_algorithm,
            discovered_at=discovered_at,
            legacy_insight_types=legacy_insight_types,
        )
        return dict(self._insight_repo.upsert(payload))

    def list_candidates(
        self,
        *,
        status: str = "all",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        normalized_status = str(status or "all").strip().lower()
        with self._db.session_scope() as session:
            query = session.query(LearningInsight).filter(
                LearningInsight.insight_type.in_(
                    list(COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES)
                )
            )
            if normalized_status != "all":
                if normalized_status in {"pending", "needs_review", "active"}:
                    query = query.filter(
                        LearningInsight.status.in_([STATUS_NEEDS_REVIEW, "active"])
                    )
                else:
                    query = query.filter(
                        LearningInsight.status == normalize_status(normalized_status)
                    )
            rows = query.order_by(
                LearningInsight.confidence.desc(), LearningInsight.created_at.desc()
            ).all()

        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = self._row_to_candidate_item(row)
            payload = dict(item.get("weak_edge_candidate") or {})
            key = str(payload.get("weak_edge_key") or item.get("insight_id") or "")
            if not key:
                continue
            current = grouped.get(key)
            if current is None:
                grouped[key] = item
                continue
            merged_payload = merge_weak_edge_payloads(
                current.get("weak_edge_candidate"),
                item.get("weak_edge_candidate"),
            )
            preferred = current
            if _candidate_sort_tuple(item) < _candidate_sort_tuple(current):
                preferred = item
            grouped[key] = {
                **preferred,
                "confidence": max(
                    float(current.get("confidence") or 0.0),
                    float(item.get("confidence") or 0.0),
                ),
                "status": _row_status_from_review_status(
                    merged_payload.get("review_status") or preferred.get("status")
                ),
                "evidence_refs_json": [merged_payload, *self._review_events(preferred)],
                "candidate_edge": dict(merged_payload.get("candidate_edge") or {}),
                "weak_edge_candidate": merged_payload,
            }
        items = list(grouped.values())
        items.sort(key=_candidate_sort_tuple)
        return items[: max(int(limit or 0), 0)] if limit else items

    def get_candidate(self, insight_id: str) -> Optional[Dict[str, Any]]:
        with self._db.session_scope() as session:
            row = session.get(LearningInsight, str(insight_id))
            if (
                row is None
                or row.insight_type not in COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES
            ):
                return None
            return self._row_to_candidate_item(row)

    def _row_to_candidate_item(self, row: LearningInsight) -> Dict[str, Any]:
        payload = extract_weak_edge_candidate_payload(_row_to_payload(row))
        review_events = self._review_events(_row_to_payload(row))
        return {
            "insight_id": row.insight_id,
            "source": row.source,
            "target_phase": row.target_phase,
            "insight_type": row.insight_type,
            "description": row.description,
            "confidence": float(row.confidence or 0.0),
            "status": normalize_status(row.status),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "evidence_refs_json": [payload, *review_events]
            if payload
            else review_events,
            "candidate_edge": dict(payload.get("candidate_edge") or {}),
            "weak_edge_candidate": payload,
        }

    @staticmethod
    def _review_events(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
        refs = payload.get("evidence_refs_json") or payload.get("evidence_refs") or []
        if isinstance(refs, Mapping):
            refs = [refs]
        events: List[Dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            if str(ref.get("type") or "") == "expert_review_feedback":
                events.append(dict(ref))
        return events


def _row_to_payload(row: Optional[LearningInsight]) -> Dict[str, Any]:
    if row is None:
        return {}
    return {
        "insight_id": row.insight_id,
        "source": row.source,
        "target_phase": row.target_phase,
        "insight_type": row.insight_type,
        "description": row.description,
        "confidence": row.confidence,
        "evidence_refs_json": list(row.evidence_refs_json or []),
        "status": row.status,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _normalize_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    candidate = _normalize_candidate_edge(payload.get("candidate_edge") or payload)
    weak_edge_key = str(
        payload.get("weak_edge_key") or weak_edge_candidate_key(candidate)
    )
    candidate_edge_id = str(
        payload.get("candidate_edge_id")
        or candidate.get("candidate_edge_id")
        or weak_edge_candidate_insight_id(candidate)
    )
    review_status = _normalize_review_status(
        payload.get("review_status") or candidate.get("review_status")
    )
    candidate["candidate_edge_id"] = candidate_edge_id
    candidate["review_status"] = review_status
    payload_dict = {
        "type": "weak_edge_candidate",
        "contract_version": WEAK_EDGE_CANDIDATE_REPO_VERSION,
        "weak_edge_key": weak_edge_key,
        "candidate_edge_id": candidate_edge_id,
        "candidate_edge": candidate,
        "entity_pair": {
            "source_entity_id": candidate.get("source_entity_id"),
            "target_entity_id": candidate.get("target_entity_id"),
            "source_name": candidate.get("source_name"),
            "target_name": candidate.get("target_name"),
            "source_type": candidate.get("source_type"),
            "target_type": candidate.get("target_type"),
        },
        "relationship_type": candidate.get("relationship_type"),
        "score": max(
            _as_score(payload.get("score")),
            _clamp_confidence(candidate.get("confidence")),
        ),
        "source_algorithm": _pick_text(
            payload.get("source_algorithm"),
            candidate.get("source"),
            payload.get("source"),
        ),
        "source_algorithms": _merge_text_lists(
            payload.get("source_algorithms"),
            [candidate.get("source")],
        ),
        "evidence_snippet": _pick_text(
            payload.get("evidence_snippet"),
            candidate.get("evidence_snippet"),
            _extract_evidence_snippet(candidate),
        ),
        "evidence_fragments": _merge_fragments(
            payload.get("evidence_fragments"),
            _collect_evidence_fragments(candidate),
        ),
        "reject_reason": str(payload.get("reject_reason") or "").strip(),
        "review_status": review_status,
        "first_discovered_at": _coerce_iso_datetime(
            payload.get("first_discovered_at") or payload.get("created_at")
        )
        or _now_iso(),
        "last_discovered_at": _coerce_iso_datetime(
            payload.get("last_discovered_at") or payload.get("created_at")
        )
        or _now_iso(),
        "duplicate_count": max(int(payload.get("duplicate_count") or 1), 1),
        "observations": [
            dict(item)
            for item in payload.get("observations") or []
            if isinstance(item, Mapping)
        ],
        "legacy_insight_types": [
            str(item).strip()
            for item in payload.get("legacy_insight_types") or []
            if str(item).strip()
        ],
    }
    if not payload_dict["observations"]:
        payload_dict["observations"] = [
            {
                "source_algorithm": payload_dict["source_algorithm"],
                "score": payload_dict["score"],
                "evidence_snippet": payload_dict["evidence_snippet"],
                "discovered_at": payload_dict["last_discovered_at"],
            }
        ]
    return payload_dict


def _normalize_candidate_edge(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(candidate or {})
    entity_pair = (
        payload.get("entity_pair")
        if isinstance(payload.get("entity_pair"), Mapping)
        else {}
    )
    evidence = (
        payload.get("evidence") if isinstance(payload.get("evidence"), Mapping) else {}
    )
    relationship_type = (
        str(
            payload.get("relationship_type")
            or payload.get("relation")
            or payload.get("rel_type")
            or payload.get("label")
            or "RELATED_TO"
        )
        .strip()
        .upper()
    )
    return {
        "source_entity_id": _pick_text(
            payload.get("source_entity_id"), entity_pair.get("source_entity_id")
        ),
        "target_entity_id": _pick_text(
            payload.get("target_entity_id"), entity_pair.get("target_entity_id")
        ),
        "source_name": _pick_text(
            payload.get("source_name"),
            entity_pair.get("source_name"),
            payload.get("source"),
        ),
        "target_name": _pick_text(
            payload.get("target_name"),
            entity_pair.get("target_name"),
            payload.get("target"),
        ),
        "source_type": _pick_text(
            payload.get("source_type"), entity_pair.get("source_type")
        ),
        "target_type": _pick_text(
            payload.get("target_type"), entity_pair.get("target_type")
        ),
        "relationship_type": relationship_type,
        "candidate_edge_id": str(payload.get("candidate_edge_id") or "").strip(),
        "confidence": max(
            _clamp_confidence(payload.get("confidence")),
            _as_score(payload.get("score")),
        ),
        "signals": _merge_text_lists(payload.get("signals"), evidence.get("signals")),
        "source": _pick_text(payload.get("source"), payload.get("source_algorithm")),
        "evidence": dict(evidence),
        "evidence_snippet": _pick_text(
            payload.get("evidence_snippet"),
            payload.get("snippet"),
            evidence.get("snippet"),
            evidence.get("evidence_snippet"),
            evidence.get("text"),
            evidence.get("excerpt"),
            evidence.get("source_text"),
        ),
        "review_status": _normalize_review_status(payload.get("review_status")),
    }


def _collect_evidence_fragments(candidate: Mapping[str, Any]) -> List[Dict[str, Any]]:
    fragments: List[Dict[str, Any]] = []
    evidence = (
        candidate.get("evidence")
        if isinstance(candidate.get("evidence"), Mapping)
        else {}
    )
    for key in ("evidence_snippet", "snippet", "text", "excerpt", "source_text"):
        value = _pick_text(candidate.get(key), evidence.get(key))
        if value:
            fragments.append({"text": value, "source": key})
    provenance = (
        candidate.get("provenance")
        if isinstance(candidate.get("provenance"), Sequence)
        else []
    )
    for item in provenance:
        if not isinstance(item, Mapping):
            continue
        value = _pick_text(
            item.get("quote_text"), item.get("text"), item.get("excerpt")
        )
        if value:
            fragments.append(
                {
                    "text": value,
                    "source": str(
                        item.get("segment_id") or item.get("source") or "provenance"
                    ),
                }
            )
    return _merge_fragments(fragments, [])


def _merge_fragments(left: Any, right: Any) -> List[Dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    merged: List[Dict[str, Any]] = []
    for item in list(left or []) + list(right or []):
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("text") or "").strip()
        source = str(item.get("source") or "").strip()
        if not text:
            continue
        key = (text, source)
        if key in seen:
            continue
        seen.add(key)
        merged.append({"text": text, "source": source})
    return merged


def _merge_text_lists(left: Any, right: Any) -> List[str]:
    values: List[str] = []
    for item in list(left or []) + list(right or []):
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    return values


def _build_candidate_description(payload: Mapping[str, Any]) -> str:
    candidate = (
        payload.get("candidate_edge")
        if isinstance(payload.get("candidate_edge"), Mapping)
        else {}
    )
    algorithms = ",".join(payload.get("source_algorithms") or []) or "unknown"
    return (
        f"弱候选边待复核: {candidate.get('source_name') or '?'} -"
        f"[{candidate.get('relationship_type') or 'RELATED_TO'}]-> "
        f"{candidate.get('target_name') or '?'}; 来源算法={algorithms}; "
        f"重复发现={int(payload.get('duplicate_count') or 1)}"
    )


def _extract_evidence_snippet(candidate: Mapping[str, Any]) -> str:
    if isinstance(candidate.get("weak_edge_candidate"), Mapping):
        return _pick_text(candidate["weak_edge_candidate"].get("evidence_snippet"))
    evidence = (
        candidate.get("evidence")
        if isinstance(candidate.get("evidence"), Mapping)
        else {}
    )
    return _pick_text(
        candidate.get("evidence_snippet"),
        candidate.get("snippet"),
        evidence.get("snippet"),
        evidence.get("evidence_snippet"),
        evidence.get("text"),
        evidence.get("excerpt"),
        evidence.get("source_text"),
    )


def _extract_reject_reason(item: Mapping[str, Any]) -> str:
    text = str(item.get("reject_reason") or item.get("reason") or "").strip()
    if text:
        return text
    refs = item.get("evidence_refs_json") or item.get("evidence_refs") or []
    if isinstance(refs, Mapping):
        refs = [refs]
    for ref in reversed(refs if isinstance(refs, list) else []):
        if not isinstance(ref, Mapping):
            continue
        if str(ref.get("type") or "") == "expert_review_feedback":
            reason = str(ref.get("reason") or "").strip()
            if reason:
                return reason
    return ""


def _normalize_review_status(value: Any) -> str:
    status = normalize_status(value)
    if status == "active":
        return STATUS_NEEDS_REVIEW
    if status == "expired":
        return STATUS_NEEDS_REVIEW
    return status


def _merge_review_status(left: Any, right: Any) -> str:
    normalized_left = _normalize_review_status(left)
    normalized_right = _normalize_review_status(right)
    if normalized_left in _TERMINAL_REVIEW_STATUSES:
        return normalized_left
    if normalized_right in _TERMINAL_REVIEW_STATUSES:
        return normalized_right
    return normalized_right or normalized_left or STATUS_NEEDS_REVIEW


def _row_status_from_review_status(value: Any) -> str:
    status = _normalize_review_status(value)
    if status in _TERMINAL_REVIEW_STATUSES:
        return status
    return STATUS_NEEDS_REVIEW


def _candidate_sort_tuple(item: Mapping[str, Any]) -> tuple[Any, ...]:
    payload = (
        item.get("weak_edge_candidate")
        if isinstance(item.get("weak_edge_candidate"), Mapping)
        else {}
    )
    return (
        -float(item.get("confidence") or 0.0),
        -int(payload.get("duplicate_count") or 1),
        str(payload.get("first_discovered_at") or item.get("created_at") or ""),
        str(item.get("insight_id") or ""),
    )


def _as_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def _pick_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _coerce_iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _min_iso_datetime(left: Any, right: Any) -> str:
    values = [
        value
        for value in (_coerce_iso_datetime(left), _coerce_iso_datetime(right))
        if value
    ]
    return min(values) if values else _now_iso()


def _max_iso_datetime(left: Any, right: Any) -> str:
    values = [
        value
        for value in (_coerce_iso_datetime(left), _coerce_iso_datetime(right))
        if value
    ]
    return max(values) if values else _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES",
    "LEGACY_WEAK_EDGE_INSIGHT_TYPES",
    "WEAK_EDGE_CANDIDATE_INSIGHT_TYPE",
    "WEAK_EDGE_CANDIDATE_REPO_VERSION",
    "WeakEdgeCandidateRepository",
    "build_weak_edge_learning_insight",
    "build_weak_edge_payload",
    "extract_weak_edge_candidate_payload",
    "merge_weak_edge_payloads",
    "weak_edge_candidate_insight_id",
    "weak_edge_candidate_key",
]
