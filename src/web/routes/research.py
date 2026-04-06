# -*- coding: utf-8 -*-
"""科研路由 — 研究课题的创建、查询、阶段执行与 WebSocket 实时推送。"""

import dataclasses
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from src.web.auth import get_current_user, verify_token

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
        cycles = getattr(pipeline, "research_cycles", None)
        if cycles is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="研究编排器未初始化",
            )
        cycle = cycles.get(cycle_id)
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


# ---------------------------------------------------------------------------
# WebSocket — 研究进度实时推送
# ---------------------------------------------------------------------------


@router.websocket("/progress/{cycle_id}")
async def ws_research_progress(ws: WebSocket, cycle_id: str):
    """WebSocket 端点 — 实时推送研究阶段执行进度。

    连接协议::

        1. 客户端发送首条消息进行认证:  {"token": "<JWT>"}
        2. 认证通过后服务端推送:        {"type": "auth_ok"}
        3. 阶段开始时推送:              {"type": "phase_started",  "data": {...}}
        4. 阶段进度推送:                {"type": "phase_progress", "data": {"phase": str, "progress": float}}
        5. 阶段完成推送:                {"type": "phase_completed","data": {...}}
        6. 全部完成推送:                {"type": "research_done",  "data": {...}}
        7. 客户端可发送 {"action": "ping"} 保持连接
    """
    await ws.accept()

    # ---- Step 1: authenticate ----
    try:
        auth_msg = await ws.receive_text()
        auth_data = json.loads(auth_msg)
        token = auth_data.get("token", "")
        payload = verify_token(token)
        if payload is None:
            await ws.send_json({"type": "error", "detail": "认证失败"})
            await ws.close(code=4001)
            return
    except Exception:
        await ws.send_json({"type": "error", "detail": "认证失败"})
        await ws.close(code=4001)
        return

    await ws.send_json({"type": "auth_ok", "user_id": payload.get("user_id", "")})

    # ---- Step 2: register to room ----
    from src.web.ws_manager import get_manager

    manager = get_manager()
    room = f"research:{cycle_id}"
    await manager.connect(ws, room)

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            action = data.get("action", "")
            if action == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("研究进度 WS 断开: cycle=%s", cycle_id)
    except Exception as exc:
        logger.debug("研究进度 WS 异常: %s", exc)
    finally:
        manager.disconnect(ws, room)
