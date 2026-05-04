from __future__ import annotations

import uuid

from sqlalchemy import text

from src.infrastructure.persistence import (
    DatabaseManager,
    Document,
    Entity,
    EntityRelationship,
    EntityTypeEnum,
    RelationshipType,
)
from src.learning.kg_node_self_learning import KGNodeSelfLearningEnhancer
from src.learning.learning_insight_repo import LearningInsightRepo
from src.learning.weak_edge_candidate_repo import WeakEdgeCandidateRepository


def _db() -> DatabaseManager:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    return db


def _seed_entities(db: DatabaseManager):
    with db.session_scope() as session:
        doc = Document(
            source_file="jingui.txt",
            content_hash="a" * 64,
            document_title="金匮要略片段",
        )
        session.add(doc)
        session.flush()
        formula = Entity(
            document_id=doc.id,
            name="桂枝汤",
            type=EntityTypeEnum.FORMULA,
            confidence=0.94,
            position=10,
            length=3,
        )
        herb = Entity(
            document_id=doc.id,
            name="桂枝",
            type=EntityTypeEnum.HERB,
            confidence=0.91,
            position=36,
            length=2,
        )
        syndrome = Entity(
            document_id=doc.id,
            name="营卫不和",
            type=EntityTypeEnum.SYNDROME,
            confidence=0.88,
            position=74,
            length=4,
        )
        session.add_all([formula, herb, syndrome])
        session.flush()
        return str(formula.id), str(herb.id), str(syndrome.id)


def test_mines_reviewable_candidate_edges_from_document_proximity() -> None:
    db = _db()
    try:
        formula_id, herb_id, _ = _seed_entities(db)
        enhancer = KGNodeSelfLearningEnhancer(db, max_candidates=10, min_confidence=0.5)

        candidates = enhancer.mine_candidate_edges(cycle_id="cycle-kg-1")
        contains = [
            item for item in candidates if item["relationship_type"] == "CONTAINS"
        ]

        assert contains
        assert contains[0]["source_entity_id"] == formula_id
        assert contains[0]["target_entity_id"] == herb_id
        assert contains[0]["review_status"] == "pending"
        assert contains[0]["needs_expert_review"] is True
        assert "document_proximity" in contains[0]["signals"]

        insights = enhancer.candidates_to_learning_insights(
            candidates, cycle_id="cycle-kg-1"
        )
        assert insights[0]["insight_type"] == "weak_edge_candidate"
        assert insights[0]["source"] == "weak_edge_candidate_repo"
        assert insights[0]["evidence_refs_json"][0]["candidate_edge_id"].startswith(
            "weak-edge:"
        )
        assert insights[0]["evidence_refs_json"][0]["duplicate_count"] == 1
    finally:
        db.close()


def test_persist_candidate_insights_uses_learning_insight_repo() -> None:
    db = _db()
    try:
        _seed_entities(db)
        repo = LearningInsightRepo(db)
        enhancer = KGNodeSelfLearningEnhancer(
            db,
            learning_insight_repo=repo,
            max_candidates=5,
            min_confidence=0.5,
        )

        persisted = enhancer.persist_candidate_insights(cycle_id="cycle-kg-2")

        assert persisted
        candidates = WeakEdgeCandidateRepository(db).list_candidates(status="all")
        assert [
            item for item in candidates if item["insight_type"] == "weak_edge_candidate"
        ]
    finally:
        db.close()


def test_existing_edge_is_not_reproposed() -> None:
    db = _db()
    try:
        formula_id, herb_id, _ = _seed_entities(db)
        with db.session_scope() as session:
            rel_type = RelationshipType(
                id=uuid.uuid4(),
                relationship_name="contains",
                relationship_type="CONTAINS",
                confidence_baseline=0.8,
            )
            session.add(rel_type)
            session.flush()
            session.add(
                EntityRelationship(
                    source_entity_id=formula_id,
                    target_entity_id=herb_id,
                    relationship_type_id=rel_type.id,
                    confidence=0.9,
                    created_by_module="test",
                )
            )

        enhancer = KGNodeSelfLearningEnhancer(db, max_candidates=10, min_confidence=0.5)
        candidates = enhancer.mine_candidate_edges(cycle_id="cycle-kg-3")

        assert not [
            item
            for item in candidates
            if item["source_entity_id"] == formula_id
            and item["target_entity_id"] == herb_id
        ]
    finally:
        db.close()


def test_apply_reviewed_edges_only_accepts_expert_accepted_candidates() -> None:
    db = _db()
    try:
        formula_id, herb_id, _ = _seed_entities(db)
        enhancer = KGNodeSelfLearningEnhancer(db, max_candidates=10, min_confidence=0.5)
        candidate = next(
            item
            for item in enhancer.mine_candidate_edges(cycle_id="cycle-kg-4")
            if item["source_entity_id"] == formula_id
            and item["target_entity_id"] == herb_id
        )

        dry_run = enhancer.apply_reviewed_edges(
            [{"review_status": "accepted", "candidate_edge": candidate}],
            dry_run=True,
        )
        assert dry_run["applied"] == 0
        assert dry_run["items"][0]["dry_run"] is True

        rejected = enhancer.apply_reviewed_edges(
            [{"review_status": "rejected", "candidate_edge": candidate}],
        )
        assert rejected["applied"] == 0

        applied = enhancer.apply_reviewed_edges(
            [{"review_status": "accepted", "candidate_edge": candidate}],
            reviewer="reviewer-a",
        )
        assert applied["applied"] == 1
        with db.session_scope() as session:
            row = session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM entity_relationships er
                    JOIN relationship_types rt ON rt.id = er.relationship_type_id
                    WHERE er.source_entity_id = :source_id
                      AND er.target_entity_id = :target_id
                      AND rt.relationship_type = 'CONTAINS'
                    """
                ),
                {"source_id": formula_id, "target_id": herb_id},
            ).scalar_one()
            assert row == 1
    finally:
        db.close()
