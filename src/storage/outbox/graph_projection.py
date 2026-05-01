from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from sqlalchemy.orm import Session

from src.storage.outbox.pg_outbox_store import PgOutboxStore, enqueue_in_session

GRAPH_PROJECTION_CONTRACT_VERSION = "graph-projection-outbox-v1"
GRAPH_PROJECTION_EVENT_TYPE = "neo4j.graph_projection.upsert"
GRAPH_PROJECTION_AGGREGATE_TYPE = "graph_projection"


def enqueue_graph_projection(
    cycle_id: str,
    phase: str,
    graph_payload: Mapping[str, Any],
    idempotency_key: str,
    *,
    session: Optional[Session] = None,
    store: Optional[PgOutboxStore] = None,
) -> Any:
    """Enqueue a JSON-safe graph projection event in PG outbox.

    ``session`` is the preferred path for transactional outbox writes because
    the event commits or rolls back together with the business rows.
    """
    payload = build_graph_projection_event_payload(
        cycle_id=cycle_id,
        phase=phase,
        graph_payload=graph_payload,
        idempotency_key=idempotency_key,
    )
    aggregate_id = _bounded_aggregate_id(idempotency_key)
    if session is not None:
        return enqueue_in_session(
            session,
            aggregate_type=GRAPH_PROJECTION_AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            event_type=GRAPH_PROJECTION_EVENT_TYPE,
            payload=payload,
        )
    if store is not None:
        return store.enqueue(
            aggregate_type=GRAPH_PROJECTION_AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            event_type=GRAPH_PROJECTION_EVENT_TYPE,
            payload=payload,
        )
    raise ValueError("enqueue_graph_projection requires session or store")


def build_graph_projection_event_payload(
    *,
    cycle_id: str,
    phase: str,
    graph_payload: Mapping[str, Any],
    idempotency_key: str,
) -> Dict[str, Any]:
    normalized_cycle_id = str(cycle_id or "").strip()
    normalized_phase = str(phase or "").strip().lower()
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_cycle_id:
        raise ValueError("cycle_id 不能为空")
    if not normalized_phase:
        raise ValueError("phase 不能为空")
    if not normalized_idempotency_key:
        raise ValueError("idempotency_key 不能为空")
    if not isinstance(graph_payload, Mapping):
        raise TypeError("graph_payload 必须是 mapping")

    payload = {
        "contract_version": GRAPH_PROJECTION_CONTRACT_VERSION,
        "cycle_id": normalized_cycle_id,
        "phase": normalized_phase,
        "idempotency_key": normalized_idempotency_key,
        "graph_payload": json_safe(graph_payload),
    }
    json.dumps(payload, ensure_ascii=False)
    return payload


def build_graph_projection_handler(
    neo4j_driver: Any,
    *,
    edge_merge_strategy: str = "overwrite",
) -> Callable[[Dict[str, Any]], None]:
    from src.storage.outbox.graph_projector import GraphProjectionProjector

    projector = GraphProjectionProjector(
        neo4j_driver,
        edge_merge_strategy=edge_merge_strategy,
    )

    def _handler(event: Dict[str, Any]) -> None:
        projector.project_event(event)

    return _handler


def handle_graph_projection_event(
    event: Mapping[str, Any],
    neo4j_driver: Any,
    *,
    edge_merge_strategy: str = "overwrite",
) -> None:
    from src.storage.outbox.graph_projector import GraphProjectionProjector

    GraphProjectionProjector(
        neo4j_driver,
        edge_merge_strategy=edge_merge_strategy,
    ).project_event(event)


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (uuid.UUID, Path)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _bounded_aggregate_id(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= 128:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{text[:111]}:{digest}"


__all__ = [
    "GRAPH_PROJECTION_AGGREGATE_TYPE",
    "GRAPH_PROJECTION_CONTRACT_VERSION",
    "GRAPH_PROJECTION_EVENT_TYPE",
    "build_graph_projection_event_payload",
    "build_graph_projection_handler",
    "enqueue_graph_projection",
    "handle_graph_projection_event",
    "json_safe",
]
