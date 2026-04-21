"""Text-analysis preview routes for the Architecture 3.0 REST API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

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