from __future__ import annotations

import logging
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from src.infrastructure.monitoring import MonitoringService
from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.research.phase_orchestrator import PhaseOrchestrator
from src.research.study_session_manager import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
)
from src.storage.backend_factory import StorageBackendFactory
from src.storage.consistency import (
    MODE_PG_ONLY,
    STATUS_DEGRADED,
    STATUS_DISABLED,
    build_consistency_state,
)
from src.storage.transaction import TransactionCoordinator
from tools.backfill_research_session_nodes import _build_backfill_report


class _RecordingPGSession:
    def __init__(self, *, flush_error=None, commit_error=None):
        self.flush_error = flush_error
        self.commit_error = commit_error
        self.flush_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def add(self, _instance):
        return None

    def add_all(self, _instances):
        return None

    def flush(self):
        self.flush_calls += 1
        if self.flush_error is not None:
            raise self.flush_error

    def commit(self):
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollback_calls += 1


class _RecordingNeo4jTx:
    def __init__(self, owner):
        self._owner = owner

    def run(self, query, **params):
        self._owner.executed_queries.append((query, params))
        if query in self._owner.fail_on_queries:
            raise RuntimeError(f"forced neo4j failure: {query}")
        return {"query": query, "params": params}


class _RecordingNeo4jSession:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, callback):
        self._owner.execute_write_calls += 1
        return callback(_RecordingNeo4jTx(self._owner))


class _RecordingNeo4jBackend:
    def __init__(self, owner):
        self._owner = owner

    def session(self, database=None):
        self._owner.session_databases.append(database)
        return _RecordingNeo4jSession(self._owner)


class _RecordingNeo4jDriver:
    def __init__(self, *, fail_on_queries=None):
        self.database = "neo4j"
        self.fail_on_queries = set(fail_on_queries or [])
        self.executed_queries = []
        self.execute_write_calls = 0
        self.session_databases = []
        self.driver = _RecordingNeo4jBackend(self)

    def close(self):
        return None


class _FakeEventBus:
    def subscribe(self, *_args, **_kwargs):
        return None


class _FakePipeline:
    def __init__(self) -> None:
        self.event_bus = _FakeEventBus()
        self.phase_handlers = SimpleNamespace(get_handler=lambda _phase_name: None)
        self.config = {}
        self.logger = logging.getLogger(__name__)


class _FakeStorageFactory:
    def __init__(self, db_manager, neo4j_driver, init_report, consistency_state):
        self._db_manager = db_manager
        self._neo4j_driver = neo4j_driver
        self._init_report = dict(init_report)
        self._consistency_state = consistency_state

    @property
    def db_manager(self):
        return self._db_manager

    @property
    def neo4j_driver(self):
        return self._neo4j_driver

    def initialize(self):
        return dict(self._init_report)

    def get_consistency_state(self):
        return self._consistency_state

    @contextmanager
    def transaction(self):
        session = self._db_manager.get_session()
        try:
            with TransactionCoordinator(session, self._neo4j_driver) as txn:
                yield txn
        finally:
            session.close()

    def close(self):
        return None


class _FakeSettings:
    database_type = "sqlite"
    database_config = {}
    neo4j_enabled = False
    environment = "test"
    loaded_files = []

    def get_section(self, *_paths, default=None):
        return default if default is not None else {}

    def get(self, _key, default=None):
        return default

    def materialize_runtime_config(self):
        return {}


class _FakeJobManager:
    def get_storage_summary(self):
        return {"storage_dir": "output/jobs", "stored_jobs": 0}


def _make_cycle() -> ResearchCycle:
    return ResearchCycle(
        cycle_id="cycle-consistency-001",
        cycle_name="结构化一致性验证",
        description="验证同一轮 structured persist",
        status=ResearchCycleStatus.COMPLETED,
        current_phase=ResearchPhase.PUBLISH,
        started_at="2026-04-17T10:00:00",
        completed_at="2026-04-17T10:05:00",
        research_objective="验证结构化持久化一致读取",
        phase_executions={
            ResearchPhase.OBSERVE: {
                "started_at": "2026-04-17T10:00:00",
                "completed_at": "2026-04-17T10:02:00",
                "duration": 120.0,
                "context": {"query": "桂枝汤版本研究"},
                "result": {
                    "status": "completed",
                    "ingestion_pipeline": {
                        "documents": [
                            {
                                "urn": "doc:observe:1",
                                "title": "伤寒论宋本",
                                "source_type": "ctext",
                                "raw_text_size": 128,
                                "metadata": {
                                    "version_metadata": {
                                        "work_title": "伤寒论",
                                        "fragment_title": "辨脉法",
                                        "work_fragment_key": "伤寒论|辨脉法",
                                        "version_lineage_key": "伤寒论|辨脉法|东汉|张仲景|宋本",
                                        "catalog_id": "ctp:shang-han-lun/bian-mai-fa",
                                        "dynasty": "东汉",
                                        "author": "张仲景",
                                        "edition": "宋本",
                                        "witness_key": "ctext:doc:1",
                                    }
                                },
                                "entities": [
                                    {
                                        "name": "桂枝汤",
                                        "type": "formula",
                                        "confidence": 0.95,
                                        "position": 0,
                                        "length": 3,
                                    }
                                ],
                                "semantic_relationships": [
                                    {
                                        "source": "桂枝汤",
                                        "target": "太阳病",
                                        "type": "TREATS",
                                        "source_type": "formula",
                                        "target_type": "syndrome",
                                        "confidence": 0.88,
                                    }
                                ],
                            }
                        ]
                    },
                },
            },
            ResearchPhase.PUBLISH: {
                "started_at": "2026-04-17T10:03:00",
                "completed_at": "2026-04-17T10:05:00",
                "duration": 120.0,
                "context": {"style": "paper"},
                "result": {
                    "status": "completed",
                    "artifacts": [
                        {
                            "name": "paper.md",
                            "artifact_type": "paper",
                            "mime_type": "text/markdown",
                            "content": {"title": "桂枝汤版本研究"},
                        }
                    ],
                },
            },
        },
    )


class TestStructuredPersistVerification(unittest.TestCase):
    def setUp(self):
        self.db_manager = DatabaseManager("sqlite:///:memory:")
        self.db_manager.init_db()

    def tearDown(self):
        self.db_manager.close()

    def test_dual_write_same_round_persist_is_consistently_readable(self):
        neo4j_driver = _RecordingNeo4jDriver()
        consistency_state = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="active",
            neo4j_driver_connected=True,
        )
        fake_factory = _FakeStorageFactory(
            db_manager=self.db_manager,
            neo4j_driver=neo4j_driver,
            init_report={
                "db_type": "postgresql",
                "pg_status": "active",
                "neo4j_status": "active",
                "neo4j_enabled": True,
            },
            consistency_state=consistency_state,
        )
        orchestrator = PhaseOrchestrator(_FakePipeline())
        cycle = _make_cycle()

        with patch("src.storage.StorageBackendFactory", return_value=fake_factory):
            persisted = orchestrator._persist_result_structured(cycle)

        self.assertTrue(persisted)

        repo = ResearchSessionRepository(self.db_manager)
        snapshot = repo.get_full_snapshot(cycle.cycle_id)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["cycle_id"], cycle.cycle_id)
        self.assertEqual(len(snapshot["phase_executions"]), 2)
        self.assertEqual(len(snapshot["artifacts"]), 1)
        self.assertEqual(len(snapshot["observe_documents"]), 1)
        self.assertEqual(len(snapshot["version_lineages"]), 1)
        self.assertEqual(snapshot["version_lineages"][0]["witness_count"], 1)
        self.assertEqual(
            snapshot["observe_documents"][0]["version_metadata"]["witness_key"],
            "ctext:doc:1",
        )

        storage_persistence = snapshot["metadata"]["storage_persistence"]
        self.assertEqual(storage_persistence["mode"], "dual_write")
        self.assertEqual(storage_persistence["consistency_state"]["mode"], "dual_write")
        self.assertEqual(storage_persistence["neo4j_status"], "active")
        self.assertGreater(storage_persistence["graph_node_count"], 0)
        self.assertGreater(storage_persistence["graph_edge_count"], 0)
        self.assertFalse(storage_persistence["eventual_consistency"]["graph_backfill_pending"])

        executed_queries = [query for query, _params in neo4j_driver.executed_queries]
        self.assertTrue(any("ResearchSession" in query for query in executed_queries))
        self.assertTrue(any("ResearchPhaseExecution" in query for query in executed_queries))
        self.assertTrue(any("ResearchArtifact" in query for query in executed_queries))
        self.assertTrue(any("VersionWitness" in query for query in executed_queries))
        self.assertTrue(any("VersionLineage" in query for query in executed_queries))


class TestNeo4jDegradationExposureVerification(unittest.TestCase):
    def test_neo4j_disabled_is_exposed_as_pg_only(self):
        factory = StorageBackendFactory({
            "database": {"type": "postgresql"},
            "neo4j": {"enabled": False},
        })
        factory._initialized = True
        factory._db_manager = object()

        state = factory.get_consistency_state()

        self.assertEqual(state.mode, MODE_PG_ONLY)
        self.assertEqual(state.neo4j_status, STATUS_DISABLED)
        self.assertNotEqual(state.neo4j_status, "active")

    def test_neo4j_init_failure_is_exposed_as_pg_only(self):
        factory = StorageBackendFactory({
            "database": {"type": "postgresql"},
            "neo4j": {"enabled": True},
        })
        factory._initialized = True
        factory._db_manager = object()
        factory._neo4j_driver = None

        state = factory.get_consistency_state()

        self.assertEqual(state.mode, MODE_PG_ONLY)
        self.assertEqual(state.neo4j_status, STATUS_DEGRADED)
        self.assertNotEqual(state.neo4j_status, "active")

    def test_driver_not_connected_is_not_misreported_by_monitoring(self):
        service = MonitoringService(_FakeSettings(), SimpleNamespace(), _FakeJobManager())
        degraded_state = build_consistency_state(
            initialized=True,
            db_type="postgresql",
            pg_status="active",
            neo4j_enabled=True,
            neo4j_status="error: driver not connected",
            neo4j_driver_connected=False,
        )

        with patch.object(service, "_get_consistency_state_dict", return_value=degraded_state.to_dict()):
            persistence = service._build_persistence_summary()

        self.assertEqual(persistence["structured_storage"]["consistency_state"]["mode"], "pg_only")
        self.assertNotEqual(
            persistence["structured_storage"]["consistency_state"]["neo4j_status"],
            "active",
        )


class TestAnomalyVocabularyVerification(unittest.TestCase):
    def test_compensation_failure_is_surfaced_as_structured_fields(self):
        pg_session = _RecordingPGSession(commit_error=RuntimeError("pg commit blocked"))
        neo4j_driver = _RecordingNeo4jDriver(fail_on_queries={"DELETE first"})
        txn = TransactionCoordinator(pg_session, neo4j_driver, auto_commit=False)

        txn.neo4j_write("CREATE first", compensate_cypher="DELETE first", id=1)
        result = txn.commit()

        self.assertFalse(result.success)
        self.assertTrue(result.needs_backfill)
        self.assertEqual(result.compensations_applied, 0)
        self.assertEqual(result.storage_mode, "dual_write")
        self.assertTrue(any(item.startswith("failed:") for item in result.compensation_details))
        self.assertIn("PostgreSQL commit 失败", result.error)

    def test_schema_drift_and_backfill_pending_share_consistency_contract_across_surfaces(self):
        factory = StorageBackendFactory({
            "database": {"type": "postgresql"},
            "neo4j": {"enabled": True},
        })
        factory._initialized = True
        factory._db_manager = SimpleNamespace(
            inspect_schema_drift=lambda: {
                "status": "degraded",
                "legacy_enum_count": 1,
                "incompatible_drift_count": 0,
                "compatibility_variant_count": 0,
            }
        )
        factory._neo4j_driver = SimpleNamespace(driver=None)

        consistency_state = factory.get_consistency_state()
        runtime_eventual_consistency = PhaseOrchestrator._classify_eventual_consistency(
            consistency_state,
            {"enabled": False, "status": "skipped", "node_count": 0},
        )
        snapshot_dependency = ResearchSessionRepository._classify_backfill_dependency(
            {
                "metadata": {
                    "storage_persistence": {
                        "eventual_consistency": runtime_eventual_consistency,
                    }
                },
                "observe_philology": {},
                "version_lineages": [],
            }
        )
        service = MonitoringService(_FakeSettings(), SimpleNamespace(), _FakeJobManager())
        with patch.object(service, "_get_consistency_state_dict", return_value=consistency_state.to_dict()):
            persistence_summary = service._build_persistence_summary()
        backfill_report = _build_backfill_report(
            settings=SimpleNamespace(environment="test", loaded_files=[], loaded_secret_files=[]),
            init_report={
                "db_type": "postgresql",
                "pg_status": "active",
                "neo4j_status": "error: driver not connected",
                "neo4j_enabled": True,
            },
            consistency_state=consistency_state.to_dict(),
            writeback_summary={"status": "active", "updated_document_count": 1},
            philology_artifact_writeback_summary={"status": "active", "created_artifact_count": 1},
            graph_summary={"status": "skipped", "node_count": 0, "edge_count": 0},
        )

        self.assertTrue(consistency_state.schema_drift_detected)
        self.assertEqual(consistency_state.mode, MODE_PG_ONLY)
        self.assertTrue(runtime_eventual_consistency["graph_backfill_pending"])
        self.assertIn("backfill", runtime_eventual_consistency["reason"])
        self.assertTrue(snapshot_dependency["graph_projection"]["backfill_pending"])
        self.assertEqual(
            snapshot_dependency["graph_projection"]["reason"],
            runtime_eventual_consistency["reason"],
        )
        self.assertTrue(
            persistence_summary["structured_storage"]["consistency_state"]["schema_drift_detected"]
        )
        self.assertEqual(
            persistence_summary["structured_storage"]["consistency_state"]["mode"],
            MODE_PG_ONLY,
        )
        self.assertTrue(backfill_report["storage"]["consistency_state"]["schema_drift_detected"])
        self.assertEqual(backfill_report["storage"]["consistency_state"]["mode"], MODE_PG_ONLY)
        self.assertIn("fields_written", backfill_report["backfill"])


if __name__ == "__main__":
    unittest.main()