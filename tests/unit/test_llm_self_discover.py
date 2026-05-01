from __future__ import annotations

import json
import unittest

from src.contexts.llm_reasoning import (
    SUPPORTED_SELF_DISCOVER_TASKS,
    build_self_discover_plan,
)


class LLMReasoningSelfDiscoverTest(unittest.TestCase):
    def test_supported_task_contract_is_stable(self) -> None:
        self.assertEqual(
            SUPPORTED_SELF_DISCOVER_TASKS,
            (
                "philology_exegesis",
                "formula_lineage",
                "pathogenesis_reasoning",
                "citation_synthesis",
            ),
        )

    def test_supported_tasks_generate_distinct_step_sequences(self) -> None:
        step_sequences = {
            task_type: tuple(
                step.step_id
                for step in build_self_discover_plan(
                    "复杂中医文献研究任务",
                    {"reasoning_framework": "systematic_review"},
                    task_type,
                ).reasoning_steps
            )
            for task_type in SUPPORTED_SELF_DISCOVER_TASKS
        }

        self.assertEqual(len(step_sequences), 4)
        self.assertEqual(len(set(step_sequences.values())), 4)

    def test_philology_exegesis_plan_has_required_evidence_and_fallbacks(self) -> None:
        plan = build_self_discover_plan(
            "《伤寒论》少阳条文中某术语如何训诂？",
            {
                "entities": [{"type": "document"}, {"type": "variant"}],
                "force_reasoning_framework": "textual_criticism",
            },
            "philology_exegesis",
        )

        self.assertEqual(plan.task_type, "philology_exegesis")
        self.assertEqual(plan.framework_id, "textual_criticism")
        self.assertIn("contextual_term_disambiguation", plan.selected_modules)
        self.assertIn("term_context", plan.evidence_slots)
        self._assert_all_steps_are_auditable(plan.to_dict())
        json.dumps(plan.to_dict(), ensure_ascii=False)

    def test_formula_lineage_plan_uses_formula_framework(self) -> None:
        plan = build_self_discover_plan(
            "四物汤在《局方》和后世文献中的方药沿革如何？",
            {"entities": [{"type": "formula"}, {"type": "herb"}]},
            "formula_lineage",
        )

        payload = plan.to_dict()
        self.assertEqual(payload["task_type"], "formula_lineage")
        self.assertEqual(payload["framework_id"], "formula_compatibility")
        self.assertIn("version_lineage_mapping", payload["selected_modules"])
        self.assertIn("herb_composition", payload["evidence_slots"])
        self._assert_all_steps_are_auditable(payload)

    def test_pathogenesis_reasoning_plan_has_distinct_steps(self) -> None:
        plan = build_self_discover_plan(
            "桂枝汤方证如何体现营卫不和的病机链？",
            {"entities": [{"type": "syndrome"}, {"type": "symptom"}]},
            "pathogenesis_reasoning",
        )

        payload = plan.to_dict()
        self.assertEqual(payload["task_type"], "pathogenesis_reasoning")
        self.assertEqual(payload["framework_id"], "pathomechanism_evidence")
        self.assertIn("pathomechanism_chain_builder", payload["selected_modules"])
        self.assertIn("pathogenesis_factor", payload["evidence_slots"])
        self._assert_all_steps_are_auditable(payload)

    def test_citation_synthesis_plan_has_support_schema_hint(self) -> None:
        plan = build_self_discover_plan(
            "这段综述中的结论是否都有原文与 EvidenceClaim 支持？",
            {"entities": [{"type": "study"}, {"type": "outcome"}]},
            "citation_synthesis",
        )

        payload = plan.to_dict()
        self.assertEqual(payload["task_type"], "citation_synthesis")
        self.assertEqual(payload["framework_id"], "systematic_review")
        self.assertIn("unsupported_claim_guard", payload["selected_modules"])
        self.assertIn("support_level", payload["evidence_slots"])
        self.assertIn("required", payload["output_schema_hint"])
        self.assertIn("reasoning_trace", payload["output_schema_hint"]["required"])
        self._assert_all_steps_are_auditable(payload)

    def test_unknown_task_falls_back_to_citation_synthesis_with_warning(self) -> None:
        plan = build_self_discover_plan("未知复杂任务", {}, "unknown_task")

        self.assertEqual(plan.task_type, "citation_synthesis")
        self.assertEqual(plan.warnings, ["unsupported_task_type:unknown_task"])
        self._assert_all_steps_are_auditable(plan.to_dict())

    def _assert_all_steps_are_auditable(self, payload: dict) -> None:
        steps = payload["reasoning_steps"]
        self.assertGreaterEqual(len(steps), 3)
        for step in steps:
            self.assertTrue(step["step_id"])
            self.assertTrue(step["instruction"])
            self.assertTrue(step["required_evidence"])
            self.assertTrue(step["failure_fallback"])
            self.assertTrue(step["output_key"])


if __name__ == "__main__":
    unittest.main()
