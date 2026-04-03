# -*- coding: utf-8 -*-
"""分析路由 — 方剂分析、文本处理链、知识图谱数据。"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.web.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class FormulaAnalysisRequest(BaseModel):
    """方剂综合分析请求。"""

    perspective: Dict[str, Any] = Field(..., description="研究视角数据")
    formula_comparisons: Optional[List[Dict[str, Any]]] = None
    weights: Optional[Dict[str, float]] = None


class TextAnalysisRequest(BaseModel):
    """文本处理链请求。"""

    raw_text: str = Field(..., min_length=1, max_length=500_000)
    source_file: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_preprocessor = None
_extractor = None
_graph_builder = None


def _get_preprocessor():
    global _preprocessor  # noqa: PLW0603
    if _preprocessor is None:
        from src.analysis.preprocessor import DocumentPreprocessor
        _preprocessor = DocumentPreprocessor()
    return _preprocessor


def _get_extractor():
    global _extractor  # noqa: PLW0603
    if _extractor is None:
        from src.analysis.entity_extractor import AdvancedEntityExtractor
        _extractor = AdvancedEntityExtractor()
    return _extractor


def _get_graph_builder():
    global _graph_builder  # noqa: PLW0603
    if _graph_builder is None:
        from src.analysis.semantic_graph import SemanticGraphBuilder
        _graph_builder = SemanticGraphBuilder()
    return _graph_builder


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/formula")
async def analyze_formula(
    body: FormulaAnalysisRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """方剂综合分析 — 调用 ResearchScoringPanel。"""
    try:
        from src.analysis.research_scoring import ResearchScoringPanel

        result = ResearchScoringPanel.score_research_perspective(
            perspective=body.perspective,
            formula_comparisons=body.formula_comparisons,
            weights=body.weights,
        )
        return {"message": "方剂分析完成", "result": result}
    except Exception as exc:
        logger.exception("方剂分析失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"方剂分析失败: {exc}",
        ) from exc


@router.post("/text")
async def analyze_text(
    body: TextAnalysisRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """文本处理链 — 预处理 → 实体抽取 → 语义建模。"""
    try:
        # 1) 预处理
        preprocessor = _get_preprocessor()
        preprocess_ctx: Dict[str, Any] = {"raw_text": body.raw_text}
        if body.source_file:
            preprocess_ctx["source_file"] = body.source_file
        if body.metadata:
            preprocess_ctx["metadata"] = body.metadata
        preprocess_result = preprocessor.execute(preprocess_ctx)

        # 2) 实体抽取
        extractor = _get_extractor()
        extraction_result = extractor.execute(preprocess_result)

        # 3) 语义建模
        graph_builder = _get_graph_builder()
        semantic_result = graph_builder.execute(extraction_result)

        return {
            "message": "文本分析完成",
            "preprocessing": {
                "processed_text": preprocess_result.get("processed_text", ""),
                "processing_steps": preprocess_result.get("processing_steps", []),
            },
            "entities": {
                "items": extraction_result.get("entities", []),
                "statistics": extraction_result.get("statistics", {}),
            },
            "semantic_graph": {
                "graph": semantic_result.get("semantic_graph", {}),
                "statistics": semantic_result.get("graph_statistics", {}),
            },
        }
    except Exception as exc:
        logger.exception("文本分析链失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文本分析失败: {exc}",
        ) from exc


@router.get("/graph/{research_id}")
async def get_knowledge_graph(
    research_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取知识图谱数据（JSON 格式，供前端可视化）。"""
    try:
        from src.research.research_pipeline import ResearchPipeline

        pipeline = ResearchPipeline()
        orchestrator = getattr(pipeline, "orchestrator", None)
        if orchestrator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="研究编排器未初始化",
            )

        cycle = orchestrator.get_research_cycle(research_id)
        if cycle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到研究课题: {research_id}",
            )

        # 从阶段执行结果中提取图谱数据
        from src.research.study_session_manager import ResearchPhase

        phase_data = {}
        if hasattr(cycle, "phase_executions"):
            phase_data = cycle.phase_executions or {}

        graph_data: Dict[str, Any] = {"nodes": [], "edges": [], "statistics": {}}

        # 尝试从 OBSERVE 阶段获取语义图谱
        observe_result = phase_data.get(ResearchPhase.OBSERVE, phase_data.get("observe", {}))
        if isinstance(observe_result, dict):
            graph_data["nodes"] = observe_result.get("semantic_graph", {}).get("nodes", [])
            graph_data["edges"] = observe_result.get("semantic_graph", {}).get("edges", [])
            graph_data["statistics"] = observe_result.get("graph_statistics", {})

        return {
            "research_id": research_id,
            "graph": graph_data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取知识图谱失败: %s", research_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取知识图谱失败: {exc}",
        ) from exc
