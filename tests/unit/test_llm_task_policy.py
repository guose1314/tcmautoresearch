"""tests/unit/test_llm_task_policy.py — LLM 任务适配性策略单元测试。"""

import unittest


class TestSuitabilityTierEnum(unittest.TestCase):
    """SuitabilityTier 枚举完整性。"""

    def test_three_tiers_exist(self):
        from src.infra.llm_task_policy import SuitabilityTier
        self.assertEqual(
            {t.value for t in SuitabilityTier},
            {"suitable", "cautious", "unsuitable_solo"},
        )


class TestTaskPolicy(unittest.TestCase):
    """TASK_POLICY 权威清单结构。"""

    def test_non_empty(self):
        from src.infra.llm_task_policy import TASK_POLICY
        self.assertGreater(len(TASK_POLICY), 10)

    def test_every_entry_has_required_fields(self):
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier
        for key, spec in TASK_POLICY.items():
            self.assertIsInstance(spec.tier, SuitabilityTier, f"{key} tier 类型错误")
            self.assertTrue(len(spec.guidance) > 0, f"{key} guidance 为空")

    def test_at_least_one_per_tier(self):
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier
        tiers_present = {spec.tier for spec in TASK_POLICY.values()}
        for t in SuitabilityTier:
            self.assertIn(t, tiers_present, f"TASK_POLICY 缺少 {t.value} 层级")

    def test_suitable_tasks_match_audit(self):
        """审计文档 §10.1 列出的适合任务都应为 suitable。"""
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier
        suitable_keys = [
            "hypothesis_generation", "question_rewrite", "terminology_explanation",
            "structured_summary", "discussion_draft", "reflect_diagnosis",
        ]
        for key in suitable_keys:
            self.assertIn(key, TASK_POLICY, f"缺少适合任务: {key}")
            self.assertEqual(TASK_POLICY[key].tier, SuitabilityTier.SUITABLE,
                             f"{key} 应为 suitable")

    def test_cautious_tasks_match_audit(self):
        """审计文档 §10.1 列出的谨慎使用任务都应为 cautious。"""
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier
        cautious_keys = ["long_form_generation", "graph_reasoning", "unsupported_conclusion"]
        for key in cautious_keys:
            self.assertIn(key, TASK_POLICY, f"缺少谨慎任务: {key}")
            self.assertEqual(TASK_POLICY[key].tier, SuitabilityTier.CAUTIOUS,
                             f"{key} 应为 cautious")

    def test_unsuitable_tasks_match_audit(self):
        """审计文档 §10.1 列出的不建议任务都应为 unsuitable_solo。"""
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier
        unsuitable_keys = ["large_evidence_synthesis", "end_to_end_research_judgment"]
        for key in unsuitable_keys:
            self.assertIn(key, TASK_POLICY, f"缺少不建议任务: {key}")
            self.assertEqual(TASK_POLICY[key].tier, SuitabilityTier.UNSUITABLE_SOLO,
                             f"{key} 应为 unsuitable_solo")


class TestEvaluateTask(unittest.TestCase):
    """evaluate_task() 评估逻辑。"""

    def test_known_task_returns_correct_tier(self):
        from src.infra.llm_task_policy import SuitabilityTier, evaluate_task
        v = evaluate_task("hypothesis_generation")
        self.assertEqual(v.tier, SuitabilityTier.SUITABLE)
        self.assertEqual(v.task, "hypothesis_generation")

    def test_unknown_task_defaults_to_cautious(self):
        from src.infra.llm_task_policy import SuitabilityTier, evaluate_task
        v = evaluate_task("totally_unknown_task_xyz")
        self.assertEqual(v.tier, SuitabilityTier.CAUTIOUS)

    def test_purpose_mapped_to_task(self):
        from src.infra.llm_task_policy import SuitabilityTier, evaluate_task
        v = evaluate_task("translation")  # purpose → task mapping
        self.assertEqual(v.tier, SuitabilityTier.SUITABLE)

    def test_verdict_has_guidance(self):
        from src.infra.llm_task_policy import evaluate_task
        v = evaluate_task("large_evidence_synthesis")
        self.assertTrue(len(v.guidance) > 0)

    def test_verdict_has_recommendations(self):
        from src.infra.llm_task_policy import evaluate_task
        v = evaluate_task("hypothesis_generation")
        self.assertIsNotNone(v.recommended_max_tokens)
        self.assertIsNotNone(v.recommended_temperature)


class TestEvaluatePurpose(unittest.TestCase):
    """evaluate_purpose() purpose → task 映射。"""

    def test_default_purpose(self):
        from src.infra.llm_task_policy import SuitabilityTier, evaluate_purpose
        v = evaluate_purpose("default")
        self.assertEqual(v.tier, SuitabilityTier.SUITABLE)

    def test_paper_plugin_purpose(self):
        from src.infra.llm_task_policy import SuitabilityTier, evaluate_purpose
        v = evaluate_purpose("paper_plugin")
        self.assertEqual(v.tier, SuitabilityTier.CAUTIOUS)

    def test_evidence_synthesis_purpose(self):
        from src.infra.llm_task_policy import SuitabilityTier, evaluate_purpose
        v = evaluate_purpose("evidence_synthesis")
        self.assertEqual(v.tier, SuitabilityTier.UNSUITABLE_SOLO)


class TestCheckSuitability(unittest.TestCase):
    """check_suitability() 日志发射。"""

    def test_suitable_no_warning(self):
        """suitable 任务不应触发 WARNING。"""
        import logging

        from src.infra.llm_task_policy import check_suitability
        with self.assertLogs("src.infra.llm_task_policy", level="DEBUG") as cm:
            logging.getLogger("src.infra.llm_task_policy").debug("trigger")
            check_suitability("default")
        warnings = [r for r in cm.output if "WARNING" in r]
        self.assertEqual(warnings, [])

    def test_unsuitable_emits_warning(self):
        """unsuitable_solo 应触发 WARNING 日志。"""
        import logging

        from src.infra.llm_task_policy import check_suitability
        with self.assertLogs("src.infra.llm_task_policy", level="WARNING") as cm:
            check_suitability("evidence_synthesis")
        self.assertTrue(any("unsuitable_solo" in r for r in cm.output))


class TestPolicySummary(unittest.TestCase):
    """get_policy_summary() 统计。"""

    def test_summary_total(self):
        from src.infra.llm_task_policy import TASK_POLICY, get_policy_summary
        s = get_policy_summary()
        self.assertEqual(s["total_tasks"], len(TASK_POLICY))

    def test_summary_counts_sum(self):
        from src.infra.llm_task_policy import get_policy_summary
        s = get_policy_summary()
        self.assertEqual(sum(s["counts"].values()), s["total_tasks"])


class TestPhaseI3PolicyAlignment(unittest.TestCase):
    """Phase I-3：每个 SUITABLE 任务都应该有可执行的 token / temperature 推荐。"""

    def test_suitable_tasks_have_recommendations(self):
        from src.infra.llm_task_policy import TASK_POLICY, SuitabilityTier, evaluate_task
        for task_name, spec in TASK_POLICY.items():
            if spec.tier != SuitabilityTier.SUITABLE:
                continue
            verdict = evaluate_task(task_name)
            self.assertIsNotNone(
                verdict.recommended_max_tokens,
                f"{task_name} 缺少 recommended_max_tokens",
            )
            self.assertIsNotNone(
                verdict.recommended_temperature,
                f"{task_name} 缺少 recommended_temperature",
            )


if __name__ == "__main__":
    unittest.main()
