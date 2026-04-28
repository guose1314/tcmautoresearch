"""T3.3: /api/catalog/views/{view} 三视图统一查询入口。

视图：
  - ``topic``    → Topic + 文档计数
  - ``subject``  → SubjectClass + 文档计数
  - ``dynasty``  → DynastySlice + 文档计数

slowapi 限流为 60/minute（缺少 slowapi 时降级为无限流，以便基础包不强依赖）。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.contexts.catalog import CatalogContext
from src.contexts.catalog.service import CatalogContextError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

# ---------------------------------------------------------------------------
# slowapi 软依赖：可用即限流；不可用即 no-op
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import guard
    from slowapi import Limiter  # type: ignore
    from slowapi.util import get_remote_address  # type: ignore

    _limiter = Limiter(key_func=get_remote_address)

    def _rate_limit(spec: str) -> Callable:
        return _limiter.limit(spec)

except Exception:  # noqa: BLE001
    _limiter = None

    def _rate_limit(spec: str) -> Callable:  # type: ignore[misc]
        def _decorator(fn: Callable) -> Callable:
            return fn

        return _decorator


# ---------------------------------------------------------------------------
# Driver 依赖：复用 analysis 路由内部的 _get_neo4j_driver；测试可 monkeypatch
# ---------------------------------------------------------------------------


def _resolve_driver():
    from src.web.routes.analysis import _get_neo4j_driver

    return _get_neo4j_driver()


def _get_catalog() -> CatalogContext:
    driver = _resolve_driver()
    if driver is None:
        raise HTTPException(status_code=503, detail="catalog backend unavailable")
    return CatalogContext(driver, database="neo4j")


VALID_VIEWS = {"topic", "subject", "dynasty"}


@router.get("/views/{view}")
@_rate_limit("60/minute")
async def list_catalog_view(
    request: Request,  # slowapi 需要 Request 在签名中
    view: str,
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(20, ge=1, le=200),
    catalog: CatalogContext = Depends(_get_catalog),
) -> Dict[str, Any]:
    """分页列出某视图节点。返回 ``{view, page, size, items}``。"""
    view_key = (view or "").strip().lower()
    if view_key not in VALID_VIEWS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported view={view!r}; allowed={sorted(VALID_VIEWS)}",
        )
    try:
        items: List[Dict[str, Any]] = catalog.list_view(view_key, page=page, size=size)
    except CatalogContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:  # pragma: no cover - 上游 driver 错误
        logger.exception("catalog list_view failed: view=%s", view_key)
        raise HTTPException(status_code=500, detail="catalog query failed")

    return {
        "view": view_key,
        "page": page,
        "size": size,
        "count": len(items),
        "items": items,
    }


@router.get("/views/{view}/query")
@_rate_limit("60/minute")
async def query_catalog_view(
    request: Request,
    view: str,
    key: Optional[str] = Query(None, description="topic.key"),
    code: Optional[str] = Query(None, description="subject.code"),
    dynasty: Optional[str] = Query(None, description="dynasty.dynasty"),
    limit: int = Query(100, ge=1, le=500),
    catalog: CatalogContext = Depends(_get_catalog),
) -> Dict[str, Any]:
    """按主键查某视图下的 documents。"""
    view_key = (view or "").strip().lower()
    if view_key not in VALID_VIEWS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported view={view!r}; allowed={sorted(VALID_VIEWS)}",
        )
    criteria: Dict[str, Any] = {"limit": limit}
    if view_key == "topic":
        if not key:
            raise HTTPException(status_code=400, detail="topic view requires 'key'")
        criteria["key"] = key
    elif view_key == "subject":
        if not code:
            raise HTTPException(status_code=400, detail="subject view requires 'code'")
        criteria["code"] = code
    else:
        if not dynasty:
            raise HTTPException(
                status_code=400, detail="dynasty view requires 'dynasty'"
            )
        criteria["dynasty"] = dynasty
    try:
        items = catalog.query(view_key, criteria)
    except CatalogContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "view": view_key,
        "criteria": {k: v for k, v in criteria.items() if k != "limit"},
        "count": len(items),
        "items": items,
    }
