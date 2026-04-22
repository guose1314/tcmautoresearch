"""Phase K / K-2 tests: tcm_reasoning contract + 5 rules + run_tcm_reasoning."""

from __future__ import annotations

import unittest

from src.research.tcm_reasoning import (
    DEFAULT_RULE_NAMES,
    PATTERN_FANGZHENG_DUIYING,
    PATTERN_JUNCHEN_ZUOSHI,
    PATTERN_SANYIN_ZHIYI,
    PATTERN_TONGBING_YIZHI,
    PATTERN_YIBING_TONGZHI,
    REASONING_PATTERNS,
    TCM_REASONING_CONTRACT_VERSION,
    TCMReasoningPremise,
    TCMReasoningRule,
    TCMReasoningStep,
    TCMReasoningTrace,
    apply_rule,
    build_default_rules,
    build_tcm_reasoning_metadata,
    rule_fangzheng_duiying,
    rule_junchen_zuoshi,
    rule_sanyin_zhiyi,
    rule_tongbing_yizhi,
    rule_yibing_tongzhi,
    run_tcm_reasoning,
)


def _premise(kind: str, canonical: str, label: str = "") -> TCMReasoningPremise:
    return TCMReasoningPremise(premise_kind=kind, canonical=canonical, label=label or canonical)


class TestContractBasics(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual(TCM_REASONING_CONTRACT_VERSION, "tcm-reasoning-trace-v1")

    def test_five_patterns_registered(self):
        self.assertEqual(len(REASONING_PATTERNS), 5)
        for pat in (
            PATTERN_TONGBING_YIZHI,
            PATTERN_YIBING_TONGZHI,
            PATTERN_SANYIN_ZHIYI,
            PATTERN_FANGZHENG_DUIYING,
            PATTERN_JUNCHEN_ZUOSHI,
        ):
            self.assertIn(pat, REASONING_PATTERNS)

    def test_default_rule_names(self):
        self.assertEqual(len(DEFAULT_RULE_NAMES), 5)

    def test_premise_round_trip(self):
        p = _premise("symptom", "头痛", "头疼")
        self.assertEqual(TCMReasoningPremise.from_dict(p.to_dict()), p)

    def test_step_round_trip(self):
        step = TCMReasoningStep(
            rule_id="rule_x",
            pattern=PATTERN_FANGZHENG_DUIYING,
            premises=[_premise("formula", "桂枝汤")],
            conclusion="conclusion",
            confidence=0.5,
            rationale="r",
        )
        self.assertEqual(TCMReasoningStep.from_dict(step.to_dict()), step)

    def test_trace_round_trip_with_contract_version(self):
        trace = TCMReasoningTrace(
            seed="t",
            premises=[_premise("herb", "麻黄")],
            steps=[],
            overall_confidence=0.0,
            pattern_coverage=[],
            notes="n",
        )
        d = trace.to_dict()
        self.assertEqual(d["contract_version"], TCM_REASONING_CONTRACT_VERSION)


class TestRuleTongBingYiZhi(unittest.TestCase):
    def test_triggers_when_one_symptom_two_syndromes(self):
        premises = [
            _premise("symptom", "咳嗽"),
            _premise("syndrome", "风寒袭肺"),
            _premise("syndrome", "肺阴虚"),
        ]
        step = rule_tongbing_yizhi(premises)
        self.assertIsNotNone(step)
        assert step is not None
        self.assertEqual(step.pattern, PATTERN_TONGBING_YIZHI)
        self.assertGreater(step.confidence, 0.5)

    def test_returns_none_when_only_one_syndrome(self):
        premises = [_premise("symptom", "咳嗽"), _premise("syndrome", "风寒袭肺")]
        self.assertIsNone(rule_tongbing_yizhi(premises))


class TestRuleYiBingTongZhi(unittest.TestCase):
    def test_triggers_when_two_symptoms_one_syndrome(self):
        premises = [
            _premise("syndrome", "脾胃虚寒"),
            _premise("symptom", "胃痛"),
            _premise("symptom", "腹泻"),
        ]
        step = rule_yibing_tongzhi(premises)
        self.assertIsNotNone(step)
        assert step is not None
        self.assertEqual(step.pattern, PATTERN_YIBING_TONGZHI)

    def test_returns_none_without_syndromes(self):
        self.assertIsNone(rule_yibing_tongzhi([_premise("symptom", "咳嗽")]))


class TestRuleSanYinZhiYi(unittest.TestCase):
    def test_triggers_when_context_contains_time_factor(self):
        premises = [_premise("context", "夏季高温")]
        step = rule_sanyin_zhiyi(premises)
        self.assertIsNotNone(step)
        assert step is not None
        self.assertEqual(step.pattern, PATTERN_SANYIN_ZHIYI)

    def test_returns_none_when_no_context(self):
        self.assertIsNone(rule_sanyin_zhiyi([]))

    def test_returns_none_when_context_irrelevant(self):
        self.assertIsNone(rule_sanyin_zhiyi([_premise("context", "xyz123")]))


class TestRuleFangZhengDuiYing(unittest.TestCase):
    def test_triggers_with_formula_and_syndrome(self):
        step = rule_fangzheng_duiying([
            _premise("formula", "桂枝汤"),
            _premise("syndrome", "太阳中风"),
        ])
        self.assertIsNotNone(step)
        assert step is not None
        self.assertEqual(step.pattern, PATTERN_FANGZHENG_DUIYING)
        self.assertGreaterEqual(step.confidence, 0.7)

    def test_returns_none_without_formula(self):
        self.assertIsNone(rule_fangzheng_duiying([_premise("syndrome", "x")]))


class TestRuleJunChenZuoShi(unittest.TestCase):
    def test_triggers_with_three_or_more_herbs(self):
        step = rule_junchen_zuoshi([
            _premise("herb", "桂枝"),
            _premise("herb", "白芍"),
            _premise("herb", "甘草"),
        ])
        self.assertIsNotNone(step)
        assert step is not None
        self.assertEqual(step.pattern, PATTERN_JUNCHEN_ZUOSHI)

    def test_returns_none_below_threshold(self):
        self.assertIsNone(rule_junchen_zuoshi([
            _premise("herb", "桂枝"),
            _premise("herb", "白芍"),
        ]))


class TestApplyRuleSafety(unittest.TestCase):
    def test_apply_rule_swallows_exception(self):
        def boom(_premises):  # type: ignore[no-untyped-def]
            raise RuntimeError("kaboom")

        rule = TCMReasoningRule("boom", PATTERN_TONGBING_YIZHI, boom)
        self.assertIsNone(apply_rule(rule, []))

    def test_apply_rule_rejects_unknown_pattern(self):
        def returns_bad(_premises):  # type: ignore[no-untyped-def]
            return TCMReasoningStep(rule_id="x", pattern="UNKNOWN_PATTERN")

        rule = TCMReasoningRule("x", "UNKNOWN_PATTERN", returns_bad)
        self.assertIsNone(apply_rule(rule, []))


class TestRunTcmReasoning(unittest.TestCase):
    def test_run_with_no_matches_yields_empty_trace(self):
        trace = run_tcm_reasoning([], seed="empty")
        self.assertEqual(trace.seed, "empty")
        self.assertEqual(trace.steps, [])
        self.assertEqual(trace.overall_confidence, 0.0)

    def test_run_with_full_premises_covers_all_five_patterns(self):
        premises = [
            _premise("symptom", "咳嗽"),
            _premise("symptom", "腹泻"),
            _premise("syndrome", "风寒袭肺"),
            _premise("syndrome", "脾胃虚寒"),
            _premise("formula", "桂枝汤"),
            _premise("herb", "桂枝"),
            _premise("herb", "白芍"),
            _premise("herb", "甘草"),
            _premise("context", "夏季"),
        ]
        trace = run_tcm_reasoning(premises, seed="full")
        self.assertEqual(len(trace.pattern_coverage), 5)
        self.assertEqual(len(trace.steps), 5)
        self.assertGreater(trace.overall_confidence, 0.0)

    def test_run_uses_default_rules_when_none_provided(self):
        rules = build_default_rules()
        self.assertEqual([r.rule_id for r in rules], list(DEFAULT_RULE_NAMES))


class TestBuildMetadata(unittest.TestCase):
    def test_metadata_keys_present(self):
        trace = TCMReasoningTrace(seed="s", premises=[_premise("herb", "h")], steps=[])
        meta = build_tcm_reasoning_metadata(trace)
        for key in (
            "tcm_reasoning_step_count",
            "tcm_reasoning_pattern_coverage",
            "tcm_reasoning_pattern_count",
            "tcm_reasoning_overall_confidence",
            "tcm_reasoning_pattern_distribution",
            "tcm_reasoning_premise_count",
            "tcm_reasoning_notes",
            "tcm_reasoning_contract_version",
        ):
            self.assertIn(key, meta)
        self.assertEqual(meta["tcm_reasoning_contract_version"], TCM_REASONING_CONTRACT_VERSION)
        self.assertEqual(meta["tcm_reasoning_premise_count"], 1)


if __name__ == "__main__":
    unittest.main()
