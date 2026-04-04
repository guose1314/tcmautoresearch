# -*- coding: utf-8 -*-
"""认证路由 — 登录端点 + 页面路由（login / dashboard）。"""

from __future__ import annotations

import hashlib
import logging
import secrets as _secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.auth import create_access_token, get_current_user, verify_token

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# 用户加载（从 secrets.yml → security.console_auth.users）
# ---------------------------------------------------------------------------

_cached_users: Optional[Dict[str, Dict[str, Any]]] = None


def _load_users() -> Dict[str, Dict[str, Any]]:
    """加载用户列表，返回 {username_lower: {username, password, display_name}}。"""
    global _cached_users
    if _cached_users is not None:
        return _cached_users

    users: Dict[str, Dict[str, Any]] = {}

    # 1. 从 secrets.yml 加载
    for path in (Path("secrets.yml"), Path("secrets.yaml")):
        if path.exists():
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                user_list = (
                    raw.get("security", {})
                    .get("console_auth", {})
                    .get("users", [])
                )
                for entry in user_list:
                    if isinstance(entry, dict) and entry.get("username"):
                        uname = str(entry["username"]).strip().lower()
                        users[uname] = {
                            "username": uname,
                            "password": str(entry.get("password", "")),
                            "password_sha256": str(entry.get("password_sha256", "")),
                            "display_name": str(
                                entry.get("display_name", uname)
                            ),
                        }
            except Exception as exc:
                logger.warning("加载 %s 用户配置失败: %s", path, exc)

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
    global _cached_users
    _cached_users = None


# ---------------------------------------------------------------------------
# POST /api/auth/login — 登录端点
# ---------------------------------------------------------------------------


@router.post("/api/auth/login", tags=["auth"])
async def login(
    username: str = Form(...),
    password: str = Form(...),
) -> Dict[str, Any]:
    """验证用户名密码，签发 JWT access token。"""
    users = _load_users()

    # 无用户配置时提示
    if not users:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="系统尚未配置用户，请在 secrets.yml 的 security.console_auth.users 中添加用户",
        )

    normalized = username.strip().lower()
    user = users.get(normalized)

    if user is None or not _verify_password(user, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        user_id=user["username"],
        extra_claims={"display_name": user["display_name"]},
    )

    logger.info("用户 %s 登录成功", user["username"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "display_name": user["display_name"],
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


@router.get("/", tags=["pages"])
async def root_redirect() -> RedirectResponse:
    """根路径重定向到登录页。"""
    return RedirectResponse(url="/login", status_code=302)
