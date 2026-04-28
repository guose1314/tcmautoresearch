"""T4.3: SelfRefineRunner 单测（fake LLMService 跑 1 轮迭代）。

验收门：critique 提到的字段在 refine 输出里被覆盖。
"""

from __future__ import annotations

import json
import unittest

from src.infra import prompt_registry
from src.llm.self_refine_runner import SelfRefineRunner


class _FakeLLM:
    """按调用顺序返回预置响应；同时校验拿到的是 self_refine.* 模板。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []  # (prompt, system_prompt)

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        self.calls.append((prompt, system_prompt))
        if not self._responses:
            raise AssertionError("FakeLLM exhausted")
        return self._responses.pop(0)


def _disable_layered_cache():
    """patch get_layered_task_cache → no-op，避免缓存命中干扰测试。"""

    class _NullCache:
        def get_text(self, *a, **kw):
            return None

        def put_text(self, *a, **kw):
            return None

    return _NullCache()


class TestSelfRefineRunner(unittest.TestCase):
    def setUp(self) -> None:
        # 替换 layered cache 单例
        self._orig_cache = prompt_registry.get_layered_task_cache
        prompt_registry.get_layered_task_cache = lambda: _disable_layered_cache()

    def tearDown(self) -> None:
        prompt_registry.get_layered_task_cache = self._orig_cache

    def test_one_round_refine_overrides_critiqued_field(self) -> None:
        # round 0:
        #   draft 输出："标题: 初稿，剂量: 未填"
        #   critique 输出 issues = [{"field": "剂量", "issue": "缺失"}]
        #   refine 输出："标题: 初稿，剂量: 6克 (修订)"
        critique_issues = [
            {"field": "剂量", "issue": "缺失剂量信息", "severity": "high"}
        ]
        fake = _FakeLLM(
            responses=[
                "标题: 初稿，剂量: 未填",
                json.dumps(critique_issues, ensure_ascii=False),
                "标题: 初稿，剂量: 6克 (已根据评审补充)",
            ]
        )
        runner = SelfRefineRunner(
            llm_service=fake,
            prompt_registry=prompt_registry,
            guard=None,  # 本测专注 refine 流程
        )
        result = runner.run(
            purpose="hypothesis_review",
            inputs={
                "task_description": "完善方剂建议",
                "input_payload": "脾气虚证 + 四君子汤",
            },
            max_refine_rounds=1,
        )

        # 三次调用：draft / critique / refine
        self.assertEqual(len(fake.calls), 3)
        # critique prompt 中应嵌入 draft
        critique_prompt = fake.calls[1][0]
        self.assertIn("初稿", critique_prompt)
        # refine prompt 中应嵌入 issues JSON
        refine_prompt = fake.calls[2][0]
        self.assertIn("剂量", refine_prompt)
        self.assertIn("缺失剂量信息", refine_prompt)

        # 验收门 1：1 轮迭代
        self.assertEqual(len(result.rounds), 1)
        rnd = result.rounds[0]
        self.assertEqual(rnd.round_index, 0)
        self.assertEqual(len(rnd.issues), 1)
        self.assertEqual(rnd.issues[0]["field"], "剂量")

        # 验收门 2：critique 提到的"剂量"字段在 refine 输出里被覆盖
        self.assertIn("剂量: 6克", result.final_output)
        self.assertNotIn("剂量: 未填", result.final_output)

        # prompt_version + schema_version 落到 feedback 条目
        self.assertEqual(len(result.feedback_records), 1)
        record = result.feedback_records[0]
        self.assertEqual(record["source_phase"], "hypothesis_review")
        self.assertEqual(record["feedback_scope"], "self_refine")
        self.assertIn("self_refine.draft", record["prompt_versions"])
        self.assertIn("self_refine.critique", record["prompt_versions"])
        self.assertIn("self_refine.refine", record["prompt_versions"])
        for entry in record["prompt_versions"].values():
            self.assertIn("prompt_version", entry)
            self.assertIn("schema_version", entry)

    def test_zero_rounds_returns_draft_only(self) -> None:
        fake = _FakeLLM(responses=["纯初稿内容"])
        runner = SelfRefineRunner(fake, prompt_registry)
        result = runner.run(
            purpose="any_purpose",
            inputs={"task_description": "x", "input_payload": "y"},
            max_refine_rounds=0,
        )
        self.assertEqual(result.final_output, "纯初稿内容")
        self.assertEqual(result.rounds, [])
        self.assertEqual(result.feedback_records, [])

    def test_feedback_sink_invoked_per_round(self) -> None:
        captured = []
        fake = _FakeLLM(
            responses=[
                "draft v1",
                "[]",  # 无 issues
                "refined v1",
            ]
        )
        runner = SelfRefineRunner(
            fake,
            prompt_registry,
            feedback_sink=lambda rec: captured.append(rec),
        )
        runner.run(
            purpose="x",
            inputs={"task_description": "t", "input_payload": "p"},
            max_refine_rounds=1,
        )
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["issues_count"], 0)

    def test_constitutional_critical_marks_failure_and_stops(self) -> None:
        from src.llm.constitutional_guard import ConstitutionalGuard, ConstitutionalRule

        guard = ConstitutionalGuard(
            rules=[
                ConstitutionalRule(
                    id="TEST.critical",
                    severity="critical",
                    pattern_type="regex",
                    target="answer",
                    body="forbidden",
                    message="bad",
                )
            ]
        )
        fake = _FakeLLM(
            responses=[
                "draft ok",
                "[]",
                "this is forbidden output",  # refine 触发 critical
                # 第二轮不应执行
            ]
        )
        runner = SelfRefineRunner(fake, prompt_registry, guard=guard)
        result = runner.run(
            purpose="x",
            inputs={"task_description": "t", "input_payload": "p"},
            max_refine_rounds=2,
        )
        self.assertFalse(result.succeeded)
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(len(fake.calls), 3)  # 不再走第二轮
        self.assertTrue(
            any(v["rule_id"] == "TEST.critical" for v in result.last_violations)
        )

    def test_purpose_override_falls_back_to_self_refine(self) -> None:
        # 未注册 myproj.draft → 应回退 self_refine.draft
        fake = _FakeLLM(responses=["draft"])
        runner = SelfRefineRunner(fake, prompt_registry)
        runner.run(
            purpose="myproj_nonexistent",
            inputs={"task_description": "t", "input_payload": "p"},
            max_refine_rounds=0,
        )
        # 没抛 KeyError 即视为通过
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
