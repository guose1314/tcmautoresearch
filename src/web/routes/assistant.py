# -*- coding: utf-8 -*-
"""AI 助手路由 — 对话、历史管理与 WebSocket 流式输出。"""

import json
import logging
from typing import Any, Dict, Optional

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

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=50_000)
    session_id: str = Field("default", max_length=200)
    context: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_engine_instance = None


def _get_engine():
    global _engine_instance  # noqa: PLW0603
    if _engine_instance is None:
        from src.ai_assistant import AssistantEngine
        _engine_instance = AssistantEngine()
    return _engine_instance


# ---------------------------------------------------------------------------
# REST routes
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """与 AI 助手对话。"""
    try:
        engine = _get_engine()
        result = engine.chat(
            message=body.message,
            session_id=body.session_id,
            context=body.context,
        )
        return result
    except Exception as exc:
        logger.exception("AI 助手对话失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"对话失败: {exc}",
        ) from exc


@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取对话历史。"""
    engine = _get_engine()
    history = engine.get_history(session_id)
    return {"session_id": session_id, "history": history, "total": len(history)}


@router.delete("/history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(
    session_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """清除对话历史。"""
    engine = _get_engine()
    engine.clear_history(session_id)


# ---------------------------------------------------------------------------
# WebSocket streaming
# ---------------------------------------------------------------------------


@router.websocket("/stream")
async def ws_stream(ws: WebSocket):
    """WebSocket 端点 — 支持 LLM 流式输出。

    连接协议::

        1. 客户端发送首条消息进行认证: {"token": "<JWT>"}
        2. 认证通过后，发送对话消息:   {"message": str, "session_id": str, "context": dict|null}
        3. 服务端逐块推送:             {"type": "chunk", "content": str}
        4. 结束时推送:                 {"type": "done", "reply": str, "suggestions": list, "references": list, "intent": str}
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

    # ---- register with ConnectionManager ----
    from src.web.ws_manager import get_manager

    manager = get_manager()
    session_room = f"assistant:{payload.get('user_id', 'anon')}"
    await manager.connect(ws, session_room)

    # ---- Step 2: conversation loop ----
    engine = _get_engine()
    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            message = data.get("message", "")
            session_id = data.get("session_id", "default")
            context = data.get("context")

            if not message:
                await ws.send_json({"type": "error", "detail": "消息不能为空"})
                continue

            # 调用引擎获取完整回复，然后分块推送
            result = engine.chat(
                message=message,
                session_id=session_id,
                context=context,
            )

            reply = result.get("reply", "")
            # 模拟流式输出：按句切分推送
            chunks = _split_into_chunks(reply)
            for chunk in chunks:
                await ws.send_json({"type": "chunk", "content": chunk})

            await ws.send_json({
                "type": "done",
                "reply": reply,
                "suggestions": result.get("suggestions", []),
                "references": result.get("references", []),
                "intent": result.get("intent", ""),
            })
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接")
    except Exception as exc:
        logger.exception("WebSocket 对话异常")
        try:
            await ws.send_json({"type": "error", "detail": str(exc)})
        except Exception:
            pass
    finally:
        manager.disconnect(ws, session_room)


def _split_into_chunks(text: str, max_chunk: int = 80) -> list[str]:
    """将文本按句号/换行分块，单块不超过 max_chunk 字符。"""
    if not text:
        return []
    import re
    # 按中英文句号、换行拆分
    segments = re.split(r'(?<=[。．.！？\n])', text)
    chunks: list[str] = []
    buf = ""
    for seg in segments:
        if len(buf) + len(seg) > max_chunk and buf:
            chunks.append(buf)
            buf = seg
        else:
            buf += seg
    if buf:
        chunks.append(buf)
    return chunks
