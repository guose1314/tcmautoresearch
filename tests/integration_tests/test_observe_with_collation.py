"""T4.2 e2e: ObservePhase 走 CollationContext.collate(...)。

通过直接调用 ObservePhaseMixin 的 collation 入口来验证：
1. 默认运行 4 个 strategy；
2. ``run_philology=False`` 时 ``cross`` 被剔除（向下兼容开关）；
3. ``enable_collation_strategies`` 显式控制策略子集；
4. 报告写回 phase 结果。
"""

from __future__ import annotations

import logging
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.contexts.collation import CollationContext
from src.contexts.collation.service import CollationReport, StrategyResult
from src.research.phases.observe_phase import ObservePhaseMixin


class _StubPipeline:
    """提供 ObservePhaseMixin 所需的最小 pipeline 接口。"""

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.logger = logging.getLogger("test_observe_with_collation")
        self.analysis_port = MagicMock(name="analysis_port")
        self.analysis_port.create_philology_service = MagicMock(return_value=None)
        self.create_module = MagicMock(return_value=None)
        self.neo4j_driver = None
        self.self_refine_runner = None
        self.db_session_factory = None


class _ObserveHarness(ObservePhaseMixin):
    """在测试里直接实例化 mixin，绕过 ResearchPhaseHandlers。"""

    def __init__(self, pipeline: _StubPipeline) -> None:
        self.pipeline = pipeline


def _make_collation_context_with_canned_reports() -> tuple[CollationContext, MagicMock]:
    """构造一个 CollationContext，其 ``collate`` 会返回固定的 4-strategy 成功报告。"""

    ctx = MagicMock(spec=CollationContext)

    def fake_collate(document_id: str, strategies=None, *, context=None):
        strategies = list(strategies or ("cross", "intra", "external", "rational"))
        report = CollationReport(document_id=document_id)
        for name in strategies:
            report.strategies[name] = StrategyResult(
                name=name,
                succeeded=True,
                payload={"document_id": document_id, "ok": True},
            )
        return report

    ctx.collate.side_effect = fake_collate
    return ctx, ctx.collate


class TestObserveWithCollation(unittest.TestCase):
    # ------------------------------------------------------------------ #
    # 默认走全 4 校
    # ------------------------------------------------------------------ #
    def test_collation_runs_all_four_strategies_per_document(self) -> None:
        pipeline = _StubPipeline()
        harness = _ObserveHarness(pipeline)

        ingestion_result = {
            "documents": [
                {
                    "urn": "doc-A",
                    "title": "金匮要略·湿病脉证治",
                    "raw_text_preview": "湿家病身上疼痛...",
                    "metadata": {
                        "parallel_versions": [{"title": "校本", "text": "湿家病身体疼痛..."}],
                    },
                },
                {
                    "urn": "doc-B",
                    "title": "中医基础理论·脏腑",
                    "raw_text_preview": "脾主运化...",
                    "metadata": {},
                },
            ]
        }
        ctx, fake_collate = _make_collation_context_with_canned_reports()

        result = harness._run_observe_collation_if_enabled(
            corpus_result=None,
            ingestion_result=ingestion_result,
            context={"collation_context": ctx},
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["document_count"], 2)
        self.assertEqual(
            sorted(result["strategies_enabled"]),
            ["cross", "external", "intra", "rational"],
        )
        # 2 docs × 4 strategies = 8 successes
        self.assertEqual(result["succeeded_total"], 8)
        self.assertEqual(result["failed_total"], 0)
        self.assertEqual(len(result["reports"]), 2)
        # collate called once per document
        self.assertEqual(fake_collate.call_count, 2)
        called_ids = sorted(call.kwargs["document_id"] for call in fake_collate.call_args_list)
        self.assertEqual(called_ids, ["doc-A", "doc-B"])

    # ------------------------------------------------------------------ #
    # run_philology=False 向下兼容：cross 必须被剔除
    # ------------------------------------------------------------------ #
    def test_run_philology_false_excludes_cross_strategy(self) -> None:
        pipeline = _StubPipeline()
        harness = _ObserveHarness(pipeline)
        ctx, fake_collate = _make_collation_context_with_canned_reports()

        result = harness._run_observe_collation_if_enabled(
            corpus_result=None,
            ingestion_result={
                "documents": [
                    {"urn": "doc-X", "title": "t", "raw_text_preview": "x", "metadata": {}}
                ]
            },
            context={"collation_context": ctx, "run_philology": False},
        )

        self.assertNotIn("cross", result["strategies_enabled"])
        self.assertEqual(
            sorted(result["strategies_enabled"]),
            ["external", "intra", "rational"],
        )
        # 验证传给 collate 的 strategies 也确实剔除了 cross
        passed_strategies = list(fake_collate.call_args.kwargs["strategies"])
        self.assertNotIn("cross", passed_strategies)

    # ------------------------------------------------------------------ #
    # enable_collation_strategies 显式选择
    # ------------------------------------------------------------------ #
    def test_enable_collation_strategies_explicit_subset(self) -> None:
        pipeline = _StubPipeline()
        harness = _ObserveHarness(pipeline)
        ctx, fake_collate = _make_collation_context_with_canned_reports()

        result = harness._run_observe_collation_if_enabled(
            corpus_result=None,
            ingestion_result={
                "documents": [
                    {"urn": "doc-Y", "title": "t", "raw_text_preview": "x", "metadata": {}}
                ]
            },
            context={
                "collation_context": ctx,
                "enable_collation_strategies": ["intra", "rational"],
            },
        )

        self.assertEqual(sorted(result["strategies_enabled"]), ["intra", "rational"])
        self.assertEqual(result["succeeded_total"], 2)
        passed_strategies = list(fake_collate.call_args.kwargs["strategies"])
        self.assertEqual(sorted(passed_strategies), ["intra", "rational"])

    # ------------------------------------------------------------------ #
    # 顶层开关关闭 → 跳过整段
    # ------------------------------------------------------------------ #
    def test_collation_disabled_returns_none(self) -> None:
        pipeline = _StubPipeline(
            config={"collation_context": {"enabled": False}}
        )
        harness = _ObserveHarness(pipeline)
        result = harness._run_observe_collation_if_enabled(
            corpus_result={"documents": []},
            ingestion_result={"documents": []},
            context={},
        )
        self.assertIsNone(result)

    # ------------------------------------------------------------------ #
    # 端到端：execute_observe_phase 把 collation_pipeline 写回 results
    # ------------------------------------------------------------------ #
    def test_execute_observe_phase_includes_collation_pipeline(self) -> None:
        pipeline = _StubPipeline()
        harness = _ObserveHarness(pipeline)
        ctx, _ = _make_collation_context_with_canned_reports()

        # mock ResearchCycle
        cycle = MagicMock()
        cycle.cycle_id = "cycle-001"

        # 关闭采集 / ingestion / literature，只走 collation 路径
        # 让 collation 直接拿到 ingestion_result.documents
        injected_ingestion = {
            "documents": [
                {
                    "urn": "doc-E2E",
                    "title": "本草纲目·序",
                    "raw_text_preview": "本草纲目总目...",
                    "metadata": {},
                }
            ],
            "processed_document_count": 1,
            "aggregate": {},
        }

        # patch helpers to short-circuit corpus/ingestion/literature
        harness._collect_observe_corpus_if_enabled = lambda c: {  # type: ignore[assignment]
            "documents": [{"urn": "doc-E2E"}]
        }
        harness._run_observe_literature_if_enabled = lambda c: None  # type: ignore[assignment]
        harness._run_observe_ingestion_if_enabled = lambda corpus, c: injected_ingestion  # type: ignore[assignment]
        harness._build_observe_philology_artifacts = lambda ing: []  # type: ignore[assignment]
        harness._build_observe_graph_assets = lambda cid, ing: {}  # type: ignore[assignment]
        # _build_observe_metadata 依赖较多内部状态，简化为返回空 dict
        harness._build_observe_metadata = lambda *args, **kwargs: {}  # type: ignore[assignment]
        # 一些 append_* 也需 stub 掉以避免触碰未实现的辅助
        harness._append_corpus_observe_updates = lambda *a, **k: None  # type: ignore[assignment]
        harness._append_ingestion_observe_updates = lambda *a, **k: None  # type: ignore[assignment]
        harness._append_literature_observe_updates = lambda *a, **k: None  # type: ignore[assignment]

        phase_result = harness.execute_observe_phase(
            cycle, {"collation_context": ctx, "enable_collation_strategies": ["intra"]}
        )

        results = phase_result.get("results") or {}
        collation_pipeline = results.get("collation_pipeline")
        self.assertIsInstance(collation_pipeline, dict)
        self.assertEqual(collation_pipeline["document_count"], 1)
        self.assertEqual(collation_pipeline["strategies_enabled"], ["intra"])
        self.assertEqual(collation_pipeline["succeeded_total"], 1)
        # metadata 摘要也写入
        meta = phase_result.get("metadata") or {}
        self.assertIn("collation_pipeline", meta)
        self.assertEqual(meta["collation_pipeline"]["document_count"], 1)


if __name__ == "__main__":
    unittest.main()
