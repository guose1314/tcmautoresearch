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
    VALID_ASSET_TYPES,
    GraphRAG,
    RetrievalResult,
)
from src.research.phases.analyze_phase import AnalyzePhaseMixin
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


class TestGraphRAGTypedRetrieval(unittest.TestCase):
    def test_evidence_asset_type_returns_traceability(self) -> None:
        rows = [
            {
                "node_id": "evidence::cycle-1::ev-1",
                "labels": ["Evidence"],
                "props": {
                    "cycle_id": "cycle-1",
                    "phase": "analyze",
                    "evidence_id": "ev-1",
                    "title": "麻仁润肠证据",
                    "excerpt": "麻仁可润肠通便",
                    "evidence_grade": "B",
                    "confidence": 0.82,
                },
                "relationship_id": "rel-ev-claim-1",
                "rel_type": "EVIDENCE_FOR",
                "neighbor_id": "claim::cycle-1::cl-1",
                "neighbor_labels": ["EvidenceClaim"],
                "source_phase": "analyze",
                "cycle_id": "cycle-1",
            }
        ]
        driver, session = _build_driver(rows)

        result = GraphRAG(neo4j_driver=driver).retrieve(
            "local",
            query="麻仁",
            asset_type="evidence",
            entity_ids=["evidence::cycle-1::ev-1"],
            cycle_id="cycle-1",
        )

        self.assertEqual(result.scope, "local")
        self.assertEqual(result.asset_type, "evidence")
        self.assertIn("麻仁润肠证据", result.body)
        self.assertIn("麻仁可润肠通便", result.body)
        self.assertEqual(result.citations[0]["asset_type"], "evidence")
        self.assertEqual(result.traceability["node_ids"], ["evidence::cycle-1::ev-1"])
        self.assertEqual(result.traceability["relationship_ids"], ["rel-ev-claim-1"])
        self.assertEqual(result.traceability["source_phase"], "analyze")
        self.assertEqual(result.traceability["cycle_id"], "cycle-1")
        self.assertIn("MATCH (n:Evidence)", session.run.call_args.args[0])
        self.assertEqual(session.run.call_args.kwargs["query_fields"][0], "evidence_id")
        self.assertIn("evidence", VALID_ASSET_TYPES)

    def test_invalid_asset_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            GraphRAG().retrieve("local", "x", asset_type="unknown")

    def test_weight_hints_prioritize_boosted_claims(self) -> None:
        rows = [
            {
                "node_id": "claim::cycle-1::cl-plain",
                "labels": ["EvidenceClaim"],
                "props": {
                    "cycle_id": "cycle-1",
                    "phase": "analyze",
                    "claim_id": "cl-plain",
                    "claim_text": "普通证据主张",
                    "relation_type": "supports",
                    "evidence_grade": "C",
                    "confidence": 0.61,
                },
                "relationship_id": "rel-plain",
                "source_phase": "analyze",
                "cycle_id": "cycle-1",
            },
            {
                "node_id": "claim::cycle-1::cl-boost",
                "labels": ["EvidenceClaim"],
                "props": {
                    "cycle_id": "cycle-1",
                    "phase": "analyze",
                    "claim_id": "cl-boost",
                    "claim_text": "高置信证据主张",
                    "relation_type": "supports",
                    "evidence_grade": "A",
                    "confidence": 0.93,
                },
                "relationship_id": "rel-boost",
                "source_phase": "analyze",
                "cycle_id": "cycle-1",
            },
        ]
        driver, _session = _build_driver(rows)

        result = GraphRAG(neo4j_driver=driver).retrieve(
            "local",
            query="麻仁",
            asset_type="claim",
            cycle_id="cycle-1",
            weight_hints=[
                {
                    "node_ids": ["claim::cycle-1::cl-boost"],
                    "relationship_ids": ["rel-boost"],
                    "boost": 1.8,
                }
            ],
        )

        self.assertIn("高置信证据主张", result.body.splitlines()[0])
        self.assertEqual(result.metadata["weight_hint_applied_count"], 1)

    def test_weight_hints_demote_rejected_relationships(self) -> None:
        rows = [
            {
                "node_id": "claim::cycle-1::cl-rejected",
                "labels": ["EvidenceClaim"],
                "props": {
                    "cycle_id": "cycle-1",
                    "phase": "analyze",
                    "claim_id": "cl-rejected",
                    "claim_text": "已拒绝的候选关系主张",
                    "relation_type": "supports",
                    "evidence_grade": "B",
                    "confidence": 0.94,
                },
                "relationship_id": "rel-rejected",
                "source_phase": "analyze",
                "cycle_id": "cycle-1",
            },
            {
                "node_id": "claim::cycle-1::cl-neutral",
                "labels": ["EvidenceClaim"],
                "props": {
                    "cycle_id": "cycle-1",
                    "phase": "analyze",
                    "claim_id": "cl-neutral",
                    "claim_text": "未被拒绝的普通关系主张",
                    "relation_type": "supports",
                    "evidence_grade": "C",
                    "confidence": 0.62,
                },
                "relationship_id": "rel-neutral",
                "source_phase": "analyze",
                "cycle_id": "cycle-1",
            },
        ]
        driver, _session = _build_driver(rows)

        result = GraphRAG(neo4j_driver=driver).retrieve(
            "local",
            query="麻仁",
            asset_type="claim",
            cycle_id="cycle-1",
            weight_hints=[
                {
                    "relationship_ids": ["rel-rejected"],
                    "boost": 0.24,
                    "effect": "suppress",
                }
            ],
        )

        self.assertIn("未被拒绝的普通关系主张", result.body.splitlines()[0])
        self.assertEqual(result.metadata["weight_hint_applied_count"], 1)


class TestGraphRAGRetrievalCache(unittest.TestCase):
    def test_same_request_uses_cached_result_and_returns_deep_copy(self) -> None:
        rows = [
            {"topic_key": "t-1", "body": "全库主题 A 摘要", "token_count": 12},
        ]
        driver, session = _build_driver(rows)
        rag = GraphRAG(neo4j_driver=driver)

        first = rag.retrieve("global", query="麻仁")
        first.citations.append({"type": "Mutated", "topic_key": "bad"})
        first.body = "polluted"
        second = rag.retrieve("global", query="麻仁")

        self.assertEqual(session.run.call_count, 1)
        self.assertIn("全库主题 A 摘要", second.body)
        self.assertEqual(
            second.citations, [{"type": "CommunitySummary", "topic_key": "t-1"}]
        )
        self.assertIsNot(first, second)

    def test_different_cycle_id_does_not_share_cache(self) -> None:
        first_rows = [self._typed_evidence_row("cycle-1", "ev-1")]
        second_rows = [self._typed_evidence_row("cycle-2", "ev-2")]
        driver, session = _build_driver(first_rows, second_rows)
        rag = GraphRAG(neo4j_driver=driver)

        first = rag.retrieve(
            "local",
            query="麻仁",
            asset_type="evidence",
            entity_ids=["ev-1"],
            cycle_id="cycle-1",
        )
        second = rag.retrieve(
            "local",
            query="麻仁",
            asset_type="evidence",
            entity_ids=["ev-1"],
            cycle_id="cycle-2",
        )

        self.assertEqual(session.run.call_count, 2)
        self.assertEqual(first.traceability["cycle_id"], "cycle-1")
        self.assertEqual(second.traceability["cycle_id"], "cycle-2")
        self.assertEqual(session.run.call_args_list[0].kwargs["cycle_id"], "cycle-1")
        self.assertEqual(session.run.call_args_list[1].kwargs["cycle_id"], "cycle-2")

    def test_different_asset_type_does_not_share_cache(self) -> None:
        evidence_rows = [self._typed_evidence_row("cycle-1", "ev-1")]
        claim_rows = [
            {
                "node_id": "claim::cycle-1::cl-1",
                "labels": ["EvidenceClaim"],
                "props": {
                    "cycle_id": "cycle-1",
                    "phase": "analyze",
                    "claim_id": "cl-1",
                    "claim_text": "麻仁可润肠通便",
                    "relation_type": "supports",
                    "evidence_grade": "B",
                    "confidence": 0.8,
                },
                "relationship_id": "rel-cl-ev-1",
                "source_phase": "analyze",
                "cycle_id": "cycle-1",
            }
        ]
        driver, session = _build_driver(evidence_rows, claim_rows)
        rag = GraphRAG(neo4j_driver=driver)

        evidence = rag.retrieve(
            "local",
            query="麻仁",
            asset_type="evidence",
            entity_ids=["shared-id"],
            cycle_id="cycle-1",
        )
        claim = rag.retrieve(
            "local",
            query="麻仁",
            asset_type="claim",
            entity_ids=["shared-id"],
            cycle_id="cycle-1",
        )

        self.assertEqual(session.run.call_count, 2)
        self.assertEqual(evidence.asset_type, "evidence")
        self.assertEqual(claim.asset_type, "claim")
        self.assertIn("MATCH (n:Evidence)", session.run.call_args_list[0].args[0])
        self.assertIn("MATCH (n:EvidenceClaim)", session.run.call_args_list[1].args[0])

    @staticmethod
    def _typed_evidence_row(cycle_id: str, evidence_id: str) -> Dict[str, Any]:
        return {
            "node_id": f"evidence::{cycle_id}::{evidence_id}",
            "labels": ["Evidence"],
            "props": {
                "cycle_id": cycle_id,
                "phase": "analyze",
                "evidence_id": evidence_id,
                "title": f"{evidence_id} 麻仁润肠证据",
                "excerpt": "麻仁可润肠通便",
                "evidence_grade": "B",
                "confidence": 0.82,
            },
            "relationship_id": f"rel-{evidence_id}",
            "rel_type": "EVIDENCE_FOR",
            "source_phase": "analyze",
            "cycle_id": cycle_id,
        }


class _AnalyzePipeline:
    config: Dict[str, Any] = {}


class _AnalyzeHarness(AnalyzePhaseMixin):
    def __init__(self) -> None:
        self.pipeline = _AnalyzePipeline()


class _AnalyzeCycle:
    cycle_id = "cycle-typed"
    research_objective = "麻仁润肠证据检索"


class _TypedRagRunner:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def retrieve(
        self, question_type: str, query: str, **kwargs: Any
    ) -> RetrievalResult:
        self.calls.append({"question_type": question_type, "query": query, **kwargs})
        return RetrievalResult(
            scope=question_type,
            asset_type=str(kwargs.get("asset_type") or ""),
            body="typed evidence context",
            token_count=3,
            citations=[{"type": "Evidence", "id": "ev-1", "asset_type": "evidence"}],
            traceability={
                "node_ids": ["ev-1"],
                "relationship_ids": ["rel-1"],
                "source_phase": "analyze",
                "source_phases": ["analyze"],
                "cycle_id": "cycle-typed",
                "cycle_ids": ["cycle-typed"],
            },
        )


class TestAnalyzeGraphRAGTypedInjection(unittest.TestCase):
    def test_apply_graph_rag_passes_asset_type_and_cycle_id(self) -> None:
        harness = _AnalyzeHarness()
        runner = _TypedRagRunner()
        context: Dict[str, Any] = {
            "enable_graph_rag": True,
            "graph_rag_runner": runner,
            "graph_rag_asset_type": "evidence",
            "graph_rag_entity_ids": ["ev-1"],
            "graph_rag_query": "麻仁",
        }

        block = harness._apply_graph_rag(context, _AnalyzeCycle())

        self.assertEqual(runner.calls[0]["question_type"], "local")
        self.assertEqual(runner.calls[0]["asset_type"], "evidence")
        self.assertEqual(runner.calls[0]["cycle_id"], "cycle-typed")
        self.assertEqual(block["asset_type"], "evidence")
        self.assertEqual(block["traceability"]["node_ids"], ["ev-1"])
        self.assertEqual(context["graph_rag_context"], block)


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
