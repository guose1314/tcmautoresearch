from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.storage.outbox import build_event_type_router
from src.storage.outbox.graph_projection import (
    GRAPH_PROJECTION_EVENT_TYPE,
    build_graph_projection_event_payload,
)
from src.storage.outbox.graph_projector import (
    EDGE_MERGE_STRATEGY_ACCUMULATE,
    GraphProjectionProjector,
)


class _RecordingTx:
    def __init__(self, owner):
        self._owner = owner

    def run(self, query, **params):
        self._owner.calls.append((query, params))
        if self._owner.fail:
            raise RuntimeError("neo4j write failed")
        return {"query": query, "params": params}


class _RecordingSession:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, callback):
        return callback(_RecordingTx(self._owner))


class _RecordingBackend:
    def __init__(self, owner):
        self._owner = owner

    def session(self, database=None):
        self._owner.session_databases.append(database)
        return _RecordingSession(self._owner)


class _RecordingNeo4jDriver:
    def __init__(self, *, fail=False):
        self.database = "neo4j"
        self.fail = fail
        self.calls = []
        self.session_databases = []
        self.driver = _RecordingBackend(self)


def _fixed_clock() -> datetime:
    return datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc)


def _event(graph_payload=None):
    return {
        "id": "event-graph-1",
        "aggregate_type": "graph_projection",
        "aggregate_id": "cycle-1:observe:graph",
        "event_type": GRAPH_PROJECTION_EVENT_TYPE,
        "payload": build_graph_projection_event_payload(
            cycle_id="cycle-1",
            phase="observe",
            idempotency_key="cycle-1:observe:graph",
            graph_payload=graph_payload
            or {
                "nodes": [
                    {
                        "id": "literature-1",
                        "label": "Literature",
                        "properties": {"title": "伤寒论"},
                    }
                ],
                "edges": [
                    {
                        "source_id": "claim-1",
                        "target_id": "literature-1",
                        "source_label": "EvidenceClaim",
                        "target_label": "Literature",
                        "relationship_type": "CITES",
                        "properties": {"support_level": "strong", "weight": 0.8},
                    }
                ],
            },
        ),
    }


class TestGraphProjectionProjector(unittest.TestCase):
    def test_same_event_generates_stable_merge_queries_without_create(self) -> None:
        driver = _RecordingNeo4jDriver()
        projector = GraphProjectionProjector(driver, clock=_fixed_clock)
        event = _event()

        first_summary = projector.project_event(event)
        first_calls = list(driver.calls)
        second_summary = projector.project_event(event)
        second_calls = driver.calls[len(first_calls) :]

        self.assertEqual(first_summary["node_count"], 1)
        self.assertEqual(first_summary["edge_count"], 1)
        self.assertEqual(first_summary, second_summary)
        self.assertEqual(first_calls, second_calls)
        self.assertEqual(len(first_calls), 2)
        for query, params in first_calls:
            self.assertIn("MERGE", query)
            self.assertNotIn("CREATE ", query)
            rows = params["rows"]
            self.assertEqual(rows[0]["projection_event_id"], "event-graph-1")
            self.assertEqual(rows[0]["projected_at"], _fixed_clock().isoformat())

        node_query, node_params = first_calls[0]
        edge_query, edge_params = first_calls[1]
        self.assertIn("MERGE (n:Literature {id: row.id})", node_query)
        self.assertIn("MERGE (source)-[r:CITES]->(target)", edge_query)
        self.assertEqual(node_params["rows"][0]["properties"]["title"], "伤寒论")
        self.assertEqual(
            edge_params["rows"][0]["properties"]["support_level"], "strong"
        )
        self.assertEqual(edge_params["rows"][0]["properties"]["weight"], 0.8)

    def test_accumulate_strategy_uses_configured_edge_property(self) -> None:
        driver = _RecordingNeo4jDriver()
        projector = GraphProjectionProjector(
            driver,
            edge_merge_strategy=EDGE_MERGE_STRATEGY_ACCUMULATE,
            edge_accumulate_property="weight",
            clock=_fixed_clock,
        )
        projector.project_event(
            _event(
                {
                    "nodes": [],
                    "edges": [
                        {
                            "source_id": "claim-1",
                            "target_id": "topic-1",
                            "source_label": "EvidenceClaim",
                            "target_label": "ResearchTopic",
                            "relationship_type": "BELONGS_TO_TOPIC",
                            "properties": {"weight": 0.4, "source": "observe"},
                        }
                    ],
                }
            )
        )

        query, params = driver.calls[0]
        self.assertIn("r.weight = coalesce(r.weight, 0)", query)
        row = params["rows"][0]
        self.assertEqual(row["accumulate_delta"], 0.4)
        self.assertNotIn("weight", row["properties"])
        self.assertEqual(row["properties"]["source"], "observe")

    def test_illegal_label_is_rejected_before_cypher_execution(self) -> None:
        driver = _RecordingNeo4jDriver()
        projector = GraphProjectionProjector(driver, clock=_fixed_clock)

        with self.assertRaises(ValueError):
            projector.project_event(
                _event(
                    {
                        "nodes": [
                            {
                                "id": "bad-1",
                                "label": "Bad Label",
                                "properties": {},
                            }
                        ],
                        "edges": [],
                    }
                )
            )

        self.assertEqual(driver.calls, [])

    def test_event_type_router_dispatches_registered_handler(self) -> None:
        seen = []
        router = build_event_type_router(
            {GRAPH_PROJECTION_EVENT_TYPE: lambda event: seen.append(event["id"])}
        )

        router(_event())

        self.assertEqual(seen, ["event-graph-1"])
        with self.assertRaises(ValueError):
            router({"id": "event-unknown", "event_type": "unknown"})


if __name__ == "__main__":
    unittest.main()
