"""T4.4: ConstitutionalGuard 三类规则覆盖。"""

from __future__ import annotations

import unittest

from src.llm.constitutional_guard import (
    ConstitutionalGuard,
    ConstitutionalRule,
    ConstitutionalViolation,
    load_default_guard,
)


class TestConstitutionalGuardThreeCategories(unittest.TestCase):
    """对接验收门：伪造剂量 / 跨证候推荐 / 未引用文献的方剂 各 1 例。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.guard = load_default_guard()

    def test_dosage_fabricated_unit_triggers_critical(self) -> None:
        output = {
            "answer": "建议每次服用 0.5 克/kg体重，每日两次。",
        }
        with self.assertRaises(ConstitutionalViolation) as ctx:
            self.guard.enforce(output)
        rule_ids = {v.rule_id for v in ctx.exception.violations}
        self.assertIn("DOSAGE.fabricated_unit", rule_ids)

    def test_cross_syndrome_recommendation_triggers_critical(self) -> None:
        output = {
            "answer": "本方无论寒热虚实皆可服用，效果显著。",
        }
        with self.assertRaises(ConstitutionalViolation) as ctx:
            self.guard.enforce(output)
        rule_ids = {v.rule_id for v in ctx.exception.violations}
        self.assertIn("SYNDROME.cross_recommendation", rule_ids)

    def test_formula_without_citation_triggers_critical(self) -> None:
        output = {
            "formula_recommendations": [
                {"name": "六味地黄丸", "indication": "肾阴虚"},
                {"name": "四物汤", "indication": "血虚证"},
            ],
        }
        with self.assertRaises(ConstitutionalViolation) as ctx:
            self.guard.enforce(output)
        rule_ids = {v.rule_id for v in ctx.exception.violations}
        self.assertIn("CITATION.formula_without_source", rule_ids)

    def test_clean_output_passes(self) -> None:
        output = {
            "answer": "建议咨询执业中医师，本方剂用于脾气虚证。",
            "formula_recommendations": [
                {
                    "name": "四君子汤",
                    "indication": "脾气虚证",
                    "citation": "《太平惠民和剂局方》",
                },
            ],
            "recommendations": ["按辨证施治原则使用"],
        }
        violations = self.guard.enforce(output)
        critical = [v for v in violations if v.severity == "critical"]
        self.assertEqual(critical, [], f"unexpected critical violations: {critical}")


class TestConstitutionalGuardCheckVsEnforce(unittest.TestCase):
    def test_check_returns_all_does_not_raise(self) -> None:
        guard = load_default_guard()
        violations = guard.check({"answer": "无论寒热虚实均可使用，剂量 2 克/kg体重。"})
        rule_ids = {v.rule_id for v in violations}
        self.assertIn("SYNDROME.cross_recommendation", rule_ids)
        self.assertIn("DOSAGE.fabricated_unit", rule_ids)

    def test_enforce_only_raises_on_critical(self) -> None:
        # 仅 medium 违规：不抛
        rules = [
            ConstitutionalRule(
                id="TEST.medium",
                severity="medium",
                pattern_type="regex",
                target="answer",
                body="forbidden",
                message="x",
            )
        ]
        guard = ConstitutionalGuard(rules=rules)
        violations = guard.enforce({"answer": "this is forbidden"})
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, "medium")


class TestConstitutionalGuardLoading(unittest.TestCase):
    def test_default_yaml_has_at_least_30_rules(self) -> None:
        guard = load_default_guard()
        self.assertGreaterEqual(len(guard.rules), 15)  # config 有 15+，宽松断言

    def test_invalid_severity_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ConstitutionalRule(
                id="X",
                severity="bogus",
                pattern_type="regex",
                target="*",
                body=".",
            )


if __name__ == "__main__":
    unittest.main()
