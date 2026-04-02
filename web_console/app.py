"""FastAPI Web Console + Architecture 3.0 REST API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.api.app import _probe_response, configure_api_services, include_api_routers
from src.api.dependencies import (
    extract_presented_auth_credential,
    get_console_auth_service_from_state,
    verify_management_api_key,
)
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

    @app.get("/api/console/auth/status")
    @app.get("/api/v1/console/auth/status")
    def console_auth_status() -> dict[str, Any]:
        console_auth_service = get_console_auth_service_from_state(app.state, resolved_settings)
        return {
            "app_title": resolved_settings.web_console_title,
            "environment": resolved_settings.environment,
            **console_auth_service.status_payload(),
        }

    @app.post("/api/console/auth/login")
    @app.post("/api/v1/console/auth/login")
    def console_auth_login(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        console_auth_service = get_console_auth_service_from_state(app.state, resolved_settings)
        username = str(payload.get("username", "") or "").strip()
        password = str(payload.get("password", "") or "")
        presented_key = str(payload.get("api_key", "") or "").strip()
        session_token = str(payload.get("session_token", "") or "").strip()

        if session_token:
            session = console_auth_service.resolve_session(session_token)
            if session is not None:
                return {
                    "authenticated": True,
                    "auth_required": console_auth_service.auth_required,
                    "auth_mode": console_auth_service.auth_mode,
                    "principal": session.principal,
                    "session_token": session.token,
                    "session_expires_at": session.expires_at,
                    "auth_source": session.auth_source,
                    "token_supplied": True,
                }

        if console_auth_service.supports_password_login and password:
            user = console_auth_service.authenticate_password(username, password)
            if user is not None:
                session = console_auth_service.create_session(
                    username=user.username,
                    principal=user.principal,
                    auth_source="password",
                )
                return {
                    "authenticated": True,
                    "auth_required": console_auth_service.auth_required,
                    "auth_mode": console_auth_service.auth_mode,
                    "principal": session.principal,
                    "session_token": session.token,
                    "session_expires_at": session.expires_at,
                    "auth_source": session.auth_source,
                    "token_supplied": True,
                }

        if presented_key:
            verify_management_api_key(presented_key, resolved_settings)
            principal = username or "控制台管理员"
            session = console_auth_service.create_session(
                username=username or "management_api_key",
                principal=principal,
                auth_source="management_api_key",
            )
            return {
                "authenticated": True,
                "auth_required": console_auth_service.auth_required,
                "auth_mode": console_auth_service.auth_mode,
                "principal": session.principal,
                "session_token": session.token,
                "session_expires_at": session.expires_at,
                "auth_source": session.auth_source,
                "token_supplied": True,
            }

        if not console_auth_service.auth_required:
            principal = username or "访客"
            return {
                "authenticated": True,
                "auth_required": False,
                "auth_mode": console_auth_service.auth_mode,
                "principal": principal,
                "session_token": "",
                "session_expires_at": "",
                "auth_source": "guest",
                "token_supplied": False,
            }

        if console_auth_service.supports_password_login:
            raise HTTPException(status_code=401, detail="用户名或密码无效")

        raise HTTPException(status_code=401, detail="缺少或无效的管理 API Key")

    @app.post("/api/console/auth/logout")
    @app.post("/api/v1/console/auth/logout")
    def console_auth_logout(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        console_auth_service = get_console_auth_service_from_state(app.state, resolved_settings)
        session_token = str(payload.get("session_token", "") or "").strip() or extract_presented_auth_credential(
            request.headers,
            request.query_params,
        )
        return {
            "revoked": console_auth_service.revoke_session(session_token),
        }

    include_api_routers(app, base_prefix="/api")
    include_api_routers(app, base_prefix="/api/v1")

    return app


app = create_app()