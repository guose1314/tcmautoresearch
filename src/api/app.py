"""Architecture 3.0 FastAPI REST API application."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import (
    create_default_architecture,
    create_default_monitoring_service,
)
from src.api.routes import (
    analysis_router,
    collection_router,
    research_router,
    system_router,
)
from src.core.architecture import SystemArchitecture
from src.infrastructure.config_loader import AppSettings, load_settings
from src.infrastructure.monitoring import MonitoringService
from web_console.job_manager import ResearchJobManager


def configure_api_services(
    app: FastAPI,
    *,
    job_manager: Optional[ResearchJobManager] = None,
    architecture: Optional[SystemArchitecture] = None,
    settings: Optional[AppSettings] = None,
) -> ResearchJobManager:
    resolved_settings = settings or load_settings()
    manager = job_manager or ResearchJobManager(
        storage_dir=resolved_settings.job_storage_dir,
        default_orchestrator_config={"pipeline_config": resolved_settings.materialize_runtime_config()},
    )
    resolved_architecture = architecture or create_default_architecture(resolved_settings)
    app.state.settings = resolved_settings
    app.state.job_manager = manager
    app.state.architecture = resolved_architecture
    app.state.monitoring_service = create_default_monitoring_service(
        resolved_settings,
        resolved_architecture,
        manager,
    )
    return manager


def include_api_routers(app: FastAPI, *, base_prefix: str) -> None:
    prefix = base_prefix.rstrip("/")
    app.include_router(system_router, prefix=f"{prefix}/system")
    app.include_router(research_router, prefix=f"{prefix}/research")
    app.include_router(collection_router, prefix=f"{prefix}/collection")
    app.include_router(analysis_router, prefix=f"{prefix}/analysis")


def _probe_response(response: Response, payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("status") == "error":
        response.status_code = 503
    return payload


def create_app(
    job_manager: Optional[ResearchJobManager] = None,
    architecture: Optional[SystemArchitecture] = None,
    settings: Optional[AppSettings] = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    app = FastAPI(title=resolved_settings.api_title, version=resolved_settings.api_version)
    manager = configure_api_services(
        app,
        job_manager=job_manager,
        architecture=architecture,
        settings=resolved_settings,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        """
        增强版健康检查（指令 I-06）。

        检查各存储后端（PostgreSQL / Neo4j / ChromaDB）的连通状态，
        并汇总 active_modules 数量，使 Kubernetes liveness 探针可精确判断服务健康状态。
        """
        storage_status: Dict[str, Any] = {}
        try:
            gateway = getattr(app.state, "storage_gateway", None)
            if gateway is None:
                from src.storage.storage_gateway import StorageGateway
                gateway = StorageGateway.from_config(
                    resolved_settings.materialize_runtime_config()
                    if hasattr(resolved_settings, "materialize_runtime_config") else {}
                )
                app.state.storage_gateway = gateway
            storage_status["postgresql"] = "ok" if getattr(gateway, "postgres_available", False) else "disabled"
            storage_status["neo4j"] = "ok" if getattr(gateway, "_neo4j_driver", None) is not None else "disabled"
            storage_status["chromadb"] = "ok" if getattr(gateway, "_rag_service", None) is not None else "disabled"
        except Exception as exc:
            storage_status["error"] = str(exc)

        arch = getattr(app.state, "architecture", None)
        active_modules = 0
        if arch is not None:
            try:
                active_modules = len(getattr(arch, "active_modules", {}) or {})
            except Exception:
                pass

        return {
            "status": "ok",
            "environment": resolved_settings.environment,
            "storage": storage_status,
            "active_modules": active_modules,
        }

    @app.get("/liveness")
    def liveness(response: Response) -> Dict[str, Any]:
        monitoring_service: MonitoringService = app.state.monitoring_service
        return _probe_response(response, monitoring_service.get_liveness_report())

    @app.get("/readiness")
    def readiness(response: Response) -> Dict[str, Any]:
        monitoring_service: MonitoringService = app.state.monitoring_service
        return _probe_response(response, monitoring_service.get_readiness_report())

    @app.on_event("shutdown")
    def shutdown_job_manager() -> None:
        manager.close()

    include_api_routers(app, base_prefix="/api/v1")
    return app


app = create_app()