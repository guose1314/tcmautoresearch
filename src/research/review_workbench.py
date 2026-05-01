from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Sequence

OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT = "observe_philology_review_workbench"
REVIEW_WORKBENCH_ASSET_KIND = "review_workbench_decisions"
_BATCH_AUDIT_HISTORY_LIMIT = 20

_REVIEWABLE_ASSET_TYPES = frozenset(
    {
        "terminology_row",
        "collation_entry",
        "claim",
        "exegesis_entry",
        "fragment_candidate",
        "evidence_chain",
        "textual_criticism_verdict",
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
    "evidence_chain_id",
    "claim_type",
    "claim_statement",
    "judgment_type",
    "term",
    "exegesis_term",
    "exegesis_entry_id",
    "textual_criticism_verdict_id",
    "verdict_id",
    "target_phase",
    "reason",
)

PHILOLOGY_REVIEW_FEEDBACK_SCOPE = "philology_review"


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
    return datetime.now(timezone.utc).isoformat()


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
    explicit_needs_manual_review = (
        decision.get("needs_manual_review")
        if "needs_manual_review" in decision
        else None
    )

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


def normalize_observe_review_workbench_decisions(
    raw_decisions: Any,
) -> List[Dict[str, Any]]:
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
    for key in (
        "review_status",
        "reviewer",
        "reviewed_at",
        "decision_basis",
        "review_source",
    ):
        value = _as_text(previous.get(key))
        if value:
            entry[key] = value
    return entry


def _append_audit_trail(
    new_decision: Dict[str, Any],
    previous_decision: Dict[str, Any] | None,
) -> None:
    """Carry forward decision_history from *previous_decision* into *new_decision*."""
    existing_history: List[Dict[str, Any]] = (
        list(previous_decision.get("decision_history") or [])
        if previous_decision
        else []
    )
    if previous_decision:
        audit_entry = _build_audit_history_entry(previous_decision)
        if audit_entry:
            existing_history.append(audit_entry)
    if existing_history:
        new_decision["decision_history"] = existing_history


def _normalize_batch_selection_snapshot(value: Any) -> Dict[str, Any]:
    payload = _as_dict(value)
    if not payload:
        return {}

    normalized: Dict[str, Any] = {}
    for field_name in ("selection_strategy", "scope"):
        text = _as_text(payload.get(field_name))
        if text:
            normalized[field_name] = text

    for field_name in ("selected_count", "visible_item_count", "total_item_count"):
        raw_value = payload.get(field_name)
        try:
            numeric = int(raw_value)
        except (TypeError, ValueError):
            continue
        if numeric >= 0:
            normalized[field_name] = numeric

    for field_name in ("asset_keys", "asset_types", "review_statuses"):
        values = _as_string_list(payload.get(field_name))
        if values:
            normalized[field_name] = values

    active_filters = payload.get("active_filters")
    if isinstance(active_filters, Mapping):
        normalized_filters = {
            key: text for key, raw in active_filters.items() if (text := _as_text(raw))
        }
        if normalized_filters:
            normalized["active_filters"] = normalized_filters

    section_counts = payload.get("section_counts")
    if isinstance(section_counts, Mapping):
        normalized_section_counts: Dict[str, int] = {}
        for key, raw_value in section_counts.items():
            name = _as_text(key)
            if not name:
                continue
            try:
                numeric = int(raw_value)
            except (TypeError, ValueError):
                continue
            if numeric >= 0:
                normalized_section_counts[name] = numeric
        if normalized_section_counts:
            normalized["section_counts"] = normalized_section_counts

    return normalized


def _build_batch_audit_entry(
    decisions: Sequence[Dict[str, Any]],
    payload: Mapping[str, Any],
    *,
    reviewer: str,
    applied_at: str,
) -> Dict[str, Any]:
    asset_type_distribution: Dict[str, int] = {}
    review_status_distribution: Dict[str, int] = {}
    for decision in decisions:
        asset_type = _as_text(decision.get("asset_type"))
        review_status = _as_text(decision.get("review_status"))
        if asset_type:
            asset_type_distribution[asset_type] = (
                asset_type_distribution.get(asset_type, 0) + 1
            )
        if review_status:
            review_status_distribution[review_status] = (
                review_status_distribution.get(review_status, 0) + 1
            )

    entry: Dict[str, Any] = {
        "applied_at": applied_at,
        "applied_count": len(decisions),
        "asset_type_distribution": asset_type_distribution,
        "review_status_distribution": review_status_distribution,
    }
    if reviewer:
        entry["reviewer"] = reviewer

    shared_decision_basis = _as_text(payload.get("shared_decision_basis"))
    if shared_decision_basis:
        entry["shared_decision_basis"] = shared_decision_basis

    shared_review_reasons = _as_string_list(payload.get("shared_review_reasons"))
    if shared_review_reasons:
        entry["shared_review_reasons"] = shared_review_reasons

    selection_snapshot = _normalize_batch_selection_snapshot(
        payload.get("selection_snapshot")
    )
    if selection_snapshot:
        entry["selection_snapshot"] = selection_snapshot

    return entry


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
    payload = _as_dict(raw_decisions)
    items: List[Any] = (
        list(raw_decisions)
        if isinstance(raw_decisions, list)
        else list(payload.get("decisions") or [])
    )
    if not items:
        return {}

    content = raw_content
    normalized_decisions: List[Dict[str, Any]] = []
    for raw_decision in items:
        normalized_decision = normalize_observe_review_workbench_decision(raw_decision)
        if not normalized_decision:
            continue
        normalized_decisions.append(normalized_decision)
        result = upsert_observe_review_workbench_artifact_content(content, raw_decision)
        if result:
            content = result

    if not isinstance(content, dict) or not content or not normalized_decisions:
        return {}

    applied_at = (
        _as_text(payload.get("applied_at"))
        or _as_text(content.get("updated_at"))
        or _utc_now_iso()
    )
    reviewer = _as_text(payload.get("reviewer")) or _as_text(
        content.get("last_reviewer")
    )
    batch_entry = _build_batch_audit_entry(
        normalized_decisions,
        payload,
        reviewer=reviewer,
        applied_at=applied_at,
    )
    batch_audit_trail = list(content.get("batch_audit_trail") or [])
    batch_audit_trail.append(batch_entry)
    content["batch_audit_trail"] = batch_audit_trail[-_BATCH_AUDIT_HISTORY_LIMIT:]
    content["batch_operation_count"] = len(content["batch_audit_trail"])
    content["last_batch_summary"] = batch_entry
    content["updated_at"] = applied_at
    if reviewer:
        content["last_reviewer"] = reviewer
    return content


def _resolve_feedback_target_phase(decision: Mapping[str, Any]) -> str:
    explicit = _as_text(decision.get("target_phase")).lower()
    if explicit:
        return explicit
    asset_type = _as_text(decision.get("asset_type")).lower()
    if asset_type in {
        "terminology_row",
        "collation_entry",
        "exegesis_entry",
        "fragment_candidate",
        "evidence_chain",
        "textual_criticism_verdict",
    }:
        return "observe"
    if asset_type == "claim":
        return "analyze"
    return "observe"


def _review_status_to_feedback_status(review_status: str) -> str:
    if review_status in {"rejected", "needs_source"}:
        return "weakness"
    if review_status == "accepted":
        return "strength"
    return "tracked"


def _review_status_to_severity(review_status: str) -> str:
    if review_status == "rejected":
        return "high"
    if review_status == "needs_source":
        return "medium"
    return "low"


def _review_status_to_score(review_status: str) -> float | None:
    if review_status == "accepted":
        return 0.85
    if review_status == "needs_source":
        return 0.45
    if review_status == "rejected":
        return 0.2
    return None


def _build_philology_review_reason(decision: Mapping[str, Any]) -> str:
    reason = _as_text(decision.get("reason")) or _as_text(
        decision.get("decision_basis")
    )
    if reason:
        return reason
    review_reasons = _as_string_list(decision.get("review_reasons"))
    return "；".join(review_reasons)


def _build_philology_review_issue_fields(
    decision: Mapping[str, Any],
    *,
    reason: str,
) -> List[str]:
    review_status = _as_text(decision.get("review_status")).lower()
    if review_status not in {"rejected", "needs_source"}:
        return []
    asset_type = _as_text(decision.get("asset_type")).lower()
    if asset_type == "exegesis_entry":
        return ["此类术语需优先检查版本 witness"]
    if asset_type == "textual_criticism_verdict":
        return ["考据裁定需补齐 citation_refs 与 witness_keys"]
    if asset_type == "collation_entry":
        return ["校勘条目需核对 base/witness 异文依据"]
    if asset_type == "terminology_row":
        return ["术语归一需核对 witness 与版本来源"]
    if reason:
        return [reason]
    return [f"{asset_type or 'philology_asset'} 复核未通过"]


def build_philology_review_learning_feedback_record(
    raw_decision: Any,
) -> Dict[str, Any]:
    """Convert one workbench review decision into a learning feedback record."""
    decision = normalize_observe_review_workbench_decision(raw_decision)
    if not decision:
        return {}

    asset_kind = decision["asset_type"]
    asset_id = decision["asset_key"]
    review_status = decision["review_status"]
    target_phase = _resolve_feedback_target_phase(decision)
    reason = _build_philology_review_reason(decision)
    severity = _review_status_to_severity(review_status)
    feedback_status = _review_status_to_feedback_status(review_status)
    issue_fields = _build_philology_review_issue_fields(decision, reason=reason)
    violations = []
    if issue_fields:
        violations.append(
            {
                "rule_id": f"philology_review:{review_status}:{asset_kind}",
                "severity": severity,
            }
        )

    issue_count = 1 if feedback_status == "weakness" else 0
    details = {
        "asset_kind": asset_kind,
        "asset_id": asset_id,
        "decision": review_status,
        "reason": reason,
        "target_phase": target_phase,
        "reviewer": decision.get("reviewer"),
        "reviewed_at": decision.get("reviewed_at"),
        "issue_fields": issue_fields,
        "violations": violations,
        "decision_payload": dict(decision),
    }
    metadata = {
        "feedback_scope": PHILOLOGY_REVIEW_FEEDBACK_SCOPE,
        "asset_kind": asset_kind,
        "asset_id": asset_id,
        "decision": review_status,
        "reason": reason,
        "target_phase": target_phase,
        "severity": severity,
        "issue_fields": issue_fields,
        "violations": violations,
        "reviewer": decision.get("reviewer"),
        "reviewed_at": decision.get("reviewed_at"),
    }
    return {
        "feedback_scope": PHILOLOGY_REVIEW_FEEDBACK_SCOPE,
        "source_phase": target_phase,
        "target_phase": target_phase,
        "feedback_status": feedback_status,
        "overall_score": _review_status_to_score(review_status),
        "grade_level": "D"
        if severity == "high"
        else "C"
        if severity == "medium"
        else "B",
        "issue_count": issue_count,
        "weakness_count": issue_count,
        "strength_count": 1 if feedback_status == "strength" else 0,
        "recorded_phase_names": [target_phase],
        "weak_phase_names": [target_phase] if issue_count else [],
        "issues": [reason] if reason and issue_count else [],
        "improvement_priorities": issue_fields,
        "details": details,
        "metadata": metadata,
    }
