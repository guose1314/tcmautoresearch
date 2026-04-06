"""文献提取管道 API 路由 — 单文档/批量/增量提取。"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from fastapi import APIRouter

from src.api.schemas import (
    ExtractionBatchRequest,
    ExtractionBatchResponse,
    ExtractionPipelineRequest,
    ExtractionPipelineResponse,
)
from src.extraction.extraction_pipeline import ExtractionPipeline

router = APIRouter(tags=["extraction"])

# 模块级复用的管道实例（延迟初始化）
_pipeline: ExtractionPipeline | None = None


def _get_pipeline() -> ExtractionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ExtractionPipeline()
    return _pipeline


def _result_to_response(r: Any) -> ExtractionPipelineResponse:
    d = r.to_dict()
    return ExtractionPipelineResponse(
        document_id=d.get("document_id", ""),
        source_file=d.get("source_file", ""),
        total_entities=len(d.get("all_items", [])),
        total_relations=len(d.get("all_relations", [])),
        overall_quality=d.get("overall_quality", {}),
        total_duration_sec=d.get("total_duration_sec", 0.0),
        module_results=d.get("module_results", {}),
        all_items=d.get("all_items", []),
        all_relations=d.get("all_relations", []),
        errors=d.get("errors", []),
    )


@router.post("/extract", response_model=ExtractionPipelineResponse)
def extract_document(payload: ExtractionPipelineRequest) -> ExtractionPipelineResponse:
    """对单篇文档执行全流程文献提取。"""
    pipeline = ExtractionPipeline(
        enable_metadata=payload.enable_metadata,
        enable_medical_content=payload.enable_medical_content,
        enable_clinical=payload.enable_clinical,
        enable_relation=payload.enable_relation,
        enable_academic_assessment=payload.enable_academic_assessment,
        enable_quality_check=payload.enable_quality_check,
    )
    result = pipeline.process_document(
        raw_text=payload.text,
        source_file=payload.source_file,
    )
    return _result_to_response(result)


@router.post("/extract/batch", response_model=ExtractionBatchResponse)
def extract_batch(payload: ExtractionBatchRequest) -> ExtractionBatchResponse:
    """批量文献提取（最多 100 篇）。"""
    t0 = time.perf_counter()
    pipeline = ExtractionPipeline(
        enable_metadata=payload.enable_metadata,
        enable_medical_content=payload.enable_medical_content,
        enable_clinical=payload.enable_clinical,
        enable_relation=payload.enable_relation,
        enable_academic_assessment=payload.enable_academic_assessment,
        enable_quality_check=payload.enable_quality_check,
    )
    docs = [
        {"raw_text": d.raw_text, "source_file": d.source_file, "document_id": d.document_id}
        for d in payload.documents
    ]
    results = pipeline.process_batch(docs)
    duration = time.perf_counter() - t0
    return ExtractionBatchResponse(
        total_documents=len(results),
        results=[_result_to_response(r) for r in results],
        total_duration_sec=duration,
    )
