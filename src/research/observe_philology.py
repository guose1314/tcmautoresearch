from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

OBSERVE_PHILOLOGY_TERMINOLOGY_TABLE_ARTIFACT = "observe_philology_terminology_table"
OBSERVE_PHILOLOGY_COLLATION_ENTRIES_ARTIFACT = "observe_philology_collation_entries"
OBSERVE_PHILOLOGY_ANNOTATION_REPORT_ARTIFACT = "observe_philology_annotation_report"
OBSERVE_PHILOLOGY_ARTIFACT_NAMES = frozenset(
    {
        OBSERVE_PHILOLOGY_TERMINOLOGY_TABLE_ARTIFACT,
        OBSERVE_PHILOLOGY_COLLATION_ENTRIES_ARTIFACT,
        OBSERVE_PHILOLOGY_ANNOTATION_REPORT_ARTIFACT,
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
]


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


def normalize_observe_philology_assets(raw_assets: Any) -> Dict[str, Any]:
    assets = _as_dict(raw_assets)
    terminology_rows = _as_dict_list(assets.get("terminology_standard_table"))
    collation_entries = _as_dict_list(assets.get("collation_entries"))
    annotation_report = _as_dict(assets.get("annotation_report"))
    summary = _as_dict(annotation_report.get("summary"))
    document_reports = _as_dict_list(annotation_report.get("documents"))

    document_identifiers = _unique_document_identifiers(terminology_rows, collation_entries, document_reports)
    document_count = _safe_int(summary.get("processed_document_count") or summary.get("document_count"), 0)
    if document_count <= 0:
        document_count = len(document_identifiers)

    philology_notes = _as_string_list(summary.get("philology_notes"))
    if philology_notes or summary:
        summary["philology_notes"] = philology_notes
    if summary or document_count:
        summary.setdefault("processed_document_count", document_count)
        summary.setdefault("terminology_standard_table_count", len(terminology_rows))
        summary.setdefault("collation_entry_count", len(collation_entries))

    normalized_report = dict(annotation_report)
    if summary or "summary" in annotation_report:
        normalized_report["summary"] = summary
    if document_reports or "documents" in annotation_report:
        normalized_report["documents"] = document_reports

    asset_count = sum(
        1
        for payload in (terminology_rows, collation_entries, normalized_report)
        if payload not in ({}, [], None, "")
    )
    available = bool(asset_count)

    return {
        "available": available,
        "asset_count": asset_count,
        "document_count": document_count,
        "terminology_standard_table": terminology_rows,
        "terminology_standard_table_count": len(terminology_rows),
        "collation_entries": collation_entries,
        "collation_entry_count": len(collation_entries),
        "annotation_report": normalized_report,
        "philology_note_count": len(philology_notes),
    }


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


def extract_observe_philology_assets_from_documents(
    observe_documents: Sequence[Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    documents = [dict(item) for item in (observe_documents or []) if isinstance(item, Mapping)]
    if not documents:
        return normalize_observe_philology_assets({})

    terminology_rows: List[Dict[str, Any]] = []
    collation_entries: List[Dict[str, Any]] = []
    row_keys: set[tuple[str, str, tuple[str, ...]]] = set()
    entry_keys: set[tuple[str, str, str, str, str]] = set()
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
                "philology_notes": document_notes,
            }
        )

    if not terminology_rows and not collation_entries and not document_reports:
        return normalize_observe_philology_assets({})

    return normalize_observe_philology_assets(
        {
            "terminology_standard_table": terminology_rows,
            "collation_entries": collation_entries,
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
                    "philology_notes": philology_notes,
                },
                "documents": document_reports,
            },
        }
    )


def extract_observe_philology_assets_from_phase_result(observe_phase_result: Mapping[str, Any] | None) -> Dict[str, Any]:
    phase_result = _as_dict(observe_phase_result)
    phase_artifacts = extract_observe_philology_assets_from_artifacts(_as_dict_list(phase_result.get("artifacts")))
    if phase_artifacts["available"]:
        return phase_artifacts

    results = _as_dict(phase_result.get("results"))
    ingestion_pipeline = _as_dict(results.get("ingestion_pipeline") or phase_result.get("ingestion_pipeline"))
    aggregate = _as_dict(ingestion_pipeline.get("aggregate"))
    assets = normalize_observe_philology_assets(aggregate.get("philology_assets"))
    if assets["available"]:
        return assets

    document_assets = extract_observe_philology_assets_from_documents(
        _as_dict_list(ingestion_pipeline.get("documents")),
    )
    if document_assets["available"]:
        return document_assets
    return normalize_observe_philology_assets({})


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

    resolved_payload: Dict[str, Any] = {}
    sources: List[str] = []
    for source_name, candidate in source_candidates:
        if not candidate.get("available"):
            continue
        sources.append(source_name)
        if not resolved_payload.get("terminology_standard_table") and candidate.get("terminology_standard_table"):
            resolved_payload["terminology_standard_table"] = candidate["terminology_standard_table"]
        if not resolved_payload.get("collation_entries") and candidate.get("collation_entries"):
            resolved_payload["collation_entries"] = candidate["collation_entries"]
        if not resolved_payload.get("annotation_report") and candidate.get("annotation_report"):
            resolved_payload["annotation_report"] = candidate["annotation_report"]

    normalized = normalize_observe_philology_assets(resolved_payload)
    if sources:
        normalized["source"] = sources[0]
        normalized["sources"] = sources
    else:
        normalized["source"] = "unavailable"
        normalized["sources"] = []
    return normalized