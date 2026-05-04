from __future__ import annotations

from typing import Any, Dict, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from src.infrastructure.persistence import DatabaseManager
from src.monitoring.production_quality import ProductionQualityMonitor
from src.web.auth import get_current_user

router = APIRouter(prefix="/api/production-monitoring", tags=["production-monitoring"])


@router.get("/quality")
async def get_production_quality_dashboard(
    request: Request,
    recent_failure_limit: int = Query(12, ge=1, le=100),
    _current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    monitor = ProductionQualityMonitor(_get_db(request))
    return await run_in_threadpool(
        monitor.collect_dashboard_payload,
        recent_failure_limit=recent_failure_limit,
    )


@router.get("/dlq")
async def list_production_dlq(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    _current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    monitor = ProductionQualityMonitor(_get_db(request))
    items = await run_in_threadpool(monitor.list_dlq, limit=limit)
    return {"items": items, "count": len(items)}


@router.post("/dlq/{event_id:path}/replay")
async def replay_production_dlq_event(
    request: Request,
    event_id: str,
    _current_user: Mapping[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    monitor = ProductionQualityMonitor(_get_db(request))
    try:
        return await run_in_threadpool(monitor.replay_dlq_event, event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _get_db(request: Request) -> DatabaseManager:
    db = getattr(request.app.state, "db_manager", None)
    if db is None:
        raise HTTPException(status_code=503, detail="database unavailable")
    return db
