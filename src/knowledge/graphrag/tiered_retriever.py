"""Four-tier GraphRAG retrieval with evidence-priority prompt ordering."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Sequence

TIERED_GRAPHRAG_RETRIEVER_VERSION = "tiered-graphrag-retriever-v1"
RETRIEVAL_TIERS = ("literature", "segment", "entity_relation", "expert_insight")
PROMPT_PRIORITY = ("expert_insight", "entity_relation", "segment", "literature")

_TIER_DEFAULT_CONFIDENCE = {
    "literature": 0.62,
    "segment": 0.72,
    "entity_relation": 0.8,
    "expert_insight": 0.9,
}
_EXPERT_REVIEWED_STATUSES = {"accepted", "approved", "reviewed", "verified"}


@dataclass(frozen=True)
class TieredRetrievalItem:
    tier: str
    source: str
    body: str
    confidence: float
    expert_reviewed: bool
    citations: list[dict[str, Any]] = field(default_factory=list)
    traceability: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = TIERED_GRAPHRAG_RETRIEVER_VERSION
        return payload


@dataclass(frozen=True)
class TieredRetrievalResult:
    query: str
    body: str
    items: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    traceability: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0
    truncated: bool = False
    scope: str = "tiered"
    asset_type: str = "tiered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": TIERED_GRAPHRAG_RETRIEVER_VERSION,
            "scope": self.scope,
            "asset_type": self.asset_type,
            "query": self.query,
            "body": self.body,
            "items": list(self.items),
            "citations": list(self.citations),
            "traceability": dict(self.traceability),
            "metadata": dict(self.metadata),
            "token_count": self.token_count,
            "truncated": self.truncated,
        }


class TieredGraphRAGRetriever:
    """Run literature, segment, KG, and expert-insight retrieval layers."""

    def __init__(
        self, *, base_retriever: Any, cache: Optional[dict[str, dict[str, Any]]] = None
    ) -> None:
        if base_retriever is None:
            raise ValueError("base_retriever is required")
        self._base = base_retriever
        self._cache = cache if cache is not None else {}

    def retrieve(
        self,
        query: str,
        *,
        topic_keys: Optional[Sequence[str]] = None,
        entity_ids: Optional[Sequence[str]] = None,
        cycle_id: Optional[str] = None,
        weight_hints: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> TieredRetrievalResult:
        cache_key = self._cache_key(
            query, topic_keys, entity_ids, cycle_id, weight_hints
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return _result_from_dict(copy.deepcopy(cached))

        items = [
            self._retrieve_tier(
                "literature",
                "community" if topic_keys else "global",
                query,
                topic_keys=topic_keys,
                entity_ids=None,
                asset_type="catalog",
                cycle_id=cycle_id,
            ),
            self._retrieve_tier(
                "segment",
                "local",
                query,
                entity_ids=entity_ids,
                asset_type="evidence",
                cycle_id=cycle_id,
            ),
            self._retrieve_tier(
                "entity_relation",
                "local",
                query,
                entity_ids=entity_ids,
                asset_type=None,
                cycle_id=cycle_id,
                weight_hints=weight_hints,
            ),
            self._retrieve_tier(
                "expert_insight",
                "local",
                query,
                entity_ids=entity_ids,
                asset_type="claim",
                cycle_id=cycle_id,
                weight_hints=weight_hints,
            ),
        ]
        result_items = [item.to_dict() for item in items if item.body or item.citations]
        body = self._build_prompt_body(result_items)
        citations = _dedupe_citations(
            citation
            for item in result_items
            for citation in item.get("citations", [])
            if isinstance(citation, Mapping)
        )
        traceability = _build_traceability(result_items)
        result = TieredRetrievalResult(
            query=str(query or ""),
            body=body,
            items=result_items,
            citations=citations,
            traceability=traceability,
            metadata={
                "retrieval_policy": "expert_reviewed_first_then_high_confidence_kg_then_candidate_insight",
                "tiers": list(RETRIEVAL_TIERS),
                "prompt_priority": list(PROMPT_PRIORITY),
                "cacheable": True,
                "persistable_trace": True,
            },
            token_count=max(1, (len(body) + 1) // 2) if body else 0,
            truncated=any(
                bool(item.get("metadata", {}).get("truncated")) for item in result_items
            ),
        )
        self._cache[cache_key] = result.to_dict()
        return result

    def _retrieve_tier(
        self,
        tier: str,
        scope: str,
        query: str,
        *,
        topic_keys: Optional[Sequence[str]] = None,
        entity_ids: Optional[Sequence[str]] = None,
        asset_type: Optional[str] = None,
        cycle_id: Optional[str] = None,
        weight_hints: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> TieredRetrievalItem:
        try:
            raw = self._base.retrieve(
                scope,
                query,
                topic_keys=topic_keys,
                entity_ids=entity_ids,
                asset_type=asset_type,
                cycle_id=cycle_id,
                weight_hints=weight_hints,
            )
        except TypeError:
            raw = self._base.retrieve(
                scope,
                query,
                topic_keys=topic_keys,
                entity_ids=entity_ids,
                asset_type=asset_type,
                cycle_id=cycle_id,
            )
        except Exception as exc:  # noqa: BLE001
            return TieredRetrievalItem(
                tier=tier,
                source=f"graph_rag:{asset_type or scope}",
                body="",
                confidence=0.0,
                expert_reviewed=False,
                metadata={"status": "degraded", "error": str(exc)},
            )
        payload = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw or {})
        citations = [
            dict(item)
            for item in payload.get("citations") or []
            if isinstance(item, Mapping)
        ]
        reviewed = tier == "expert_insight" or any(
            _citation_reviewed(item) for item in citations
        )
        confidence = _confidence_from_payload(tier, payload, citations)
        return TieredRetrievalItem(
            tier=tier,
            source=f"graph_rag:{asset_type or scope}",
            body=str(payload.get("body") or ""),
            confidence=confidence,
            expert_reviewed=reviewed,
            citations=[
                {**item, "tier": tier, "source": f"graph_rag:{asset_type or scope}"}
                for item in citations
            ],
            traceability=dict(payload.get("traceability") or {}),
            metadata={
                "scope": payload.get("scope") or scope,
                "asset_type": payload.get("asset_type") or asset_type or "",
                "token_count": int(payload.get("token_count") or 0),
                "truncated": bool(payload.get("truncated", False)),
                **(
                    dict(payload.get("metadata") or {})
                    if isinstance(payload.get("metadata"), Mapping)
                    else {}
                ),
            },
        )

    def _build_prompt_body(self, items: Sequence[Mapping[str, Any]]) -> str:
        ordered: list[Mapping[str, Any]] = []
        for tier in PROMPT_PRIORITY:
            tier_items = [item for item in items if item.get("tier") == tier]
            tier_items.sort(
                key=lambda item: (
                    not bool(item.get("expert_reviewed")),
                    -float(item.get("confidence") or 0.0),
                )
            )
            ordered.extend(tier_items)
        parts = []
        for item in ordered:
            body = str(item.get("body") or "").strip()
            if not body:
                continue
            parts.append(
                f"[{item.get('tier')}] reviewed={bool(item.get('expert_reviewed'))} "
                f"confidence={float(item.get('confidence') or 0.0):.3f}\n{body}"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _cache_key(
        query: str,
        topic_keys: Optional[Sequence[str]],
        entity_ids: Optional[Sequence[str]],
        cycle_id: Optional[str],
        weight_hints: Optional[Sequence[Mapping[str, Any]]],
    ) -> str:
        payload = {
            "query": str(query or ""),
            "topic_keys": [str(item) for item in topic_keys or []],
            "entity_ids": [str(item) for item in entity_ids or []],
            "cycle_id": str(cycle_id or ""),
            "weight_hints": [
                dict(item) for item in weight_hints or [] if isinstance(item, Mapping)
            ],
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _result_from_dict(payload: Mapping[str, Any]) -> TieredRetrievalResult:
    return TieredRetrievalResult(
        query=str(payload.get("query") or ""),
        body=str(payload.get("body") or ""),
        items=[
            dict(item)
            for item in payload.get("items") or []
            if isinstance(item, Mapping)
        ],
        citations=[
            dict(item)
            for item in payload.get("citations") or []
            if isinstance(item, Mapping)
        ],
        traceability=dict(payload.get("traceability") or {}),
        metadata=dict(payload.get("metadata") or {}),
        token_count=int(payload.get("token_count") or 0),
        truncated=bool(payload.get("truncated", False)),
        scope=str(payload.get("scope") or "tiered"),
        asset_type=str(payload.get("asset_type") or "tiered"),
    )


def _build_traceability(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    node_ids: list[str] = []
    relationship_ids: list[str] = []
    tier_trace: list[dict[str, Any]] = []
    for item in items:
        trace = (
            item.get("traceability")
            if isinstance(item.get("traceability"), Mapping)
            else {}
        )
        for value in trace.get("node_ids") or []:
            _append_unique(node_ids, value)
        for value in trace.get("relationship_ids") or []:
            _append_unique(relationship_ids, value)
        tier_trace.append(
            {
                "tier": item.get("tier"),
                "source": item.get("source"),
                "confidence": item.get("confidence"),
                "expert_reviewed": item.get("expert_reviewed"),
                "node_ids": list(trace.get("node_ids") or []),
                "relationship_ids": list(trace.get("relationship_ids") or []),
            }
        )
    return {
        "node_ids": node_ids,
        "relationship_ids": relationship_ids,
        "tiers": tier_trace,
        "persistable": True,
        "contract_version": TIERED_GRAPHRAG_RETRIEVER_VERSION,
    }


def _dedupe_citations(values: Any) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        item = dict(value)
        key = (
            str(item.get("tier") or ""),
            str(item.get("type") or ""),
            str(item.get("id") or item.get("topic_key") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        citations.append(item)
    return citations


def _citation_reviewed(item: Mapping[str, Any]) -> bool:
    status = str(item.get("review_status") or item.get("status") or "").strip().lower()
    return bool(
        item.get("expert_reviewed") is True or status in _EXPERT_REVIEWED_STATUSES
    )


def _confidence_from_payload(
    tier: str,
    payload: Mapping[str, Any],
    citations: Sequence[Mapping[str, Any]],
) -> float:
    candidates = [payload.get("confidence"), payload.get("score")]
    candidates.extend(item.get("confidence") or item.get("score") for item in citations)
    for value in candidates:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        return max(0.0, min(1.0, number))
    return _TIER_DEFAULT_CONFIDENCE.get(tier, 0.5)


def _append_unique(items: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


__all__ = [
    "PROMPT_PRIORITY",
    "RETRIEVAL_TIERS",
    "TIERED_GRAPHRAG_RETRIEVER_VERSION",
    "TieredGraphRAGRetriever",
    "TieredRetrievalItem",
    "TieredRetrievalResult",
]
