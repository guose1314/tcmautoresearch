"""T3.3: /api/catalog/views/{view} 三视图 API 集成测试。

驱动通过 monkeypatch 替换 ``src.web.routes.analysis._get_neo4j_driver`` 返回 mock。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeRecord(dict):
    def data(self) -> Dict[str, Any]:
        return dict(self)


def _make_driver(query_results: Dict[str, List[_FakeRecord]]):
    """构造与 CatalogContext 兼容的 mock driver。"""
    session = MagicMock(name="Neo4jSession")

    def _run(query: str, **params: Any):
        for needle, records in query_results.items():
            if needle in query:
                return iter(records)
        return iter([])

    session.run.side_effect = _run
    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=session)
    session_ctx.__exit__ = MagicMock(return_value=False)

    inner = MagicMock(name="InnerDriver")
    inner.session = MagicMock(return_value=session_ctx)

    wrapper = MagicMock(name="DriverWrapper")
    wrapper.driver = inner
    wrapper.database = "neo4j"
    return wrapper


def _build_app(driver) -> FastAPI:
    """挂载 catalog router；override _resolve_driver 以注入 mock driver。"""
    from src.web.routes import catalog as catalog_route

    app = FastAPI()
    app.include_router(catalog_route.router)
    # 直接 patch 模块级解析器
    catalog_route._resolve_driver = lambda: driver  # type: ignore[attr-defined]
    return app


class TestCatalogViewsAPI(unittest.TestCase):
    def test_topic_view_returns_paginated_items(self) -> None:
        driver = _make_driver(
            {
                "MATCH (t:Topic)": [
                    _FakeRecord(
                        key="spleen_qi_deficiency",
                        label="脾气虚",
                        description="",
                        document_count=12,
                    ),
                    _FakeRecord(
                        key="dampness_obstruction",
                        label="湿阻",
                        description="",
                        document_count=7,
                    ),
                ],
                "CREATE CONSTRAINT": [],
            }
        )
        client = TestClient(_build_app(driver))
        resp = client.get("/api/catalog/views/topic", params={"page": 1, "size": 10})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["view"], "topic")
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["size"], 10)
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["items"][0]["key"], "spleen_qi_deficiency")
        self.assertEqual(body["items"][0]["document_count"], 12)

    def test_subject_view_returns_items(self) -> None:
        driver = _make_driver(
            {
                "MATCH (s:SubjectClass)": [
                    _FakeRecord(
                        code="R29", name="中医基础理论", scheme="CLC", document_count=42
                    ),
                ],
                "CREATE CONSTRAINT": [],
            }
        )
        client = TestClient(_build_app(driver))
        resp = client.get("/api/catalog/views/subject")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["view"], "subject")
        self.assertEqual(body["count"], 1)
        item = body["items"][0]
        self.assertEqual(item["code"], "R29")
        self.assertEqual(item["scheme"], "CLC")

    def test_dynasty_view_returns_items(self) -> None:
        driver = _make_driver(
            {
                "MATCH (d:DynastySlice)": [
                    _FakeRecord(
                        dynasty="Tang", start_year=618, end_year=907, document_count=88
                    ),
                ],
                "CREATE CONSTRAINT": [],
            }
        )
        client = TestClient(_build_app(driver))
        resp = client.get("/api/catalog/views/dynasty", params={"size": 5})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["view"], "dynasty")
        self.assertEqual(body["size"], 5)
        item = body["items"][0]
        self.assertEqual(item["dynasty"], "Tang")
        self.assertEqual(item["start_year"], 618)

    def test_invalid_view_returns_400(self) -> None:
        driver = _make_driver({})
        client = TestClient(_build_app(driver))
        resp = client.get("/api/catalog/views/unknown")
        self.assertEqual(resp.status_code, 400)

    def test_topic_query_endpoint_requires_key(self) -> None:
        driver = _make_driver({})
        client = TestClient(_build_app(driver))
        resp = client.get("/api/catalog/views/topic/query")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
