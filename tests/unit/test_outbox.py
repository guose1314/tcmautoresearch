"""Phase L-2 — Outbox 模式单元测试。"""

from __future__ import annotations

import unittest

from src.storage.outbox import (
    CONTRACT_VERSION,
    OUTBOX_CONTRACT_VERSION,
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSED,
    InMemoryOutboxStore,
    OutboxEvent,
    OutboxReplaySummary,
    replay_pending_events,
)


def _make_event(eid: str = "evt-1", payload: dict | None = None) -> OutboxEvent:
    return OutboxEvent(
        event_id=eid,
        event_type="neo4j.cycle_projection",
        payload=payload or {"cycle_id": "c-1"},
    )


class TestContractBasics(unittest.TestCase):
    def test_contract_version(self) -> None:
        self.assertEqual(CONTRACT_VERSION, "outbox-event-v1")
        self.assertEqual(OUTBOX_CONTRACT_VERSION, CONTRACT_VERSION)

    def test_status_constants(self) -> None:
        self.assertEqual(OUTBOX_STATUS_PENDING, "pending")
        self.assertEqual(OUTBOX_STATUS_PROCESSED, "processed")
        self.assertEqual(OUTBOX_STATUS_FAILED, "failed")


class TestOutboxEventValidation(unittest.TestCase):
    def test_default_status_is_pending(self) -> None:
        evt = _make_event()
        self.assertEqual(evt.status, OUTBOX_STATUS_PENDING)
        self.assertEqual(evt.attempts, 0)
        self.assertIsNone(evt.last_error)

    def test_empty_event_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OutboxEvent(event_id="", event_type="t", payload={})

    def test_empty_event_type_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OutboxEvent(event_id="e", event_type="", payload={})

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(ValueError):
            OutboxEvent(event_id="e", event_type="t", payload={}, status="weird")

    def test_payload_must_be_dict(self) -> None:
        with self.assertRaises(TypeError):
            OutboxEvent(event_id="e", event_type="t", payload=[1, 2])  # type: ignore[arg-type]


class TestOutboxEventStateTransitions(unittest.TestCase):
    def test_mark_processed(self) -> None:
        evt = _make_event()
        evt.mark_processed()
        self.assertEqual(evt.status, OUTBOX_STATUS_PROCESSED)
        self.assertEqual(evt.attempts, 1)
        self.assertIsNone(evt.last_error)

    def test_mark_failed(self) -> None:
        evt = _make_event()
        evt.mark_failed("neo4j down")
        self.assertEqual(evt.status, OUTBOX_STATUS_FAILED)
        self.assertEqual(evt.attempts, 1)
        self.assertEqual(evt.last_error, "neo4j down")

    def test_reset_for_retry(self) -> None:
        evt = _make_event()
        evt.mark_failed("boom")
        evt.reset_for_retry()
        self.assertEqual(evt.status, OUTBOX_STATUS_PENDING)
        self.assertIsNone(evt.last_error)


class TestOutboxEventSerialization(unittest.TestCase):
    def test_to_dict_includes_contract_version(self) -> None:
        evt = _make_event()
        data = evt.to_dict()
        self.assertEqual(data["contract_version"], CONTRACT_VERSION)
        self.assertEqual(data["event_id"], "evt-1")
        self.assertEqual(data["status"], OUTBOX_STATUS_PENDING)

    def test_round_trip(self) -> None:
        evt = _make_event()
        evt.mark_failed("err")
        round_trip = OutboxEvent.from_dict(evt.to_dict())
        self.assertEqual(round_trip.event_id, evt.event_id)
        self.assertEqual(round_trip.status, evt.status)
        self.assertEqual(round_trip.attempts, evt.attempts)
        self.assertEqual(round_trip.last_error, evt.last_error)


class TestInMemoryOutboxStore(unittest.TestCase):
    def test_append_and_get(self) -> None:
        store = InMemoryOutboxStore()
        evt = store.append(_make_event())
        self.assertEqual(len(store), 1)
        self.assertIs(store.get("evt-1"), evt)

    def test_append_duplicate_raises(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event())
        with self.assertRaises(ValueError):
            store.append(_make_event())

    def test_upsert_overwrites(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event(payload={"v": 1}))
        store.upsert(_make_event(payload={"v": 2}))
        self.assertEqual(store.get("evt-1").payload["v"], 2)  # type: ignore[union-attr]

    def test_list_pending_and_failed(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event("a"))
        store.append(_make_event("b"))
        store.mark_failed("b", "boom")
        self.assertEqual({e.event_id for e in store.list_pending()}, {"a"})
        self.assertEqual({e.event_id for e in store.list_failed()}, {"b"})

    def test_mark_processed_unknown_returns_none(self) -> None:
        store = InMemoryOutboxStore()
        self.assertIsNone(store.mark_processed("missing"))

    def test_reset_failed_for_retry(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event("a"))
        store.mark_failed("a", "boom")
        count = store.reset_failed_for_retry()
        self.assertEqual(count, 1)
        self.assertEqual(store.get("a").status, OUTBOX_STATUS_PENDING)  # type: ignore[union-attr]

    def test_purge_processed(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event("a"))
        store.append(_make_event("b"))
        store.mark_processed("a")
        purged = store.purge_processed()
        self.assertEqual(purged, 1)
        self.assertEqual(len(store), 1)


class TestReplayPendingEvents(unittest.TestCase):
    def test_all_processed_when_handler_succeeds(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event("a"))
        store.append(_make_event("b"))

        seen: list[str] = []

        def handler(evt: OutboxEvent) -> None:
            seen.append(evt.event_id)

        summary = replay_pending_events(store, handler)
        self.assertIsInstance(summary, OutboxReplaySummary)
        self.assertEqual(summary.attempted, 2)
        self.assertEqual(summary.processed, 2)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(set(seen), {"a", "b"})
        self.assertEqual(len(store.list_pending()), 0)

    def test_handler_exception_marks_failed_and_swallowed(self) -> None:
        store = InMemoryOutboxStore()
        store.append(_make_event("a"))
        store.append(_make_event("b"))

        def handler(evt: OutboxEvent) -> None:
            if evt.event_id == "b":
                raise RuntimeError("neo4j down")

        summary = replay_pending_events(store, handler)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertIn("b", summary.failed_event_ids)
        self.assertEqual(store.get("b").status, OUTBOX_STATUS_FAILED)  # type: ignore[union-attr]
        self.assertEqual(store.get("b").last_error, "neo4j down")  # type: ignore[union-attr]

    def test_max_events_limits_replay(self) -> None:
        store = InMemoryOutboxStore()
        for i in range(5):
            store.append(_make_event(f"e{i}"))
        summary = replay_pending_events(store, lambda evt: None, max_events=2)
        self.assertEqual(summary.attempted, 2)
        self.assertEqual(summary.processed, 2)
        self.assertEqual(len(store.list_pending()), 3)


if __name__ == "__main__":
    unittest.main()
