# -*- coding: utf-8 -*-
"""TCMAutoResearch Web 应用入口 — FastAPI 应用构建与中间件配置。"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.infrastructure.config_loader import AppSettings
from src.infrastructure.runtime_config_assembler import build_runtime_assembly

_BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = _BASE_DIR / "static"
TEMPLATES_DIR = _BASE_DIR / "templates"

# 默认 CORS 允许列表 — 开发环境宽松，生产环境应收紧
_DEFAULT_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]


def create_app(
    *,
    title: Optional[str] = None,
    version: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    extra_config: Optional[Dict[str, Any]] = None,
    settings: Optional[AppSettings] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> FastAPI:
    """构建并返回 FastAPI 应用实例。

    Parameters
    ----------
    title : str
        应用标题。
    version : str
        应用版本号。
    cors_origins : list[str] | None
        CORS 允许来源列表，为 ``None`` 时使用默认开发列表。
    extra_config : dict | None
        额外配置，存入 ``app.state.config``。
    """
    runtime_assembly = None
    if settings is not None or config_path is not None or environment is not None:
        runtime_assembly = build_runtime_assembly(
            settings=settings,
            config_path=config_path,
            environment=environment,
            entrypoint="web",
        )
    resolved_settings = runtime_assembly.settings if runtime_assembly is not None else None
    resolved_title = title or (resolved_settings.api_title if resolved_settings is not None else "TCMAutoResearch")
    resolved_version = version or (resolved_settings.api_version if resolved_settings is not None else "2.0.0")
    resolved_extra_config = dict(runtime_assembly.runtime_config) if runtime_assembly is not None else {}
    if extra_config:
        resolved_extra_config.update(extra_config)

    app = FastAPI(title=resolved_title, version=resolved_version)

    # ---- CORS 中间件 ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or (resolved_settings.web_console_cors_origins if resolved_settings is not None else _DEFAULT_CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=resolved_extra_config.get("cors_methods", ["*"]),
        allow_headers=resolved_extra_config.get("cors_headers", ["*"]),
    )

    # ---- 静态文件 ----
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---- Jinja2 模板 ----
    if TEMPLATES_DIR.is_dir():
        app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # ---- 额外配置 ----
    app.state.config = resolved_extra_config
    if resolved_settings is not None:
        app.state.settings = resolved_settings
    if runtime_assembly is not None:
        app.state.runtime_assembly = runtime_assembly

    # ---- 数据库初始化 ----
    try:
        from src.infrastructure.persistence import DatabaseManager

        _db_cfg = resolved_extra_config.get("database", {}) if resolved_extra_config else {}
        _db_type = str(_db_cfg.get("type", "sqlite")).strip().lower()
        _db_path = str(
            _db_cfg.get("path")
            or os.path.join("data", "tcmautoresearch.db")
        ).strip()
        if _db_type == "sqlite":
            _conn_str = f"sqlite:///{os.path.abspath(_db_path)}"
        elif _db_type in ("postgresql", "postgres", "pg"):
            _explicit = str(
                _db_cfg.get("connection_string")
                or _db_cfg.get("database_url")
                or _db_cfg.get("url")
                or ""
            ).strip()
            if _explicit:
                _conn_str = _explicit
            else:
                _pg_host = str(_db_cfg.get("host", "localhost")).strip()
                _pg_port = int(_db_cfg.get("port", 5432))
                _pg_name = str(_db_cfg.get("name", "tcmautoresearch")).strip()
                _pg_user = str(_db_cfg.get("user", "postgres")).strip()
                _pg_pass_env = str(_db_cfg.get("password_env", "TCM_DB_PASSWORD")).strip()
                _pg_pass = os.environ.get(_pg_pass_env, "")
                from urllib.parse import quote_plus
                _conn_str = (
                    f"postgresql+psycopg2://{quote_plus(_pg_user)}:"
                    f"{quote_plus(_pg_pass)}@{_pg_host}:{_pg_port}/{_pg_name}"
                )
        else:
            _conn_str = str(
                _db_cfg.get("connection_string")
                or _db_cfg.get("database_url")
                or _db_cfg.get("url")
                or (resolved_settings.database_url if resolved_settings is not None else "")
            ).strip()

        if _conn_str:
            db_manager = DatabaseManager(
                connection_string=_conn_str,
                echo=bool(_db_cfg.get("echo", False)),
            )
            db_manager.init_db()
            with db_manager.session_scope() as _sess:
                DatabaseManager.create_default_relationships(_sess)
            app.state.db_manager = db_manager
            logging.getLogger(__name__).info("数据库已连接: %s", _conn_str)
    except Exception as exc:
        logging.getLogger(__name__).warning("数据库初始化失败，ORM 查询将不可用: %s", exc)

    # ---- 认证 & 页面路由 ----
    from src.web.routes.auth import router as auth_router

    app.include_router(auth_router)

    # ---- 业务路由 ----
    from src.web.routes.analysis import router as analysis_router
    from src.web.routes.assistant import router as assistant_router
    from src.web.routes.dashboard import router as dashboard_router
    from src.web.routes.research import router as research_router

    app.include_router(research_router)
    app.include_router(analysis_router)
    app.include_router(assistant_router)
    app.include_router(dashboard_router)

    # ---- 健康检查 ----
    @app.get("/health", tags=["system"])
    async def health_check() -> Dict[str, Any]:
        payload: Dict[str, Any] = {"status": "ok", "version": resolved_version}
        if resolved_settings is not None:
            payload["environment"] = resolved_settings.environment
        # 数据库连通性探测
        db_mgr = getattr(getattr(app, "state", None), "db_manager", None)
        if db_mgr is None:
            payload["status"] = "degraded"
            payload["db"] = "unavailable"
        return payload

    # ---- 关闭时清理数据库连接 ----
    @app.on_event("shutdown")
    def shutdown_db() -> None:
        db_mgr = getattr(getattr(app, "state", None), "db_manager", None)
        if db_mgr is not None:
            db_mgr.close()

    return app
