"""Token budget policy focused regression tests."""

from __future__ import annotations

import unittest

from src.infra.token_budget_policy import (
    apply_token_budget_to_prompt,
    estimate_text_tokens,
    resolve_token_budget,
)


class TestTokenBudgetResolution(unittest.TestCase):
    def test_task_budget_takes_priority(self):
        resolution = resolve_token_budget(
            task="hypothesis_generation",
            purpose="assistant",
            settings={
                "enabled": True,
                "default_input_tokens": 1024,
                "min_input_tokens": 128,
                "max_context_tokens": 4096,
                "reserve_output_tokens": 512,
                "purpose_input_budgets": {"assistant": 900},
                "task_input_budgets": {"hypothesis_generation": 640},
            },
        )
        self.assertEqual(resolution.input_budget_tokens, 640)
        self.assertEqual(resolution.source, "task")

    def test_context_window_hard_cap_is_respected(self):
        resolution = resolve_token_budget(
            purpose="paper_plugin",
            max_output_tokens=768,
            settings={
                "enabled": True,
                "default_input_tokens": 1600,
                "min_input_tokens": 128,
                "max_context_tokens": 1024,
                "reserve_output_tokens": 512,
                "purpose_input_budgets": {"paper_plugin": 900},
                "task_input_budgets": {},
            },
        )
        self.assertEqual(resolution.hard_cap_tokens, 256)
        self.assertEqual(resolution.input_budget_tokens, 256)


class TestTokenBudgetApplication(unittest.TestCase):
    def test_budget_application_preserves_suffix_prompt(self):
        body = "证据片段：" + ("黄芪补气改善疲劳。" * 400)
        suffix = "JSON Schema:\n{\"type\": \"object\", \"required\": [\"summary\"]}"
        result = apply_token_budget_to_prompt(
            body,
            system_prompt="你是一位中医药科研分析助手。",
            task="structured_summary",
            suffix_prompt=suffix,
            settings={
                "enabled": True,
                "default_input_tokens": 240,
                "min_input_tokens": 128,
                "max_context_tokens": 256,
                "reserve_output_tokens": 64,
                "keep_head_ratio": 0.7,
                "keep_tail_ratio": 0.3,
                "trim_notice": "\n\n[..trimmed..]\n\n",
                "purpose_input_budgets": {},
                "task_input_budgets": {"structured_summary": 180},
            },
        )

        self.assertTrue(result.trimmed)
        self.assertIn("[..trimmed..]", result.user_prompt)
        self.assertTrue(result.user_prompt.endswith(suffix))
        self.assertLess(result.total_input_tokens_after, result.total_input_tokens_before)

    def test_budget_application_can_be_disabled(self):
        prompt = "A" * 4000
        result = apply_token_budget_to_prompt(
            prompt,
            settings={
                "enabled": False,
                "default_input_tokens": 256,
                "min_input_tokens": 128,
                "max_context_tokens": 256,
                "reserve_output_tokens": 64,
                "purpose_input_budgets": {},
                "task_input_budgets": {},
            },
        )
        self.assertFalse(result.trimmed)
        self.assertEqual(result.user_prompt, prompt)

    def test_token_estimator_handles_mixed_language(self):
        count = estimate_text_tokens("黄芪 improves qi and energy.")
        self.assertGreater(count, 0)


class TestPhaseI3BudgetHitTelemetry(unittest.TestCase):
    """Phase I-3 — budget 命中评测：判断 resolve 输出是否达到了请求预算。"""

    def test_purpose_budget_within_hard_cap_is_a_hit(self):
        resolution = resolve_token_budget(
            purpose="paper_plugin",
            settings={
                "enabled": True,
                "default_input_tokens": 1024,
                "min_input_tokens": 128,
                "max_context_tokens": 4096,
                "reserve_output_tokens": 512,
                "purpose_input_budgets": {"paper_plugin": 1500},
                "task_input_budgets": {},
            },
        )
        # 请求 1500 < hard cap 3584 → 完整命中
        self.assertEqual(resolution.input_budget_tokens, 1500)
        self.assertEqual(resolution.source, "purpose")
        self.assertGreaterEqual(resolution.hard_cap_tokens, resolution.input_budget_tokens)

    def test_budget_capped_by_context_window_is_a_miss(self):
        resolution = resolve_token_budget(
            task="paper_full_section",
            settings={
                "enabled": True,
                "default_input_tokens": 1024,
                "min_input_tokens": 128,
                "max_context_tokens": 1024,
                "reserve_output_tokens": 512,
                "purpose_input_budgets": {},
                "task_input_budgets": {"paper_full_section": 2048},
            },
        )
        # 请求 2048 但 hard cap 仅 512 → budget miss
        self.assertEqual(resolution.hard_cap_tokens, 512)
        self.assertEqual(resolution.input_budget_tokens, 512)
        self.assertEqual(resolution.source, "task")


if __name__ == "__main__":
    unittest.main()