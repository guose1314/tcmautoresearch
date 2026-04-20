"""System and architecture routes for the Architecture 3.0 REST API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse

from src.api.dependencies import (
    get_architecture,
    get_job_manager,
    get_monitoring_service,
    get_settings,
    require_management_api_key,
)
from src.api.schemas import (
    ArchitectureSummaryResponse,
    HealthProbeResponse,
    ModuleDependencyResponse,
    ModuleDependentResponse,
    ModuleDetail,
    ModuleListResponse,
    MonitoringMetricsResponse,
    PersistedJobListResponse,
    PersistedJobPayloadResponse,
    PersistenceSummaryResponse,
    SystemExportRequest,
    SystemExportResponse,
    SystemHealthResponse,
    SystemStatusResponse,
)
from src.core.architecture import SystemArchitecture
from src.infrastructure.config_loader import AppSettings
from src.infrastructure.monitoring import MonitoringService
from web_console.job_manager import ResearchJobManager

router = APIRouter(tags=["system"])


def _build_export_output_path(export_dir: Path, output_name: str | None) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_name = str(output_name or "").strip()
    if not safe_name:
        safe_name = f"system-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    if not safe_name.endswith(".json"):
        safe_name = f"{safe_name}.json"
    return export_dir / Path(safe_name).name


@router.get("/health")
def health(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> SystemHealthResponse:
    return monitoring_service.get_health_report()


@router.get("/liveness")
def liveness(
    response: Response,
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> HealthProbeResponse:
    payload = monitoring_service.get_liveness_report()
    if payload.get("status") == "error":
        response.status_code = 503
    return payload


@router.get("/readiness")
def readiness(
    response: Response,
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> HealthProbeResponse:
    payload = monitoring_service.get_readiness_report()
    if payload.get("status") == "error":
        response.status_code = 503
    return payload


@router.get("/storage/health")
def storage_health(
    response: Response,
    settings: AppSettings = Depends(get_settings),
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    _: None = Depends(require_management_api_key),
) -> Dict[str, Any]:
    """F-2-4: 返回 StorageObservability + DegradationGovernor + BackfillLedger 合并报告。

    优先使用 MonitoringService 绑定的活跃 factory（含真实运行时计数器），
    若无绑定则回退到创建临时 factory（仅配置/模式信息）。
    """
    factory = monitoring_service.bound_storage_factory
    is_transient = factory is None
    try:
        if is_transient:
            from src.storage import StorageBackendFactory
            factory = StorageBackendFactory(settings.materialize_runtime_config())
            factory.initialize()
        obs_report = factory.observability.get_health_report()
        gov_report = factory.degradation_governor.to_governance_report()
        backfill_summary = factory.backfill_ledger.get_summary()
    except Exception as exc:
        response.status_code = 503
        return {"error": str(exc), "storage_health": None, "governance": None, "backfill": None}
    finally:
        if is_transient and factory is not None:
            try:
                factory.close()
            except Exception:
                pass
    return {
        "storage_health": obs_report,
        "governance": gov_report,
        "backfill": backfill_summary,
    }


@router.get("/status")
def get_system_status(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    _: None = Depends(require_management_api_key),
) -> SystemStatusResponse:
    return monitoring_service.get_system_status_snapshot()


@router.get("/architecture")
def get_architecture_summary(
    architecture: SystemArchitecture = Depends(get_architecture),
    _: None = Depends(require_management_api_key),
) -> ArchitectureSummaryResponse:
    return architecture.get_architecture_summary()


@router.get("/modules")
def list_modules(
    architecture: SystemArchitecture = Depends(get_architecture),
    _: None = Depends(require_management_api_key),
) -> ModuleListResponse:
    modules = architecture.get_module_list()
    return {
        "modules": modules,
        "count": len(modules),
    }


@router.get("/modules/{module_id}")
def get_module(
    module_id: str,
    architecture: SystemArchitecture = Depends(get_architecture),
    _: None = Depends(require_management_api_key),
) -> ModuleDetail:
    module = architecture.get_module_by_id(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="module 不存在")
    return module


@router.get("/modules/{module_id}/dependencies")
def get_module_dependencies(
    module_id: str,
    architecture: SystemArchitecture = Depends(get_architecture),
    _: None = Depends(require_management_api_key),
) -> ModuleDependencyResponse:
    module = architecture.get_module_by_id(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="module 不存在")
    dependencies = architecture.get_module_dependencies(module_id)
    return {
        "module_id": module_id,
        "dependencies": dependencies,
        "count": len(dependencies),
    }


@router.get("/modules/{module_id}/dependents")
def get_module_dependents(
    module_id: str,
    architecture: SystemArchitecture = Depends(get_architecture),
    _: None = Depends(require_management_api_key),
) -> ModuleDependentResponse:
    module = architecture.get_module_by_id(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail="module 不存在")
    dependents = architecture.get_module_dependents(module_id)
    return {
        "module_id": module_id,
        "dependents": dependents,
        "count": len(dependents),
    }


@router.get("/metrics")
def get_monitoring_metrics(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    _: None = Depends(require_management_api_key),
) -> MonitoringMetricsResponse:
    return monitoring_service.collect_metrics()


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
def get_monitoring_metrics_prometheus(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
    _: None = Depends(require_management_api_key),
) -> PlainTextResponse:
    return PlainTextResponse(
        monitoring_service.export_prometheus_metrics(),
        media_type=monitoring_service.prometheus_content_type,
    )


@router.get("/export")
def get_system_export_payload(
    architecture: SystemArchitecture = Depends(get_architecture),
    _: None = Depends(require_management_api_key),
) -> Dict[str, Any]:
    return architecture.get_system_export_payload()


@router.post("/export")
def export_system_snapshot(
    payload: SystemExportRequest = Body(default_factory=SystemExportRequest),
    architecture: SystemArchitecture = Depends(get_architecture),
    settings: AppSettings = Depends(get_settings),
    _: None = Depends(require_management_api_key),
) -> SystemExportResponse:
    export_dir = settings.export_directory
    output_path = _build_export_output_path(export_dir, payload.output_name)
    exported = architecture.export_system_info(str(output_path))
    if not exported:
        raise HTTPException(status_code=500, detail="系统导出失败")

    response: Dict[str, Any] = {
        "exported": True,
        "output_path": str(output_path),
        "file_size_bytes": output_path.stat().st_size if output_path.exists() else 0,
    }
    if payload.include_payload:
        response["payload"] = architecture.get_system_export_payload()
    return response


@router.get("/persistence/summary")
def get_persistence_summary(
    manager: ResearchJobManager = Depends(get_job_manager),
    _: None = Depends(require_management_api_key),
) -> PersistenceSummaryResponse:
    return manager.get_storage_summary()


@router.get("/persistence/jobs")
def list_persisted_jobs(
    limit: int = Query(10, ge=1, le=100),
    manager: ResearchJobManager = Depends(get_job_manager),
    _: None = Depends(require_management_api_key),
) -> PersistedJobListResponse:
    jobs = manager.list_persisted_jobs(limit=limit)
    return {
        "jobs": jobs,
        "count": len(jobs),
        "limit": limit,
    }


@router.get("/persistence/jobs/{job_id}")
def get_persisted_job(
    job_id: str,
    manager: ResearchJobManager = Depends(get_job_manager),
    _: None = Depends(require_management_api_key),
) -> PersistedJobPayloadResponse:
    payload = manager.get_persisted_job(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="持久化任务不存在")
    return payload