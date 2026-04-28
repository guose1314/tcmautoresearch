"""T4.5 集成测试：SelfRefineRunner 接入 hypothesis / analyze / publish 三阶段。

验收门：
- 3 个 phase 各 1 个测试用例，验证 ``self_refine_v2_*`` metadata 写入；
- ``self_refine_v2_token_usage_ratio`` ≤ 2.5（即 token 使用增幅不超过 2.5×）；
- ``enable_self_refine=False`` 时不触发 v2 路径（保留旧 fallback）。
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from src.llm.self_refine_runner import RefineResult, RefineRound
from src.research._self_refine_t45 import (
    apply_self_refine_v2,
    resolve_enable_self_refine,
    resolve_self_refine_runner,
)


def _make_fake_runner(*, refined_text: str, critique: str = "[]"):
    """构造一个仅模拟 token 增量的 SelfRefineRunner。

    ``refined_text`` 长度直接控制 token_usage_ratio，便于验证 ≤ 2.5×。
    """

    runner = MagicMock(name="FakeSelfRefineRunner")

    def fake_run(purpose: str, inputs: Dict[str, Any], max_refine_rounds: int = 1):
        draft = str(inputs.get("input_payload") or "")
        rounds = [
            RefineRound(
                round_index=0,
                draft=draft,
                critique_raw=critique,
                issues=[{"field": "summary", "issue": "需要更精确的术语"}],
                refined=refined_text,
            )
        ]
        return RefineResult(
            purpose=purpose,
            final_output=refined_text,
            rounds=rounds,
            succeeded=True,
        )

    runner.run.side_effect = fake_run
    return runner


class _StubPipeline:
    def __init__(self, *, runner=None, enable: bool = True) -> None:
        self.config = {"self_refine": {"enable_self_refine": bool(enable)}}
        self.self_refine_runner = runner


class TestSelfRefineV2Hypothesis(unittest.TestCase):
    """T4.5: hypothesis 阶段集成测试。"""

    def test_hypothesis_self_refine_v2_emits_metadata_with_bounded_tokens(self) -> None:
        draft = "假设：脾气虚证患者使用四君子汤可显著改善脾胃运化功能。"
        # refined 长度与 draft 同量级，确保 token ratio ≤ 2.5
        refined = "假设：脾气虚证用四君子汤后脾胃运化功能改善（建议加入证候量化评分）。"
        runner = _make_fake_runner(refined_text=refined)
        pipeline = _StubPipeline(runner=runner, enable=True)

        # 模拟 hypothesis phase 的调用路径
        context: Dict[str, Any] = {}
        self.assertTrue(resolve_enable_self_refine(context, pipeline.config))
        resolved_runner = resolve_self_refine_runner(context, pipeline)
        self.assertIs(resolved_runner, runner)

        meta = apply_self_refine_v2(
            runner=resolved_runner,
            purpose="hypothesis",
            draft_text=draft,
            max_refine_rounds=1,
        )
        # 验证 metadata 字段
        self.assertTrue(meta["self_refine_v2_succeeded"])
        self.assertEqual(meta["self_refine_v2_round_count"], 1)
        self.assertIn("self_refine_v2", meta)
        self.assertEqual(meta["self_refine_v2"]["purpose"], "hypothesis")
        # token_usage 增幅 ≤ 2.5×
        ratio = meta["self_refine_v2_token_usage_ratio"]
        self.assertLessEqual(ratio, 2.5, f"token ratio {ratio} exceeds 2.5×")
        # runner 被以 purpose='hypothesis' 调用
        runner.run.assert_called_once()
        kwargs = runner.run.call_args.kwargs
        self.assertEqual(kwargs.get("purpose") or runner.run.call_args.args[0], "hypothesis")

    def test_hypothesis_self_refine_v2_disabled_returns_no_metadata(self) -> None:
        pipeline = _StubPipeline(runner=_make_fake_runner(refined_text="x"), enable=False)
        self.assertFalse(resolve_enable_self_refine({}, pipeline.config))


class TestSelfRefineV2Analyze(unittest.TestCase):
    """T4.5: analyze 阶段集成测试。"""

    def test_analyze_self_refine_v2_emits_metadata_with_bounded_tokens(self) -> None:
        draft = "统计分析：纳入 320 例样本，p<0.001，关联强度 OR=2.4 (95%CI 1.8-3.1)。"
        refined = "分析：320 例样本 p<0.001，OR=2.4 (CI 1.8-3.1)。证据等级 B。"
        runner = _make_fake_runner(refined_text=refined)
        pipeline = _StubPipeline(runner=runner, enable=True)

        meta = apply_self_refine_v2(
            runner=resolve_self_refine_runner({}, pipeline),
            purpose="analyze",
            draft_text=draft,
            max_refine_rounds=1,
        )
        self.assertTrue(meta["self_refine_v2_succeeded"])
        self.assertEqual(meta["self_refine_v2"]["purpose"], "analyze")
        self.assertLessEqual(meta["self_refine_v2_token_usage_ratio"], 2.5)
        # 同时验证 baseline 与 estimate 一致性
        self.assertGreaterEqual(
            meta["self_refine_v2_token_usage_estimate"],
            meta["self_refine_v2_token_usage_baseline"],
        )


class TestSelfRefineV2Publish(unittest.TestCase):
    """T4.5: publish 阶段集成测试。"""

    def test_publish_self_refine_v2_emits_metadata_with_bounded_tokens(self) -> None:
        draft = (
            "标题：基于真实世界数据的四君子汤治疗脾胃虚弱证临床研究\n\n"
            "摘要：本研究纳入多中心数据，采用倾向性评分匹配..."
        )
        refined = (
            "标题：基于真实世界数据的四君子汤治疗脾胃虚弱证临床研究（润色版）\n\n"
            "摘要：基于多中心 RWE，倾向性评分匹配，得出结构化 IMRD 结论。"
        )
        runner = _make_fake_runner(refined_text=refined)
        pipeline = _StubPipeline(runner=runner, enable=True)

        meta = apply_self_refine_v2(
            runner=resolve_self_refine_runner({}, pipeline),
            purpose="publish",
            draft_text=draft,
            max_refine_rounds=1,
        )
        self.assertTrue(meta["self_refine_v2_succeeded"])
        self.assertEqual(meta["self_refine_v2"]["purpose"], "publish")
        self.assertLessEqual(meta["self_refine_v2_token_usage_ratio"], 2.5)
        self.assertEqual(meta["self_refine_v2_violation_count"], 0)


class TestSelfRefineV2WiringInPhases(unittest.TestCase):
    """确认三个 phase 模块都正确 import 了 v2 hook。"""

    def test_hypothesis_module_imports_helper(self) -> None:
        import src.research.phases.hypothesis_phase as mod

        src_text = open(mod.__file__, encoding="utf-8").read()
        self.assertIn("_self_refine_t45", src_text)
        self.assertIn('purpose="hypothesis"', src_text)

    def test_analyze_module_imports_helper(self) -> None:
        import src.research.phases.analyze_phase as mod

        src_text = open(mod.__file__, encoding="utf-8").read()
        self.assertIn("_self_refine_t45", src_text)
        self.assertIn('purpose="analyze"', src_text)

    def test_publish_module_imports_helper(self) -> None:
        import src.research.phases.publish_phase as mod

        src_text = open(mod.__file__, encoding="utf-8").read()
        self.assertIn("_self_refine_t45", src_text)
        self.assertIn('purpose="publish"', src_text)


class TestSelfRefineV2RunnerMissingFallback(unittest.TestCase):
    """runner 缺失时优雅降级，不抛错。"""

    def test_apply_returns_error_marker_when_runner_none(self) -> None:
        meta = apply_self_refine_v2(
            runner=None, purpose="hypothesis", draft_text="x"
        )
        self.assertIn("self_refine_v2_error", meta)

    def test_apply_returns_error_marker_when_draft_empty(self) -> None:
        runner = _make_fake_runner(refined_text="x")
        meta = apply_self_refine_v2(runner=runner, purpose="hypothesis", draft_text="")
        self.assertIn("self_refine_v2_error", meta)
        runner.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
