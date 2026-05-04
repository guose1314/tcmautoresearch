from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.infrastructure.persistence import DatabaseManager, LearningInsight
from src.learning.learning_insight_repo import (
    STATUS_ACCEPTED,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
    STATUS_REVIEWED,
    LearningInsightRepo,
)


def _repo(threshold_policy=None):
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    return db, LearningInsightRepo(db, threshold_policy=threshold_policy)


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
        prompt_observe = repo.list_prompt_bias_eligible("observe")

        assert reviewed is not None
        assert reviewed["status"] == STATUS_REVIEWED
        assert reviewed["status"] == STATUS_ACCEPTED
        assert [item["insight_id"] for item in active_analyze] == ["analyze-1"]
        assert active_observe == []
        assert [item["insight_id"] for item in prompt_observe] == ["observe-1"]
    finally:
        db.close()


def test_learning_insight_expiration_filtering_and_expire_old() -> None:
    db, repo = _repo()
    try:
        now = datetime.now(timezone.utc)
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
        with db.session_scope() as session:
            session.get(LearningInsight, "old-1").status = STATUS_ACTIVE
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


def test_learning_insight_threshold_policy_and_rejected_negative_examples() -> None:
    db, repo = _repo(
        threshold_policy={
            "min_repeat_count": 2,
            "min_evidence_source_count": 2,
            "min_expert_vote_score": 0,
            "reject_below_expert_vote_score": -1,
        }
    )
    try:
        needs_review = repo.upsert(
            insight_id="thin-1",
            source="pg_miner",
            target_phase="hypothesis",
            insight_type="prompt_bias",
            description="证据来源不足，先进入待审",
            confidence=0.7,
            repeat_count=1,
            evidence_refs_json=[{"source_id": "doc-1"}],
        )
        promoted = repo.upsert(
            insight_id="strong-1",
            source="pg_miner",
            target_phase="hypothesis",
            insight_type="prompt_bias",
            description="重复出现且多来源支持，可进入 prompt",
            confidence=0.82,
            repeat_count=3,
            evidence_refs_json=[{"source_id": "doc-1"}, {"source_id": "doc-2"}],
            expert_votes={"accepted": 1},
        )
        rejected = repo.upsert(
            insight_id="bad-1",
            source="expert_feedback",
            target_phase="hypothesis",
            insight_type="prompt_bias",
            description="专家驳回的错误候选",
            confidence=0.95,
            status=STATUS_REJECTED,
            evidence_refs_json=[{"source_id": "review-1", "expert_vote": "rejected"}],
        )

        prompt_items = repo.list_prompt_bias_eligible("hypothesis")
        rejected_items = repo.list_rejected("hypothesis")

        assert needs_review["status"] == STATUS_NEEDS_REVIEW
        assert promoted["status"] == STATUS_ACTIVE
        assert rejected["status"] == STATUS_REJECTED
        assert [item["insight_id"] for item in prompt_items] == ["strong-1"]
        assert [item["insight_id"] for item in rejected_items] == ["bad-1"]
    finally:
        db.close()


def test_learning_insight_legacy_reviewed_status_migrates_to_accepted() -> None:
    db, repo = _repo()
    try:
        with db.session_scope() as session:
            session.add(
                LearningInsight(
                    insight_id="legacy-reviewed",
                    source="legacy",
                    target_phase="publish",
                    insight_type="method_policy",
                    description="旧 reviewed 状态",
                    confidence=0.8,
                    evidence_refs_json=[],
                    status="reviewed",
                    created_at=datetime.now(timezone.utc),
                )
            )

        migrated_count = repo.migrate_legacy_statuses()
        prompt_items = repo.list_prompt_bias_eligible("publish")

        assert migrated_count == 1
        assert prompt_items[0]["status"] == STATUS_ACCEPTED
    finally:
        db.close()
