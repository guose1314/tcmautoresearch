"""compute_tier_router 单元测试。"""

import unittest

from src.research.compute_tier_router import (
    ComputeTier,
    ComputeTierRouter,
    TierDecision,
)


class TestTierDecision(unittest.TestCase):
    """TierDecision 数据结构测试。"""

    def test_should_use_llm_true_for_l3(self):
        d = TierDecision(tier=ComputeTier.L3_LLM, reason="test", evidence_scores={})
        self.assertTrue(d.should_use_llm)

    def test_should_use_llm_false_for_l1(self):
        d = TierDecision(tier=ComputeTier.L1_RULES, reason="test", evidence_scores={})
        self.assertFalse(d.should_use_llm)

    def test_should_use_llm_false_for_l2(self):
        d = TierDecision(tier=ComputeTier.L2_RETRIEVAL, reason="test", evidence_scores={})
        self.assertFalse(d.should_use_llm)

    def test_to_dict(self):
        d = TierDecision(tier=ComputeTier.L2_RETRIEVAL, reason="sufficient", evidence_scores={"x": 0.5})
        result = d.to_dict()
        self.assertEqual(result["tier"], "L2_RETRIEVAL")
        self.assertEqual(result["tier_level"], 2)
        self.assertFalse(result["should_use_llm"])
        self.assertEqual(result["evidence_scores"], {"x": 0.5})


class TestComputeTierRouterL1(unittest.TestCase):
    """L1 (规则层) 充分性判断。"""

    def test_has_rule_result_triggers_l1(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {"has_rule_result": True})
        self.assertEqual(decision.tier, ComputeTier.L1_RULES)
        self.assertFalse(decision.should_use_llm)

    def test_high_rule_confidence_with_entities_triggers_l1(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {
            "entity_count": 5,
            "relationship_count": 3,
            "rule_confidence": 0.7,
        })
        self.assertEqual(decision.tier, ComputeTier.L1_RULES)

    def test_low_rule_confidence_does_not_trigger_l1(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {
            "entity_count": 1,
            "relationship_count": 0,
            "rule_confidence": 0.2,
        })
        self.assertNotEqual(decision.tier, ComputeTier.L1_RULES)


class TestComputeTierRouterL2(unittest.TestCase):
    """L2 (检索层) 充分性判断。"""

    def test_sufficient_retrieval_triggers_l2(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {
            "retrieval_hits": 5,
            "evidence_items": 8,
        })
        self.assertEqual(decision.tier, ComputeTier.L2_RETRIEVAL)

    def test_high_kg_coverage_triggers_l2(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {
            "kg_coverage": 0.8,
        })
        self.assertEqual(decision.tier, ComputeTier.L2_RETRIEVAL)

    def test_partial_retrieval_not_enough(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {
            "retrieval_hits": 1,
            "evidence_items": 2,
        })
        self.assertEqual(decision.tier, ComputeTier.L3_LLM)


class TestComputeTierRouterL3(unittest.TestCase):
    """L3 (LLM) 触发条件。"""

    def test_no_evidence_triggers_l3(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {})
        self.assertEqual(decision.tier, ComputeTier.L3_LLM)
        self.assertTrue(decision.should_use_llm)

    def test_translation_always_l3(self):
        router = ComputeTierRouter()
        decision = router.decide("translation", {
            "entity_count": 10,
            "retrieval_hits": 10,
            "evidence_items": 10,
        })
        self.assertEqual(decision.tier, ComputeTier.L3_LLM)


class TestComputeTierRouterForceAndConfig(unittest.TestCase):
    """强制覆盖与配置。"""

    def test_force_tier_overrides(self):
        router = ComputeTierRouter()
        decision = router.decide("hypothesis", {}, force_tier="L1")
        self.assertEqual(decision.tier, ComputeTier.L1_RULES)
        self.assertIn("forced", decision.reason)

    def test_config_force_tier(self):
        router = ComputeTierRouter({"compute_tier_router": {"force_tier": "L2"}})
        decision = router.decide("hypothesis", {"entity_count": 0})
        self.assertEqual(decision.tier, ComputeTier.L2_RETRIEVAL)

    def test_disabled_router_always_l3(self):
        router = ComputeTierRouter({"compute_tier_router": {"enabled": False}})
        decision = router.decide("hypothesis", {"has_rule_result": True})
        self.assertEqual(decision.tier, ComputeTier.L3_LLM)
        self.assertEqual(decision.reason, "router_disabled")

    def test_custom_thresholds(self):
        # Lower thresholds so fewer evidence items suffice for L2
        config = {"compute_tier_router": {
            "enabled": True,
            "thresholds": {"hypothesis": {"l2_retrieval_hits": 1, "l2_evidence_items": 1}},
        }}
        router = ComputeTierRouter(config)
        decision = router.decide("hypothesis", {"retrieval_hits": 1, "evidence_items": 1})
        self.assertEqual(decision.tier, ComputeTier.L2_RETRIEVAL)


class TestComputeTierRouterTaskTypes(unittest.TestCase):
    """各任务类型默认阈值差异化测试。"""

    def test_reflection_lower_evidence_bar(self):
        router = ComputeTierRouter()
        # reflection has lower thresholds: l2_evidence_items=3, l2_retrieval_hits=2
        decision = router.decide("reflection", {"retrieval_hits": 2, "evidence_items": 3})
        self.assertEqual(decision.tier, ComputeTier.L2_RETRIEVAL)

    def test_gap_analysis_higher_bar(self):
        router = ComputeTierRouter()
        # gap_analysis has higher thresholds
        decision = router.decide("gap_analysis", {"retrieval_hits": 2, "evidence_items": 3})
        self.assertEqual(decision.tier, ComputeTier.L3_LLM)

    def test_unknown_task_uses_fallback(self):
        router = ComputeTierRouter()
        decision = router.decide("some_unknown_task", {"has_rule_result": True})
        self.assertEqual(decision.tier, ComputeTier.L1_RULES)


if __name__ == "__main__":
    unittest.main()
