import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from src.storage.backend_factory import (
    StorageBackendFactory,
    _build_pg_connection_string,
)


class _FakeDatabaseManager:
    instances = []

    def __init__(self, connection_string, **kwargs):
        self.connection_string = connection_string
        self.kwargs = kwargs
        self.closed = False
        type(self).instances.append(self)

    def init_db(self):
        return None

    def get_schema_completeness_report(self):
        return {"status": "ok", "missing_tables": []}

    @staticmethod
    def create_default_relationships(session):
        return None

    @contextmanager
    def session_scope(self):
        yield object()

    def close(self):
        self.closed = True


class _FakeNeo4jDriver:
    instances = []

    def __init__(self, uri, auth, database="neo4j", **kwargs):
        self.uri = uri
        self.auth = auth
        self.database = database
        self.kwargs = kwargs
        self.connected = False
        self.closed = False
        type(self).instances.append(self)

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True


class _FakeOutboxStore:
    def __init__(self, _db_manager):
        self.events = []

    def enqueue(self, **kwargs):
        self.events.append(kwargs)
        return "event-1"


class TestBackendFactoryPasswordResolution(unittest.TestCase):
    def setUp(self):
        self.original_db_password = os.environ.get("TCM_DB_PASSWORD")
        self.original_neo4j_password = os.environ.get("TCM_NEO4J_PASSWORD")
        _FakeDatabaseManager.instances.clear()
        _FakeNeo4jDriver.instances.clear()

    def tearDown(self):
        if self.original_db_password is None:
            os.environ.pop("TCM_DB_PASSWORD", None)
        else:
            os.environ["TCM_DB_PASSWORD"] = self.original_db_password
        if self.original_neo4j_password is None:
            os.environ.pop("TCM_NEO4J_PASSWORD", None)
        else:
            os.environ["TCM_NEO4J_PASSWORD"] = self.original_neo4j_password

    def test_build_pg_connection_string_prefers_explicit_password_over_env(self):
        os.environ["TCM_DB_PASSWORD"] = "stale-env-password"

        connection_string = _build_pg_connection_string(
            {
                "host": "localhost",
                "port": 5432,
                "name": "tcmautoresearch",
                "user": "tcm_user",
                "password": "explicit-password",
                "password_env": "TCM_DB_PASSWORD",
            }
        )

        self.assertEqual(
            connection_string,
            "postgresql://tcm_user:explicit-password@localhost:5432/tcmautoresearch?sslmode=prefer",
        )

    def test_build_pg_connection_string_falls_back_to_env_when_password_missing(self):
        os.environ["TCM_DB_PASSWORD"] = "env-password"

        connection_string = _build_pg_connection_string(
            {
                "host": "localhost",
                "port": 5432,
                "name": "tcmautoresearch",
                "user": "tcm_user",
                "password_env": "TCM_DB_PASSWORD",
            }
        )

        self.assertEqual(
            connection_string,
            "postgresql://tcm_user:env-password@localhost:5432/tcmautoresearch?sslmode=prefer",
        )

    def test_factory_initialize_prefers_explicit_neo4j_password_over_env(self):
        os.environ["TCM_NEO4J_PASSWORD"] = "stale-env-password"

        config = {
            "database": {
                "type": "sqlite",
                "path": "./data/test-backend-factory.db",
            },
            "neo4j": {
                "enabled": True,
                "uri": "bolt://localhost:7687",
                "user": "neo4j",
                "password": "explicit-neo4j-password",
                "password_env": "TCM_NEO4J_PASSWORD",
                "database": "neo4j",
            },
        }

        with (
            patch("src.storage.backend_factory.DatabaseManager", _FakeDatabaseManager),
            patch(
                "src.storage.neo4j_driver.Neo4jDriver",
                _FakeNeo4jDriver,
            ),
        ):
            factory = StorageBackendFactory(config)
            report = factory.initialize()
            factory.close()

        self.assertEqual(report["pg_status"], "active")
        self.assertEqual(report["neo4j_status"], "active")
        self.assertEqual(len(_FakeNeo4jDriver.instances), 1)
        self.assertEqual(
            _FakeNeo4jDriver.instances[0].auth,
            ("neo4j", "explicit-neo4j-password"),
        )

    def test_factory_enqueue_graph_projection_uses_pg_outbox_store(self):
        factory = StorageBackendFactory({"database": {"type": "sqlite"}})
        factory._initialized = True
        factory._db_manager = object()

        with patch("src.storage.outbox.PgOutboxStore", _FakeOutboxStore):
            event_id = factory.enqueue_graph_projection(
                "cycle-1",
                "observe",
                {"nodes": [], "edges": []},
                "cycle-1:observe:graph",
            )

        self.assertEqual(event_id, "event-1")
        self.assertEqual(len(factory.outbox_store.events), 1)
        event = factory.outbox_store.events[0]
        self.assertEqual(event["event_type"], "neo4j.graph_projection.upsert")
        self.assertEqual(event["aggregate_type"], "graph_projection")
        self.assertEqual(event["payload"]["cycle_id"], "cycle-1")


if __name__ == "__main__":
    unittest.main()
