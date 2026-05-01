"""T6.1 — Transactional Outbox 集成测试。

验收门：
- 手工杀 worker 后 PG 仍写成功（事件留在 outbox_events.pending）。
- 恢复 worker 后 Neo4j 追上（handler 被调用，行被 mark processed）。
- outbox_dlq 集成测试：handler 连续失败 ≥ 5 次后行被搬到 outbox_dlq。

使用 sqlite in-memory + JSON column；与生产 PG 共用同一份 ORM。
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from src.infrastructure.persistence import (
    DatabaseManager,
    OutboxDLQORM,
    OutboxEventORM,
    OutboxStatusEnum,
)
from src.storage.outbox.graph_projection import (
    GRAPH_PROJECTION_EVENT_TYPE,
    build_graph_projection_handler,
    enqueue_graph_projection,
)
from src.storage.outbox.outbox_worker import OutboxWorker
from src.storage.outbox.pg_outbox_store import (
    MAX_RETRY_COUNT,
    PgOutboxStore,
    enqueue_in_session,
)


def _build_db() -> DatabaseManager:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    return db


class _RecordingNeo4jTx:
    def __init__(self, owner):
        self._owner = owner

    def run(self, query, **params):
        self._owner.calls.append((query, params))
        if self._owner.fail:
            raise RuntimeError("neo4j unavailable")
        return {"query": query, "params": params}


class _RecordingNeo4jSession:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, callback):
        return callback(_RecordingNeo4jTx(self._owner))


class _RecordingNeo4jBackend:
    def __init__(self, owner):
        self._owner = owner

    def session(self, database=None):
        self._owner.session_databases.append(database)
        return _RecordingNeo4jSession(self._owner)


class _RecordingNeo4jDriver:
    def __init__(self, *, fail=False):
        self.database = "neo4j"
        self.fail = fail
        self.calls = []
        self.session_databases = []
        self.driver = _RecordingNeo4jBackend(self)


class TestTransactionalOutbox(unittest.TestCase):
    def test_enqueue_in_session_persists_pending_row(self) -> None:
        db = _build_db()
        with db.session_scope() as session:
            row = enqueue_in_session(
                session,
                aggregate_type="document",
                aggregate_id="doc-1",
                event_type="neo4j.projection.upsert",
                payload={"entities": [{"id": "e1"}]},
            )
            self.assertEqual(row.status, OutboxStatusEnum.PENDING.value)

        store = PgOutboxStore(db)
        self.assertEqual(store.count_pending(), 1)
        self.assertEqual(store.count_dlq(), 0)

    def test_pg_persists_when_worker_offline(self) -> None:
        """手工杀 worker：PG 仍写成功，事件留在 pending。"""
        db = _build_db()
        store = PgOutboxStore(db)
        # 不启动任何 worker，直接 enqueue 多条
        for i in range(3):
            store.enqueue(
                aggregate_type="document",
                aggregate_id=f"doc-{i}",
                event_type="neo4j.projection.upsert",
                payload={"i": i},
            )
        self.assertEqual(store.count_pending(), 3)
        self.assertEqual(store.count_dlq(), 0)

    def test_worker_drains_pending_to_processed(self) -> None:
        """恢复 worker → Neo4j（handler）追上，行被 mark processed。"""
        db = _build_db()
        store = PgOutboxStore(db)
        for i in range(4):
            store.enqueue(
                aggregate_type="document",
                aggregate_id=f"doc-{i}",
                event_type="neo4j.projection.upsert",
                payload={"i": i},
            )

        seen: List[Dict[str, Any]] = []

        def handler(event: Dict[str, Any]) -> None:
            seen.append(event)

        worker = OutboxWorker(store, handler=handler, batch_size=10)
        stats = asyncio.run(worker.run_once())

        self.assertEqual(stats["claimed"], 4)
        self.assertEqual(stats["processed"], 4)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(len(seen), 4)
        self.assertEqual(store.count_pending(), 0)

        # 行确实落到 processed 状态
        with db.session_scope() as session:
            statuses = [r.status for r in session.query(OutboxEventORM).all()]
        self.assertTrue(all(s == OutboxStatusEnum.PROCESSED.value for s in statuses))

    def test_handler_failure_moves_to_dlq_after_max_retry(self) -> None:
        """handler 连续失败 ≥ MAX_RETRY_COUNT 次后，行被搬到 outbox_dlq。"""
        self.assertEqual(MAX_RETRY_COUNT, 5)
        db = _build_db()
        store = PgOutboxStore(db)
        store.enqueue(
            aggregate_type="document",
            aggregate_id="doc-bad",
            event_type="neo4j.projection.upsert",
            payload={"will": "fail"},
        )

        def always_fail(event: Dict[str, Any]) -> None:
            raise RuntimeError("neo4j unavailable")

        worker = OutboxWorker(store, handler=always_fail, batch_size=1)
        # 5 轮重试 → DLQ
        moved = False
        for _ in range(MAX_RETRY_COUNT):
            stats = asyncio.run(worker.run_once())
            if stats["moved_to_dlq"]:
                moved = True
                break
            self.assertEqual(stats["failed"], 1)

        self.assertTrue(moved, "事件未在 MAX_RETRY_COUNT 次失败后进入 DLQ")
        self.assertEqual(store.count_pending(), 0)
        self.assertEqual(store.count_dlq(), 1)

        with db.session_scope() as session:
            self.assertEqual(session.query(OutboxEventORM).count(), 0)
            dlq_rows = session.query(OutboxDLQORM).all()
            self.assertEqual(len(dlq_rows), 1)
            self.assertEqual(dlq_rows[0].retry_count, MAX_RETRY_COUNT)
            self.assertIn("neo4j unavailable", dlq_rows[0].last_error)
            self.assertEqual(dlq_rows[0].aggregate_id, "doc-bad")

    def test_failure_then_recovery_succeeds_on_retry(self) -> None:
        """模拟 worker 第一次失败、第二次成功的恢复流。"""
        db = _build_db()
        store = PgOutboxStore(db)
        store.enqueue(
            aggregate_type="document",
            aggregate_id="doc-flaky",
            event_type="neo4j.projection.upsert",
            payload={"v": 1},
        )

        attempts = {"n": 0}

        def flaky(event: Dict[str, Any]) -> None:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")

        worker = OutboxWorker(store, handler=flaky, batch_size=1)
        s1 = asyncio.run(worker.run_once())
        self.assertEqual(s1["failed"], 1)
        self.assertEqual(s1["moved_to_dlq"], 0)
        self.assertEqual(store.count_pending(), 1)  # back to pending

        s2 = asyncio.run(worker.run_once())
        self.assertEqual(s2["processed"], 1)
        self.assertEqual(store.count_pending(), 0)
        self.assertEqual(store.count_dlq(), 0)

    def test_graph_projection_outbox_commits_and_worker_marks_processed(self) -> None:
        db = _build_db()
        node_id = uuid4()
        created_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

        with db.session_scope() as session:
            row = enqueue_graph_projection(
                "cycle-graph-1",
                "observe",
                {
                    "nodes": [
                        {
                            "id": node_id,
                            "label": "Literature",
                            "properties": {
                                "created_at": created_at,
                                "score": Decimal("0.82"),
                                "source_path": Path("data/example.txt"),
                            },
                        }
                    ],
                    "edges": [],
                },
                "cycle-graph-1:observe:projection",
                session=session,
            )
            self.assertEqual(row.status, OutboxStatusEnum.PENDING.value)

        store = PgOutboxStore(db)
        self.assertEqual(store.count_pending(), 1)

        fake_neo4j = _RecordingNeo4jDriver()
        worker = OutboxWorker(
            store,
            handler=build_graph_projection_handler(fake_neo4j),
            batch_size=10,
        )

        stats = asyncio.run(worker.run_once())

        self.assertEqual(stats["claimed"], 1)
        self.assertEqual(stats["processed"], 1)
        self.assertEqual(store.count_pending(), 0)
        self.assertEqual(len(fake_neo4j.calls), 1)
        query, params = fake_neo4j.calls[0]
        self.assertIn("MERGE (n:Literature {id: row.id})", query)
        self.assertNotIn("CREATE ", query)
        projected_node = params["rows"][0]
        self.assertEqual(projected_node["id"], str(node_id))
        self.assertEqual(
            projected_node["properties"]["created_at"], created_at.isoformat()
        )
        self.assertEqual(projected_node["properties"]["score"], 0.82)
        self.assertEqual(
            projected_node["properties"]["source_path"], str(Path("data/example.txt"))
        )
        self.assertTrue(projected_node["projection_event_id"])
        self.assertTrue(projected_node["projected_at"])

        with db.session_scope() as session:
            rows = session.query(OutboxEventORM).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].status, OutboxStatusEnum.PROCESSED.value)
            self.assertEqual(rows[0].event_type, GRAPH_PROJECTION_EVENT_TYPE)

    def test_graph_projection_handler_failure_moves_to_dlq_after_max_retry(
        self,
    ) -> None:
        db = _build_db()
        store = PgOutboxStore(db)
        with db.session_scope() as session:
            enqueue_graph_projection(
                "cycle-graph-fail",
                "observe",
                {
                    "nodes": [
                        {
                            "id": "literature-fail",
                            "label": "Literature",
                            "properties": {"title": "伤寒论"},
                        }
                    ],
                    "edges": [],
                },
                "cycle-graph-fail:observe:projection",
                session=session,
            )

        worker = OutboxWorker(
            store,
            handler=build_graph_projection_handler(_RecordingNeo4jDriver(fail=True)),
            batch_size=1,
        )
        moved = False
        for _ in range(MAX_RETRY_COUNT):
            stats = asyncio.run(worker.run_once())
            if stats["moved_to_dlq"]:
                moved = True
                break
            self.assertEqual(stats["failed"], 1)

        self.assertTrue(moved)
        self.assertEqual(store.count_pending(), 0)
        self.assertEqual(store.count_dlq(), 1)
        with db.session_scope() as session:
            self.assertEqual(session.query(OutboxEventORM).count(), 0)
            dlq_rows = session.query(OutboxDLQORM).all()
            self.assertEqual(len(dlq_rows), 1)
            self.assertEqual(dlq_rows[0].event_type, GRAPH_PROJECTION_EVENT_TYPE)
            self.assertEqual(dlq_rows[0].retry_count, MAX_RETRY_COUNT)
            self.assertIn("neo4j unavailable", dlq_rows[0].last_error)


if __name__ == "__main__":
    unittest.main()
