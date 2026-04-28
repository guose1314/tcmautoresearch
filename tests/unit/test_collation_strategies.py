"""T4.1: 4 个 collation strategy 各 1 个 happy-path 单测。"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# cross
# ---------------------------------------------------------------------------

class TestCrossCollationStrategy(unittest.TestCase):
    def test_cross_uses_philology_service_version_collation(self) -> None:
        from src.contexts.collation.strategies.cross import CrossCollationStrategy

        fake_service = MagicMock(name="PhilologyService")
        fake_service._build_version_collation.return_value = {
            "enabled": True,
            "witness_count": 1,
            "difference_count": 2,
            "witnesses": [{"witness_title": "底本 vs 校本", "difference_count": 2}],
            "summary": ["与 校本 存在 2 处异文"],
            "collation_entries": [{"id": "ce-1"}, {"id": "ce-2"}],
        }
        strategy = CrossCollationStrategy(philology_service=fake_service)
        out = strategy.run(
            "doc-1",
            context={
                "raw_text": "底本原文",
                "parallel_versions": [{"title": "校本", "text": "校本原文"}],
            },
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["witness_count"], 1)
        self.assertEqual(out["difference_count"], 2)
        self.assertEqual(len(out["collation_entries"]), 2)
        fake_service._build_version_collation.assert_called_once()

    def test_cross_returns_disabled_when_service_missing(self) -> None:
        from src.contexts.collation.strategies.cross import CrossCollationStrategy

        out = CrossCollationStrategy(philology_service=None).run(
            "doc-1", context={"raw_text": "x"}
        )
        self.assertFalse(out["enabled"])
        self.assertEqual(out["witness_count"], 0)


# ---------------------------------------------------------------------------
# intra
# ---------------------------------------------------------------------------

class _FakeRecord(dict):
    def data(self) -> Dict[str, Any]:
        return dict(self)


def _make_neo4j_driver(records: List[_FakeRecord]):
    session = MagicMock(name="Neo4jSession")
    session.run.return_value = iter(records)

    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=session)
    session_ctx.__exit__ = MagicMock(return_value=False)

    inner = MagicMock(name="InnerDriver")
    inner.session = MagicMock(return_value=session_ctx)
    wrapper = MagicMock()
    wrapper.driver = inner
    return wrapper, session


class TestIntraCollationStrategy(unittest.TestCase):
    def test_intra_classifies_pairs_into_echoes_and_contradictions(self) -> None:
        from src.contexts.collation.strategies.intra import IntraCollationStrategy

        records = [
            _FakeRecord(
                entity_a="脾气虚", type_a="syndrome",
                entity_b="四君子汤", type_b="formula",
                rel_types=["SUPPORTS"],
            ),
            _FakeRecord(
                entity_a="附子", type_a="herb",
                entity_b="半夏", type_b="herb",
                rel_types=["CONTRADICTS"],
            ),
            _FakeRecord(
                entity_a="人参", type_a="herb",
                entity_b="脾气虚", type_b="syndrome",
                rel_types=[],
            ),
        ]
        driver, session = _make_neo4j_driver(records)
        out = IntraCollationStrategy(neo4j_driver=driver).run(
            "doc-1", context={"intra_limit": 100}
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["co_mention_count"], 3)
        self.assertEqual(out["echo_count"], 1)
        self.assertEqual(out["contradiction_count"], 1)
        self.assertEqual(out["echoes"][0]["entity_a"], "脾气虚")
        self.assertEqual(out["contradictions"][0]["entity_a"], "附子")
        # ensure cypher param was passed
        session.run.assert_called_once()
        kwargs = session.run.call_args.kwargs
        self.assertEqual(kwargs.get("document_id"), "doc-1")


# ---------------------------------------------------------------------------
# external
# ---------------------------------------------------------------------------

class _FakeLitRecord:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _CollectingSession:
    """模拟 SQLAlchemy session：累计 add 的对象。"""

    def __init__(self):
        self.added: List[Any] = []
        self.committed = False

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestExternalCollationStrategy(unittest.TestCase):
    def test_external_calls_retriever_and_persists(self) -> None:
        from src.contexts.collation.strategies.external import ExternalCollationStrategy

        retriever = MagicMock(name="LiteratureRetriever")
        retriever.search.return_value = {
            "open_api_results": {
                "arxiv": [
                    _FakeLitRecord(
                        title="Astragalus polysaccharide review",
                        authors=["Zhang", "Liu"],
                        year=2024,
                        doi="10.1234/x",
                        url="https://arxiv.org/abs/2401.0001",
                        abstract="abs",
                        citation_count=3,
                        external_id="2401.0001",
                    )
                ],
                "google_scholar": [
                    _FakeLitRecord(
                        title="GS hit",
                        authors=["A"],
                        year=2023,
                        doi="",
                        url="https://scholar.google.com/?q=x",
                        abstract="",
                        citation_count=1,
                        external_id="gs-1",
                    )
                ],
            }
        }
        captured_session = _CollectingSession()
        strategy = ExternalCollationStrategy(
            literature_retriever=retriever,
            db_session_factory=lambda: captured_session,
            sources=("arxiv", "google_scholar"),
        )
        out = strategy.run("doc-1", context={"query": "黄芪 多糖"})

        self.assertTrue(out["enabled"])
        self.assertEqual(out["evidence_count"], 2)
        self.assertEqual(out["persisted_count"], 2)
        self.assertEqual(out["sources"], ["arxiv", "google_scholar"])
        retriever.search.assert_called_once()
        # ORM rows captured
        self.assertEqual(len(captured_session.added), 2)
        sources = sorted(obj.source for obj in captured_session.added)
        self.assertEqual(sources, ["arxiv", "google_scholar"])
        self.assertTrue(captured_session.committed)

    def test_external_returns_disabled_when_retriever_missing(self) -> None:
        from src.contexts.collation.strategies.external import ExternalCollationStrategy

        out = ExternalCollationStrategy().run("doc-1", context={"query": "x"})
        self.assertFalse(out["enabled"])


# ---------------------------------------------------------------------------
# rational
# ---------------------------------------------------------------------------

class TestRationalCollationStrategy(unittest.TestCase):
    def test_rational_invokes_self_refine_runner(self) -> None:
        from src.contexts.collation.strategies.rational import RationalCollationStrategy
        from src.llm.self_refine_runner import RefineResult, RefineRound

        fake_runner = MagicMock(name="SelfRefineRunner")
        fake_runner.run.return_value = RefineResult(
            purpose="collation_rational",
            final_output="修订版文本",
            rounds=[
                RefineRound(
                    round_index=0,
                    draft="初稿",
                    critique_raw="[]",
                    issues=[{"field": "证候", "issue": "前后矛盾"}],
                    refined="修订版文本",
                )
            ],
            succeeded=True,
        )
        strategy = RationalCollationStrategy(self_refine_runner=fake_runner)
        out = strategy.run(
            "doc-1",
            context={
                "raw_text": "原文：脾气虚宜辛温发散",
                "rational_rounds": 1,
            },
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["rounds"], 1)
        self.assertEqual(out["issues_found"], 1)
        self.assertTrue(out["succeeded"])
        self.assertEqual(out["final_output"], "修订版文本")
        fake_runner.run.assert_called_once()
        kwargs = fake_runner.run.call_args.kwargs
        self.assertEqual(kwargs["purpose"], "collation_rational")
        self.assertEqual(kwargs["max_refine_rounds"], 1)


if __name__ == "__main__":
    unittest.main()
