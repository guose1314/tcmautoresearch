"""T6.1 — PostgreSQL/SQLAlchemy backed Outbox store.

This is the durable counterpart of :class:`InMemoryOutboxStore` defined in
:mod:`src.storage.outbox.outbox_store`. It writes to ``outbox_events`` /
``outbox_dlq`` ORM tables (see :mod:`src.infrastructure.persistence`) and is
designed to be enrolled in the *same* SQLAlchemy session as the business
write — guaranteeing PG-side atomicity ("transactional outbox" pattern).

Public API
==========

* :func:`enqueue_in_session` — call inside ``DatabaseManager.session_scope`` to
  emit an event in the same transaction as the business writes.
* :class:`PgOutboxStore` — wraps a ``DatabaseManager`` and exposes
  ``claim_pending`` / ``mark_processed`` / ``mark_failed`` / DLQ helpers.

Failure policy
==============

On the 5th consecutive failure (``retry_count >= 5``) the row is moved to
``outbox_dlq`` and removed from ``outbox_events``. The threshold is
configurable via :data:`MAX_RETRY_COUNT`.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy.orm import Session

from src.infrastructure.persistence import (
    DatabaseManager,
    OutboxDLQORM,
    OutboxEventORM,
    OutboxStatusEnum,
)

logger = logging.getLogger(__name__)

MAX_RETRY_COUNT = 5


# ---------------------------------------------------------------------------
# Inline transactional enqueue
# ---------------------------------------------------------------------------


def enqueue_in_session(
    session: Session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: Dict[str, Any],
) -> OutboxEventORM:
    """Add a pending outbox row to the **caller's** session.

    The caller controls the transaction boundary; this function only stages
    the row via ``session.add`` so it commits/rolls back together with the
    business writes.
    """
    if not aggregate_type or not aggregate_id or not event_type:
        raise ValueError("aggregate_type / aggregate_id / event_type 不能为空")
    row = OutboxEventORM(
        id=uuid.uuid4(),
        aggregate_type=str(aggregate_type),
        aggregate_id=str(aggregate_id),
        event_type=str(event_type),
        payload=dict(payload or {}),
        status=OutboxStatusEnum.PENDING.value,
        retry_count=0,
    )
    session.add(row)
    return row


# ---------------------------------------------------------------------------
# PgOutboxStore
# ---------------------------------------------------------------------------


class PgOutboxStore:
    """SQLAlchemy-backed outbox store.

    The store does **not** open long-lived transactions; each ``claim_pending``
    / ``mark_*`` invocation runs in its own ``session_scope`` so the OutboxWorker
    can interleave many small commits without holding row locks.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    # ── enqueue (standalone tx) ───────────────────────────────────────

    def enqueue(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> str:
        with self._db.session_scope() as session:
            row = enqueue_in_session(
                session,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
            )
            session.flush()
            return str(row.id)

    # ── claim ─────────────────────────────────────────────────────────

    def claim_pending(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Mark up to ``limit`` pending events as ``processing`` and return snapshots.

        Snapshots are plain dicts decoupled from the session so the worker can
        process them outside of a DB transaction.
        """
        out: List[Dict[str, Any]] = []
        with self._db.session_scope() as session:
            rows = (
                session.query(OutboxEventORM)
                .filter(OutboxEventORM.status == OutboxStatusEnum.PENDING.value)
                .order_by(OutboxEventORM.created_at.asc())
                .limit(int(limit))
                .all()
            )
            for row in rows:
                row.status = OutboxStatusEnum.PROCESSING.value
                out.append(_row_to_snapshot(row))
        return out

    # ── mark ──────────────────────────────────────────────────────────

    def mark_processed(self, event_id: str) -> bool:
        with self._db.session_scope() as session:
            row = session.get(OutboxEventORM, _coerce_uuid(event_id))
            if row is None:
                return False
            row.status = OutboxStatusEnum.PROCESSED.value
            row.processed_at = datetime.now(timezone.utc)
            row.last_error = None
            return True

    def mark_failed(self, event_id: str, error: str) -> Dict[str, Any]:
        """Record one failure; on retry_count == MAX move the row into DLQ.

        Returns ``{"moved_to_dlq": bool, "retry_count": int}``.
        """
        with self._db.session_scope() as session:
            row = session.get(OutboxEventORM, _coerce_uuid(event_id))
            if row is None:
                return {"moved_to_dlq": False, "retry_count": 0}
            row.retry_count = int(row.retry_count or 0) + 1
            row.last_error = str(error)[:8192]
            if row.retry_count >= MAX_RETRY_COUNT:
                dlq = OutboxDLQORM(
                    id=uuid.uuid4(),
                    original_event_id=row.id,
                    aggregate_type=row.aggregate_type,
                    aggregate_id=row.aggregate_id,
                    event_type=row.event_type,
                    payload=dict(row.payload or {}),
                    retry_count=row.retry_count,
                    last_error=row.last_error,
                    created_at=row.created_at,
                )
                session.add(dlq)
                session.delete(row)
                logger.warning(
                    "outbox event %s moved to DLQ after %d failures",
                    event_id,
                    row.retry_count,
                )
                return {"moved_to_dlq": True, "retry_count": row.retry_count}
            row.status = OutboxStatusEnum.PENDING.value
            return {"moved_to_dlq": False, "retry_count": row.retry_count}

    # ── inspection ────────────────────────────────────────────────────

    def count_pending(self) -> int:
        with self._db.session_scope() as session:
            return int(
                session.query(OutboxEventORM)
                .filter(OutboxEventORM.status == OutboxStatusEnum.PENDING.value)
                .count()
            )

    def count_dlq(self) -> int:
        with self._db.session_scope() as session:
            return int(session.query(OutboxDLQORM).count())

    def list_dlq(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self._db.session_scope() as session:
            rows = session.query(OutboxDLQORM).limit(int(limit)).all()
            return [
                {
                    "id": str(r.id),
                    "original_event_id": str(r.original_event_id),
                    "aggregate_type": r.aggregate_type,
                    "aggregate_id": r.aggregate_id,
                    "event_type": r.event_type,
                    "payload": dict(r.payload or {}),
                    "retry_count": int(r.retry_count or 0),
                    "last_error": r.last_error,
                }
                for r in rows
            ]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row_to_snapshot(row: OutboxEventORM) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "aggregate_type": row.aggregate_type,
        "aggregate_id": row.aggregate_id,
        "event_type": row.event_type,
        "payload": dict(row.payload or {}),
        "retry_count": int(row.retry_count or 0),
    }


def _coerce_uuid(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except Exception:
        return value


@contextmanager
def transactional_outbox(db: DatabaseManager) -> Iterator[Session]:
    """Convenience wrapper: open a session_scope and expose it for inline enqueue.

    Example::

        with transactional_outbox(db) as session:
            session.add(my_business_row)
            enqueue_in_session(session, aggregate_type="document",
                               aggregate_id=str(doc.id),
                               event_type="neo4j.document.upsert",
                               payload={"id": str(doc.id)})
    """
    with db.session_scope() as session:
        yield session
