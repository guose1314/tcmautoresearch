"""Text-analysis preview routes for the Architecture 3.0 REST API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.preprocessor import DocumentPreprocessor
from src.api.dependencies import (
    get_entity_extractor,
    get_preprocessor,
    get_relation_extractor,
)
from src.api.schemas import AnalyzeDocumentRequest, AnalyzeDocumentResponse
from src.extraction.relation_extractor import RelationExtractor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])
_SUPPORTED_GRAPH_TYPES = frozenset({"philology_asset_graph"})


@router.post("/documents/preview")
def preview_document_analysis(
    payload: AnalyzeDocumentRequest,
    preprocessor: DocumentPreprocessor = Depends(get_preprocessor),
    entity_extractor: AdvancedEntityExtractor = Depends(get_entity_extractor),
    relation_extractor: RelationExtractor = Depends(get_relation_extractor),
) -> AnalyzeDocumentResponse:
    preprocessed = preprocessor.execute({"raw_text": payload.text})
    processed_text = str(preprocessed.get("processed_text") or "")
    tokens = [str(item) for item in preprocessor.segment_text(processed_text)[: payload.max_tokens_preview]]

    extraction = entity_extractor.execute({"processed_text": processed_text})
    entities: List[Dict[str, Any]] = list(extraction.get("entities") or [])[: payload.max_entities]

    relations: List[Dict[str, Any]] = []
    relation_statistics: Dict[str, Any] = {}
    if payload.include_relations:
        relations = relation_extractor.extract(entities)
        relation_statistics = relation_extractor.relationship_statistics()

    return {
        "processed_text": processed_text,
        "processing_steps": preprocessed.get("processing_steps") or [],
        "analysis_result": {
            "entities": entities,
            "statistics": extraction.get("statistics") or {},
            "confidence_scores": extraction.get("confidence_scores") or {},
            "relations": relations,
            "relation_statistics": relation_statistics,
        },
        "analysis_summary": {
            "input_length": len(payload.text),
            "processed_length": len(processed_text),
            "token_count": len(tokens),
            "preview_tokens": tokens,
            "entity_count": len(entities),
            "relation_count": len(relations),
        },
    }


# ── Knowledge Graph stats ─────────────────────────────────────────────


@router.get("/kg/stats")
def kg_stats() -> Dict[str, Any]:
    """返回知识图谱统计信息、schema 版本与 drift 状态。"""
    from src.storage.graph_schema import get_schema_summary

    result: Dict[str, Any] = get_schema_summary()

    # 尝试从已有 StorageBackendFactory 读取 live drift 状态
    try:
        from src.storage.backend_factory import StorageBackendFactory

        factory = StorageBackendFactory.get_instance()
        neo4j_driver = getattr(factory, "_neo4j_driver", None)
        if neo4j_driver is not None:
            drift_report = neo4j_driver.ensure_schema_version()
            result["schema_drift_detected"] = drift_report.get("drift_detected", False)
            result["drift_report"] = drift_report
            stats = neo4j_driver.get_graph_statistics()
            result["graph_statistics"] = stats
        else:
            result["schema_drift_detected"] = None
            result["drift_report"] = None
            result["graph_statistics"] = None
            result["note"] = "Neo4j driver not initialized"
    except Exception as exc:
        logger.debug("kg/stats 获取 live 数据失败: %s", exc)
        result["schema_drift_detected"] = None
        result["drift_report"] = None
        result["graph_statistics"] = None
        result["note"] = f"Neo4j unavailable: {exc}"

    return result


@router.get("/kg/subgraph")
def kg_subgraph(
    graph_type: str = Query("philology_asset_graph"),
    cycle_id: str = Query(""),
    work_title: str = Query(""),
    version_lineage_key: str = Query(""),
    witness_key: str = Query(""),
    review_status: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """返回受治理的知识图谱子图查询模板，并在 Neo4j 可用时执行只读查询。"""
    from tools.neo4j_query_templates import CANONICAL_READ_TEMPLATES

    template = CANONICAL_READ_TEMPLATES.get(graph_type)
    if graph_type not in _SUPPORTED_GRAPH_TYPES or template is None:
        return {
            "graph_type": graph_type,
            "supported_graph_types": sorted(_SUPPORTED_GRAPH_TYPES),
            "error": "unsupported_graph_type",
        }

    response: Dict[str, Any] = {
        "graph_type": graph_type,
        "supported_graph_types": sorted(_SUPPORTED_GRAPH_TYPES),
        "template": template,
        "params": {
            "cycle_id": cycle_id,
            "work_title": work_title,
            "version_lineage_key": version_lineage_key,
            "witness_key": witness_key,
            "review_status": review_status,
            "limit": limit,
        },
        "records": [],
        "record_count": 0,
    }

    if not cycle_id:
        response["note"] = "cycle_id 为空，仅返回 canonical query template"
        return response

    try:
        from src.storage.backend_factory import StorageBackendFactory

        factory = StorageBackendFactory.get_instance()
        neo4j_driver = getattr(factory, "_neo4j_driver", None)
        if neo4j_driver is None or not getattr(neo4j_driver, "driver", None):
            response["note"] = "Neo4j driver not initialized"
            return response

        with neo4j_driver.driver.session(database=neo4j_driver.database) as session:
            records = session.execute_read(
                lambda tx: [
                    dict(record)
                    for record in tx.run(
                        template["cypher"],
                        cycle_id=cycle_id,
                        work_title=work_title,
                        version_lineage_key=version_lineage_key,
                        witness_key=witness_key,
                        review_status=review_status,
                        limit=limit,
                    )
                ]
            )
        response["records"] = records
        response["record_count"] = len(records)
    except Exception as exc:
        logger.debug("kg/subgraph 执行失败: %s", exc)
        response["note"] = f"Neo4j unavailable: {exc}"

    return response