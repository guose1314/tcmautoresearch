"""WebSocket helpers for Architecture 3.0 real-time progress streaming."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from src.api.dependencies import verify_management_api_key_for_websocket


async def stream_job_events_over_websocket(websocket: WebSocket, job_id: str) -> None:
    """Stream job events to a WebSocket client using the shared job event envelope."""

    try:
        verify_management_api_key_for_websocket(websocket)
    except HTTPException:
        await websocket.close(code=4401, reason="缺少或无效的认证凭据")
        return

    manager = getattr(websocket.app.state, "job_manager", None)
    if manager is None:
        await websocket.close(code=1011, reason="job manager 未配置")
        return

    job = manager.get_job(job_id)
    if job is None:
        await websocket.close(code=4404, reason="job 不存在")
        return

    await websocket.accept()
    cursor = 0
    try:
        while True:
            pending_events = []
            with job.condition:
                if cursor < len(job.events):
                    pending_events = job.events[cursor:]
                    cursor = len(job.events)
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