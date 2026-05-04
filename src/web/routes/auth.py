# -*- coding: utf-8 -*-
"""认证路由 — 统一登录端点 + 页面路由（login / dashboard）。"""

from __future__ import annotations

import hashlib
import logging
import secrets as _secrets
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from src.web.auth import create_access_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONSOLE_INDEX_FILE = _REPO_ROOT / "web_console" / "static" / "index.html"

# ---------------------------------------------------------------------------
# 用户加载（从 secrets.yml → security.console_auth.users）
# ---------------------------------------------------------------------------

_cached_users: Optional[Dict[str, Dict[str, Any]]] = None
_cached_security: Optional[Dict[str, Any]] = None


def _load_security_config() -> Dict[str, Any]:
    """通过 ConfigCenter 加载 security 密钥配置（缓存结果）。"""
    global _cached_security
    if _cached_security is not None:
        return _cached_security

    try:
        from src.infrastructure.config_loader import load_settings

        settings = load_settings()
        _cached_security = settings.get_secret_section("security", default={})
    except Exception as exc:
        logger.warning("通过 ConfigCenter 加载安全配置失败: %s", exc)
        _cached_security = {}

    return _cached_security


def _get_management_api_key_from_sources() -> str:
    import os

    env_candidates = (
        "MANAGEMENT_API_KEY",
        "WEB_CONSOLE_MANAGEMENT_API_KEY",
        "TCM_MANAGEMENT_API_KEY",
        "TCM__SECRETS__SECURITY__MANAGEMENT_API_KEY",
    )
    for name in env_candidates:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value

    security = _load_security_config()
    candidates = (
        security.get("management_api_key"),
        security.get("access_control", {}).get("management_api_key")
        if isinstance(security.get("access_control"), dict)
        else "",
    )
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _load_users() -> Dict[str, Dict[str, Any]]:
    """加载用户列表，返回 {username_lower: {username, password, display_name}}。"""
    global _cached_users
    if _cached_users is not None:
        return _cached_users

    users: Dict[str, Dict[str, Any]] = {}

    # 1. 从安全配置加载（优先 project root，其次当前工作目录）
    user_list = _load_security_config().get("console_auth", {}).get("users", [])
    for entry in user_list:
        if isinstance(entry, dict) and entry.get("username"):
            uname = str(entry["username"]).strip().lower()
            users[uname] = {
                "username": uname,
                "password": str(entry.get("password", "")),
                "password_sha256": str(entry.get("password_sha256", "")),
                "display_name": str(entry.get("display_name", uname)),
            }

    # 2. 环境变量兜底: WEB_ADMIN_USER / WEB_ADMIN_PASSWORD
    import os

    env_user = os.environ.get("WEB_ADMIN_USER", "").strip()
    env_pass = os.environ.get("WEB_ADMIN_PASSWORD", "").strip()
    if env_user and env_pass:
        uname = env_user.lower()
        users[uname] = {
            "username": uname,
            "password": env_pass,
            "password_sha256": "",
            "display_name": env_user,
        }

    _cached_users = users
    logger.info("已加载 %d 个 Web 用户", len(users))
    return users


def _verify_password(user: Dict[str, Any], password: str) -> bool:
    """验证密码（支持 SHA256 哈希和明文，均使用常时间比较）。"""
    if user.get("password_sha256"):
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return _secrets.compare_digest(digest, user["password_sha256"])
    if user.get("password"):
        return _secrets.compare_digest(password, user["password"])
    return False


def reset_user_cache() -> None:
    """重置用户缓存（用于测试）。"""
    global _cached_users, _cached_security
    _cached_users = None
    _cached_security = None


def _has_management_api_key() -> bool:
    """检查是否配置了管理 API Key。"""
    if _get_management_api_key_from_sources():
        return True

    try:
        from src.infrastructure.config_loader import load_settings

        settings = load_settings()
        from src.api.dependencies import is_management_auth_enabled

        return is_management_auth_enabled(settings)
    except Exception:
        return False


def _verify_api_key(presented_key: str) -> bool:
    """验证管理 API Key（常时间比较）。"""
    expected = _get_management_api_key_from_sources()
    if expected:
        return _secrets.compare_digest(presented_key, expected)

    try:
        from src.infrastructure.config_loader import load_settings

        settings = load_settings()
        from src.api.dependencies import _get_management_api_key

        expected = _get_management_api_key(settings)
        if not expected:
            return False
        return _secrets.compare_digest(presented_key, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# GET /api/auth/status — 认证模式查询（前端用于自适应 UI）
# ---------------------------------------------------------------------------


@router.get("/api/auth/status", tags=["auth"])
async def auth_status(request: Request) -> Dict[str, Any]:
    """返回当前认证配置，前端据此决定显示哪些登录字段。"""
    users = _load_users()
    supports_api_key = _has_management_api_key()

    supports_password = bool(users)
    auth_required = supports_password or supports_api_key

    if supports_password:
        auth_mode = "password"
    elif supports_api_key:
        auth_mode = "management_api_key"
    else:
        auth_mode = "open"

    return {
        "auth_required": auth_required,
        "auth_mode": auth_mode,
        "supports_password_login": supports_password,
        "supports_api_key_login": supports_api_key,
        "guest_allowed": not auth_required,
    }


# ---------------------------------------------------------------------------
# POST /api/auth/login — 登录端点（同时支持 form 和 JSON）
# ---------------------------------------------------------------------------


@router.post("/api/auth/login", tags=["auth"])
async def login(
    request: Request,
) -> Dict[str, Any]:
    """统一登录端点：同时支持 form-urlencoded 和 JSON body。

    - form: ``username`` + ``password``
    - JSON: ``{"username": "...", "password": "..."}`` 或 ``{"api_key": "..."}``
    """
    req_username: Optional[str] = None
    req_password: Optional[str] = None
    api_key: Optional[str] = None

    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                req_username = str(body.get("username") or "").strip()
                req_password = str(body.get("password") or "")
                api_key = str(body.get("api_key") or "").strip() or None
        except Exception:
            pass
    elif (
        "application/x-www-form-urlencoded" in content_type
        or "multipart/form-data" in content_type
    ):
        try:
            form_data = await request.form()
            req_username = str(form_data.get("username") or "").strip()
            req_password = str(form_data.get("password") or "")
            api_key = str(form_data.get("api_key") or "").strip() or None
        except Exception:
            pass
    else:
        # 兼容客户端未携带明确 content-type 的场景，先尝试 JSON，再尝试表单。
        try:
            body = await request.json()
            if isinstance(body, dict):
                req_username = str(body.get("username") or "").strip()
                req_password = str(body.get("password") or "")
                api_key = str(body.get("api_key") or "").strip() or None
        except Exception:
            try:
                form_data = await request.form()
                req_username = str(form_data.get("username") or "").strip()
                req_password = str(form_data.get("password") or "")
                api_key = str(form_data.get("api_key") or "").strip() or None
            except Exception:
                pass

    # ---------- API Key 登录 ----------
    if api_key:
        if not _verify_api_key(api_key):
            raise HTTPException(
                status_code=401,
                detail="管理 API Key 无效",
                headers={"WWW-Authenticate": "Bearer"},
            )
        display_name = (req_username or "").strip() or "管理员"
        token = create_access_token(
            user_id="api_key_user",
            extra_claims={"display_name": display_name, "auth_source": "api_key"},
        )
        logger.info("API Key 登录成功 (display_name=%s)", display_name)
        return {
            "access_token": token,
            "token_type": "bearer",
            "display_name": display_name,
            "auth_source": "api_key",
        }

    # ---------- 用户名 + 密码登录 ----------
    req_username = (req_username or "").strip()
    req_password = req_password or ""

    if not req_username or not req_password:
        raise HTTPException(
            status_code=422,
            detail="请提供用户名和密码",
        )

    users = _load_users()
    if not users:
        raise HTTPException(
            status_code=503,
            detail="系统尚未配置用户，请在 secrets.yml 的 security.console_auth.users 中添加用户",
        )

    normalized = req_username.lower()
    user = users.get(normalized)

    if user is None or not _verify_password(user, req_password):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        user_id=user["username"],
        extra_claims={"display_name": user["display_name"], "auth_source": "password"},
    )

    logger.info("用户 %s 登录成功", user["username"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "display_name": user["display_name"],
        "auth_source": "password",
    }


# ---------------------------------------------------------------------------
# GET /api/auth/me — 当前用户信息
# ---------------------------------------------------------------------------


@router.get("/api/auth/me", tags=["auth"])
async def me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """返回当前登录用户基本信息。"""
    return {
        "user_id": current_user.get("sub", ""),
        "username": current_user.get("sub", ""),
        "display_name": current_user.get("display_name", "用户"),
    }


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse, tags=["pages"])
async def login_page(request: Request) -> HTMLResponse:
    """渲染登录页面。"""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html")


@router.get("/dashboard", response_class=HTMLResponse, tags=["pages"])
async def dashboard_page(request: Request) -> HTMLResponse:
    """渲染主控台页面（前端 JS 负责 JWT 校验）。"""
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/console", tags=["pages"])
async def console_page(request: Request):
    """渲染实时任务控制台，兼容登录页 ``next=console`` 跳转。"""
    if _CONSOLE_INDEX_FILE.is_file():
        return FileResponse(_CONSOLE_INDEX_FILE)

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/", tags=["pages"])
async def root_redirect() -> RedirectResponse:
    """根路径重定向到登录页。"""
    return RedirectResponse(url="/login", status_code=302)
