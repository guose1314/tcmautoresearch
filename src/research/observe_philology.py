from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence

from src.research.catalog_contract import (
    CATALOG_BASELINE_FIELDS,
    CATALOG_CORE_FIELDS,
    CATALOG_FILTER_FIELDS,
    assess_catalog_completeness,
    build_backfill_summary,
    build_catalog_hierarchy,
    has_baseline_fields,
)
from src.research.evidence_chain_contract import (
    build_evidence_chain_summary,
)
from src.research.exegesis_contract import (
    FIELD_DEFINITION,
    FIELD_DEFINITION_SOURCE,
    assess_exegesis_completeness,
    build_exegesis_note,
    build_exegesis_summary,
    definition_source_rank,
)
from src.research.fragment_contract import (
    CANDIDATE_KINDS,
    build_fragment_summary,
)
from src.research.review_workbench import (
    OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
    REVIEW_WORKBENCH_ASSET_KIND,
    normalize_observe_review_workbench_decisions,
)
from src.semantic_modeling.tcm_relationships import TCMRelationshipDefinitions

OBSERVE_PHILOLOGY_TERMINOLOGY_TABLE_ARTIFACT = "observe_philology_terminology_table"
OBSERVE_PHILOLOGY_COLLATION_ENTRIES_ARTIFACT = "observe_philology_collation_entries"
OBSERVE_PHILOLOGY_ANNOTATION_REPORT_ARTIFACT = "observe_philology_annotation_report"
OBSERVE_PHILOLOGY_CATALOG_SUMMARY_ARTIFACT = "observe_philology_catalog_summary"
OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT = "observe_philology_catalog_review"
OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT = "observe_philology_fragment_reconstruction"
OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT = "observe_philology_evidence_chain"
OBSERVE_PHILOLOGY_ARTIFACT_NAMES = frozenset(
    {
        OBSERVE_PHILOLOGY_TERMINOLOGY_TABLE_ARTIFACT,
        OBSERVE_PHILOLOGY_COLLATION_ENTRIES_ARTIFACT,
        OBSERVE_PHILOLOGY_ANNOTATION_REPORT_ARTIFACT,
        OBSERVE_PHILOLOGY_CATALOG_SUMMARY_ARTIFACT,
        OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT,
        OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT,
        OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT,
        OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT,
    }
)
_TERMINOLOGY_COLUMNS = [
    "document_title",
    "document_urn",
    "canonical",
    "label",
    "status",
    "observed_forms",
    "configured_variants",
    "sources",
    "notes",
    "definition",
    "definition_source",
    "semantic_scope",
    "dynasty_usage",
    "disambiguation_basis",
    "exegesis_notes",
]
_CATALOG_CORE_FIELDS = CATALOG_CORE_FIELDS
_CATALOG_FILTER_FIELDS = CATALOG_FILTER_FIELDS
_FRAGMENT_CANDIDATE_FIELDS = (
    "fragment_candidates",
    "lost_text_candidates",
    "citation_source_candidates",
)
_CATALOG_REVIEW_SCOPE_FIELDS = {
    "document": ("document_id", "document_urn", "document_title", "witness_key"),
    "version_lineage": ("version_lineage_key",),
    "witness": ("witness_key", "document_urn", "document_title"),
}
_CATALOG_REVIEW_SCOPE_ORDER = {
    "version_lineage": 1,
    "witness": 2,
    "document": 3,
}
_CATALOG_REVIEW_ASSET_KIND = "catalog_review_decisions"
_BATCH_AUDIT_HISTORY_LIMIT = 20
_EXEGESIS_LABEL_CATEGORY_MAP = {
    "本草药名": "herb",
    "方剂名": "formula",
    "证候术语": "syndrome",
    "理论术语": "theory",
    "功效术语": "efficacy",
    "通用术语": "common",
}
_EXEGESIS_MACHINE_NOTE_MARKERS = (
    "识别为",
    "统一为",
    "检测到异写",
)
_FORMULA_COMPOSITION_ROLE_LABELS = {
    "sovereign": "君药",
    "minister": "臣药",
    "assistant": "佐药",
    "envoy": "使药",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return default
    return numeric


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _normalize_count_mapping(value: Any) -> Dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: Dict[str, int] = {}
    for raw_key, raw_count in value.items():
        key = _as_text(raw_key)
        if not key:
            continue
        count = _safe_int(raw_count, 0)
        if count <= 0:
            continue
        counts[key] = count
    return {key: counts[key] for key in sorted(counts)}


def _count_values(items: Sequence[Mapping[str, Any]], field_name: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        key = _as_text(item.get(field_name))
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _unique_texts(values: Sequence[Any]) -> List[str]:
    seen: set[str] = set()
    items: List[str] = []
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


def _resolve_needs_manual_review(
    review_status: Any,
    review_reasons: Sequence[str],
    *,
    explicit_value: Any = None,
) -> bool:
    if explicit_value is not None:
        return bool(explicit_value)

    normalized_status = _normalize_review_status(review_status)
    if normalized_status in {"accepted", "rejected"}:
        return False
    return normalized_status in {"pending", "needs_source"} or bool(review_reasons)


def _normalize_catalog_review_scope(value: Any) -> str:
    normalized = _as_text(value).lower()
    if normalized in _CATALOG_REVIEW_SCOPE_FIELDS:
        return normalized
    return ""


def _record_matches_catalog_review_identifiers(
    decision: Mapping[str, Any],
    record: Mapping[str, Any],
    fields: Sequence[str],
) -> bool:
    compared = False
    for field_name in fields:
        expected = _as_text(decision.get(field_name))
        if not expected:
            continue
        compared = True
        if expected != _as_text(record.get(field_name)):
            return False
    return compared


def normalize_observe_catalog_review_decision(raw_decision: Any) -> Dict[str, Any]:
    decision = _as_dict(raw_decision)
    scope = _normalize_catalog_review_scope(decision.get("scope"))
    review_status = _normalize_review_status(decision.get("review_status"))
    if not scope or not review_status:
        return {}

    normalized: Dict[str, Any] = {
        "scope": scope,
        "review_status": review_status,
        "review_source": "manual_review",
    }
    for field_name in _CATALOG_REVIEW_SCOPE_FIELDS[scope]:
        value = _as_text(decision.get(field_name))
        if value:
            normalized[field_name] = value
    if not any(_as_text(normalized.get(field_name)) for field_name in _CATALOG_REVIEW_SCOPE_FIELDS[scope]):
        return {}

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


def _normalize_catalog_review_decisions(raw_decisions: Any) -> List[Dict[str, Any]]:
    payload = _as_dict(raw_decisions)
    items: List[Any]
    if isinstance(raw_decisions, list):
        items = list(raw_decisions)
    else:
        items = list(payload.get("decisions") or [])

    decisions: List[Dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for item in items:
        normalized = normalize_observe_catalog_review_decision(item)
        if not normalized:
            continue
        scope = normalized["scope"]
        identity = (
            scope,
            tuple(
                (field_name, _as_text(normalized.get(field_name)))
                for field_name in _CATALOG_REVIEW_SCOPE_FIELDS[scope]
                if _as_text(normalized.get(field_name))
            ),
        )
        if identity in seen:
            continue
        seen.add(identity)
        decisions.append(normalized)

    decisions.sort(
        key=lambda item: (
            _CATALOG_REVIEW_SCOPE_ORDER.get(str(item.get("scope") or ""), 99),
            str(item.get("version_lineage_key") or ""),
            str(item.get("witness_key") or ""),
            str(item.get("document_urn") or ""),
            str(item.get("document_title") or ""),
        )
    )
    return decisions


def _build_catalog_audit_entry(previous: Mapping[str, Any]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {}
    for key in ("scope", "review_status", "reviewer", "reviewed_at", "decision_basis", "review_source"):
        value = _as_text(previous.get(key))
        if value:
            entry[key] = value
    return entry


def _append_catalog_audit_trail(
    new_decision: Dict[str, Any],
    previous_decision: Mapping[str, Any] | None,
) -> None:
    existing_history: List[Dict[str, Any]] = list(previous_decision.get("decision_history") or []) if previous_decision else []
    if previous_decision:
        audit_entry = _build_catalog_audit_entry(previous_decision)
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
            key: text
            for key, raw in active_filters.items()
            if (text := _as_text(raw))
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


def _build_catalog_batch_audit_entry(
    decisions: Sequence[Dict[str, Any]],
    payload: Mapping[str, Any],
    *,
    reviewer: str,
    applied_at: str,
) -> Dict[str, Any]:
    scope_distribution: Dict[str, int] = {}
    review_status_distribution: Dict[str, int] = {}
    for decision in decisions:
        scope = _as_text(decision.get("scope"))
        review_status = _as_text(decision.get("review_status"))
        if scope:
            scope_distribution[scope] = scope_distribution.get(scope, 0) + 1
        if review_status:
            review_status_distribution[review_status] = review_status_distribution.get(review_status, 0) + 1

    entry: Dict[str, Any] = {
        "applied_at": applied_at,
        "applied_count": len(decisions),
        "scope_distribution": scope_distribution,
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

    selection_snapshot = _normalize_batch_selection_snapshot(payload.get("selection_snapshot"))
    if selection_snapshot:
        entry["selection_snapshot"] = selection_snapshot

    return entry


def upsert_observe_catalog_review_artifact_content(
    raw_content: Any,
    raw_decision: Any,
) -> Dict[str, Any]:
    decision = normalize_observe_catalog_review_decision(raw_decision)
    if not decision:
        return {}

    existing_decisions = _normalize_catalog_review_decisions(raw_content)
    scope = decision["scope"]
    identity = tuple(
        (field_name, _as_text(decision.get(field_name)))
        for field_name in _CATALOG_REVIEW_SCOPE_FIELDS[scope]
        if _as_text(decision.get(field_name))
    )
    previous = next(
        (
            item
            for item in existing_decisions
            if item.get("scope") == scope
            and tuple(
                (field_name, _as_text(item.get(field_name)))
                for field_name in _CATALOG_REVIEW_SCOPE_FIELDS[scope]
                if _as_text(item.get(field_name))
            )
            == identity
        ),
        None,
    )
    _append_catalog_audit_trail(decision, previous)

    filtered_decisions = [
        item
        for item in existing_decisions
        if (
            item.get("scope") != scope
            or tuple(
                (field_name, _as_text(item.get(field_name)))
                for field_name in _CATALOG_REVIEW_SCOPE_FIELDS[scope]
                if _as_text(item.get(field_name))
            )
            != identity
        )
    ]
    filtered_decisions.append(decision)
    filtered_decisions = _normalize_catalog_review_decisions(filtered_decisions)
    return {
        "asset_kind": _CATALOG_REVIEW_ASSET_KIND,
        "decision_count": len(filtered_decisions),
        "updated_at": decision.get("reviewed_at"),
        "last_reviewer": decision.get("reviewer"),
        "decisions": filtered_decisions,
    }


def upsert_observe_catalog_review_artifact_content_batch(
    raw_content: Any,
    raw_decisions: Any,
) -> Dict[str, Any]:
    """Apply multiple catalog review decisions in one pass, preserving audit trails."""
    payload = _as_dict(raw_decisions)
    items: List[Any] = list(raw_decisions) if isinstance(raw_decisions, list) else list(payload.get("decisions") or [])
    if not items:
        return {}

    content = raw_content
    normalized_decisions: List[Dict[str, Any]] = []
    for raw_decision in items:
        normalized_decision = normalize_observe_catalog_review_decision(raw_decision)
        if not normalized_decision:
            continue
        normalized_decisions.append(normalized_decision)
        result = upsert_observe_catalog_review_artifact_content(content, raw_decision)
        if result:
            content = result

    if not isinstance(content, dict) or not content or not normalized_decisions:
        return {}

    applied_at = _as_text(payload.get("applied_at")) or _as_text(content.get("updated_at")) or _utc_now_iso()
    reviewer = _as_text(payload.get("reviewer")) or _as_text(content.get("last_reviewer"))
    batch_entry = _build_catalog_batch_audit_entry(
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


def _normalize_temporal_semantics(
    value: Any,
    *,
    dynasty: str = "",
    author: str = "",
    edition: str = "",
) -> Dict[str, Any]:
    payload = _as_dict(value)
    dynasties = _unique_texts([*_as_string_list(payload.get("dynasties")), payload.get("dynasty"), dynasty])
    authors = _unique_texts([*_as_string_list(payload.get("authors")), payload.get("author"), author])
    editions = _unique_texts([*_as_string_list(payload.get("editions")), payload.get("edition"), edition])
    semantic_hint = _as_text(payload.get("semantic_hint"))
    note = _as_text(payload.get("note"))

    if not semantic_hint:
        semantic_hint = " / ".join(part for part in (dynasties[:1] + authors[:1] + editions[:1]) if part)

    normalized: Dict[str, Any] = {}
    if dynasties:
        normalized["dynasties"] = dynasties
        normalized["dynasty"] = dynasties[0]
    if authors:
        normalized["authors"] = authors
        normalized["author"] = authors[0]
    if editions:
        normalized["editions"] = editions
        normalized["edition"] = editions[0]
    if semantic_hint:
        normalized["semantic_hint"] = semantic_hint
    if note:
        normalized["note"] = note
    return normalized


def _normalize_exegesis_entries(value: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in _as_dict_list(value):
        canonical = _as_text(item.get("canonical"))
        semantic_scope = _as_text(item.get("semantic_scope") or item.get("label"))
        identity = (canonical, semantic_scope)
        if not canonical or identity in seen:
            continue
        seen.add(identity)
        review_status = _normalize_review_status(item.get("review_status")) or "pending"
        review_reasons = _unique_texts(_as_string_list(item.get("review_reasons")))
        if not review_reasons:
            review_reasons = ["catalog_summary_machine_generated"]
        entry: Dict[str, Any] = {
            "canonical": canonical,
            "label": _as_text(item.get("label") or semantic_scope),
            "definition": _as_text(item.get("definition")),
            "definition_source": _as_text(item.get("definition_source")),
            "semantic_scope": semantic_scope,
            "observed_forms": _as_string_list(item.get("observed_forms")),
            "configured_variants": _as_string_list(item.get("configured_variants")),
            "sources": _as_string_list(item.get("sources")),
            "source_refs": _as_string_list(item.get("source_refs")),
            "notes": _as_string_list(item.get("notes")),
            "dynasty_usage": _unique_texts(_as_string_list(item.get("dynasty_usage"))),
            "disambiguation_basis": _unique_texts(
                [
                    *_as_string_list(item.get("disambiguation_basis")),
                    *_as_string_list(item.get("sources")),
                    *_as_string_list(item.get("source_refs")),
                ]
            ),
            "review_status": review_status,
            "needs_manual_review": bool(item.get("needs_manual_review", True)),
            "review_reasons": review_reasons,
            "exegesis_notes": _as_text(item.get("exegesis_notes")),
        }
        entries.append(entry)
    return entries


def _catalog_entry_has_baseline_fields(entry: Mapping[str, Any]) -> bool:
    return has_baseline_fields(entry)


def _normalize_catalog_document(record: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = {
        "document_id": _as_text(record.get("document_id") or record.get("id")),
        "document_title": _as_text(record.get("document_title") or record.get("title")),
        "document_urn": _as_text(record.get("document_urn") or record.get("urn")),
        "source_type": _as_text(record.get("source_type")),
        "catalog_id": _as_text(record.get("catalog_id")),
        "work_title": _as_text(record.get("work_title")),
        "fragment_title": _as_text(record.get("fragment_title")),
        "work_fragment_key": _as_text(record.get("work_fragment_key")),
        "version_lineage_key": _as_text(record.get("version_lineage_key")),
        "witness_key": _as_text(record.get("witness_key")),
        "dynasty": _as_text(record.get("dynasty")),
        "author": _as_text(record.get("author")),
        "edition": _as_text(record.get("edition")),
        "lineage_source": _as_text(record.get("lineage_source")),
    }
    completeness_result = assess_catalog_completeness(normalized)
    missing_core_fields = completeness_result["missing_core_fields"]
    normalized["missing_core_fields"] = missing_core_fields
    normalized["metadata_completeness"] = completeness_result["metadata_completeness"]
    normalized["needs_backfill"] = completeness_result["needs_backfill"]
    normalized["backfill_candidates"] = completeness_result["backfill_candidates"]
    temporal_semantics = _normalize_temporal_semantics(
        record.get("temporal_semantics"),
        dynasty=normalized["dynasty"],
        author=normalized["author"],
        edition=normalized["edition"],
    )
    if temporal_semantics:
        normalized["temporal_semantics"] = temporal_semantics

    exegesis_entries = _normalize_exegesis_entries(record.get("exegesis_entries"))
    if exegesis_entries:
        normalized["exegesis_entries"] = exegesis_entries

    review_status = _normalize_review_status(record.get("review_status"))
    review_reasons = _unique_texts(
        [*_as_string_list(record.get("review_reasons")), *[f"missing:{field_name}" for field_name in missing_core_fields]]
    )
    explicit_needs_manual_review = record.get("needs_manual_review") if "needs_manual_review" in record else None
    needs_manual_review = _resolve_needs_manual_review(
        review_status,
        review_reasons,
        explicit_value=explicit_needs_manual_review,
    )
    if review_status:
        normalized["review_status"] = review_status
    elif needs_manual_review:
        normalized["review_status"] = "pending"
    if needs_manual_review:
        normalized["needs_manual_review"] = True
    elif explicit_needs_manual_review is False:
        normalized["needs_manual_review"] = False
    if review_reasons:
        normalized["review_reasons"] = review_reasons
    reviewer = _as_text(record.get("reviewer"))
    reviewed_at = _as_text(record.get("reviewed_at"))
    decision_basis = _as_text(record.get("decision_basis"))
    review_source = _as_text(record.get("review_source"))
    if reviewer:
        normalized["reviewer"] = reviewer
    if reviewed_at:
        normalized["reviewed_at"] = reviewed_at
    if decision_basis:
        normalized["decision_basis"] = decision_basis
    if review_source:
        normalized["review_source"] = review_source

    related_collation_entry_count = _safe_int(record.get("related_collation_entry_count"), 0)
    if related_collation_entry_count > 0:
        normalized["related_collation_entry_count"] = related_collation_entry_count
    return normalized


def _normalize_catalog_witness(record: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = {
        "document_id": _as_text(record.get("document_id") or record.get("id")),
        "urn": _as_text(record.get("urn") or record.get("document_urn")),
        "title": _as_text(record.get("title") or record.get("document_title")),
        "source_type": _as_text(record.get("source_type")),
        "catalog_id": _as_text(record.get("catalog_id")),
        "witness_key": _as_text(record.get("witness_key")),
        "dynasty": _as_text(record.get("dynasty")),
        "author": _as_text(record.get("author")),
        "edition": _as_text(record.get("edition")),
    }
    temporal_semantics = _normalize_temporal_semantics(
        record.get("temporal_semantics"),
        dynasty=normalized["dynasty"],
        author=normalized["author"],
        edition=normalized["edition"],
    )
    if temporal_semantics:
        normalized["temporal_semantics"] = temporal_semantics

    review_status = _normalize_review_status(record.get("review_status"))
    review_reasons = _unique_texts(_as_string_list(record.get("review_reasons")))
    explicit_needs_manual_review = record.get("needs_manual_review") if "needs_manual_review" in record else None
    needs_manual_review = _resolve_needs_manual_review(
        review_status,
        review_reasons,
        explicit_value=explicit_needs_manual_review,
    )
    if review_status:
        normalized["review_status"] = review_status
    elif needs_manual_review:
        normalized["review_status"] = "pending"
    if needs_manual_review:
        normalized["needs_manual_review"] = True
    elif explicit_needs_manual_review is False:
        normalized["needs_manual_review"] = False
    if review_reasons:
        normalized["review_reasons"] = review_reasons
    reviewer = _as_text(record.get("reviewer"))
    reviewed_at = _as_text(record.get("reviewed_at"))
    decision_basis = _as_text(record.get("decision_basis"))
    review_source = _as_text(record.get("review_source"))
    if reviewer:
        normalized["reviewer"] = reviewer
    if reviewed_at:
        normalized["reviewed_at"] = reviewed_at
    if decision_basis:
        normalized["decision_basis"] = decision_basis
    if review_source:
        normalized["review_source"] = review_source
    return normalized


def _normalize_catalog_documents(raw_documents: Any) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in _as_dict_list(raw_documents):
        if not _catalog_entry_has_baseline_fields(item):
            continue
        normalized = _normalize_catalog_document(item)
        identity = _as_text(
            normalized.get("document_id")
            or normalized.get("witness_key")
            or normalized.get("document_urn")
            or normalized.get("document_title")
        )
        if not identity or identity in seen:
            continue
        seen.add(identity)
        documents.append(normalized)
    documents.sort(
        key=lambda item: (
            str(item.get("work_title") or ""),
            str(item.get("fragment_title") or ""),
            str(item.get("edition") or ""),
            str(item.get("document_title") or ""),
            str(item.get("document_urn") or ""),
        )
    )
    return documents


def _build_catalog_lineages(documents: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    seen_witnesses: set[tuple[str, str]] = set()

    for document in documents:
        lineage_key = _as_text(
            document.get("version_lineage_key")
            or document.get("work_fragment_key")
            or document.get("witness_key")
            or document.get("document_urn")
            or document.get("document_title")
        )
        if not lineage_key:
            continue

        group = grouped.setdefault(
            lineage_key,
            {
                "version_lineage_key": _as_text(document.get("version_lineage_key") or lineage_key),
                "work_fragment_key": _as_text(document.get("work_fragment_key")),
                "work_title": _as_text(document.get("work_title")),
                "fragment_title": _as_text(document.get("fragment_title")),
                "dynasty": _as_text(document.get("dynasty")),
                "author": _as_text(document.get("author")),
                "edition": _as_text(document.get("edition")),
                "witnesses": [],
            },
        )

        witness = _normalize_catalog_witness(document)
        witness_identity = _as_text(
            witness.get("witness_key")
            or witness.get("document_id")
            or witness.get("urn")
            or witness.get("title")
            or witness.get("catalog_id")
        )
        if witness_identity:
            seen_key = (lineage_key, witness_identity)
            if seen_key in seen_witnesses:
                continue
            seen_witnesses.add(seen_key)
        group["witnesses"].append(witness)

    ordered = sorted(
        grouped.values(),
        key=lambda item: (
            str(item.get("work_title") or ""),
            str(item.get("fragment_title") or ""),
            str(item.get("edition") or ""),
            str(item.get("version_lineage_key") or ""),
        ),
    )
    for item in ordered:
        witnesses = [dict(witness) for witness in item.get("witnesses") or [] if isinstance(witness, Mapping)]
        witnesses.sort(
            key=lambda witness: (
                str(witness.get("source_type") or ""),
                str(witness.get("title") or ""),
                str(witness.get("urn") or ""),
                str(witness.get("witness_key") or ""),
            )
        )
        item["witnesses"] = witnesses
        item["witness_count"] = len(witnesses)
    return ordered


def _normalize_catalog_lineages(raw_lineages: Any) -> List[Dict[str, Any]]:
    normalized_documents: List[Dict[str, Any]] = []
    for item in _as_dict_list(raw_lineages):
        base_fields = {
            "work_title": item.get("work_title"),
            "fragment_title": item.get("fragment_title"),
            "work_fragment_key": item.get("work_fragment_key"),
            "version_lineage_key": item.get("version_lineage_key"),
            "dynasty": item.get("dynasty"),
            "author": item.get("author"),
            "edition": item.get("edition"),
        }
        for witness in _as_dict_list(item.get("witnesses")):
            normalized_documents.append(
                _normalize_catalog_document(
                    {
                        **base_fields,
                        "document_id": witness.get("document_id") or witness.get("id"),
                        "document_title": witness.get("title") or witness.get("document_title"),
                        "document_urn": witness.get("urn") or witness.get("document_urn"),
                        "source_type": witness.get("source_type"),
                        "catalog_id": witness.get("catalog_id"),
                        "witness_key": witness.get("witness_key"),
                    }
                )
            )
    if normalized_documents:
        return _build_catalog_lineages(_normalize_catalog_documents(normalized_documents))
    return []


def _build_catalog_summary_metrics(
    documents: Sequence[Mapping[str, Any]],
    version_lineages: Sequence[Mapping[str, Any]],
    base_summary: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = dict(base_summary or {})
    witnesses: List[Dict[str, Any]] = []
    for lineage in version_lineages:
        witnesses.extend(_as_dict_list(lineage.get("witnesses")))

    if documents:
        catalog_document_count = len(documents)
        work_count = len({_as_text(item.get("work_title")) for item in documents if _as_text(item.get("work_title"))})
        work_fragment_count = len(
            {
                _as_text(item.get("work_fragment_key") or f"{_as_text(item.get('work_title'))}|{_as_text(item.get('fragment_title'))}")
                for item in documents
                if _as_text(item.get("work_fragment_key") or item.get("work_title") or item.get("fragment_title"))
            }
        )
        version_lineage_count = len(version_lineages)
        witness_count = len(
            {
                _as_text(item.get("witness_key") or item.get("document_id") or item.get("document_urn") or item.get("document_title"))
                for item in documents
                if _as_text(item.get("witness_key") or item.get("document_id") or item.get("document_urn") or item.get("document_title"))
            }
        )
        catalog_id_count = len({_as_text(item.get("catalog_id")) for item in documents if _as_text(item.get("catalog_id"))})
        missing_core_metadata_count = sum(1 for item in documents if item.get("missing_core_fields"))
        source_type_counts = _count_values(documents, "source_type")
        lineage_source_counts = _count_values(documents, "lineage_source")
    elif version_lineages:
        catalog_document_count = sum(
            max(_safe_int(item.get("witness_count"), 0), len(_as_dict_list(item.get("witnesses"))))
            for item in version_lineages
        )
        work_count = len({_as_text(item.get("work_title")) for item in version_lineages if _as_text(item.get("work_title"))})
        work_fragment_count = len(
            {
                _as_text(item.get("work_fragment_key") or f"{_as_text(item.get('work_title'))}|{_as_text(item.get('fragment_title'))}")
                for item in version_lineages
                if _as_text(item.get("work_fragment_key") or item.get("work_title") or item.get("fragment_title"))
            }
        )
        version_lineage_count = len(version_lineages)
        witness_count = len(
            {
                _as_text(item.get("witness_key") or item.get("document_id") or item.get("urn") or item.get("title") or item.get("catalog_id"))
                for item in witnesses
                if _as_text(item.get("witness_key") or item.get("document_id") or item.get("urn") or item.get("title") or item.get("catalog_id"))
            }
        )
        catalog_id_count = len({_as_text(item.get("catalog_id")) for item in witnesses if _as_text(item.get("catalog_id"))})
        missing_core_metadata_count = _safe_int(summary.get("missing_core_metadata_count"), 0)
        source_type_counts = _count_values(witnesses, "source_type")
        lineage_source_counts = _normalize_count_mapping(summary.get("lineage_source_counts"))
    else:
        catalog_document_count = _safe_int(summary.get("catalog_document_count"), 0)
        work_count = _safe_int(summary.get("work_count"), 0)
        work_fragment_count = _safe_int(summary.get("work_fragment_count"), 0)
        version_lineage_count = _safe_int(summary.get("version_lineage_count"), 0)
        witness_count = _safe_int(summary.get("witness_count"), 0)
        catalog_id_count = _safe_int(summary.get("catalog_id_count"), 0)
        missing_core_metadata_count = _safe_int(summary.get("missing_core_metadata_count"), 0)
        source_type_counts = _normalize_count_mapping(summary.get("source_type_counts"))
        lineage_source_counts = _normalize_count_mapping(summary.get("lineage_source_counts"))

    dynasty_counts: Dict[str, int] = {}
    exegesis_identities: set[tuple[str, str]] = set()
    temporal_semantic_count = 0
    review_status_counts: Dict[str, int] = {}
    needs_manual_review_count = 0
    for item in documents:
        temporal_semantics = _as_dict(item.get("temporal_semantics"))
        dynasties = _unique_texts([*_as_string_list(temporal_semantics.get("dynasties")), item.get("dynasty")])
        if dynasties or temporal_semantics:
            temporal_semantic_count += 1
        for dynasty in dynasties:
            dynasty_counts[dynasty] = dynasty_counts.get(dynasty, 0) + 1
        for entry in _as_dict_list(item.get("exegesis_entries")):
            canonical = _as_text(entry.get("canonical"))
            semantic_scope = _as_text(entry.get("semantic_scope") or entry.get("label"))
            if canonical:
                exegesis_identities.add((canonical, semantic_scope))
        review_status = _normalize_review_status(item.get("review_status"))
        if review_status:
            review_status_counts[review_status] = review_status_counts.get(review_status, 0) + 1
        if bool(item.get("needs_manual_review")):
            needs_manual_review_count += 1

    summary.update(
        {
            "catalog_document_count": catalog_document_count,
            "work_count": work_count,
            "work_fragment_count": work_fragment_count,
            "version_lineage_count": version_lineage_count,
            "witness_count": witness_count,
            "catalog_id_count": catalog_id_count,
            "missing_core_metadata_count": missing_core_metadata_count,
            "source_type_counts": source_type_counts,
            "lineage_source_counts": lineage_source_counts,
            "exegesis_entry_count": len(exegesis_identities),
            "temporal_semantic_count": temporal_semantic_count,
            "dynasty_counts": {key: dynasty_counts[key] for key in sorted(dynasty_counts)},
            "review_status_counts": {key: review_status_counts[key] for key in sorted(review_status_counts)},
            "pending_review_count": review_status_counts.get("pending", 0),
            "needs_manual_review_count": needs_manual_review_count,
        }
    )
    if documents:
        summary["catalog_hierarchy"] = build_catalog_hierarchy(documents)
        backfill = build_backfill_summary(documents)
        summary["needs_backfill_count"] = backfill["needs_backfill_count"]
        summary["backfill_field_gap_counts"] = backfill["field_gap_counts"]

    # 训诂摘要 — 汇聚 source distribution 与 category distribution
    all_exegesis: List[Dict[str, Any]] = []
    for item in documents:
        all_exegesis.extend(_as_dict_list(item.get("exegesis_entries")))
    if all_exegesis:
        exegesis_summary = build_exegesis_summary(all_exegesis)
        summary["exegesis_definition_coverage"] = exegesis_summary.get("definition_coverage", 0.0)
        summary["exegesis_source_distribution"] = exegesis_summary.get("source_distribution", {})
        summary["exegesis_category_distribution"] = exegesis_summary.get("category_distribution", {})
        summary["exegesis_disambiguation_count"] = exegesis_summary.get("disambiguation_count", 0)
        summary["exegesis_needs_disambiguation"] = exegesis_summary.get("needs_disambiguation", 0)
        summary["exegesis_dynasty_term_counts"] = exegesis_summary.get("dynasty_term_counts", {})

    return summary


def _normalize_catalog_summary(raw_catalog_summary: Any) -> Dict[str, Any]:
    payload = _as_dict(raw_catalog_summary)
    raw_summary = _as_dict(payload.get("summary"))
    documents = _normalize_catalog_documents(payload.get("documents"))
    version_lineages = _build_catalog_lineages(documents) if documents else _normalize_catalog_lineages(payload.get("version_lineages"))

    if not documents and not version_lineages and not raw_summary:
        return {}

    return {
        "summary": _build_catalog_summary_metrics(documents, version_lineages, raw_summary),
        "documents": documents,
        "version_lineages": version_lineages,
    }


def _extract_document_catalog_entry(document: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = _as_dict(document.get("metadata"))
    version_metadata = _as_dict(metadata.get("version_metadata"))
    if not version_metadata and isinstance(document.get("version_metadata"), Mapping):
        version_metadata = _as_dict(document.get("version_metadata"))

    raw_entry = {
        "document_id": document.get("id"),
        "document_title": document.get("title") or document.get("document_title"),
        "document_urn": document.get("urn") or document.get("document_urn"),
        "source_type": version_metadata.get("source_type") or document.get("source_type"),
        "catalog_id": version_metadata.get("catalog_id") or document.get("catalog_id"),
        "work_title": version_metadata.get("work_title") or document.get("work_title"),
        "fragment_title": version_metadata.get("fragment_title") or document.get("fragment_title"),
        "work_fragment_key": version_metadata.get("work_fragment_key") or document.get("work_fragment_key"),
        "version_lineage_key": version_metadata.get("version_lineage_key") or document.get("version_lineage_key"),
        "witness_key": version_metadata.get("witness_key") or document.get("witness_key"),
        "dynasty": version_metadata.get("dynasty") or document.get("dynasty"),
        "author": version_metadata.get("author") or document.get("author"),
        "edition": version_metadata.get("edition") or document.get("edition"),
        "lineage_source": version_metadata.get("lineage_source"),
    }
    if not _catalog_entry_has_baseline_fields(raw_entry):
        return {}
    return _normalize_catalog_document(raw_entry)


def _build_catalog_summary_from_documents(observe_documents: Sequence[Mapping[str, Any]] | None) -> Dict[str, Any]:
    catalog_documents: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for document in observe_documents or []:
        if not isinstance(document, Mapping):
            continue
        catalog_entry = _extract_document_catalog_entry(document)
        if not catalog_entry:
            continue
        identity = _as_text(
            catalog_entry.get("document_id")
            or catalog_entry.get("witness_key")
            or catalog_entry.get("document_urn")
            or catalog_entry.get("document_title")
        )
        if not identity or identity in seen:
            continue
        seen.add(identity)
        catalog_documents.append(catalog_entry)

    if not catalog_documents:
        return {}

    catalog_documents = _normalize_catalog_documents(catalog_documents)
    version_lineages = _build_catalog_lineages(catalog_documents)
    return {
        "summary": _build_catalog_summary_metrics(catalog_documents, version_lineages),
        "documents": catalog_documents,
        "version_lineages": version_lineages,
    }


def _catalog_lookup_token(prefix: str, value: Any) -> str:
    normalized = _as_text(value)
    if not normalized:
        return ""
    return f"{prefix}:{normalized}"


def _catalog_document_lookup_keys(
    record: Mapping[str, Any],
    *,
    title_key: str = "document_title",
    urn_key: str = "document_urn",
    witness_key_key: str = "witness_key",
    catalog_id_key: str = "catalog_id",
    document_id_key: str = "document_id",
) -> List[str]:
    keys = []
    for prefix, raw_value in (
        ("document", record.get(document_id_key) or record.get("id")),
        ("witness", record.get(witness_key_key)),
        ("urn", record.get(urn_key) or record.get("urn")),
        ("title", record.get(title_key) or record.get("title")),
        ("catalog", record.get(catalog_id_key)),
    ):
        token = _catalog_lookup_token(prefix, raw_value)
        if token and token not in keys:
            keys.append(token)
    return keys


def _build_catalog_document_lookup(documents: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for document in documents:
        normalized_document = dict(document)
        for key in _catalog_document_lookup_keys(normalized_document):
            lookup.setdefault(key, normalized_document)
    return lookup


def _lookup_catalog_document(
    record: Mapping[str, Any],
    lookup: Mapping[str, Mapping[str, Any]],
    *,
    title_key: str = "document_title",
    urn_key: str = "document_urn",
    witness_key_key: str = "witness_key",
    catalog_id_key: str = "catalog_id",
    document_id_key: str = "document_id",
) -> Dict[str, Any]:
    for key in _catalog_document_lookup_keys(
        record,
        title_key=title_key,
        urn_key=urn_key,
        witness_key_key=witness_key_key,
        catalog_id_key=catalog_id_key,
        document_id_key=document_id_key,
    ):
        match = lookup.get(key)
        if isinstance(match, Mapping):
            return dict(match)
    return {}


def _merge_text_lists(*value_groups: Sequence[Any]) -> List[str]:
    values: List[str] = []
    for group in value_groups:
        values.extend(_unique_texts(group))
    return _unique_texts(values)


def _resolve_exegesis_category(row: Mapping[str, Any], label: str) -> str:
    category = _as_text(row.get("category")).lower()
    if category in _EXEGESIS_LABEL_CATEGORY_MAP.values():
        return category
    return _EXEGESIS_LABEL_CATEGORY_MAP.get(label, "")


def _looks_like_machine_terminology_note(note: Any) -> bool:
    normalized = _as_text(note)
    if not normalized:
        return False
    return any(marker in normalized for marker in _EXEGESIS_MACHINE_NOTE_MARKERS)


def _resolve_note_based_exegesis_definition(
    notes: Sequence[str],
    sources: Sequence[str],
) -> Dict[str, Any]:
    curated_notes = [note for note in notes if not _looks_like_machine_terminology_note(note)]
    if not curated_notes:
        return {}
    if "config_terminology_standard" in sources:
        return {
            "definition": curated_notes[0],
            "definition_source": "config_terminology_standard",
            "source_refs": ["config_terminology_standard"],
        }
    return {
        "definition": curated_notes[0],
        "definition_source": "terminology_note",
        "source_refs": _unique_texts([*sources[:1], "terminology_note"]),
    }


def _build_structured_knowledge_exegesis_definition(
    canonical: str,
    *,
    category: str,
    label: str,
) -> Dict[str, Any]:
    display_label = label or canonical
    if category == "herb":
        efficacies = _unique_texts(TCMRelationshipDefinitions.get_herb_efficacy(canonical))
        properties = {
            key: _as_text(value)
            for key, value in TCMRelationshipDefinitions.get_herb_properties(canonical).items()
            if _as_text(value)
        }
        if not efficacies and not properties:
            return {}
        parts = [f"{canonical}为{display_label}"]
        source_refs: List[str] = []
        if efficacies:
            parts.append(f"常见功效：{'、'.join(efficacies)}")
            source_refs.append("TCMRelationshipDefinitions.HERB_EFFICACY_MAP")
        property_parts: List[str] = []
        if properties.get("气"):
            property_parts.append(f"气{properties['气']}")
        if properties.get("味"):
            property_parts.append(f"味{properties['味']}")
        if property_parts:
            parts.append(f"四气五味：{'，'.join(property_parts)}")
            source_refs.append("TCMRelationshipDefinitions.HERB_PROPERTIES")
        return {
            "definition": "；".join(parts),
            "definition_source": "structured_tcm_knowledge",
            "source_refs": source_refs,
        }
    if category == "formula":
        composition = TCMRelationshipDefinitions.get_formula_composition(canonical)
        if not composition:
            return {}
        composition_parts: List[str] = []
        for role_name in ("sovereign", "minister", "assistant", "envoy"):
            members = _unique_texts(composition.get(role_name) or [])
            if not members:
                continue
            composition_parts.append(
                f"{_FORMULA_COMPOSITION_ROLE_LABELS.get(role_name, role_name)}：{'、'.join(members)}"
            )
        definition = f"{canonical}为{display_label}"
        if composition_parts:
            definition = f"{definition}；常见组成：{'；'.join(composition_parts)}"
        return {
            "definition": definition,
            "definition_source": "structured_tcm_knowledge",
            "source_refs": ["TCMRelationshipDefinitions.FORMULA_COMPOSITIONS"],
        }
    if category == "syndrome":
        syndrome_info = TCMRelationshipDefinitions.get_syndrome_definition(canonical)
        if not syndrome_info:
            return {}
        parts = [f"{canonical}：{syndrome_info.get('definition', '')}"]
        symptoms = syndrome_info.get("symptoms") or []
        if symptoms:
            parts.append(f"典型表现：{'、'.join(symptoms)}")
        pathogenesis = _as_text(syndrome_info.get("pathogenesis"))
        if pathogenesis:
            parts.append(f"病机：{pathogenesis}")
        return {
            "definition": "；".join(parts),
            "definition_source": "structured_tcm_knowledge",
            "source_refs": ["TCMRelationshipDefinitions.SYNDROME_DEFINITIONS"],
        }
    if category == "theory":
        theory_def = TCMRelationshipDefinitions.get_theory_term_definition(canonical)
        if not theory_def:
            return {}
        return {
            "definition": f"{canonical}：{theory_def}",
            "definition_source": "structured_tcm_knowledge",
            "source_refs": ["TCMRelationshipDefinitions.THEORY_TERM_DEFINITIONS"],
        }
    return {}


def _resolve_exegesis_definition(
    row: Mapping[str, Any],
    *,
    canonical: str,
    label: str,
) -> Dict[str, Any]:
    notes = _as_string_list(row.get("notes"))
    sources = _as_string_list(row.get("sources"))
    note_based_definition = _resolve_note_based_exegesis_definition(notes, sources)
    if note_based_definition.get("definition_source") == "config_terminology_standard":
        return note_based_definition
    category = _resolve_exegesis_category(row, label)
    structured_definition = _build_structured_knowledge_exegesis_definition(
        canonical,
        category=category,
        label=label,
    )
    if structured_definition:
        return structured_definition
    if note_based_definition:
        return note_based_definition
    return {}


def _exegesis_definition_source_rank(value: Any) -> int:
    normalized = _as_text(value)
    if normalized == "config_terminology_standard":
        return 4
    if normalized == "structured_tcm_knowledge":
        return 3
    if normalized == "terminology_note":
        return 2
    if normalized == "canonical_fallback":
        return 1
    return 0


def _merge_exegesis_entries(entries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[tuple[str, str], Dict[str, Any]] = {}
    for raw_entry in entries:
        for entry in _normalize_exegesis_entries([raw_entry]):
            identity = (_as_text(entry.get("canonical")), _as_text(entry.get("semantic_scope") or entry.get("label")))
            current = merged.get(identity)
            if current is None:
                merged[identity] = dict(entry)
                continue

            for field_name in (
                "observed_forms",
                "configured_variants",
                "sources",
                "source_refs",
                "notes",
                "dynasty_usage",
                "disambiguation_basis",
                "review_reasons",
            ):
                current[field_name] = _merge_text_lists(
                    current.get(field_name) or [],
                    entry.get(field_name) or [],
                )
            current_rank = _exegesis_definition_source_rank(current.get("definition_source"))
            entry_rank = _exegesis_definition_source_rank(entry.get("definition_source"))
            if (not current.get("definition") and entry.get("definition")) or entry_rank > current_rank:
                current["definition"] = entry.get("definition") or current.get("definition")
                current["definition_source"] = entry.get("definition_source") or current.get("definition_source")
            current["needs_manual_review"] = bool(current.get("needs_manual_review")) or bool(entry.get("needs_manual_review"))
            current["review_status"] = _normalize_review_status(current.get("review_status") or entry.get("review_status")) or "pending"

    return [
        merged[key]
        for key in sorted(
            merged,
            key=lambda item: (
                item[0],
                item[1],
            ),
        )
    ]


def _build_exegesis_entry_from_row(row: Mapping[str, Any], *, dynasty: str = "") -> Dict[str, Any]:
    canonical = _as_text(row.get("canonical"))
    if not canonical:
        return {}

    label = _as_text(row.get("label") or row.get("category") or "待判定义项")
    observed_forms = _as_string_list(row.get("observed_forms"))
    configured_variants = _as_string_list(row.get("configured_variants"))
    sources = _as_string_list(row.get("sources"))
    notes = _as_string_list(row.get("notes"))

    # 若 terminology_row 已携带 PhilologyService 填充的释义，优先尊重
    row_definition = _as_text(row.get(FIELD_DEFINITION))
    row_definition_source = _as_text(row.get(FIELD_DEFINITION_SOURCE))
    derived_payload = _resolve_exegesis_definition(
        row,
        canonical=canonical,
        label=label,
    )
    derived_rank = _exegesis_definition_source_rank(derived_payload.get("definition_source"))
    row_rank = definition_source_rank(row_definition_source)
    if row_definition and row_rank >= derived_rank:
        definition = row_definition
        definition_source = row_definition_source or "canonical_fallback"
        source_refs = _as_string_list(row.get("disambiguation_basis"))
    else:
        definition = _as_text(derived_payload.get("definition"))
        definition_source = _as_text(derived_payload.get("definition_source")) or "canonical_fallback"
        source_refs = _as_string_list(derived_payload.get("source_refs"))
    if not definition:
        if observed_forms:
            definition = f"{canonical} 暂据术语标准表归并自 {observed_forms[0]}"
        else:
            definition = f"{canonical} 暂据术语标准表归入 {label}"

    if definition_source in {"config_terminology_standard", "structured_tcm_knowledge"}:
        review_reasons = ["exegesis_authority_resolved", f"definition_source:{definition_source}"]
    elif definition_source == "terminology_note":
        review_reasons = ["exegesis_note_sourced", "definition_source:terminology_note"]
    else:
        review_reasons = ["exegesis_machine_derived", "definition_source:canonical_fallback"]
    if _as_text(row.get("status")).lower() and _as_text(row.get("status")).lower() != "standardized":
        review_reasons.append("terminology_not_fully_standardized")

    return {
        "canonical": canonical,
        "label": label,
        "definition": definition,
        "definition_source": definition_source,
        "semantic_scope": label,
        "observed_forms": observed_forms,
        "configured_variants": configured_variants,
        "sources": sources,
        "source_refs": source_refs,
        "notes": notes,
        "dynasty_usage": _unique_texts([dynasty, row.get("dynasty")]),
        "disambiguation_basis": _merge_text_lists(sources, source_refs, notes[:1], observed_forms[:1]),
        "exegesis_notes": _as_text(row.get("exegesis_notes")) or build_exegesis_note(
            canonical, definition_source,
            category=_as_text(row.get("category")),
            disambiguation_basis=_merge_text_lists(sources, source_refs),
        ),
        "review_status": "pending",
        "needs_manual_review": True,
        "review_reasons": review_reasons,
    }


def _resolve_review_state(
    record: Mapping[str, Any],
    *,
    related_collation_entry_count: int,
    exegesis_count: int,
    missing_core_fields: Sequence[str],
) -> tuple[str, bool, List[str]]:
    review_status = _normalize_review_status(record.get("review_status"))
    review_reasons = _merge_text_lists(
        _as_string_list(record.get("review_reasons")),
        [f"missing:{field_name}" for field_name in missing_core_fields],
    )
    if related_collation_entry_count > 0:
        review_reasons = _merge_text_lists(review_reasons, ["version_collation_present"])
    if exegesis_count > 0:
        review_reasons = _merge_text_lists(review_reasons, ["exegesis_machine_derived"])

    explicit_needs_manual_review = record.get("needs_manual_review") if "needs_manual_review" in record else None
    needs_manual_review = _resolve_needs_manual_review(
        review_status,
        review_reasons,
        explicit_value=explicit_needs_manual_review,
    )
    if needs_manual_review and not review_reasons:
        review_reasons = ["catalog_summary_machine_generated"]
    if not review_status and needs_manual_review:
        review_status = "pending"
    return review_status, needs_manual_review, review_reasons


def _catalog_review_matches_document(decision: Mapping[str, Any], document: Mapping[str, Any]) -> bool:
    scope = _normalize_catalog_review_scope(decision.get("scope"))
    if scope == "version_lineage":
        return _record_matches_catalog_review_identifiers(decision, document, ("version_lineage_key",))
    if scope == "witness":
        return _record_matches_catalog_review_identifiers(decision, document, _CATALOG_REVIEW_SCOPE_FIELDS["witness"])
    if scope == "document":
        return _record_matches_catalog_review_identifiers(decision, document, _CATALOG_REVIEW_SCOPE_FIELDS["document"])
    return False


def _catalog_review_matches_witness(
    decision: Mapping[str, Any],
    witness: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> bool:
    combined = {
        **dict(lineage),
        **dict(witness),
        "document_title": witness.get("document_title") or witness.get("title"),
        "document_urn": witness.get("document_urn") or witness.get("urn"),
    }
    scope = _normalize_catalog_review_scope(decision.get("scope"))
    if scope == "version_lineage":
        return _record_matches_catalog_review_identifiers(decision, combined, ("version_lineage_key",))
    if scope == "witness":
        return _record_matches_catalog_review_identifiers(decision, combined, _CATALOG_REVIEW_SCOPE_FIELDS["witness"])
    if scope == "document":
        return _record_matches_catalog_review_identifiers(decision, combined, _CATALOG_REVIEW_SCOPE_FIELDS["document"])
    return False


def _catalog_review_matches_lineage(decision: Mapping[str, Any], lineage: Mapping[str, Any]) -> bool:
    scope = _normalize_catalog_review_scope(decision.get("scope"))
    if scope != "version_lineage":
        return False
    return _record_matches_catalog_review_identifiers(decision, lineage, ("version_lineage_key",))


def _apply_catalog_review_decision(record: Mapping[str, Any], decision: Mapping[str, Any]) -> Dict[str, Any]:
    updated = dict(record)
    updated["review_status"] = _normalize_review_status(decision.get("review_status")) or updated.get("review_status")
    updated["needs_manual_review"] = bool(decision.get("needs_manual_review"))
    updated["review_reasons"] = _unique_texts(_as_string_list(decision.get("review_reasons")))
    updated["review_source"] = _as_text(decision.get("review_source") or "manual_review")
    reviewer = _as_text(decision.get("reviewer"))
    reviewed_at = _as_text(decision.get("reviewed_at"))
    decision_basis = _as_text(decision.get("decision_basis"))
    if reviewer:
        updated["reviewer"] = reviewer
    if reviewed_at:
        updated["reviewed_at"] = reviewed_at
    if decision_basis:
        updated["decision_basis"] = decision_basis
    return updated


def _apply_catalog_review_decisions(
    catalog_summary: Mapping[str, Any],
    raw_review_decisions: Any,
) -> Dict[str, Any]:
    catalog_payload = _as_dict(catalog_summary)
    review_decisions = _normalize_catalog_review_decisions(raw_review_decisions)
    if not catalog_payload or not review_decisions:
        return catalog_payload

    documents = _as_dict_list(catalog_payload.get("documents"))
    version_lineages = _as_dict_list(catalog_payload.get("version_lineages"))
    ordered_decisions = sorted(
        review_decisions,
        key=lambda item: (
            _CATALOG_REVIEW_SCOPE_ORDER.get(str(item.get("scope") or ""), 99),
            str(item.get("reviewed_at") or ""),
        ),
    )

    updated_documents: List[Dict[str, Any]] = []
    for document in documents:
        updated_document = dict(document)
        for decision in ordered_decisions:
            if _catalog_review_matches_document(decision, updated_document):
                updated_document = _apply_catalog_review_decision(updated_document, decision)
        updated_documents.append(_normalize_catalog_document(updated_document))

    updated_document_lookup = _build_catalog_document_lookup(updated_documents)
    updated_lineages: List[Dict[str, Any]] = []
    for lineage in version_lineages:
        updated_lineage = dict(lineage)
        updated_witnesses: List[Dict[str, Any]] = []
        for witness in _as_dict_list(lineage.get("witnesses")):
            updated_witness = dict(witness)
            matched_document = _lookup_catalog_document(
                witness,
                updated_document_lookup,
                title_key="title",
                urn_key="urn",
                witness_key_key="witness_key",
                catalog_id_key="catalog_id",
                document_id_key="document_id",
            )
            if matched_document:
                for field_name in (
                    "review_status",
                    "needs_manual_review",
                    "review_reasons",
                    "reviewer",
                    "reviewed_at",
                    "decision_basis",
                    "review_source",
                ):
                    if field_name in matched_document:
                        updated_witness[field_name] = matched_document[field_name]
            for decision in ordered_decisions:
                if _catalog_review_matches_witness(decision, updated_witness, updated_lineage):
                    updated_witness = _apply_catalog_review_decision(updated_witness, decision)
            updated_witnesses.append(_normalize_catalog_witness(updated_witness))

        updated_lineage["witnesses"] = updated_witnesses
        updated_lineage["witness_count"] = len(updated_witnesses)
        for decision in ordered_decisions:
            if _catalog_review_matches_lineage(decision, updated_lineage):
                updated_lineage = _apply_catalog_review_decision(updated_lineage, decision)

        if "review_status" not in updated_lineage:
            witness_statuses = _unique_texts([witness.get("review_status") for witness in updated_witnesses])
            if len(witness_statuses) == 1 and witness_statuses[0]:
                updated_lineage["review_status"] = witness_statuses[0]
        if "needs_manual_review" not in updated_lineage:
            if any(bool(witness.get("needs_manual_review")) for witness in updated_witnesses):
                updated_lineage["needs_manual_review"] = True
            elif updated_lineage.get("review_status") in {"accepted", "rejected"}:
                updated_lineage["needs_manual_review"] = False
        if not _as_string_list(updated_lineage.get("review_reasons")):
            witness_reasons = _unique_texts(
                [
                    reason
                    for witness in updated_witnesses
                    for reason in _as_string_list(witness.get("review_reasons"))
                ]
            )
            if witness_reasons:
                updated_lineage["review_reasons"] = witness_reasons
        updated_lineages.append(updated_lineage)

    summary = _build_catalog_summary_metrics(
        updated_documents,
        updated_lineages,
        _as_dict(catalog_payload.get("summary")),
    )
    return {
        "summary": summary,
        "documents": updated_documents,
        "version_lineages": updated_lineages,
    }


def _catalog_record_matches_document(
    record: Mapping[str, Any],
    document: Mapping[str, Any],
) -> bool:
    document_keys = set(_catalog_document_lookup_keys(document))
    if document_keys.intersection(_catalog_document_lookup_keys(record)):
        return True
    if document_keys.intersection(
        _catalog_document_lookup_keys(
            record,
            title_key="witness_title",
            urn_key="witness_urn",
            witness_key_key="witness_witness_key",
            catalog_id_key="witness_catalog_id",
            document_id_key="witness_document_id",
        )
    ):
        return True
    return False


def _enrich_terminology_rows_with_catalog_metadata(
    rows: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    lookup = _build_catalog_document_lookup(documents)
    enriched_rows: List[Dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        match = _lookup_catalog_document(row, lookup)
        if match:
            for field_name in (
                "catalog_id",
                "work_title",
                "fragment_title",
                "work_fragment_key",
                "version_lineage_key",
                "witness_key",
                "dynasty",
                "author",
                "edition",
                "lineage_source",
            ):
                if not _as_text(merged.get(field_name)) and _as_text(match.get(field_name)):
                    merged[field_name] = match[field_name]
        enriched_rows.append(merged)
    return enriched_rows


def _enrich_collation_entries_with_catalog_metadata(
    entries: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    lookup = _build_catalog_document_lookup(documents)
    enriched_entries: List[Dict[str, Any]] = []
    for entry in entries:
        merged = dict(entry)
        base_document = _lookup_catalog_document(entry, lookup)
        witness_document = _lookup_catalog_document(
            entry,
            lookup,
            title_key="witness_title",
            urn_key="witness_urn",
            witness_key_key="witness_witness_key",
            catalog_id_key="witness_catalog_id",
            document_id_key="witness_document_id",
        )
        if base_document:
            for field_name in (
                "catalog_id",
                "work_title",
                "fragment_title",
                "work_fragment_key",
                "version_lineage_key",
                "witness_key",
                "dynasty",
                "author",
                "edition",
                "lineage_source",
            ):
                if not _as_text(merged.get(field_name)) and _as_text(base_document.get(field_name)):
                    merged[field_name] = base_document[field_name]
                if _as_text(base_document.get(field_name)):
                    merged[f"base_{field_name}"] = base_document[field_name]
        if witness_document:
            for field_name in (
                "catalog_id",
                "work_title",
                "fragment_title",
                "work_fragment_key",
                "version_lineage_key",
                "witness_key",
                "dynasty",
                "author",
                "edition",
                "lineage_source",
                "document_id",
            ):
                if _as_text(witness_document.get(field_name)):
                    merged[f"witness_{field_name}"] = witness_document[field_name]
        enriched_entries.append(merged)
    return enriched_entries


def _enrich_fragment_candidates_with_catalog_metadata(
    entries: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    lookup = _build_catalog_document_lookup(documents)
    enriched_entries: List[Dict[str, Any]] = []
    for entry in entries:
        merged = dict(entry)
        base_document = _lookup_catalog_document(entry, lookup)
        witness_document = _lookup_catalog_document(
            entry,
            lookup,
            title_key="witness_title",
            urn_key="witness_urn",
            witness_key_key="witness_witness_key",
            catalog_id_key="witness_catalog_id",
            document_id_key="witness_document_id",
        )
        if base_document:
            for field_name in (
                "catalog_id",
                "work_title",
                "fragment_title",
                "work_fragment_key",
                "version_lineage_key",
                "witness_key",
                "dynasty",
                "author",
                "edition",
                "lineage_source",
                "document_id",
            ):
                if not _as_text(merged.get(field_name)) and _as_text(base_document.get(field_name)):
                    merged[field_name] = base_document[field_name]
                if _as_text(base_document.get(field_name)):
                    merged[f"base_{field_name}"] = base_document[field_name]
        if witness_document:
            for field_name in (
                "catalog_id",
                "work_title",
                "fragment_title",
                "work_fragment_key",
                "version_lineage_key",
                "witness_key",
                "dynasty",
                "author",
                "edition",
                "lineage_source",
                "document_id",
            ):
                if _as_text(witness_document.get(field_name)):
                    merged[f"witness_{field_name}"] = witness_document[field_name]
        enriched_entries.append(merged)
    return enriched_entries


def _enrich_document_reports_with_catalog_metadata(
    document_reports: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    lookup = _build_catalog_document_lookup(documents)
    enriched_reports: List[Dict[str, Any]] = []
    for report in document_reports:
        merged = dict(report)
        match = _lookup_catalog_document(report, lookup)
        if match:
            for field_name in (
                "catalog_id",
                "work_title",
                "fragment_title",
                "work_fragment_key",
                "version_lineage_key",
                "witness_key",
                "dynasty",
                "author",
                "edition",
                "lineage_source",
            ):
                if not _as_text(merged.get(field_name)) and _as_text(match.get(field_name)):
                    merged[field_name] = match[field_name]
        enriched_reports.append(merged)
    return enriched_reports


def _enrich_catalog_summary(
    catalog_summary: Mapping[str, Any],
    terminology_rows: Sequence[Mapping[str, Any]],
    collation_entries: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    catalog_payload = _as_dict(catalog_summary)
    documents = _normalize_catalog_documents(catalog_payload.get("documents"))
    if not documents:
        version_lineages = _normalize_catalog_lineages(catalog_payload.get("version_lineages"))
        if not version_lineages:
            return catalog_payload
        summary = _build_catalog_summary_metrics([], version_lineages, _as_dict(catalog_payload.get("summary")))
        return {
            "summary": summary,
            "documents": [],
            "version_lineages": version_lineages,
        }

    enriched_documents: List[Dict[str, Any]] = []
    document_lookup = _build_catalog_document_lookup(documents)
    for document in documents:
        document_rows = [row for row in terminology_rows if _catalog_record_matches_document(row, document)]
        document_collations = [entry for entry in collation_entries if _catalog_record_matches_document(entry, document)]
        exegesis_entries = _merge_exegesis_entries(
            [
                _build_exegesis_entry_from_row(row, dynasty=_as_text(document.get("dynasty")))
                for row in document_rows
                if _build_exegesis_entry_from_row(row, dynasty=_as_text(document.get("dynasty")))
            ]
        )
        temporal_semantics = _normalize_temporal_semantics(
            document.get("temporal_semantics"),
            dynasty=_as_text(document.get("dynasty")),
            author=_as_text(document.get("author")),
            edition=_as_text(document.get("edition")),
        )
        review_status, needs_manual_review, review_reasons = _resolve_review_state(
            document,
            related_collation_entry_count=len(document_collations),
            exegesis_count=len(exegesis_entries),
            missing_core_fields=_as_string_list(document.get("missing_core_fields")),
        )
        enriched_document = dict(document)
        if exegesis_entries:
            enriched_document["exegesis_entries"] = exegesis_entries
        if temporal_semantics:
            enriched_document["temporal_semantics"] = temporal_semantics
        if review_status:
            enriched_document["review_status"] = review_status
        if needs_manual_review:
            enriched_document["needs_manual_review"] = True
        if review_reasons:
            enriched_document["review_reasons"] = review_reasons
        if document_collations:
            enriched_document["related_collation_entry_count"] = len(document_collations)
        enriched_documents.append(_normalize_catalog_document(enriched_document))

    version_lineages = _build_catalog_lineages(enriched_documents)
    enriched_lineages: List[Dict[str, Any]] = []
    for lineage in version_lineages:
        lineage_key = _as_text(lineage.get("version_lineage_key") or lineage.get("work_fragment_key"))
        lineage_documents = [
            document
            for document in enriched_documents
            if _as_text(document.get("version_lineage_key") or document.get("work_fragment_key")) == lineage_key
        ]
        lineage_collations = [
            entry
            for entry in collation_entries
            if any(_catalog_record_matches_document(entry, document) for document in lineage_documents)
        ]
        lineage_exegesis = _merge_exegesis_entries(
            [
                entry
                for document in lineage_documents
                for entry in _as_dict_list(document.get("exegesis_entries"))
            ]
        )
        lineage_temporal_semantics = _normalize_temporal_semantics(
            {
                "dynasties": _unique_texts(
                    [
                        dynasty
                        for document in lineage_documents
                        for dynasty in _as_string_list(_as_dict(document.get("temporal_semantics")).get("dynasties"))
                    ]
                ),
                "authors": _unique_texts(
                    [
                        author
                        for document in lineage_documents
                        for author in _as_string_list(_as_dict(document.get("temporal_semantics")).get("authors"))
                    ]
                ),
                "editions": _unique_texts(
                    [
                        edition
                        for document in lineage_documents
                        for edition in _as_string_list(_as_dict(document.get("temporal_semantics")).get("editions"))
                    ]
                ),
            },
            dynasty=_as_text(lineage.get("dynasty")),
            author=_as_text(lineage.get("author")),
            edition=_as_text(lineage.get("edition")),
        )
        review_status, needs_manual_review, review_reasons = _resolve_review_state(
            lineage,
            related_collation_entry_count=len(lineage_collations),
            exegesis_count=len(lineage_exegesis),
            missing_core_fields=[],
        )
        witnesses: List[Dict[str, Any]] = []
        for witness in _as_dict_list(lineage.get("witnesses")):
            witness_document = _lookup_catalog_document(
                witness,
                document_lookup,
                title_key="title",
                urn_key="urn",
                witness_key_key="witness_key",
                catalog_id_key="catalog_id",
                document_id_key="document_id",
            )
            enriched_witness = dict(witness)
            if witness_document:
                if witness_document.get("temporal_semantics"):
                    enriched_witness["temporal_semantics"] = witness_document["temporal_semantics"]
                if witness_document.get("review_status"):
                    enriched_witness["review_status"] = witness_document["review_status"]
                if witness_document.get("needs_manual_review"):
                    enriched_witness["needs_manual_review"] = True
                if witness_document.get("review_reasons"):
                    enriched_witness["review_reasons"] = witness_document["review_reasons"]
            witnesses.append(_normalize_catalog_witness(enriched_witness))

        enriched_lineage = dict(lineage)
        if lineage_exegesis:
            enriched_lineage["exegesis_entries"] = lineage_exegesis
        if lineage_temporal_semantics:
            enriched_lineage["temporal_semantics"] = lineage_temporal_semantics
        if review_status:
            enriched_lineage["review_status"] = review_status
        elif any(witness.get("review_status") == "pending" for witness in witnesses):
            enriched_lineage["review_status"] = "pending"
        if needs_manual_review or any(witness.get("needs_manual_review") for witness in witnesses):
            enriched_lineage["needs_manual_review"] = True
        if review_reasons:
            enriched_lineage["review_reasons"] = review_reasons
        if lineage_collations:
            enriched_lineage["related_collation_entry_count"] = len(lineage_collations)
        enriched_lineage["witnesses"] = witnesses
        enriched_lineage["witness_count"] = len(witnesses)
        enriched_lineages.append(enriched_lineage)

    summary = _build_catalog_summary_metrics(
        enriched_documents,
        enriched_lineages,
        _as_dict(catalog_payload.get("summary")),
    )
    return {
        "summary": summary,
        "documents": enriched_documents,
        "version_lineages": enriched_lineages,
    }


def _record_filter_candidates(record: Mapping[str, Any], field_name: str) -> List[str]:
    if field_name == "document_title":
        return _unique_texts([
            record.get("document_title"),
            record.get("title"),
            record.get("witness_title"),
        ])
    if field_name == "work_title":
        return _unique_texts([
            record.get("work_title"),
            record.get("base_work_title"),
            record.get("witness_work_title"),
        ])
    if field_name == "version_lineage_key":
        return _unique_texts([
            record.get("version_lineage_key"),
            record.get("base_version_lineage_key"),
            record.get("witness_version_lineage_key"),
        ])
    if field_name == "witness_key":
        return _unique_texts([
            record.get("witness_key"),
            record.get("base_witness_key"),
            record.get("witness_witness_key"),
        ])
    return []


def _record_matches_catalog_filters(record: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for field_name in _CATALOG_FILTER_FIELDS:
        expected = _as_text(filters.get(field_name))
        if not expected:
            continue
        candidates = _record_filter_candidates(record, field_name)
        if expected not in candidates:
            return False
    return True


def _filter_catalog_lineages(
    version_lineages: Sequence[Mapping[str, Any]],
    filters: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    filtered_lineages: List[Dict[str, Any]] = []
    for lineage in version_lineages:
        witnesses = [
            _normalize_catalog_witness(witness)
            for witness in _as_dict_list(lineage.get("witnesses"))
            if _record_matches_catalog_filters(
                {
                    **dict(lineage),
                    **dict(witness),
                    "document_title": witness.get("title") or witness.get("document_title"),
                    "document_urn": witness.get("urn") or witness.get("document_urn"),
                },
                filters,
            )
        ]
        lineage_payload = dict(lineage)
        lineage_payload["witnesses"] = witnesses
        lineage_payload["witness_count"] = len(witnesses)
        if witnesses or _record_matches_catalog_filters(lineage_payload, filters):
            filtered_lineages.append(lineage_payload)
    return filtered_lineages


def normalize_observe_philology_filters(raw_filters: Any) -> Dict[str, str]:
    filters = _as_dict(raw_filters)
    return {
        field_name: _as_text(filters.get(field_name))
        for field_name in _CATALOG_FILTER_FIELDS
        if _as_text(filters.get(field_name))
    }


def filter_observe_philology_assets(
    observe_philology: Any,
    filters: Any = None,
) -> Dict[str, Any]:
    normalized = normalize_observe_philology_assets(observe_philology)
    normalized_filters = normalize_observe_philology_filters(filters)
    if not normalized_filters:
        return normalized

    terminology_rows = [
        row
        for row in _as_dict_list(normalized.get("terminology_standard_table"))
        if _record_matches_catalog_filters(row, normalized_filters)
    ]
    collation_entries = [
        entry
        for entry in _as_dict_list(normalized.get("collation_entries"))
        if _record_matches_catalog_filters(entry, normalized_filters)
    ]
    annotation_report = _as_dict(normalized.get("annotation_report"))
    summary = _as_dict(annotation_report.get("summary"))
    document_reports = [
        report
        for report in _as_dict_list(annotation_report.get("documents"))
        if _record_matches_catalog_filters(report, normalized_filters)
    ]
    catalog_summary = _as_dict(normalized.get("catalog_summary"))
    catalog_documents = [
        document
        for document in _as_dict_list(catalog_summary.get("documents"))
        if _record_matches_catalog_filters(document, normalized_filters)
    ]
    filtered_fragment_candidates = {
        field_name: [
            item
            for item in _as_dict_list(normalized.get(field_name))
            if _record_matches_catalog_filters(item, normalized_filters)
        ]
        for field_name in _FRAGMENT_CANDIDATE_FIELDS
    }
    filtered_catalog_summary: Dict[str, Any] = {}
    if catalog_documents:
        filtered_catalog_summary["documents"] = catalog_documents
    elif _as_dict_list(catalog_summary.get("version_lineages")):
        filtered_lineages = _filter_catalog_lineages(
            _as_dict_list(catalog_summary.get("version_lineages")),
            normalized_filters,
        )
        if filtered_lineages:
            filtered_catalog_summary["version_lineages"] = filtered_lineages

    filtered_summary = dict(summary)
    if filtered_summary or document_reports or terminology_rows or collation_entries or filtered_catalog_summary:
        filtered_summary["processed_document_count"] = max(
            len(document_reports),
            len(catalog_documents),
        )
        filtered_summary["terminology_standard_table_count"] = len(terminology_rows)
        filtered_summary["collation_entry_count"] = len(collation_entries)

    filtered_assets: Dict[str, Any] = {
        "terminology_standard_table": terminology_rows,
        "collation_entries": collation_entries,
        "annotation_report": {
            "summary": filtered_summary,
            "documents": document_reports,
        },
        "catalog_summary": filtered_catalog_summary,
        "catalog_review_decisions": _as_dict_list(normalized.get("catalog_review_decisions")),
        "review_workbench_decisions": _as_dict_list(normalized.get("review_workbench_decisions")),
        "catalog_review_batch_audit_trail": _as_dict_list(normalized.get("catalog_review_batch_audit_trail")),
        "catalog_review_last_batch_summary": _as_dict(normalized.get("catalog_review_last_batch_summary")),
        "review_workbench_batch_audit_trail": _as_dict_list(normalized.get("review_workbench_batch_audit_trail")),
        "review_workbench_last_batch_summary": _as_dict(normalized.get("review_workbench_last_batch_summary")),
    }
    for field_name, items in filtered_fragment_candidates.items():
        filtered_assets[field_name] = items
    # 考据证据链 — pass through (not filtered by catalog dimensions)
    if _as_dict_list(normalized.get("evidence_chains")):
        filtered_assets["evidence_chains"] = _as_dict_list(normalized.get("evidence_chains"))
    if _as_dict_list(normalized.get("conflict_claims")):
        filtered_assets["conflict_claims"] = _as_dict_list(normalized.get("conflict_claims"))
    if _as_text(normalized.get("source")):
        filtered_assets["source"] = normalized["source"]
    if _as_string_list(normalized.get("sources")):
        filtered_assets["sources"] = _as_string_list(normalized.get("sources"))
    return normalize_observe_philology_assets(filtered_assets)


def _format_lineage_option_label(record: Mapping[str, Any]) -> str:
    work_title = _as_text(record.get("work_title")) or "未标注作品"
    fragment_title = _as_text(record.get("fragment_title")) or "未标注章节"
    edition = _as_text(record.get("edition")) or _as_text(record.get("dynasty")) or _as_text(record.get("version_lineage_key"))
    parts = [work_title, fragment_title]
    if edition:
        parts.append(edition)
    return " / ".join(parts)


def _format_witness_option_label(record: Mapping[str, Any]) -> str:
    title = _as_text(record.get("document_title") or record.get("title") or record.get("witness_key"))
    meta = " · ".join(part for part in (_as_text(record.get("edition")), _as_text(record.get("dynasty"))) if part)
    if meta:
        return f"{title} · {meta}"
    return title


def build_observe_philology_filter_contract(
    observe_philology: Any,
    filters: Any = None,
) -> Dict[str, Any]:
    normalized = normalize_observe_philology_assets(observe_philology)
    active_filters = normalize_observe_philology_filters(filters)
    catalog_summary = _as_dict(normalized.get("catalog_summary"))
    catalog_documents = _as_dict_list(catalog_summary.get("documents"))
    terminology_rows = _as_dict_list(normalized.get("terminology_standard_table"))
    collation_entries = _as_dict_list(normalized.get("collation_entries"))

    option_maps: Dict[str, Dict[str, Dict[str, Any]]] = {field_name: {} for field_name in _CATALOG_FILTER_FIELDS}

    def _add_option(field_name: str, value: Any, label: str) -> None:
        normalized_value = _as_text(value)
        if not normalized_value:
            return
        bucket = option_maps[field_name].setdefault(
            normalized_value,
            {
                "value": normalized_value,
                "label": label or normalized_value,
                "count": 0,
            },
        )
        bucket["count"] += 1

    for document in catalog_documents:
        _add_option("document_title", document.get("document_title"), _as_text(document.get("document_title")))
        _add_option("work_title", document.get("work_title"), _as_text(document.get("work_title")))
        _add_option(
            "version_lineage_key",
            document.get("version_lineage_key"),
            _format_lineage_option_label(document),
        )
        _add_option("witness_key", document.get("witness_key"), _format_witness_option_label(document))

    for row in terminology_rows:
        _add_option("document_title", row.get("document_title"), _as_text(row.get("document_title")))
        _add_option("work_title", row.get("work_title"), _as_text(row.get("work_title")))
        _add_option("version_lineage_key", row.get("version_lineage_key"), _format_lineage_option_label(row))
        _add_option("witness_key", row.get("witness_key"), _format_witness_option_label(row))

    for entry in collation_entries:
        _add_option("document_title", entry.get("document_title"), _as_text(entry.get("document_title")))
        _add_option("document_title", entry.get("witness_title"), _as_text(entry.get("witness_title")))
        for field_name in ("work_title", "version_lineage_key", "witness_key"):
            for candidate in _record_filter_candidates(entry, field_name):
                label = candidate
                if field_name == "version_lineage_key":
                    label = _format_lineage_option_label(entry)
                if field_name == "witness_key":
                    label = _format_witness_option_label(entry)
                _add_option(field_name, candidate, label)

    for field_name in _FRAGMENT_CANDIDATE_FIELDS:
        for entry in _as_dict_list(normalized.get(field_name)):
            for candidate in _record_filter_candidates(entry, "document_title"):
                _add_option("document_title", candidate, candidate)
            for candidate in _record_filter_candidates(entry, "work_title"):
                _add_option("work_title", candidate, candidate)
            for candidate in _record_filter_candidates(entry, "version_lineage_key"):
                _add_option("version_lineage_key", candidate, candidate)
            for candidate in _record_filter_candidates(entry, "witness_key"):
                _add_option("witness_key", candidate, candidate)

    return {
        "active_filters": active_filters,
        "options": {
            field_name: sorted(
                option_maps[field_name].values(),
                key=lambda item: (str(item.get("label") or ""), str(item.get("value") or "")),
            )
            for field_name in _CATALOG_FILTER_FIELDS
            if option_maps[field_name]
        },
    }


def _merge_philology_candidates(
    candidates: Sequence[tuple[str, Mapping[str, Any]]],
    *,
    include_sources: bool,
) -> Dict[str, Any]:
    resolved_payload: Dict[str, Any] = {}
    sources: List[str] = []
    for source_name, candidate in candidates:
        if not candidate.get("available"):
            continue
        sources.append(source_name)
        for field_name in (
            "terminology_standard_table",
            "collation_entries",
            "annotation_report",
            "catalog_summary",
            "catalog_review_decisions",
            "catalog_review_batch_audit_trail",
            "catalog_review_last_batch_summary",
            "review_workbench_decisions",
            "review_workbench_batch_audit_trail",
            "review_workbench_last_batch_summary",
            "evidence_chains",
            "conflict_claims",
            *_FRAGMENT_CANDIDATE_FIELDS,
        ):
            if not resolved_payload.get(field_name) and candidate.get(field_name):
                resolved_payload[field_name] = candidate[field_name]

    normalized = normalize_observe_philology_assets(resolved_payload)
    if include_sources:
        if sources:
            normalized["source"] = sources[0]
            normalized["sources"] = sources
        else:
            normalized["source"] = "unavailable"
            normalized["sources"] = []
    return normalized


def _unique_document_identifiers(*groups: Sequence[Mapping[str, Any]]) -> List[str]:
    identifiers: List[str] = []
    for group in groups:
        for item in group:
            if not isinstance(item, Mapping):
                continue
            for key in ("document_urn", "document_title", "urn", "title"):
                value = str(item.get(key) or "").strip()
                if value:
                    if value not in identifiers:
                        identifiers.append(value)
                    break
    return identifiers


def _build_workbench_asset_key(asset_type: str, *parts: tuple[str, Any]) -> str:
    normalized_parts = [
        f"{name}={_as_text(value)}"
        for name, value in parts
        if _as_text(value)
    ]
    return f"{asset_type}::{'|'.join(normalized_parts) if normalized_parts else 'unkeyed'}"


_WORKBENCH_REVIEW_MERGE_FIELDS = (
    "review_status",
    "needs_manual_review",
    "review_reasons",
    "review_source",
    "reviewer",
    "reviewed_at",
    "decision_basis",
)


def _apply_workbench_review_to_item(
    item: Dict[str, Any],
    decision: Dict[str, Any],
) -> Dict[str, Any]:
    updated = dict(item)
    status = _as_text(decision.get("review_status"))
    if status:
        updated["review_status"] = status
    needs = decision.get("needs_manual_review")
    if needs is not None:
        updated["needs_manual_review"] = bool(needs)
    reasons = decision.get("review_reasons")
    if isinstance(reasons, list) and reasons:
        updated["review_reasons"] = reasons
    for field_name in ("review_source", "reviewer", "reviewed_at", "decision_basis"):
        value = _as_text(decision.get(field_name))
        if value:
            updated[field_name] = value
    return updated


def _apply_workbench_review_decisions(
    terminology_rows: List[Dict[str, Any]],
    collation_entries: List[Dict[str, Any]],
    fragment_candidate_payloads: Dict[str, List[Dict[str, Any]]],
    evidence_chains: List[Dict[str, Any]],
    review_workbench_decisions: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    if not review_workbench_decisions:
        return terminology_rows, collation_entries, fragment_candidate_payloads, evidence_chains

    lookup: Dict[tuple[str, str], Dict[str, Any]] = {}
    for decision in review_workbench_decisions:
        asset_type = _as_text(decision.get("asset_type")).lower()
        asset_key = _as_text(decision.get("asset_key"))
        if asset_type and asset_key:
            lookup[(asset_type, asset_key)] = decision

    if not lookup:
        return terminology_rows, collation_entries, fragment_candidate_payloads, evidence_chains

    updated_rows: List[Dict[str, Any]] = []
    for row in terminology_rows:
        key = _build_workbench_asset_key(
            "terminology_row",
            ("document_urn", row.get("document_urn")),
            ("document_title", row.get("document_title")),
            ("version_lineage_key", row.get("version_lineage_key")),
            ("witness_key", row.get("witness_key")),
            ("canonical", row.get("canonical")),
            ("label", row.get("label")),
        )
        decision = lookup.get(("terminology_row", key))
        updated_rows.append(_apply_workbench_review_to_item(row, decision) if decision else row)

    updated_collation: List[Dict[str, Any]] = []
    for entry in collation_entries:
        key = _build_workbench_asset_key(
            "collation_entry",
            ("document_urn", entry.get("document_urn")),
            ("witness_urn", entry.get("witness_urn")),
            ("version_lineage_key", entry.get("version_lineage_key")),
            ("witness_key", entry.get("witness_key")),
            ("difference_type", entry.get("difference_type")),
            ("base_text", entry.get("base_text")),
            ("witness_text", entry.get("witness_text")),
        )
        decision = lookup.get(("collation_entry", key))
        updated_collation.append(_apply_workbench_review_to_item(entry, decision) if decision else entry)

    updated_fragments: Dict[str, List[Dict[str, Any]]] = {}
    for field_name, items in fragment_candidate_payloads.items():
        updated_items: List[Dict[str, Any]] = []
        for entry in items:
            key = _build_workbench_asset_key(
                "fragment_candidate",
                ("candidate_kind", field_name),
                ("fragment_candidate_id", entry.get("fragment_candidate_id") or entry.get("candidate_id") or entry.get("id")),
                ("document_urn", entry.get("document_urn")),
                ("version_lineage_key", entry.get("version_lineage_key")),
                ("witness_key", entry.get("witness_key")),
                ("fragment_title", entry.get("fragment_title") or entry.get("title")),
            )
            decision = lookup.get(("fragment_candidate", key))
            updated_items.append(_apply_workbench_review_to_item(entry, decision) if decision else entry)
        updated_fragments[field_name] = updated_items

    updated_chains: List[Dict[str, Any]] = []
    for chain in evidence_chains:
        chain_id = _as_text(chain.get("evidence_chain_id") or chain.get("id"))
        claim_type = _as_text(chain.get("claim_type"))
        claim_statement = _as_text(chain.get("claim_statement"))
        key = _build_workbench_asset_key(
            "evidence_chain",
            ("evidence_chain_id", chain_id),
            ("claim_type", claim_type),
            ("claim_statement", claim_statement[:80] if claim_statement else ""),
        )
        decision = lookup.get(("evidence_chain", key))
        updated_chains.append(_apply_workbench_review_to_item(chain, decision) if decision else chain)

    return updated_rows, updated_collation, updated_fragments, updated_chains


def normalize_observe_philology_assets(raw_assets: Any) -> Dict[str, Any]:
    assets = _as_dict(raw_assets)
    source = _as_text(assets.get("source"))
    sources = _as_string_list(assets.get("sources"))
    catalog_review_payload = _as_dict(assets.get("catalog_review_decisions"))
    review_workbench_payload = _as_dict(assets.get("review_workbench_decisions"))
    catalog_review_decisions = _normalize_catalog_review_decisions(assets.get("catalog_review_decisions"))
    review_workbench_decisions = normalize_observe_review_workbench_decisions(assets.get("review_workbench_decisions"))
    catalog_review_batch_audit_trail = _as_dict_list(
        assets.get("catalog_review_batch_audit_trail") or catalog_review_payload.get("batch_audit_trail")
    )
    catalog_review_last_batch_summary = _as_dict(
        assets.get("catalog_review_last_batch_summary") or catalog_review_payload.get("last_batch_summary")
    )
    review_workbench_batch_audit_trail = _as_dict_list(
        assets.get("review_workbench_batch_audit_trail") or review_workbench_payload.get("batch_audit_trail")
    )
    review_workbench_last_batch_summary = _as_dict(
        assets.get("review_workbench_last_batch_summary") or review_workbench_payload.get("last_batch_summary")
    )
    terminology_rows = _as_dict_list(assets.get("terminology_standard_table"))
    collation_entries = _as_dict_list(assets.get("collation_entries"))
    fragment_candidate_payloads = {
        field_name: _as_dict_list(assets.get(field_name))
        for field_name in _FRAGMENT_CANDIDATE_FIELDS
    }
    annotation_report = _as_dict(assets.get("annotation_report"))
    catalog_summary = _normalize_catalog_summary(assets.get("catalog_summary"))
    summary = _as_dict(annotation_report.get("summary"))
    document_reports = _as_dict_list(annotation_report.get("documents"))

    catalog_documents = _as_dict_list(catalog_summary.get("documents"))
    terminology_rows = _enrich_terminology_rows_with_catalog_metadata(terminology_rows, catalog_documents)
    collation_entries = _enrich_collation_entries_with_catalog_metadata(collation_entries, catalog_documents)
    fragment_candidate_payloads = {
        field_name: _enrich_fragment_candidates_with_catalog_metadata(items, catalog_documents)
        for field_name, items in fragment_candidate_payloads.items()
    }
    document_reports = _enrich_document_reports_with_catalog_metadata(document_reports, catalog_documents)
    catalog_summary = _enrich_catalog_summary(catalog_summary, terminology_rows, collation_entries)
    catalog_summary = _apply_catalog_review_decisions(catalog_summary, catalog_review_decisions)
    evidence_chains = _as_dict_list(assets.get("evidence_chains"))
    terminology_rows, collation_entries, fragment_candidate_payloads, evidence_chains = _apply_workbench_review_decisions(
        terminology_rows, collation_entries, fragment_candidate_payloads, evidence_chains, review_workbench_decisions,
    )
    catalog_metrics = _as_dict(catalog_summary.get("summary"))

    document_identifiers = _unique_document_identifiers(terminology_rows, collation_entries, document_reports)
    document_count = _safe_int(summary.get("processed_document_count") or summary.get("document_count"), 0)
    if document_count <= 0:
        document_count = len(document_identifiers)
    if document_count <= 0:
        document_count = _safe_int(catalog_metrics.get("catalog_document_count"), 0)

    philology_notes = _as_string_list(summary.get("philology_notes"))
    should_materialize_summary = bool(summary or terminology_rows or collation_entries or document_reports)
    if philology_notes or should_materialize_summary:
        summary["philology_notes"] = philology_notes
    if should_materialize_summary:
        summary.setdefault("processed_document_count", document_count)
        summary.setdefault("terminology_standard_table_count", len(terminology_rows))
        summary.setdefault("collation_entry_count", len(collation_entries))

    normalized_report = dict(annotation_report)
    if should_materialize_summary or "summary" in annotation_report:
        normalized_report["summary"] = summary
    if document_reports or "documents" in annotation_report:
        normalized_report["documents"] = document_reports

    asset_count = sum(
        1
        for payload in (
            terminology_rows,
            collation_entries,
            normalized_report,
            catalog_summary,
            catalog_review_decisions,
            review_workbench_decisions,
            evidence_chains,
            *fragment_candidate_payloads.values(),
        )
        if payload not in ({}, [], None, "")
    )
    available = bool(asset_count)

    normalized_assets = {
        "available": available,
        "asset_count": asset_count,
        "document_count": document_count,
        "terminology_standard_table": terminology_rows,
        "terminology_standard_table_count": len(terminology_rows),
        "collation_entries": collation_entries,
        "collation_entry_count": len(collation_entries),
        "annotation_report": normalized_report,
        "catalog_summary": catalog_summary,
        "catalog_review_decisions": catalog_review_decisions,
        "catalog_review_batch_audit_trail": catalog_review_batch_audit_trail,
        "catalog_review_last_batch_summary": catalog_review_last_batch_summary,
        "catalog_review_batch_operation_count": len(catalog_review_batch_audit_trail),
        "review_workbench_decisions": review_workbench_decisions,
        "review_workbench_batch_audit_trail": review_workbench_batch_audit_trail,
        "review_workbench_last_batch_summary": review_workbench_last_batch_summary,
        "review_workbench_batch_operation_count": len(review_workbench_batch_audit_trail),
        "catalog_document_count": _safe_int(catalog_metrics.get("catalog_document_count"), len(_as_dict_list(catalog_summary.get("documents")))),
        "version_lineage_count": _safe_int(catalog_metrics.get("version_lineage_count"), len(_as_dict_list(catalog_summary.get("version_lineages")))),
        "witness_count": _safe_int(catalog_metrics.get("witness_count"), 0),
        "missing_catalog_metadata_count": _safe_int(catalog_metrics.get("missing_core_metadata_count"), 0),
        "philology_note_count": len(philology_notes),
        "source": source or "",
        "sources": sources,
    }
    normalized_assets["fragment_candidate_count"] = sum(len(items) for items in fragment_candidate_payloads.values())
    for field_name, items in fragment_candidate_payloads.items():
        normalized_assets[field_name] = items

    # 考据证据链
    conflict_claims = _as_dict_list(assets.get("conflict_claims"))
    normalized_assets["evidence_chains"] = evidence_chains
    normalized_assets["conflict_claims"] = conflict_claims
    normalized_assets["evidence_chain_count"] = _safe_int(assets.get("evidence_chain_count"), len(evidence_chains))
    normalized_assets["conflict_count"] = _safe_int(assets.get("conflict_count"), len(conflict_claims))

    # 辑佚摘要 — 注入到 catalog_summary.summary 供 dashboard 消费
    all_fragment_items = [item for items in fragment_candidate_payloads.values() for item in items]
    if all_fragment_items:
        frag_summary = build_fragment_summary(
            fragment_candidate_payloads.get("fragment_candidates", []),
            fragment_candidate_payloads.get("lost_text_candidates", []),
            fragment_candidate_payloads.get("citation_source_candidates", []),
        )
        catalog_metrics["fragment_candidate_count"] = frag_summary["fragment_candidate_count"]
        catalog_metrics["lost_text_candidate_count"] = frag_summary["lost_text_candidate_count"]
        catalog_metrics["citation_source_candidate_count"] = frag_summary["citation_source_candidate_count"]
        catalog_metrics["fragment_total_count"] = frag_summary["total"]
        catalog_metrics["fragment_needs_review_count"] = frag_summary["needs_review_count"]
        catalog_metrics["fragment_high_confidence_count"] = frag_summary["high_confidence_count"]
        catalog_metrics["fragment_avg_score"] = frag_summary["avg_score"]
        catalog_metrics["fragment_kind_distribution"] = frag_summary["kind_distribution"]
        catalog_metrics["fragment_review_status_distribution"] = frag_summary["review_status_distribution"]
        # 确保 catalog_summary 包含更新后的 metrics
        if not catalog_summary:
            catalog_summary = {"summary": catalog_metrics, "documents": [], "version_lineages": []}
            normalized_assets["catalog_summary"] = catalog_summary
        elif "summary" not in catalog_summary:
            catalog_summary["summary"] = catalog_metrics

    # 考据证据链摘要 — 注入到 catalog_summary.summary 供 dashboard 消费
    if evidence_chains:
        ec_summary = build_evidence_chain_summary(evidence_chains)
        catalog_metrics["evidence_chain_count"] = ec_summary["total"]
        catalog_metrics["evidence_conflict_count"] = ec_summary["conflict_count"]
        catalog_metrics["evidence_needs_review_count"] = ec_summary["needs_review_count"]
        catalog_metrics["evidence_claim_type_distribution"] = ec_summary["claim_type_distribution"]
        catalog_metrics["evidence_judgment_distribution"] = ec_summary["judgment_type_distribution"]
        catalog_metrics["evidence_confidence_avg"] = ec_summary.get("avg_confidence", 0.0)
        catalog_metrics["evidence_confidence_min"] = 0.0
        catalog_metrics["evidence_confidence_max"] = 0.0
        if not catalog_summary:
            catalog_summary = {"summary": catalog_metrics, "documents": [], "version_lineages": []}
            normalized_assets["catalog_summary"] = catalog_summary
        else:
            catalog_summary["summary"] = catalog_metrics

    return normalized_assets


def build_observe_philology_artifact_payloads(
    philology_assets: Any,
    artifact_output: Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    config = dict(artifact_output or {})
    if config.get("enabled", True) is False:
        return []

    assets = normalize_observe_philology_assets(philology_assets)
    if not assets["available"]:
        return []

    terminology_rows = assets["terminology_standard_table"]
    collation_entries = assets["collation_entries"]
    annotation_report = assets["annotation_report"]
    artifacts: List[Dict[str, Any]] = []

    if config.get("include_terminology_standard_table", True) and terminology_rows:
        artifacts.append(
            {
                "name": OBSERVE_PHILOLOGY_TERMINOLOGY_TABLE_ARTIFACT,
                "artifact_type": "dataset",
                "mime_type": "application/json",
                "description": "Observe 阶段文献学术语标准表",
                "content": {
                    "asset_kind": "terminology_standard_table",
                    "row_count": len(terminology_rows),
                    "columns": list(_TERMINOLOGY_COLUMNS),
                    "rows": terminology_rows,
                },
                "metadata": {
                    "asset_kind": "terminology_standard_table",
                    "row_count": len(terminology_rows),
                    "phase": "observe",
                },
            }
        )
    if config.get("include_collation_entries", True) and collation_entries:
        artifacts.append(
            {
                "name": OBSERVE_PHILOLOGY_COLLATION_ENTRIES_ARTIFACT,
                "artifact_type": "analysis",
                "mime_type": "application/json",
                "description": "Observe 阶段文献学校勘条目",
                "content": {
                    "asset_kind": "collation_entries",
                    "entry_count": len(collation_entries),
                    "entries": collation_entries,
                },
                "metadata": {
                    "asset_kind": "collation_entries",
                    "entry_count": len(collation_entries),
                    "phase": "observe",
                },
            }
        )
    if config.get("include_annotation_report", True) and annotation_report:
        artifacts.append(
            {
                "name": OBSERVE_PHILOLOGY_ANNOTATION_REPORT_ARTIFACT,
                "artifact_type": "report",
                "mime_type": "application/json",
                "description": "Observe 阶段文献学汇总报告",
                "content": annotation_report,
                "metadata": {
                    "asset_kind": "annotation_report",
                    "document_count": assets["document_count"],
                    "phase": "observe",
                },
            }
        )
    if config.get("include_catalog_summary", True) and assets.get("catalog_summary"):
        artifacts.append(
            {
                "name": OBSERVE_PHILOLOGY_CATALOG_SUMMARY_ARTIFACT,
                "artifact_type": "dataset",
                "mime_type": "application/json",
                "description": "Observe 阶段目录学目录基线摘要",
                "content": assets["catalog_summary"],
                "metadata": {
                    "asset_kind": "catalog_summary",
                    "catalog_document_count": assets["catalog_document_count"],
                    "version_lineage_count": assets["version_lineage_count"],
                    "phase": "observe",
                },
            }
        )

    # 辑佚候选项报告
    fragment_candidates = assets.get("fragment_candidates") or []
    lost_text_candidates = assets.get("lost_text_candidates") or []
    citation_source_candidates = assets.get("citation_source_candidates") or []
    all_fragment_items = [*fragment_candidates, *lost_text_candidates, *citation_source_candidates]
    if config.get("include_fragment_reconstruction", True) and all_fragment_items:
        fragment_summary = build_fragment_summary(
            fragment_candidates, lost_text_candidates, citation_source_candidates,
        )
        artifacts.append(
            {
                "name": OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT,
                "artifact_type": "analysis",
                "mime_type": "application/json",
                "description": "Observe 阶段辑佚候选项报告",
                "content": {
                    "asset_kind": "fragment_reconstruction",
                    "summary": fragment_summary,
                    "fragment_candidates": fragment_candidates,
                    "lost_text_candidates": lost_text_candidates,
                    "citation_source_candidates": citation_source_candidates,
                },
                "metadata": {
                    "asset_kind": "fragment_reconstruction",
                    "fragment_candidate_count": len(fragment_candidates),
                    "lost_text_candidate_count": len(lost_text_candidates),
                    "citation_source_candidate_count": len(citation_source_candidates),
                    "phase": "observe",
                },
            }
        )

    # 考据证据链报告
    evidence_chains = assets.get("evidence_chains") or []
    conflict_claims = assets.get("conflict_claims") or []
    if config.get("include_evidence_chain", True) and evidence_chains:
        ec_summary = build_evidence_chain_summary(evidence_chains)
        artifacts.append(
            {
                "name": OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT,
                "artifact_type": "analysis",
                "mime_type": "application/json",
                "description": "Observe 阶段考据证据链报告",
                "content": {
                    "asset_kind": "evidence_chain",
                    "summary": ec_summary,
                    "evidence_chains": evidence_chains,
                    "conflict_claims": conflict_claims,
                },
                "metadata": {
                    "asset_kind": "evidence_chain",
                    "evidence_chain_count": len(evidence_chains),
                    "conflict_count": len(conflict_claims),
                    "phase": "observe",
                },
            }
        )

    return artifacts


def _resolve_artifact_kind(artifact: Mapping[str, Any]) -> str:
    metadata = _as_dict(artifact.get("metadata"))
    content = _as_dict(artifact.get("content"))
    explicit_kind = str(metadata.get("asset_kind") or content.get("asset_kind") or "").strip()
    if explicit_kind:
        return explicit_kind

    name = str(artifact.get("name") or "").strip()
    if name == OBSERVE_PHILOLOGY_TERMINOLOGY_TABLE_ARTIFACT:
        return "terminology_standard_table"
    if name == OBSERVE_PHILOLOGY_COLLATION_ENTRIES_ARTIFACT:
        return "collation_entries"
    if name == OBSERVE_PHILOLOGY_ANNOTATION_REPORT_ARTIFACT:
        return "annotation_report"
    if name == OBSERVE_PHILOLOGY_CATALOG_SUMMARY_ARTIFACT:
        return "catalog_summary"
    if name == OBSERVE_PHILOLOGY_CATALOG_REVIEW_ARTIFACT:
        return _CATALOG_REVIEW_ASSET_KIND
    if name == OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT:
        return "fragment_reconstruction"
    if name == OBSERVE_PHILOLOGY_EVIDENCE_CHAIN_ARTIFACT:
        return "evidence_chain"
    if name == OBSERVE_PHILOLOGY_WORKBENCH_REVIEW_ARTIFACT:
        return REVIEW_WORKBENCH_ASSET_KIND
    return ""


def extract_observe_philology_assets_from_artifacts(artifacts: Sequence[Mapping[str, Any]] | None) -> Dict[str, Any]:
    collected: Dict[str, Any] = {}
    for artifact in artifacts or []:
        if not isinstance(artifact, Mapping):
            continue
        asset_kind = _resolve_artifact_kind(artifact)
        content = _as_dict(artifact.get("content"))
        if asset_kind == "terminology_standard_table":
            rows = _as_dict_list(content.get("rows") or content.get("terminology_standard_table"))
            if rows:
                collected["terminology_standard_table"] = rows
        elif asset_kind == "collation_entries":
            entries = _as_dict_list(content.get("entries") or content.get("collation_entries"))
            if entries:
                collected["collation_entries"] = entries
        elif asset_kind == "annotation_report" and content:
            collected["annotation_report"] = content
        elif asset_kind == "catalog_summary" and content:
            collected["catalog_summary"] = content
        elif asset_kind == _CATALOG_REVIEW_ASSET_KIND and content:
            collected["catalog_review_decisions"] = content
            batch_audit_trail = _as_dict_list(content.get("batch_audit_trail"))
            if batch_audit_trail:
                collected["catalog_review_batch_audit_trail"] = batch_audit_trail
            last_batch_summary = _as_dict(content.get("last_batch_summary"))
            if last_batch_summary:
                collected["catalog_review_last_batch_summary"] = last_batch_summary
        elif asset_kind == "fragment_reconstruction" and content:
            for fk in CANDIDATE_KINDS:
                items = _as_dict_list(content.get(fk))
                if items:
                    collected[fk] = items
        elif asset_kind == "evidence_chain" and content:
            chains = _as_dict_list(content.get("evidence_chains"))
            if chains:
                collected["evidence_chains"] = chains
            conflicts = _as_dict_list(content.get("conflict_claims"))
            if conflicts:
                collected["conflict_claims"] = conflicts
        elif asset_kind == REVIEW_WORKBENCH_ASSET_KIND and content:
            collected["review_workbench_decisions"] = content
            batch_audit_trail = _as_dict_list(content.get("batch_audit_trail"))
            if batch_audit_trail:
                collected["review_workbench_batch_audit_trail"] = batch_audit_trail
            last_batch_summary = _as_dict(content.get("last_batch_summary"))
            if last_batch_summary:
                collected["review_workbench_last_batch_summary"] = last_batch_summary
    return normalize_observe_philology_assets(collected)


def _merge_terminology_rows(rows: Sequence[Mapping[str, Any]], document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    merged_rows: List[Dict[str, Any]] = []
    document_title = str(document.get("title") or document.get("document_title") or "").strip()
    document_urn = str(document.get("urn") or document.get("document_urn") or "").strip()
    source_type = str(document.get("source_type") or "").strip()
    for row in rows:
        merged_rows.append(
            {
                **dict(row),
                "document_title": str(row.get("document_title") or document_title).strip(),
                "document_urn": str(row.get("document_urn") or document_urn).strip(),
                "source_type": str(row.get("source_type") or source_type).strip(),
            }
        )
    return merged_rows


def _merge_collation_entries(entries: Sequence[Mapping[str, Any]], document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    merged_entries: List[Dict[str, Any]] = []
    document_title = str(document.get("title") or document.get("document_title") or "").strip()
    document_urn = str(document.get("urn") or document.get("document_urn") or "").strip()
    source_type = str(document.get("source_type") or "").strip()
    for entry in entries:
        merged_entries.append(
            {
                **dict(entry),
                "document_title": str(entry.get("document_title") or document_title).strip(),
                "document_urn": str(entry.get("document_urn") or document_urn).strip(),
                "source_type": str(entry.get("source_type") or source_type).strip(),
            }
        )
    return merged_entries


def _merge_fragment_candidates(entries: Sequence[Mapping[str, Any]], document: Mapping[str, Any]) -> List[Dict[str, Any]]:
    merged_entries: List[Dict[str, Any]] = []
    document_title = str(document.get("title") or document.get("document_title") or "").strip()
    document_urn = str(document.get("urn") or document.get("document_urn") or "").strip()
    source_type = str(document.get("source_type") or "").strip()
    for entry in entries:
        merged_entries.append(
            {
                **dict(entry),
                "document_title": str(entry.get("document_title") or document_title).strip(),
                "document_urn": str(entry.get("document_urn") or document_urn).strip(),
                "source_type": str(entry.get("source_type") or source_type).strip(),
            }
        )
    return merged_entries


def extract_observe_philology_assets_from_documents(
    observe_documents: Sequence[Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    documents = [dict(item) for item in (observe_documents or []) if isinstance(item, Mapping)]
    if not documents:
        return normalize_observe_philology_assets({})

    catalog_summary = _build_catalog_summary_from_documents(documents)

    terminology_rows: List[Dict[str, Any]] = []
    collation_entries: List[Dict[str, Any]] = []
    fragment_candidate_payloads: Dict[str, List[Dict[str, Any]]] = {
        field_name: []
        for field_name in _FRAGMENT_CANDIDATE_FIELDS
    }
    row_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    entry_keys: set[tuple[str, str, str, str, str]] = set()
    fragment_candidate_keys: set[tuple[str, str]] = set()
    philology_document_count = 0
    term_mapping_count = 0
    orthographic_variant_count = 0
    recognized_term_count = 0
    version_collation_difference_count = 0
    version_collation_witness_count = 0
    philology_notes: List[str] = []
    document_reports: List[Dict[str, Any]] = []

    for document in documents:
        philology_assets = _as_dict(document.get("philology_assets"))
        philology = _as_dict(document.get("philology"))
        term_standardization = _as_dict(philology.get("term_standardization"))
        version_collation = _as_dict(philology.get("version_collation"))
        fragment_reconstruction = _as_dict(philology.get("fragment_reconstruction"))
        document_notes = _as_string_list(document.get("philology_notes"))
        has_payload = bool(philology_assets or philology or document_notes)
        if has_payload:
            philology_document_count += 1
        else:
            continue

        term_mapping_count += _safe_int(term_standardization.get("mapping_count"), 0)
        orthographic_variant_count += _safe_int(term_standardization.get("orthographic_variant_count"), 0)
        recognized_term_count += _safe_int(term_standardization.get("recognized_term_count"), 0)
        version_collation_difference_count += _safe_int(version_collation.get("difference_count"), 0)
        if _safe_int(version_collation.get("witness_count"), 0) > 0:
            version_collation_witness_count += 1

        for note in document_notes:
            if note not in philology_notes:
                philology_notes.append(note)

        for row in _merge_terminology_rows(_as_dict_list(philology_assets.get("terminology_standard_table")), document):
            observed_forms = tuple(sorted(_as_string_list(row.get("observed_forms"))))
            row_key = (
                str(row.get("document_urn") or row.get("document_title") or "").strip(),
                str(row.get("canonical") or "").strip(),
                observed_forms,
            )
            if row_key in row_keys:
                continue
            row_keys.add(row_key)
            terminology_rows.append(row)

        for entry in _merge_collation_entries(_as_dict_list(philology_assets.get("collation_entries")), document):
            entry_key = (
                str(entry.get("document_urn") or entry.get("document_title") or "").strip(),
                str(entry.get("witness_urn") or entry.get("witness_title") or "").strip(),
                str(entry.get("difference_type") or "").strip(),
                str(entry.get("base_text") or "").strip(),
                str(entry.get("witness_text") or "").strip(),
            )
            if entry_key in entry_keys:
                continue
            entry_keys.add(entry_key)
            collation_entries.append(entry)

        for field_name in _FRAGMENT_CANDIDATE_FIELDS:
            merged_entries = _merge_fragment_candidates(_as_dict_list(philology_assets.get(field_name)), document)
            for entry in merged_entries:
                candidate_id = str(
                    entry.get("fragment_candidate_id")
                    or entry.get("candidate_id")
                    or entry.get("id")
                    or ""
                ).strip()
                identity = (field_name, candidate_id or str(entry))
                if identity in fragment_candidate_keys:
                    continue
                fragment_candidate_keys.add(identity)
                fragment_candidate_payloads[field_name].append(entry)

        document_reports.append(
            {
                "document_title": str(document.get("title") or document.get("document_title") or "").strip(),
                "document_urn": str(document.get("urn") or document.get("document_urn") or "").strip(),
                "source_type": str(document.get("source_type") or "").strip(),
                "mapping_count": _safe_int(term_standardization.get("mapping_count"), 0),
                "recognized_term_count": _safe_int(term_standardization.get("recognized_term_count"), 0),
                "terminology_standard_table_count": _safe_int(
                    term_standardization.get("terminology_standard_table_count"),
                    len(_as_dict_list(philology_assets.get("terminology_standard_table"))),
                ),
                "difference_count": _safe_int(version_collation.get("difference_count"), 0),
                "collation_entry_count": _safe_int(
                    version_collation.get("collation_entry_count"),
                    len(_as_dict_list(philology_assets.get("collation_entries"))),
                ),
                "witness_count": _safe_int(version_collation.get("witness_count"), 0),
                "fragment_candidate_count": _safe_int(
                    fragment_reconstruction.get("fragment_candidate_count"),
                    len(_as_dict_list(philology_assets.get("fragment_candidates"))),
                ),
                "lost_text_candidate_count": _safe_int(
                    fragment_reconstruction.get("lost_text_candidate_count"),
                    len(_as_dict_list(philology_assets.get("lost_text_candidates"))),
                ),
                "citation_source_candidate_count": _safe_int(
                    fragment_reconstruction.get("citation_source_candidate_count"),
                    len(_as_dict_list(philology_assets.get("citation_source_candidates"))),
                ),
                "philology_notes": document_notes,
            }
        )

    if (
        not terminology_rows
        and not collation_entries
        and not any(fragment_candidate_payloads.values())
        and not document_reports
        and not catalog_summary
    ):
        return normalize_observe_philology_assets({})

    return normalize_observe_philology_assets(
        {
            "terminology_standard_table": terminology_rows,
            "collation_entries": collation_entries,
            **fragment_candidate_payloads,
            "catalog_summary": catalog_summary,
            "annotation_report": {
                "summary": {
                    "processed_document_count": len(document_reports),
                    "philology_document_count": philology_document_count,
                    "term_mapping_count": term_mapping_count,
                    "orthographic_variant_count": orthographic_variant_count,
                    "recognized_term_count": recognized_term_count,
                    "terminology_standard_table_count": len(terminology_rows),
                    "version_collation_difference_count": version_collation_difference_count,
                    "version_collation_witness_count": version_collation_witness_count,
                    "collation_entry_count": len(collation_entries),
                    "fragment_candidate_count": len(fragment_candidate_payloads["fragment_candidates"]),
                    "lost_text_candidate_count": len(fragment_candidate_payloads["lost_text_candidates"]),
                    "citation_source_candidate_count": len(fragment_candidate_payloads["citation_source_candidates"]),
                    "philology_notes": philology_notes,
                },
                "documents": document_reports,
            },
        }
    )


def extract_observe_philology_assets_from_phase_result(observe_phase_result: Mapping[str, Any] | None) -> Dict[str, Any]:
    phase_result = _as_dict(observe_phase_result)
    phase_artifacts = extract_observe_philology_assets_from_artifacts(_as_dict_list(phase_result.get("artifacts")))
    results = _as_dict(phase_result.get("results"))
    ingestion_pipeline = _as_dict(results.get("ingestion_pipeline") or phase_result.get("ingestion_pipeline"))
    aggregate = _as_dict(ingestion_pipeline.get("aggregate"))
    assets = normalize_observe_philology_assets(aggregate.get("philology_assets"))
    document_assets = extract_observe_philology_assets_from_documents(
        _as_dict_list(ingestion_pipeline.get("documents")),
    )
    return _merge_philology_candidates(
        [
            ("artifacts", phase_artifacts),
            ("aggregate", assets),
            ("documents", document_assets),
        ],
        include_sources=False,
    )


def resolve_observe_philology_assets(
    *,
    observe_philology: Any = None,
    artifacts: Sequence[Mapping[str, Any]] | None = None,
    observe_phase_result: Mapping[str, Any] | None = None,
    observe_documents: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    source_candidates = [
        ("observe_philology", normalize_observe_philology_assets(observe_philology)),
        ("artifacts", extract_observe_philology_assets_from_artifacts(artifacts)),
        ("phase_output", extract_observe_philology_assets_from_phase_result(observe_phase_result)),
        ("observe_documents", extract_observe_philology_assets_from_documents(observe_documents)),
    ]
    return _merge_philology_candidates(source_candidates, include_sources=True)