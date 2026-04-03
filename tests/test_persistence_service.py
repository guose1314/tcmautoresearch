"""架构 3.0 持久化层测试。"""

from __future__ import annotations

import os
import tempfile
import unittest

from src.infrastructure.persistence import PersistenceService, ResearchRecord
from src.storage.db_models import (
    DatabaseManager,
    Document,
    ProcessStatusEnum,
    RelationshipType,
)


class TestPersistenceService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "persistence.db")
        self.service = PersistenceService(
            {
                "database": {
                    "type": "sqlite",
                    "path": self.db_path,
                }
            }
        )
        initialized = self.service.initialize()
        self.assertTrue(initialized)

    def tearDown(self) -> None:
        self.service.cleanup()
        self.tmpdir.cleanup()

    def test_persist_document_graph_and_query_snapshot(self) -> None:
        result = self.service.execute(
            {
                "entity_type": "document_graph",
                "operation": "upsert",
                "data": {
                    "document": {
                        "source_file": "tests/sample_classic.txt",
                        "objective": "验证持久化层",
                        "raw_text_size": 2048,
                        "process_status": "completed",
                        "quality_score": 0.93,
                    },
                    "entities": [
                        {"name": "小柴胡汤", "type": "formula", "confidence": 0.98, "position": 0, "length": 4},
                        {"name": "柴胡", "type": "herb", "confidence": 0.97, "position": 12, "length": 2},
                        {"name": "少阳证", "type": "syndrome", "confidence": 0.92, "position": 20, "length": 3},
                    ],
                    "relationships": [
                        {
                            "source_entity_name": "小柴胡汤",
                            "target_entity_name": "柴胡",
                            "relationship_type": "CONTAINS",
                            "confidence": 0.99,
                        },
                        {
                            "source_entity_name": "小柴胡汤",
                            "target_entity_name": "少阳证",
                            "relationship_type": "TREATS",
                            "confidence": 0.81,
                        },
                    ],
                    "statistics": {
                        "formulas_count": 1,
                        "herbs_count": 1,
                        "syndromes_count": 1,
                        "relationships_count": 2,
                        "graph_nodes_count": 3,
                        "graph_edges_count": 2,
                        "graph_density": 0.66,
                        "source_modules": ["entity_extractor", "semantic_graph_builder"],
                    },
                    "quality_metrics": {
                        "confidence_score": 0.93,
                        "completeness": 0.9,
                        "entity_precision": 0.91,
                        "relationship_precision": 0.89,
                        "graph_quality_score": 0.92,
                        "evaluator": "unit-test",
                    },
                    "research_analysis": {
                        "summary_analysis": {"finding": "小柴胡汤与少阳证关联显著"},
                        "research_perspectives": {"formula": "和解少阳"},
                    },
                    "logs": [
                        {
                            "module_name": "entity_extractor",
                            "status": "success",
                            "message": "entities extracted",
                            "execution_time_ms": 15,
                        }
                    ],
                },
            }
        )

        self.assertTrue(result["found"])
        self.assertEqual(result["entity_count"], 3)
        self.assertEqual(result["relationship_count"], 2)
        self.assertEqual(result["document"]["process_status"], "completed")
        self.assertEqual(result["statistics"]["relationships_count"], 2)
        self.assertEqual(result["quality_metrics"]["evaluator"], "unit-test")
        self.assertEqual(result["research_analysis"]["summary_analysis"]["finding"], "小柴胡汤与少阳证关联显著")

        snapshot = self.service.get_document_snapshot(document_id=result["document"]["id"])
        self.assertTrue(snapshot["found"])
        self.assertEqual(snapshot["document"]["source_file"], "tests/sample_classic.txt")
        self.assertEqual(len(snapshot["logs"]), 1)

    def test_persist_research_record_upsert(self) -> None:
        first = self.service.persist_research_record(
            {
                "cycle_id": "cycle_001",
                "cycle_name": "持久化回归",
                "status": "completed",
                "current_phase": "publish",
                "started_at": "2026-03-31T10:00:00",
                "completed_at": "2026-03-31T10:30:00",
                "duration": 1800.0,
                "research_objective": "验证 ORM 研究记录写入",
                "outcomes": [{"phase": "analyze", "result": {"summary": "ok"}}],
                "metadata": {"operator": "unit-test"},
            }
        )
        second = self.service.persist_research_record(
            {
                "cycle_id": "cycle_001",
                "cycle_name": "持久化回归",
                "status": "failed",
                "current_phase": "reflect",
                "duration": 2000.0,
                "outcomes": [{"phase": "reflect", "result": {"summary": "retry"}}],
                "metadata": {"operator": "unit-test", "retry": True},
            }
        )

        self.assertEqual(first["cycle_id"], "cycle_001")
        self.assertEqual(second["status"], "failed")
        self.assertEqual(second["current_phase"], "reflect")
        self.assertEqual(second["metadata"]["retry"], True)

        fetched = self.service.execute(
            {
                "entity_type": "research_record",
                "operation": "get",
                "data": {"cycle_id": "cycle_001"},
            }
        )
        self.assertTrue(fetched["found"])
        self.assertEqual(fetched["status"], "failed")

        manager = self.service.database_manager
        self.assertIsNotNone(manager)
        with manager.session_scope() as session:
            self.assertEqual(session.query(ResearchRecord).count(), 1)

    def test_legacy_storage_compatibility_uses_new_models(self) -> None:
        compat_db = os.path.join(self.tmpdir.name, "compat.db")
        manager = DatabaseManager(f"sqlite:///{compat_db}")
        manager.init_db()
        with manager.session_scope() as session:
            DatabaseManager.create_default_relationships(session)
            session.add(
                Document(
                    source_file="compat-source.txt",
                    process_status=ProcessStatusEnum.PENDING,
                    raw_text_size=128,
                )
            )

        with manager.session_scope() as session:
            self.assertGreaterEqual(session.query(RelationshipType).count(), 8)
            stored = session.query(Document).filter_by(source_file="compat-source.txt").one()
            self.assertEqual(stored.process_status.value, "pending")
            self.assertEqual(stored.raw_text_size, 128)

        manager.close()


if __name__ == "__main__":
    unittest.main()