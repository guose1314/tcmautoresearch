"""T6.2 — slowapi 速率限制中间件。

策略
====

* ``/api/analysis/*`` → ``60/minute``
* ``/api/research/*``  → ``60/minute``
* ``/api/catalog/*``   → ``120/minute``
* 其他 ``/api/*``       → ``300/minute``（兜底）

429 响应体走统一错误格式（与 FastAPI ``HTTPException`` 兼容）::

    {
        "detail": "rate limit exceeded: 60/minute",
        "error": "rate_limit_exceeded",
        "limit": "60/minute",
        "scope": "/api/analysis"
    }
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from limits import parse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

RATE_LIMIT_RULES: Tuple[Tuple[str, str], ...] = (
    ("/api/analysis", "60/minute"),
    ("/api/research", "60/minute"),
    ("/api/catalog", "120/minute"),
)
DEFAULT_API_LIMIT = "300/minute"

__all__ = [
    "RATE_LIMIT_RULES",
    "DEFAULT_API_LIMIT",
    "install_rate_limiter",
    "resolve_limit_for_path",
]


def resolve_limit_for_path(path: str) -> Optional[str]:
    if not path:
        return None
    for prefix, limit in RATE_LIMIT_RULES:
        if path.startswith(prefix):
            return limit
    if path.startswith("/api/"):
        return DEFAULT_API_LIMIT
    return None


def _path_scope(path: str) -> str:
    for prefix, _ in RATE_LIMIT_RULES:
        if path.startswith(prefix):
            return prefix
    return "/api"


def _key_func(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not client_ip:
        client_ip = get_remote_address(request) or "unknown"
    scope = _path_scope(request.url.path or "")
    return f"{client_ip}|{scope}"


def _build_429(limit_str: str, scope: str) -> JSONResponse:
    body = {
        "detail": f"rate limit exceeded: {limit_str}",
        "error": "rate_limit_exceeded",
        "limit": limit_str,
        "scope": scope,
    }
    response = JSONResponse(status_code=429, content=body)
    response.headers["Retry-After"] = "60"
    return response


def _exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """兜底处理：若有路由用 slowapi 装饰器抛 RateLimitExceeded，仍走统一格式。"""
    limit_obj = getattr(exc, "limit", None)
    limit_str = str(getattr(limit_obj, "limit", limit_obj) or "")
    scope = _path_scope(request.url.path or "")
    return _build_429(limit_str or "rate_limited", scope)


def install_rate_limiter(
    app: FastAPI,
    *,
    rules: Iterable[Tuple[str, str]] = RATE_LIMIT_RULES,
    default_limit: str = DEFAULT_API_LIMIT,
) -> Limiter:
    """挂载基于 slowapi 内部限流器的路径维度速率限制。"""
    limiter = Limiter(key_func=_key_func, default_limits=[])
    app.state.limiter = limiter

    @app.middleware("http")
    async def _path_rate_limit_middleware(request: Request, call_next):  # type: ignore[no-redef]
        path = request.url.path or ""
        limit_str = resolve_limit_for_path(path)
        if limit_str is None:
            return await call_next(request)
        try:
            item = parse(limit_str)
            key = _key_func(request)
            allowed = limiter.limiter.hit(item, key)
        except Exception:  # 限流器异常时降级放行，避免影响业务
            logger.exception("rate limiter hit() failed; allowing request")
            return await call_next(request)
        if not allowed:
            return _build_429(limit_str, _path_scope(path))
        return await call_next(request)

    app.add_exception_handler(RateLimitExceeded, _exception_handler)
    logger.info(
        "rate limiter installed (rules=%s, default=%s)",
        list(rules), default_limit,
    )
    return limiter
