"""Paragraph-level evidence provenance for extracted research assets."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from typing import Any, Iterable, Mapping, Optional, Sequence

TEXT_SEGMENT_PROVENANCE_VERSION = "text-segment-provenance-v1"


@dataclass(frozen=True)
class TextSegmentProvenance:
    """A source text span that supports an entity, relation, topic, or hypothesis."""

    document_id: str
    segment_id: str
    char_start: int
    char_end: int
    line_start: int
    line_end: int
    quote_text: str
    normalization_hash: str

    def with_document_id(self, document_id: str) -> "TextSegmentProvenance":
        return replace(self, document_id=str(document_id or ""))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = TEXT_SEGMENT_PROVENANCE_VERSION
        return payload


class TextSegmentIndex:
    """Build and query bounded source text segments without changing the text."""

    def __init__(
        self, raw_text: str, *, document_id: str = "", max_segment_chars: int = 900
    ):
        self.raw_text = str(raw_text or "")
        self.document_id = str(document_id or "")
        self.max_segment_chars = max(120, int(max_segment_chars or 900))
        self.segments = self._build_segments()

    def find_for_span(
        self, start: Any, end: Any = None
    ) -> Optional[TextSegmentProvenance]:
        try:
            char_start = max(0, int(start))
            char_end = max(char_start, int(end if end is not None else char_start + 1))
        except (TypeError, ValueError):
            return None
        for segment in self.segments:
            if segment.char_start <= char_start < segment.char_end:
                return segment
            if segment.char_start < char_end <= segment.char_end:
                return segment
        return None

    def find_for_quote(self, quote: Any) -> Optional[TextSegmentProvenance]:
        text = str(quote or "").strip()
        if not text:
            return None
        position = self.raw_text.find(text)
        if position >= 0:
            return self.find_for_span(position, position + len(text))
        normalized_quote = _normalize_for_match(text)
        if not normalized_quote:
            return None
        for segment in self.segments:
            if normalized_quote in _normalize_for_match(segment.quote_text):
                return segment
        return None

    def find_for_terms(self, *terms: Any) -> Optional[TextSegmentProvenance]:
        normalized_terms = [
            str(term or "").strip() for term in terms if str(term or "").strip()
        ]
        if not normalized_terms:
            return None

        best_segment: Optional[TextSegmentProvenance] = None
        best_score = -1
        for segment in self.segments:
            quote = segment.quote_text
            score = sum(1 for term in normalized_terms if term in quote)
            if score > best_score:
                best_score = score
                best_segment = segment
            if score == len(normalized_terms):
                return segment
        if best_score > 0:
            return best_segment

        first_term = normalized_terms[0]
        return self.find_for_quote(first_term)

    def provenance_dicts_for_terms(self, *terms: Any) -> list[dict[str, Any]]:
        segment = self.find_for_terms(*terms)
        return [segment.to_dict()] if segment is not None else []

    def _build_segments(self) -> list[TextSegmentProvenance]:
        if not self.raw_text:
            return []

        line_spans = _line_spans(self.raw_text)
        segments: list[TextSegmentProvenance] = []
        current_start: Optional[int] = None
        current_end = 0
        current_line_start = 1
        current_line_end = 1

        def flush() -> None:
            nonlocal current_start, current_end, current_line_start, current_line_end
            if current_start is None or current_end <= current_start:
                current_start = None
                return
            quote_text = self.raw_text[current_start:current_end].strip()
            if quote_text:
                segment_index = len(segments) + 1
                segments.append(
                    TextSegmentProvenance(
                        document_id=self.document_id,
                        segment_id=f"seg_{segment_index:06d}",
                        char_start=current_start,
                        char_end=current_end,
                        line_start=current_line_start,
                        line_end=current_line_end,
                        quote_text=quote_text,
                        normalization_hash=_normalization_hash(quote_text),
                    )
                )
            current_start = None

        for line_no, line_start, line_end, line_text in line_spans:
            stripped = line_text.strip()
            if not stripped:
                flush()
                continue
            if current_start is None:
                current_start = line_start
                current_line_start = line_no
            current_end = line_end
            current_line_end = line_no
            if current_end - current_start >= self.max_segment_chars:
                flush()

        flush()
        if segments:
            return segments
        quote_text = self.raw_text.strip()
        if not quote_text:
            return []
        return [
            TextSegmentProvenance(
                document_id=self.document_id,
                segment_id="seg_000001",
                char_start=0,
                char_end=len(self.raw_text),
                line_start=1,
                line_end=max(1, self.raw_text.count("\n") + 1),
                quote_text=quote_text,
                normalization_hash=_normalization_hash(quote_text),
            )
        ]


def attach_provenance_to_entities(
    entities: Iterable[Mapping[str, Any]],
    index: TextSegmentIndex,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for entity in entities or []:
        item = dict(entity)
        provenance = _existing_provenance(item)
        if not provenance:
            segment = index.find_for_span(
                item.get("position"), item.get("end_position")
            )
            if segment is None:
                name = item.get("name") or item.get("text") or item.get("value")
                segment = index.find_for_quote(name)
            if segment is not None:
                provenance = [segment.to_dict()]
        if provenance:
            item["provenance"] = provenance
            metadata = dict(item.get("metadata") or {})
            metadata.setdefault("provenance", provenance)
            item["metadata"] = metadata
        enriched.append(item)
    return enriched


def attach_provenance_to_edges(
    edges: Iterable[Mapping[str, Any]],
    index: TextSegmentIndex,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for edge in edges or []:
        item = dict(edge)
        provenance = _existing_provenance(item)
        if not provenance:
            source = _plain_name(item.get("source") or item.get("from"))
            target = _plain_name(item.get("target") or item.get("to"))
            relation = item.get("relation") or item.get("rel_type") or item.get("label")
            attrs = (
                item.get("attributes")
                if isinstance(item.get("attributes"), Mapping)
                else {}
            )
            relation = (
                relation
                or attrs.get("relationship_type")
                or attrs.get("relationship_name")
            )
            segment = index.find_for_terms(source, target)
            if segment is None:
                segment = index.find_for_terms(source) or index.find_for_terms(
                    target, relation
                )
            if segment is not None:
                provenance = [segment.to_dict()]
        if provenance:
            item["provenance"] = provenance
            if not item.get("evidence"):
                item["evidence"] = str(provenance[0].get("quote_text") or "")
            attrs = dict(item.get("attributes") or {})
            attrs.setdefault("provenance", provenance)
            item["attributes"] = attrs
        enriched.append(item)
    return enriched


def attach_provenance_to_research_view(
    research_view: Mapping[str, Any],
    index: TextSegmentIndex,
) -> dict[str, Any]:
    view = dict(research_view or {})
    view["community_topics"] = [
        _attach_item_provenance(
            item,
            index,
            terms=[
                *(item.get("member_names") or []),
                *(item.get("hub_entities") or []),
                item.get("label"),
            ],
        )
        for item in list(view.get("community_topics") or [])
        if isinstance(item, Mapping)
    ]
    view["novelty_candidates"] = [
        _attach_item_provenance(
            item,
            index,
            terms=[
                item.get("source"),
                item.get("target"),
                item.get("relation"),
                item.get("reason"),
            ],
        )
        for item in list(view.get("novelty_candidates") or [])
        if isinstance(item, Mapping)
    ]
    hypothesis_items = view.get("hypotheses") or view.get("hypothesis_candidates") or []
    enriched_hypotheses = [
        _attach_item_provenance(
            item,
            index,
            terms=[
                item.get("source"),
                item.get("target"),
                item.get("claim"),
                item.get("reason"),
            ],
        )
        for item in list(hypothesis_items)
        if isinstance(item, Mapping)
    ]
    if enriched_hypotheses:
        view["hypotheses"] = enriched_hypotheses
        view["hypothesis_candidates"] = enriched_hypotheses
    view["salient_relations"] = [
        _attach_item_provenance(
            item,
            index,
            terms=[item.get("source"), item.get("target"), item.get("relation")],
        )
        for item in list(view.get("salient_relations") or [])
        if isinstance(item, Mapping)
    ]
    return view


def _attach_item_provenance(
    item: Mapping[str, Any],
    index: TextSegmentIndex,
    *,
    terms: Sequence[Any],
) -> dict[str, Any]:
    payload = dict(item)
    if _existing_provenance(payload):
        return payload
    segment = index.find_for_terms(*terms)
    if segment is not None:
        payload["provenance"] = [segment.to_dict()]
    return payload


def _existing_provenance(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    direct = item.get("provenance")
    if isinstance(direct, list):
        return [dict(value) for value in direct if isinstance(value, Mapping)]
    attrs = (
        item.get("attributes") if isinstance(item.get("attributes"), Mapping) else {}
    )
    nested = attrs.get("provenance")
    if isinstance(nested, list):
        return [dict(value) for value in nested if isinstance(value, Mapping)]
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    nested = metadata.get("provenance")
    if isinstance(nested, list):
        return [dict(value) for value in nested if isinstance(value, Mapping)]
    return []


def _line_spans(text: str) -> list[tuple[int, int, int, str]]:
    spans: list[tuple[int, int, int, str]] = []
    offset = 0
    for line_no, line in enumerate(text.splitlines(keepends=True), start=1):
        start = offset
        offset += len(line)
        spans.append((line_no, start, offset, line))
    if not spans and text:
        spans.append((1, 0, len(text), text))
    return spans


def _plain_name(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if ":" in text else text


def _normalize_for_match(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", text)


def _normalization_hash(value: str) -> str:
    normalized = _normalize_for_match(value)
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()
