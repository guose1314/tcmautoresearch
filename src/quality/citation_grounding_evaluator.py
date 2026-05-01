from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from src.generation.citation_evidence_synthesizer import (
    SUPPORT_LEVEL_MODERATE,
    SUPPORT_LEVEL_STRONG,
    SUPPORT_LEVEL_UNSUPPORTED,
    SUPPORT_LEVEL_WEAK,
    CitationGroundingRecord,
    summarize_citation_grounding,
)

CITATION_GROUNDING_EVALUATOR_VERSION = "citation-grounding-evaluator-v1"

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


@dataclass(frozen=True)
class MarkdownClaimBlock:
    claim_id: str
    paragraph_id: str
    text: str
    citation_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_citation_grounding(
    *,
    publish_result: Optional[Mapping[str, Any]] = None,
    report_markdown: str = "",
    grounding_records: Optional[
        Sequence[Mapping[str, Any] | CitationGroundingRecord]
    ] = None,
) -> Dict[str, Any]:
    """Evaluate whether report claims are cited and evidence-grounded."""
    publish_payload = (
        dict(publish_result or {}) if isinstance(publish_result, Mapping) else {}
    )
    markdown = str(report_markdown or "").strip() or _extract_report_markdown(
        publish_payload
    )
    claim_blocks = extract_markdown_claim_blocks(markdown)
    explicit_records = _normalize_grounding_records(
        grounding_records
        if grounding_records is not None
        else _extract_grounding_records(publish_payload)
    )
    records_by_claim = {
        str(record.get("claim_id") or "").strip(): record
        for record in explicit_records
        if str(record.get("claim_id") or "").strip()
    }

    evaluated_records: List[Dict[str, Any]] = []
    for block in claim_blocks:
        record = dict(records_by_claim.get(block.claim_id) or {})
        if record:
            record.setdefault("paragraph_id", block.paragraph_id)
            record.setdefault("claim_text", block.text)
            if not record.get("citation_keys") and block.citation_keys:
                record["citation_keys"] = list(block.citation_keys)
        else:
            support_level = (
                SUPPORT_LEVEL_WEAK if block.citation_keys else SUPPORT_LEVEL_UNSUPPORTED
            )
            record = CitationGroundingRecord(
                claim_id=block.claim_id,
                paragraph_id=block.paragraph_id,
                citation_keys=list(block.citation_keys),
                support_level=support_level,
                uncertainty_note=_default_uncertainty_note(support_level),
                claim_text=block.text,
            ).to_dict()
        evaluated_records.append(record)

    if not evaluated_records:
        evaluated_records = explicit_records

    summary = summarize_citation_grounding(evaluated_records)
    record_count = int(summary.get("record_count") or 0)
    supported_count = int(summary.get("supported_count") or 0)
    unsupported_count = int(summary.get("unsupported_count") or 0)
    support_level_counts = dict(summary.get("support_level_counts") or {})
    cited_claim_count = sum(1 for block in claim_blocks if block.citation_keys)
    citation_keys = _dedupe(
        key for block in claim_blocks for key in block.citation_keys
    )
    unsupported_claim_ids = [
        str(record.get("claim_id") or "").strip()
        for record in evaluated_records
        if str(record.get("support_level") or "").strip() == SUPPORT_LEVEL_UNSUPPORTED
    ]

    return {
        "contract_version": CITATION_GROUNDING_EVALUATOR_VERSION,
        "record_count": record_count,
        "claim_block_count": len(claim_blocks),
        "cited_claim_count": cited_claim_count,
        "uncited_claim_count": max(len(claim_blocks) - cited_claim_count, 0),
        "citation_key_count": len(citation_keys),
        "citation_keys": citation_keys,
        "supported_count": supported_count,
        "unsupported_count": unsupported_count,
        "weak_count": int(support_level_counts.get(SUPPORT_LEVEL_WEAK) or 0),
        "moderate_count": int(support_level_counts.get(SUPPORT_LEVEL_MODERATE) or 0),
        "strong_count": int(support_level_counts.get(SUPPORT_LEVEL_STRONG) or 0),
        "support_level_counts": support_level_counts,
        "citation_grounding_support_rate": _safe_rate(supported_count, record_count),
        "unsupported_rate": _safe_rate(unsupported_count, record_count),
        "unsupported_claim_ids": [item for item in unsupported_claim_ids if item],
        "claim_blocks": [block.to_dict() for block in claim_blocks],
        "grounding_records": evaluated_records,
    }


def extract_markdown_claim_blocks(markdown: str) -> List[MarkdownClaimBlock]:
    blocks: List[MarkdownClaimBlock] = []
    for index, paragraph in enumerate(_iter_markdown_paragraphs(markdown), start=1):
        if not _CLAIM_MARKER_PATTERN.search(paragraph):
            continue
        claim_id = _extract_claim_id(paragraph) or f"claim-{index}"
        citation_keys = extract_citation_keys(paragraph)
        blocks.append(
            MarkdownClaimBlock(
                claim_id=claim_id,
                paragraph_id=f"markdown:paragraph:{index}",
                text=_clean_claim_text(paragraph),
                citation_keys=citation_keys,
            )
        )
    return blocks


def extract_citation_keys(text: str) -> List[str]:
    keys: List[str] = []
    for match in _MARKDOWN_CITATION_PATTERN.finditer(str(text or "")):
        keys.extend(_split_citation_keys(match.group("keys")))
    for match in _BRACKET_CITATION_PATTERN.finditer(str(text or "")):
        keys.extend(_split_citation_keys(match.group("keys")))
    for match in _INLINE_CITATION_KEYS_PATTERN.finditer(str(text or "")):
        keys.extend(_split_citation_keys(match.group("keys")))
    return _dedupe(keys)


def _iter_markdown_paragraphs(markdown: str) -> List[str]:
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
            return _normalize_claim_id(match.group("id"))
    return ""


def _normalize_claim_id(value: Any) -> str:
    text = str(value or "").strip()
    text = text.strip(" []<>`'\"")
    if text.endswith("--"):
        text = text[:-2].strip()
    return text


def _split_citation_keys(value: Any) -> List[str]:
    keys: List[str] = []
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


def _extract_report_markdown(payload: Mapping[str, Any]) -> str:
    for key in (
        "report_markdown",
        "paper_markdown",
        "markdown_report",
        "markdown",
        "report_body",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("results", "research_artifact", "paper_context", "metadata"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _extract_report_markdown(value)
            if nested:
                return nested
    return ""


def _extract_grounding_records(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in (
        "citation_grounding_records",
        "citation_grounding",
        "grounding_records",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    for key in ("results", "research_artifact", "paper_context", "metadata"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _extract_grounding_records(value)
            if nested:
                return nested
    return []


def _normalize_grounding_records(
    records: Optional[Sequence[Mapping[str, Any] | CitationGroundingRecord]],
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in records or []:
        if isinstance(item, CitationGroundingRecord):
            normalized.append(item.to_dict())
        elif hasattr(item, "to_dict"):
            payload = item.to_dict()
            if isinstance(payload, Mapping):
                normalized.append(dict(payload))
        elif isinstance(item, Mapping):
            normalized.append(dict(item))
    return normalized


def _default_uncertainty_note(support_level: str) -> str:
    if support_level == SUPPORT_LEVEL_WEAK:
        return "The markdown claim has a citation key but no linked CitationGroundingRecord."
    return "The markdown claim has no citation key or linked CitationGroundingRecord."


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(float(numerator) / float(denominator), 6)


def _dedupe(values: Iterable[Any]) -> List[str]:
    seen: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


__all__ = [
    "CITATION_GROUNDING_EVALUATOR_VERSION",
    "MarkdownClaimBlock",
    "evaluate_citation_grounding",
    "extract_citation_keys",
    "extract_markdown_claim_blocks",
]
