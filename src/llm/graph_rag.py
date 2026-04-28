"""GraphRAG — 三档（global / community / local）摘要检索。

T5.5 设计：

- ``global``：全库 :class:`CommunitySummary` 节点拼接，作为研究主题级背景。
- ``community``：按 ``topic_keys`` 过滤的社区级摘要，对应 Topic 子社区。
- ``local``：以 ``entity_ids`` 为种子的 1-hop 子图，渲染成简短文本。

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 公共契约
# ---------------------------------------------------------------------------

VALID_QUESTION_TYPES = ("global", "community", "local")
DEFAULT_TOKEN_BUDGET = 8000  # 4060 8GB 单 query 守门


@dataclass
class RetrievalResult:
    scope: str = "global"
    body: str = ""
    token_count: int = 0
    citations: List[Dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "body": self.body,
            "token_count": self.token_count,
            "citations": list(self.citations),
            "truncated": self.truncated,
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
    ) -> None:
        self._driver = neo4j_driver
        self._database = neo4j_database
        self._token_budget = int(token_budget)
        self._local_neighbor_limit = int(local_neighbor_limit)
        self._tokenizer = tokenizer

    # ------------------------------------------------------------------ #
    def retrieve(
        self,
        question_type: str,
        query: str,
        *,
        topic_keys: Optional[Sequence[str]] = None,
        entity_ids: Optional[Sequence[str]] = None,
    ) -> RetrievalResult:
        scope = (question_type or "").strip().lower()
        if scope not in VALID_QUESTION_TYPES:
            raise ValueError(
                f"unsupported question_type={question_type!r}; "
                f"expected one of {VALID_QUESTION_TYPES}"
            )
        if self._driver is None:
            return RetrievalResult(scope=scope)
        try:
            opener = self._resolve_session_opener()
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph_rag: cannot open session (%s)", exc)
            return RetrievalResult(scope=scope)

        try:
            with opener(database=self._database) as session:
                if scope == "global":
                    rows = list(session.run(CYPHER_GLOBAL_SUMMARIES))
                    return self._render_summaries(scope, rows)
                if scope == "community":
                    keys = self._resolve_topic_keys(query, topic_keys)
                    if not keys:
                        return RetrievalResult(scope=scope)
                    rows = list(
                        session.run(CYPHER_COMMUNITY_SUMMARIES, topic_keys=list(keys))
                    )
                    return self._render_summaries(scope, rows)
                # local
                ids = list(entity_ids or [])
                if not ids:
                    return RetrievalResult(scope=scope)
                rows = list(
                    session.run(
                        CYPHER_LOCAL_NEIGHBORS,
                        entity_ids=ids,
                        limit=self._local_neighbor_limit,
                    )
                )
                return self._render_local(scope, rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("graph_rag retrieve failed: %s", exc)
            return RetrievalResult(scope=scope)

    # ------------------------------------------------------------------ #
    def _render_summaries(
        self, scope: str, rows: Iterable[Any]
    ) -> RetrievalResult:
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

    def _render_local(
        self, scope: str, rows: Iterable[Any]
    ) -> RetrievalResult:
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


__all__ = ["GraphRAG", "RetrievalResult", "DEFAULT_TOKEN_BUDGET", "VALID_QUESTION_TYPES"]
