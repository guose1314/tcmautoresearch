from __future__ import annotations

import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.infrastructure.persistence import (
    DatabaseManager,
    Document,
    Entity,
    EntityTypeEnum,
    LearningInsight,
)
from src.learning.kg_node_self_learning import KGNodeSelfLearningEnhancer
from src.learning.learning_insight_repo import LearningInsightRepo
from src.web.auth import get_current_user
from src.web.routes.candidate_edge_review import router


class _FakeNeo4jDriver:
    def __init__(self) -> None:
        self.nodes = []
        self.relationships = []

    def create_node(self, node) -> bool:
        self.nodes.append(node)
        return True

    def create_relationship(self, edge, source_label: str, target_label: str) -> bool:
        self.relationships.append(
            {
                "edge": edge,
                "source_label": source_label,
                "target_label": target_label,
            }
        )
        return True


def _db() -> DatabaseManager:
    tmpdir = TemporaryDirectory()
    db_path = Path(tmpdir.name) / "candidate-review-api.db"
    db = DatabaseManager(f"sqlite:///{db_path.as_posix()}")
    db._tmpdir = tmpdir
    db.init_db()
    return db


def _close_db(db: DatabaseManager) -> None:
    db.close()
    tmpdir = getattr(db, "_tmpdir", None)
    if tmpdir is not None:
        tmpdir.cleanup()


def _seed_candidate_insight(db: DatabaseManager) -> str:
    with db.session_scope() as session:
        doc = Document(
            source_file=f"candidate-{uuid.uuid4()}.txt",
            content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            document_title="候选边审核测试",
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
        session.add_all([formula, herb])
        session.flush()
    enhancer = KGNodeSelfLearningEnhancer(db, max_candidates=5, min_confidence=0.5)
    candidate = next(
        item
        for item in enhancer.mine_candidate_edges(cycle_id="cycle-review-api")
        if item["relationship_type"] == "CONTAINS"
    )
    insight = enhancer.candidates_to_learning_insights(
        [candidate], cycle_id="cycle-review-api"
    )[0]
    return LearningInsightRepo(db).upsert(insight)["insight_id"]


def _client(db: DatabaseManager, fake_neo4j=None) -> TestClient:
    app = FastAPI()
    app.state.db_manager = db
    if fake_neo4j is not None:
        app.state.neo4j_driver = fake_neo4j
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "expert-1",
        "display_name": "Expert One",
    }
    return TestClient(app)


def test_candidate_edge_accept_writes_pg_and_neo4j_after_review() -> None:
    db = _db()
    try:
        insight_id = _seed_candidate_insight(db)
        fake_neo4j = _FakeNeo4jDriver()
        client = _client(db, fake_neo4j)

        list_response = client.get("/api/review/candidate-edges?status=all")
        assert list_response.status_code == 200
        assert list_response.json()["items"][0]["insight_id"] == insight_id

        response = client.post(
            f"/api/review/candidate-edges/{quote(insight_id, safe='')}/accept",
            json={"reason": "证据充足", "grounding_score": 0.91, "evidence_grade": "A"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "accepted"
        assert payload["apply_result"]["applied"] == 1
        assert fake_neo4j.relationships
        assert fake_neo4j.relationships[0]["edge"].relationship_type == "CONTAINS"
        with db.session_scope() as session:
            relationship_count = session.execute(
                text("SELECT count(*) FROM entity_relationships")
            ).scalar_one()
            row = session.get(LearningInsight, insight_id)
            assert relationship_count == 1
            assert row.status == "accepted"
            feedback = row.evidence_refs_json[-1]
            assert feedback["type"] == "expert_review_feedback"
            assert feedback["expert_vote"] == "accepted"
            assert feedback["relationship_ids"]
    finally:
        _close_db(db)


def test_candidate_edge_reject_records_reason_without_graph_write() -> None:
    db = _db()
    try:
        insight_id = _seed_candidate_insight(db)
        client = _client(db)

        response = client.post(
            f"/api/review/candidate-edges/{quote(insight_id, safe='')}/reject",
            json={"reason": "证据片段无法支持关系"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
        with db.session_scope() as session:
            relationship_count = session.execute(
                text("SELECT count(*) FROM entity_relationships")
            ).scalar_one()
            row = session.get(LearningInsight, insight_id)
            assert relationship_count == 0
            assert row.status == "rejected"
            feedback = row.evidence_refs_json[-1]
            assert feedback["expert_vote"] == "rejected"
            assert feedback["reason"] == "证据片段无法支持关系"
    finally:
        _close_db(db)
