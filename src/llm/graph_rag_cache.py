"""In-memory LRU cache for GraphRAG retrieval results."""

from __future__ import annotations

import copy
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional, Sequence

DEFAULT_GRAPH_RAG_CACHE_SIZE = 256


@dataclass(frozen=True)
class GraphRAGCacheKey:
    """Normalized cache key for a GraphRAG retrieval request."""

    scope: str
    query: str
    topic_keys: tuple[str, ...]
    entity_ids: tuple[str, ...]
    asset_type: str
    cycle_id: str


def build_graph_rag_cache_key(
    *,
    scope: str,
    query: str,
    topic_keys: Optional[Sequence[Any]] = None,
    entity_ids: Optional[Sequence[Any]] = None,
    asset_type: str = "",
    cycle_id: Optional[str] = None,
) -> GraphRAGCacheKey:
    """Build a stable key from the request dimensions that affect retrieval."""

    return GraphRAGCacheKey(
        scope=str(scope or "").strip().lower(),
        query=str(query or ""),
        topic_keys=_normalize_sequence(topic_keys),
        entity_ids=_normalize_sequence(entity_ids),
        asset_type=str(asset_type or "").strip().lower(),
        cycle_id=str(cycle_id or "").strip(),
    )


class GraphRAGMemoryCache:
    """Small process-local LRU cache returning deep copies on get/put."""

    def __init__(self, max_size: int = DEFAULT_GRAPH_RAG_CACHE_SIZE) -> None:
        try:
            normalized_size = int(max_size)
        except (TypeError, ValueError):
            normalized_size = DEFAULT_GRAPH_RAG_CACHE_SIZE
        self.max_size = max(0, normalized_size)
        self._items: OrderedDict[GraphRAGCacheKey, Any] = OrderedDict()

    def get(self, key: GraphRAGCacheKey) -> Any:
        if self.max_size <= 0 or key not in self._items:
            return None
        value = self._items.pop(key)
        self._items[key] = value
        return copy.deepcopy(value)

    def put(self, key: GraphRAGCacheKey, value: Any) -> None:
        if self.max_size <= 0:
            return
        if key in self._items:
            self._items.pop(key)
        self._items[key] = copy.deepcopy(value)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


def _normalize_sequence(values: Optional[Sequence[Any]]) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(str(item).strip() for item in values if str(item).strip())


__all__ = [
    "DEFAULT_GRAPH_RAG_CACHE_SIZE",
    "GraphRAGCacheKey",
    "GraphRAGMemoryCache",
    "build_graph_rag_cache_key",
]
