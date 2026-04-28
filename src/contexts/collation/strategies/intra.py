"""本校（intra collation）：在 Neo4j 同一 Document 子图内寻找前后呼应/矛盾对。

通过 ``MATCH (e1)-[:MENTIONED_IN]->(d)<-[:MENTIONED_IN]-(e2)`` 找到同文共现实体；
若两实体之间存在显式 ``CONTRADICTS`` / ``SUPPORTS`` 关系或同名异义/反义对，
则记入 ``contradictions`` 或 ``echoes``。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


_QUERY_INTRA_PAIRS = """
MATCH (d:Document {id: $document_id})
MATCH (e1)-[:MENTIONED_IN]->(d)<-[:MENTIONED_IN]-(e2)
WHERE id(e1) < id(e2)
OPTIONAL MATCH (e1)-[r]->(e2)
WITH e1, e2, collect(DISTINCT type(r)) AS rel_types
RETURN e1.name AS entity_a,
       coalesce(e1.type, '') AS type_a,
       e2.name AS entity_b,
       coalesce(e2.type, '') AS type_b,
       rel_types
LIMIT $limit
""".strip()


_CONTRADICTION_REL_TYPES = {
    "CONTRADICTS",
    "DISPUTES",
    "CONFLICTS_WITH",
    "OPPOSES",
}
_ECHO_REL_TYPES = {
    "SUPPORTS",
    "ECHOES",
    "REINFORCES",
    "CONFIRMS",
    "AGREES_WITH",
}


class IntraCollationStrategy:
    """本校（同文呼应/矛盾）。"""

    name = "intra"

    def __init__(self, *, neo4j_driver: Any = None, neo4j_database: str = "neo4j") -> None:
        self._driver = neo4j_driver
        self._database = neo4j_database

    def run(self, document_id: str, *, context: Mapping[str, Any]) -> Dict[str, Any]:
        if self._driver is None:
            return {
                "document_id": document_id,
                "enabled": False,
                "reason": "Neo4j driver not provided",
                "echoes": [],
                "contradictions": [],
                "co_mention_count": 0,
            }

        limit = int(context.get("intra_limit") or 200)
        records = list(self._run_cypher(document_id, limit=limit))

        echoes = []
        contradictions = []
        for rec in records:
            rel_types = {str(t).upper() for t in (rec.get("rel_types") or [])}
            pair = {
                "entity_a": rec.get("entity_a"),
                "type_a": rec.get("type_a"),
                "entity_b": rec.get("entity_b"),
                "type_b": rec.get("type_b"),
                "relations": sorted(rel_types),
            }
            if rel_types & _CONTRADICTION_REL_TYPES:
                contradictions.append(pair)
            elif rel_types & _ECHO_REL_TYPES:
                echoes.append(pair)
        return {
            "document_id": document_id,
            "enabled": True,
            "co_mention_count": len(records),
            "echoes": echoes,
            "contradictions": contradictions,
            "echo_count": len(echoes),
            "contradiction_count": len(contradictions),
        }

    # ------------------------------------------------------------------ #
    def _run_cypher(self, document_id: str, *, limit: int):
        opener = self._resolve_session_opener()
        with opener(database=self._database) as session:
            result = session.run(
                _QUERY_INTRA_PAIRS, document_id=document_id, limit=limit
            )
            for record in result:
                if hasattr(record, "data"):
                    yield record.data()
                else:
                    yield dict(record)

    def _resolve_session_opener(self):
        # 与 CatalogContext 一致：兼容 wrapper.driver.session 与 driver.session 两种
        inner = getattr(self._driver, "driver", None)
        if inner is not None and hasattr(inner, "session"):
            return inner.session
        if hasattr(self._driver, "session"):
            return self._driver.session
        raise RuntimeError("neo4j driver has no .session()")


__all__ = ["IntraCollationStrategy"]
