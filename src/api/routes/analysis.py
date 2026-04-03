"""Text-analysis preview routes for the Architecture 3.0 REST API."""

from __future__ import annotations

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