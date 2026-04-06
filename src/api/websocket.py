"""WebSocket helpers for Architecture 3.0 real-time progress streaming."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from src.api.dependencies import verify_management_api_key_for_websocket


async def _authenticate_and_get_job(
    websocket: WebSocket, job_id: str,
) -> Optional[Tuple["object", "object"]]:
    """校验认证并获取 job，失败时关闭连接并返回 None。"""
    try:
        verify_management_api_key_for_websocket(websocket)
    except HTTPException:
        await websocket.close(code=4401, reason="缺少或无效的认证凭据")
        return None

    manager = getattr(websocket.app.state, "job_manager", None)
    if manager is None:
        await websocket.close(code=1011, reason="job manager 未配置")
        return None

    job = manager.get_job(job_id)
    if job is None:
        await websocket.close(code=4404, reason="job 不存在")
        return None

    return manager, job


def _drain_pending_events(job: "object", cursor: int) -> Tuple[list, int]:
    """从 job.events 中拉取未发送事件，返回 (events, new_cursor)。"""
    with job.condition:  # type: ignore[attr-defined]
        if cursor < len(job.events):  # type: ignore[attr-defined]
            pending = job.events[cursor:]  # type: ignore[attr-defined]
            return pending, len(job.events)  # type: ignore[attr-defined]
    return [], cursor


async def stream_job_events_over_websocket(websocket: WebSocket, job_id: str) -> None:
    """Stream job events to a WebSocket client using the shared job event envelope."""

    result = await _authenticate_and_get_job(websocket, job_id)
    if result is None:
        return
    _manager, job = result

    await websocket.accept()
    cursor = 0
    try:
        while True:
            pending_events, cursor = _drain_pending_events(job, cursor)
            if pending_events:
                for event in pending_events:
                    await websocket.send_json(event)
                if job.is_terminal() and cursor >= len(job.events):
                    break
                continue
            if job.is_terminal():
                break
            await websocket.send_json(
                {
                    "sequence": cursor,
                    "event": "heartbeat",
                    "job_id": job.job_id,
                    "timestamp": datetime.now().isoformat(),
                    "data": {"status": "alive"},
                }
            )
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass