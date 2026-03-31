"""FastAPI Web Console + Architecture 3.0 REST API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.api.app import _probe_response, configure_api_services, include_api_routers
from src.infrastructure.config_loader import AppSettings, load_settings
from src.infrastructure.monitoring import MonitoringService
from web_console.job_manager import ResearchJobManager

STATIC_DIR = Path(__file__).with_name("static")
INDEX_FILE = STATIC_DIR / "index.html"


def create_app(
    job_manager: Optional[ResearchJobManager] = None,
    settings: Optional[AppSettings] = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    app = FastAPI(title=resolved_settings.web_console_title, version=resolved_settings.web_console_version)
    manager = configure_api_services(app, job_manager=job_manager, settings=resolved_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.web_console_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": resolved_settings.environment}

    @app.get("/liveness")
    def liveness(response: Response) -> dict[str, Any]:
        monitoring_service: MonitoringService = app.state.monitoring_service
        return _probe_response(response, monitoring_service.get_liveness_report())

    @app.get("/readiness")
    def readiness(response: Response) -> dict[str, Any]:
        monitoring_service: MonitoringService = app.state.monitoring_service
        return _probe_response(response, monitoring_service.get_readiness_report())

    @app.on_event("shutdown")
    def shutdown_job_manager() -> None:
        manager.close()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(INDEX_FILE)

    include_api_routers(app, base_prefix="/api")
    include_api_routers(app, base_prefix="/api/v1")

    return app


app = create_app()