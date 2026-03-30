"""FastAPI REST API + SSE 流式推理进度接口。"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from web_console.job_manager import ResearchJobManager, format_sse


def _normalize_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    topic = str(payload.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic 不能为空")
    return {
        "topic": topic,
        "orchestrator_config": payload.get("orchestrator_config") or {},
        "phase_contexts": payload.get("phase_contexts") or {},
        "cycle_name": payload.get("cycle_name"),
        "description": payload.get("description"),
        "scope": payload.get("scope"),
    }


def create_app(job_manager: Optional[ResearchJobManager] = None) -> FastAPI:
    app = FastAPI(title="TCM Auto Research Web Console", version="0.1.0")
    manager = job_manager or ResearchJobManager()
    app.state.job_manager = manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/research/run")
    def run_research(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        try:
            return manager.run_sync(_normalize_request(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/research/jobs", status_code=202)
    def create_research_job(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        try:
            job = manager.create_job(_normalize_request(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "job_id": job.job_id,
            "status": job.status,
            "stream_url": f"/api/research/jobs/{job.job_id}/events",
            "status_url": f"/api/research/jobs/{job.job_id}",
        }

    @app.get("/api/research/jobs/{job_id}")
    def get_research_job(job_id: str) -> Dict[str, Any]:
        job = manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job 不存在")
        return job.snapshot()

    @app.get("/api/research/jobs/{job_id}/events")
    def stream_research_job(job_id: str) -> StreamingResponse:
        job = manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job 不存在")

        def event_stream():
            cursor = 0
            while True:
                pending_events = []
                with job.condition:
                    if cursor >= len(job.events) and not job.is_terminal():
                        job.condition.wait(timeout=5.0)
                    if cursor < len(job.events):
                        pending_events = job.events[cursor:]
                        cursor = len(job.events)
                if pending_events:
                    for event in pending_events:
                        yield format_sse(event)
                    continue
                if job.is_terminal():
                    break
                yield "event: heartbeat\ndata: {\"status\": \"alive\"}\n\n"
                time.sleep(0.1)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


app = create_app()