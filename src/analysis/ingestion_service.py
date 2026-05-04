from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence
from uuid import UUID

from src.analysis.unsupervised_research_enhancer import (
    apply_unsupervised_annotations,
    build_unsupervised_research_view,
)

logger = logging.getLogger(__name__)


PreprocessorProvider = Callable[[], Any]
ExtractorProvider = Callable[[], Any]
GraphBuilderProvider = Callable[[], Any]
KgProvider = Callable[[], Any]
UnsupervisedBuilder = Callable[
    [str, Optional[str], list[Dict[str, Any]], Dict[str, Any]],
    tuple[list[Dict[str, Any]], Dict[str, Any], Dict[str, Any]],
]
KgPersistor = Callable[[list[Dict[str, Any]], Dict[str, Any]], Dict[str, int]]
OrmPersistor = Callable[..., Dict[str, int]]
ResearchSummaryBuilder = Callable[[Mapping[str, Any]], Dict[str, Any]]
GraphProjectionEnqueuer = Callable[..., Any]


class AnalysisIngestionService:
    """Application service for the Web analysis text ingestion pipeline."""

    def __init__(
        self,
        *,
        preprocessor_provider: Optional[PreprocessorProvider] = None,
        extractor_provider: Optional[ExtractorProvider] = None,
        graph_builder_provider: Optional[GraphBuilderProvider] = None,
        kg_provider: Optional[KgProvider] = None,
        unsupervised_builder: Optional[UnsupervisedBuilder] = None,
        kg_persistor: Optional[KgPersistor] = None,
        orm_persistor: Optional[OrmPersistor] = None,
        research_summary_builder: Optional[ResearchSummaryBuilder] = None,
        graph_projection_enqueuer: Optional[GraphProjectionEnqueuer] = None,
        created_by: str = "text_analysis",
    ) -> None:
        self._preprocessor_provider = preprocessor_provider or _default_preprocessor
        self._extractor_provider = extractor_provider or _default_extractor
        self._graph_builder_provider = graph_builder_provider or _default_graph_builder
        self._kg_provider = kg_provider
        self._unsupervised_builder = unsupervised_builder or build_unsupervised_assets
        self._kg_persistor = kg_persistor or _noop_kg_persistor
        self._orm_persistor = orm_persistor or _noop_orm_persistor
        self._research_summary_builder = (
            research_summary_builder or build_research_response_summary
        )
        self._graph_projection_enqueuer = graph_projection_enqueuer
        self._created_by = str(created_by or "text_analysis")

    def analyze_and_persist(
        self,
        raw_text: str,
        source_file: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run preprocess/extract/graph/enhance/persist and return API summary."""
        preprocess_ctx: Dict[str, Any] = {"raw_text": raw_text}
        if source_file:
            preprocess_ctx["source_file"] = source_file
        if metadata:
            preprocess_ctx["metadata"] = dict(metadata)

        preprocessor = self._preprocessor_provider()
        preprocess_result = preprocessor.execute(preprocess_ctx)

        extractor = self._extractor_provider()
        extraction_result = extractor.execute(preprocess_result)

        graph_builder = self._graph_builder_provider()
        semantic_result = graph_builder.execute(extraction_result)

        entities = list(extraction_result.get("entities", []) or [])
        graph_data = dict(semantic_result.get("semantic_graph", {}) or {})
        entities, graph_data, research_view = self._unsupervised_builder(
            raw_text,
            source_file,
            entities,
            graph_data,
        )

        persisted = self._kg_persistor(entities, graph_data)
        orm_result = self._orm_persistor(
            entities=entities,
            graph_data=graph_data,
            source_file=source_file,
            created_by=self._created_by,
            raw_text=raw_text,
            metadata=metadata,
            semantic_result=semantic_result,
            research_view=research_view,
        )
        kg_counts = self._resolve_kg_counts()

        return {
            "message": "文本分析完成",
            "preprocessing": {
                "processed_text": preprocess_result.get("processed_text", ""),
                "processing_steps": preprocess_result.get("processing_steps", []),
            },
            "entities": {
                "items": entities,
                "statistics": extraction_result.get("statistics", {}),
            },
            "semantic_graph": {
                "graph": graph_data,
                "statistics": semantic_result.get("graph_statistics", {}),
            },
            "knowledge_accumulation": {
                "new_entities": int(persisted.get("new_entities", 0)),
                "new_relations": int(persisted.get("new_relations", 0)),
                "total_entities": kg_counts["total_entities"],
                "total_relations": kg_counts["total_relations"],
                "orm_entities": int(orm_result.get("orm_entities", 0)),
                "orm_relations": int(orm_result.get("orm_relations", 0)),
                "orm_statistics": int(orm_result.get("orm_statistics", 0)),
                "orm_analyses": int(orm_result.get("orm_analyses", 0)),
                "neo4j_nodes": int(orm_result.get("neo4j_nodes", 0)),
                "neo4j_edges": int(orm_result.get("neo4j_edges", 0)),
            },
            "research_enhancement": self._research_summary_builder(research_view),
        }

    def _resolve_kg_counts(self) -> Dict[str, int]:
        if self._kg_provider is None:
            return {"total_entities": 0, "total_relations": 0}
        try:
            kg = self._kg_provider()
        except Exception as exc:  # noqa: BLE001
            logger.warning("analysis KG count resolution failed: %s", exc)
            return {"total_entities": 0, "total_relations": 0}
        return {
            "total_entities": int(getattr(kg, "entity_count", 0) or 0),
            "total_relations": int(getattr(kg, "relation_count", 0) or 0),
        }

    def project_graph_assets(
        self,
        projection_entities: Sequence[Mapping[str, Any]],
        projection_relations: Sequence[Mapping[str, Any]],
        *,
        session: Any = None,
        db_manager: Any = None,
        storage_factory: Any = None,
        cycle_id: Optional[str] = None,
        phase: str = "analysis",
        source_file: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queue legacy Web analysis graph assets through the graph outbox."""
        graph_payload = build_graph_projection_payload(
            projection_entities,
            projection_relations,
        )
        node_count = len(graph_payload["nodes"])
        edge_count = len(graph_payload["edges"])
        if node_count == 0 and edge_count == 0:
            return {
                "neo4j_nodes": 0,
                "neo4j_edges": 0,
                "graph_projection_status": "empty",
                "graph_projection_mode": "outbox",
                "needs_backfill": False,
            }

        normalized_cycle_id = str(cycle_id or source_file or "web-analysis").strip()
        normalized_phase = str(phase or "analysis").strip().lower() or "analysis"
        normalized_idempotency_key = str(
            idempotency_key
            or f"web-analysis:{normalized_cycle_id}:{normalized_phase}:graph"
        ).strip()

        try:
            event_ref = None
            if self._graph_projection_enqueuer is not None:
                event_ref = self._graph_projection_enqueuer(
                    cycle_id=normalized_cycle_id,
                    phase=normalized_phase,
                    graph_payload=graph_payload,
                    idempotency_key=normalized_idempotency_key,
                    session=session,
                    db_manager=db_manager,
                    storage_factory=storage_factory,
                )
            elif storage_factory is not None and hasattr(
                storage_factory,
                "enqueue_graph_projection",
            ):
                event_ref = storage_factory.enqueue_graph_projection(
                    normalized_cycle_id,
                    normalized_phase,
                    graph_payload,
                    normalized_idempotency_key,
                )
            elif session is not None or db_manager is not None:
                from src.storage.outbox.graph_projection import enqueue_graph_projection

                if session is not None:
                    event_ref = enqueue_graph_projection(
                        normalized_cycle_id,
                        normalized_phase,
                        graph_payload,
                        normalized_idempotency_key,
                        session=session,
                    )
                else:
                    with db_manager.session_scope() as outbox_session:
                        event_ref = enqueue_graph_projection(
                            normalized_cycle_id,
                            normalized_phase,
                            graph_payload,
                            normalized_idempotency_key,
                            session=outbox_session,
                        )
            else:
                return {
                    "neo4j_nodes": 0,
                    "neo4j_edges": 0,
                    "graph_projection_status": "skipped",
                    "graph_projection_mode": "outbox",
                    "needs_backfill": True,
                    "reason": "storage_factory_or_db_manager_unavailable",
                }

            return {
                "neo4j_nodes": node_count,
                "neo4j_edges": edge_count,
                "graph_projection_status": "queued",
                "graph_projection_mode": "outbox",
                "needs_backfill": False,
                "outbox_event_id": _event_ref_to_text(event_ref),
                "idempotency_key": normalized_idempotency_key,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("analysis graph projection enqueue failed: %s", exc)
            return {
                "neo4j_nodes": 0,
                "neo4j_edges": 0,
                "graph_projection_status": "failed",
                "graph_projection_mode": "outbox",
                "needs_backfill": True,
                "error": str(exc),
            }


def build_unsupervised_assets(
    raw_text: str,
    source_file: Optional[str],
    entities: list[Dict[str, Any]],
    graph_data: Dict[str, Any],
) -> tuple[list[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    research_view = build_unsupervised_research_view(
        raw_text,
        entities,
        graph_data,
        source_file=source_file,
    )
    enriched_entities, enriched_graph = apply_unsupervised_annotations(
        entities,
        graph_data,
        research_view,
    )
    return enriched_entities, enriched_graph, research_view


def build_research_response_summary(
    research_view: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "document_signature": _json_ready(
            research_view.get("document_signature") or {}
        ),
        "community_topics": _json_ready(
            list(research_view.get("community_topics") or [])[:5]
        ),
        "bridge_entities": _json_ready(
            list(research_view.get("bridge_entities") or [])[:5]
        ),
        "novelty_candidates": _json_ready(
            list(research_view.get("novelty_candidates") or [])[:5]
        ),
        "literature_alignment": _json_ready(
            list(research_view.get("literature_alignment") or [])
        ),
    }


def build_graph_projection_payload(
    projection_entities: Sequence[Mapping[str, Any]],
    projection_relations: Sequence[Mapping[str, Any]],
) -> Dict[str, list[Dict[str, Any]]]:
    nodes: list[Dict[str, Any]] = []
    labels_by_id: Dict[str, str] = {}
    for item in projection_entities or []:
        if not isinstance(item, Mapping):
            continue
        node_id = str(item.get("id") or item.get("name") or "").strip()
        if not node_id:
            continue
        label = _graph_label(item.get("label") or item.get("type") or "Entity")
        props = _projection_properties(item)
        nodes.append({"id": node_id, "label": label, "properties": props})
        labels_by_id[node_id] = label

    edges: list[Dict[str, Any]] = []
    for item in projection_relations or []:
        if not isinstance(item, Mapping):
            continue
        source_id = str(
            item.get("source_id") or item.get("src_id") or item.get("source") or ""
        ).strip()
        target_id = str(
            item.get("target_id") or item.get("dst_id") or item.get("target") or ""
        ).strip()
        if not source_id or not target_id:
            continue
        rel_type = _graph_relationship_type(
            item.get("relationship_type")
            or item.get("rel_type")
            or item.get("relation")
        )
        source_label = _graph_label(
            item.get("source_label")
            or item.get("src_label")
            or labels_by_id.get(source_id)
            or "Entity"
        )
        target_label = _graph_label(
            item.get("target_label")
            or item.get("dst_label")
            or labels_by_id.get(target_id)
            or "Entity"
        )
        props = _projection_properties(item)
        edges.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "source_label": source_label,
                "target_label": target_label,
                "relationship_type": rel_type,
                "properties": props,
            }
        )
    return {"nodes": nodes, "edges": edges}


def _projection_properties(item: Mapping[str, Any]) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    raw_props = item.get("props") or item.get("properties") or {}
    if isinstance(raw_props, Mapping):
        props.update(_json_ready(raw_props))
    name = str(item.get("name") or "").strip()
    if name and "name" not in props:
        props["name"] = name
    return props


def _graph_label(value: Any) -> str:
    text = str(value or "Entity").strip()
    aliases = {
        "research_document": "ResearchDocument",
        "research_topic": "ResearchTopic",
        "topic": "ResearchTopic",
        "formula": "Formula",
        "herb": "Herb",
        "syndrome": "Syndrome",
        "symptom": "Symptom",
        "efficacy": "Efficacy",
        "property": "Property",
        "other": "Entity",
        "generic": "Entity",
    }
    lowered = text.lower()
    if lowered in aliases:
        return aliases[lowered]
    tokens = [token for token in text.replace("-", "_").split("_") if token]
    label = "".join(token[:1].upper() + token[1:] for token in tokens)
    if not label or not label.replace("_", "").isalnum() or not label[0].isalpha():
        return "Entity"
    return label


def _graph_relationship_type(value: Any) -> str:
    text = str(value or "RELATED").strip().upper()
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)
    cleaned = "_".join(token for token in cleaned.split("_") if token)
    if not cleaned or not cleaned[0].isalpha():
        return "RELATED"
    return cleaned


def _event_ref_to_text(value: Any) -> str:
    if value is None:
        return ""
    event_id = getattr(value, "id", None)
    return str(event_id if event_id is not None else value)


def _default_preprocessor() -> Any:
    from src.analysis.preprocessor import DocumentPreprocessor

    inst = DocumentPreprocessor()
    inst.initialize()
    return inst


def _default_extractor() -> Any:
    from src.analysis.entity_extractor import AdvancedEntityExtractor

    inst = AdvancedEntityExtractor()
    inst.initialize()
    return inst


def _default_graph_builder() -> Any:
    from src.analysis.semantic_graph import SemanticGraphBuilder

    inst = SemanticGraphBuilder()
    inst.initialize()
    return inst


def _noop_kg_persistor(
    _entities: list[Dict[str, Any]],
    _graph_data: Dict[str, Any],
) -> Dict[str, int]:
    return {"new_entities": 0, "new_relations": 0}


def _noop_orm_persistor(**_kwargs: Any) -> Dict[str, int]:
    return {
        "orm_entities": 0,
        "orm_relations": 0,
        "orm_statistics": 0,
        "orm_analyses": 0,
        "neo4j_nodes": 0,
        "neo4j_edges": 0,
        "needs_backfill": False,
    }


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, (tuple, set)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value") and not isinstance(
        value, (str, bytes, int, float, bool)
    ):
        return _json_ready(value.value)
    return str(value)


__all__ = [
    "AnalysisIngestionService",
    "build_graph_projection_payload",
    "build_research_response_summary",
    "build_unsupervised_assets",
]
