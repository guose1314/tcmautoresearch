"""Phase L-2 — 双写 outbox 模式。

提供 ``OutboxEvent`` 契约与 ``InMemoryOutboxStore`` 最小实现，确保 PG
事务成功后即便 Neo4j 暂时不可用也能将待写事件落地，由后台 replay
worker 异步重放。
"""

from .event_contract import (
    CONTRACT_VERSION,
    OUTBOX_CONTRACT_VERSION,
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSED,
    OUTBOX_VALID_STATUSES,
    OutboxEvent,
)
from .graph_projection import (
    GRAPH_PROJECTION_AGGREGATE_TYPE,
    GRAPH_PROJECTION_CONTRACT_VERSION,
    GRAPH_PROJECTION_EVENT_TYPE,
    build_graph_projection_event_payload,
    build_graph_projection_handler,
    enqueue_graph_projection,
    handle_graph_projection_event,
    json_safe,
)
from .graph_projector import (
    EDGE_MERGE_STRATEGIES,
    EDGE_MERGE_STRATEGY_ACCUMULATE,
    EDGE_MERGE_STRATEGY_OVERWRITE,
    GraphProjectionProjector,
)
from .outbox_store import (
    InMemoryOutboxStore,
    OutboxReplaySummary,
    replay_pending_events,
)
from .outbox_worker import OutboxHandler, OutboxWorker, build_event_type_router
from .pg_outbox_store import (
    MAX_RETRY_COUNT,
    PgOutboxStore,
    enqueue_in_session,
    transactional_outbox,
)

__all__ = [
    "CONTRACT_VERSION",
    "OUTBOX_CONTRACT_VERSION",
    "OUTBOX_STATUS_FAILED",
    "OUTBOX_STATUS_PENDING",
    "OUTBOX_STATUS_PROCESSED",
    "OUTBOX_VALID_STATUSES",
    "OutboxEvent",
    "InMemoryOutboxStore",
    "OutboxReplaySummary",
    "replay_pending_events",
    "GRAPH_PROJECTION_AGGREGATE_TYPE",
    "GRAPH_PROJECTION_CONTRACT_VERSION",
    "GRAPH_PROJECTION_EVENT_TYPE",
    "build_graph_projection_event_payload",
    "build_graph_projection_handler",
    "enqueue_graph_projection",
    "handle_graph_projection_event",
    "json_safe",
    "EDGE_MERGE_STRATEGIES",
    "EDGE_MERGE_STRATEGY_ACCUMULATE",
    "EDGE_MERGE_STRATEGY_OVERWRITE",
    "GraphProjectionProjector",
    # T6.1
    "MAX_RETRY_COUNT",
    "PgOutboxStore",
    "enqueue_in_session",
    "transactional_outbox",
    "OutboxWorker",
    "OutboxHandler",
    "build_event_type_router",
]
