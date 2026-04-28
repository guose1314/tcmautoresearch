"""T3.1: CatalogContext 三视图 mock Neo4j 单测。"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.contexts.catalog import (
    CatalogContext,
    DynastySliceView,
    SubjectClassView,
    TopicView,
)
from src.contexts.catalog import cypher as catalog_cypher
from src.contexts.catalog.service import CatalogContextError


class _FakeRecord(dict):
    """简易 record：兼容 dict 与 ``record.data()`` 两种访问。"""

    def data(self) -> Dict[str, Any]:
        return dict(self)


def _make_session_mock(query_results: Dict[str, List[_FakeRecord]] | None = None):
    """构造支持 ``with driver.driver.session(...) as s: s.run(...)`` 协议的 mock。

    ``query_results``: 把以 (cypher 子串 -> records) 的映射作为返回值。
    """
    query_results = query_results or {}
    session = MagicMock(name="Neo4jSession")

    def _run(query: str, **params: Any):
        for needle, records in query_results.items():
            if needle in query:
                return iter(records)
        return iter([])

    session.run.side_effect = _run

    session_ctx = MagicMock(name="SessionContextManager")
    session_ctx.__enter__ = MagicMock(return_value=session)
    session_ctx.__exit__ = MagicMock(return_value=False)

    inner_driver = MagicMock(name="Neo4jInnerDriver")
    inner_driver.session = MagicMock(return_value=session_ctx)

    wrapper = MagicMock(name="Neo4jDriverWrapper")
    wrapper.driver = inner_driver
    wrapper.database = "neo4j"
    return wrapper, session, inner_driver


class TestCatalogConstraints(unittest.TestCase):
    def test_ensure_constraints_runs_three_ddls(self) -> None:
        driver, session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        ctx.ensure_constraints()
        executed = [call.args[0] for call in session.run.call_args_list]
        self.assertEqual(len(executed), 3)
        self.assertTrue(any("Topic" in q and "t.key IS UNIQUE" in q for q in executed))
        self.assertTrue(
            any("SubjectClass" in q and "s.code IS UNIQUE" in q for q in executed)
        )
        self.assertTrue(
            any("DynastySlice" in q and "d.dynasty IS UNIQUE" in q for q in executed)
        )

    def test_constraints_constants_are_idempotent_form(self) -> None:
        for ddl in catalog_cypher.CATALOG_CONSTRAINTS:
            self.assertIn("IF NOT EXISTS", ddl)

    def test_init_rejects_none_driver(self) -> None:
        with self.assertRaises(CatalogContextError):
            CatalogContext(None)


class TestCatalogRebuildTopic(unittest.TestCase):
    def test_rebuild_topic_view_runs_constraints_then_merges(self) -> None:
        driver, session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        written = ctx.rebuild_topic_view(
            [
                {
                    "key": "spleen_qi_def",
                    "label": "脾气虚",
                    "documents": [
                        {"document_id": "doc-1", "weight": 0.9},
                        {"document_id": "doc-2"},
                    ],
                }
            ]
        )
        self.assertEqual(written, 1)
        statements = [call.args[0] for call in session.run.call_args_list]
        # 3 个约束 + 1 个 MERGE Topic + 2 个关系
        self.assertEqual(len(statements), 6)
        self.assertTrue(any("MERGE (t:Topic" in s for s in statements))
        self.assertTrue(any("BELONGS_TO_TOPIC" in s for s in statements))

    def test_rebuild_topic_view_requires_key(self) -> None:
        driver, _session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        with self.assertRaises(CatalogContextError):
            ctx.rebuild_topic_view([{"label": "no key"}])


class TestCatalogRebuildSubject(unittest.TestCase):
    def test_rebuild_subject_view_links_documents(self) -> None:
        driver, session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        written = ctx.rebuild_subject_view(
            [
                {
                    "code": "R29",
                    "name": "中医基础理论",
                    "documents": [{"document_id": "doc-1"}, {"document_id": "doc-2"}],
                },
                {"code": "R28", "documents": []},
            ]
        )
        self.assertEqual(written, 2)
        statements = [call.args[0] for call in session.run.call_args_list]
        # MERGE_SUBJECT_CLASS 与 LINK 都包含 'MERGE (s:SubjectClass'；用起始词区分独立 MERGE 调用。
        standalone_merge = sum(
            1 for s in statements if s.startswith("MERGE (s:SubjectClass")
        )
        self.assertEqual(standalone_merge, 2)
        self.assertEqual(sum(1 for s in statements if "IN_SUBJECT" in s), 2)

    def test_rebuild_subject_defaults_scheme_to_clc(self) -> None:
        driver, session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        ctx.rebuild_subject_view([{"code": "R28", "documents": []}])
        merge_calls = [
            call
            for call in session.run.call_args_list
            if call.args[0].startswith("MERGE (s:SubjectClass")
        ]
        self.assertEqual(merge_calls[0].kwargs.get("scheme"), "CLC")


class TestCatalogRebuildDynasty(unittest.TestCase):
    def test_rebuild_dynasty_view_passes_year_range(self) -> None:
        driver, session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        written = ctx.rebuild_dynasty_view(
            [
                {
                    "dynasty": "Tang",
                    "start_year": 618,
                    "end_year": 907,
                    "documents": [{"document_id": "doc-tang"}],
                }
            ]
        )
        self.assertEqual(written, 1)
        merge_calls = [
            call
            for call in session.run.call_args_list
            if call.args[0].startswith("MERGE (d:DynastySlice")
        ]
        self.assertEqual(len(merge_calls), 1)
        self.assertEqual(merge_calls[0].kwargs.get("dynasty"), "Tang")
        self.assertEqual(merge_calls[0].kwargs.get("start_year"), 618)
        self.assertEqual(merge_calls[0].kwargs.get("end_year"), 907)


class TestCatalogQuery(unittest.TestCase):
    def test_query_topic_returns_records(self) -> None:
        driver, _session, _ = _make_session_mock(
            query_results={
                "BELONGS_TO_TOPIC": [
                    _FakeRecord(document_id="doc-1", source_file="a.txt", weight=0.9),
                    _FakeRecord(document_id="doc-2", source_file="b.txt", weight=0.5),
                ]
            }
        )
        ctx = CatalogContext(driver)
        results = ctx.query("topic", {"key": "spleen_qi_def"})
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["document_id"], "doc-1")
        self.assertEqual(results[0]["weight"], 0.9)

    def test_query_subject_uses_code(self) -> None:
        driver, session, _ = _make_session_mock(
            query_results={
                "IN_SUBJECT": [_FakeRecord(document_id="doc-x", source_file="x.txt")]
            }
        )
        ctx = CatalogContext(driver)
        results = ctx.query("subject", {"code": "R29", "limit": 50})
        self.assertEqual(results, [{"document_id": "doc-x", "source_file": "x.txt"}])
        run_call = session.run.call_args
        self.assertEqual(run_call.kwargs.get("code"), "R29")
        self.assertEqual(run_call.kwargs.get("limit"), 50)

    def test_query_dynasty_uses_dynasty(self) -> None:
        driver, session, _ = _make_session_mock(
            query_results={
                "IN_DYNASTY": [_FakeRecord(document_id="doc-d", source_file="d.txt")]
            }
        )
        ctx = CatalogContext(driver)
        results = ctx.query("dynasty", {"dynasty": "Tang"})
        self.assertEqual(len(results), 1)
        self.assertEqual(session.run.call_args.kwargs.get("dynasty"), "Tang")

    def test_query_rejects_unknown_view(self) -> None:
        driver, _session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        with self.assertRaises(CatalogContextError):
            ctx.query("bogus", {"key": "x"})

    def test_query_requires_view_primary_key(self) -> None:
        driver, _session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        with self.assertRaises(CatalogContextError):
            ctx.query("topic", {})


class TestCatalogViewModels(unittest.TestCase):
    def test_topic_view_to_dict(self) -> None:
        v = TopicView(key="k1", label="L", document_ids=["d1"], weights={"d1": 0.5})
        self.assertEqual(v.to_dict()["key"], "k1")
        self.assertEqual(v.to_dict()["weights"], {"d1": 0.5})

    def test_subject_view_default_scheme(self) -> None:
        v = SubjectClassView(code="R29", name="x")
        self.assertEqual(v.scheme, "CLC")

    def test_dynasty_view_year_optional(self) -> None:
        v = DynastySliceView(dynasty="Tang")
        self.assertIsNone(v.start_year)
        self.assertIsNone(v.end_year)


class TestUpsertTopicMembership(unittest.TestCase):
    def test_upsert_runs_merge_topic_then_link(self) -> None:
        driver, session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        written = ctx.upsert_topic_membership(
            "doc-42",
            [
                {"key": "spleen_qi_def", "label": "脾气虚", "weight": 0.8},
                {"key": "dampness", "label": "湿阻", "weight": 0.4},
            ],
        )
        self.assertEqual(written, 2)
        statements = [call.args[0] for call in session.run.call_args_list]
        # 3 个 constraint DDL + 2 个 MERGE Topic + 2 个 LINK
        self.assertEqual(len(statements), 7)
        merges = [s for s in statements if s.startswith("MERGE (t:Topic")]
        links = [s for s in statements if "BELONGS_TO_TOPIC" in s]
        self.assertEqual(len(merges), 2)
        self.assertEqual(len(links), 2)

    def test_upsert_requires_document_id(self) -> None:
        driver, _session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        with self.assertRaises(CatalogContextError):
            ctx.upsert_topic_membership("", [{"key": "x"}])

    def test_upsert_requires_key(self) -> None:
        driver, _session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        with self.assertRaises(CatalogContextError):
            ctx.upsert_topic_membership("doc-1", [{"label": "no key"}])


class TestListView(unittest.TestCase):
    def test_list_topic_view_returns_records(self) -> None:
        driver, _session, _ = _make_session_mock(
            {
                "MATCH (t:Topic)": [
                    _FakeRecord(
                        key="spleen_qi", label="脾气虚",
                        description="", document_count=5,
                    ),
                ]
            }
        )
        ctx = CatalogContext(driver)
        items = ctx.list_view("topic", page=1, size=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["key"], "spleen_qi")
        self.assertEqual(items[0]["document_count"], 5)

    def test_list_view_rejects_unknown(self) -> None:
        driver, _session, _ = _make_session_mock()
        ctx = CatalogContext(driver)
        with self.assertRaises(CatalogContextError):
            ctx.list_view("garbage")


if __name__ == "__main__":
    unittest.main()
