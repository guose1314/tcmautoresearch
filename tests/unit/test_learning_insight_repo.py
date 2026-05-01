from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.infrastructure.persistence import DatabaseManager, LearningInsight
from src.learning.learning_insight_repo import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_REVIEWED,
    LearningInsightRepo,
)


def _repo():
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    return db, LearningInsightRepo(db)


def test_learning_insight_upsert_is_idempotent() -> None:
    db, repo = _repo()
    try:
        first = repo.upsert(
            {
                "insight_id": "insight-1",
                "source": "graph_pattern_miner",
                "target_phase": "hypothesis",
                "insight_type": "prompt_bias",
                "description": "优先核查方证关系",
                "confidence": 0.72,
                "evidence_refs": [{"node_id": "n1"}],
            }
        )
        second = repo.upsert(
            insight_id="insight-1",
            source="graph_pattern_miner",
            target_phase="hypothesis",
            insight_type="prompt_bias",
            description="优先核查桂枝汤方证关系",
            confidence=0.91,
            evidence_refs_json=[{"node_id": "n2"}],
        )

        assert first["insight_id"] == "insight-1"
        assert second["description"] == "优先核查桂枝汤方证关系"
        assert second["confidence"] == 0.91
        assert second["evidence_refs_json"] == [{"node_id": "n2"}]
        with db.session_scope() as session:
            assert session.query(LearningInsight).count() == 1
    finally:
        db.close()


def test_learning_insight_list_active_filters_by_phase_and_review_status() -> None:
    db, repo = _repo()
    try:
        repo.upsert(
            insight_id="observe-1",
            source="pg_miner",
            target_phase="observe",
            insight_type="method_policy",
            description="观察阶段保留版本 witness",
            confidence=0.8,
        )
        repo.upsert(
            insight_id="analyze-1",
            source="neo4j_miner",
            target_phase="analyze",
            insight_type="evidence_weight",
            description="提高 EvidenceClaim 权重",
            confidence=0.9,
        )

        reviewed = repo.mark_reviewed("observe-1")
        active_analyze = repo.list_active("analyze")
        active_observe = repo.list_active("observe")

        assert reviewed is not None
        assert reviewed["status"] == STATUS_REVIEWED
        assert [item["insight_id"] for item in active_analyze] == ["analyze-1"]
        assert active_observe == []
    finally:
        db.close()


def test_learning_insight_expiration_filtering_and_expire_old() -> None:
    db, repo = _repo()
    try:
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        repo.upsert(
            insight_id="old-1",
            source="neo4j_miner",
            target_phase="hypothesis",
            insight_type="prompt_bias",
            description="已过期 insight",
            confidence=0.7,
            expires_at=now - timedelta(days=1),
        )
        repo.upsert(
            insight_id="fresh-1",
            source="neo4j_miner",
            target_phase="hypothesis",
            insight_type="prompt_bias",
            description="仍有效 insight",
            confidence=0.8,
            expires_at=now + timedelta(days=1),
        )

        active = repo.list_active("hypothesis", now=now)
        expired_count = repo.expire_old(now=now)

        assert [item["insight_id"] for item in active] == ["fresh-1"]
        assert expired_count == 1
        with db.session_scope() as session:
            old = session.get(LearningInsight, "old-1")
            fresh = session.get(LearningInsight, "fresh-1")
            assert old.status == STATUS_EXPIRED
            assert fresh.status == STATUS_ACTIVE
    finally:
        db.close()
