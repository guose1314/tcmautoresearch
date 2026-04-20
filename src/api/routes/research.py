"""Research orchestration routes for the Architecture 3.0 REST API."""

from __future__ import annotations

import json
import time

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
)
from fastapi.responses import Response, StreamingResponse

from src.api import websocket as websocket_streaming
from src.api.dependencies import (
    get_job_manager,
    get_research_session_repository,
    require_management_api_key,
)
from src.api.research_utils import (
    build_artifact_file_response,
    build_markdown_report,
    build_report_stem,
    build_research_dashboard_payload,
    normalize_research_request,
    resolve_preferred_report_artifact,
)
from src.api.schemas import (
    ResearchBatchCatalogReviewRequest,
    ResearchBatchCatalogReviewResponse,
    ResearchBatchPhilologyReviewRequest,
    ResearchBatchPhilologyReviewResponse,
    ResearchCatalogReviewRequest,
    ResearchCatalogReviewResponse,
    ResearchDashboardResponse,
    ResearchJobAccepted,
    ResearchJobDeletionResponse,
    ResearchJobListResponse,
    ResearchJobSnapshot,
    ResearchLearningFeedbackLibraryResponse,
    ResearchLearningFeedbackListResponse,
    ResearchPhilologyWorkbenchReviewRequest,
    ResearchPhilologyWorkbenchReviewResponse,
    ResearchResult,
    ResearchRunRequest,
)
from src.infrastructure.research_session_repo import ResearchSessionRepository
from web_console.job_manager import ResearchJobManager, format_sse

router = APIRouter(tags=["research"])


def _resolve_job_snapshot(manager: ResearchJobManager, job_id: str) -> dict:
    job = manager.get_job(job_id)
    if job is not None:
        return job.snapshot()

    payload = manager.get_persisted_job(job_id)
    if isinstance(payload, dict) and isinstance(payload.get("job"), dict):
        return dict(payload["job"])

    raise HTTPException(status_code=404, detail="job 不存在")


def _resolve_cycle_id(job_snapshot: dict) -> str:
    result = job_snapshot.get("result") if isinstance(job_snapshot.get("result"), dict) else {}
    return str(job_snapshot.get("cycle_id") or result.get("cycle_id") or "").strip()


def _resolve_review_reviewer(request: Request, explicit_reviewer: str) -> str:
    reviewer = str(explicit_reviewer or "").strip()
    if reviewer:
        if reviewer == "管理 API Key":
            return "管理 API"
        return reviewer

    auth_context = getattr(request.state, "auth_context", None)
    if isinstance(auth_context, dict):
        auth_source = str(auth_context.get("auth_source") or "").strip()
        if auth_source in {"management_api_key", "open"}:
            return "管理 API"
        for field_name in ("principal", "display_name", "username", "user_id"):
            value = str(auth_context.get(field_name) or "").strip()
            if value:
                if value in {"管理 API Key", "访客"}:
                    return "管理 API"
                return value
    return "管理 API"


def _resolve_learning_feedback_library(
    repository: ResearchSessionRepository,
    cycle_id: str,
) -> ResearchLearningFeedbackLibraryResponse:
    library = repository.get_learning_feedback_library(cycle_id)
    if library is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")
    return {
        "cycle_id": cycle_id,
        "contract_version": str(library.get("contract_version") or ""),
        "summary": dict(library.get("summary") or {}),
        "replay_feedback": dict(library.get("replay_feedback") or {}),
        "records": list(library.get("records") or []),
    }


def _hydrate_dashboard_snapshot_learning_feedback(
    snapshot: dict,
    repository: ResearchSessionRepository,
) -> dict:
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    learning_feedback_library = result.get("learning_feedback_library") if isinstance(result.get("learning_feedback_library"), dict) else {}
    if learning_feedback_library:
        return snapshot

    cycle_id = _resolve_cycle_id(snapshot)
    if not cycle_id:
        return snapshot

    repository_library = repository.get_learning_feedback_library(cycle_id)
    if repository_library is None:
        return snapshot

    hydrated_snapshot = dict(snapshot)
    hydrated_result = dict(result)
    hydrated_result["learning_feedback_library"] = repository_library
    hydrated_snapshot["result"] = hydrated_result
    return hydrated_snapshot


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
    return _resolve_job_snapshot(manager, job_id)


@router.get("/jobs/{job_id}/dashboard")
def get_research_job_dashboard(
    job_id: str,
    document_title: str=Query(""),
    work_title: str=Query(""),
    version_lineage_key: str=Query(""),
    witness_key: str=Query(""),
    asset_type: str=Query(""),
    review_status: str=Query(""),
    priority_bucket: str=Query(""),
    reviewer: str=Query(""),
    manager: ResearchJobManager=Depends(get_job_manager),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchDashboardResponse:
    return build_research_dashboard_payload(
        _hydrate_dashboard_snapshot_learning_feedback(_resolve_job_snapshot(manager, job_id), repository),
        philology_filters={
            "document_title": document_title,
            "work_title": work_title,
            "version_lineage_key": version_lineage_key,
            "witness_key": witness_key,
            "asset_type": asset_type,
            "review_status": review_status,
            "priority_bucket": priority_bucket,
            "reviewer": reviewer,
        },
    )


@router.get("/jobs/{job_id}/learning-feedback")
def get_research_job_learning_feedback(
    job_id: str,
    manager: ResearchJobManager=Depends(get_job_manager),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchLearningFeedbackLibraryResponse:
    job_snapshot = _resolve_job_snapshot(manager, job_id)
    cycle_id = _resolve_cycle_id(job_snapshot)
    if not cycle_id:
        raise HTTPException(status_code=409, detail="job 尚未关联持久化 cycle_id")
    return _resolve_learning_feedback_library(repository, cycle_id)


@router.get("/sessions/{cycle_id}/learning-feedback")
def get_research_session_learning_feedback(
    cycle_id: str,
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchLearningFeedbackLibraryResponse:
    return _resolve_learning_feedback_library(repository, cycle_id)


@router.get("/learning-feedback")
def list_research_learning_feedback(
    cycle_id: str=Query(""),
    feedback_scope: str=Query(""),
    target_phase: str=Query(""),
    cycle_trend: str=Query(""),
    limit: int=Query(50, ge=1, le=200),
    offset: int=Query(0, ge=0),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchLearningFeedbackListResponse:
    filters = {
        "cycle_id": str(cycle_id or "").strip() or None,
        "feedback_scope": str(feedback_scope or "").strip().lower() or None,
        "target_phase": str(target_phase or "").strip().lower() or None,
        "cycle_trend": str(cycle_trend or "").strip().lower() or None,
    }
    page = repository.list_learning_feedback(
        cycle_id=filters["cycle_id"],
        feedback_scope=filters["feedback_scope"],
        target_phase=filters["target_phase"],
        cycle_trend=filters["cycle_trend"],
        limit=limit,
        offset=offset,
    )
    return {
        "items": list(page.get("items") or []),
        "total": int(page.get("total") or 0),
        "limit": int(page.get("limit") or limit),
        "offset": int(page.get("offset") or offset),
        "filters": filters,
    }


@router.post("/jobs/{job_id}/catalog-review")
def update_research_job_catalog_review(
    job_id: str,
    payload: ResearchCatalogReviewRequest,
    request: Request,
    manager: ResearchJobManager=Depends(get_job_manager),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchCatalogReviewResponse:
    job_snapshot = _resolve_job_snapshot(manager, job_id)
    result = job_snapshot.get("result") if isinstance(job_snapshot.get("result"), dict) else None
    if not isinstance(result, dict):
        raise HTTPException(status_code=409, detail="job 尚未生成可写回的研究结果")

    cycle_id = _resolve_cycle_id(job_snapshot)
    if not cycle_id:
        raise HTTPException(status_code=409, detail="job 尚未关联持久化 cycle_id")

    review_payload = payload.model_dump()
    review_payload["reviewer"] = _resolve_review_reviewer(request, str(review_payload.get("reviewer") or ""))
    if not str(review_payload.get("decision_basis") or "").strip():
        review_payload["decision_basis"] = "管理 API 目录学 review 写回"

    try:
        review_artifact = repository.upsert_observe_catalog_review(cycle_id, review_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if review_artifact is None:
        if repository.get_session(cycle_id) is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
        raise HTTPException(status_code=409, detail="Observe 阶段尚未持久化，暂不可写回 review")

    refreshed_snapshot = repository.get_full_snapshot(cycle_id)
    if refreshed_snapshot is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")

    observe_philology = refreshed_snapshot.get("observe_philology") if isinstance(refreshed_snapshot, dict) else {}
    manager.sync_job_observe_philology(job_id, observe_philology if isinstance(observe_philology, dict) else {})
    return {
        "job_id": job_id,
        "cycle_id": cycle_id,
        "observe_philology": observe_philology if isinstance(observe_philology, dict) else {},
        "review_artifact": review_artifact,
    }


@router.post("/jobs/{job_id}/philology-review")
def update_research_job_philology_review(
    job_id: str,
    payload: ResearchPhilologyWorkbenchReviewRequest,
    request: Request,
    manager: ResearchJobManager=Depends(get_job_manager),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchPhilologyWorkbenchReviewResponse:
    job_snapshot = _resolve_job_snapshot(manager, job_id)
    result = job_snapshot.get("result") if isinstance(job_snapshot.get("result"), dict) else None
    if not isinstance(result, dict):
        raise HTTPException(status_code=409, detail="job 尚未生成可写回的研究结果")

    cycle_id = _resolve_cycle_id(job_snapshot)
    if not cycle_id:
        raise HTTPException(status_code=409, detail="job 尚未关联持久化 cycle_id")

    review_payload = payload.model_dump()
    review_payload["reviewer"] = _resolve_review_reviewer(request, str(review_payload.get("reviewer") or ""))
    if not str(review_payload.get("decision_basis") or "").strip():
        review_payload["decision_basis"] = "控制台文献学工作台快速审核"

    try:
        review_artifact = repository.upsert_observe_workbench_review(cycle_id, review_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if review_artifact is None:
        if repository.get_session(cycle_id) is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
        raise HTTPException(status_code=409, detail="Observe 阶段尚未持久化，暂不可写回文献学 review")

    refreshed_snapshot = repository.get_full_snapshot(cycle_id)
    if refreshed_snapshot is None:
        raise HTTPException(status_code=404, detail="研究会话不存在")

    observe_philology = refreshed_snapshot.get("observe_philology") if isinstance(refreshed_snapshot, dict) else {}
    manager.sync_job_observe_philology(job_id, observe_philology if isinstance(observe_philology, dict) else {})
    return {
        "job_id": job_id,
        "cycle_id": cycle_id,
        "observe_philology": observe_philology if isinstance(observe_philology, dict) else {},
        "review_artifact": review_artifact,
    }


@router.post("/jobs/{job_id}/batch-catalog-review")
def batch_catalog_review(
    job_id: str,
    payload: ResearchBatchCatalogReviewRequest,
    request: Request,
    manager: ResearchJobManager=Depends(get_job_manager),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchBatchCatalogReviewResponse:
    job_snapshot = _resolve_job_snapshot(manager, job_id)
    result = job_snapshot.get("result") if isinstance(job_snapshot.get("result"), dict) else None
    if not isinstance(result, dict):
        raise HTTPException(status_code=409, detail="job 尚未生成可写回的研究结果")

    cycle_id = _resolve_cycle_id(job_snapshot)
    if not cycle_id:
        raise HTTPException(status_code=409, detail="job 尚未关联持久化 cycle_id")

    reviewer = _resolve_review_reviewer(request, "")
    raw_decisions = []
    for d in payload.decisions:
        item = d.model_dump()
        item["reviewer"] = _resolve_review_reviewer(request, str(item.get("reviewer") or "")) or reviewer
        item["review_reasons"] = list(item.get("review_reasons") or payload.shared_review_reasons or [])
        if not str(item.get("decision_basis") or "").strip():
            item["decision_basis"] = str(payload.shared_decision_basis or "").strip() or "管理 API 批量目录学 review 写回"
        raw_decisions.append(item)

    batch_payload = {
        "decisions": raw_decisions,
        "selection_snapshot": payload.selection_snapshot,
        "shared_decision_basis": payload.shared_decision_basis,
        "shared_review_reasons": payload.shared_review_reasons,
        "reviewer": reviewer,
    }

    try:
        review_artifact = repository.upsert_observe_catalog_review_batch(cycle_id, batch_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if review_artifact is None:
        if repository.get_session(cycle_id) is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
        raise HTTPException(status_code=409, detail="Observe 阶段尚未持久化，暂不可写回 review")

    refreshed_snapshot = repository.get_full_snapshot(cycle_id)
    observe_philology = refreshed_snapshot.get("observe_philology") if isinstance(refreshed_snapshot, dict) else {}
    manager.sync_job_observe_philology(job_id, observe_philology if isinstance(observe_philology, dict) else {})
    return {
        "job_id": job_id,
        "cycle_id": cycle_id,
        "applied_count": len(raw_decisions),
        "observe_philology": observe_philology if isinstance(observe_philology, dict) else {},
        "review_artifact": review_artifact,
    }


@router.post("/jobs/{job_id}/batch-philology-review")
def batch_philology_review(
    job_id: str,
    payload: ResearchBatchPhilologyReviewRequest,
    request: Request,
    manager: ResearchJobManager=Depends(get_job_manager),
    repository: ResearchSessionRepository=Depends(get_research_session_repository),
    _: None=Depends(require_management_api_key),
) -> ResearchBatchPhilologyReviewResponse:
    job_snapshot = _resolve_job_snapshot(manager, job_id)
    result = job_snapshot.get("result") if isinstance(job_snapshot.get("result"), dict) else None
    if not isinstance(result, dict):
        raise HTTPException(status_code=409, detail="job 尚未生成可写回的研究结果")

    cycle_id = _resolve_cycle_id(job_snapshot)
    if not cycle_id:
        raise HTTPException(status_code=409, detail="job 尚未关联持久化 cycle_id")

    reviewer = _resolve_review_reviewer(request, "")
    raw_decisions = []
    for d in payload.decisions:
        item = d.model_dump()
        item["reviewer"] = _resolve_review_reviewer(request, str(item.get("reviewer") or "")) or reviewer
        item["review_reasons"] = list(item.get("review_reasons") or payload.shared_review_reasons or [])
        if not str(item.get("decision_basis") or "").strip():
            item["decision_basis"] = str(payload.shared_decision_basis or "").strip() or "控制台批量文献学工作台审核"
        raw_decisions.append(item)

    batch_payload = {
        "decisions": raw_decisions,
        "selection_snapshot": payload.selection_snapshot,
        "shared_decision_basis": payload.shared_decision_basis,
        "shared_review_reasons": payload.shared_review_reasons,
        "reviewer": reviewer,
    }

    try:
        review_artifact = repository.upsert_observe_workbench_review_batch(cycle_id, batch_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if review_artifact is None:
        if repository.get_session(cycle_id) is None:
            raise HTTPException(status_code=404, detail="研究会话不存在")
        raise HTTPException(status_code=409, detail="Observe 阶段尚未持久化，暂不可写回文献学 review")

    refreshed_snapshot = repository.get_full_snapshot(cycle_id)
    observe_philology = refreshed_snapshot.get("observe_philology") if isinstance(refreshed_snapshot, dict) else {}
    manager.sync_job_observe_philology(job_id, observe_philology if isinstance(observe_philology, dict) else {})
    return {
        "job_id": job_id,
        "cycle_id": cycle_id,
        "applied_count": len(raw_decisions),
        "observe_philology": observe_philology if isinstance(observe_philology, dict) else {},
        "review_artifact": review_artifact,
    }


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
