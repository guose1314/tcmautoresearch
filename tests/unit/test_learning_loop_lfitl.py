"""T5.2: LearningLoopOrchestrator.prepare_cycle 接入 LFITL 验收测试。

验收门：跑两轮 cycle，第二轮 prompt 中能看到第一轮反馈引发的偏置段。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, Dict, List

from src.research.learning_loop_orchestrator import LearningLoopOrchestrator


class _FakeFeedbackRepo:
    """In-memory feedback repo with the agreed ``recent(limit=N)`` contract."""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def add(self, record: Dict[str, Any]) -> None:
        self._records.append(record)

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(self._records[-limit:])


def _make_pipeline() -> Any:
    """Bare pipeline stub: orchestrator only needs config + a few duck-typed methods."""

    return SimpleNamespace(config={})


class TestLearningLoopLFITLIntegration(unittest.TestCase):
    def test_two_cycles_propagate_bias_from_first_into_second(self) -> None:
        repo = _FakeFeedbackRepo()
        llo = LearningLoopOrchestrator(
            feedback_repo=repo,
            recent_feedback_limit=10,
        )
        pipeline = _make_pipeline()

        # ---- Cycle 1: 还没有任何反馈 ----
        prep1 = llo.prepare_cycle(pipeline)
        self.assertEqual(prep1["prompt_bias_blocks"], {})
        ctx1 = LearningLoopOrchestrator.inject_phase_context(
            {"task": "hypothesis"},
            learning_strategy=prep1.get("learning_strategy"),
            previous_iteration_feedback=prep1.get("previous_iteration_feedback"),
            prompt_bias_blocks=prep1.get("prompt_bias_blocks"),
            lfitl_plan=prep1.get("lfitl_plan"),
        )
        self.assertNotIn("prompt_bias_blocks", ctx1)

        # 模拟第 1 轮 hypothesis phase 产生了 high 反馈
        repo.add(
            {
                "source_phase": "hypothesis",
                "severity": "high",
                "issue_fields": ["证候", "药味"],
                "violations": [{"rule_id": "R-001", "severity": "high"}],
            }
        )

        # ---- Cycle 2: 应该看到 cycle 1 的反馈被翻译进 prompt bias ----
        prep2 = llo.prepare_cycle(pipeline)
        bias_blocks = prep2["prompt_bias_blocks"]
        self.assertIn("hypothesis", bias_blocks)
        block = bias_blocks["hypothesis"]
        self.assertEqual(block["severity"], "high")
        self.assertIn("证候", block["bias_text"])
        self.assertIn("R-001", block["bias_text"])

        # inject_phase_context 应把 bias_blocks 透传到 phase 上下文
        ctx2 = LearningLoopOrchestrator.inject_phase_context(
            {"task": "hypothesis"},
            learning_strategy=prep2.get("learning_strategy"),
            previous_iteration_feedback=prep2.get("previous_iteration_feedback"),
            prompt_bias_blocks=prep2.get("prompt_bias_blocks"),
            lfitl_plan=prep2.get("lfitl_plan"),
        )
        self.assertIn("prompt_bias_blocks", ctx2)
        self.assertIn("hypothesis", ctx2["prompt_bias_blocks"])
        self.assertIn("证候", ctx2["prompt_bias_blocks"]["hypothesis"]["bias_text"])
        # lfitl_plan 也应附带在 cycle context 里
        self.assertIn("lfitl_plan", ctx2)
        self.assertGreaterEqual(ctx2["lfitl_plan"]["summary"]["prompt_bias_count"], 1)

    def test_missing_repo_disables_lfitl_silently(self) -> None:
        llo = LearningLoopOrchestrator()  # 没有 feedback_repo
        prep = llo.prepare_cycle(_make_pipeline())
        self.assertIsNone(prep["lfitl_plan"])
        self.assertEqual(prep["prompt_bias_blocks"], {})


if __name__ == "__main__":
    unittest.main()
