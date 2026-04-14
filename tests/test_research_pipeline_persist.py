"""
tests/test_research_pipeline_persist.py
ResearchPipeline._persist_result() 单元测试
"""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.research.research_pipeline import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
    ResearchPipeline,
)


def _make_cycle(
    cycle_id: str = "cycle_test_001",
    status: ResearchCycleStatus = ResearchCycleStatus.COMPLETED,
) -> ResearchCycle:
    cycle = ResearchCycle(
        cycle_id=cycle_id,
        cycle_name="测试循环",
        description="单元测试用",
        research_objective="验证持久化",
    )
    cycle.status = status
    cycle.started_at = "2026-01-01T00:00:00"
    cycle.completed_at = datetime.now().isoformat()
    cycle.duration = 42.0
    cycle.outcomes = [{"phase": "observe", "result": {"observations": ["obs1"]}}]
    return cycle


def _make_phase_execution(
    phase_name: str,
    result: dict,
    *,
    context: dict | None = None,
    started_at: str = "2026-01-01T00:00:00",
    completed_at: str = "2026-01-01T00:00:05",
    duration: float = 5.0,
) -> dict:
    return {
        "phase": phase_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration": duration,
        "context": context or {},
        "result": result,
    }


class TestPersistResultBasic(unittest.TestCase):
    """基本读写测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_returns_true_on_success(self):
        cycle = _make_cycle()
        result = self.pipeline._persist_result(cycle)
        self.assertTrue(result)

    def test_creates_db_file(self):
        self.pipeline._persist_result(_make_cycle())
        self.assertTrue(os.path.isfile(self.db_path))

    def test_row_written(self):
        cycle = _make_cycle("cycle_abc")
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT cycle_id, cycle_name, status FROM research_results WHERE cycle_id=?",
            ("cycle_abc",),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "cycle_abc")
        self.assertEqual(row[1], "测试循环")
        self.assertEqual(row[2], "completed")

    def test_outcomes_serialized_as_json(self):
        cycle = _make_cycle()
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        raw = conn.execute(
            "SELECT outcomes_json FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()[0]
        conn.close()
        data = json.loads(raw)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) > 0)

    def test_metadata_serialized_as_json(self):
        cycle = _make_cycle()
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        raw = conn.execute(
            "SELECT metadata_json FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()[0]
        conn.close()
        data = json.loads(raw)
        self.assertIsInstance(data, dict)

    def test_persisted_at_is_set(self):
        self.pipeline._persist_result(_make_cycle())
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT persisted_at FROM research_results").fetchone()
        conn.close()
        self.assertIsNotNone(row[0])
        # 格式为 ISO 8601
        datetime.fromisoformat(row[0])

    def test_duration_stored(self):
        cycle = _make_cycle()
        cycle.duration = 99.5
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT duration FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()
        conn.close()
        self.assertAlmostEqual(row[0], 99.5)


class TestPersistResultUpsert(unittest.TestCase):
    """幂等写入 / upsert 测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_upsert_overwrites_existing(self):
        cycle = _make_cycle("cycle_dup")
        self.pipeline._persist_result(cycle)
        # 更新状态后再写
        cycle.status = ResearchCycleStatus.FAILED
        self.pipeline._persist_result(cycle)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT status FROM research_results WHERE cycle_id=?", ("cycle_dup",)).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "failed")

    def test_multiple_cycles_stored(self):
        for i in range(5):
            self.pipeline._persist_result(_make_cycle(f"cycle_{i:03d}"))
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM research_results").fetchone()[0]
        conn.close()
        self.assertEqual(count, 5)


class TestPersistResultErrorHandling(unittest.TestCase):
    """错误处理：失败不阻断主链"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_returns_false_on_db_error(self):
        cycle = _make_cycle()
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("boom")):
            result = self.pipeline._persist_result(cycle)
        self.assertFalse(result)

    def test_does_not_raise_on_error(self):
        cycle = _make_cycle()
        with patch("sqlite3.connect", side_effect=Exception("unexpected")):
            try:
                self.pipeline._persist_result(cycle)
            except Exception:
                self.fail("_persist_result() should not propagate exceptions")


class TestPersistResultDefaultPath(unittest.TestCase):
    """默认路径（output/research_results.db）测试"""

    def test_creates_output_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "subdir", "research_results.db")
            pipeline = ResearchPipeline({"result_store_path": db_path})
            pipeline._persist_result(_make_cycle())
            self.assertTrue(os.path.isfile(db_path))


class TestPersistResultIntegration(unittest.TestCase):
    """complete_research_cycle() 调用 _persist_result() 集成测试"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "research_results.db")
        self.pipeline = ResearchPipeline({"result_store_path": self.db_path})

    def test_complete_cycle_triggers_persist(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="集成测试循环",
            description="desc",
            objective="obj",
            scope="scope",
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        self.pipeline.complete_research_cycle(cycle.cycle_id)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status FROM research_results WHERE cycle_id=?",
            (cycle.cycle_id,),
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "completed")


class TestStructuredPersistResult(unittest.TestCase):
    def _make_structured_cycle(self) -> ResearchCycle:
        cycle = _make_cycle("cycle_structured")
        cycle.phase_executions = {
            ResearchPhase.OBSERVE: _make_phase_execution(
                "observe",
                {
                    "phase": "observe",
                    "status": "completed",
                    "ingestion_pipeline": {
                        "documents": [
                            {
                                "urn": "doc:observe:1",
                                "title": "桂枝汤观察文档",
                                "raw_text_size": 128,
                                "processed_text_size": 120,
                                "entity_count": 2,
                                "entities": [
                                    {"name": "桂枝汤", "type": "formula", "confidence": 0.95, "position": 0, "length": 3},
                                    {"name": "桂枝", "type": "herb", "confidence": 0.93, "position": 4, "length": 2},
                                ],
                                "semantic_relationships": [
                                    {
                                        "source": "桂枝汤",
                                        "target": "桂枝",
                                        "type": "contains",
                                        "source_type": "formula",
                                        "target_type": "herb",
                                        "confidence": 0.95,
                                    }
                                ],
                            }
                        ],
                        "aggregate": {
                            "semantic_relationships": [
                                {
                                    "source": "桂枝汤",
                                    "target": "桂枝",
                                    "type": "contains",
                                    "source_type": "formula",
                                    "target_type": "herb",
                                    "metadata": {"confidence": 0.95},
                                }
                            ]
                        },
                    },
                    "results": {
                        "ingestion_pipeline": {
                            "documents": [
                                {
                                    "urn": "doc:observe:1",
                                    "title": "桂枝汤观察文档",
                                    "raw_text_size": 128,
                                    "processed_text_size": 120,
                                    "entity_count": 2,
                                    "entities": [
                                        {"name": "桂枝汤", "type": "formula", "confidence": 0.95, "position": 0, "length": 3},
                                        {"name": "桂枝", "type": "herb", "confidence": 0.93, "position": 4, "length": 2},
                                    ],
                                    "semantic_relationships": [
                                        {
                                            "source": "桂枝汤",
                                            "target": "桂枝",
                                            "type": "contains",
                                            "source_type": "formula",
                                            "target_type": "herb",
                                            "confidence": 0.95,
                                        }
                                    ],
                                }
                            ],
                            "aggregate": {
                                "semantic_relationships": [
                                    {
                                        "source": "桂枝汤",
                                        "target": "桂枝",
                                        "type": "contains",
                                        "source_type": "formula",
                                        "target_type": "herb",
                                        "metadata": {"confidence": 0.95},
                                    }
                                ]
                            }
                        }
                    },
                    "artifacts": [],
                    "metadata": {},
                    "error": None,
                },
                context={"question": "桂枝汤调和营卫机制"},
            ),
            ResearchPhase.PUBLISH: _make_phase_execution(
                "publish",
                {
                    "phase": "publish",
                    "status": "completed",
                    "results": {
                        "deliverables": ["Markdown 论文初稿"],
                    },
                    "artifacts": [
                        {
                            "name": "markdown",
                            "path": "./output/research_report.md",
                            "type": "file",
                        }
                    ],
                    "metadata": {},
                    "error": None,
                },
                duration=12.0,
            ),
        }
        return cycle

    def test_prefers_structured_storage_when_database_config_present(self):
        pipeline = ResearchPipeline(
            {
                "database": {"type": "postgresql", "host": "postgres", "name": "tcmautoresearch"},
                "neo4j": {"enabled": False},
            }
        )
        cycle = self._make_structured_cycle()

        fake_factory = MagicMock()
        fake_factory.initialize.return_value = {
            "db_type": "postgresql",
            "pg_status": "active",
            "neo4j_status": "skipped",
        }
        fake_factory.db_manager = object()
        fake_factory.neo4j_driver = None
        fake_txn = MagicMock()
        fake_txn.pg_session = object()
        fake_factory.transaction.return_value.__enter__.return_value = fake_txn
        fake_factory.transaction.return_value.__exit__.return_value = False

        fake_repo = MagicMock()
        fake_repo.get_session.return_value = None
        fake_repo.save_from_cycle.return_value = {
            "id": "session-1",
            "cycle_id": cycle.cycle_id,
            "created_at": "2026-04-12T16:41:00",
        }
        fake_repo.add_phase_execution.side_effect = [
            {"id": "phase-observe", "phase": "observe", "status": "completed"},
            {"id": "phase-publish", "phase": "publish", "status": "completed"},
        ]
        fake_repo.add_artifact.return_value = {
            "id": "artifact-1",
            "phase_execution_id": "phase-publish",
            "name": "markdown",
            "artifact_type": "paper",
        }
        fake_repo.replace_observe_document_graphs.return_value = []

        with patch("src.storage.StorageBackendFactory", return_value=fake_factory), patch(
            "src.infrastructure.research_session_repo.ResearchSessionRepository",
            return_value=fake_repo,
        ), patch(
            "src.research.phase_orchestrator.sqlite3.connect",
            side_effect=AssertionError("structured path should not fall back to sqlite"),
        ):
            result = pipeline._persist_result(cycle)

        self.assertTrue(result)
        fake_factory.initialize.assert_called_once()
        fake_factory.transaction.assert_called_once()
        fake_repo.save_from_cycle.assert_called_once()
        self.assertEqual(fake_repo.add_phase_execution.call_count, 2)
        fake_repo.replace_observe_document_graphs.assert_called_once()
        fake_repo.add_artifact.assert_called_once()
        fake_repo.update_session.assert_called_once()
        self.assertIs(fake_repo.save_from_cycle.call_args.kwargs["session"], fake_txn.pg_session)
        self.assertTrue(all(call.kwargs["session"] is fake_txn.pg_session for call in fake_repo.add_phase_execution.call_args_list))
        self.assertIs(fake_repo.replace_observe_document_graphs.call_args.kwargs["session"], fake_txn.pg_session)
        self.assertIs(fake_repo.add_artifact.call_args.kwargs["session"], fake_txn.pg_session)
        self.assertIs(fake_repo.update_session.call_args.kwargs["session"], fake_txn.pg_session)
        fake_factory.close.assert_called_once()

    def test_projects_research_assets_to_neo4j_when_enabled(self):
        pipeline = ResearchPipeline(
            {
                "database": {"type": "postgresql", "host": "postgres", "name": "tcmautoresearch"},
                "neo4j": {"enabled": True},
            }
        )
        cycle = self._make_structured_cycle()

        fake_factory = MagicMock()
        fake_factory.initialize.return_value = {
            "db_type": "postgresql",
            "pg_status": "active",
            "neo4j_status": "active",
        }
        fake_factory.db_manager = object()
        fake_factory.neo4j_driver = object()
        fake_txn = MagicMock()
        fake_txn.pg_session = object()
        fake_factory.transaction.return_value.__enter__.return_value = fake_txn
        fake_factory.transaction.return_value.__exit__.return_value = False

        fake_repo = MagicMock()
        fake_repo.get_session.return_value = None
        fake_repo.save_from_cycle.return_value = {
            "id": "session-1",
            "cycle_id": cycle.cycle_id,
            "created_at": "2026-04-12T16:41:00",
        }
        fake_repo.add_phase_execution.side_effect = [
            {
                "id": "phase-observe",
                "phase": "observe",
                "status": "completed",
                "created_at": "2026-04-12T16:41:01",
            },
            {
                "id": "phase-publish",
                "phase": "publish",
                "status": "completed",
                "created_at": "2026-04-12T16:41:02",
            },
        ]
        fake_repo.add_artifact.return_value = {
            "id": "artifact-1",
            "phase_execution_id": "phase-publish",
            "name": "markdown",
            "artifact_type": "paper",
            "description": "研究报告输出",
            "file_path": "./output/research_report.md",
            "mime_type": "text/markdown",
            "size_bytes": 0,
            "created_at": "2026-04-12T16:41:03",
            "updated_at": "2026-04-12T16:41:04",
        }
        fake_repo.replace_observe_document_graphs.return_value = [
            {
                "id": "observe-doc-1",
                "phase_execution_id": "phase-observe",
                "urn": "doc:observe:1",
                "title": "桂枝汤观察文档",
                "source_type": "ctext",
                "catalog_id": "ctp:guizhi-tang",
                "version_metadata": {
                    "work_title": "伤寒论",
                    "fragment_title": "桂枝汤",
                    "work_fragment_key": "伤寒论|桂枝汤",
                    "version_lineage_key": "伤寒论|桂枝汤|东汉|张仲景|宋本",
                    "catalog_id": "ctp:guizhi-tang",
                    "dynasty": "东汉",
                    "author": "张仲景",
                    "edition": "宋本",
                    "witness_key": "ctext:doc:observe:1",
                },
                "entity_count": 2,
                "relationship_count": 1,
                "entities": [
                    {
                        "id": "entity-formula-1",
                        "document_id": "observe-doc-1",
                        "name": "桂枝汤",
                        "type": "other",
                        "confidence": 0.95,
                        "position": 0,
                        "length": 3,
                        "alternative_names": [],
                        "description": "",
                        "entity_metadata": {
                            "raw_type": "formula",
                            "cycle_id": cycle.cycle_id,
                            "phase_execution_id": "phase-observe",
                            "document_urn": "doc:observe:1",
                            "document_title": "桂枝汤观察文档",
                        },
                        "created_at": "2026-04-12T16:41:05",
                        "updated_at": "2026-04-12T16:41:06",
                    },
                    {
                        "id": "entity-herb-1",
                        "document_id": "observe-doc-1",
                        "name": "桂枝",
                        "type": "herb",
                        "confidence": 0.93,
                        "position": 4,
                        "length": 2,
                        "alternative_names": [],
                        "description": "",
                        "entity_metadata": {
                            "raw_type": "herb",
                            "cycle_id": cycle.cycle_id,
                            "phase_execution_id": "phase-observe",
                            "document_urn": "doc:observe:1",
                            "document_title": "桂枝汤观察文档",
                        },
                        "created_at": "2026-04-12T16:41:07",
                        "updated_at": "2026-04-12T16:41:08",
                    },
                ],
                "semantic_relationships": [
                    {
                        "id": "observe-rel-1",
                        "source_entity_name": "桂枝汤",
                        "target_entity_name": "桂枝",
                        "source_entity_type": "formula",
                        "target_entity_type": "herb",
                        "relationship_type": "CONTAINS",
                        "relationship_name": "包含",
                        "confidence": 0.95,
                        "created_by_module": "observe_phase",
                        "evidence": "桂枝汤包含桂枝",
                        "relationship_metadata": {
                            "cycle_id": cycle.cycle_id,
                            "phase_execution_id": "phase-observe",
                            "document_id": "observe-doc-1",
                            "document_urn": "doc:observe:1",
                            "document_title": "桂枝汤观察文档",
                        },
                        "created_at": "2026-04-12T16:41:09",
                    }
                ],
            }
        ]

        with patch("src.storage.StorageBackendFactory", return_value=fake_factory), patch(
            "src.infrastructure.research_session_repo.ResearchSessionRepository",
            return_value=fake_repo,
        ):
            result = pipeline._persist_result(cycle)

        self.assertTrue(result)
        fake_factory.transaction.assert_called_once()
        fake_repo.replace_observe_document_graphs.assert_called_once()
        fake_txn.neo4j_batch_nodes.assert_called_once()
        fake_txn.neo4j_batch_edges.assert_called_once()

        nodes = fake_txn.neo4j_batch_nodes.call_args.args[0]
        labels = {node.label for node in nodes}
        self.assertIn("ResearchSession", labels)
        self.assertIn("ResearchPhaseExecution", labels)
        self.assertIn("ResearchArtifact", labels)
        self.assertIn("Formula", labels)
        self.assertIn("Herb", labels)
        self.assertIn("VersionWitness", labels)
        self.assertIn("VersionLineage", labels)

        session_nodes = [node for node in nodes if node.label == "ResearchSession"]
        self.assertEqual(len(session_nodes), 1)
        self.assertEqual(session_nodes[0].properties["cycle_id"], cycle.cycle_id)
        self.assertEqual(session_nodes[0].properties["created_at"], "2026-04-12T16:41:00")

        phase_nodes = {node.id: node for node in nodes if node.label == "ResearchPhaseExecution"}
        self.assertEqual(phase_nodes["phase-publish"].properties["created_at"], "2026-04-12T16:41:02")
        self.assertEqual(phase_nodes["phase-publish"].properties["cycle_id"], cycle.cycle_id)

        artifact_nodes = {node.id: node for node in nodes if node.label == "ResearchArtifact"}
        self.assertEqual(artifact_nodes["artifact-1"].properties["created_at"], "2026-04-12T16:41:03")
        self.assertEqual(artifact_nodes["artifact-1"].properties["updated_at"], "2026-04-12T16:41:04")
        self.assertEqual(artifact_nodes["artifact-1"].properties["description"], "研究报告输出")

        formula_nodes = [node for node in nodes if node.label == "Formula"]
        herb_nodes = [node for node in nodes if node.label == "Herb"]
        self.assertEqual(len(formula_nodes), 1)
        self.assertEqual(len(herb_nodes), 1)
        self.assertEqual(formula_nodes[0].properties["entity_id"], "entity-formula-1")
        self.assertEqual(herb_nodes[0].properties["entity_id"], "entity-herb-1")

        edges = fake_txn.neo4j_batch_edges.call_args.args[0]
        relationship_types = {edge.relationship_type for edge, _, _ in edges}
        self.assertIn("HAS_PHASE", relationship_types)
        self.assertIn("GENERATED", relationship_types)
        self.assertIn("CONTAINS", relationship_types)
        self.assertIn("CAPTURED", relationship_types)
        self.assertIn("OBSERVED_WITNESS", relationship_types)
        self.assertIn("BELONGS_TO_LINEAGE", relationship_types)

    def test_projects_session_phase_nodes_to_neo4j_without_observe_documents(self):
        pipeline = ResearchPipeline(
            {
                "database": {"type": "postgresql", "host": "postgres", "name": "tcmautoresearch"},
                "neo4j": {"enabled": True},
            }
        )
        cycle = _make_cycle("cycle_structured_no_docs")
        cycle.phase_executions = {
            ResearchPhase.OBSERVE: _make_phase_execution(
                "observe",
                {
                    "phase": "observe",
                    "status": "completed",
                    "ingestion_pipeline": {
                        "aggregate": {},
                    },
                    "results": {
                        "ingestion_pipeline": {
                            "aggregate": {},
                        },
                    },
                    "artifacts": [],
                    "metadata": {},
                    "error": None,
                },
                context={"question": "无文档 observe Neo4j 投影"},
            ),
        }

        fake_factory = MagicMock()
        fake_factory.initialize.return_value = {
            "db_type": "postgresql",
            "pg_status": "active",
            "neo4j_status": "active",
        }
        fake_factory.db_manager = object()
        fake_factory.neo4j_driver = object()
        fake_txn = MagicMock()
        fake_txn.pg_session = object()
        fake_factory.transaction.return_value.__enter__.return_value = fake_txn
        fake_factory.transaction.return_value.__exit__.return_value = False

        fake_repo = MagicMock()
        fake_repo.get_session.return_value = None
        fake_repo.save_from_cycle.return_value = {
            "id": "session-no-docs",
            "cycle_id": cycle.cycle_id,
            "created_at": "2026-04-12T16:50:00",
        }
        fake_repo.add_phase_execution.return_value = {
            "id": "phase-observe-no-docs",
            "phase": "observe",
            "status": "completed",
            "created_at": "2026-04-12T16:50:01",
        }
        fake_repo.replace_observe_document_graphs.return_value = []

        with patch("src.storage.StorageBackendFactory", return_value=fake_factory), patch(
            "src.infrastructure.research_session_repo.ResearchSessionRepository",
            return_value=fake_repo,
        ):
            result = pipeline._persist_result(cycle)

        self.assertTrue(result)
        fake_repo.replace_observe_document_graphs.assert_not_called()
        fake_txn.neo4j_batch_nodes.assert_called_once()
        fake_txn.neo4j_batch_edges.assert_called_once()
        fake_repo.add_artifact.assert_not_called()

        nodes = fake_txn.neo4j_batch_nodes.call_args.args[0]
        labels = {node.label for node in nodes}
        self.assertEqual(labels, {"ResearchSession", "ResearchPhaseExecution"})

        edges = fake_txn.neo4j_batch_edges.call_args.args[0]
        relationship_types = {edge.relationship_type for edge, _, _ in edges}
        self.assertEqual(relationship_types, {"HAS_PHASE"})

    def test_persists_observe_structured_philology_artifacts(self):
        pipeline = ResearchPipeline(
            {
                "database": {"type": "postgresql", "host": "postgres", "name": "tcmautoresearch"},
                "neo4j": {"enabled": False},
            }
        )
        cycle = _make_cycle("cycle_structured_philology")
        cycle.phase_executions = {
            ResearchPhase.OBSERVE: _make_phase_execution(
                "observe",
                {
                    "phase": "observe",
                    "status": "completed",
                    "results": {"ingestion_pipeline": {"aggregate": {}}},
                    "artifacts": [
                        {
                            "name": "observe_philology_terminology_table",
                            "artifact_type": "dataset",
                            "mime_type": "application/json",
                            "description": "Observe 阶段文献学术语标准表",
                            "content": {"row_count": 2, "rows": [{"canonical": "黄芪"}, {"canonical": "当归"}]},
                            "metadata": {"asset_kind": "terminology_standard_table", "row_count": 2},
                        },
                        {
                            "name": "observe_philology_collation_entries",
                            "artifact_type": "analysis",
                            "mime_type": "application/json",
                            "description": "Observe 阶段文献学校勘条目",
                            "content": {"entry_count": 1, "entries": [{"base_text": "黃芪", "witness_text": "黃耆"}]},
                            "metadata": {"asset_kind": "collation_entries", "entry_count": 1},
                        },
                        {
                            "name": "observe_philology_annotation_report",
                            "artifact_type": "report",
                            "mime_type": "application/json",
                            "description": "Observe 阶段文献学汇总报告",
                            "content": {"summary": {"processed_document_count": 1}},
                            "metadata": {"asset_kind": "annotation_report", "document_count": 1},
                        },
                    ],
                    "metadata": {},
                    "error": None,
                },
                context={"question": "验证文献学持久化产物"},
            ),
        }

        fake_factory = MagicMock()
        fake_factory.initialize.return_value = {
            "db_type": "postgresql",
            "pg_status": "active",
            "neo4j_status": "skipped",
        }
        fake_factory.db_manager = object()
        fake_factory.neo4j_driver = None
        fake_txn = MagicMock()
        fake_txn.pg_session = object()
        fake_factory.transaction.return_value.__enter__.return_value = fake_txn
        fake_factory.transaction.return_value.__exit__.return_value = False

        fake_repo = MagicMock()
        fake_repo.get_session.return_value = None
        fake_repo.save_from_cycle.return_value = {
            "id": "session-philology-artifacts",
            "cycle_id": cycle.cycle_id,
            "created_at": "2026-04-14T18:00:00",
        }
        fake_repo.add_phase_execution.return_value = {
            "id": "phase-observe-philology-artifacts",
            "phase": "observe",
            "status": "completed",
            "created_at": "2026-04-14T18:00:01",
        }
        fake_repo.replace_observe_document_graphs.return_value = []
        fake_repo.add_artifact.side_effect = lambda cycle_id, payload, session=None: {
            "id": f"artifact-{payload['name']}",
            "phase_execution_id": payload.get("phase_execution_id"),
            "name": payload["name"],
            "artifact_type": payload["artifact_type"],
            "mime_type": payload.get("mime_type"),
            "metadata": payload.get("metadata"),
            "content": payload.get("content"),
        }

        with patch("src.storage.StorageBackendFactory", return_value=fake_factory), patch(
            "src.infrastructure.research_session_repo.ResearchSessionRepository",
            return_value=fake_repo,
        ):
            result = pipeline._persist_result(cycle)

        self.assertTrue(result)
        self.assertEqual(fake_repo.add_artifact.call_count, 3)
        artifact_payloads = [call.args[1] for call in fake_repo.add_artifact.call_args_list]
        self.assertEqual(
            [payload["artifact_type"] for payload in artifact_payloads],
            ["dataset", "analysis", "report"],
        )
        self.assertTrue(all(payload["mime_type"] == "application/json" for payload in artifact_payloads))
        self.assertEqual(artifact_payloads[0]["content"]["row_count"], 2)
        self.assertEqual(artifact_payloads[1]["content"]["entry_count"], 1)
        self.assertEqual(artifact_payloads[2]["content"]["summary"]["processed_document_count"], 1)
        self.assertEqual(artifact_payloads[0]["metadata"]["asset_kind"], "terminology_standard_table")
        self.assertEqual(artifact_payloads[1]["metadata"]["asset_kind"], "collation_entries")
        self.assertEqual(artifact_payloads[2]["metadata"]["asset_kind"], "annotation_report")
        self.assertTrue(all(payload["size_bytes"] > 0 for payload in artifact_payloads))


if __name__ == "__main__":
    unittest.main()
