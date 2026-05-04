"""Ground LLM research outputs against text spans and reviewed evidence."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

CITATION_GROUNDING_EVALUATOR_VERSION = "citation-grounding-evaluator-v2"
DEFAULT_GROUNDING_THRESHOLD = 0.72

_SUPPORTED_REVIEW_STATUSES = frozenset(
    {"accepted", "approved", "reviewed", "verified", "citation_supported"}
)
_SUPPORTED_LEVELS = frozenset({"strong", "moderate", "weak", "supported"})
_UNSUPPORTED_LEVELS = frozenset({"unsupported", "none", "missing"})
_CLAIM_ID_PATTERNS = (
    re.compile(r"\[(?:claim|claim_id):(?P<id>[^\]]+)\]", re.IGNORECASE),
    re.compile(r"<!--\s*claim_id\s*[:=]\s*(?P<id>[^>]+?)\s*-->", re.IGNORECASE),
    re.compile(r"(?:^|\b)claim_id\s*[:=]\s*(?P<id>[A-Za-z0-9_.:\-]+)", re.IGNORECASE),
)
_MARKDOWN_CITATION_PATTERN = re.compile(r"\[@(?P<keys>[^\]]+)\]")
_BRACKET_CITATION_PATTERN = re.compile(
    r"\[(?:cite|citation):(?P<keys>[^\]]+)\]",
    re.IGNORECASE,
)
_INLINE_CITATION_KEYS_PATTERN = re.compile(
    r"citation_keys?\s*[:=]\s*(?P<keys>[^\n\r;]+)",
    re.IGNORECASE,
)
_CLAIM_MARKER_PATTERN = re.compile(
    r"\[(?:claim|claim_id):|<!--\s*claim_id\s*[:=]|(?:^|\b)claim\s*[:：]",
    re.IGNORECASE,
)
_WORD_PATTERN = re.compile(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class GroundedAsset:
    asset_id: str
    asset_type: str
    text: str
    terms: list[str] = field(default_factory=list)
    citation_keys: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    source_type: str
    text: str
    citation_keys: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    reviewed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CitationGroundingEvaluator:
    """Evaluate whether generated entities, relations, and claims are grounded."""

    def __init__(self, *, threshold: float = DEFAULT_GROUNDING_THRESHOLD) -> None:
        self.threshold = _clamp_score(threshold, DEFAULT_GROUNDING_THRESHOLD)

    def evaluate(
        self,
        *,
        llm_output: Any = None,
        report_markdown: str = "",
        text_segments: Optional[Sequence[Mapping[str, Any]]] = None,
        reviewed_evidence: Optional[Sequence[Mapping[str, Any]]] = None,
        evidence_protocol: Optional[Mapping[str, Any]] = None,
        graph_rag_context: Optional[Mapping[str, Any]] = None,
        citation_records: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> dict[str, Any]:
        payload = _coerce_mapping(llm_output)
        markdown = str(report_markdown or "").strip() or _extract_report_markdown(
            payload
        )
        assets = _dedupe_assets(_extract_assets(payload, markdown))
        evidence_sources = _dedupe_sources(
            [
                *_sources_from_segments(text_segments),
                *_sources_from_provenance(_collect_provenance(payload)),
                *_sources_from_reviewed_evidence(reviewed_evidence),
                *_sources_from_evidence_protocol(evidence_protocol),
                *_sources_from_graph_context(graph_rag_context),
                *_sources_from_grounding_records(_extract_grounding_records(payload)),
            ]
        )
        known_citation_keys = _known_citation_keys(citation_records, evidence_sources)

        supported_assets: list[dict[str, Any]] = []
        unsupported_assets: list[dict[str, Any]] = []
        citation_mismatch: list[dict[str, Any]] = []
        for asset in assets:
            support_source = _supporting_source(asset, evidence_sources)
            if support_source is not None:
                supported_assets.append(
                    {
                        "asset_id": asset.asset_id,
                        "asset_type": asset.asset_type,
                        "source_id": support_source.source_id,
                        "source_type": support_source.source_type,
                    }
                )
            else:
                unsupported_assets.append(asset.to_dict())

            missing_citations = [
                key
                for key in asset.citation_keys
                if _normalize_key(key) not in known_citation_keys
            ]
            for citation_key in missing_citations:
                citation_mismatch.append(
                    {
                        "asset_id": asset.asset_id,
                        "asset_type": asset.asset_type,
                        "citation_key": citation_key,
                        "reason": "unknown_citation_key",
                    }
                )
            if asset.citation_keys and support_source is None:
                citation_mismatch.append(
                    {
                        "asset_id": asset.asset_id,
                        "asset_type": asset.asset_type,
                        "citation_keys": list(asset.citation_keys),
                        "reason": "citation_not_grounding_asset",
                    }
                )

        asset_count = len(assets)
        supported_count = len(supported_assets)
        grounding_score = _safe_rate(supported_count, asset_count)
        unsupported_claims = [
            item for item in unsupported_assets if item.get("asset_type") == "claim"
        ]
        return {
            "contract_version": CITATION_GROUNDING_EVALUATOR_VERSION,
            "grounding_score": grounding_score,
            "threshold": self.threshold,
            "formal_conclusion_allowed": grounding_score >= self.threshold,
            "asset_count": asset_count,
            "supported_asset_count": supported_count,
            "unsupported_asset_count": len(unsupported_assets),
            "evidence_source_count": len(evidence_sources),
            "unsupported_claims": unsupported_claims,
            "unsupported_assets": unsupported_assets,
            "citation_mismatch": _dedupe_mismatches(citation_mismatch),
            "supported_assets": supported_assets,
        }


def evaluate_citation_grounding(
    *,
    llm_output: Any = None,
    report_markdown: str = "",
    text_segments: Optional[Sequence[Mapping[str, Any]]] = None,
    reviewed_evidence: Optional[Sequence[Mapping[str, Any]]] = None,
    evidence_protocol: Optional[Mapping[str, Any]] = None,
    graph_rag_context: Optional[Mapping[str, Any]] = None,
    citation_records: Optional[Sequence[Mapping[str, Any]]] = None,
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> dict[str, Any]:
    return CitationGroundingEvaluator(threshold=threshold).evaluate(
        llm_output=llm_output,
        report_markdown=report_markdown,
        text_segments=text_segments,
        reviewed_evidence=reviewed_evidence,
        evidence_protocol=evidence_protocol,
        graph_rag_context=graph_rag_context,
        citation_records=citation_records,
    )


def _extract_assets(payload: Mapping[str, Any], markdown: str) -> list[GroundedAsset]:
    assets: list[GroundedAsset] = []
    for item in _iter_named_list_items(payload, {"entities"}):
        name = _first_text(item, "name", "text", "value", "canonical")
        if not name:
            continue
        entity_type = _first_text(item, "type", "entity_type") or "entity"
        assets.append(
            GroundedAsset(
                asset_id=_first_text(item, "id", "entity_id") or f"entity:{name}",
                asset_type="entity",
                text=name,
                terms=[name],
                citation_keys=_citation_keys_from_mapping(item),
                provenance=_extract_provenance(item),
            )
        )
    for item in _iter_named_list_items(
        payload, {"relationships", "relations", "edges", "entity_relationships"}
    ):
        source = _plain_name(_first_text(item, "source", "from", "source_entity"))
        target = _plain_name(_first_text(item, "target", "to", "target_entity"))
        relation = _first_text(item, "type", "relation", "relation_type", "label")
        if not (source or target):
            continue
        relation_text = " ".join(part for part in (source, relation, target) if part)
        assets.append(
            GroundedAsset(
                asset_id=(
                    _first_text(item, "id", "relationship_id")
                    or f"relation:{source}:{relation}:{target}"
                ),
                asset_type="relation",
                text=relation_text,
                terms=[term for term in (source, target) if term],
                citation_keys=_citation_keys_from_mapping(item),
                provenance=_extract_provenance(item),
            )
        )
    for item in _iter_named_list_items(
        payload,
        {"claims", "conclusions", "hypotheses", "hypothesis_candidates"},
    ):
        claim = _claim_asset_from_mapping(item)
        if claim is not None:
            assets.append(claim)
    for record in _extract_grounding_records(payload):
        if _is_placeholder_grounding_record(record):
            continue
        claim = _claim_asset_from_mapping(record)
        if claim is not None:
            assets.append(claim)
    assets.extend(_extract_markdown_claim_assets(markdown))
    return assets


def _claim_asset_from_mapping(item: Mapping[str, Any]) -> Optional[GroundedAsset]:
    claim_id = _first_text(item, "claim_id", "id", "hypothesis_id")
    source = _plain_name(_first_text(item, "source", "source_entity"))
    target = _plain_name(_first_text(item, "target", "target_entity"))
    relation = _first_text(item, "relation", "relation_type", "type")
    claim_text = _first_text(
        item,
        "claim_text",
        "claim",
        "conclusion",
        "decision_basis",
        "reason",
        "title",
        "description",
    )
    if not claim_text and any((source, target, relation)):
        claim_text = " ".join(part for part in (source, relation, target) if part)
    if not claim_text and not claim_id:
        return None
    terms = [term for term in (source, target) if term]
    if not terms:
        terms = _significant_terms(claim_text)[:6]
    return GroundedAsset(
        asset_id=claim_id or f"claim:{_normalize_compact(claim_text)[:48]}",
        asset_type="claim",
        text=claim_text or claim_id,
        terms=terms,
        citation_keys=_citation_keys_from_mapping(item),
        provenance=_extract_provenance(item),
    )


def _extract_markdown_claim_assets(markdown: str) -> list[GroundedAsset]:
    assets: list[GroundedAsset] = []
    for index, paragraph in enumerate(_iter_markdown_paragraphs(markdown), start=1):
        if not _CLAIM_MARKER_PATTERN.search(paragraph):
            continue
        claim_id = _extract_claim_id(paragraph) or f"markdown-claim-{index}"
        clean_text = _clean_claim_text(paragraph)
        assets.append(
            GroundedAsset(
                asset_id=claim_id,
                asset_type="claim",
                text=clean_text,
                terms=_significant_terms(clean_text)[:6],
                citation_keys=extract_citation_keys(paragraph),
            )
        )
    return assets


def extract_citation_keys(text: str) -> list[str]:
    keys: list[str] = []
    for match in _MARKDOWN_CITATION_PATTERN.finditer(str(text or "")):
        keys.extend(_split_citation_keys(match.group("keys")))
    for match in _BRACKET_CITATION_PATTERN.finditer(str(text or "")):
        keys.extend(_split_citation_keys(match.group("keys")))
    for match in _INLINE_CITATION_KEYS_PATTERN.finditer(str(text or "")):
        keys.extend(_split_citation_keys(match.group("keys")))
    return _dedupe_text(keys)


def _sources_from_segments(
    segments: Optional[Sequence[Mapping[str, Any]]],
) -> list[EvidenceSource]:
    return [
        _source_from_provenance(item)
        for item in segments or []
        if isinstance(item, Mapping) and str(item.get("quote_text") or "").strip()
    ]


def _sources_from_provenance(
    provenance_items: Sequence[Mapping[str, Any]],
) -> list[EvidenceSource]:
    return [
        _source_from_provenance(item)
        for item in provenance_items or []
        if isinstance(item, Mapping) and str(item.get("quote_text") or "").strip()
    ]


def _source_from_provenance(item: Mapping[str, Any]) -> EvidenceSource:
    source_id = _first_text(item, "segment_id", "id") or "text-segment"
    document_id = _first_text(item, "document_id")
    if document_id:
        source_id = f"{document_id}:{source_id}"
    return EvidenceSource(
        source_id=source_id,
        source_type="text_segment_provenance",
        text=str(item.get("quote_text") or ""),
        citation_keys=_citation_keys_from_mapping(item),
        provenance=[dict(item)],
        reviewed=True,
    )


def _sources_from_reviewed_evidence(
    evidence_items: Optional[Sequence[Mapping[str, Any]]],
) -> list[EvidenceSource]:
    sources: list[EvidenceSource] = []
    for item in evidence_items or []:
        if not isinstance(item, Mapping):
            continue
        reviewed = _is_reviewed(item)
        if reviewed:
            sources.append(_source_from_mapping(item, source_type="reviewed_evidence"))
    return sources


def _sources_from_evidence_protocol(
    evidence_protocol: Optional[Mapping[str, Any]],
) -> list[EvidenceSource]:
    protocol = _coerce_mapping(evidence_protocol)
    sources: list[EvidenceSource] = []
    for record in protocol.get("evidence_records") or []:
        if isinstance(record, Mapping):
            reviewed = _is_reviewed(record) or not str(
                record.get("review_status") or ""
            )
            source = _source_from_mapping(record, source_type="evidence_record")
            if reviewed and (source.text or source.provenance):
                sources.append(source)
    for claim in protocol.get("claims") or []:
        if isinstance(claim, Mapping):
            reviewed = _is_reviewed(claim) or bool(claim.get("evidence_ids"))
            if reviewed:
                sources.append(
                    _source_from_mapping(claim, source_type="evidence_claim")
                )
    return sources


def _sources_from_graph_context(
    graph_rag_context: Optional[Mapping[str, Any]],
) -> list[EvidenceSource]:
    context = _coerce_mapping(graph_rag_context)
    traces = context.get("traces") if isinstance(context.get("traces"), Mapping) else {}
    sources: list[EvidenceSource] = []
    for trace_type, items in dict(traces or {}).items():
        for item in items or []:
            if not isinstance(item, Mapping):
                continue
            source = _source_from_mapping(item, source_type=f"graph_trace:{trace_type}")
            if source.text or source.source_id:
                sources.append(source)
    return sources


def _sources_from_grounding_records(
    grounding_records: Sequence[Mapping[str, Any]],
) -> list[EvidenceSource]:
    sources: list[EvidenceSource] = []
    for record in grounding_records or []:
        if not isinstance(record, Mapping) or _is_placeholder_grounding_record(record):
            continue
        support_level = str(record.get("support_level") or "").strip().lower()
        if support_level in _SUPPORTED_LEVELS:
            sources.append(
                _source_from_mapping(record, source_type="citation_grounding_record")
            )
    return sources


def _source_from_mapping(
    item: Mapping[str, Any], *, source_type: str
) -> EvidenceSource:
    provenance = _extract_provenance(item)
    text = _first_text(
        item,
        "quote_text",
        "excerpt",
        "claim_text",
        "decision_basis",
        "body",
        "label",
        "title",
        "description",
        "text",
    )
    if not text and provenance:
        text = "\n".join(str(value.get("quote_text") or "") for value in provenance)
    source = _plain_name(_first_text(item, "source", "source_entity"))
    target = _plain_name(_first_text(item, "target", "target_entity"))
    relation = _first_text(item, "relation", "relation_type", "type")
    if not text and any((source, target, relation)):
        text = " ".join(part for part in (source, relation, target) if part)
    return EvidenceSource(
        source_id=_first_text(item, "claim_id", "evidence_id", "id", "source_ref")
        or _normalize_compact(text)[:64]
        or source_type,
        source_type=source_type,
        text=text,
        citation_keys=_citation_keys_from_mapping(item),
        provenance=provenance,
        reviewed=True,
    )


def _supporting_source(
    asset: GroundedAsset,
    evidence_sources: Sequence[EvidenceSource],
) -> Optional[EvidenceSource]:
    for provenance in asset.provenance:
        if _source_text_supports_asset(str(provenance.get("quote_text") or ""), asset):
            return _source_from_provenance(provenance)
    for source in evidence_sources:
        if not source.reviewed:
            continue
        if asset.asset_id and asset.asset_id == source.source_id:
            return source
        if source.provenance and any(
            _source_text_supports_asset(str(item.get("quote_text") or ""), asset)
            for item in source.provenance
        ):
            return source
        if _source_text_supports_asset(source.text, asset):
            return source
    return None


def _source_text_supports_asset(source_text: str, asset: GroundedAsset) -> bool:
    source_norm = _normalize_compact(source_text)
    asset_norm = _normalize_compact(asset.text)
    if not source_norm:
        return False
    if asset_norm and (asset_norm in source_norm or source_norm in asset_norm):
        return True
    terms = [
        _normalize_compact(term) for term in asset.terms if _normalize_compact(term)
    ]
    if not terms:
        return False
    matched = sum(1 for term in terms if term in source_norm)
    required = len(terms) if len(terms) <= 2 else 2
    return matched >= required


def _known_citation_keys(
    citation_records: Optional[Sequence[Mapping[str, Any]]],
    evidence_sources: Sequence[EvidenceSource],
) -> set[str]:
    keys: set[str] = set()
    for record in citation_records or []:
        if isinstance(record, Mapping):
            keys.update(
                _normalize_key(key) for key in _citation_keys_from_mapping(record)
            )
    for source in evidence_sources:
        keys.update(_normalize_key(key) for key in source.citation_keys)
    return {key for key in keys if key}


def _collect_provenance(value: Any) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        if "segment_id" in value and "quote_text" in value:
            collected.append(dict(value))
        for key in ("provenance", "text_segment_provenance"):
            nested = value.get(key)
            if isinstance(nested, list):
                collected.extend(
                    dict(item) for item in nested if isinstance(item, Mapping)
                )
            elif isinstance(nested, Mapping):
                collected.append(dict(nested))
        for nested_value in value.values():
            if isinstance(nested_value, (Mapping, list, tuple)):
                collected.extend(_collect_provenance(nested_value))
    elif isinstance(value, (list, tuple)):
        for item in value:
            collected.extend(_collect_provenance(item))
    return collected


def _extract_provenance(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    provenance = _collect_provenance(item.get("provenance"))
    if provenance:
        return provenance
    for key in ("attributes", "metadata"):
        nested = item.get(key)
        if isinstance(nested, Mapping):
            provenance = _collect_provenance(nested.get("provenance"))
            if provenance:
                return provenance
    if "segment_id" in item and "quote_text" in item:
        return [dict(item)]
    return []


def _extract_grounding_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in _iter_named_list_items(
        payload,
        {"citation_grounding_records", "citation_grounding", "grounding_records"},
    ):
        if isinstance(item, Mapping):
            records.append(dict(item))
    return records


def _iter_named_list_items(
    value: Any,
    names: set[str],
) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if key in names and isinstance(nested_value, list):
                for item in nested_value:
                    if isinstance(item, Mapping):
                        yield item
            elif isinstance(nested_value, (Mapping, list, tuple)) and key not in {
                "provenance",
                "citation_records",
            }:
                yield from _iter_named_list_items(nested_value, names)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_named_list_items(item, names)


def _extract_report_markdown(payload: Mapping[str, Any]) -> str:
    for key in (
        "report_markdown",
        "paper_markdown",
        "markdown_report",
        "markdown",
        "report_body",
        "content",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("paper_draft", "results", "research_artifact", "paper_context"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _extract_report_markdown(value)
            if nested:
                return nested
    return ""


def _iter_markdown_paragraphs(markdown: str) -> list[str]:
    text = str(markdown or "").strip()
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) == 1:
        return [line.strip() for line in text.splitlines() if line.strip()]
    return paragraphs


def _extract_claim_id(text: str) -> str:
    for pattern in _CLAIM_ID_PATTERNS:
        match = pattern.search(str(text or ""))
        if match:
            return str(match.group("id") or "").strip().strip(" []<>`'\"")
    return ""


def _split_citation_keys(value: Any) -> list[str]:
    keys: list[str] = []
    for item in re.split(r"[;,，；\s]+", str(value or "")):
        normalized = item.strip().strip("[](){}.,;，；")
        if normalized.startswith("@"):
            normalized = normalized[1:]
        if normalized:
            keys.append(normalized)
    return keys


def _clean_claim_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"\[(?:claim|claim_id):[^\]]+\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"<!--\s*claim_id\s*[:=][^>]+-->", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = _MARKDOWN_CITATION_PATTERN.sub("", cleaned)
    cleaned = _BRACKET_CITATION_PATTERN.sub("", cleaned)
    cleaned = _INLINE_CITATION_KEYS_PATTERN.sub("", cleaned)
    return " ".join(cleaned.split())


def _citation_keys_from_mapping(item: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for key in (
        "citation_key",
        "citation_id",
        "source_ref",
        "document_urn",
        "witness_key",
        "id",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            keys.append(value.strip())
    for key in ("citation_keys", "source_refs", "evidence_claim_ids", "witness_keys"):
        values = item.get(key)
        if isinstance(values, list):
            keys.extend(str(value).strip() for value in values if str(value).strip())
    citation = item.get("citation")
    if isinstance(citation, Mapping):
        keys.extend(_citation_keys_from_mapping(citation))
    return _dedupe_text(keys)


def _is_reviewed(item: Mapping[str, Any]) -> bool:
    status = (
        str(
            item.get("review_status")
            or item.get("expert_review_status")
            or item.get("status")
            or ""
        )
        .strip()
        .lower()
    )
    support_level = str(item.get("support_level") or "").strip().lower()
    if status in _SUPPORTED_REVIEW_STATUSES:
        return True
    if support_level in _SUPPORTED_LEVELS:
        return True
    return False


def _is_placeholder_grounding_record(record: Mapping[str, Any]) -> bool:
    claim_id = str(record.get("claim_id") or "").strip().lower()
    paragraph_id = str(record.get("paragraph_id") or "").strip().lower()
    claim_text = str(record.get("claim_text") or "").strip()
    support_level = str(record.get("support_level") or "").strip().lower()
    return (
        claim_id == "unsupported"
        and paragraph_id == "publish:unsupported"
        and not claim_text
        and support_level in _UNSUPPORTED_LEVELS
    )


def _first_text(item: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (Mapping, list, tuple)):
            text = str(value).strip()
            if text:
                return text
    attrs = item.get("attributes")
    if isinstance(attrs, Mapping):
        return _first_text(attrs, *keys)
    return ""


def _plain_name(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if ":" in text else text


def _significant_terms(text: str) -> list[str]:
    return _dedupe_text(
        match.group(0) for match in _WORD_PATTERN.finditer(str(text or ""))
    )


def _normalize_compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().strip("@[](){}.,;，；").lower()


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        return {"report_markdown": value}
    return {}


def _dedupe_text(values: Iterable[Any]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _dedupe_assets(assets: Iterable[GroundedAsset]) -> list[GroundedAsset]:
    deduped: list[GroundedAsset] = []
    seen: set[tuple[str, str, str]] = set()
    for asset in assets:
        key = (asset.asset_type, asset.asset_id, _normalize_compact(asset.text))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(asset)
    return deduped


def _dedupe_sources(sources: Iterable[EvidenceSource]) -> list[EvidenceSource]:
    deduped: list[EvidenceSource] = []
    seen: set[tuple[str, str, str]] = set()
    for source in sources:
        key = (source.source_type, source.source_id, _normalize_compact(source.text))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _dedupe_mismatches(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (
            str(item.get("asset_id") or ""),
            str(item.get("asset_type") or ""),
            str(item.get("citation_key") or item.get("citation_keys") or ""),
            str(item.get("reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(float(numerator) / float(denominator), 6)


def _clamp_score(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(0.0, min(1.0, number))


__all__ = [
    "CITATION_GROUNDING_EVALUATOR_VERSION",
    "DEFAULT_GROUNDING_THRESHOLD",
    "CitationGroundingEvaluator",
    "EvidenceSource",
    "GroundedAsset",
    "evaluate_citation_grounding",
    "extract_citation_keys",
]
