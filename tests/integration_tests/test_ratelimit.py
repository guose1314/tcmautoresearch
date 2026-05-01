"""T6.2 — slowapi 速率限制集成测试。

验收门：
- ``/api/analysis/*`` 和 ``/api/research/*`` 在 60/minute 后返回 429。
- ``/api/catalog/*`` 在 120/minute 后返回 429。
- 429 响应体包含统一字段 ``detail`` / ``error="rate_limit_exceeded"``。

使用最小 FastAPI 应用（不依赖业务路由）以便快速跑通。
"""

from __future__ import annotations

import unittest
from typing import Tuple

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.middleware.ratelimit import (
    DEFAULT_API_LIMIT,
    RATE_LIMIT_RULES,
    install_rate_limiter,
    resolve_limit_for_path,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    install_rate_limiter(app)

    @app.get("/api/analysis/sample")
    async def _analysis():
        return {"ok": True}

    @app.get("/api/research/cycle")
    async def _research():
        return {"ok": True}

    @app.get("/api/catalog/list")
    async def _catalog():
        return {"ok": True}

    @app.get("/api/other/ping")
    async def _other():
        return {"ok": True}

    @app.get("/health")
    async def _health():
        return {"status": "ok"}

    return app


def _drive(client: TestClient, path: str, total: int, *, ip: str) -> Tuple[int, int]:
    """在固定 IP 下发 ``total`` 次请求，返回 (200_count, 429_count)。"""
    ok = 0
    rate_limited = 0
    headers = {"X-Forwarded-For": ip}
    for _ in range(total):
        resp = client.get(path, headers=headers)
        if resp.status_code == 200:
            ok += 1
        elif resp.status_code == 429:
            rate_limited += 1
    return ok, rate_limited


class TestRateLimitMiddleware(unittest.TestCase):
    def test_resolve_limit_for_path(self) -> None:
        self.assertEqual(resolve_limit_for_path("/api/analysis/x"), "60/minute")
        self.assertEqual(resolve_limit_for_path("/api/research/y"), "60/minute")
        self.assertEqual(resolve_limit_for_path("/api/catalog/z"), "120/minute")
        self.assertEqual(resolve_limit_for_path("/api/other/q"), DEFAULT_API_LIMIT)
        self.assertIsNone(resolve_limit_for_path("/health"))

    def test_analysis_returns_429_after_60(self) -> None:
        app = _build_app()
        client = TestClient(app)
        ok, blocked = _drive(client, "/api/analysis/sample", total=65, ip="10.0.0.1")
        self.assertEqual(ok, 60, f"前 60 次必须放行 (got ok={ok})")
        self.assertEqual(blocked, 5, f"超出后必须 429 (got blocked={blocked})")

    def test_research_returns_429_after_60(self) -> None:
        app = _build_app()
        client = TestClient(app)
        ok, blocked = _drive(client, "/api/research/cycle", total=62, ip="10.0.0.2")
        self.assertEqual(ok, 60)
        self.assertEqual(blocked, 2)

    def test_catalog_allows_120_then_429(self) -> None:
        app = _build_app()
        client = TestClient(app)
        ok, blocked = _drive(client, "/api/catalog/list", total=123, ip="10.0.0.3")
        self.assertEqual(ok, 120)
        self.assertEqual(blocked, 3)

    def test_unified_429_error_body(self) -> None:
        app = _build_app()
        client = TestClient(app)
        # 触发 429
        for _ in range(60):
            client.get("/api/analysis/sample", headers={"X-Forwarded-For": "10.0.0.4"})
        resp = client.get(
            "/api/analysis/sample", headers={"X-Forwarded-For": "10.0.0.4"}
        )
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertEqual(body.get("error"), "rate_limit_exceeded")
        self.assertIn("detail", body)
        self.assertIn("rate limit exceeded", body["detail"])
        self.assertEqual(body.get("scope"), "/api/analysis")
        self.assertIn("60/minute", body.get("limit", ""))
        self.assertEqual(resp.headers.get("Retry-After"), "60")

    def test_health_endpoint_not_rate_limited(self) -> None:
        app = _build_app()
        client = TestClient(app)
        for _ in range(200):
            resp = client.get("/health")
            self.assertEqual(resp.status_code, 200)

    def test_per_ip_isolation(self) -> None:
        """不同 IP 应有独立限流计数。"""
        app = _build_app()
        client = TestClient(app)
        ok_a, blocked_a = _drive(
            client, "/api/analysis/sample", total=60, ip="10.0.1.1"
        )
        ok_b, blocked_b = _drive(
            client, "/api/analysis/sample", total=60, ip="10.0.1.2"
        )
        self.assertEqual(ok_a, 60)
        self.assertEqual(ok_b, 60)
        self.assertEqual(blocked_a, 0)
        self.assertEqual(blocked_b, 0)

    def test_per_scope_isolation_same_ip(self) -> None:
        """同 IP 不同 scope（analysis vs catalog）应该独立计数。"""
        app = _build_app()
        client = TestClient(app)
        # 打满 analysis
        ok_a, blocked_a = _drive(
            client, "/api/analysis/sample", total=60, ip="10.0.2.1"
        )
        self.assertEqual(ok_a, 60)
        # catalog 不应被影响
        resp = client.get("/api/catalog/list", headers={"X-Forwarded-For": "10.0.2.1"})
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
