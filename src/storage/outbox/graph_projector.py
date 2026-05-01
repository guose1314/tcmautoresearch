from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

from src.storage.neo4j_driver import _safe_cypher_label
from src.storage.outbox.graph_projection import (
    GRAPH_PROJECTION_CONTRACT_VERSION,
    GRAPH_PROJECTION_EVENT_TYPE,
)

EDGE_MERGE_STRATEGY_OVERWRITE = "overwrite"
EDGE_MERGE_STRATEGY_ACCUMULATE = "accumulate"
EDGE_MERGE_STRATEGIES = frozenset(
    {EDGE_MERGE_STRATEGY_OVERWRITE, EDGE_MERGE_STRATEGY_ACCUMULATE}
)


class GraphProjectionProjector:
    """Idempotent Neo4j projector for graph projection outbox events."""

    def __init__(
        self,
        neo4j_driver: Any,
        *,
        edge_merge_strategy: str = EDGE_MERGE_STRATEGY_OVERWRITE,
        edge_accumulate_property: str = "weight",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if neo4j_driver is None:
            raise RuntimeError("neo4j_driver is required for graph projection")
        strategy = (
            str(edge_merge_strategy or EDGE_MERGE_STRATEGY_OVERWRITE).strip().lower()
        )
        if strategy not in EDGE_MERGE_STRATEGIES:
            raise ValueError(
                f"unsupported edge_merge_strategy={edge_merge_strategy!r}; "
                f"expected one of {sorted(EDGE_MERGE_STRATEGIES)}"
            )
        self._neo4j_driver = neo4j_driver
        self._edge_merge_strategy = strategy
        self._edge_accumulate_property = _safe_cypher_label(
            str(edge_accumulate_property or "weight")
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def project_event(self, event: Mapping[str, Any]) -> Dict[str, Any]:
        graph_payload = _extract_graph_payload(event)
        projection_event_id = _resolve_projection_event_id(event)
        projected_at = self._clock().isoformat()
        node_rows = _build_node_rows(
            graph_payload.get("nodes") or [],
            projection_event_id=projection_event_id,
            projected_at=projected_at,
        )
        edge_rows = self._build_edge_rows(
            graph_payload.get("edges") or [],
            projection_event_id=projection_event_id,
            projected_at=projected_at,
        )

        backend = getattr(self._neo4j_driver, "driver", None)
        if backend is None:
            raise RuntimeError("Neo4j driver 未连接，无法执行图投影")
        database = getattr(self._neo4j_driver, "database", "neo4j")
        with backend.session(database=database) as session:
            for label, rows in node_rows.items():
                if rows:
                    session.execute_write(
                        lambda tx, query=_build_node_merge_query(label), rows=rows: (
                            tx.run(query, rows=rows)
                        )
                    )
            for (source_label, target_label, rel_type), rows in edge_rows.items():
                if rows:
                    session.execute_write(
                        lambda tx, query=self._build_edge_merge_query(source_label, target_label, rel_type), rows=rows: (
                            tx.run(query, rows=rows)
                        )
                    )

        return {
            "projection_event_id": projection_event_id,
            "projected_at": projected_at,
            "node_count": sum(len(rows) for rows in node_rows.values()),
            "edge_count": sum(len(rows) for rows in edge_rows.values()),
            "edge_merge_strategy": self._edge_merge_strategy,
        }

    def _build_edge_rows(
        self,
        edges: Sequence[Any],
        *,
        projection_event_id: str,
        projected_at: str,
    ) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
        grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        for item in edges:
            if not isinstance(item, Mapping):
                continue
            source_id = str(item.get("source_id") or "").strip()
            target_id = str(item.get("target_id") or "").strip()
            relationship_type = str(item.get("relationship_type") or "").strip()
            source_label = str(item.get("source_label") or "").strip()
            target_label = str(item.get("target_label") or "").strip()
            if not all(
                (source_id, target_id, relationship_type, source_label, target_label)
            ):
                continue
            properties = (
                dict(item.get("properties") or {})
                if isinstance(item.get("properties"), Mapping)
                else {}
            )
            accumulate_delta = 1
            if self._edge_merge_strategy == EDGE_MERGE_STRATEGY_ACCUMULATE:
                accumulate_delta = properties.pop(self._edge_accumulate_property, 1)
            grouped[(source_label, target_label, relationship_type)].append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "properties": properties,
                    "projection_event_id": projection_event_id,
                    "projected_at": projected_at,
                    "accumulate_delta": accumulate_delta,
                }
            )
        return grouped

    def _build_edge_merge_query(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
    ) -> str:
        query = (
            "UNWIND $rows AS row\n"
            f"MATCH (source:{_safe_cypher_label(source_label)} {{id: row.source_id}})\n"
            f"MATCH (target:{_safe_cypher_label(target_label)} {{id: row.target_id}})\n"
            f"MERGE (source)-[r:{_safe_cypher_label(rel_type)}]->(target)\n"
            "SET r += row.properties,\n"
            "    r.projection_event_id = row.projection_event_id,\n"
            "    r.projected_at = row.projected_at"
        )
        if self._edge_merge_strategy == EDGE_MERGE_STRATEGY_ACCUMULATE:
            query += (
                ",\n"
                f"    r.{_safe_cypher_label(self._edge_accumulate_property)} = "
                f"coalesce(r.{_safe_cypher_label(self._edge_accumulate_property)}, 0) "
                "+ coalesce(row.accumulate_delta, 1)"
            )
        return query


def _extract_graph_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    event_type = str(event.get("event_type") or "").strip()
    if event_type != GRAPH_PROJECTION_EVENT_TYPE:
        raise ValueError(
            f"unsupported outbox event_type for graph projection: {event_type!r}"
        )
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    if payload.get("contract_version") != GRAPH_PROJECTION_CONTRACT_VERSION:
        raise ValueError(
            "unsupported graph projection contract_version: "
            f"{payload.get('contract_version')!r}"
        )
    graph_payload = payload.get("graph_payload")
    if not isinstance(graph_payload, Mapping):
        raise ValueError("graph projection event payload missing graph_payload")
    return graph_payload


def _resolve_projection_event_id(event: Mapping[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    return str(
        event.get("id")
        or payload.get("idempotency_key")
        or event.get("aggregate_id")
        or "graph-projection-event"
    ).strip()


def _build_node_rows(
    nodes: Sequence[Any],
    *,
    projection_event_id: str,
    projected_at: str,
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in nodes:
        if not isinstance(item, Mapping):
            continue
        node_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not node_id or not label:
            continue
        properties = (
            dict(item.get("properties") or {})
            if isinstance(item.get("properties"), Mapping)
            else {}
        )
        grouped[label].append(
            {
                "id": node_id,
                "properties": properties,
                "projection_event_id": projection_event_id,
                "projected_at": projected_at,
            }
        )
    return grouped


def _build_node_merge_query(label: str) -> str:
    return (
        "UNWIND $rows AS row\n"
        f"MERGE (n:{_safe_cypher_label(label)} {{id: row.id}})\n"
        "SET n += row.properties,\n"
        "    n.projection_event_id = row.projection_event_id,\n"
        "    n.projected_at = row.projected_at"
    )


__all__ = [
    "EDGE_MERGE_STRATEGIES",
    "EDGE_MERGE_STRATEGY_ACCUMULATE",
    "EDGE_MERGE_STRATEGY_OVERWRITE",
    "GraphProjectionProjector",
]
