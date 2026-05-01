"""T5.1: FeedbackTranslator 三种翻译路径单测。

覆盖：
- ``graph_weight``：severity → factor，多 severity 聚合成多 action。
- ``prompt_bias``：按 source_phase 聚合 issue_fields + violations，输出文本/avoid_fields。
- ``modes``：critical → conservative，high>=3 → cautious，否则 normal。
另含 :class:`GraphWeightUpdater` 与 :class:`PromptBiasCompiler` 的轻量验证。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.contexts.lfitl import (
    FeedbackEntry,
    FeedbackTranslator,
    GraphWeightUpdater,
    PromptBiasCompiler,
)


def _make_feedback(
    *,
    source_phase: str = "hypothesis",
    severity: str = "medium",
    graph_targets: List[str] | None = None,
    issue_fields: List[str] | None = None,
    violations: List[Dict[str, Any]] | None = None,
    issues: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    return {
        "source_phase": source_phase,
        "severity": severity,
        "graph_targets": list(graph_targets or []),
        "issue_fields": list(issue_fields or []),
        "violations": list(violations or []),
        "issues": list(issues or []),
    }


# ---------------------------------------------------------------------------
# graph_weight 路径
# ---------------------------------------------------------------------------


class TestGraphWeightTranslation(unittest.TestCase):
    def test_severity_maps_to_factor_and_aggregates_per_severity(self) -> None:
        fbs = [
            _make_feedback(severity="critical", graph_targets=["n-A", "n-B"]),
            _make_feedback(severity="critical", graph_targets=["n-B", "n-C"]),  # 去重
            _make_feedback(severity="high", graph_targets=["n-D"]),
            _make_feedback(
                severity="low", graph_targets=["n-Z"]
            ),  # factor=1.0 应被丢弃
        ]
        plan = FeedbackTranslator().translate(fbs)
        actions = sorted(plan.graph_weight_actions, key=lambda a: a.factor)
        self.assertEqual(len(actions), 2)  # critical + high；low 被剔除
        critical = next(a for a in actions if a.factor == 0.5)
        high = next(a for a in actions if a.factor == 0.7)
        self.assertEqual(sorted(critical.node_ids), ["n-A", "n-B", "n-C"])
        self.assertEqual(high.node_ids, ["n-D"])
        self.assertIn("severity=critical", critical.reason)

    def test_graph_targets_inferred_from_issues(self) -> None:
        fbs = [
            {
                "source_phase": "analyze",
                "severity": "high",
                "issues": [
                    {"field": "evidence", "entity_id": "ent-1"},
                    {"field": "evidence", "node_id": "ent-2"},
                ],
            }
        ]
        plan = FeedbackTranslator().translate(fbs)
        self.assertEqual(len(plan.graph_weight_actions), 1)
        ids = sorted(plan.graph_weight_actions[0].node_ids)
        self.assertEqual(ids, ["ent-1", "ent-2"])


# ---------------------------------------------------------------------------
# prompt_bias 路径
# ---------------------------------------------------------------------------


class TestPromptBiasTranslation(unittest.TestCase):
    def test_per_phase_aggregation_and_text(self) -> None:
        fbs = [
            _make_feedback(
                source_phase="hypothesis",
                severity="high",
                issue_fields=["statement"],
                violations=[{"rule_id": "no_overclaim", "severity": "high"}],
            ),
            _make_feedback(
                source_phase="hypothesis",
                severity="medium",
                issue_fields=["evidence_grade"],
            ),
            _make_feedback(
                source_phase="publish",
                severity="critical",
                issue_fields=["abstract"],
                violations=[{"rule_id": "tcm_safety", "severity": "critical"}],
            ),
        ]
        plan = FeedbackTranslator().translate(fbs)
        by_purpose = {a.purpose: a for a in plan.prompt_bias_actions}
        self.assertIn("hypothesis", by_purpose)
        self.assertIn("publish", by_purpose)

        hyp = by_purpose["hypothesis"]
        self.assertEqual(sorted(hyp.avoid_fields), ["evidence_grade", "statement"])
        self.assertEqual(hyp.severity, "high")
        self.assertIn("statement", hyp.bias_text)
        self.assertIn("no_overclaim", hyp.bias_text)

        pub = by_purpose["publish"]
        self.assertEqual(pub.severity, "critical")
        self.assertIn("tcm_safety", pub.bias_text)

    def test_no_issues_no_violations_yields_no_action(self) -> None:
        fbs = [_make_feedback(source_phase="analyze", severity="low")]
        plan = FeedbackTranslator().translate(fbs)
        self.assertEqual(plan.prompt_bias_actions, [])


# ---------------------------------------------------------------------------
# modes 路径
# ---------------------------------------------------------------------------


class TestModesTranslation(unittest.TestCase):
    def test_critical_triggers_conservative_mode(self) -> None:
        plan = FeedbackTranslator().translate([_make_feedback(severity="critical")])
        self.assertEqual(plan.modes, {"global": "conservative"})

    def test_three_high_triggers_cautious_mode(self) -> None:
        fbs = [_make_feedback(severity="high") for _ in range(3)]
        plan = FeedbackTranslator().translate(fbs)
        self.assertEqual(plan.modes, {"global": "cautious"})

    def test_default_normal_mode(self) -> None:
        fbs = [
            _make_feedback(severity="medium"),
            _make_feedback(severity="low"),
        ]
        plan = FeedbackTranslator().translate(fbs)
        self.assertEqual(plan.modes, {"global": "normal"})


# ---------------------------------------------------------------------------
# GraphWeightUpdater (Cypher)
# ---------------------------------------------------------------------------


def _build_neo4j_driver(updated_count: int = 3):
    record = {"updated": updated_count}
    result = MagicMock(name="Result")
    result.single.return_value = record
    session = MagicMock(name="Session")
    session.run.return_value = result
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=session)
    cm.__exit__ = MagicMock(return_value=False)
    inner = MagicMock()
    inner.session = MagicMock(return_value=cm)
    wrapper = MagicMock()
    wrapper.driver = inner
    return wrapper, session


class TestGraphWeightUpdater(unittest.TestCase):
    def test_apply_runs_cypher_per_action(self) -> None:
        plan = FeedbackTranslator().translate(
            [
                _make_feedback(severity="critical", graph_targets=["a", "b"]),
                _make_feedback(severity="high", graph_targets=["c"]),
            ]
        )
        driver, session = _build_neo4j_driver(updated_count=2)
        result = GraphWeightUpdater(neo4j_driver=driver).apply(plan)
        self.assertEqual(result["applied"], 2)
        self.assertEqual(result["skipped"], 0)
        # 验证 Cypher 与参数
        self.assertEqual(session.run.call_count, 2)
        first_call = session.run.call_args_list[0]
        self.assertIn("MATCH (n) WHERE n.id IN $ids", first_call.args[0])
        self.assertIn(
            "SET n.weight = coalesce(n.weight, 1.0) * $factor", first_call.args[0]
        )
        # 顺序 critical 先（factor=0.5）
        factors = sorted(call.kwargs["factor"] for call in session.run.call_args_list)
        self.assertEqual(factors, [0.5, 0.7])

    def test_dry_run_skips_session(self) -> None:
        plan = FeedbackTranslator().translate(
            [_make_feedback(severity="critical", graph_targets=["a"])]
        )
        result = GraphWeightUpdater(neo4j_driver=None, dry_run=True).apply(plan)
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result["applied"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_learning_insights_compile_to_weight_hints(self) -> None:
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        insights = [
            {
                "insight_id": "insight-boost",
                "status": "active",
                "insight_type": "evidence_weight",
                "target_phase": "analyze",
                "confidence": 0.91,
                "description": "优先检索高复现证据链",
                "evidence_refs_json": [
                    {
                        "node_ids": ["claim-boost"],
                        "relationship_ids": ["rel-boost"],
                    }
                ],
                "expires_at": (now + timedelta(days=1)).isoformat(),
            },
            {
                "insight_id": "insight-low",
                "status": "active",
                "insight_type": "evidence_weight",
                "confidence": 0.4,
                "evidence_refs_json": [{"node_ids": ["claim-low"]}],
            },
        ]

        hints = GraphWeightUpdater().build_weight_hints_from_insights(
            insights,
            min_confidence=0.7,
            now=now,
        )

        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["node_ids"], ["claim-boost"])
        self.assertEqual(hints[0]["relationship_ids"], ["rel-boost"])
        self.assertGreater(hints[0]["boost"], 1.0)


# ---------------------------------------------------------------------------
# PromptBiasCompiler
# ---------------------------------------------------------------------------


class TestPromptBiasCompiler(unittest.TestCase):
    def test_compile_returns_per_purpose_blocks(self) -> None:
        plan = FeedbackTranslator().translate(
            [
                _make_feedback(
                    source_phase="hypothesis",
                    severity="high",
                    issue_fields=["statement"],
                    violations=[{"rule_id": "no_overclaim", "severity": "high"}],
                )
            ]
        )
        blocks = PromptBiasCompiler().compile(plan)
        self.assertIn("hypothesis", blocks)
        self.assertEqual(blocks["hypothesis"]["severity"], "high")
        self.assertIn("statement", blocks["hypothesis"]["avoid_fields"])
        self.assertIn("no_overclaim", blocks["hypothesis"]["bias_text"])

    def test_inject_writes_bias_into_runner_inputs(self) -> None:
        compiler = PromptBiasCompiler()
        plan = FeedbackTranslator().translate(
            [
                _make_feedback(
                    source_phase="analyze",
                    severity="medium",
                    issue_fields=["summary"],
                )
            ]
        )
        blocks = compiler.compile(plan)
        runner_inputs: Dict[str, Any] = {
            "task_description": "analyze",
            "input_payload": "...",
        }
        compiler.inject(runner_inputs, "analyze", blocks)
        self.assertIn("bias", runner_inputs)
        self.assertIn("summary", runner_inputs["bias"])
        self.assertEqual(runner_inputs["avoid_fields"], ["summary"])

    def test_inject_does_not_overwrite_existing_bias(self) -> None:
        compiler = PromptBiasCompiler()
        blocks = {"x": {"bias_text": "B1", "avoid_fields": ["f"]}}
        runner_inputs = {"bias": "user-set"}
        compiler.inject(runner_inputs, "x", blocks)
        self.assertEqual(runner_inputs["bias"], "user-set")

    def test_learning_insights_filter_active_confident_and_not_expired(self) -> None:
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        insights = [
            {
                "status": "active",
                "insight_type": "prompt_bias",
                "target_phase": "analyze",
                "confidence": 0.86,
                "description": "下一轮分析优先验证版本证据链",
                "expires_at": (now + timedelta(days=1)).isoformat(),
            },
            {
                "status": "active",
                "insight_type": "evidence_weight",
                "target_phase": "analyze",
                "confidence": 0.3,
                "description": "低置信度不应进入 prompt",
            },
            {
                "status": "active",
                "insight_type": "method_policy",
                "target_phase": "publish",
                "confidence": 0.93,
                "description": "过期策略不应进入 prompt",
                "expires_at": (now - timedelta(seconds=1)).isoformat(),
            },
        ]

        blocks = PromptBiasCompiler().compile_learning_insights(
            insights,
            min_confidence=0.75,
            now=now,
        )

        self.assertEqual(list(blocks), ["analyze"])
        self.assertIn("下一轮分析优先验证版本证据链", blocks["analyze"]["bias_text"])
        self.assertNotIn("低置信度", blocks["analyze"]["bias_text"])


# ---------------------------------------------------------------------------
# FeedbackEntry.from_dict 边角
# ---------------------------------------------------------------------------


class TestFeedbackEntryNormalization(unittest.TestCase):
    def test_severity_inferred_from_violations_when_missing(self) -> None:
        entry = FeedbackEntry.from_dict(
            {
                "source_phase": "publish",
                "violations": [
                    {"rule_id": "x", "severity": "medium"},
                    {"rule_id": "y", "severity": "critical"},
                ],
            }
        )
        self.assertEqual(entry.severity, "critical")

    def test_default_severity_medium(self) -> None:
        entry = FeedbackEntry.from_dict({"source_phase": "p"})
        self.assertEqual(entry.severity, "medium")


if __name__ == "__main__":
    unittest.main()
