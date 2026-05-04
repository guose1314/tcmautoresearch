"""Synthesize structured evidence packages for hypotheses and relations."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

CITATION_EVIDENCE_SYNTHESIZER_VERSION = "citation-evidence-synthesizer-v1"

_ACCEPTED_STATUSES = {"accepted", "approved", "reviewed", "verified"}
_REJECTED_STATUSES = {"rejected", "contradicted", "unsupported"}
_UNCERTAIN_STATUSES = {"pending", "needs_review", "needs_source", "candidate"}


@dataclass(frozen=True)
class CitationEvidencePackage:
    package_id: str
    target_type: str
    target_id: str
    target_text: str
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    contradicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    uncertain_evidence: list[dict[str, Any]] = field(default_factory=list)
    missing_evidence: list[dict[str, Any]] = field(default_factory=list)
    evidence_status: str = "insufficient"
    conclusion_status: str = "candidate_observation"
    needs_review: bool = True
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = CITATION_EVIDENCE_SYNTHESIZER_VERSION
        return payload


class CitationEvidenceSynthesizer:
    """Aggregate text provenance, KG traces, versions, and review feedback."""

    def synthesize(
        self,
        target: Mapping[str, Any],
        *,
        text_segments: Optional[Sequence[Mapping[str, Any]]] = None,
        entities: Optional[Sequence[Mapping[str, Any]]] = None,
        relationships: Optional[Sequence[Mapping[str, Any]]] = None,
        version_info: Optional[Sequence[Mapping[str, Any]]] = None,
        expert_feedback: Optional[Sequence[Mapping[str, Any]]] = None,
        graph_rag_results: Optional[Sequence[Mapping[str, Any]]] = None,
        evidence_protocol: Optional[Mapping[str, Any]] = None,
    ) -> CitationEvidencePackage:
        target_payload = dict(target or {})
        target_type = _target_type(target_payload)
        target_id = _target_id(target_payload, target_type)
        target_text = _target_text(target_payload)
        terms = _target_terms(target_payload, target_text)

        supporting: list[dict[str, Any]] = []
        contradicting: list[dict[str, Any]] = []
        uncertain: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []

        for segment in text_segments or []:
            if isinstance(segment, Mapping) and _matches_terms(segment, terms):
                supporting.append(_evidence_item("text_segment", segment, target_id))
        for entity in entities or []:
            if isinstance(entity, Mapping) and _matches_terms(entity, terms):
                bucket = _bucket_for_status(entity)
                _append_bucket(
                    bucket,
                    supporting,
                    contradicting,
                    uncertain,
                    entity,
                    target_id,
                    "entity",
                )
        for relation in relationships or []:
            if isinstance(relation, Mapping) and _matches_terms(relation, terms):
                bucket = _bucket_for_status(relation)
                _append_bucket(
                    bucket,
                    supporting,
                    contradicting,
                    uncertain,
                    relation,
                    target_id,
                    "relationship",
                )
        for version in version_info or []:
            if isinstance(version, Mapping) and _matches_terms(version, terms):
                bucket = _bucket_for_status(version)
                _append_bucket(
                    bucket,
                    supporting,
                    contradicting,
                    uncertain,
                    version,
                    target_id,
                    "version",
                )
        for feedback in expert_feedback or []:
            if isinstance(feedback, Mapping) and _matches_terms(feedback, terms):
                bucket = _bucket_for_status(feedback)
                _append_bucket(
                    bucket,
                    supporting,
                    contradicting,
                    uncertain,
                    feedback,
                    target_id,
                    "expert_feedback",
                )
        for item in _evidence_from_protocol(evidence_protocol):
            if _matches_terms(item, terms) or _matches_target_id(item, target_id):
                bucket = _bucket_for_status(item)
                _append_bucket(
                    bucket,
                    supporting,
                    contradicting,
                    uncertain,
                    item,
                    target_id,
                    "evidence_protocol",
                )
        for item in _evidence_from_graph_rag(graph_rag_results):
            if _matches_terms(item, terms) or _matches_target_id(item, target_id):
                bucket = _bucket_for_status(item)
                _append_bucket(
                    bucket,
                    supporting,
                    contradicting,
                    uncertain,
                    item,
                    target_id,
                    "graph_rag",
                )

        supporting = _dedupe_evidence(supporting)
        contradicting = _dedupe_evidence(contradicting)
        uncertain = _dedupe_evidence(uncertain)
        if not supporting:
            missing.append(
                {
                    "target_id": target_id,
                    "target_type": target_type,
                    "reason": "no_supporting_evidence",
                    "terms": terms,
                }
            )
        evidence_status, conclusion_status = _resolve_statuses(
            supporting, contradicting, uncertain, missing
        )
        package_id = _stable_package_id(target_type, target_id, target_text)
        return CitationEvidencePackage(
            package_id=package_id,
            target_type=target_type,
            target_id=target_id,
            target_text=target_text,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            uncertain_evidence=uncertain,
            missing_evidence=missing,
            evidence_status=evidence_status,
            conclusion_status=conclusion_status,
            needs_review=bool(missing or contradicting or uncertain),
            summary={
                "supporting_count": len(supporting),
                "contradicting_count": len(contradicting),
                "uncertain_count": len(uncertain),
                "missing_count": len(missing),
            },
        )

    def synthesize_many(
        self,
        targets: Iterable[Mapping[str, Any]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return [
            self.synthesize(target, **kwargs).to_dict()
            for target in targets or []
            if isinstance(target, Mapping)
        ]


def synthesize_citation_evidence_package(
    target: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    return CitationEvidenceSynthesizer().synthesize(target, **kwargs).to_dict()


def _target_type(target: Mapping[str, Any]) -> str:
    if target.get("hypothesis_id") or target.get("claim") or target.get("claim_text"):
        return "hypothesis"
    if any(key in target for key in ("source", "target", "relation", "relation_type")):
        return "relation"
    return str(target.get("target_type") or target.get("type") or "claim").strip()


def _target_id(target: Mapping[str, Any], target_type: str) -> str:
    for key in ("claim_id", "hypothesis_id", "relationship_id", "id", "target_id"):
        value = str(target.get(key) or "").strip()
        if value:
            return value
    if target_type == "relation":
        return (
            ":".join(
                str(target.get(key) or "").strip()
                for key in ("source", "relation", "relation_type", "target")
                if str(target.get(key) or "").strip()
            )
            or "relation"
        )
    return _stable_package_id(target_type, "", _target_text(target))


def _target_text(target: Mapping[str, Any]) -> str:
    for key in ("claim_text", "claim", "title", "description", "decision_basis"):
        value = str(target.get(key) or "").strip()
        if value:
            return value
    source = _plain_name(target.get("source") or target.get("source_entity"))
    relation = str(
        target.get("relation")
        or target.get("relation_type")
        or target.get("type")
        or ""
    ).strip()
    target_name = _plain_name(target.get("target") or target.get("target_entity"))
    return " ".join(part for part in (source, relation, target_name) if part)


def _target_terms(target: Mapping[str, Any], target_text: str) -> list[str]:
    terms = []
    for key in ("source", "source_entity", "target", "target_entity", "name"):
        text = _plain_name(target.get(key))
        if text:
            terms.append(text)
    if not terms:
        terms.extend(_tokenize_terms(target_text)[:6])
    return _dedupe_text(terms)


def _matches_terms(item: Mapping[str, Any], terms: Sequence[str]) -> bool:
    if not terms:
        return False
    haystack = _flatten_text(item)
    normalized = _compact(haystack)
    if not normalized:
        return False
    matched = sum(
        1 for term in terms if _compact(term) and _compact(term) in normalized
    )
    required = len(terms) if len(terms) <= 2 else 2
    return matched >= required


def _matches_target_id(item: Mapping[str, Any], target_id: str) -> bool:
    if not target_id:
        return False
    normalized = _compact(target_id)
    for key in ("claim_id", "hypothesis_id", "evidence_id", "id", "target_id"):
        if _compact(item.get(key)) == normalized:
            return True
    for key in ("evidence_ids", "evidence_claim_ids", "node_ids"):
        values = item.get(key)
        if isinstance(values, list) and normalized in {
            _compact(value) for value in values
        }:
            return True
    return False


def _append_bucket(
    bucket: str,
    supporting: list[dict[str, Any]],
    contradicting: list[dict[str, Any]],
    uncertain: list[dict[str, Any]],
    payload: Mapping[str, Any],
    target_id: str,
    source_type: str,
) -> None:
    item = _evidence_item(source_type, payload, target_id)
    if bucket == "contradicting":
        contradicting.append(item)
    elif bucket == "uncertain":
        uncertain.append(item)
    else:
        supporting.append(item)


def _bucket_for_status(item: Mapping[str, Any]) -> str:
    status = (
        str(
            item.get("review_status")
            or item.get("expert_review_status")
            or item.get("status")
            or item.get("support_level")
            or item.get("verdict")
            or ""
        )
        .strip()
        .lower()
    )
    if status in _REJECTED_STATUSES:
        return "contradicting"
    if status in _UNCERTAIN_STATUSES:
        return "uncertain"
    if status in _ACCEPTED_STATUSES or status in {
        "strong",
        "moderate",
        "weak",
        "supported",
    }:
        return "supporting"
    if item.get("expert_reviewed") is True or item.get("has_text_evidence") is True:
        return "supporting"
    return "supporting"


def _evidence_item(
    source_type: str, payload: Mapping[str, Any], target_id: str
) -> dict[str, Any]:
    text = _first_text(
        payload,
        "quote_text",
        "excerpt",
        "claim_text",
        "body",
        "title",
        "description",
        "text",
    )
    if not text:
        text = _flatten_text(payload)[:500]
    return {
        "source_type": source_type,
        "target_id": target_id,
        "evidence_id": _first_text(
            payload, "evidence_id", "claim_id", "id", "segment_id", "source_ref"
        ),
        "text": text,
        "confidence": _confidence(payload),
        "expert_reviewed": bool(
            payload.get("expert_reviewed")
            or _bucket_for_status(payload) == "supporting"
        ),
        "source": _first_text(payload, "source", "source_ref", "document_id", "tier"),
        "payload": dict(payload),
    }


def _evidence_from_protocol(
    evidence_protocol: Optional[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    protocol = (
        dict(evidence_protocol or {}) if isinstance(evidence_protocol, Mapping) else {}
    )
    items: list[dict[str, Any]] = []
    for key in ("evidence_records", "claims", "citation_records"):
        values = protocol.get(key)
        if isinstance(values, list):
            items.extend(dict(item) for item in values if isinstance(item, Mapping))
    return items


def _evidence_from_graph_rag(
    results: Optional[Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for result in results or []:
        if not isinstance(result, Mapping):
            continue
        for item in result.get("items") or []:
            if isinstance(item, Mapping):
                payload = dict(item)
                payload.setdefault("source", "tiered_graph_rag")
                items.append(payload)
        for citation in result.get("citations") or []:
            if isinstance(citation, Mapping):
                items.append({**dict(citation), "source": "graph_rag_citation"})
        traces = (
            result.get("traces") if isinstance(result.get("traces"), Mapping) else {}
        )
        for trace_items in dict(traces).values():
            if isinstance(trace_items, list):
                items.extend(
                    dict(item) for item in trace_items if isinstance(item, Mapping)
                )
        if result.get("body"):
            items.append(
                {
                    "body": result.get("body"),
                    "source": "graph_rag_body",
                    "confidence": 0.7,
                }
            )
    return items


def _resolve_statuses(
    supporting: Sequence[Mapping[str, Any]],
    contradicting: Sequence[Mapping[str, Any]],
    uncertain: Sequence[Mapping[str, Any]],
    missing: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    if contradicting:
        return "contested", "candidate_observation"
    if not supporting or missing:
        return "insufficient", "candidate_observation"
    if uncertain:
        return "partially_supported", "candidate_observation"
    return "supported", "formal_conclusion"


def _dedupe_evidence(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            str(item.get("source_type") or ""),
            str(item.get("evidence_id") or ""),
            _compact(item.get("text")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(item))
    return deduped


def _stable_package_id(target_type: str, target_id: str, target_text: str) -> str:
    seed = "|".join((target_type, target_id, target_text))
    digest = hashlib.sha1(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"evidence-package:{digest}"


def _first_text(item: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (Mapping, list, tuple)):
            text = str(value).strip()
            if text:
                return text
    nested = (
        item.get("attributes") if isinstance(item.get("attributes"), Mapping) else {}
    )
    return _first_text(nested, *keys) if nested else ""


def _flatten_text(value: Any) -> str:
    if isinstance(value, Mapping):
        parts = []
        for item in value.values():
            if isinstance(item, (Mapping, list, tuple)):
                parts.append(_flatten_text(item))
            else:
                parts.append(str(item or ""))
        return " ".join(part for part in parts if part)
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_text(item) for item in value)
    return str(value or "")


def _plain_name(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if ":" in text else text


def _tokenize_terms(text: str) -> list[str]:
    raw = str(text or "")
    terms = []
    current = ""
    for char in raw:
        if "\u4e00" <= char <= "\u9fff":
            current += char
            if len(current) >= 2:
                terms.append(current)
                current = ""
        else:
            current = ""
    return _dedupe_text(terms)


def _dedupe_text(values: Iterable[Any]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _compact(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _confidence(item: Mapping[str, Any]) -> float:
    for key in ("confidence", "score", "weight"):
        if item.get(key) in (None, ""):
            continue
        try:
            return max(0.0, min(1.0, float(item.get(key))))
        except (TypeError, ValueError):
            continue
    return 0.5


__all__ = [
    "CITATION_EVIDENCE_SYNTHESIZER_VERSION",
    "CitationEvidencePackage",
    "CitationEvidenceSynthesizer",
    "synthesize_citation_evidence_package",
]
