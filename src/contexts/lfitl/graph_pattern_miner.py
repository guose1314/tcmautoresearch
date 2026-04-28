"""GraphPatternMiner — LFITL 内核：从 Neo4j 中挖掘"高频被纠正的图模式"。

设计动机
========

T5.1 的 :class:`GraphWeightUpdater` 会把"被反馈批评过"的节点
``weight *= factor (<1.0)``。本 miner 反向利用这一信号：

* 找出由"权重已被压低"的节点参与的高频 (label, rel_type, label) 三元组；
* 把它们抽象成 :class:`Pattern`，回灌到 :class:`FeedbackTranslator`
  让下一轮的 prompt_bias / graph_weight 提前规避同类结构；
* 同时给 LearningLoopOrchestrator 一个"高频负反馈模式"看板。

输出契约
========

``mine(neo4j_driver, since_ts) -> list[Pattern]``，模式定义::

    @dataclass
    class Pattern:
        node_labels: list[str]   # 起点 + 终点 label，长度==2
        rel_types:   list[str]   # 关系 type 列表（通常 1 个）
        support:     int         # 命中条数（被反馈节点参与的实例数）
        confidence:  float       # support / total_edges_of_same_shape
        last_negative_count: int # 在 since_ts 之后被打负反馈的次数

Cypher 模板
===========

默认查询（节点 ``weight < 1.0`` 视为"被反馈批评过"）::

    MATCH (a)-[r]->(b)
    WHERE coalesce(a.weight, 1.0) < 1.0 OR coalesce(b.weight, 1.0) < 1.0
    WITH labels(a) AS la, type(r) AS rt, labels(b) AS lb,
         count(*) AS support
    WHERE support >= $min_support
    RETURN la, rt, lb, support
    ORDER BY support DESC
    LIMIT $limit

如果 ``since_ts`` 提供，则在 ``WHERE`` 中追加::

    AND coalesce(a.last_updated_ts, 0) >= $since_ts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Pattern:
    """高频被反馈纠正的图模式。"""

    node_labels: List[str] = field(default_factory=list)
    rel_types: List[str] = field(default_factory=list)
    support: int = 0
    confidence: float = 0.0
    last_negative_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_labels": list(self.node_labels),
            "rel_types": list(self.rel_types),
            "support": int(self.support),
            "confidence": float(self.confidence),
            "last_negative_count": int(self.last_negative_count),
        }


_CYPHER_NEGATIVE = (
    "MATCH (a)-[r]->(b) "
    "WHERE (coalesce(a.weight, 1.0) < 1.0 OR coalesce(b.weight, 1.0) < 1.0) "
    "{ts_clause}"
    "WITH labels(a) AS la, type(r) AS rt, labels(b) AS lb, count(*) AS support "
    "WHERE support >= $min_support "
    "RETURN la, rt, lb, support "
    "ORDER BY support DESC "
    "LIMIT $limit"
)

_CYPHER_TOTAL = (
    "MATCH (a)-[r]->(b) "
    "WITH labels(a) AS la, type(r) AS rt, labels(b) AS lb, count(*) AS total "
    "RETURN la, rt, lb, total"
)


class GraphPatternMiner:
    """从 Neo4j 挖掘高频被纠正的图模式。"""

    def __init__(
        self,
        *,
        neo4j_database: str = "neo4j",
        min_support: int = 2,
        limit: int = 50,
    ) -> None:
        self._database = neo4j_database
        self._min_support = int(min_support)
        self._limit = int(limit)

    # ------------------------------------------------------------------ #
    def mine(
        self,
        neo4j_driver: Any,
        since_ts: Optional[float] = None,
    ) -> List[Pattern]:
        """挖掘负反馈高频图模式；driver 缺失时静默返回空。"""
        if neo4j_driver is None:
            return []
        try:
            opener = self._resolve_session_opener(neo4j_driver)
        except Exception as exc:  # noqa: BLE001
            logger.warning("graph pattern miner: cannot open session (%s)", exc)
            return []

        ts_clause = (
            "AND coalesce(a.last_updated_ts, 0) >= $since_ts " if since_ts else ""
        )
        cypher = _CYPHER_NEGATIVE.format(ts_clause=ts_clause)
        params: Dict[str, Any] = {
            "min_support": self._min_support,
            "limit": self._limit,
        }
        if since_ts is not None:
            params["since_ts"] = float(since_ts)

        patterns: List[Pattern] = []
        totals: Dict[tuple, int] = {}
        try:
            with opener(database=self._database) as session:
                neg_records = list(session.run(cypher, **params))
                tot_records = list(session.run(_CYPHER_TOTAL))
                for rec in tot_records:
                    key = (
                        tuple(self._record_field(rec, "la") or []),
                        self._record_field(rec, "rt"),
                        tuple(self._record_field(rec, "lb") or []),
                    )
                    totals[key] = int(self._record_field(rec, "total") or 0)
                for rec in neg_records:
                    la = list(self._record_field(rec, "la") or [])
                    rt = self._record_field(rec, "rt")
                    lb = list(self._record_field(rec, "lb") or [])
                    support = int(self._record_field(rec, "support") or 0)
                    total = totals.get((tuple(la), rt, tuple(lb)), support) or support
                    confidence = (support / total) if total else 0.0
                    patterns.append(
                        Pattern(
                            node_labels=[la[0] if la else "", lb[0] if lb else ""],
                            rel_types=[rt] if rt else [],
                            support=support,
                            confidence=round(confidence, 4),
                            last_negative_count=support,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.exception("graph pattern miner failed: %s", exc)
            return []
        return patterns

    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_session_opener(driver: Any):
        inner = getattr(driver, "driver", None)
        if inner is not None and hasattr(inner, "session"):
            return inner.session
        if hasattr(driver, "session"):
            return driver.session
        raise RuntimeError("neo4j driver has no .session()")

    @staticmethod
    def _record_field(record: Any, key: str) -> Any:
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


__all__ = ["GraphPatternMiner", "Pattern"]
