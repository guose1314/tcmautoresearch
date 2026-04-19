"""Architecture 3.0 FastAPI REST API application."""

from __future__ import annotations

import logging
from pathlib import Path
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
    extraction_router,
    research_router,
    system_router,
)
from src.core.architecture import SystemArchitecture
from src.infrastructure.config_loader import AppSettings
from src.infrastructure.monitoring import MonitoringService
from src.infrastructure.runtime_config_assembler import (
    RuntimeAssembly,
    build_runtime_assembly,
)
from web_console.job_manager import ResearchJobManager

logger = logging.getLogger(__name__)


def configure_api_services(
    app: FastAPI,
    *,
    job_manager: Optional[ResearchJobManager] = None,
    architecture: Optional[SystemArchitecture] = None,
    settings: Optional[AppSettings] = None,
    runtime_assembly: Optional[RuntimeAssembly] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> ResearchJobManager:
    resolved_runtime_assembly = runtime_assembly or build_runtime_assembly(
        settings=settings,
        config_path=config_path,
        environment=environment,
        entrypoint="web",
    )
    resolved_settings = resolved_runtime_assembly.settings
    manager = job_manager or ResearchJobManager(runtime_assembly=resolved_runtime_assembly)
    resolved_architecture = architecture or create_default_architecture(resolved_settings)
    app.state.settings = resolved_settings
    app.state.runtime_assembly = resolved_runtime_assembly
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
    app.include_router(extraction_router, prefix=f"{prefix}/extraction")


def _probe_response(response: Response, payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("status") == "error":
        response.status_code = 503
    return payload


def create_app(
    job_manager: Optional[ResearchJobManager] = None,
    architecture: Optional[SystemArchitecture] = None,
    settings: Optional[AppSettings] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> FastAPI:
    runtime_assembly = build_runtime_assembly(
        settings=settings,
        config_path=config_path,
        environment=environment,
        entrypoint="web",
    )
    resolved_settings = runtime_assembly.settings
    app = FastAPI(title=resolved_settings.api_title, version=resolved_settings.api_version)
    manager = configure_api_services(
        app,
        job_manager=job_manager,
        architecture=architecture,
        settings=resolved_settings,
        runtime_assembly=runtime_assembly,
    )

    try:
        from src.infrastructure.persistence import DatabaseManager

        db_manager = DatabaseManager(
            connection_string=resolved_settings.database_url,
            echo=resolved_settings.database_config.get("echo", False),
        )
        db_manager.init_db()
        with db_manager.session_scope() as _session:
            DatabaseManager.create_default_relationships(_session)
        app.state.db_manager = db_manager
        monitoring_service: MonitoringService = app.state.monitoring_service
        monitoring_service.bind_db_manager(db_manager)
    except Exception as exc:
        logger.warning("独立 API 数据库初始化失败，研究会话写回能力不可用: %s", exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=resolved_settings.api_cors_methods,
        allow_headers=resolved_settings.api_cors_headers,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        payload: dict[str, Any] = {"status": "ok", "environment": resolved_settings.environment}
        try:
            monitoring_service: MonitoringService = app.state.monitoring_service
            liveness = monitoring_service.get_liveness_report()
            if liveness.get("status") == "error":
                payload["status"] = "degraded"
        except Exception:
            pass
        return payload

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
        db_mgr = getattr(app.state, "db_manager", None)
        if db_mgr is not None:
            db_mgr.close()
        manager.close()

    include_api_routers(app, base_prefix="/api/v1")
    return app