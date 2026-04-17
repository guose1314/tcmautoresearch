from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional


def build_evidence_protocol(
    reasoning_payload: Any,
    *,
    evidence_records: Optional[Iterable[Any]] = None,
    evidence_grade: Optional[Mapping[str, Any]] = None,
    evidence_summary: Optional[Mapping[str, Any]] = None,
    max_evidence_records: Optional[int] = None,
    max_claims: Optional[int] = None,
) -> Dict[str, Any]:
    reasoning = _as_dict(reasoning_payload)
    nested_reasoning = _as_dict(reasoning.get("reasoning_results"))

    raw_evidence_records = list(evidence_records) if evidence_records is not None else _as_list(
        reasoning.get("evidence_records") or nested_reasoning.get("evidence_records")
    )
    raw_claims = _as_list(reasoning.get("entity_relationships") or nested_reasoning.get("entity_relationships"))
    raw_evidence_summary = _as_dict(evidence_summary)
    if not raw_evidence_summary:
        raw_evidence_summary = _as_dict(reasoning.get("evidence_summary") or nested_reasoning.get("evidence_summary"))

    evidence_grade_summary = normalize_evidence_grade_summary(
        evidence_grade
        or _as_dict(reasoning.get("evidence_grade"))
        or _as_dict(nested_reasoning.get("evidence_grade"))
    )
    default_evidence_grade = _as_text(evidence_grade_summary.get("overall_grade"))

    normalized_records = [
        normalize_evidence_record(record, default_evidence_grade=default_evidence_grade)
        for record in raw_evidence_records
        if isinstance(record, Mapping)
    ]
    normalized_claims = [
        normalize_claim_record(claim)
        for claim in raw_claims
        if isinstance(claim, Mapping)
    ]

    if max_evidence_records is not None:
        normalized_records = normalized_records[: max(0, int(max_evidence_records))]
    if max_claims is not None:
        normalized_claims = normalized_claims[: max(0, int(max_claims))]

    citation_records = build_citation_records_from_evidence_records(normalized_records)
    research_grade = _build_research_grade_protocol(reasoning, nested_reasoning)

    if not any(
        (
            normalized_records,
            normalized_claims,
            raw_evidence_summary,
            evidence_grade_summary,
            citation_records,
            research_grade,
        )
    ):
        return {}

    return {
        "contract_version": "evidence-claim-v2",
        "evidence_records": normalized_records,
        "claims": normalized_claims,
        "evidence_summary": raw_evidence_summary,
        "evidence_grade_summary": evidence_grade_summary,
        "citation_records": citation_records,
        "citation_count": len(citation_records),
        "research_grade": research_grade,
        "summary": _build_protocol_summary(normalized_records, normalized_claims, citation_records),
        "contract": {
            "required_fields": [
                "evidence_id",
                "source_type",
                "source_ref",
                "excerpt",
                "evidence_grade",
                "provenance",
            ],
            "claim_fields": [
                "claim_id",
                "source_entity",
                "target_entity",
                "relation_type",
                "confidence",
                "support_count",
                "evidence_ids",
            ],
            "citation_fields": [
                "title",
                "authors",
                "year",
                "source_type",
                "source_ref",
            ],
        },
    }


def normalize_evidence_record(
    record: Mapping[str, Any],
    *,
    default_evidence_grade: str = "",
) -> Dict[str, Any]:
    payload = _as_dict(record)
    provenance = _normalize_provenance(payload.get("provenance"), payload)
    source_entity = _as_text(payload.get("source_entity") or payload.get("source"))
    target_entity = _as_text(payload.get("target_entity") or payload.get("target"))
    relation_type = _as_text(payload.get("relation_type") or payload.get("type") or "related") or "related"
    title = _first_text(
        payload.get("title"),
        payload.get("document_title"),
        provenance.get("title"),
        provenance.get("document_title"),
        provenance.get("work_title"),
    )
    document_title = _first_text(payload.get("document_title"), provenance.get("document_title"), title)
    work_title = _first_text(payload.get("work_title"), provenance.get("work_title"))
    source_type = _first_text(payload.get("source_type"), provenance.get("source_type"), provenance.get("source"))
    source_ref = _first_text(
        payload.get("source_ref"),
        provenance.get("source_ref"),
        provenance.get("document_urn"),
        provenance.get("urn"),
        provenance.get("source_id"),
    )
    evidence_id = _first_text(payload.get("evidence_id"), payload.get("id"))
    if not evidence_id:
        evidence_id = _derive_record_id(source_entity, target_entity, relation_type, title, source_ref)

    normalized = {
        "evidence_id": evidence_id,
        "source_entity": source_entity,
        "target_entity": target_entity,
        "relation_type": relation_type,
        "confidence": _as_float(payload.get("confidence"), 0.0),
        "excerpt": _first_text(
            payload.get("excerpt"),
            payload.get("evidence"),
            provenance.get("excerpt"),
            provenance.get("text"),
            provenance.get("snippet"),
            provenance.get("sentence"),
        ),
        "entity_spans": _normalize_entity_spans(payload.get("entity_spans") or provenance.get("entity_spans")),
        "evidence_grade": _first_text(payload.get("evidence_grade"), default_evidence_grade),
        "title": title,
        "authors": _normalize_string_list(payload.get("authors") or provenance.get("authors")),
        "year": _normalize_year(payload.get("year") or provenance.get("year") or provenance.get("publication_year")),
        "journal": _first_text(payload.get("journal"), provenance.get("journal")),
        "publisher": _first_text(payload.get("publisher"), provenance.get("publisher")),
        "doi": _first_text(payload.get("doi"), provenance.get("doi")),
        "url": _first_text(payload.get("url"), provenance.get("url")),
        "abstract": _first_text(payload.get("abstract"), provenance.get("abstract")),
        "note": _first_text(payload.get("note"), provenance.get("note")),
        "source_type": source_type,
        "source_ref": source_ref,
        "document_title": document_title,
        "work_title": work_title,
        "version_lineage_key": _first_text(payload.get("version_lineage_key"), provenance.get("version_lineage_key")),
        "witness_key": _first_text(payload.get("witness_key"), provenance.get("witness_key")),
        "provenance": provenance,
    }
    entry_type = _first_text(payload.get("entry_type"), provenance.get("entry_type"), _infer_citation_entry_type(normalized))
    if entry_type:
        normalized["entry_type"] = entry_type
    return normalized


def normalize_claim_record(claim: Mapping[str, Any]) -> Dict[str, Any]:
    payload = _as_dict(claim)
    evidence_ids = [
        item
        for item in (_as_text(candidate) for candidate in _as_list(payload.get("evidence_ids")))
        if item
    ]
    source_entity = _as_text(payload.get("source_entity") or payload.get("source"))
    target_entity = _as_text(payload.get("target_entity") or payload.get("target"))
    relation_type = _as_text(payload.get("relation_type") or payload.get("type") or "related") or "related"
    claim_id = _first_text(payload.get("claim_id"), payload.get("id"))
    if not claim_id:
        claim_id = _derive_record_id(source_entity, target_entity, relation_type, "claim", ",".join(evidence_ids))

    support_count = payload.get("support_count")
    try:
        normalized_support_count = int(support_count)
    except (TypeError, ValueError):
        normalized_support_count = len(evidence_ids)

    return {
        "claim_id": claim_id,
        "source_entity": source_entity,
        "target_entity": target_entity,
        "relation_type": relation_type,
        "confidence": _as_float(payload.get("confidence"), 0.0),
        "support_count": normalized_support_count,
        "evidence_ids": evidence_ids,
        "document_title": _as_text(payload.get("document_title")),
        "work_title": _as_text(payload.get("work_title")),
        "version_lineage_key": _as_text(payload.get("version_lineage_key")),
        "witness_key": _as_text(payload.get("witness_key")),
        "review_status": _as_text(payload.get("review_status")),
        "needs_manual_review": bool(payload.get("needs_manual_review", False)),
        "review_reasons": _normalize_string_list(payload.get("review_reasons")),
        "reviewer": _as_text(payload.get("reviewer")),
        "reviewed_at": _as_text(payload.get("reviewed_at")),
        "decision_basis": _as_text(payload.get("decision_basis")),
    }


def build_citation_records_from_evidence_protocol(evidence_protocol: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return build_citation_records_from_evidence_records(
        _as_list(_as_dict(evidence_protocol).get("evidence_records"))
    )


def build_citation_records_from_evidence_records(records: Iterable[Any]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for record in records:
        normalized = record if isinstance(record, dict) else normalize_evidence_record(_as_dict(record))
        title = _first_text(normalized.get("title"), normalized.get("document_title"), normalized.get("work_title"))
        source_ref = _as_text(normalized.get("source_ref"))
        doi = _as_text(normalized.get("doi"))
        url = _as_text(normalized.get("url"))
        if not any((title, source_ref, doi, url)):
            continue

        dedupe_key = (title, source_ref, doi, url)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        note_segments = []
        evidence_id = _as_text(normalized.get("evidence_id"))
        if evidence_id:
            note_segments.append(f"evidence_id={evidence_id}")
        relation_type = _as_text(normalized.get("relation_type"))
        if relation_type:
            note_segments.append(f"relation_type={relation_type}")

        citation = {
            "title": title or source_ref or evidence_id,
            "authors": _normalize_string_list(normalized.get("authors")),
            "year": normalized.get("year"),
            "journal": _as_text(normalized.get("journal")),
            "publisher": _as_text(normalized.get("publisher")),
            "doi": doi,
            "url": url,
            "abstract": _as_text(normalized.get("abstract")),
            "note": "; ".join(note_segments),
            "source": _as_text(normalized.get("source_type") or "evidence_protocol"),
            "source_type": _as_text(normalized.get("source_type")),
            "source_ref": source_ref,
            "entry_type": _as_text(normalized.get("entry_type") or _infer_citation_entry_type(normalized)),
        }
        citations.append(citation)

    return citations


def normalize_evidence_grade_summary(evidence_grade: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    payload = _as_dict(evidence_grade)
    if not payload:
        return {}

    bias_distribution: Dict[str, int] = {}
    for key, value in _as_dict(payload.get("bias_risk_distribution")).items():
        try:
            bias_distribution[str(key)] = int(value)
        except (TypeError, ValueError):
            continue

    factor_averages: Dict[str, float] = {}
    for key, value in _as_dict(payload.get("factor_averages")).items():
        numeric = _as_float(value, None)
        if numeric is None:
            continue
        factor_averages[str(key)] = round(numeric, 4)

    summary_lines = _normalize_string_list(payload.get("summary"))
    study_results = _as_list(payload.get("study_results"))
    study_count = payload.get("study_count")
    try:
        normalized_study_count = int(study_count)
    except (TypeError, ValueError):
        normalized_study_count = len(study_results)

    return {
        "overall_grade": _as_text(payload.get("overall_grade")),
        "overall_score": round(_as_float(payload.get("overall_score"), 0.0), 4),
        "study_count": normalized_study_count,
        "factor_averages": factor_averages,
        "bias_risk_distribution": bias_distribution,
        "summary": summary_lines,
    }


def _build_research_grade_protocol(
    reasoning: Mapping[str, Any],
    nested_reasoning: Mapping[str, Any],
) -> Dict[str, Any]:
    diagnostics = _as_dict(reasoning.get("research_grade_diagnostics") or nested_reasoning.get("research_grade_diagnostics"))
    fusion = _as_dict(reasoning.get("multimodal_fusion") or nested_reasoning.get("multimodal_fusion"))
    if not diagnostics and not fusion:
        return {}
    return {
        "diagnostics": diagnostics,
        "fusion": {
            "confidence": _as_float(fusion.get("confidence"), 0.0),
            "evidence_score": _as_float(fusion.get("evidence_score"), 0.0),
            "strategy": _as_text(fusion.get("strategy") or "attention"),
        },
    }


def _build_protocol_summary(
    evidence_records: List[Dict[str, Any]],
    claims: List[Dict[str, Any]],
    citation_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    source_type_counts: Dict[str, int] = {}
    relation_type_counts: Dict[str, int] = {}
    linked_claim_count = 0

    for record in evidence_records:
        source_type = _as_text(record.get("source_type")) or "unknown"
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        relation_type = _as_text(record.get("relation_type")) or "related"
        relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1

    for claim in claims:
        if _as_list(claim.get("evidence_ids")):
            linked_claim_count += 1

    return {
        "evidence_record_count": len(evidence_records),
        "claim_count": len(claims),
        "citation_count": len(citation_records),
        "source_type_counts": source_type_counts,
        "relation_type_counts": relation_type_counts,
        "linked_claim_count": linked_claim_count,
    }


def _normalize_provenance(value: Any, record: Mapping[str, Any]) -> Dict[str, Any]:
    provenance = _as_dict(value)
    field_map = {
        "source": "source",
        "source_type": "source_type",
        "source_ref": "source_ref",
        "document_urn": "document_urn",
        "document_title": "document_title",
        "work_title": "work_title",
        "version_lineage_key": "version_lineage_key",
        "witness_key": "witness_key",
        "title": "title",
        "excerpt": "excerpt",
        "text": "text",
        "doi": "doi",
        "url": "url",
        "journal": "journal",
        "publisher": "publisher",
        "year": "year",
        "publication_year": "publication_year",
        "authors": "authors",
        "abstract": "abstract",
        "entry_type": "entry_type",
        "note": "note",
        "entity_spans": "entity_spans",
    }
    for target_key, source_key in field_map.items():
        if target_key in provenance and provenance.get(target_key) not in (None, "", [], {}):
            continue
        candidate = record.get(source_key)
        if candidate in (None, "", [], {}):
            continue
        provenance[target_key] = candidate
    return provenance


def _infer_citation_entry_type(record: Mapping[str, Any]) -> str:
    journal = _as_text(record.get("journal"))
    publisher = _as_text(record.get("publisher"))
    if journal:
        return "article"
    if publisher:
        return "book"
    return "misc"


def _derive_record_id(
    source_entity: str,
    target_entity: str,
    relation_type: str,
    title: str,
    source_ref: str,
) -> str:
    parts = [source_entity, target_entity, relation_type, title or source_ref or "evidence"]
    normalized_parts = [_slugify(part) for part in parts if part]
    if not normalized_parts:
        return "derived:evidence"
    return "derived:" + ":".join(normalized_parts)


def _slugify(value: Any) -> str:
    text = _as_text(value).lower().replace(" ", "_")
    allowed = []
    for char in text:
        if char.isalnum() or char in {"_", "-", ":"}:
            allowed.append(char)
    return "".join(allowed)[:64] or "item"


def _normalize_entity_spans(value: Any) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, Mapping):
            continue
        spans.append(dict(item))
    return spans


def _normalize_string_list(value: Any) -> List[str]:
    normalized: List[str] = []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    for item in _as_list(value):
        text = _as_text(item)
        if text:
            normalized.append(text)
    return normalized


def _normalize_year(value: Any) -> Any:
    if value in (None, ""):
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return _as_text(value)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any, default: Optional[float]) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default