"""T5.5: GraphRAG 三档摘要 + offline community summaries 单测。

验收门：
- 3 类 question (global / community / local) 各 1 测试。
- token 消耗在 4060 8GB 上单 query ≤ 8000。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.llm.graph_rag import (
    DEFAULT_TOKEN_BUDGET,
    GraphRAG,
    RetrievalResult,
)
from tools.build_community_summaries import build_community_summaries

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _record(payload: Dict[str, Any]):
    rec = MagicMock()
    rec.get.side_effect = lambda key, default=None: payload.get(key, default)
    rec.__getitem__ = lambda self, key: payload[key]
    return rec


def _build_driver(*record_batches: List[Dict[str, Any]]):
    """``session.run`` 依次返回多批记录。"""

    batches = [iter([_record(r) for r in batch]) for batch in record_batches]
    session = MagicMock(name="Session")
    session.run.side_effect = batches
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=False)
    inner = MagicMock()
    inner.session = MagicMock(return_value=cm)
    wrapper = MagicMock()
    wrapper.driver = inner
    return wrapper, session


# ---------------------------------------------------------------------------
# 三档 question 各一测试
# ---------------------------------------------------------------------------


class TestGraphRAGQuestionTypes(unittest.TestCase):
    def test_global_concatenates_all_community_summaries(self) -> None:
        rows = [
            {"topic_key": "t-1", "body": "全库主题 A 摘要", "token_count": 12},
            {"topic_key": "t-2", "body": "全库主题 B 摘要", "token_count": 10},
        ]
        driver, session = _build_driver(rows)
        result = GraphRAG(neo4j_driver=driver).retrieve("global", query="")
        self.assertIsInstance(result, RetrievalResult)
        self.assertEqual(result.scope, "global")
        self.assertIn("[t-1]", result.body)
        self.assertIn("[t-2]", result.body)
        self.assertEqual(len(result.citations), 2)
        # Token budget 守门
        self.assertLessEqual(result.token_count, DEFAULT_TOKEN_BUDGET)
        # 验证调用 Cypher
        self.assertIn("MATCH (cs:CommunitySummary)", session.run.call_args.args[0])

    def test_community_filters_by_topic_keys(self) -> None:
        rows = [
            {"topic_key": "t-1", "body": "社区 t-1 摘要", "token_count": 5},
        ]
        driver, session = _build_driver(rows)
        result = GraphRAG(neo4j_driver=driver).retrieve(
            "community", query="麻仁润肠", topic_keys=["t-1"]
        )
        self.assertEqual(result.scope, "community")
        self.assertIn("社区 t-1 摘要", result.body)
        self.assertEqual(session.run.call_args.kwargs["topic_keys"], ["t-1"])
        self.assertLessEqual(result.token_count, DEFAULT_TOKEN_BUDGET)

    def test_local_renders_one_hop_subgraph(self) -> None:
        rows = [
            {
                "src": "Herb-麻仁",
                "src_labels": ["Herb"],
                "rel": "TREATS",
                "dst": "Symptom-便秘",
                "dst_labels": ["Symptom"],
            },
            {
                "src": "Herb-麻仁",
                "src_labels": ["Herb"],
                "rel": "PAIRED_WITH",
                "dst": "Herb-杏仁",
                "dst_labels": ["Herb"],
            },
        ]
        driver, session = _build_driver(rows)
        result = GraphRAG(neo4j_driver=driver).retrieve(
            "local", query="麻仁", entity_ids=["Herb-麻仁"]
        )
        self.assertEqual(result.scope, "local")
        self.assertIn("[TREATS]", result.body)
        self.assertIn("便秘", result.body)
        self.assertEqual(session.run.call_args.kwargs["entity_ids"], ["Herb-麻仁"])
        self.assertLessEqual(result.token_count, DEFAULT_TOKEN_BUDGET)


class TestGraphRAGTokenBudget(unittest.TestCase):
    def test_truncates_when_budget_exhausted(self) -> None:
        # 200 条长摘要，每条 ~200 字，总量远超 budget=500
        rows = [
            {"topic_key": f"t-{i}", "body": "摘要" * 200, "token_count": 200}
            for i in range(50)
        ]
        driver, _ = _build_driver(rows)
        result = GraphRAG(neo4j_driver=driver, token_budget=500).retrieve(
            "global", query=""
        )
        self.assertTrue(result.truncated)
        self.assertLessEqual(result.token_count, 500)

    def test_invalid_question_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            GraphRAG().retrieve("unknown", "x")

    def test_no_driver_returns_empty(self) -> None:
        result = GraphRAG().retrieve("global", "x")
        self.assertEqual(result.body, "")
        self.assertEqual(result.token_count, 0)


# ---------------------------------------------------------------------------
# tools/build_community_summaries
# ---------------------------------------------------------------------------


class TestBuildCommunitySummaries(unittest.TestCase):
    def test_writes_one_summary_per_topic(self) -> None:
        # 1 个 topic + 2 个文档
        topics = [{"key": "t-1", "label": "麻仁"}]
        docs = [
            {"id": "d-1", "title": "麻子仁丸", "summary": "通便润燥"},
            {"id": "d-2", "title": "麻仁丸方", "summary": "脾约证"},
        ]
        # session.run 调用顺序：list_topics, list_docs(t-1), upsert(t-1)
        driver, session = _build_driver(topics, docs, [])
        captured: List[str] = []

        def _fake_llm(prompt: str, *, max_tokens: int = 1500) -> str:
            captured.append(prompt)
            return "摘要：麻仁通便润燥；常配杏仁。"

        result = build_community_summaries(
            neo4j_driver=driver,
            llm_call=_fake_llm,
            max_tokens=200,
            sample_size=10,
        )
        self.assertEqual(result["written"], ["t-1"])
        self.assertEqual(result["topic_count"], 1)
        # LLM 收到包含主题 label
        self.assertIn("麻仁", captured[0])
        # MERGE CommunitySummary 触发
        upsert_call = session.run.call_args_list[-1]
        self.assertIn("MERGE (cs:CommunitySummary", upsert_call.args[0])
        self.assertEqual(upsert_call.kwargs["key"], "t-1")
        self.assertGreater(upsert_call.kwargs["n"], 0)

    def test_dry_run_skips_write(self) -> None:
        topics = [{"key": "t-1", "label": "麻仁"}]
        driver, session = _build_driver(topics, [])
        result = build_community_summaries(
            neo4j_driver=driver,
            dry_run=True,
        )
        self.assertEqual(result["skipped"], ["t-1"])
        self.assertEqual(result["written"], [])
        # 只跑了 list_topics + list_docs，没跑 upsert
        self.assertEqual(session.run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
