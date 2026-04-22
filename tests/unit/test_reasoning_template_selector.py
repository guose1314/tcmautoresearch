"""reasoning_template_selector 单元测试。"""

import unittest

from src.research.reasoning_template_selector import (
    FRAMEWORK_IDS,
    ReasoningFramework,
    select_reasoning_framework,
)


class TestSelectReasoningFramework(unittest.TestCase):
    """select_reasoning_framework 核心选择逻辑。"""

    def test_returns_reasoning_framework_dataclass(self):
        result = select_reasoning_framework("研究黄芪补气机制")
        self.assertIsInstance(result, ReasoningFramework)
        self.assertIn(result.framework_id, FRAMEWORK_IDS)
        self.assertTrue(0 <= result.confidence <= 1)

    def test_formula_compatibility_selected_for_drug_pair_objective(self):
        result = select_reasoning_framework(
            "研究黄芪-人参药对的配伍协同增效机制",
            {"entities": [{"text": "黄芪", "type": "herb"}, {"text": "人参", "type": "herb"}]},
        )
        self.assertEqual(result.framework_id, "formula_compatibility")
        self.assertIn("配伍", result.hypothesis_guidance)

    def test_pathomechanism_selected_for_syndrome_research(self):
        result = select_reasoning_framework(
            "脾虚证型的辨证论治规律与病机传变研究",
            {"research_domain": "pathomechanism"},
        )
        self.assertEqual(result.framework_id, "pathomechanism_evidence")
        self.assertIn("病因病机", result.hypothesis_guidance)

    def test_textual_criticism_selected_for_philology_research(self):
        result = select_reasoning_framework(
            "《神农本草经》不同版本校勘异文考据分析",
            {"entities": [{"text": "神农本草经", "type": "document"}]},
        )
        self.assertEqual(result.framework_id, "textual_criticism")
        self.assertIn("文献学", result.hypothesis_guidance)

    def test_systematic_review_selected_for_evidence_synthesis(self):
        result = select_reasoning_framework(
            "黄芪注射液治疗慢性肾炎的系统评价与Meta分析",
        )
        self.assertEqual(result.framework_id, "systematic_review")
        self.assertIn("循证", result.hypothesis_guidance)

    def test_force_framework_overrides_auto_selection(self):
        result = select_reasoning_framework(
            "黄芪-人参药对配伍研究",
            force_framework="textual_criticism",
        )
        self.assertEqual(result.framework_id, "textual_criticism")
        self.assertEqual(result.confidence, 1.0)
        self.assertIn("forced_by_config", result.selection_reasons)

    def test_config_override_via_context(self):
        result = select_reasoning_framework(
            "任意研究目标",
            {"reasoning_framework": "pathomechanism_evidence"},
        )
        self.assertEqual(result.framework_id, "pathomechanism_evidence")
        self.assertIn("config_override", result.selection_reasons)

    def test_learning_strategy_framework_override(self):
        result = select_reasoning_framework(
            "任意研究目标",
            {"learning_strategy": {"reasoning_framework": "formula_compatibility"}},
        )
        self.assertEqual(result.framework_id, "formula_compatibility")

    def test_low_signal_defaults_to_systematic_review(self):
        result = select_reasoning_framework("无明显信号的目标")
        self.assertEqual(result.framework_id, "systematic_review")

    def test_to_dict_serializable(self):
        result = select_reasoning_framework("方剂配伍研究")
        d = result.to_dict()
        self.assertIn("framework_id", d)
        self.assertIn("confidence", d)
        self.assertIn("selection_reasons", d)
        self.assertIsInstance(d["selection_reasons"], list)

    def test_framework_has_all_phase_guidance(self):
        for fid in FRAMEWORK_IDS:
            result = select_reasoning_framework("x", force_framework=fid)
            self.assertTrue(result.hypothesis_guidance, f"{fid} missing hypothesis_guidance")
            self.assertTrue(result.analyze_focus, f"{fid} missing analyze_focus")
            self.assertTrue(result.reflect_lens, f"{fid} missing reflect_lens")
            self.assertGreater(len(result.analyze_evidence_priority), 0)
            self.assertGreater(len(result.reflect_quality_dimensions), 0)

    def test_knowledge_gap_type_influences_selection(self):
        result = select_reasoning_framework(
            "研究目标",
            {"knowledge_gap": {"gap_type": "drug_pair_synergy", "description": "药对协同"}},
        )
        # drug_pair matches formula_compatibility signals
        self.assertEqual(result.framework_id, "formula_compatibility")

    def test_entity_type_signals_influence_selection(self):
        result = select_reasoning_framework(
            "研究分析",
            {"entities": [
                {"text": "六味地黄丸", "type": "formula"},
                {"text": "熟地", "type": "herb"},
                {"text": "山药", "type": "herb"},
            ]},
        )
        self.assertEqual(result.framework_id, "formula_compatibility")


class TestPhaseIBenchmarkReplay(unittest.TestCase):
    """Phase I / I-2: 同一 case 多次 replay 必须得到一致 prompt 结构。"""

    def test_select_reasoning_framework_is_deterministic(self):
        objective = "黄芪-人参药对的配伍协同增效机制"
        context = {"entities": [{"text": "黄芪", "type": "herb"}, {"text": "人参", "type": "herb"}]}
        first = select_reasoning_framework(objective, context)
        second = select_reasoning_framework(objective, context)
        self.assertEqual(first.framework_id, second.framework_id)
        self.assertEqual(first.confidence, second.confidence)
        self.assertEqual(first.selection_reasons, second.selection_reasons)

    def test_optimizer_prepare_call_is_deterministic(self):
        from src.infra.small_model_optimizer import SmallModelOptimizer

        optimizer = SmallModelOptimizer()
        sections = {
            "objective": "研究桂枝汤减轻发热",
            "evidence": "试验 A、试验 B、试验 C 各取得正向结果",
        }
        a = optimizer.prepare_call(
            phase="hypothesis",
            task_type="hypothesis_generation",
            dossier_sections=sections,
        )
        b = optimizer.prepare_call(
            phase="hypothesis",
            task_type="hypothesis_generation",
            dossier_sections=sections,
        )
        self.assertEqual(a.action, b.action)
        self.assertEqual(a.framework_name, b.framework_name)
        self.assertEqual(a.estimated_tokens, b.estimated_tokens)
        self.assertEqual(a.context_text, b.context_text)
        self.assertEqual(a.output_scaffold, b.output_scaffold)

    def test_prompt_registry_snapshot_is_deterministic(self):
        from src.infra.prompt_registry import export_prompt_registry_snapshot

        first = export_prompt_registry_snapshot()
        second = export_prompt_registry_snapshot()
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(first["total_prompts"], second["total_prompts"])
        # entries must be alphabetically sorted
        names = [entry["name"] for entry in first["entries"]]
        self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
