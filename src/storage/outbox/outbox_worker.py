"""T6.1 — OutboxWorker: asyncio-based background drainer.

Single-process worker that periodically claims pending outbox events from
:class:`PgOutboxStore` and dispatches them to a registered handler. On
handler success the event is marked ``processed``; on failure
``mark_failed`` increments ``retry_count`` and (at threshold) moves the row
to ``outbox_dlq``.

Typical wiring::

    from src.infrastructure.persistence import DatabaseManager
    from src.storage.outbox.pg_outbox_store import PgOutboxStore
    from src.storage.outbox.outbox_worker import OutboxWorker

    db = DatabaseManager(url); db.init_db()
    store = PgOutboxStore(db)

    async def neo4j_handler(event: dict) -> None:
        # event = {"id", "aggregate_type", "aggregate_id", "event_type", "payload"}
        ...  # write to Neo4j here

    worker = OutboxWorker(store, handler=neo4j_handler, poll_interval=0.5)
    task = asyncio.create_task(worker.run_forever())
    ...
    await worker.stop(); await task
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Union

from .pg_outbox_store import PgOutboxStore

logger = logging.getLogger(__name__)

OutboxHandler = Callable[[Dict[str, Any]], Union[None, Awaitable[None]]]


def build_event_type_router(
    handlers: Mapping[str, OutboxHandler],
    *,
    default_handler: Optional[OutboxHandler] = None,
) -> OutboxHandler:
    """Route outbox snapshots to handlers by ``event_type``."""
    registered = {str(key): handler for key, handler in dict(handlers or {}).items()}

    def _router(event: Dict[str, Any]) -> Union[None, Awaitable[None]]:
        event_type = str(event.get("event_type") or "").strip()
        handler = registered.get(event_type) or default_handler
        if handler is None:
            raise ValueError(
                f"no outbox handler registered for event_type={event_type!r}"
            )
        return handler(event)

    return _router


class OutboxWorker:
    """Single-process asyncio worker draining the outbox."""

    def __init__(
        self,
        store: PgOutboxStore,
        *,
        handler: OutboxHandler,
        poll_interval: float = 1.0,
        batch_size: int = 50,
    ) -> None:
        self._store = store
        self._handler = handler
        self._poll_interval = max(0.05, float(poll_interval))
        self._batch_size = max(1, int(batch_size))
        self._stop_event = asyncio.Event()
        self._running = False
        self._stats: Dict[str, int] = {
            "claimed": 0,
            "processed": 0,
            "failed": 0,
            "moved_to_dlq": 0,
        }

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    async def stop(self) -> None:
        self._stop_event.set()

    async def run_once(self) -> Dict[str, int]:
        """Drain one batch; returns per-batch counters.

        Useful for unit tests where running ``run_forever`` would deadlock.
        """
        batch_stats = {"claimed": 0, "processed": 0, "failed": 0, "moved_to_dlq": 0}
        events = self._store.claim_pending(limit=self._batch_size)
        batch_stats["claimed"] = len(events)
        for event in events:
            event_id = event["id"]
            try:
                result = self._handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001 — outbox swallows handler errors
                outcome = self._store.mark_failed(event_id, repr(exc))
                batch_stats["failed"] += 1
                if outcome.get("moved_to_dlq"):
                    batch_stats["moved_to_dlq"] += 1
                logger.warning(
                    "outbox handler failed for %s: %s (retry=%d, dlq=%s)",
                    event_id,
                    exc,
                    outcome.get("retry_count", 0),
                    bool(outcome.get("moved_to_dlq")),
                )
                continue
            self._store.mark_processed(event_id)
            batch_stats["processed"] += 1

        for k, v in batch_stats.items():
            self._stats[k] = self._stats.get(k, 0) + v
        return batch_stats

    async def run_forever(self) -> None:
        if self._running:
            raise RuntimeError("OutboxWorker is already running")
        self._running = True
        self._stop_event.clear()
        logger.info(
            "OutboxWorker started (poll_interval=%.2fs, batch_size=%d)",
            self._poll_interval,
            self._batch_size,
        )
        try:
            while not self._stop_event.is_set():
                try:
                    stats = await self.run_once()
                except Exception:  # noqa: BLE001
                    logger.exception("OutboxWorker batch crashed; will retry")
                    stats = {"claimed": 0}
                # backoff: idle longer when nothing to do
                wait = self._poll_interval if stats.get("claimed", 0) == 0 else 0.0
                if wait > 0:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                    except asyncio.TimeoutError:
                        pass
        finally:
            self._running = False
            logger.info("OutboxWorker stopped (stats=%s)", self._stats)
