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
    ResearchLearningFeedback,
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


def _make_learning_feedback_payload() -> dict:
    replay_feedback = {
        "status": "completed",
        "iteration_number": 3,
        "learning_summary": {
            "recorded_phases": ["observe", "analyze"],
            "weak_phase_count": 1,
            "cycle_trend": "improving",
            "tuned_parameters": {
                "max_concurrent_tasks": 6,
                "quality_threshold": 0.74,
            },
        },
        "quality_assessment": {"overall_cycle_score": 0.82},
    }
    return {
        "contract_version": "research-feedback-library.v1",
        "replay_feedback": replay_feedback,
        "records": [
            {
                "feedback_scope": "cycle_summary",
                "source_phase": "reflect",
                "feedback_status": "summary",
                "overall_score": 0.82,
                "cycle_trend": "improving",
                "issue_count": 1,
                "weakness_count": 1,
                "strength_count": 1,
                "strategy_changed": True,
                "strategy_before_fingerprint": "before-001",
                "strategy_after_fingerprint": "after-001",
                "recorded_phase_names": ["observe", "analyze"],
                "weak_phase_names": ["analyze"],
                "improvement_priorities": [
                    "优先: 提升analyze阶段数据完整性 (评分 0.35)"
                ],
                "replay_feedback": replay_feedback,
                "details": {
                    "learning_summary": replay_feedback["learning_summary"],
                    "quality_assessment": replay_feedback["quality_assessment"],
                    "strategy_diff": {
                        "changed": True,
                        "before_fingerprint": "before-001",
                        "after_fingerprint": "after-001",
                    },
                    "tuned_parameters": replay_feedback["learning_summary"][
                        "tuned_parameters"
                    ],
                },
            },
            {
                "feedback_scope": "phase_assessment",
                "source_phase": "reflect",
                "target_phase": "observe",
                "feedback_status": "strength",
                "overall_score": 0.91,
                "grade_level": "high",
                "strength_count": 1,
                "recorded_phase_names": ["observe"],
                "quality_dimensions": {
                    "completeness": 0.9,
                    "consistency": 0.88,
                    "evidence_quality": 0.93,
                },
                "issues": [],
            },
            {
                "feedback_scope": "phase_assessment",
                "source_phase": "reflect",
                "target_phase": "analyze",
                "feedback_status": "weakness",
                "overall_score": 0.35,
                "grade_level": "very_low",
                "issue_count": 1,
                "weakness_count": 1,
                "recorded_phase_names": ["analyze"],
                "weak_phase_names": ["analyze"],
                "quality_dimensions": {
                    "completeness": 0.3,
                    "consistency": 0.4,
                    "evidence_quality": 0.2,
                },
                "issues": ["missing required: status"],
            },
        ],
    }


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

    def test_learning_feedback_table_created(self, db_manager):
        assert "research_learning_feedback" in Base.metadata.tables

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

    def test_create_session_upserts_existing_cycle_id(self, repo):
        payload = _make_payload(cycle_id="cycle-upsert")
        created = repo.create_session(payload)

        updated = repo.create_session(
            {
                **payload,
                "cycle_name": "更新后的测试会话",
                "status": "active",
                "current_phase": "observe",
            }
        )

        assert updated["id"] == created["id"]
        assert updated["cycle_name"] == "更新后的测试会话"
        assert updated["status"] == "active"
        assert updated["current_phase"] == "observe"
        assert repo.list_sessions()["total"] == 1

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
        result = repo.update_session(
            payload["cycle_id"],
            {
                "cycle_name": "更新后的名称",
                "budget": 5000.0,
                "tags": ["中医", "方剂"],
            },
        )
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
        pe = repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "observe",
                "status": "running",
                "input": {"topic": "麻黄汤"},
            },
        )
        assert pe is not None
        assert pe["phase"] == "observe"
        assert pe["status"] == "running"
        assert pe["input"] == {"topic": "麻黄汤"}

    def test_add_phase_execution_nonexistent_session(self, repo):
        assert repo.add_phase_execution("nonexistent", {"phase": "observe"}) is None

    def test_update_phase_execution(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        pe = repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "hypothesis",
            },
        )
        updated = repo.update_phase_execution(
            uuid.UUID(pe["id"]),
            {
                "status": "completed",
                "duration": 12.5,
                "output": {"hypothesis": "麻黄汤可治表寒证"},
            },
        )
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
        assert sorted(p["phase"] for p in phases) == [
            "experiment",
            "hypothesis",
            "observe",
        ]

    def test_list_phase_executions_nonexistent_session(self, repo):
        assert repo.list_phase_executions("nonexistent") == []


# ---------------------------------------------------------------------------
# 工件
# ---------------------------------------------------------------------------


class TestArtifact:
    def test_add_artifact(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        art = repo.add_artifact(
            session_payload["cycle_id"],
            {
                "name": "麻黄汤分析报告",
                "artifact_type": "report",
                "content": {"summary": "报告正文"},
                "size_bytes": 1024,
            },
        )
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
        art = repo.add_artifact(
            session_payload["cycle_id"],
            {
                "name": "方剂对比数据集",
                "artifact_type": "dataset",
                "phase_execution_id": pe["id"],
            },
        )
        assert art["phase_execution_id"] == pe["id"]

    def test_list_artifacts(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        repo.add_artifact(
            session_payload["cycle_id"], {"name": "a1", "artifact_type": "paper"}
        )
        repo.add_artifact(
            session_payload["cycle_id"], {"name": "a2", "artifact_type": "dataset"}
        )
        arts = repo.list_artifacts(session_payload["cycle_id"])
        assert len(arts) == 2

    def test_list_artifacts_filter_type(self, repo):
        session_payload = _make_payload()
        repo.create_session(session_payload)
        repo.add_artifact(
            session_payload["cycle_id"], {"name": "a1", "artifact_type": "paper"}
        )
        repo.add_artifact(
            session_payload["cycle_id"], {"name": "a2", "artifact_type": "dataset"}
        )
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
# 学习反馈库
# ---------------------------------------------------------------------------


class TestLearningFeedbackLibrary:
    def test_replace_learning_feedback_library_persists_records(self, repo):
        session_payload = _make_payload(cycle_id="feedback-library")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "reflect", "status": "completed"}
        )

        saved = repo.replace_learning_feedback_library(
            session_payload["cycle_id"],
            _make_learning_feedback_payload(),
            phase_execution_id=phase["id"],
        )

        assert saved is not None
        assert saved["summary"]["record_count"] == 3
        assert saved["summary"]["weak_phase_names"] == ["analyze"]
        assert (
            saved["replay_feedback"]["learning_summary"]["tuned_parameters"][
                "max_concurrent_tasks"
            ]
            == 6
        )

    def test_list_learning_feedback_supports_cross_cycle_queries(
        self, repo, db_manager
    ):
        for cycle_id, phase_score in (("feedback-a", 0.35), ("feedback-b", 0.42)):
            repo.create_session(_make_payload(cycle_id=cycle_id))
            phase = repo.add_phase_execution(
                cycle_id, {"phase": "reflect", "status": "completed"}
            )
            payload = _make_learning_feedback_payload()
            payload["records"][2]["overall_score"] = phase_score
            repo.replace_learning_feedback_library(
                cycle_id, payload, phase_execution_id=phase["id"]
            )

        page = repo.list_learning_feedback(
            feedback_scope="phase_assessment",
            target_phase="analyze",
            limit=10,
        )

        assert page["total"] == 2
        assert len(page["items"]) == 2
        assert all(item["target_phase"] == "analyze" for item in page["items"])

    def test_get_full_snapshot_includes_learning_feedback_library(self, repo):
        session_payload = _make_payload(cycle_id="feedback-snapshot")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "reflect", "status": "completed"}
        )
        repo.replace_learning_feedback_library(
            session_payload["cycle_id"],
            _make_learning_feedback_payload(),
            phase_execution_id=phase["id"],
        )

        snapshot = repo.get_full_snapshot(session_payload["cycle_id"])

        assert snapshot is not None
        library = snapshot["learning_feedback_library"]
        assert library["summary"]["record_count"] == 3
        assert library["summary"]["cycle_trend"] == "improving"
        assert library["records"][0]["feedback_scope"] == "cycle_summary"
        assert library["replay_feedback"]["iteration_number"] == 3


# ---------------------------------------------------------------------------
# Observe 文档图谱
# ---------------------------------------------------------------------------


class TestObserveDocumentGraph:
    def test_replace_observe_document_graphs_persists_entities_and_relationships(
        self, repo
    ):
        session_payload = _make_payload(cycle_id="observe-cycle")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "observe", "status": "completed"}
        )

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
                        {
                            "name": "桂枝汤",
                            "type": "formula",
                            "confidence": 0.95,
                            "position": 0,
                            "length": 3,
                        },
                        {
                            "name": "桂枝",
                            "type": "herb",
                            "confidence": 0.93,
                            "position": 4,
                            "length": 2,
                        },
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
                    "output_generation": {
                        "quality_metrics": {"confidence_score": 0.91}
                    },
                }
            ],
        )

        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot["phase_execution_id"] == phase["id"]
        assert snapshot["entity_count"] == 2
        assert snapshot["relationship_count"] == 1
        assert (
            snapshot["entities"][0]["entity_metadata"]["cycle_id"]
            == session_payload["cycle_id"]
        )
        assert snapshot["semantic_relationships"][0]["relationship_type"] == "CONTAINS"
        assert snapshot["semantic_relationships"][0]["source_entity_type"] == "formula"
        assert snapshot["source_type"] == "ctext"
        assert (
            snapshot["version_metadata"]["catalog_id"]
            == "ctp:shang-han-lun/bian-mai-fa"
        )
        assert (
            snapshot["version_metadata"]["version_lineage_key"]
            == "伤寒论|辨脉法|东汉|张仲景|宋本"
        )

    def test_get_full_snapshot_includes_observe_documents(self, repo):
        session_payload = _make_payload(cycle_id="observe-snapshot")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "observe", "status": "completed"}
        )
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
                        {
                            "name": "桂枝汤",
                            "type": "formula",
                            "confidence": 0.95,
                            "position": 0,
                            "length": 3,
                        },
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
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "observe", "status": "completed"}
        )

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
        assert {w["catalog_id"] for w in lineages[0]["witnesses"]} == {
            "ctp:shang-han-lun/bian-mai-fa",
            "archive_org",
        }

    def test_list_observe_document_graphs_derives_version_metadata_for_legacy_rows(
        self, repo, db_manager
    ):
        session_payload = _make_payload(cycle_id="observe-legacy-lineage")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "observe", "status": "completed"}
        )

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

        legacy_snapshot = repo.list_observe_document_graphs(
            session_payload["cycle_id"]
        )[0]

        assert legacy_snapshot["source_type"] == "local"
        assert legacy_snapshot["work_title"] == "本草纲目"
        assert legacy_snapshot["dynasty"] == "明"
        assert legacy_snapshot["author"] == "李时珍"
        assert legacy_snapshot["version_metadata"]["catalog_id"].endswith(
            "013-本草纲目-明-李时珍.txt"
        )
        assert legacy_snapshot["version_metadata"]["version_lineage_key"]

    def test_backfill_observe_document_version_metadata_persists_legacy_rows(
        self, repo, db_manager
    ):
        session_payload = _make_payload(cycle_id="observe-legacy-writeback")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"], {"phase": "observe", "status": "completed"}
        )

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

        summary = repo.backfill_observe_document_version_metadata(
            session_payload["cycle_id"]
        )

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
        assert document.document_urn and document.document_urn.endswith(
            "013-本草纲目-明-李时珍.txt"
        )
        assert document.document_title == "本草纲目-明-李时珍"
        assert document.source_type == "local"
        assert document.work_title == "本草纲目"
        assert document.fragment_title == "本草纲目"
        assert document.dynasty == "明"
        assert document.author == "李时珍"
        assert document.version_lineage_key
        assert document.version_metadata_json["catalog_id"].endswith(
            "013-本草纲目-明-李时珍.txt"
        )
        assert notes["source_type"] == "local"
        assert (
            notes["version_metadata"]["version_lineage_key"]
            == document.version_lineage_key
        )

    def test_backfill_observe_philology_artifacts_persists_from_phase_output(
        self, repo
    ):
        session_payload = _make_payload(cycle_id="observe-philology-backfill")
        repo.create_session(session_payload)
        observe_output = {
            "phase": "observe",
            "status": "completed",
            "results": {
                "ingestion_pipeline": {
                    "documents": [
                        {
                            "urn": "doc:observe:philology:1",
                            "title": "补血汤宋本",
                            "source_type": "ctext",
                            "metadata": {
                                "version_metadata": {
                                    "catalog_id": "ctp:buxue-tang/songben",
                                    "work_title": "补血汤",
                                    "fragment_title": "补血汤",
                                    "work_fragment_key": "补血汤|补血汤",
                                    "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                                    "witness_key": "ctext:doc:observe:philology:1",
                                    "dynasty": "明",
                                    "author": "李时珍",
                                    "edition": "宋本",
                                    "lineage_source": "explicit_metadata",
                                }
                            },
                        }
                    ],
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
        assert summary["created_artifact_count"] == 4
        assert set(artifacts) == {
            "observe_philology_terminology_table",
            "observe_philology_collation_entries",
            "observe_philology_annotation_report",
            "observe_philology_catalog_summary",
        }
        assert (
            artifacts["observe_philology_terminology_table"]["artifact_type"]
            == "dataset"
        )
        assert (
            artifacts["observe_philology_terminology_table"]["content"]["rows"][0][
                "canonical"
            ]
            == "黄芪"
        )
        assert (
            artifacts["observe_philology_collation_entries"]["content"]["entries"][0][
                "witness_text"
            ]
            == "黃耆"
        )
        assert (
            artifacts["observe_philology_annotation_report"]["content"]["summary"][
                "collation_entry_count"
            ]
            == 1
        )
        assert (
            artifacts["observe_philology_catalog_summary"]["content"]["summary"][
                "version_lineage_count"
            ]
            == 1
        )
        assert snapshot is not None
        assert snapshot["observe_philology"]["terminology_standard_table_count"] == 1
        assert snapshot["observe_philology"]["collation_entry_count"] == 1
        assert (
            snapshot["observe_philology"]["catalog_summary"]["summary"][
                "catalog_document_count"
            ]
            == 1
        )
        assert snapshot["observe_philology"]["source"] == "artifacts"

    def test_upsert_observe_catalog_review_persists_artifact_and_updates_snapshot(
        self, repo
    ):
        session_payload = _make_payload(cycle_id="observe-philology-review-writeback")
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "observe",
                "status": "completed",
                "output": {"phase": "observe", "status": "completed"},
            },
        )
        repo.add_artifact(
            session_payload["cycle_id"],
            {
                "phase_execution_id": phase["id"],
                "name": "observe_philology_catalog_summary",
                "artifact_type": "dataset",
                "content": {
                    "summary": {
                        "catalog_document_count": 1,
                        "work_count": 1,
                        "work_fragment_count": 1,
                        "version_lineage_count": 1,
                        "witness_count": 1,
                        "missing_core_metadata_count": 0,
                        "source_type_counts": {"local": 1},
                    },
                    "documents": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:review:1",
                            "catalog_id": "review:catalog:1",
                            "source_type": "local",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "work_fragment_key": "补血汤|补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "review:witness:1",
                            "dynasty": "明",
                            "author": "李时珍",
                            "edition": "宋本",
                        }
                    ],
                    "version_lineages": [
                        {
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "work_fragment_key": "补血汤|补血汤",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "dynasty": "明",
                            "author": "李时珍",
                            "edition": "宋本",
                            "witness_count": 1,
                            "witnesses": [
                                {
                                    "title": "补血汤宋本",
                                    "urn": "doc:review:1",
                                    "catalog_id": "review:catalog:1",
                                    "source_type": "local",
                                    "witness_key": "review:witness:1",
                                }
                            ],
                        }
                    ],
                },
            },
        )

        saved_artifact = repo.upsert_observe_catalog_review(
            session_payload["cycle_id"],
            {
                "scope": "version_lineage",
                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                "review_status": "accepted",
                "reviewer": "repo-test",
                "decision_basis": "unit test",
            },
        )
        snapshot = repo.get_full_snapshot(session_payload["cycle_id"])
        artifacts = {
            artifact["name"]: artifact
            for artifact in repo.list_artifacts(session_payload["cycle_id"])
        }

        assert saved_artifact is not None
        assert saved_artifact["name"] == "observe_philology_catalog_review"
        assert (
            artifacts["observe_philology_catalog_review"]["content"]["decision_count"]
            == 1
        )
        assert snapshot is not None
        document = snapshot["observe_philology"]["catalog_summary"]["documents"][0]
        lineage = snapshot["observe_philology"]["catalog_summary"]["version_lineages"][
            0
        ]
        assert document["review_status"] == "accepted"
        assert document["needs_manual_review"] is False
        assert document["reviewer"] == "repo-test"
        assert document["review_source"] == "manual_review"
        assert lineage["review_status"] == "accepted"
        assert lineage["reviewer"] == "repo-test"

    def test_upsert_observe_workbench_review_persists_artifact_and_updates_snapshot(
        self, repo
    ):
        session_payload = _make_payload(
            cycle_id="observe-philology-workbench-review-writeback"
        )
        repo.create_session(session_payload)
        phase = repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "observe",
                "status": "completed",
                "output": {"phase": "observe", "status": "completed"},
            },
        )
        repo.add_artifact(
            session_payload["cycle_id"],
            {
                "phase_execution_id": phase["id"],
                "name": "observe_philology_catalog_summary",
                "artifact_type": "dataset",
                "content": {
                    "summary": {
                        "catalog_document_count": 1,
                        "work_count": 1,
                        "work_fragment_count": 1,
                        "version_lineage_count": 1,
                        "witness_count": 1,
                        "missing_core_metadata_count": 0,
                        "source_type_counts": {"local": 1},
                    },
                    "documents": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:workbench:1",
                            "catalog_id": "workbench:catalog:1",
                            "source_type": "local",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "work_fragment_key": "补血汤|补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "workbench:witness:1",
                            "dynasty": "明",
                            "author": "李时珍",
                            "edition": "宋本",
                        }
                    ],
                },
            },
        )

        saved_artifact = repo.upsert_observe_workbench_review(
            session_payload["cycle_id"],
            {
                "asset_type": "claim",
                "asset_key": "claim::claim_id=claim-1|source_entity=黄芪|target_entity=补气|relation_type=treats",
                "review_status": "accepted",
                "reviewer": "repo-reviewer",
                "decision_basis": "人工 claim 复核",
                "claim_id": "claim-1",
                "source_entity": "黄芪",
                "target_entity": "补气",
                "relation_type": "treats",
                "work_title": "补血汤",
                "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                "witness_key": "workbench:witness:1",
            },
        )
        snapshot = repo.get_full_snapshot(session_payload["cycle_id"])
        artifacts = {
            artifact["name"]: artifact
            for artifact in repo.list_artifacts(session_payload["cycle_id"])
        }

        assert saved_artifact is not None
        assert saved_artifact["name"] == "observe_philology_review_workbench"
        assert (
            artifacts["observe_philology_review_workbench"]["content"]["decision_count"]
            == 1
        )
        assert snapshot is not None
        decisions = snapshot["observe_philology"]["review_workbench_decisions"]
        assert len(decisions) == 1
        assert decisions[0]["asset_type"] == "claim"
        assert decisions[0]["review_status"] == "accepted"
        assert decisions[0]["reviewer"] == "repo-reviewer"

    def test_upsert_observe_workbench_review_appends_philology_feedback(self, repo):
        session_payload = _make_payload(cycle_id="observe-philology-feedback-writeback")
        repo.create_session(session_payload)
        repo.add_phase_execution(
            session_payload["cycle_id"],
            {"phase": "observe", "status": "completed", "output": {"phase": "observe"}},
        )

        saved_artifact = repo.upsert_observe_workbench_review(
            session_payload["cycle_id"],
            {
                "asset_type": "exegesis_entry",
                "asset_key": "exegesis::黄芪",
                "review_status": "rejected",
                "reviewer": "repo-reviewer",
                "reason": "未核对宋本 witness",
                "term": "黄芪",
            },
        )
        feedback = repo.list_learning_feedback(
            session_payload["cycle_id"],
            feedback_scope="philology_review",
        )

        assert saved_artifact is not None
        assert feedback["total"] == 1
        item = feedback["items"][0]
        assert item["feedback_scope"] == "philology_review"
        assert item["target_phase"] == "observe"
        assert item["metadata"]["asset_kind"] == "exegesis_entry"
        assert item["metadata"]["asset_id"] == "exegesis::黄芪"
        assert item["metadata"]["decision"] == "rejected"
        assert "此类术语需优先检查版本 witness" in item["metadata"]["issue_fields"]

    def test_backfill_observe_philology_artifacts_skips_sessions_without_philology(
        self, repo
    ):
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

    def test_backfill_phase_graph_assets_persists_from_historical_phase_outputs(
        self, repo
    ):
        session_payload = _make_payload(cycle_id="phase-graph-assets-backfill")
        repo.create_session(session_payload)

        repo.add_phase_execution(
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
                                    "urn": "doc:graph-assets:observe:1",
                                    "title": "伤寒论宋本",
                                    "metadata": {
                                        "version_metadata": {
                                            "catalog_id": "catalog:observe:1",
                                            "work_title": "伤寒论",
                                            "fragment_title": "辨太阳病脉证并治",
                                            "work_fragment_key": "伤寒论|辨太阳病脉证并治",
                                            "version_lineage_key": "伤寒论|辨太阳病脉证并治|汉|张仲景|宋本",
                                            "witness_key": "witness:observe:1",
                                            "dynasty": "汉",
                                            "author": "张仲景",
                                            "edition": "宋本",
                                        }
                                    },
                                }
                            ],
                            "aggregate": {
                                "philology_assets": {
                                    "terminology_standard_table": [
                                        {
                                            "document_title": "伤寒论宋本",
                                            "document_urn": "doc:graph-assets:observe:1",
                                            "canonical": "桂枝",
                                            "label": "本草药名",
                                            "status": "standardized",
                                            "observed_forms": ["桂支"],
                                        }
                                    ],
                                    "evidence_chains": [
                                        {
                                            "claim_id": "claim-observe-1",
                                            "claim_text": "桂枝用于解肌发表",
                                            "source_entity": "桂枝",
                                            "target_entity": "解肌发表",
                                            "relation_type": "treats",
                                            "evidence_ids": ["ev-observe-1"],
                                            "document_title": "伤寒论宋本",
                                            "work_title": "伤寒论",
                                            "version_lineage_key": "伤寒论|辨太阳病脉证并治|汉|张仲景|宋本",
                                            "witness_key": "witness:observe:1",
                                        }
                                    ],
                                }
                            },
                        }
                    },
                    "metadata": {},
                    "artifacts": [],
                    "error": None,
                },
            },
        )
        repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "hypothesis",
                "status": "completed",
                "output": {
                    "phase": "hypothesis",
                    "status": "completed",
                    "results": {
                        "hypotheses": [
                            {
                                "hypothesis_id": "hyp-1",
                                "statement": "桂枝与营卫失和存在相关性",
                                "source_entities": ["桂枝", "营卫失和"],
                                "supporting_signals": ["太阳中风"],
                            }
                        ]
                    },
                    "metadata": {},
                    "artifacts": [],
                    "error": None,
                },
            },
        )
        repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "analyze",
                "status": "completed",
                "output": {
                    "phase": "analyze",
                    "status": "completed",
                    "results": {
                        "evidence_protocol": {
                            "evidence_records": [
                                {
                                    "evidence_id": "ev-1",
                                    "title": "桂枝汤条文",
                                    "source_type": "classical_text",
                                    "source_ref": "doc:analyze:1",
                                    "source_entity": "桂枝",
                                    "target_entity": "太阳中风",
                                    "relation_type": "treats",
                                    "document_title": "伤寒论",
                                }
                            ],
                            "claims": [
                                {
                                    "claim_id": "claim-1",
                                    "claim_text": "桂枝治疗太阳中风",
                                    "source_entity": "桂枝",
                                    "target_entity": "太阳中风",
                                    "relation_type": "treats",
                                    "evidence_ids": ["ev-1"],
                                }
                            ],
                            "evidence_grade_summary": {"overall_grade": "B"},
                        }
                    },
                    "metadata": {},
                    "artifacts": [],
                    "error": None,
                },
            },
        )

        summary = repo.backfill_phase_graph_assets(session_payload["cycle_id"])
        phase_outputs = {
            phase["phase"]: phase["output"]
            for phase in repo.list_phase_executions(session_payload["cycle_id"])
        }

        assert summary["status"] == "active"
        assert summary["updated_phase_count"] == 3
        assert summary["graph_assets_written_phase_count"] == 3
        assert summary["metadata_updated_phase_count"] == 3
        assert summary["graph_asset_subgraph_count"] == 3
        assert summary["updated_observe_phase_count"] == 1
        assert summary["updated_hypothesis_phase_count"] == 1
        assert summary["updated_analyze_phase_count"] == 1
        assert (
            "philology_subgraph" in phase_outputs["observe"]["results"]["graph_assets"]
        )
        assert phase_outputs["observe"]["metadata"]["graph_asset_subgraphs"] == [
            "philology_subgraph"
        ]
        assert phase_outputs["hypothesis"]["metadata"]["graph_asset_subgraphs"] == [
            "hypothesis_subgraph"
        ]
        assert phase_outputs["analyze"]["metadata"]["graph_asset_subgraphs"] == [
            "evidence_subgraph"
        ]
        assert phase_outputs["analyze"]["metadata"]["graph_asset_node_count"] > 0

    def test_backfill_phase_graph_assets_dry_run_does_not_persist(self, repo):
        session_payload = _make_payload(cycle_id="phase-graph-assets-backfill-dry-run")
        repo.create_session(session_payload)
        repo.add_phase_execution(
            session_payload["cycle_id"],
            {
                "phase": "hypothesis",
                "status": "completed",
                "output": {
                    "phase": "hypothesis",
                    "status": "completed",
                    "results": {
                        "hypotheses": [
                            {
                                "hypothesis_id": "dry-run-h1",
                                "statement": "干运行不落库",
                                "source_entities": ["黄芪"],
                            }
                        ]
                    },
                    "metadata": {},
                    "artifacts": [],
                    "error": None,
                },
            },
        )

        summary = repo.backfill_phase_graph_assets(
            session_payload["cycle_id"], dry_run=True
        )
        phase_output = repo.list_phase_executions(session_payload["cycle_id"])[0][
            "output"
        ]

        assert summary["status"] == "dry_run"
        assert summary["dry_run"] is True
        assert summary["updated_phase_count"] == 1
        assert summary["graph_assets_written_phase_count"] == 1
        assert phase_output["results"].get("graph_assets") in (None, {})
        assert phase_output["metadata"].get("graph_asset_subgraphs") in (None, [])

    def test_external_transaction_rolls_back_observe_graph_on_neo4j_failure(
        self, db_manager, repo
    ):
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
                                {
                                    "name": "麻黄汤",
                                    "type": "formula",
                                    "confidence": 0.95,
                                    "position": 0,
                                    "length": 3,
                                },
                            ],
                            "semantic_relationships": [],
                        }
                    ],
                    session=txn.pg_session,
                )
                txn.neo4j_write("CREATE first", compensate_cypher="DELETE first", id=1)
                txn.neo4j_write(
                    "CREATE second", compensate_cypher="DELETE second", id=2
                )

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
                                properties={
                                    "cycle_id": "session-1",
                                    "phase": "observe",
                                },
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

        assert (
            "MATCH (a:ResearchSession {id: $src_id}) MATCH (b:ResearchPhaseExecution {id: $tgt_id})"
            in first_query
        )
        assert ", (b:ResearchPhaseExecution {id: $tgt_id})" not in first_query
        assert "MERGE (a)-[r:HAS_PHASE]->(b)" in first_query
        assert first_params == {
            "src_id": "session-1",
            "tgt_id": "phase-1",
            "props": {"cycle_id": "session-1", "phase": "observe"},
        }

        assert (
            "MATCH (a:ResearchPhaseExecution {id: $src_id}) MATCH (b:ResearchArtifact {id: $tgt_id})"
            in second_query
        )
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

        assert (
            driver.create_relationship(
                single_edge,
                "ResearchSession",
                "ResearchPhaseExecution",
            )
            is True
        )

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

        assert (
            driver.batch_create_relationships(
                [
                    (
                        batch_edge,
                        "ResearchPhaseExecution",
                        "ResearchArtifact",
                    )
                ]
            )
            is True
        )

        batch_query, batch_params = backend.executed_queries[0]
        assert (
            "MATCH (source:ResearchPhaseExecution {id: row.source_id})" in batch_query
        )
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


# ---------------------------------------------------------------------------
# Phase H / H-2: Reviewer assignment surface
# ---------------------------------------------------------------------------


class TestReviewAssignments:
    """claim / release / reassign / complete / list / aggregate workflows."""

    def _seed_session(self, repo) -> str:
        payload = _make_payload()
        repo.create_session(payload)
        return payload["cycle_id"]

    def test_claim_persists_row_with_claimed_status(self, repo):
        cycle_id = self._seed_session(repo)
        result = repo.claim_review_assignment(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            priority_bucket="high",
            notes="紧急",
        )
        assert result is not None
        assert result["assignee"] == "李研究员"
        assert result["queue_status"] == "claimed"
        assert result["priority_bucket"] == "high"
        assert result["claimed_at"] is not None
        assert result["reviewer_label"] == "李研究员"

    def test_claim_blank_assignee_raises(self, repo):
        cycle_id = self._seed_session(repo)
        with pytest.raises(ValueError):
            repo.claim_review_assignment(cycle_id, "catalog", "k-1", "  ")

    def test_claim_returns_none_when_session_missing(self, repo):
        result = repo.claim_review_assignment(
            "cycle-does-not-exist",
            "catalog",
            "k-1",
            "李研究员",
        )
        assert result is None

    def test_release_clears_assignee_and_marks_unassigned(self, repo):
        cycle_id = self._seed_session(repo)
        repo.claim_review_assignment(cycle_id, "catalog", "k-1", "李研究员")
        released = repo.release_review_assignment(
            cycle_id, "catalog", "k-1", notes="退回"
        )
        assert released is not None
        assert released["assignee"] is None
        assert released["queue_status"] == "unassigned"
        assert released["released_at"] is not None
        assert released["reviewer_label"] == "未认领"

    def test_release_returns_none_for_missing_target(self, repo):
        cycle_id = self._seed_session(repo)
        assert repo.release_review_assignment(cycle_id, "catalog", "missing") is None

    def test_reassign_updates_assignee_and_refreshes_claimed_at(self, repo):
        cycle_id = self._seed_session(repo)
        first = repo.claim_review_assignment(cycle_id, "catalog", "k-1", "李研究员")
        reassigned = repo.reassign_review_assignment(
            cycle_id,
            "catalog",
            "k-1",
            "张研究员",
            priority_bucket="low",
        )
        assert reassigned is not None
        assert reassigned["assignee"] == "张研究员"
        assert reassigned["priority_bucket"] == "low"
        assert reassigned["queue_status"] == "claimed"
        assert reassigned["claimed_at"] is not None
        assert reassigned["id"] == first["id"]

    def test_complete_marks_completed_at(self, repo):
        cycle_id = self._seed_session(repo)
        repo.claim_review_assignment(cycle_id, "catalog", "k-1", "李研究员")
        completed = repo.complete_review_assignment(cycle_id, "catalog", "k-1")
        assert completed is not None
        assert completed["queue_status"] == "completed"
        assert completed["completed_at"] is not None

    def test_unique_constraint_on_target(self, repo, db_manager):
        cycle_id = self._seed_session(repo)
        first = repo.claim_review_assignment(cycle_id, "catalog", "k-1", "李研究员")
        again = repo.claim_review_assignment(cycle_id, "catalog", "k-1", "张研究员")
        assert again["id"] == first["id"]
        assert again["assignee"] == "张研究员"
        # Only a single physical row exists for (cycle_id, asset_type, asset_key).
        items = repo.list_review_queue(cycle_id=cycle_id, asset_type="catalog")
        assert len(items) == 1

    def test_list_review_queue_filters(self, repo):
        cycle_id = self._seed_session(repo)
        repo.claim_review_assignment(
            cycle_id, "catalog", "k-1", "李研究员", priority_bucket="high"
        )
        repo.claim_review_assignment(
            cycle_id, "catalog", "k-2", "张研究员", priority_bucket="low"
        )
        repo.claim_review_assignment(
            cycle_id, "workbench", "k-3", "李研究员", priority_bucket="medium"
        )

        all_items = repo.list_review_queue(cycle_id=cycle_id)
        assert len(all_items) == 3

        only_li = repo.list_review_queue(cycle_id=cycle_id, assignee="李研究员")
        assert {row["asset_key"] for row in only_li} == {"k-1", "k-3"}

        only_high = repo.list_review_queue(cycle_id=cycle_id, priority_bucket="high")
        assert [row["asset_key"] for row in only_high] == ["k-1"]

        only_workbench = repo.list_review_queue(
            cycle_id=cycle_id, asset_type="workbench"
        )
        assert [row["asset_key"] for row in only_workbench] == ["k-3"]

        repo.release_review_assignment(cycle_id, "catalog", "k-2")
        unassigned = repo.list_review_queue(cycle_id=cycle_id, unassigned_only=True)
        assert [row["asset_key"] for row in unassigned] == ["k-2"]

    def test_list_review_queue_only_overdue(self, repo):
        cycle_id = self._seed_session(repo)
        past_due = datetime(2020, 1, 1, 12, 0, 0)
        repo.claim_review_assignment(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            due_at=past_due,
        )
        repo.claim_review_assignment(cycle_id, "catalog", "k-2", "李研究员")

        overdue = repo.list_review_queue(cycle_id=cycle_id, only_overdue=True)
        assert [row["asset_key"] for row in overdue] == ["k-1"]
        assert overdue[0]["is_overdue"] is True

    def test_aggregate_reviewer_workload_groups_and_orders(self, repo):
        cycle_id = self._seed_session(repo)
        repo.claim_review_assignment(
            cycle_id, "catalog", "k-1", "李研究员", priority_bucket="high"
        )
        repo.claim_review_assignment(
            cycle_id, "catalog", "k-2", "李研究员", priority_bucket="medium"
        )
        repo.claim_review_assignment(
            cycle_id, "catalog", "k-3", "张研究员", priority_bucket="low"
        )
        repo.claim_review_assignment(cycle_id, "catalog", "k-4", "张研究员")
        repo.release_review_assignment(cycle_id, "catalog", "k-4")

        buckets = repo.aggregate_reviewer_workload(cycle_id=cycle_id)
        labels = [b["reviewer_label"] for b in buckets]
        # 未认领 always sorted last.
        assert labels[-1] == "未认领"
        assert set(labels) == {"李研究员", "张研究员", "未认领"}

        by_label = {b["reviewer_label"]: b for b in buckets}
        assert by_label["李研究员"]["total"] == 2
        assert by_label["李研究员"]["claimed"] == 2
        assert by_label["李研究员"]["high_priority"] == 1
        assert by_label["李研究员"]["medium_priority"] == 1
        assert by_label["张研究员"]["total"] == 1
        assert by_label["张研究员"]["low_priority"] == 1
        assert by_label["未认领"]["total"] == 1
        assert by_label["未认领"]["unassigned"] == 1
        assert by_label["未认领"]["reviewer"] == ""

    def test_aggregate_reviewer_workload_includes_overdue(self, repo):
        cycle_id = self._seed_session(repo)
        past_due = datetime(2020, 1, 1, 12, 0, 0)
        repo.claim_review_assignment(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            due_at=past_due,
        )
        buckets = repo.aggregate_reviewer_workload(cycle_id=cycle_id)
        assert buckets[0]["overdue"] == 1


class TestReviewDisputes:
    """Phase H / H-3: open / assign / resolve / withdraw / list disputes."""

    def _seed_session(self, repo) -> str:
        payload = _make_payload()
        repo.create_session(payload)
        return payload["cycle_id"]

    def test_open_persists_with_auto_case_id(self, repo):
        cycle_id = self._seed_session(repo)
        result = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "需要重新审核版本谱系",
        )
        assert result is not None
        assert result["dispute_status"] == "open"
        assert result["asset_type"] == "catalog"
        assert result["asset_key"] == "k-1"
        assert result["opened_by"] == "李研究员"
        assert result["arbitrator"] in (None, "")
        assert isinstance(result["case_id"], str) and result["case_id"].startswith(
            "DISP-"
        )
        assert isinstance(result["events"], list) and len(result["events"]) == 1
        assert result["events"][0].get("event") == "opened"

    def test_open_with_arbitrator_marks_assigned(self, repo):
        cycle_id = self._seed_session(repo)
        result = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "需要专家裁决",
            arbitrator="张专家",
        )
        assert result["dispute_status"] == "assigned"
        assert result["arbitrator"] == "张专家"
        events = result["events"]
        assert len(events) == 2
        assert {e.get("event") for e in events} == {"opened", "assigned"}

    def test_open_blank_summary_raises(self, repo):
        cycle_id = self._seed_session(repo)
        with pytest.raises(ValueError):
            repo.open_review_dispute(cycle_id, "catalog", "k-1", "李研究员", "  ")

    def test_open_returns_none_when_session_missing(self, repo):
        result = repo.open_review_dispute(
            "cycle-does-not-exist",
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        assert result is None

    def test_open_with_explicit_case_id_unique(self, repo):
        cycle_id = self._seed_session(repo)
        first = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "case-1",
            case_id="DISP-MANUAL-001",
        )
        assert first["case_id"] == "DISP-MANUAL-001"
        with pytest.raises(Exception):
            repo.open_review_dispute(
                cycle_id,
                "catalog",
                "k-2",
                "李研究员",
                "case-1-dup",
                case_id="DISP-MANUAL-001",
            )

    def test_assign_updates_arbitrator_and_appends_event(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        case_id = opened["case_id"]
        assigned = repo.assign_review_dispute(
            cycle_id,
            case_id,
            "张专家",
            actor="管理员",
            notes="安排裁决",
        )
        assert assigned is not None
        assert assigned["dispute_status"] == "assigned"
        assert assigned["arbitrator"] == "张专家"
        assert any(e.get("event") == "assigned" for e in assigned["events"])

    def test_assign_terminal_status_raises(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        case_id = opened["case_id"]
        repo.withdraw_review_dispute(cycle_id, case_id, actor="李研究员")
        with pytest.raises(ValueError):
            repo.assign_review_dispute(cycle_id, case_id, "张专家")

    def test_assign_returns_none_for_missing_case(self, repo):
        cycle_id = self._seed_session(repo)
        assert repo.assign_review_dispute(cycle_id, "DISP-NONE", "张专家") is None

    def test_resolve_marks_resolved_and_records_event(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
            arbitrator="张专家",
        )
        case_id = opened["case_id"]
        resolved = repo.resolve_review_dispute(
            cycle_id,
            case_id,
            "accepted",
            resolved_by="张专家",
            resolution_notes="同意原审",
        )
        assert resolved is not None
        assert resolved["dispute_status"] == "resolved"
        assert resolved["resolution"] == "accepted"
        assert resolved["resolution_notes"] == "同意原审"
        assert any(e.get("event") == "resolved" for e in resolved["events"])

    def test_resolve_invalid_resolution_raises(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        with pytest.raises(ValueError):
            repo.resolve_review_dispute(
                cycle_id, opened["case_id"], "invalid", resolved_by="张专家"
            )

    def test_resolve_terminal_status_raises(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        case_id = opened["case_id"]
        repo.resolve_review_dispute(cycle_id, case_id, "accepted", resolved_by="张专家")
        with pytest.raises(ValueError):
            repo.resolve_review_dispute(
                cycle_id, case_id, "rejected", resolved_by="张专家"
            )

    def test_withdraw_marks_terminal(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        withdrawn = repo.withdraw_review_dispute(
            cycle_id,
            opened["case_id"],
            actor="李研究员",
            notes="撤回",
        )
        assert withdrawn is not None
        assert withdrawn["dispute_status"] == "withdrawn"
        assert any(e.get("event") == "withdrawn" for e in withdrawn["events"])

    def test_withdraw_terminal_raises(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            "测试",
        )
        case_id = opened["case_id"]
        repo.resolve_review_dispute(cycle_id, case_id, "accepted", resolved_by="张专家")
        with pytest.raises(ValueError):
            repo.withdraw_review_dispute(cycle_id, case_id, actor="李研究员")

    def test_list_review_disputes_filters(self, repo):
        cycle_id = self._seed_session(repo)
        a = repo.open_review_dispute(cycle_id, "catalog", "k-1", "李研究员", "S1")
        b = repo.open_review_dispute(
            cycle_id, "catalog", "k-2", "张研究员", "S2", arbitrator="王专家"
        )
        c = repo.open_review_dispute(cycle_id, "workbench", "k-3", "李研究员", "S3")
        repo.resolve_review_dispute(
            cycle_id, c["case_id"], "rejected", resolved_by="裁判"
        )

        all_items = repo.list_review_disputes(cycle_id=cycle_id)
        assert len(all_items) == 3

        only_open = repo.list_review_disputes(cycle_id=cycle_id, dispute_status="open")
        assert {row["case_id"] for row in only_open} == {a["case_id"]}

        only_arbitrator = repo.list_review_disputes(
            cycle_id=cycle_id, arbitrator="王专家"
        )
        assert {row["case_id"] for row in only_arbitrator} == {b["case_id"]}

        only_workbench = repo.list_review_disputes(
            cycle_id=cycle_id, asset_type="workbench"
        )
        assert {row["case_id"] for row in only_workbench} == {c["case_id"]}

        only_li = repo.list_review_disputes(cycle_id=cycle_id, opened_by="李研究员")
        assert {row["case_id"] for row in only_li} == {a["case_id"], c["case_id"]}

    def test_get_review_dispute(self, repo):
        cycle_id = self._seed_session(repo)
        opened = repo.open_review_dispute(cycle_id, "catalog", "k-1", "李研究员", "S1")
        fetched = repo.get_review_dispute(cycle_id, opened["case_id"])
        assert fetched is not None
        assert fetched["case_id"] == opened["case_id"]
        assert repo.get_review_dispute(cycle_id, "DISP-NONE") is None


class TestReviewQualitySummaryRepo:
    """Phase H / H-4: aggregate_review_quality_summary integration."""

    def _seed_session(self, repo) -> str:
        payload = _make_payload()
        repo.create_session(payload)
        return payload["cycle_id"]

    def test_empty_cycle_returns_supported_zero_metrics(self, repo):
        cycle_id = self._seed_session(repo)
        summary = repo.aggregate_review_quality_summary(cycle_id=cycle_id)
        assert summary["supported"] is True
        assert summary["assignment_count"] == 0
        assert summary["dispute_count"] == 0
        assert summary["agreement_rate"] == 0.0
        assert summary["overdue_count"] == 0

    def test_overdue_and_dispute_metrics_combine(self, repo):
        cycle_id = self._seed_session(repo)
        past_due = datetime(2020, 1, 1, 12, 0, 0)
        repo.claim_review_assignment(
            cycle_id,
            "catalog",
            "k-1",
            "李研究员",
            due_at=past_due,
        )
        repo.claim_review_assignment(cycle_id, "catalog", "k-2", "张研究员")
        opened_a = repo.open_review_dispute(
            cycle_id, "catalog", "k-1", "李研究员", "S1"
        )
        opened_b = repo.open_review_dispute(
            cycle_id, "catalog", "k-2", "张研究员", "S2"
        )
        repo.resolve_review_dispute(
            cycle_id,
            opened_a["case_id"],
            "accepted",
            resolved_by="裁判",
        )
        repo.resolve_review_dispute(
            cycle_id,
            opened_b["case_id"],
            "rejected",
            resolved_by="裁判",
        )

        summary = repo.aggregate_review_quality_summary(cycle_id=cycle_id)
        assert summary["assignment_count"] == 2
        assert summary["overdue_count"] == 1
        assert summary["dispute_count"] == 2
        assert summary["resolved_dispute_count"] == 2
        assert summary["agreement_rate"] == 0.5
        assert summary["overturn_rate"] == 0.5

    def test_filter_by_reviewer_narrows_metrics(self, repo):
        cycle_id = self._seed_session(repo)
        repo.claim_review_assignment(cycle_id, "catalog", "k-1", "李研究员")
        repo.claim_review_assignment(cycle_id, "catalog", "k-2", "张研究员")

        summary = repo.aggregate_review_quality_summary(
            cycle_id=cycle_id,
            reviewer="李研究员",
        )
        assert summary["assignment_count"] == 1
