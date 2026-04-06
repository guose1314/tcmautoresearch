"""Research orchestration routes for the Architecture 3.0 REST API."""

from __future__ import annotations

import json
import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
)
from fastapi.responses import Response, StreamingResponse

from src.api import websocket as websocket_streaming
from src.api.dependencies import get_job_manager, require_management_api_key
from src.api.research_utils import (
    build_research_dashboard_payload,
    build_artifact_file_response,
    build_markdown_report,
    build_report_stem,
    normalize_research_request,
    resolve_preferred_report_artifact,
)
from src.api.schemas import (
    ResearchJobAccepted,
    ResearchJobDeletionResponse,
    ResearchJobListResponse,
    ResearchJobSnapshot,
    ResearchDashboardResponse,
    ResearchResult,
    ResearchRunRequest,
)
from web_console.job_manager import ResearchJobManager, format_sse

router = APIRouter(tags=["research"])


@router.post("/run")
def run_research(
    payload: ResearchRunRequest,
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> ResearchResult:
    try:
        return manager.run_sync(normalize_research_request(payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs", status_code=202)
def create_research_job(
    payload: ResearchRunRequest,
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> ResearchJobAccepted:
    try:
        job = manager.create_job(normalize_research_request(payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stream_url": f"/api/research/jobs/{job.job_id}/events",
        "status_url": f"/api/research/jobs/{job.job_id}",
        "websocket_url": f"/api/research/jobs/{job.job_id}/ws",
        "versioned_stream_url": f"/api/v1/research/jobs/{job.job_id}/events",
        "versioned_status_url": f"/api/v1/research/jobs/{job.job_id}",
        "versioned_websocket_url": f"/api/v1/research/jobs/{job.job_id}/ws",
    }


@router.get("/jobs")
def list_research_jobs(
    limit: int=Query(8, ge=1, le=50),
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> ResearchJobListResponse:
    jobs = manager.list_jobs(limit=limit)
    return {
        "jobs": jobs,
        "count": len(jobs),
        "limit": limit,
    }


@router.get("/jobs/{job_id}")
def get_research_job(
    job_id: str,
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> ResearchJobSnapshot:
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job 不存在")
    return job.snapshot()


@router.get("/jobs/{job_id}/dashboard")
def get_research_job_dashboard(
    job_id: str,
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> ResearchDashboardResponse:
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job 不存在")
    return build_research_dashboard_payload(job.snapshot())


@router.delete("/jobs/{job_id}")
def delete_research_job(
    job_id: str,
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> ResearchJobDeletionResponse:
    try:
        return manager.delete_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job 不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/report")
def export_research_job_report(
    job_id: str,
    report_format: str=Query("auto", alias="format"),
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> Response:
    job = manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job 不存在")
    if not isinstance(job.result, dict):
        raise HTTPException(status_code=409, detail="job 尚未生成可导出的最终报告")

    preferred_artifact = resolve_preferred_report_artifact(job.result, report_format)
    if preferred_artifact is not None:
        return build_artifact_file_response(preferred_artifact)

    stem = build_report_stem(job_id, job.result)
    if report_format == "json":
        payload = json.dumps(job.result, ensure_ascii=False, indent=2)
        return Response(
            content=payload.encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="research-report-{stem}.json"'},
        )
    if report_format in {"markdown", "auto"}:
        payload = build_markdown_report(job_id, job.result)
        return Response(
            content=payload.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'inline; filename="research-report-{stem}.md"'},
        )
    raise HTTPException(status_code=400, detail="仅支持 auto、markdown 或 json 导出")


@router.get("/jobs/{job_id}/events")
def stream_research_job(
    job_id: str,
    manager: ResearchJobManager=Depends(get_job_manager),
    _: None=Depends(require_management_api_key),
) -> StreamingResponse:
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


@router.websocket("/jobs/{job_id}/ws")
async def websocket_research_job(websocket: WebSocket, job_id: str) -> None:
    await websocket_streaming.stream_job_events_over_websocket(websocket, job_id)
