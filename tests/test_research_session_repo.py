"""P3.1 ResearchSession 持久化 — 单元测试。

使用 SQLite :memory: 数据库，无外部依赖。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from src.infrastructure.persistence import (
    ArtifactTypeEnum,
    Base,
    DatabaseManager,
    Document,
    PhaseExecution,
    PhaseStatusEnum,
    ResearchArtifact,
    ResearchSession,
    SessionStatusEnum,
)
from src.infrastructure.research_session_repo import (
    ResearchSessionRepository,
    _parse_datetime,
    _to_artifact_type,
    _to_phase_status,
    _to_session_status,
)
from src.storage.neo4j_driver import Neo4jDriver, Neo4jEdge
from src.storage.transaction import TransactionCoordinator


class _RecordingNeo4jTx:
    def __init__(self, backend):
        self._backend = backend

    def run(self, query, **params):
        self._backend.executed_queries.append((query, params))
        if query in self._backend.fail_on_queries:
            raise RuntimeError(f"blocked: {query}")


class _RecordingNeo4jSession:
    def __init__(self, backend):
        self._backend = backend

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute_write(self, callback):
        return callback(_RecordingNeo4jTx(self._backend))


class _RecordingNeo4jDriver:
    def __init__(self, fail_on_queries=None):
        self.driver = self
        self.database = "neo4j"
        self.fail_on_queries = set(fail_on_queries or [])
        self.executed_queries = []

    def session(self, database=None):
        return _RecordingNeo4jSession(self)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_manager():
    mgr = DatabaseManager("sqlite:///:memory:")
    mgr.init_db()
    yield mgr
    mgr.close()


@pytest.fixture()
def repo(db_manager):
    return ResearchSessionRepository(db_manager)


def _make_payload(**overrides):
    base = {
        "cycle_id": f"test-{uuid.uuid4().hex[:8]}",
        "cycle_name": "测试会话",
        "description": "单元测试创建",
        "research_objective": "验证持久化",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 枚举转换
# ---------------------------------------------------------------------------

class TestEnumConversion:
    def test_to_session_status_from_string(self):
        assert _to_session_status("active") == SessionStatusEnum.ACTIVE

    def test_to_session_status_from_enum(self):
        assert _to_session_status(SessionStatusEnum.FAILED) == SessionStatusEnum.FAILED

    def test_to_session_status_fallback(self):
        assert _to_session_status("invalid") == SessionStatusEnum.PENDING

    def test_to_phase_status_from_string(self):
        assert _to_phase_status("running") == PhaseStatusEnum.RUNNING

    def test_to_phase_status_fallback(self):
        assert _to_phase_status("xyz") == PhaseStatusEnum.PENDING

    def test_to_artifact_type_from_string(self):
        assert _to_artifact_type("paper") == ArtifactTypeEnum.PAPER

    def test_to_artifact_type_fallback(self):
        assert _to_artifact_type("xyz") == ArtifactTypeEnum.OTHER

    def test_parse_datetime_none(self):
        assert _parse_datetime(None) is None

    def test_parse_datetime_string(self):
        dt = _parse_datetime("2026-01-01T12:00:00")
        assert isinstance(dt, datetime)
        assert dt.year == 2026

    def test_parse_datetime_object(self):
        now = datetime.utcnow()
        assert _parse_datetime(now) is now


# ---------------------------------------------------------------------------
# ORM 模型基础
# ---------------------------------------------------------------------------

class TestORMModels:
    def test_research_session_table_created(self, db_manager):
        assert "research_sessions" in Base.metadata.tables

    def test_phase_execution_table_created(self, db_manager):
        assert "phase_executions" in Base.metadata.tables

    def test_research_artifact_table_created(self, db_manager):
        assert "research_artifacts" in Base.metadata.tables

    def test_session_status_enum_values(self):
        values = {e.value for e in SessionStatusEnum}
        assert values == {"pending", "active", "completed", "failed", "suspended"}

    def test_phase_status_enum_values(self):
        values = {e.value for e in PhaseStatusEnum}
        assert values == {"pending", "running", "completed", "failed", "skipped"}

    def test_artifact_type_enum_values(self):
        values = {e.value for e in ArtifactTypeEnum}
        assert "paper" in values
        assert "dataset" in values
        assert "other" in values


# ---------------------------------------------------------------------------
# 会话 CRUD
# ---------------------------------------------------------------------------

class TestSessionCRUD:
    def test_create_session(self, repo):
        result = repo.create_session(_make_payload())
        assert result["cycle_name"] == "测试会话"
        assert result["status"] == "pending"
        assert result["id"]  # UUID assigned
        assert result["created_at"] is not None

    def test_get_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        result = repo.get_session(payload["cycle_id"])
        assert result is not None
        assert result["cycle_id"] == payload["cycle_id"]

    def test_get_session_not_found(self, repo):
        assert repo.get_session("nonexistent") is None

    def test_get_session_by_id(self, repo):
        created = repo.create_session(_make_payload())
        result = repo.get_session_by_id(uuid.UUID(created["id"]))
        assert result is not None
        assert result["cycle_name"] == "测试会话"

    def test_update_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        result = repo.update_session(payload["cycle_id"], {
            "cycle_name": "更新后的名称",
            "budget": 5000.0,
            "tags": ["中医", "方剂"],
        })
        assert result["cycle_name"] == "更新后的名称"
        assert result["budget"] == 5000.0
        assert result["tags"] == ["中医", "方剂"]

    def test_update_session_not_found(self, repo):
        assert repo.update_session("nonexistent", {"status": "active"}) is None

    def test_delete_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        assert repo.delete_session(payload["cycle_id"]) is True
        assert repo.get_session(payload["cycle_id"]) is None

    def test_delete_session_not_found(self, repo):
        assert repo.delete_session("nonexistent") is False

    def test_list_sessions_empty(self, repo):
        result = repo.list_sessions()
        assert result["total"] == 0
        assert result["items"] == []

    def test_list_sessions_pagination(self, repo):
        for i in range(5):
            repo.create_session(_make_payload(cycle_name=f"会话{i}"))
        result = repo.list_sessions(limit=2, offset=0)
        assert result["total"] == 5
        assert len(result["items"]) == 2
        result2 = repo.list_sessions(limit=2, offset=4)
        assert len(result2["items"]) == 1

    def test_list_sessions_filter_status(self, repo):
        repo.create_session(_make_payload())
        repo.create_session(_make_payload(status="active"))
        result = repo.list_sessions(status="active")
        assert result["total"] == 1
        assert result["items"][0]["status"] == "active"


# ---------------------------------------------------------------------------
# 状态转换
# ---------------------------------------------------------------------------

class TestStatusTransitions:
    def test_start_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        result = repo.start_session(payload["cycle_id"])
        assert result["status"] == "active"
        assert result["started_at"] is not None

    def test_complete_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        result = repo.complete_session(payload["cycle_id"])
        assert result["status"] == "completed"
        assert result["completed_at"] is not None

    def test_fail_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        result = repo.fail_session(payload["cycle_id"])
        assert result["status"] == "failed"

    def test_suspend_session(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        result = repo.suspend_session(payload["cycle_id"])
        assert result["status"] == "suspended"


# ---------------------------------------------------------------------------
# 阶段执行
# ---------------------------------------------------------------------------

class TestPhaseExecution:
    def test_add_phase_execution(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        pe = repo.add_phase_execution(session_payload["cycle_id"], {
            "phase": "observe",
            "status": "running",
            "input": {"topic": "麻黄汤"},
        })
        assert pe is not None
        assert pe["phase"] == "observe"
        assert pe["status"] == "running"
        assert pe["input"] == {"topic": "麻黄汤"}

    def test_add_phase_execution_nonexistent_session(self, repo):
        assert repo.add_phase_execution("nonexistent", {"phase": "observe"}) is None

    def test_update_phase_execution(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        pe = repo.add_phase_execution(session_payload["cycle_id"], {
            "phase": "hypothesis",
        })
        updated = repo.update_phase_execution(uuid.UUID(pe["id"]), {
            "status": "completed",
            "duration": 12.5,
            "output": {"hypothesis": "麻黄汤可治表寒证"},
        })
        assert updated["status"] == "completed"
        assert updated["duration"] == 12.5
        assert updated["output"]["hypothesis"] == "麻黄汤可治表寒证"

    def test_update_phase_execution_not_found(self, repo):
        assert repo.update_phase_execution(uuid.uuid4(), {"status": "failed"}) is None

    def test_list_phase_executions(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        for phase in ("observe", "hypothesis", "experiment"):
            repo.add_phase_execution(session_payload["cycle_id"], {"phase": phase})
        phases = repo.list_phase_executions(session_payload["cycle_id"])
        assert len(phases) == 3
        assert sorted(p["phase"] for p in phases) == ["experiment", "hypothesis", "observe"]

    def test_list_phase_executions_nonexistent_session(self, repo):
        assert repo.list_phase_executions("nonexistent") == []


# ---------------------------------------------------------------------------
# 工件
# ---------------------------------------------------------------------------

class TestArtifact:
    def test_add_artifact(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        art = repo.add_artifact(session_payload["cycle_id"], {
            "name": "麻黄汤分析报告",
            "artifact_type": "report",
            "content": {"summary": "报告正文"},
            "size_bytes": 1024,
        })
        assert art is not None
        assert art["name"] == "麻黄汤分析报告"
        assert art["artifact_type"] == "report"
        assert art["content"] == {"summary": "报告正文"}

    def test_add_artifact_nonexistent_session(self, repo):
        assert repo.add_artifact("nonexistent", {"name": "test"}) is None

    def test_add_artifact_with_phase(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        pe = repo.add_phase_execution(session_payload["cycle_id"], {"phase": "analyze"})
        art = repo.add_artifact(session_payload["cycle_id"], {
            "name": "方剂对比数据集",
            "artifact_type": "dataset",
            "phase_execution_id": pe["id"],
        })
        assert art["phase_execution_id"] == pe["id"]

    def test_list_artifacts(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        repo.add_artifact(session_payload["cycle_id"], {"name": "a1", "artifact_type": "paper"})
        repo.add_artifact(session_payload["cycle_id"], {"name": "a2", "artifact_type": "dataset"})
        arts = repo.list_artifacts(session_payload["cycle_id"])
        assert len(arts) == 2

    def test_list_artifacts_filter_type(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        repo.add_artifact(session_payload["cycle_id"], {"name": "a1", "artifact_type": "paper"})
        repo.add_artifact(session_payload["cycle_id"], {"name": "a2", "artifact_type": "dataset"})
        arts = repo.list_artifacts(session_payload["cycle_id"], artifact_type="paper")
        assert len(arts) == 1
        assert arts[0]["artifact_type"] == "paper"

    def test_delete_artifact(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        art = repo.add_artifact(session_payload["cycle_id"], {"name": "to-delete"})
        assert repo.delete_artifact(uuid.UUID(art["id"])) is True
        assert repo.list_artifacts(session_payload["cycle_id"]) == []

    def test_delete_artifact_not_found(self, repo):
        assert repo.delete_artifact(uuid.uuid4()) is False


# ---------------------------------------------------------------------------
# Observe 文档图谱
# ---------------------------------------------------------------------------

class TestObserveDocumentGraph:
    def test_replace_observe_document_graphs_persists_entities_and_relationships(self, repo):
        session_payload = _make_payload(cycle_id="observe-cycle")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe", "status": "completed"})

        snapshots = repo.replace_observe_document_graphs(
            session_payload["cycle_id"],
            phase["id"],
            [
                {
                    "urn": "doc:observe:1",
                    "title": "观察文档一",
                    "source_type": "ctext",
                    "raw_text_size": 128,
                    "processed_text_size": 120,
                    "entity_count": 2,
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
                            "witness_key": "ctext:ctp:shang-han-lun/bian-mai-fa",
                        }
                    },
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
                    "output_generation": {"quality_metrics": {"confidence_score": 0.91}},
                }
            ],
        )

        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot["phase_execution_id"] == phase["id"]
        assert snapshot["entity_count"] == 2
        assert snapshot["relationship_count"] == 1
        assert snapshot["entities"][0]["entity_metadata"]["cycle_id"] == session_payload["cycle_id"]
        assert snapshot["semantic_relationships"][0]["relationship_type"] == "CONTAINS"
        assert snapshot["semantic_relationships"][0]["source_entity_type"] == "formula"
        assert snapshot["source_type"] == "ctext"
        assert snapshot["version_metadata"]["catalog_id"] == "ctp:shang-han-lun/bian-mai-fa"
        assert snapshot["version_metadata"]["version_lineage_key"] == "伤寒论|辨脉法|东汉|张仲景|宋本"

    def test_get_full_snapshot_includes_observe_documents(self, repo):
        session_payload = _make_payload(cycle_id="observe-snapshot")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe", "status": "completed"})
        repo.replace_observe_document_graphs(
            session_payload["cycle_id"],
            phase["id"],
            [
                {
                    "urn": "doc:observe:1",
                    "title": "观察文档一",
                    "source_type": "ctext",
                    "raw_text_size": 128,
                    "entity_count": 1,
                    "metadata": {
                        "version_metadata": {
                            "work_title": "黄帝内经",
                            "fragment_title": "上古天真论",
                            "work_fragment_key": "黄帝内经|上古天真论",
                            "version_lineage_key": "黄帝内经|上古天真论|先秦至汉|佚名|CTP本",
                            "catalog_id": "ctp:huangdi-neijing/shang-gu-tian-zhen-lun",
                            "dynasty": "先秦至汉",
                            "author": "佚名",
                            "edition": "CTP本",
                            "witness_key": "ctext:ctp:huangdi-neijing/shang-gu-tian-zhen-lun",
                        }
                    },
                    "entities": [
                        {"name": "桂枝汤", "type": "formula", "confidence": 0.95, "position": 0, "length": 3},
                    ],
                    "semantic_relationships": [],
                }
            ],
        )

        snapshot = repo.get_full_snapshot(session_payload["cycle_id"])

        assert snapshot is not None
        assert len(snapshot["observe_documents"]) == 1
        assert snapshot["observe_documents"][0]["entity_count"] == 1
        assert snapshot["observe_documents"][0]["title"] == "观察文档一"
        assert len(snapshot["version_lineages"]) == 1
        assert snapshot["version_lineages"][0]["witness_count"] == 1
        assert snapshot["version_lineages"][0]["work_title"] == "黄帝内经"

    def test_list_observe_version_lineages_groups_multiple_witnesses(self, repo):
        session_payload = _make_payload(cycle_id="observe-lineage")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe", "status": "completed"})

        repo.replace_observe_document_graphs(
            session_payload["cycle_id"],
            phase["id"],
            [
                {
                    "urn": "doc:observe:1",
                    "title": "伤寒论宋本",
                    "source_type": "ctext",
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
                    "entities": [],
                    "semantic_relationships": [],
                },
                {
                    "urn": "doc:observe:2",
                    "title": "伤寒论影印本",
                    "source_type": "archive_org",
                    "metadata": {
                        "version_metadata": {
                            "work_title": "伤寒论",
                            "fragment_title": "辨脉法",
                            "work_fragment_key": "伤寒论|辨脉法",
                            "version_lineage_key": "伤寒论|辨脉法|东汉|张仲景|宋本",
                            "catalog_id": "archive_org",
                            "dynasty": "东汉",
                            "author": "张仲景",
                            "edition": "宋本",
                            "witness_key": "archive_org:doc:2",
                        }
                    },
                    "entities": [],
                    "semantic_relationships": [],
                },
            ],
        )

        lineages = repo.list_observe_version_lineages(session_payload["cycle_id"])

        assert len(lineages) == 1
        assert lineages[0]["witness_count"] == 2
        assert {w["catalog_id"] for w in lineages[0]["witnesses"]} == {"ctp:shang-han-lun/bian-mai-fa", "archive_org"}

    def test_list_observe_document_graphs_derives_version_metadata_for_legacy_rows(self, repo, db_manager):
        session_payload = _make_payload(cycle_id="observe-legacy-lineage")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe", "status": "completed"})

        snapshots = repo.replace_observe_document_graphs(
            session_payload["cycle_id"],
            phase["id"],
            [
                {
                    "urn": r"C:\Users\hgk\tcmautoresearch\data\013-本草纲目-明-李时珍.txt",
                    "title": "本草纲目-明-李时珍",
                    "entities": [],
                    "semantic_relationships": [],
                }
            ],
        )

        document_id = snapshots[0]["id"]
        session = db_manager.get_session()
        try:
            document = session.get(Document, uuid.UUID(document_id))
            assert document is not None
            document.document_urn = None
            document.document_title = None
            document.source_type = None
            document.catalog_id = None
            document.work_title = None
            document.fragment_title = None
            document.work_fragment_key = None
            document.version_lineage_key = None
            document.witness_key = None
            document.dynasty = None
            document.author = None
            document.edition = None
            document.version_metadata_json = {}
            document.notes = json.dumps(
                {
                    "cycle_id": session_payload["cycle_id"],
                    "phase": "observe",
                    "phase_execution_id": phase["id"],
                    "document_index": 0,
                    "urn": r"C:\Users\hgk\tcmautoresearch\data\013-本草纲目-明-李时珍.txt",
                    "title": "本草纲目-明-李时珍",
                },
                ensure_ascii=False,
            )
            session.commit()
        finally:
            session.close()
            db_manager.remove_session()

        legacy_snapshot = repo.list_observe_document_graphs(session_payload["cycle_id"])[0]

        assert legacy_snapshot["source_type"] == "local"
        assert legacy_snapshot["work_title"] == "本草纲目"
        assert legacy_snapshot["dynasty"] == "明"
        assert legacy_snapshot["author"] == "李时珍"
        assert legacy_snapshot["version_metadata"]["catalog_id"].endswith("013-本草纲目-明-李时珍.txt")
        assert legacy_snapshot["version_metadata"]["version_lineage_key"]

    def test_backfill_observe_document_version_metadata_persists_legacy_rows(self, repo, db_manager):
        session_payload = _make_payload(cycle_id="observe-legacy-writeback")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe", "status": "completed"})

        snapshots = repo.replace_observe_document_graphs(
            session_payload["cycle_id"],
            phase["id"],
            [
                {
                    "urn": r"C:\Users\hgk\tcmautoresearch\data\013-本草纲目-明-李时珍.txt",
                    "title": "本草纲目-明-李时珍",
                    "entities": [],
                    "semantic_relationships": [],
                }
            ],
        )

        document_id = snapshots[0]["id"]
        session = db_manager.get_session()
        try:
            document = session.get(Document, uuid.UUID(document_id))
            assert document is not None
            document.document_urn = None
            document.document_title = None
            document.source_type = None
            document.catalog_id = None
            document.work_title = None
            document.fragment_title = None
            document.work_fragment_key = None
            document.version_lineage_key = None
            document.witness_key = None
            document.dynasty = None
            document.author = None
            document.edition = None
            document.version_metadata_json = {}
            document.notes = json.dumps(
                {
                    "cycle_id": session_payload["cycle_id"],
                    "phase": "observe",
                    "phase_execution_id": phase["id"],
                    "document_index": 0,
                    "urn": r"C:\Users\hgk\tcmautoresearch\data\013-本草纲目-明-李时珍.txt",
                    "title": "本草纲目-明-李时珍",
                },
                ensure_ascii=False,
            )
            session.commit()
        finally:
            session.close()
            db_manager.remove_session()

        summary = repo.backfill_observe_document_version_metadata(session_payload["cycle_id"])

        session = db_manager.get_session()
        try:
            document = session.get(Document, uuid.UUID(document_id))
            assert document is not None
            notes = json.loads(document.notes)
        finally:
            session.close()
            db_manager.remove_session()

        assert summary["scanned_document_count"] == 1
        assert summary["updated_document_count"] == 1
        assert document.document_urn and document.document_urn.endswith("013-本草纲目-明-李时珍.txt")
        assert document.document_title == "本草纲目-明-李时珍"
        assert document.source_type == "local"
        assert document.work_title == "本草纲目"
        assert document.fragment_title == "本草纲目"
        assert document.dynasty == "明"
        assert document.author == "李时珍"
        assert document.version_lineage_key
        assert document.version_metadata_json["catalog_id"].endswith("013-本草纲目-明-李时珍.txt")
        assert notes["source_type"] == "local"
        assert notes["version_metadata"]["version_lineage_key"] == document.version_lineage_key

    def test_backfill_observe_philology_artifacts_persists_from_phase_output(self, repo):
        session_payload = _make_payload(cycle_id="observe-philology-backfill")
        repo.create_session(session_payload)
        observe_output = {
            "phase": "observe",
            "status": "completed",
            "results": {
                "ingestion_pipeline": {
                    "documents": [],
                    "aggregate": {
                        "philology_assets": {
                            "terminology_standard_table": [
                                {
                                    "document_title": "补血汤宋本",
                                    "document_urn": "doc:observe:philology:1",
                                    "canonical": "黄芪",
                                    "label": "本草药名",
                                    "status": "standardized",
                                    "observed_forms": ["黃芪"],
                                    "configured_variants": ["黃耆"],
                                    "sources": ["normalizer_term_mapping"],
                                    "notes": ["黃芪 统一为 黄芪（本草药名）"],
                                }
                            ],
                            "collation_entries": [
                                {
                                    "document_title": "补血汤宋本",
                                    "document_urn": "doc:observe:philology:1",
                                    "difference_type": "replace",
                                    "base_text": "黃芪",
                                    "witness_text": "黃耆",
                                    "judgement": "异体字通用",
                                    "base_context": "黃芪當歸",
                                    "witness_context": "黃耆當歸",
                                }
                            ],
                            "annotation_report": {
                                "summary": {
                                    "processed_document_count": 1,
                                    "philology_document_count": 1,
                                    "term_mapping_count": 1,
                                    "orthographic_variant_count": 1,
                                    "recognized_term_count": 1,
                                    "terminology_standard_table_count": 1,
                                    "version_collation_difference_count": 1,
                                    "version_collation_witness_count": 1,
                                    "collation_entry_count": 1,
                                    "philology_notes": ["输出 1 条可复用校勘条目"],
                                },
                                "documents": [
                                    {
                                        "document_title": "补血汤宋本",
                                        "document_urn": "doc:observe:philology:1",
                                        "source_type": "ctext",
                                        "mapping_count": 1,
                                        "recognized_term_count": 1,
                                        "terminology_standard_table_count": 1,
                                        "difference_count": 1,
                                        "collation_entry_count": 1,
                                        "witness_count": 1,
                                        "philology_notes": ["输出 1 条可复用校勘条目"],
                                    }
                                ],
                            },
                        }
                    },
                }
            },
            "artifacts": [],
            "metadata": {},
            "error": None,
        }
        phase = repo.add_phase_execution(
            session_payload["cycle_id"],
            {"phase": "observe", "status": "completed", "output": observe_output},
        )

        summary = repo.backfill_observe_philology_artifacts(session_payload["cycle_id"])
        artifacts = {
            artifact["name"]: artifact
            for artifact in repo.list_artifacts(session_payload["cycle_id"])
            if artifact.get("phase_execution_id") == phase["id"]
        }
        snapshot = repo.get_full_snapshot(session_payload["cycle_id"])

        assert summary["scanned_phase_count"] == 1
        assert summary["updated_phase_count"] == 1
        assert summary["created_artifact_count"] == 3
        assert set(artifacts) == {
            "observe_philology_terminology_table",
            "observe_philology_collation_entries",
            "observe_philology_annotation_report",
        }
        assert artifacts["observe_philology_terminology_table"]["artifact_type"] == "dataset"
        assert artifacts["observe_philology_terminology_table"]["content"]["rows"][0]["canonical"] == "黄芪"
        assert artifacts["observe_philology_collation_entries"]["content"]["entries"][0]["witness_text"] == "黃耆"
        assert artifacts["observe_philology_annotation_report"]["content"]["summary"]["collation_entry_count"] == 1
        assert snapshot is not None
        assert snapshot["observe_philology"]["terminology_standard_table_count"] == 1
        assert snapshot["observe_philology"]["collation_entry_count"] == 1
        assert snapshot["observe_philology"]["source"] == "artifacts"

    def test_backfill_observe_philology_artifacts_skips_sessions_without_philology(self, repo):
        session_payload = _make_payload(cycle_id="observe-philology-backfill-skip")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "observe",
                "status": "completed",
                "output": {
                    "phase": "observe",
                    "status": "completed",
                    "results": {
                        "ingestion_pipeline": {
                            "documents": [
                                {
                                    "urn": "doc:observe:plain:1",
                                    "title": "普通观察文档",
                                    "entities": [],
                                    "semantic_relationships": [],
                                }
                            ],
                            "aggregate": {
                                "total_entities": 0,
                                "entity_type_counts": {},
                                "average_confidence": 0.0,
                            },
                        }
                    },
                    "artifacts": [],
                    "metadata": {},
                    "error": None,
                },
            },
        )

        summary = repo.backfill_observe_philology_artifacts(session_payload["cycle_id"])
        artifacts = [
            artifact
            for artifact in repo.list_artifacts(session_payload["cycle_id"])
            if artifact.get("phase_execution_id") == phase["id"]
        ]

        assert summary["scanned_phase_count"] == 1
        assert summary["updated_phase_count"] == 0
        assert summary["created_artifact_count"] == 0
        assert artifacts == []

    def test_external_transaction_rolls_back_observe_graph_on_neo4j_failure(self, db_manager, repo):
        session_payload = _make_payload(cycle_id="observe-txn-rollback")
        neo4j_driver = _RecordingNeo4jDriver(fail_on_queries={"CREATE second"})
        session = db_manager.get_session()

        with pytest.raises(RuntimeError, match="事务提交失败"):
            with TransactionCoordinator(session, neo4j_driver) as txn:
                repo.create_session(session_payload, session=txn.pg_session)
                phase = repo.add_phase_execution(
                    session_payload["cycle_id"],
                    {"phase": "observe", "status": "completed"},
                    session=txn.pg_session,
                )
                repo.replace_observe_document_graphs(
                    session_payload["cycle_id"],
                    phase["id"],
                    [
                        {
                            "urn": "doc:observe:rollback",
                            "title": "事务回滚观察文档",
                            "entity_count": 1,
                            "entities": [
                                {"name": "麻黄汤", "type": "formula", "confidence": 0.95, "position": 0, "length": 3},
                            ],
                            "semantic_relationships": [],
                        }
                    ],
                    session=txn.pg_session,
                )
                txn.neo4j_write("CREATE first", compensate_cypher="DELETE first", id=1)
                txn.neo4j_write("CREATE second", compensate_cypher="DELETE second", id=2)

        session.close()
        db_manager.remove_session()

        assert repo.get_session(session_payload["cycle_id"]) is None
        assert repo.list_observe_document_graphs(session_payload["cycle_id"]) == []
        assert neo4j_driver.executed_queries == [
            ("CREATE first", {"id": 1}),
            ("CREATE second", {"id": 2}),
            ("DELETE first", {"id": 1}),
        ]

    def test_transaction_batch_edges_uses_split_match_clauses(self, db_manager):
        neo4j_driver = _RecordingNeo4jDriver()
        session = db_manager.get_session()

        try:
            with TransactionCoordinator(session, neo4j_driver) as txn:
                txn.neo4j_batch_edges(
                    [
                        (
                            Neo4jEdge(
                                source_id="session-1",
                                target_id="phase-1",
                                relationship_type="HAS_PHASE",
                                properties={"cycle_id": "session-1", "phase": "observe"},
                            ),
                            "ResearchSession",
                            "ResearchPhaseExecution",
                        ),
                        (
                            Neo4jEdge(
                                source_id="phase-1",
                                target_id="artifact-1",
                                relationship_type="GENERATED",
                                properties={"cycle_id": "session-1"},
                            ),
                            "ResearchPhaseExecution",
                            "ResearchArtifact",
                        ),
                    ],
                    compensate=False,
                )
        finally:
            session.close()
            db_manager.remove_session()

        assert len(neo4j_driver.executed_queries) == 2
        first_query, first_params = neo4j_driver.executed_queries[0]
        second_query, second_params = neo4j_driver.executed_queries[1]

        assert "MATCH (a:ResearchSession {id: $src_id}) MATCH (b:ResearchPhaseExecution {id: $tgt_id})" in first_query
        assert ", (b:ResearchPhaseExecution {id: $tgt_id})" not in first_query
        assert "MERGE (a)-[r:HAS_PHASE]->(b)" in first_query
        assert first_params == {
            "src_id": "session-1",
            "tgt_id": "phase-1",
            "props": {"cycle_id": "session-1", "phase": "observe"},
        }

        assert "MATCH (a:ResearchPhaseExecution {id: $src_id}) MATCH (b:ResearchArtifact {id: $tgt_id})" in second_query
        assert ", (b:ResearchArtifact {id: $tgt_id})" not in second_query
        assert "MERGE (a)-[r:GENERATED]->(b)" in second_query
        assert second_params == {
            "src_id": "phase-1",
            "tgt_id": "artifact-1",
            "props": {"cycle_id": "session-1"},
        }

    def test_neo4j_driver_relationship_writes_use_split_match_clauses(self):
        backend = _RecordingNeo4jDriver()
        driver = Neo4jDriver("neo4j://unit-test", ("neo4j", "password"))
        driver.driver = backend

        single_edge = Neo4jEdge(
            source_id="session-1",
            target_id="phase-1",
            relationship_type="HAS_PHASE",
            properties={"phase": "observe"},
        )

        assert driver.create_relationship(
            single_edge,
            "ResearchSession",
            "ResearchPhaseExecution",
        ) is True

        single_query, single_params = backend.executed_queries[0]
        assert "MATCH (source:ResearchSession {id: $source_id})" in single_query
        assert "MATCH (target:ResearchPhaseExecution {id: $target_id})" in single_query
        assert ", (target:ResearchPhaseExecution {id: $target_id})" not in single_query
        assert "MERGE (source)-[r:HAS_PHASE]->(target)" in single_query
        assert single_params == {
            "source_id": "session-1",
            "target_id": "phase-1",
            "properties": {"phase": "observe"},
        }

        backend.executed_queries.clear()

        batch_edge = Neo4jEdge(
            source_id="phase-1",
            target_id="artifact-1",
            relationship_type="GENERATED",
            properties={"cycle_id": "session-1"},
        )

        assert driver.batch_create_relationships(
            [
                (
                    batch_edge,
                    "ResearchPhaseExecution",
                    "ResearchArtifact",
                )
            ]
        ) is True

        batch_query, batch_params = backend.executed_queries[0]
        assert "MATCH (source:ResearchPhaseExecution {id: row.source_id})" in batch_query
        assert "MATCH (target:ResearchArtifact {id: row.target_id})" in batch_query
        assert ", (target:ResearchArtifact {id: row.target_id})" not in batch_query
        assert "MERGE (source)-[r:GENERATED]->(target)" in batch_query
        assert batch_params == {
            "rows": [
                {
                    "source_id": "phase-1",
                    "target_id": "artifact-1",
                    "properties": {"cycle_id": "session-1"},
                }
            ]
        }


# ---------------------------------------------------------------------------
# 全快照
# ---------------------------------------------------------------------------

class TestFullSnapshot:
    def test_get_full_snapshot(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe"})
        repo.add_artifact(session_payload["cycle_id"], {"name": "snap-art"})
        snap = repo.get_full_snapshot(session_payload["cycle_id"])
        assert snap is not None
        assert len(snap["phase_executions"]) == 1
        assert len(snap["artifacts"]) == 1
        assert snap["cycle_name"] == "测试会话"

    def test_get_full_snapshot_not_found(self, repo):
        assert repo.get_full_snapshot("nonexistent") is None


# ---------------------------------------------------------------------------
# ResearchCycle 互转
# ---------------------------------------------------------------------------

class TestCycleConversion:
    def test_save_from_cycle_create(self, repo):
        from src.research.study_session_manager import (
            ResearchCycle,
            ResearchCycleStatus,
            ResearchPhase,
        )

        cycle = ResearchCycle(
            cycle_id="cycle-from-dc",
            cycle_name="dataclass 会话",
            description="从 dataclass 创建",
            status=ResearchCycleStatus.ACTIVE,
            current_phase=ResearchPhase.OBSERVE,
            researchers=["张三"],
            tags=["测试"],
        )
        result = repo.save_from_cycle(cycle)
        assert result["cycle_id"] == "cycle-from-dc"
        assert result["status"] == "active"
        assert result["researchers"] == ["张三"]
        assert result["tags"] == ["测试"]

    def test_save_from_cycle_update(self, repo):
        from src.research.study_session_manager import (
            ResearchCycle,
            ResearchCycleStatus,
            ResearchPhase,
        )

        cycle = ResearchCycle(
            cycle_id="cycle-update",
            cycle_name="初始",
            description="",
            status=ResearchCycleStatus.PENDING,
        )
        repo.save_from_cycle(cycle)

        cycle.cycle_name = "已更新"
        cycle.status = ResearchCycleStatus.COMPLETED
        result = repo.save_from_cycle(cycle)
        assert result["cycle_name"] == "已更新"
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# 级联删除
# ---------------------------------------------------------------------------

class TestCascadeDelete:
    def test_delete_session_cascades_phases_and_artifacts(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        repo.add_phase_execution(session_payload["cycle_id"], {"phase": "observe"})
        repo.add_artifact(session_payload["cycle_id"], {"name": "级联工件"})

        assert repo.delete_session(session_payload["cycle_id"]) is True
        assert repo.list_phase_executions(session_payload["cycle_id"]) == []
        assert repo.list_artifacts(session_payload["cycle_id"]) == []


# ---------------------------------------------------------------------------
# JSON 字段完整性
# ---------------------------------------------------------------------------

class TestJsonFields:
    def test_researchers_roundtrip(self, repo):
        payload = _make_payload(researchers=["李时珍", "张仲景"])
        created = repo.create_session(payload)
        fetched = repo.get_session(payload["cycle_id"])
        assert fetched["researchers"] == ["李时珍", "张仲景"]

    def test_quality_metrics_roundtrip(self, repo):
        payload = _make_payload(quality_metrics={"score": 0.95, "notes": "优秀"})
        repo.create_session(payload)
        fetched = repo.get_session(payload["cycle_id"])
        assert fetched["quality_metrics"]["score"] == 0.95

    def test_empty_json_defaults(self, repo):
        payload = _make_payload()
        repo.create_session(payload)
        fetched = repo.get_session(payload["cycle_id"])
        assert fetched["researchers"] == []
        assert fetched["resources"] == {}
        assert fetched["tags"] == []
