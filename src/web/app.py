# -*- coding: utf-8 -*-
"""TCMAutoResearch Web 应用入口 — FastAPI 应用构建与中间件配置。"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
    title: str = "TCMAutoResearch",
    version: str = "2.0.0",
    cors_origins: Optional[List[str]] = None,
    extra_config: Optional[Dict[str, Any]] = None,
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
    app = FastAPI(title=title, version=version)

    # ---- CORS 中间件 ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or _DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=extra_config.get("cors_methods", ["*"]) if extra_config else ["*"],
        allow_headers=extra_config.get("cors_headers", ["*"]) if extra_config else ["*"],
    )

    # ---- 静态文件 ----
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ---- Jinja2 模板 ----
    if TEMPLATES_DIR.is_dir():
        app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # ---- 额外配置 ----
    app.state.config = extra_config or {}

    # ---- 数据库初始化 ----
    try:
        from src.infrastructure.persistence import DatabaseManager

        _db_cfg = extra_config.get("database", {}) if extra_config else {}
        _db_type = str(_db_cfg.get("type", "sqlite")).strip().lower()
        _db_path = str(
            _db_cfg.get("path")
            or os.path.join("data", "tcmautoresearch.db")
        ).strip()
        if _db_type == "sqlite":
            _conn_str = f"sqlite:///{os.path.abspath(_db_path)}"
        else:
            _conn_str = str(_db_cfg.get("connection_string", "")).strip()

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
    async def health_check() -> Dict[str, str]:
        return {"status": "ok", "version": version}

    # ---- 关闭时清理数据库连接 ----
    @app.on_event("shutdown")
    def shutdown_db() -> None:
        db_mgr = getattr(getattr(app, "state", None), "db_manager", None)
        if db_mgr is not None:
            db_mgr.close()

    return app
