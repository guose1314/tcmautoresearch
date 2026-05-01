from __future__ import annotations

import warnings
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch

from src.analysis.ingestion_service import AnalysisIngestionService
from src.infrastructure.persistence import DatabaseManager, OutboxEventORM
from src.storage.outbox.graph_projection import GRAPH_PROJECTION_EVENT_TYPE
from src.web.routes import analysis


class _FakeStep:
    def __init__(self, result: Dict[str, Any]) -> None:
        self.result = result
        self.calls = []

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(payload)
        return dict(self.result)


class _FakeKg:
    entity_count = 42
    relation_count = 24


def test_analysis_ingestion_service_preserves_text_response_contract() -> None:
    preprocessor = _FakeStep(
        {"processed_text": "桂枝汤 processed", "processing_steps": ["normalize"]}
    )
    extractor = _FakeStep(
        {
            "entities": [{"name": "桂枝汤", "type": "formula"}],
            "statistics": {"entity_count": 1},
        }
    )
    graph_builder = _FakeStep(
        {
            "semantic_graph": {
                "nodes": [{"id": "桂枝汤"}],
                "edges": [{"source": "桂枝汤", "target": "营卫不和"}],
            },
            "graph_statistics": {"nodes_count": 1, "edges_count": 1},
        }
    )
    orm_calls = []

    def _unsupervised_builder(raw_text, source_file, entities, graph_data):
        return (
            [{**entities[0], "unsupervised_learning": {"community_id": 1}}],
            {**graph_data, "enhanced": True},
            {"community_topics": [{"label": "方证"}]},
        )

    def _kg_persistor(entities, graph_data):
        assert entities[0]["unsupervised_learning"]["community_id"] == 1
        assert graph_data["enhanced"] is True
        return {"new_entities": 1, "new_relations": 1}

    def _orm_persistor(**kwargs):
        orm_calls.append(kwargs)
        return {
            "orm_entities": 1,
            "orm_relations": 1,
            "orm_statistics": 1,
            "orm_analyses": 1,
            "neo4j_nodes": 2,
            "neo4j_edges": 1,
            "needs_backfill": False,
        }

    service = AnalysisIngestionService(
        preprocessor_provider=lambda: preprocessor,
        extractor_provider=lambda: extractor,
        graph_builder_provider=lambda: graph_builder,
        kg_provider=lambda: _FakeKg(),
        unsupervised_builder=_unsupervised_builder,
        kg_persistor=_kg_persistor,
        orm_persistor=_orm_persistor,
        research_summary_builder=lambda view: {
            "community_topics": view["community_topics"]
        },
    )

    response = service.analyze_and_persist(
        "桂枝汤调和营卫",
        "shanghanlun.txt",
        {"dynasty": "东汉"},
    )

    assert response["message"] == "文本分析完成"
    assert response["preprocessing"]["processed_text"] == "桂枝汤 processed"
    assert response["entities"]["items"][0]["name"] == "桂枝汤"
    assert response["semantic_graph"]["graph"]["enhanced"] is True
    assert response["semantic_graph"]["statistics"] == {
        "nodes_count": 1,
        "edges_count": 1,
    }
    assert response["knowledge_accumulation"] == {
        "new_entities": 1,
        "new_relations": 1,
        "total_entities": 42,
        "total_relations": 24,
        "orm_entities": 1,
        "orm_relations": 1,
        "orm_statistics": 1,
        "orm_analyses": 1,
        "neo4j_nodes": 2,
        "neo4j_edges": 1,
    }
    assert response["research_enhancement"]["community_topics"][0]["label"] == "方证"
    assert preprocessor.calls[0]["metadata"] == {"dynasty": "东汉"}
    assert orm_calls[0]["source_file"] == "shanghanlun.txt"
    assert orm_calls[0]["created_by"] == "text_analysis"
    assert orm_calls[0]["raw_text"] == "桂枝汤调和营卫"


def test_text_route_uses_service_factory_without_direct_neo4j_projection() -> None:
    class _FakeService:
        def __init__(self) -> None:
            self.calls = []

        def analyze_and_persist(self, raw_text, source_file=None, metadata=None):
            self.calls.append(
                {
                    "raw_text": raw_text,
                    "source_file": source_file,
                    "metadata": metadata,
                }
            )
            return {
                "message": "文本分析完成",
                "preprocessing": {"processed_text": raw_text, "processing_steps": []},
                "entities": {"items": [], "statistics": {}},
                "semantic_graph": {"graph": {}, "statistics": {}},
                "knowledge_accumulation": {
                    "new_entities": 0,
                    "new_relations": 0,
                    "total_entities": 0,
                    "total_relations": 0,
                    "orm_entities": 0,
                    "orm_relations": 0,
                    "orm_statistics": 0,
                    "orm_analyses": 0,
                    "neo4j_nodes": 0,
                    "neo4j_edges": 0,
                },
                "research_enhancement": {},
            }

    class _FakeServiceFactory:
        def __init__(self, service: _FakeService) -> None:
            self.service = service
            self.requests = []

        def __call__(self, request):
            self.requests.append(request)
            return self.service

    service = _FakeService()
    factory = _FakeServiceFactory(service)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(analysis_ingestion_service_factory=factory)
        )
    )
    body = analysis.TextAnalysisRequest(
        raw_text="桂枝汤调和营卫",
        source_file="shanghanlun.txt",
        metadata={"dynasty": "东汉"},
    )

    with patch.object(
        analysis,
        "_project_to_neo4j",
        side_effect=AssertionError("route must not project to Neo4j directly"),
    ):
        response = analysis.analyze_text(request, body, user={"user_id": "tester"})

    assert response["message"] == "文本分析完成"
    assert factory.requests == [request]
    assert service.calls == [
        {
            "raw_text": "桂枝汤调和营卫",
            "source_file": "shanghanlun.txt",
            "metadata": {"dynasty": "东汉"},
        }
    ]


def test_project_graph_assets_queues_graph_outbox_payload() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    try:
        service = AnalysisIngestionService()

        result = service.project_graph_assets(
            [{"id": "formula-1", "name": "桂枝汤", "type": "formula"}],
            [
                {
                    "src_id": "formula-1",
                    "dst_id": "syndrome-1",
                    "rel_type": "TREATS",
                    "dst_label": "Syndrome",
                    "props": {"confidence": 0.82},
                }
            ],
            db_manager=db,
            cycle_id="doc-1",
            phase="analysis",
            idempotency_key="doc-1:analysis:graph",
        )

        assert result["graph_projection_status"] == "queued"
        assert result["graph_projection_mode"] == "outbox"
        assert result["neo4j_nodes"] == 1
        assert result["neo4j_edges"] == 1

        with db.session_scope() as session:
            row = session.query(OutboxEventORM).one()
            assert row.event_type == GRAPH_PROJECTION_EVENT_TYPE
            assert row.payload["cycle_id"] == "doc-1"
            graph_payload = row.payload["graph_payload"]
            assert graph_payload["nodes"][0]["label"] == "Formula"
            assert graph_payload["nodes"][0]["properties"]["name"] == "桂枝汤"
            assert graph_payload["edges"][0]["relationship_type"] == "TREATS"
            assert graph_payload["edges"][0]["source_label"] == "Formula"
            assert graph_payload["edges"][0]["target_label"] == "Syndrome"
    finally:
        db.close()


def test_legacy_project_to_neo4j_warns_and_delegates_to_service() -> None:
    class _FakeProjectionService:
        def __init__(self) -> None:
            self.calls = []

        def project_graph_assets(self, entities, relations, **kwargs):
            self.calls.append({"entities": entities, "relations": relations, **kwargs})
            return {"neo4j_nodes": 1, "neo4j_edges": 0}

    service = _FakeProjectionService()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = analysis._project_to_neo4j(
            [{"id": "formula-1", "name": "桂枝汤", "type": "formula"}],
            [],
            service=service,
            cycle_id="doc-1",
        )

    assert result == {"neo4j_nodes": 1, "neo4j_edges": 0}
    assert service.calls[0]["entities"][0]["name"] == "桂枝汤"
    assert service.calls[0]["cycle_id"] == "doc-1"
    assert any(item.category is DeprecationWarning for item in caught)


def test_persist_to_orm_queues_graph_outbox_without_legacy_projection() -> None:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    try:
        with db.session_scope() as session:
            DatabaseManager.create_default_relationships(session)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(db_manager=db))
        )

        with patch.object(
            analysis,
            "_project_to_neo4j",
            side_effect=AssertionError("distill path must not call legacy projector"),
        ):
            result = analysis._persist_to_orm(
                request,
                entities=[
                    {"name": "桂枝汤", "type": "formula", "confidence": 0.9},
                    {"name": "营卫不和", "type": "syndrome", "confidence": 0.8},
                ],
                graph_data={
                    "edges": [
                        {
                            "source": "桂枝汤",
                            "target": "营卫不和",
                            "relation": "treats",
                            "confidence": 0.82,
                        }
                    ]
                },
                source_file="distill.txt",
                created_by="llm_distill",
                raw_text="桂枝汤治疗营卫不和",
                semantic_result={},
                research_view={"document_signature": {"entity_count": 2}},
            )

        assert result["orm_entities"] == 2
        assert result["orm_relations"] == 1
        assert result["neo4j_nodes"] >= 2
        assert result["neo4j_edges"] == 1
        with db.session_scope() as session:
            row = session.query(OutboxEventORM).one()
            assert row.event_type == GRAPH_PROJECTION_EVENT_TYPE
    finally:
        db.close()
