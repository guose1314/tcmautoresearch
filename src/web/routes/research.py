# -*- coding: utf-8 -*-
"""科研路由 — 研究课题的创建、查询与阶段执行。"""

import dataclasses
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.web.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class CreateResearchRequest(BaseModel):
    """创建研究课题的请求体。"""

    cycle_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    objective: str = Field("", max_length=2000)
    scope: str = Field("", max_length=1000)
    researchers: Optional[List[str]] = None


class ExecutePhaseRequest(BaseModel):
    """执行研究阶段的请求体。"""

    phase: str = Field(
        ...,
        description="阶段名称: observe / hypothesis / experiment / analyze / publish / reflect",
    )
    phase_context: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_pipeline_instance = None


def _get_pipeline():
    """惰性获取 ResearchPipeline 单例。"""
    global _pipeline_instance  # noqa: PLW0603
    if _pipeline_instance is None:
        from src.research.research_pipeline import ResearchPipeline

        _pipeline_instance = ResearchPipeline()
    return _pipeline_instance


def _cycle_to_dict(cycle) -> Dict[str, Any]:
    """将 ResearchCycle dataclass 转为可序列化字典。"""
    if dataclasses.is_dataclass(cycle) and not isinstance(cycle, type):
        data = dataclasses.asdict(cycle)
        # Enum 值转字符串
        for key, val in data.items():
            if hasattr(val, "value"):
                data[key] = val.value
            elif isinstance(val, dict):
                data[key] = {
                    (k.value if hasattr(k, "value") else k): v
                    for k, v in val.items()
                }
        return data
    if isinstance(cycle, dict):
        return cycle
    return {"data": str(cycle)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_research(
    body: CreateResearchRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """创建研究课题。"""
    try:
        pipeline = _get_pipeline()
        cycle = pipeline.create_research_cycle(
            cycle_name=body.cycle_name,
            description=body.description,
            objective=body.objective,
            scope=body.scope,
            researchers=body.researchers,
        )
        logger.info("用户 %s 创建研究课题: %s", user.get("user_id"), body.cycle_name)
        return {"message": "研究课题创建成功", "cycle": _cycle_to_dict(cycle)}
    except Exception as exc:
        logger.exception("创建研究课题失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建研究课题失败: {exc}",
        ) from exc


@router.get("/{cycle_id}")
async def get_research_detail(
    cycle_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取研究课题详情。"""
    try:
        pipeline = _get_pipeline()
        orchestrator = getattr(pipeline, "orchestrator", None)
        if orchestrator is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="研究编排器未初始化",
            )
        cycle = orchestrator.get_research_cycle(cycle_id)
        if cycle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到研究课题: {cycle_id}",
            )
        return {"cycle": _cycle_to_dict(cycle)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取研究课题详情失败: %s", cycle_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取研究详情失败: {exc}",
        ) from exc


@router.post("/{cycle_id}/execute")
async def execute_research_phase(
    cycle_id: str,
    body: ExecutePhaseRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """执行指定研究阶段。"""
    from src.research.study_session_manager import ResearchPhase

    # 验证 phase 值
    try:
        phase_enum = ResearchPhase(body.phase)
    except ValueError:
        valid = [p.value for p in ResearchPhase]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无效的阶段名称 '{body.phase}'，可用值: {valid}",
        )

    try:
        pipeline = _get_pipeline()
        result = pipeline.execute_research_phase(
            cycle_id=cycle_id,
            phase=phase_enum,
            phase_context=body.phase_context,
        )
        logger.info(
            "用户 %s 执行阶段 %s (cycle=%s)",
            user.get("user_id"),
            body.phase,
            cycle_id,
        )
        return {"message": f"阶段 '{body.phase}' 执行完成", "result": result}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("执行研究阶段失败: cycle=%s phase=%s", cycle_id, body.phase)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"执行研究阶段失败: {exc}",
        ) from exc


@router.get("/list", name="research_list")
async def list_research(
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取所有研究项目列表。"""
    try:
        pipeline = _get_pipeline()
        orchestrator = getattr(pipeline, "orchestrator", None)
        if orchestrator is None:
            return {"cycles": []}

        # orchestrator 可能提供 list / get_all 方法
        cycles_raw = []
        for method_name in ("list_research_cycles", "get_all_cycles", "list_cycles"):
            fn = getattr(orchestrator, method_name, None)
            if callable(fn):
                cycles_raw = fn()
                break

        cycles = [_cycle_to_dict(c) for c in cycles_raw] if cycles_raw else []
        return {"cycles": cycles, "total": len(cycles)}
    except Exception as exc:
        logger.exception("获取研究列表失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取研究列表失败: {exc}",
        ) from exc
