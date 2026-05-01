from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence

SUPPORT_LEVEL_STRONG = "strong"
SUPPORT_LEVEL_MODERATE = "moderate"
SUPPORT_LEVEL_WEAK = "weak"
SUPPORT_LEVEL_UNSUPPORTED = "unsupported"
SUPPORT_LEVELS = (
    SUPPORT_LEVEL_STRONG,
    SUPPORT_LEVEL_MODERATE,
    SUPPORT_LEVEL_WEAK,
    SUPPORT_LEVEL_UNSUPPORTED,
)


@dataclass
class CitationGroundingRecord:
    claim_id: str = ""
    paragraph_id: str = ""
    citation_keys: List[str] = field(default_factory=list)
    evidence_claim_ids: List[str] = field(default_factory=list)
    witness_keys: List[str] = field(default_factory=list)
    support_level: str = SUPPORT_LEVEL_UNSUPPORTED
    uncertainty_note: str = ""
    evidence_ids: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    citation_records: List[Dict[str, Any]] = field(default_factory=list)
    graph_trace_ids: List[str] = field(default_factory=list)
    claim_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CitationEvidenceSynthesizer:
    def synthesize(
        self,
        *,
        evidence_protocol: Mapping[str, Any] | None = None,
        citation_records: Sequence[Mapping[str, Any]] | None = None,
        observe_philology: Mapping[str, Any] | None = None,
        graph_rag_context: Mapping[str, Any] | None = None,
    ) -> List[CitationGroundingRecord]:
        protocol = _as_dict(evidence_protocol)
        records = [
            _as_dict(item) for item in _as_list(protocol.get("evidence_records"))
        ]
        claims = [_as_dict(item) for item in _as_list(protocol.get("claims"))]
        citations = _dedupe_dicts(
            [
                *[
                    _as_dict(item)
                    for item in _as_list(protocol.get("citation_records"))
                ],
                *[_as_dict(item) for item in _as_list(citation_records)],
            ],
            key_fields=("citation_id", "id", "source_ref", "doi", "url", "title"),
        )
        graph_context = _as_dict(graph_rag_context)
        graph_traces = _as_dict(graph_context.get("traces"))
        evidence_claim_traces = [
            _as_dict(item) for item in _as_list(graph_traces.get("EvidenceClaim"))
        ]
        version_witness_traces = [
            _as_dict(item) for item in _as_list(graph_traces.get("VersionWitness"))
        ]
        citation_traces = [
            _as_dict(item) for item in _as_list(graph_traces.get("CitationRecord"))
        ]
        observe_witness_keys = _collect_witness_keys(_as_dict(observe_philology))

        if claims:
            return [
                self._build_claim_grounding_record(
                    claim_index=index,
                    claim=claim,
                    evidence_records=records,
                    citation_records=citations,
                    evidence_claim_traces=evidence_claim_traces,
                    version_witness_traces=version_witness_traces,
                    citation_traces=citation_traces,
                    observe_witness_keys=observe_witness_keys,
                )
                for index, claim in enumerate(claims, start=1)
            ]

        if evidence_claim_traces:
            synthetic_claims = [
                {
                    "claim_id": _text(trace.get("id")) or f"graph-claim-{index}",
                    "decision_basis": _text(trace.get("body") or trace.get("label")),
                }
                for index, trace in enumerate(evidence_claim_traces, start=1)
            ]
            return [
                self._build_claim_grounding_record(
                    claim_index=index,
                    claim=claim,
                    evidence_records=records,
                    citation_records=citations,
                    evidence_claim_traces=evidence_claim_traces,
                    version_witness_traces=version_witness_traces,
                    citation_traces=citation_traces,
                    observe_witness_keys=observe_witness_keys,
                )
                for index, claim in enumerate(synthetic_claims, start=1)
            ]

        if citations or citation_traces:
            source_citations = citations or [
                _trace_to_citation_record(trace) for trace in citation_traces
            ]
            return [
                self._build_citation_only_record(index, citation)
                for index, citation in enumerate(source_citations, start=1)
            ]

        return [
            CitationGroundingRecord(
                claim_id="unsupported",
                paragraph_id="publish:unsupported",
                support_level=SUPPORT_LEVEL_UNSUPPORTED,
                uncertainty_note="No evidence claim, citation record, graph trace, or version witness is available.",
            )
        ]

    def _build_claim_grounding_record(
        self,
        *,
        claim_index: int,
        claim: Mapping[str, Any],
        evidence_records: Sequence[Mapping[str, Any]],
        citation_records: Sequence[Mapping[str, Any]],
        evidence_claim_traces: Sequence[Mapping[str, Any]],
        version_witness_traces: Sequence[Mapping[str, Any]],
        citation_traces: Sequence[Mapping[str, Any]],
        observe_witness_keys: Sequence[str],
    ) -> CitationGroundingRecord:
        claim_payload = _as_dict(claim)
        claim_id = _text(
            claim_payload.get("claim_id")
            or claim_payload.get("id")
            or f"claim-{claim_index}"
        )
        evidence_ids = _string_list(claim_payload.get("evidence_ids"))
        matched_evidence = _match_evidence_records(claim_payload, evidence_records)
        if not evidence_ids:
            evidence_ids = [
                _text(record.get("evidence_id") or record.get("id"))
                for record in matched_evidence
                if _text(record.get("evidence_id") or record.get("id"))
            ]
        matched_claim_traces = [
            trace
            for trace in evidence_claim_traces
            if _trace_matches_claim(trace, claim_id)
        ]
        if not matched_claim_traces and len(evidence_claim_traces) == 1:
            matched_claim_traces = list(evidence_claim_traces)

        source_refs = _collect_source_refs([claim_payload, *matched_evidence])
        matched_citations = _match_citation_records(source_refs, citation_records)
        if not matched_citations and matched_claim_traces and citation_records:
            matched_citations = list(citation_records)
        matched_citation_traces = _match_citation_traces(source_refs, citation_traces)
        if not matched_citation_traces and matched_claim_traces and citation_traces:
            matched_citation_traces = list(citation_traces)

        witness_keys = _dedupe_strings(
            [
                *_collect_witness_keys(claim_payload),
                *_collect_witness_keys(matched_evidence),
                *_collect_witness_keys(matched_citations),
                *_collect_witness_keys(version_witness_traces),
                *[_trace_id(trace) for trace in version_witness_traces],
                *observe_witness_keys,
            ]
        )
        citation_keys = _dedupe_strings(
            [
                *[_citation_key(citation) for citation in matched_citations],
                *[_trace_id(trace) for trace in matched_citation_traces],
            ]
        )
        evidence_claim_ids = _dedupe_strings(
            [claim_id, *[_trace_id(trace) for trace in matched_claim_traces]]
        )
        graph_trace_ids = _dedupe_strings(
            [
                *[_trace_id(trace) for trace in matched_claim_traces],
                *[_trace_id(trace) for trace in version_witness_traces],
                *[_trace_id(trace) for trace in matched_citation_traces],
            ]
        )
        support_level = _resolve_support_level(
            has_evidence_claim=bool(matched_claim_traces),
            has_evidence_record=bool(matched_evidence or evidence_ids),
            has_citation=bool(matched_citations or matched_citation_traces),
            has_witness=bool(witness_keys),
        )

        return CitationGroundingRecord(
            claim_id=claim_id,
            paragraph_id=_text(claim_payload.get("paragraph_id"))
            or f"publish:claim:{claim_index}",
            citation_keys=citation_keys,
            evidence_claim_ids=evidence_claim_ids,
            witness_keys=witness_keys,
            support_level=support_level,
            uncertainty_note=_uncertainty_note(support_level),
            evidence_ids=_dedupe_strings(evidence_ids),
            source_refs=source_refs,
            citation_records=[copy.deepcopy(dict(item)) for item in matched_citations],
            graph_trace_ids=graph_trace_ids,
            claim_text=_claim_text(claim_payload),
        )

    def _build_citation_only_record(
        self,
        index: int,
        citation: Mapping[str, Any],
    ) -> CitationGroundingRecord:
        citation_payload = _as_dict(citation)
        citation_key = _citation_key(citation_payload) or f"citation-{index}"
        return CitationGroundingRecord(
            claim_id=f"citation:{citation_key}",
            paragraph_id=f"publish:citation:{index}",
            citation_keys=[citation_key],
            support_level=SUPPORT_LEVEL_WEAK,
            uncertainty_note=_uncertainty_note(SUPPORT_LEVEL_WEAK),
            source_refs=_collect_source_refs([citation_payload]),
            citation_records=[copy.deepcopy(citation_payload)],
            claim_text=_text(citation_payload.get("title") or citation_key),
        )


def summarize_citation_grounding(
    records: Iterable[CitationGroundingRecord | Mapping[str, Any]],
) -> Dict[str, Any]:
    counts = {level: 0 for level in SUPPORT_LEVELS}
    total = 0
    for record in records:
        payload = record.to_dict() if hasattr(record, "to_dict") else _as_dict(record)
        level = _text(payload.get("support_level")) or SUPPORT_LEVEL_UNSUPPORTED
        if level not in counts:
            level = SUPPORT_LEVEL_UNSUPPORTED
        counts[level] += 1
        total += 1
    return {
        "record_count": total,
        "support_level_counts": counts,
        "unsupported_count": counts[SUPPORT_LEVEL_UNSUPPORTED],
        "supported_count": total - counts[SUPPORT_LEVEL_UNSUPPORTED],
    }


def _resolve_support_level(
    *,
    has_evidence_claim: bool,
    has_evidence_record: bool,
    has_citation: bool,
    has_witness: bool,
) -> str:
    if has_evidence_claim and has_citation and has_witness:
        return SUPPORT_LEVEL_STRONG
    if (has_evidence_claim and (has_citation or has_witness)) or (
        has_evidence_record and has_citation
    ):
        return SUPPORT_LEVEL_MODERATE
    if has_citation or has_evidence_record or has_witness:
        return SUPPORT_LEVEL_WEAK
    return SUPPORT_LEVEL_UNSUPPORTED


def _uncertainty_note(support_level: str) -> str:
    if support_level == SUPPORT_LEVEL_STRONG:
        return "EvidenceClaim, citation, and version witness are all linked."
    if support_level == SUPPORT_LEVEL_MODERATE:
        return "The claim has partial graph or citation support, but one grounding axis is incomplete."
    if support_level == SUPPORT_LEVEL_WEAK:
        return "Only weak grounding is available, usually citation-only or evidence-only support."
    return "No reliable evidence, citation, or witness grounding is available."


def _match_evidence_records(
    claim: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    evidence_ids = set(_string_list(claim.get("evidence_ids")))
    if evidence_ids:
        return [
            _as_dict(record)
            for record in evidence_records
            if _text(record.get("evidence_id") or record.get("id")) in evidence_ids
        ]
    source_entity = _text(claim.get("source_entity") or claim.get("source"))
    target_entity = _text(claim.get("target_entity") or claim.get("target"))
    relation_type = _text(claim.get("relation_type") or claim.get("type"))
    matched: List[Dict[str, Any]] = []
    for record in evidence_records:
        payload = _as_dict(record)
        if source_entity and source_entity != _text(
            payload.get("source_entity") or payload.get("source")
        ):
            continue
        if target_entity and target_entity != _text(
            payload.get("target_entity") or payload.get("target")
        ):
            continue
        if relation_type and relation_type != _text(
            payload.get("relation_type") or payload.get("type")
        ):
            continue
        if any((source_entity, target_entity, relation_type)):
            matched.append(payload)
    return matched


def _match_citation_records(
    source_refs: Sequence[str],
    citation_records: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not source_refs:
        return []
    source_ref_set = set(source_refs)
    matched: List[Dict[str, Any]] = []
    for citation in citation_records:
        payload = _as_dict(citation)
        candidate_refs = _collect_source_refs([payload])
        if source_ref_set.intersection(candidate_refs):
            matched.append(payload)
    return matched


def _match_citation_traces(
    source_refs: Sequence[str],
    citation_traces: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    if not source_refs:
        return []
    source_ref_set = set(source_refs)
    matched: List[Dict[str, Any]] = []
    for trace in citation_traces:
        payload = _as_dict(trace)
        trace_refs = _collect_source_refs(
            [payload, _as_dict(payload.get("traceability"))]
        )
        if source_ref_set.intersection(trace_refs):
            matched.append(payload)
    return matched


def _trace_matches_claim(trace: Mapping[str, Any], claim_id: str) -> bool:
    if not claim_id:
        return False
    payload = _as_dict(trace)
    if _trace_id(payload) == claim_id:
        return True
    citation = _as_dict(payload.get("citation"))
    if _text(citation.get("id") or citation.get("claim_id")) == claim_id:
        return True
    traceability = _as_dict(payload.get("traceability"))
    node_ids = _string_list(traceability.get("node_ids"))
    return claim_id in node_ids


def _trace_to_citation_record(trace: Mapping[str, Any]) -> Dict[str, Any]:
    payload = _as_dict(trace)
    return {
        "id": _trace_id(payload),
        "title": _text(
            payload.get("title") or payload.get("label") or payload.get("id")
        ),
        "source_ref": _text(
            payload.get("source_ref")
            or _as_dict(payload.get("traceability")).get("source_ref")
        ),
        "source_type": _text(payload.get("source_type") or "graph_trace"),
    }


def _collect_source_refs(containers: Iterable[Any]) -> List[str]:
    refs: List[str] = []
    for container in containers:
        payload = _as_dict(container)
        for key in (
            "source_ref",
            "document_urn",
            "urn",
            "doi",
            "url",
            "citation_id",
            "id",
        ):
            _append_unique(refs, payload.get(key))
        provenance = _as_dict(payload.get("provenance"))
        if provenance:
            for key in ("source_ref", "document_urn", "urn", "doi", "url"):
                _append_unique(refs, provenance.get(key))
    return refs


def _collect_witness_keys(value: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(value, Mapping):
        for field_name, field_value in value.items():
            if "witness" in str(field_name).lower():
                if isinstance(field_value, (str, int, float)):
                    _append_unique(keys, field_value)
                elif isinstance(field_value, Mapping):
                    _append_unique(keys, field_value.get("witness_key"))
                    _append_unique(keys, field_value.get("witness_urn"))
                    _append_unique(keys, field_value.get("id"))
                elif isinstance(field_value, list):
                    keys.extend(_collect_witness_keys(field_value))
            elif isinstance(field_value, (Mapping, list, tuple)):
                keys.extend(_collect_witness_keys(field_value))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.extend(_collect_witness_keys(item))
    return _dedupe_strings(keys)


def _citation_key(citation: Mapping[str, Any]) -> str:
    payload = _as_dict(citation)
    return _text(
        payload.get("citation_id")
        or payload.get("id")
        or payload.get("source_ref")
        or payload.get("doi")
        or payload.get("url")
        or payload.get("title")
    )


def _trace_id(trace: Mapping[str, Any]) -> str:
    payload = _as_dict(trace)
    traceability = _as_dict(payload.get("traceability"))
    return _text(
        payload.get("id")
        or traceability.get("node_id")
        or traceability.get("citation_record_id")
        or payload.get("source_ref")
    )


def _claim_text(claim: Mapping[str, Any]) -> str:
    explicit = _text(
        claim.get("claim_text") or claim.get("statement") or claim.get("decision_basis")
    )
    if explicit:
        return explicit
    source_entity = _text(claim.get("source_entity") or claim.get("source"))
    relation_type = _text(claim.get("relation_type") or claim.get("type") or "related")
    target_entity = _text(claim.get("target_entity") or claim.get("target"))
    return " ".join(
        item for item in (source_entity, relation_type, target_entity) if item
    )


def _dedupe_dicts(
    values: Iterable[Mapping[str, Any]],
    *,
    key_fields: Sequence[str],
) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        payload = _as_dict(value)
        identity = ""
        for field_name in key_fields:
            identity = _text(payload.get(field_name))
            if identity:
                break
        if not identity:
            identity = str(len(deduped))
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(payload)
    return deduped


def _dedupe_strings(values: Iterable[Any]) -> List[str]:
    deduped: List[str] = []
    for value in values:
        _append_unique(deduped, value)
    return deduped


def _append_unique(values: List[str], value: Any) -> None:
    text = _text(value)
    if text and text not in values:
        values.append(text)


def _string_list(value: Any) -> List[str]:
    return [_text(item) for item in _as_list(value) if _text(item)]


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "CitationEvidenceSynthesizer",
    "CitationGroundingRecord",
    "SUPPORT_LEVELS",
    "SUPPORT_LEVEL_STRONG",
    "SUPPORT_LEVEL_MODERATE",
    "SUPPORT_LEVEL_WEAK",
    "SUPPORT_LEVEL_UNSUPPORTED",
    "summarize_citation_grounding",
]
