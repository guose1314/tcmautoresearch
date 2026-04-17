from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence

OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT = "observe_philology_review_workbench"
REVIEW_WORKBENCH_ASSET_KIND = "review_workbench_decisions"

_REVIEWABLE_ASSET_TYPES = frozenset(
    {
        "terminology_row",
        "collation_entry",
        "claim",
        "fragment_candidate",
    }
)
_REVIEWABLE_OPTIONAL_FIELDS = (
    "candidate_kind",
    "document_id",
    "document_title",
    "document_urn",
    "work_title",
    "fragment_title",
    "version_lineage_key",
    "witness_key",
    "canonical",
    "label",
    "difference_type",
    "base_text",
    "witness_text",
    "claim_id",
    "source_entity",
    "target_entity",
    "relation_type",
    "fragment_candidate_id",
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        normalized = _as_text(item)
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _unique_texts(values: Sequence[Any]) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _as_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _normalize_review_status(value: Any) -> str:
    normalized = _as_text(value).lower()
    if normalized in {"pending", "accepted", "rejected", "needs_source"}:
        return normalized
    return ""


def _normalize_asset_type(value: Any) -> str:
    normalized = _as_text(value).lower()
    if normalized in _REVIEWABLE_ASSET_TYPES:
        return normalized
    return ""


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _resolve_needs_manual_review(
    review_status: str,
    review_reasons: Sequence[str],
    *,
    explicit_value: Any = None,
) -> bool:
    if explicit_value is not None:
        return bool(explicit_value)
    if review_status in {"accepted", "rejected"}:
        return False
    return review_status in {"pending", "needs_source"} or bool(review_reasons)


def normalize_observe_review_workbench_decision(raw_decision: Any) -> Dict[str, Any]:
    decision = _as_dict(raw_decision)
    asset_type = _normalize_asset_type(decision.get("asset_type"))
    asset_key = _as_text(decision.get("asset_key"))
    review_status = _normalize_review_status(decision.get("review_status"))
    if not asset_type or not asset_key or not review_status:
        return {}

    normalized: Dict[str, Any] = {
        "asset_type": asset_type,
        "asset_key": asset_key,
        "review_status": review_status,
        "review_source": "manual_review",
    }
    for field_name in _REVIEWABLE_OPTIONAL_FIELDS:
        value = _as_text(decision.get(field_name))
        if value:
            normalized[field_name] = value

    reviewer = _as_text(decision.get("reviewer"))
    reviewed_at = _as_text(decision.get("reviewed_at")) or _utc_now_iso()
    decision_basis = _as_text(decision.get("decision_basis"))
    review_reasons = _unique_texts(
        [
            *_as_string_list(decision.get("review_reasons")),
            "manual_review_written",
            f"manual_review_status:{review_status}",
        ]
    )
    explicit_needs_manual_review = decision.get("needs_manual_review") if "needs_manual_review" in decision else None

    normalized["needs_manual_review"] = _resolve_needs_manual_review(
        review_status,
        review_reasons,
        explicit_value=explicit_needs_manual_review,
    )
    normalized["review_reasons"] = review_reasons
    normalized["reviewed_at"] = reviewed_at
    if reviewer:
        normalized["reviewer"] = reviewer
    if decision_basis:
        normalized["decision_basis"] = decision_basis
    decision_history = decision.get("decision_history")
    if isinstance(decision_history, list) and decision_history:
        normalized["decision_history"] = decision_history
    return normalized


def normalize_observe_review_workbench_decisions(raw_decisions: Any) -> List[Dict[str, Any]]:
    payload = _as_dict(raw_decisions)
    if isinstance(raw_decisions, list):
        items = list(raw_decisions)
    else:
        items = list(payload.get("decisions") or [])

    decisions: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        normalized = normalize_observe_review_workbench_decision(item)
        if not normalized:
            continue
        identity = (normalized["asset_type"], normalized["asset_key"])
        if identity in seen:
            continue
        seen.add(identity)
        decisions.append(normalized)

    decisions.sort(
        key=lambda item: (
            str(item.get("asset_type") or ""),
            str(item.get("asset_key") or ""),
            str(item.get("reviewed_at") or ""),
        )
    )
    return decisions


def _build_audit_history_entry(previous: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a compact audit entry from the previous decision being overwritten."""
    entry: Dict[str, Any] = {}
    for key in ("review_status", "reviewer", "reviewed_at", "decision_basis", "review_source"):
        value = _as_text(previous.get(key))
        if value:
            entry[key] = value
    return entry


def _append_audit_trail(
    new_decision: Dict[str, Any],
    previous_decision: Dict[str, Any] | None,
) -> None:
    """Carry forward decision_history from *previous_decision* into *new_decision*."""
    existing_history: List[Dict[str, Any]] = list(previous_decision.get("decision_history") or []) if previous_decision else []
    if previous_decision:
        audit_entry = _build_audit_history_entry(previous_decision)
        if audit_entry:
            existing_history.append(audit_entry)
    if existing_history:
        new_decision["decision_history"] = existing_history


def upsert_observe_review_workbench_artifact_content(
    raw_content: Any,
    raw_decision: Any,
) -> Dict[str, Any]:
    decision = normalize_observe_review_workbench_decision(raw_decision)
    if not decision:
        return {}

    existing_decisions = normalize_observe_review_workbench_decisions(raw_content)
    previous = next(
        (
            item
            for item in existing_decisions
            if item.get("asset_type") == decision["asset_type"]
            and item.get("asset_key") == decision["asset_key"]
        ),
        None,
    )
    _append_audit_trail(decision, previous)

    decisions = [
        item
        for item in existing_decisions
        if not (
            item.get("asset_type") == decision["asset_type"]
            and item.get("asset_key") == decision["asset_key"]
        )
    ]
    decisions.append(decision)
    decisions = normalize_observe_review_workbench_decisions(decisions)
    return {
        "asset_kind": REVIEW_WORKBENCH_ASSET_KIND,
        "decision_count": len(decisions),
        "updated_at": decision.get("reviewed_at"),
        "last_reviewer": decision.get("reviewer"),
        "decisions": decisions,
    }


def upsert_observe_review_workbench_artifact_content_batch(
    raw_content: Any,
    raw_decisions: Any,
) -> Dict[str, Any]:
    """Apply multiple review decisions in one pass, preserving audit trails."""
    items: List[Any] = list(raw_decisions) if isinstance(raw_decisions, list) else []
    if not items:
        return {}

    content = raw_content
    for raw_decision in items:
        result = upsert_observe_review_workbench_artifact_content(content, raw_decision)
        if result:
            content = result

    if not isinstance(content, dict) or not content:
        return {}
    return content