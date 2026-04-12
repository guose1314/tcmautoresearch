"""FastAPI Web Console + Architecture 3.0 REST API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.app import _probe_response, configure_api_services, include_api_routers
from src.api.dependencies import (
    extract_presented_auth_credential,
    get_console_auth_service_from_state,
    verify_management_api_key,
)
from src.infrastructure.config_loader import AppSettings
from src.infrastructure.monitoring import MonitoringService
from src.infrastructure.runtime_config_assembler import build_runtime_assembly
from web_console.job_manager import ResearchJobManager

STATIC_DIR = Path(__file__).with_name("static")
INDEX_FILE = STATIC_DIR / "index.html"
_WEB_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "web" / "templates"
_WEB_STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "web" / "static"


def create_app(
    job_manager: Optional[ResearchJobManager] = None,
    settings: Optional[AppSettings] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> FastAPI:
    runtime_assembly = build_runtime_assembly(
        settings=settings,
        config_path=config_path,
        environment=environment,
    )
    resolved_settings = runtime_assembly.settings
    app = FastAPI(title=resolved_settings.web_console_title, version=resolved_settings.web_console_version)
    manager = configure_api_services(
        app,
        job_manager=job_manager,
        settings=resolved_settings,
        runtime_assembly=runtime_assembly,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.web_console_cors_origins,
        allow_credentials=True,
        allow_methods=resolved_settings.web_console_cors_methods,
        allow_headers=resolved_settings.web_console_cors_headers,
    )

    # ---- 主数据库初始化 ----
    from src.infrastructure.persistence import DatabaseManager
    db_manager = DatabaseManager(
        connection_string=resolved_settings.database_url,
        echo=resolved_settings.database_config.get("echo", False),
    )
    db_manager.init_db()
    # 预置关系类型
    with db_manager.session_scope() as _s:
        DatabaseManager.create_default_relationships(_s)
    app.state.db_manager = db_manager
    monitoring_service: MonitoringService = app.state.monitoring_service
    monitoring_service.bind_db_manager(db_manager)

    # 先注册 Architecture API 路由，避免被后续 Web 路由的动态路径抢占
    include_api_routers(app, base_prefix="/api")
    include_api_routers(app, base_prefix="/api/v1")

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
        if hasattr(app.state, "db_manager") and app.state.db_manager:
            app.state.db_manager.close()
        manager.close()

    # ---- 控制台 SPA ----
    @app.get("/console", response_class=FileResponse)
    def console_page() -> FileResponse:
        return FileResponse(INDEX_FILE)

    # ---- 统一 JWT 认证路由 (共享 src/web/routes/auth) ----
    from src.web.routes.auth import router as auth_router

    app.include_router(auth_router)

    # ---- 仪表盘 & 业务页面路由 (HTMX 端点) ----
    from src.web.routes.analysis import router as analysis_router
    from src.web.routes.assistant import router as assistant_router
    from src.web.routes.dashboard import router as dashboard_router
    from src.web.routes.research import router as research_router

    app.include_router(dashboard_router)
    app.include_router(analysis_router)
    app.include_router(assistant_router)
    app.include_router(research_router)

    # ---- Jinja2 模板支持 (统一登录页) ----
    if _WEB_TEMPLATES_DIR.is_dir():
        app.state.templates = Jinja2Templates(directory=str(_WEB_TEMPLATES_DIR))

    # ---- 静态资源 (本地 JS/CSS，避免依赖外部 CDN) ----
    if _WEB_STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_WEB_STATIC_DIR)), name="web_static")

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

    return app


app = create_app()