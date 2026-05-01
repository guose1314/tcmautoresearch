"""GraphRAG — 三档（global / community / local）摘要检索。

T5.5 设计：

- ``global``：全库 :class:`CommunitySummary` 节点拼接，作为研究主题级背景。
- ``community``：按 ``topic_keys`` 过滤的社区级摘要，对应 Topic 子社区。
- ``local``：以 ``entity_ids`` 为种子的 1-hop 子图，渲染成简短文本。
- ``asset_type``：在三档 scope 之内增加研究资产过滤，支持 hypothesis / evidence /
    catalog / witness / claim，并返回 traceability。

调用契约::

    rag = GraphRAG(neo4j_driver=driver, token_budget=8000)
    result = rag.retrieve("community", query="麻仁润肠", topic_keys=["t-1"])
    result.body          # 拼接后的纯文本
    result.token_count   # ≈ 字符长度 / 4，便于 4060 8GB 单 query ≤ 8k 守门
    result.scope         # "community"
    result.citations     # [{"type": "CommunitySummary", "topic_key": "t-1"}]

向后兼容：driver 缺失或异常时静默降级为空 :class:`RetrievalResult`，方便单测注入 mock。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from src.llm.graph_rag_cache import (
    DEFAULT_GRAPH_RAG_CACHE_SIZE,
    GraphRAGMemoryCache,
    build_graph_rag_cache_key,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 公共契约
# ---------------------------------------------------------------------------

VALID_QUESTION_TYPES = ("global", "community", "local")
VALID_ASSET_TYPES = ("hypothesis", "evidence", "catalog", "witness", "claim")
DEFAULT_TOKEN_BUDGET = 8000  # 4060 8GB 单 query 守门

_ASSET_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    "hypothesis": {
        "label": "Hypothesis",
        "source_phase": "hypothesis",
        "query_fields": ("hypothesis_id", "title", "description", "domain"),
        "summary_fields": ("title", "description", "status"),
    },
    "evidence": {
        "label": "Evidence",
        "source_phase": "analyze",
        "query_fields": (
            "evidence_id",
            "title",
            "excerpt",
            "source_entity",
            "target_entity",
            "document_title",
            "work_title",
        ),
        "summary_fields": ("title", "excerpt", "evidence_grade", "confidence"),
    },
    "catalog": {
        "label": "Catalog",
        "source_phase": "observe",
        "query_fields": ("catalog_id", "title", "source", "classification"),
        "summary_fields": ("title", "source", "classification", "review_status"),
    },
    "witness": {
        "label": "VersionWitness",
        "source_phase": "observe",
        "query_fields": (
            "witness_key",
            "work_title",
            "document_title",
            "source_ref",
            "catalog_id",
            "version_lineage_key",
        ),
        "summary_fields": (
            "document_title",
            "work_title",
            "source_ref",
            "review_status",
        ),
    },
    "claim": {
        "label": "EvidenceClaim",
        "source_phase": "analyze",
        "query_fields": (
            "claim_id",
            "claim_text",
            "source_entity",
            "target_entity",
            "relation_type",
            "document_title",
            "work_title",
        ),
        "summary_fields": (
            "claim_text",
            "relation_type",
            "evidence_grade",
            "confidence",
        ),
    },
}


@dataclass
class RetrievalResult:
    scope: str = "global"
    body: str = ""
    token_count: int = 0
    citations: List[Dict[str, Any]] = field(default_factory=list)
    truncated: bool = False
    asset_type: str = ""
    traceability: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "asset_type": self.asset_type,
            "body": self.body,
            "token_count": self.token_count,
            "citations": list(self.citations),
            "truncated": self.truncated,
            "traceability": dict(self.traceability),
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Cypher 模板
# ---------------------------------------------------------------------------

CYPHER_GLOBAL_SUMMARIES = (
    "MATCH (cs:CommunitySummary) "
    "RETURN cs.topic_key AS topic_key, cs.body AS body, "
    "       coalesce(cs.token_count, 0) AS token_count "
    "ORDER BY cs.token_count ASC"
)

CYPHER_COMMUNITY_SUMMARIES = (
    "MATCH (cs:CommunitySummary) WHERE cs.topic_key IN $topic_keys "
    "RETURN cs.topic_key AS topic_key, cs.body AS body, "
    "       coalesce(cs.token_count, 0) AS token_count"
)

CYPHER_LOCAL_NEIGHBORS = (
    "MATCH (n) WHERE n.id IN $entity_ids "
    "OPTIONAL MATCH (n)-[r]-(m) "
    "RETURN n.id AS src, labels(n) AS src_labels, "
    "       type(r) AS rel, m.id AS dst, labels(m) AS dst_labels "
    "LIMIT $limit"
)

CYPHER_TYPED_ASSETS_TEMPLATE = (
    "MATCH (n:{label}) "
    "WHERE ($cycle_id = '' OR coalesce(n.cycle_id, '') = $cycle_id) "
    "  AND ("
    "    (size($entity_ids) > 0 AND (n.id IN $entity_ids "
    "      OR coalesce(n.hypothesis_id, '') IN $entity_ids "
    "      OR coalesce(n.evidence_id, '') IN $entity_ids "
    "      OR coalesce(n.claim_id, '') IN $entity_ids "
    "      OR coalesce(n.catalog_id, '') IN $entity_ids "
    "      OR coalesce(n.witness_key, '') IN $entity_ids)) "
    "    OR ($query <> '' AND any(field IN $query_fields "
    "      WHERE toLower(toString(coalesce(n[field], ''))) CONTAINS toLower($query))) "
    "    OR (size($entity_ids) = 0 AND $query = '')"
    "  ) "
    "OPTIONAL MATCH (n)-[r]-(m) "
    "RETURN n.id AS node_id, labels(n) AS labels, properties(n) AS props, "
    "       elementId(n) AS node_element_id, type(r) AS rel_type, "
    "       elementId(r) AS relationship_id, m.id AS neighbor_id, "
    "       labels(m) AS neighbor_labels, "
    "       coalesce(n.phase, $default_source_phase) AS source_phase, "
    "       coalesce(n.cycle_id, $cycle_id) AS cycle_id "
    "LIMIT $limit"
)


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------


class GraphRAG:
    """三档摘要检索器。"""

    def __init__(
        self,
        *,
        neo4j_driver: Any = None,
        neo4j_database: str = "neo4j",
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        local_neighbor_limit: int = 50,
        tokenizer: Optional[Any] = None,
        cache: Optional[GraphRAGMemoryCache] = None,
        cache_size: int = DEFAULT_GRAPH_RAG_CACHE_SIZE,
    ) -> None:
        self._driver = neo4j_driver
        self._database = neo4j_database
        self._token_budget = int(token_budget)
        self._local_neighbor_limit = int(local_neighbor_limit)
        self._tokenizer = tokenizer
        self._cache = cache if cache is not None else GraphRAGMemoryCache(cache_size)

    # ------------------------------------------------------------------ #
    def retrieve(
        self,
        question_type: str,
        query: str,
        *,
        topic_keys: Optional[Sequence[str]] = None,
        entity_ids: Optional[Sequence[str]] = None,
        asset_type: Optional[str] = None,
        cycle_id: Optional[str] = None,
        weight_hints: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> RetrievalResult:
        scope = (question_type or "").strip().lower()
        if scope not in VALID_QUESTION_TYPES:
            raise ValueError(
                f"unsupported question_type={question_type!r}; "
                f"expected one of {VALID_QUESTION_TYPES}"
            )
        normalized_asset_type = self._normalize_asset_type(asset_type)
        normalized_weight_hints = self._normalize_weight_hints(weight_hints)
        use_cache = not normalized_weight_hints
        cache_key = build_graph_rag_cache_key(
            scope=scope,
            query=str(query or ""),
            topic_keys=topic_keys,
            entity_ids=entity_ids,
            asset_type=normalized_asset_type,
            cycle_id=cycle_id,
        )
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        if self._driver is None:
            result = self._empty_result(scope, normalized_asset_type)
            if normalized_weight_hints:
                result.metadata["weight_hint_applied_count"] = 0
            if use_cache:
                self._cache.put(cache_key, result)
            return result
        try:
            opener = self._resolve_session_opener()
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph_rag: cannot open session (%s)", exc)
            result = self._empty_result(scope, normalized_asset_type)
            if normalized_weight_hints:
                result.metadata["weight_hint_applied_count"] = 0
            if use_cache:
                self._cache.put(cache_key, result)
            return result

        try:
            with opener(database=self._database) as session:
                if normalized_asset_type:
                    result = self._retrieve_typed_assets(
                        session,
                        scope,
                        str(query or ""),
                        asset_type=normalized_asset_type,
                        entity_ids=entity_ids,
                        cycle_id=cycle_id,
                        weight_hints=normalized_weight_hints,
                    )
                    if use_cache:
                        self._cache.put(cache_key, result)
                    return result
                if scope == "global":
                    rows = list(session.run(CYPHER_GLOBAL_SUMMARIES))
                    result = self._render_summaries(scope, rows)
                    if normalized_weight_hints:
                        result.metadata["weight_hint_applied_count"] = 0
                    if use_cache:
                        self._cache.put(cache_key, result)
                    return result
                if scope == "community":
                    keys = self._resolve_topic_keys(query, topic_keys)
                    if not keys:
                        result = RetrievalResult(scope=scope)
                        if normalized_weight_hints:
                            result.metadata["weight_hint_applied_count"] = 0
                        if use_cache:
                            self._cache.put(cache_key, result)
                        return result
                    rows = list(
                        session.run(CYPHER_COMMUNITY_SUMMARIES, topic_keys=list(keys))
                    )
                    result = self._render_summaries(scope, rows)
                    if normalized_weight_hints:
                        result.metadata["weight_hint_applied_count"] = 0
                    if use_cache:
                        self._cache.put(cache_key, result)
                    return result
                # local
                ids = list(entity_ids or [])
                if not ids:
                    result = RetrievalResult(scope=scope)
                    if normalized_weight_hints:
                        result.metadata["weight_hint_applied_count"] = 0
                    if use_cache:
                        self._cache.put(cache_key, result)
                    return result
                rows = list(
                    session.run(
                        CYPHER_LOCAL_NEIGHBORS,
                        entity_ids=ids,
                        limit=self._local_neighbor_limit,
                    )
                )
                result = self._render_local(scope, rows)
                if normalized_weight_hints:
                    result.metadata["weight_hint_applied_count"] = 0
                if use_cache:
                    self._cache.put(cache_key, result)
                return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("graph_rag retrieve failed: %s", exc)
            result = self._empty_result(scope, normalized_asset_type)
            if normalized_weight_hints:
                result.metadata["weight_hint_applied_count"] = 0
            if use_cache:
                self._cache.put(cache_key, result)
            return result

    def _retrieve_typed_assets(
        self,
        session: Any,
        scope: str,
        query: str,
        *,
        asset_type: str,
        entity_ids: Optional[Sequence[str]],
        cycle_id: Optional[str],
        weight_hints: Sequence[Mapping[str, Any]],
    ) -> RetrievalResult:
        config = _ASSET_TYPE_CONFIG[asset_type]
        cypher = CYPHER_TYPED_ASSETS_TEMPLATE.format(label=config["label"])
        rows = list(
            session.run(
                cypher,
                query=str(query or "").strip(),
                query_fields=list(config["query_fields"]),
                entity_ids=[str(item) for item in (entity_ids or []) if str(item)],
                cycle_id=str(cycle_id or "").strip(),
                default_source_phase=str(config["source_phase"]),
                limit=self._local_neighbor_limit,
            )
        )
        rows, applied_count = self._apply_weight_hints(rows, weight_hints)
        return self._render_typed_assets(
            scope,
            asset_type,
            rows,
            config,
            metadata={"weight_hint_applied_count": applied_count},
        )

    # ------------------------------------------------------------------ #
    def _render_summaries(self, scope: str, rows: Iterable[Any]) -> RetrievalResult:
        body_parts: List[str] = []
        citations: List[Dict[str, Any]] = []
        truncated = False
        running_tokens = 0
        for rec in rows:
            topic_key = self._field(rec, "topic_key") or ""
            body = self._field(rec, "body") or ""
            if not body:
                continue
            piece = f"[{topic_key}] {body}"
            piece_tokens = self._estimate_tokens(piece)
            if running_tokens + piece_tokens > self._token_budget:
                truncated = True
                break
            body_parts.append(piece)
            citations.append({"type": "CommunitySummary", "topic_key": topic_key})
            running_tokens += piece_tokens
        text = "\n\n".join(body_parts)
        return RetrievalResult(
            scope=scope,
            body=text,
            token_count=running_tokens,
            citations=citations,
            truncated=truncated,
        )

    def _render_local(self, scope: str, rows: Iterable[Any]) -> RetrievalResult:
        body_parts: List[str] = []
        citations: List[Dict[str, Any]] = []
        truncated = False
        running_tokens = 0
        for rec in rows:
            src = self._field(rec, "src") or ""
            dst = self._field(rec, "dst") or ""
            rel = self._field(rec, "rel") or ""
            src_labels = list(self._field(rec, "src_labels") or [])
            dst_labels = list(self._field(rec, "dst_labels") or [])
            if not src:
                continue
            if dst and rel:
                piece = (
                    f"({src_labels[0] if src_labels else ''}:{src})-"
                    f"[{rel}]->({dst_labels[0] if dst_labels else ''}:{dst})"
                )
            else:
                piece = f"({src_labels[0] if src_labels else ''}:{src})"
            piece_tokens = self._estimate_tokens(piece)
            if running_tokens + piece_tokens > self._token_budget:
                truncated = True
                break
            body_parts.append(piece)
            citations.append({"type": "Entity", "id": src})
            running_tokens += piece_tokens
        return RetrievalResult(
            scope=scope,
            body="\n".join(body_parts),
            token_count=running_tokens,
            citations=citations,
            truncated=truncated,
        )

    def _render_typed_assets(
        self,
        scope: str,
        asset_type: str,
        rows: Iterable[Any],
        config: Mapping[str, Any],
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> RetrievalResult:
        body_parts: List[str] = []
        citations: List[Dict[str, Any]] = []
        node_ids: List[str] = []
        relationship_ids: List[str] = []
        source_phases: List[str] = []
        cycle_ids: List[str] = []
        seen_pieces: set[str] = set()
        truncated = False
        running_tokens = 0
        label = str(config.get("label") or asset_type)
        summary_fields = tuple(config.get("summary_fields") or ())

        for rec in rows:
            node_id = str(self._field(rec, "node_id") or "").strip()
            props = self._field(rec, "props") or {}
            if not isinstance(props, Mapping):
                props = {}
            node_ref = node_id or str(self._field(rec, "node_element_id") or "").strip()
            if not node_ref:
                continue
            relationship_id = str(self._field(rec, "relationship_id") or "").strip()
            source_phase = str(
                self._field(rec, "source_phase") or config.get("source_phase") or ""
            ).strip()
            cycle_id = str(
                self._field(rec, "cycle_id") or props.get("cycle_id") or ""
            ).strip()

            piece = self._format_typed_asset_piece(
                asset_type,
                label,
                node_ref,
                props,
                summary_fields,
            )
            if piece not in seen_pieces:
                piece_tokens = self._estimate_tokens(piece)
                if running_tokens + piece_tokens > self._token_budget:
                    truncated = True
                    break
                body_parts.append(piece)
                citations.append(
                    {"type": label, "id": node_ref, "asset_type": asset_type}
                )
                seen_pieces.add(piece)
                running_tokens += piece_tokens
            self._append_unique(node_ids, node_ref)
            self._append_unique(relationship_ids, relationship_id)
            self._append_unique(source_phases, source_phase)
            self._append_unique(cycle_ids, cycle_id)

        traceability = {
            "node_ids": node_ids,
            "relationship_ids": relationship_ids,
            "source_phase": source_phases[0]
            if len(source_phases) == 1
            else "mixed"
            if source_phases
            else "",
            "source_phases": source_phases,
            "cycle_id": cycle_ids[0]
            if len(cycle_ids) == 1
            else "mixed"
            if cycle_ids
            else "",
            "cycle_ids": cycle_ids,
        }
        return RetrievalResult(
            scope=scope,
            asset_type=asset_type,
            body="\n".join(body_parts),
            token_count=running_tokens,
            citations=citations,
            truncated=truncated,
            traceability=traceability,
            metadata=dict(metadata or {}),
        )

    def _format_typed_asset_piece(
        self,
        asset_type: str,
        label: str,
        node_ref: str,
        props: Mapping[str, Any],
        summary_fields: Sequence[str],
    ) -> str:
        parts: List[str] = []
        for field_name in summary_fields:
            value = props.get(field_name)
            if value in (None, "", [], {}):
                continue
            parts.append(f"{field_name}={value}")
        summary = "；".join(parts) if parts else node_ref
        return f"[{asset_type}:{node_ref}] ({label}) {summary}"

    # ------------------------------------------------------------------ #
    def _resolve_topic_keys(
        self, query: str, topic_keys: Optional[Sequence[str]]
    ) -> List[str]:
        if topic_keys:
            return [str(k) for k in topic_keys if str(k).strip()]
        # Fallback：从 query 里粗暴抽词
        if not query:
            return []
        tokens = [t for t in re.split(r"[\s,;；，、/]+", query) if t.strip()]
        return tokens[:5]

    def _estimate_tokens(self, text: str) -> int:
        if self._tokenizer is not None:
            try:
                return int(self._tokenizer(text))
            except Exception:  # noqa: BLE001
                pass
        # 字符 → 估算 token：中英混排粗略按 1 token / 2 char
        if not text:
            return 0
        return max(1, (len(text) + 1) // 2)

    def _empty_result(self, scope: str, asset_type: str = "") -> RetrievalResult:
        return RetrievalResult(
            scope=scope,
            asset_type=asset_type,
            traceability={
                "node_ids": [],
                "relationship_ids": [],
                "source_phase": "",
                "source_phases": [],
                "cycle_id": "",
                "cycle_ids": [],
            },
        )

    @staticmethod
    def _normalize_asset_type(asset_type: Optional[str]) -> str:
        text = str(asset_type or "").strip().lower()
        if not text:
            return ""
        if text not in VALID_ASSET_TYPES:
            raise ValueError(
                f"unsupported asset_type={asset_type!r}; "
                f"expected one of {VALID_ASSET_TYPES}"
            )
        return text

    @staticmethod
    def _append_unique(items: List[str], value: str) -> None:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)

    @classmethod
    def _apply_weight_hints(
        cls,
        rows: Sequence[Any],
        weight_hints: Sequence[Mapping[str, Any]],
    ) -> tuple[List[Any], int]:
        if not weight_hints:
            return list(rows), 0
        scored: List[tuple[float, int, Any]] = []
        applied_count = 0
        for index, row in enumerate(rows):
            score = cls._row_weight_hint_score(row, weight_hints)
            if score != 1.0:
                applied_count += 1
            scored.append((score, index, row))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [row for _score, _index, row in scored], applied_count

    @classmethod
    def _row_weight_hint_score(
        cls,
        row: Any,
        weight_hints: Sequence[Mapping[str, Any]],
    ) -> float:
        row_node_id = str(cls._field(row, "node_id") or "").strip()
        row_relationship_id = str(cls._field(row, "relationship_id") or "").strip()
        neighbor_id = str(cls._field(row, "neighbor_id") or "").strip()
        props = cls._field(row, "props") or {}
        if not isinstance(props, Mapping):
            props = {}
        row_ids = {
            item
            for item in (
                row_node_id,
                row_relationship_id,
                neighbor_id,
                str(props.get("id") or "").strip(),
                str(props.get("claim_id") or "").strip(),
                str(props.get("evidence_id") or "").strip(),
                str(props.get("hypothesis_id") or "").strip(),
            )
            if item
        }
        score = 1.0
        for hint in weight_hints:
            node_ids = {str(item) for item in hint.get("node_ids", []) if str(item)}
            relationship_ids = {
                str(item) for item in hint.get("relationship_ids", []) if str(item)
            }
            target_ids = {str(item) for item in hint.get("target_ids", []) if str(item)}
            matches_node = bool(
                (row_node_id and row_node_id in node_ids) or (row_ids & node_ids)
            )
            matches_relationship = bool(
                row_relationship_id and row_relationship_id in relationship_ids
            )
            matches_target = bool(row_ids & target_ids)
            if matches_node or matches_relationship or matches_target:
                score = max(score, _hint_boost_value(hint))
        return score

    @staticmethod
    def _normalize_weight_hints(
        weight_hints: Optional[Sequence[Mapping[str, Any]]],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for hint in weight_hints or []:
            if not isinstance(hint, Mapping):
                continue
            node_ids = _normalize_id_list(hint.get("node_ids"))
            relationship_ids = _normalize_id_list(hint.get("relationship_ids"))
            target_ids = _normalize_id_list(hint.get("target_ids"))
            target_ids.extend(
                item
                for item in _normalize_id_list(hint.get("ids"))
                if item not in target_ids
            )
            target_id = str(hint.get("target_id") or "").strip()
            if target_id and target_id not in target_ids:
                target_ids.append(target_id)
            if not node_ids and not relationship_ids and not target_ids:
                continue
            boost = _hint_boost_value(hint)
            normalized.append(
                {
                    **dict(hint),
                    "node_ids": node_ids,
                    "relationship_ids": relationship_ids,
                    "target_ids": target_ids,
                    "boost": boost,
                    "factor": boost,
                }
            )
        return normalized

    def _resolve_session_opener(self):
        inner = getattr(self._driver, "driver", None)
        if inner is not None and hasattr(inner, "session"):
            return inner.session
        if hasattr(self._driver, "session"):
            return self._driver.session
        raise RuntimeError("neo4j driver has no .session()")

    @staticmethod
    def _field(record: Any, key: str) -> Any:
        if record is None:
            return None
        if hasattr(record, "get"):
            try:
                return record.get(key)
            except Exception:
                pass
        try:
            return record[key]
        except Exception:
            return None


def _normalize_id_list(values: Any) -> List[str]:
    if values in (None, ""):
        return []
    if isinstance(values, (str, int, float)):
        text = str(values).strip()
        return [text] if text else []
    normalized: List[str] = []
    try:
        iterator = iter(values)
    except TypeError:
        text = str(values).strip()
        return [text] if text else []
    for item in iterator:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _hint_boost_value(hint: Mapping[str, Any]) -> float:
    for key in ("boost", "factor", "weight_boost", "weight_factor"):
        if hint.get(key) in (None, ""):
            continue
        try:
            value = float(hint.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    try:
        confidence = float(hint.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    return max(1.0, 1.0 + min(max(confidence, 0.0), 1.0))


__all__ = [
    "GraphRAG",
    "GraphRAGMemoryCache",
    "RetrievalResult",
    "DEFAULT_TOKEN_BUDGET",
    "VALID_ASSET_TYPES",
    "VALID_QUESTION_TYPES",
]
