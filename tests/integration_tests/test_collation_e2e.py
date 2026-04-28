"""T4.1 e2e: CollationContext 跑 1 文档全四校。"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.contexts.collation import CollationContext


class _FakeRecord(dict):
    def data(self) -> Dict[str, Any]:
        return dict(self)


def _build_neo4j_driver(records: List[_FakeRecord]):
    session = MagicMock()
    session.run.return_value = iter(records)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=False)
    inner = MagicMock()
    inner.session = MagicMock(return_value=cm)
    wrapper = MagicMock()
    wrapper.driver = inner
    return wrapper


class _FakeLitRecord:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _CollectingSession:
    def __init__(self):
        self.added: List[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestCollationContextE2E(unittest.TestCase):
    def test_collate_runs_all_four_strategies(self) -> None:
        # cross
        philology = MagicMock()
        philology._build_version_collation.return_value = {
            "enabled": True,
            "witness_count": 1,
            "difference_count": 1,
            "witnesses": [{"witness_title": "校本", "difference_count": 1}],
            "summary": ["与 校本 存在 1 处异文"],
            "collation_entries": [{"id": "ce-1"}],
        }
        # intra
        neo4j = _build_neo4j_driver(
            [
                _FakeRecord(
                    entity_a="脾气虚", type_a="syndrome",
                    entity_b="四君子汤", type_b="formula",
                    rel_types=["SUPPORTS"],
                ),
            ]
        )
        # external
        retriever = MagicMock()
        retriever.search.return_value = {
            "open_api_results": {
                "arxiv": [
                    _FakeLitRecord(
                        title="paper", authors=["A"], year=2024, doi="",
                        url="u", abstract="", citation_count=1,
                        external_id="arx-1",
                    )
                ],
                "google_scholar": [],
            }
        }
        captured_session = _CollectingSession()
        # rational
        from src.llm.self_refine_runner import RefineResult, RefineRound
        runner = MagicMock()
        runner.run.return_value = RefineResult(
            purpose="collation_rational",
            final_output="修订",
            rounds=[
                RefineRound(round_index=0, draft="d", critique_raw="[]", issues=[], refined="修订")
            ],
            succeeded=True,
        )

        ctx = CollationContext(
            philology_service=philology,
            neo4j_driver=neo4j,
            literature_retriever=retriever,
            self_refine_runner=runner,
            db_session_factory=lambda: captured_session,
        )
        report = ctx.collate(
            "doc-e2e-1",
            context={
                "raw_text": "底本原文：脾气虚证宜补气健脾。",
                "parallel_versions": [{"title": "校本", "text": "底本原文：脾气虚证应补气健脾。"}],
                "query": "脾气虚 补气健脾",
                "rational_rounds": 1,
            },
        )

        self.assertEqual(report.document_id, "doc-e2e-1")
        self.assertEqual(set(report.strategies.keys()), {"cross", "intra", "external", "rational"})
        for name in ("cross", "intra", "external", "rational"):
            self.assertTrue(
                report.strategies[name].succeeded,
                f"strategy {name} failed: {report.strategies[name].error}",
            )

        cross = report.strategies["cross"].payload
        self.assertEqual(cross["witness_count"], 1)

        intra = report.strategies["intra"].payload
        self.assertEqual(intra["echo_count"], 1)

        external = report.strategies["external"].payload
        self.assertEqual(external["evidence_count"], 1)
        self.assertEqual(external["persisted_count"], 1)
        self.assertEqual(len(captured_session.added), 1)

        rational = report.strategies["rational"].payload
        self.assertEqual(rational["rounds"], 1)
        self.assertEqual(rational["final_output"], "修订")

        # to_dict 摘要
        d = report.to_dict()
        self.assertEqual(d["summary"]["total"], 4)
        self.assertEqual(d["summary"]["succeeded"], 4)

    def test_unknown_strategy_marked_failed_but_does_not_break_others(self) -> None:
        ctx = CollationContext()  # 全 None
        report = ctx.collate("doc-x", strategies=("cross", "bogus"))
        self.assertFalse(report.strategies["bogus"].succeeded)
        self.assertIn("unknown strategy", report.strategies["bogus"].error)
        # cross 因 service=None 仍能跑且成功（返回 enabled=False）
        self.assertTrue(report.strategies["cross"].succeeded)


if __name__ == "__main__":
    unittest.main()
