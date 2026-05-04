from __future__ import annotations

from src.infrastructure.persistence import DatabaseManager
from src.learning.learning_insight_repo import LearningInsightRepo
from src.learning.weak_edge_candidate_repo import WeakEdgeCandidateRepository


def _db() -> DatabaseManager:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    return db


def _candidate(*, confidence: float, snippet: str) -> dict:
    return {
        "source_entity_id": "formula-1",
        "target_entity_id": "syndrome-1",
        "source_name": "桂枝汤",
        "target_name": "营卫不和",
        "source_type": "formula",
        "target_type": "syndrome",
        "relationship_type": "TREATS",
        "confidence": confidence,
        "evidence": {"snippet": snippet},
    }


def test_repo_dedupes_same_edge_across_algorithms() -> None:
    db = _db()
    try:
        repo = WeakEdgeCandidateRepository(db)

        first = repo.upsert_candidate(
            _candidate(confidence=0.74, snippet="桂枝汤主治营卫不和。"),
            target_phase="analyze",
            source_algorithm="kg_node_self_learning",
            legacy_insight_types=["candidate_edge"],
        )
        second = repo.upsert_candidate(
            _candidate(confidence=0.61, snippet="方证关系提示其可治营卫不和。"),
            target_phase="analyze",
            source_algorithm="rule_relation_quality",
            legacy_insight_types=["candidate_rule_relation"],
        )

        assert first["insight_id"] == second["insight_id"]

        item = repo.get_candidate(first["insight_id"])
        assert item is not None
        payload = item["weak_edge_candidate"]
        assert payload["duplicate_count"] == 2
        assert set(payload["source_algorithms"]) == {
            "kg_node_self_learning",
            "rule_relation_quality",
        }
        assert payload["candidate_edge"]["candidate_edge_id"] == first["insight_id"]

        listed = repo.list_candidates(status="all")
        assert len(listed) == 1
    finally:
        db.close()


def test_repo_surfaces_review_status_and_reject_reason() -> None:
    db = _db()
    try:
        repo = WeakEdgeCandidateRepository(db)
        stored = repo.upsert_candidate(
            _candidate(confidence=0.7, snippet="证据仍需人工复核。"),
            target_phase="analyze",
            source_algorithm="kg_node_self_learning",
            legacy_insight_types=["candidate_edge"],
        )

        LearningInsightRepo(db).record_review_decision(
            stored["insight_id"],
            "rejected",
            reviewer="expert-1",
            reason="证据片段不足以支持该边",
        )

        item = repo.get_candidate(stored["insight_id"])
        assert item is not None
        assert item["status"] == "rejected"
        assert item["weak_edge_candidate"]["review_status"] == "rejected"
        assert item["weak_edge_candidate"]["reject_reason"] == "证据片段不足以支持该边"
    finally:
        db.close()


def test_repo_lists_higher_confidence_candidate_first() -> None:
    db = _db()
    try:
        repo = WeakEdgeCandidateRepository(db)
        repo.upsert_candidate(
            {
                **_candidate(confidence=0.55, snippet="低分候选。"),
                "source_entity_id": "formula-2",
                "source_name": "四君子汤",
            },
            target_phase="analyze",
            source_algorithm="kg_node_self_learning",
            legacy_insight_types=["candidate_edge"],
        )
        repo.upsert_candidate(
            {
                **_candidate(confidence=0.88, snippet="高分候选。"),
                "source_entity_id": "formula-3",
                "source_name": "麻子仁丸",
            },
            target_phase="analyze",
            source_algorithm="kg_node_self_learning",
            legacy_insight_types=["candidate_edge"],
        )

        listed = repo.list_candidates(status="all")

        assert listed[0]["candidate_edge"]["source_name"] == "麻子仁丸"
        assert listed[1]["candidate_edge"]["source_name"] == "四君子汤"
    finally:
        db.close()
