"""Phase E 单元测试 — ReasoningTemplateSelector / DynamicInvocationStrategy / DossierLayerCompressor / SmallModelOptimizer。"""

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# 1. ReasoningTemplateSelector
# ═══════════════════════════════════════════════════════════════════════════════
from src.infra.reasoning_template_selector import (
    ReasoningTemplateSelector,
    SelectionResult,
)


class TestReasoningTemplateSelector:
    """推理模板选择器测试。"""

    def setup_method(self):
        self.selector = ReasoningTemplateSelector()

    # ── 基本选择逻辑 ──

    def test_select_returns_selection_result(self):
        result = self.selector.select(phase="observe")
        assert isinstance(result, SelectionResult)
        assert result.framework is not None

    def test_observe_phase_prefers_evidential(self):
        result = self.selector.select(phase="observe")
        assert result.framework.name == "evidential"

    def test_analyze_phase_prefers_analytical(self):
        result = self.selector.select(phase="analyze")
        assert result.framework.name == "analytical"

    def test_hypothesis_phase_prefers_analytical(self):
        result = self.selector.select(phase="hypothesis")
        assert result.framework.name == "analytical"

    def test_discuss_phase_prefers_dialectical(self):
        result = self.selector.select(phase="discuss")
        assert result.framework.name == "dialectical"

    def test_reflect_phase_prefers_dialectical(self):
        result = self.selector.select(phase="reflect")
        assert result.framework.name == "dialectical"

    def test_publish_phase_prefers_concise(self):
        result = self.selector.select(phase="publish")
        assert result.framework.name == "concise"

    # ── 偏好覆盖 ──

    def test_template_preferences_can_override_default(self):
        prefs = {"comparative": 2.0}  # 强偏好 comparative
        result = self.selector.select(phase="observe", template_preferences=prefs)
        assert result.framework.name == "comparative"

    def test_no_preferences_uses_defaults(self):
        result = self.selector.select(phase="analyze", template_preferences=None)
        assert result.framework.name == "analytical"

    # ── 复杂度影响 ──

    def test_low_complexity_avoids_high_complexity_frameworks(self):
        result = self.selector.select(phase="analyze", task_complexity="low")
        # 低复杂度不应选择高复杂度亲和框架
        assert result.framework.name != "dialectical"

    def test_high_complexity_avoids_concise(self):
        result = self.selector.select(phase="analyze", task_complexity="high")
        assert result.framework.name != "concise"

    # ── 预算约束 ──

    def test_tight_budget_penalizes_high_overhead(self):
        result = self.selector.select(phase="hypothesis", available_budget_tokens=500)
        # 预算很紧时应选 overhead 低的框架
        assert result.framework.token_overhead <= 100

    def test_generous_budget_allows_any_framework(self):
        result = self.selector.select(phase="hypothesis", available_budget_tokens=3000)
        assert result.framework is not None

    # ── 框架属性 ──

    def test_all_frameworks_have_system_directive(self):
        for phase in ["observe", "analyze", "hypothesis", "discuss", "reflect", "publish"]:
            result = self.selector.select(phase=phase)
            assert result.framework.system_directive

    def test_all_frameworks_have_output_scaffold(self):
        for phase in ["observe", "analyze", "hypothesis", "discuss", "reflect", "publish"]:
            result = self.selector.select(phase=phase)
            # concise 框架设计上无 scaffold（精简直答）
            if result.framework.name != "concise":
                assert result.framework.output_scaffold

    def test_unknown_phase_falls_back_gracefully(self):
        result = self.selector.select(phase="unknown_phase_xyz")
        assert result.framework is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DynamicInvocationStrategy
# ═══════════════════════════════════════════════════════════════════════════════

from src.infra.dynamic_invocation_strategy import (
    DynamicInvocationStrategy,
    InvocationDecision,
)


class TestDynamicInvocationStrategy:
    """动态调用策略测试。"""

    def setup_method(self):
        self.strategy = DynamicInvocationStrategy(model_context_window=4096, output_reserve=1024)

    # ── 正常 proceed ──

    def test_simple_task_proceeds(self):
        decision = self.strategy.decide(task_type="entity_extraction", input_tokens=500)
        assert decision.action == "proceed"

    def test_medium_task_proceeds(self):
        decision = self.strategy.decide(task_type="summarization", input_tokens=1500)
        assert decision.action == "proceed"

    # ── Skip 决策 ──

    def test_high_cache_likelihood_skips(self):
        decision = self.strategy.decide(
            task_type="entity_extraction", input_tokens=500, cache_hit_likelihood=0.95
        )
        assert decision.action == "skip"

    def test_moderate_cache_likelihood_does_not_skip(self):
        decision = self.strategy.decide(
            task_type="entity_extraction", input_tokens=500, cache_hit_likelihood=0.5
        )
        assert decision.action != "skip"

    # ── Decompose 决策 ──

    def test_over_budget_decomposable_task_decomposes(self):
        # effective_budget = 4096 - 1024 = 3072; 85% = 2611
        decision = self.strategy.decide(task_type="hypothesis_generation", input_tokens=2700)
        assert decision.action == "decompose"

    def test_over_budget_non_decomposable_proceeds_with_trim(self):
        decision = self.strategy.decide(task_type="text_classification", input_tokens=2700)
        assert decision.action == "proceed"
        assert decision.degradation_hints.get("will_be_trimmed") is True

    def test_high_complexity_decomposable_with_moderate_input_decomposes(self):
        # input > 60% of budget (3072 * 0.6 = 1843)
        decision = self.strategy.decide(task_type="evidence_synthesis", input_tokens=2000)
        assert decision.action == "decompose"

    def test_high_complexity_below_60pct_proceeds(self):
        decision = self.strategy.decide(task_type="evidence_synthesis", input_tokens=1500)
        assert decision.action == "proceed"

    # ── 重试降级 ──

    def test_retry_1_simplifies_prompt(self):
        decision = self.strategy.decide(task_type="hypothesis_generation", input_tokens=2000, retry_count=1)
        assert decision.action == "retry_simplified"
        assert decision.degradation_hints["step"] == "simplify_prompt"

    def test_retry_2_reduces_schema(self):
        decision = self.strategy.decide(task_type="hypothesis_generation", input_tokens=2000, retry_count=2)
        assert decision.action == "retry_simplified"
        assert decision.degradation_hints["step"] == "reduce_output_schema"

    def test_retry_3_falls_back_to_rules(self):
        decision = self.strategy.decide(task_type="hypothesis_generation", input_tokens=2000, retry_count=3)
        assert decision.action == "skip"
        assert "fallback" in decision.degradation_hints

    # ── 成本追踪 ──

    def test_metrics_initial_state(self):
        assert self.strategy.metrics.total_calls == 0

    def test_decide_increments_total_calls(self):
        self.strategy.decide(task_type="summarization", input_tokens=800)
        assert self.strategy.metrics.total_calls == 1

    def test_skip_increments_skipped_calls(self):
        self.strategy.decide(task_type="summarization", input_tokens=800, cache_hit_likelihood=0.95)
        assert self.strategy.metrics.skipped_calls == 1

    def test_record_completion_tracks_output_tokens(self):
        self.strategy.decide(task_type="summarization", input_tokens=800)
        self.strategy.record_completion(output_tokens=256, cache_hit=False)
        assert self.strategy.metrics.total_output_tokens == 256

    def test_cost_report_format(self):
        self.strategy.decide(task_type="summarization", input_tokens=800)
        report = self.strategy.get_cost_report()
        assert "total_calls" in report
        assert "effective_call_rate" in report


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DossierLayerCompressor
# ═══════════════════════════════════════════════════════════════════════════════

from src.infra.dossier_layer_compressor import (
    CompressedLayer,
    DossierLayerCompressor,
    LayeredDossier,
)


class TestDossierLayerCompressor:
    """分层压缩测试。"""

    def setup_method(self):
        self.compressor = DossierLayerCompressor()
        self.sample_sections = {
            "objective": "研究附子配伍减毒增效的机理，阐明现代药理学证据。",
            "evidence": "张仲景《伤寒论》记载附子与甘草配伍...（证据段落）" * 20,
            "entities": "附子/Aconitum/乌头碱/甘草/甘草酸..." * 10,
            "graph": "附子 → 温阳散寒; 甘草 → 调和诸药; 配伍减毒..." * 10,
            "terminology": "乌头碱: aconitine; 附子: Radix Aconiti...",
            "hypothesis_history": "H1: 甘草酸与乌头碱竞争性结合; H2: 热处理降解..." * 5,
            "version_info": "v3.2, cycle_12",
            "controversies": "争议：是否剂量依赖性..." * 5,
            "corpus_digest": "本草纲目附子条目摘要..." * 8,
        }

    # ── 层级结构 ──

    def test_compress_returns_layered_dossier(self):
        result = self.compressor.compress(self.sample_sections)
        assert isinstance(result, LayeredDossier)

    def test_all_three_layers_present(self):
        result = self.compressor.compress(self.sample_sections)
        assert 0 in result.layers
        assert 1 in result.layers
        assert 2 in result.layers

    def test_layer_0_is_shortest(self):
        result = self.compressor.compress(self.sample_sections)
        assert result.layers[0].estimated_tokens <= result.layers[1].estimated_tokens

    def test_layer_1_shorter_than_layer_2(self):
        result = self.compressor.compress(self.sample_sections)
        assert result.layers[1].estimated_tokens <= result.layers[2].estimated_tokens

    # ── 预算约束 ──

    def test_layer_0_within_budget(self):
        result = self.compressor.compress(self.sample_sections)
        assert result.layers[0].estimated_tokens <= 600  # 允许少量浮动

    def test_layer_1_within_budget(self):
        result = self.compressor.compress(self.sample_sections)
        assert result.layers[1].estimated_tokens <= 1700

    def test_layer_2_within_budget(self):
        result = self.compressor.compress(self.sample_sections)
        assert result.layers[2].estimated_tokens <= 3200

    # ── select_for_budget ──

    def test_select_for_budget_picks_highest_fitting_layer(self):
        # 使用大量内容确保各层有明显差异
        large_sections = {
            "objective": "研究附子配伍减毒增效的机理" * 10,
            "evidence": "张仲景《伤寒论》记载附子与甘草配伍" * 200,
            "entities": "附子/Aconitum/乌头碱/甘草/甘草酸" * 200,
            "graph": "附子 → 温阳散寒; 甘草 → 调和诸药; 配伍减毒" * 200,
            "terminology": "乌头碱: aconitine; 附子: Radix Aconiti" * 200,
            "hypothesis_history": "H1: 甘草酸与乌头碱竞争性结合" * 200,
            "version_info": "v3.2, cycle_12",
            "controversies": "争议：是否剂量依赖性" * 200,
            "corpus_digest": "本草纲目附子条目摘要" * 200,
        }
        result = self.compressor.compress(large_sections)
        # Layer 2 (budget=3072) 应该大于 2000 tokens
        # 所以 select_for_budget(2000) 应返回 Layer 1 或更低
        selected = result.select_for_budget(2000)
        assert selected.level <= 1

    def test_select_for_budget_very_tight_returns_layer_0(self):
        result = self.compressor.compress(self.sample_sections)
        selected = result.select_for_budget(300)
        assert selected.level == 0

    def test_select_for_budget_generous_returns_layer_2(self):
        result = self.compressor.compress(self.sample_sections)
        selected = result.select_for_budget(5000)
        assert selected.level == 2

    # ── 空输入 ──

    def test_empty_sections(self):
        result = self.compressor.compress({})
        assert isinstance(result, LayeredDossier)
        layer_0 = result.get_layer(0)
        assert layer_0.estimated_tokens == 0

    # ── section fallback ──

    def test_summary_fallback(self):
        sections = {"evidence_summary": "简短的证据摘要", "objective": "目标"}
        result = self.compressor.compress(sections)
        # Layer 0 spec asks for "evidence_summary" — should resolve
        layer_0 = result.get_layer(0)
        assert "evidence_summary" in layer_0.sections_included or "evidence" not in layer_0.sections_included

    # ── metadata ──

    def test_to_metadata_format(self):
        result = self.compressor.compress(self.sample_sections)
        meta = result.to_metadata()
        assert "layer_count" in meta
        assert meta["layer_count"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SmallModelOptimizer (集成协调)
# ═══════════════════════════════════════════════════════════════════════════════

from src.infra.small_model_optimizer import CallPlan, SmallModelOptimizer


class TestSmallModelOptimizer:
    """小模型优化器集成测试。"""

    def setup_method(self):
        self.optimizer = SmallModelOptimizer(model_context_window=4096, output_reserve=1024)
        self.dossier = {
            "objective": "研究附子配伍减毒机理",
            "evidence": "证据内容" * 50,
            "entities": "实体列表" * 20,
            "hypothesis_history": "假说历史" * 10,
        }

    # ── prepare_call 基本行为 ──

    def test_prepare_call_returns_call_plan(self):
        plan = self.optimizer.prepare_call(
            phase="analyze", task_type="summarization", dossier_sections=self.dossier
        )
        assert isinstance(plan, CallPlan)

    def test_proceed_plan_has_context_and_directive(self):
        plan = self.optimizer.prepare_call(
            phase="analyze", task_type="summarization", dossier_sections=self.dossier
        )
        if plan.action == "proceed":
            assert plan.context_text
            assert plan.reasoning_directive
            assert plan.framework_name

    def test_skip_plan_has_no_context(self):
        plan = self.optimizer.prepare_call(
            phase="analyze",
            task_type="summarization",
            dossier_sections=self.dossier,
            cache_hit_likelihood=0.95,
        )
        assert plan.action == "skip"
        assert plan.context_text == ""

    def test_should_call_llm_property(self):
        plan = self.optimizer.prepare_call(
            phase="analyze", task_type="summarization", dossier_sections=self.dossier
        )
        if plan.action == "proceed":
            assert plan.should_call_llm is True

        skip_plan = self.optimizer.prepare_call(
            phase="analyze",
            task_type="summarization",
            dossier_sections=self.dossier,
            cache_hit_likelihood=0.95,
        )
        assert skip_plan.should_call_llm is False

    # ── 偏好桥接 ──

    def test_template_preferences_respected(self):
        plan = self.optimizer.prepare_call(
            phase="observe",
            task_type="summarization",
            dossier_sections=self.dossier,
            template_preferences={"comparative": 3.0},
        )
        if plan.action != "skip":
            assert plan.framework_name == "comparative"

    # ── 重试路径 ──

    def test_retry_simplified_plan(self):
        plan = self.optimizer.prepare_call(
            phase="analyze",
            task_type="hypothesis_generation",
            dossier_sections=self.dossier,
            retry_count=1,
        )
        assert plan.action == "retry_simplified"

    # ── 成本报告 ──

    def test_cost_report_after_calls(self):
        self.optimizer.prepare_call(
            phase="analyze", task_type="summarization", dossier_sections=self.dossier
        )
        report = self.optimizer.get_cost_report()
        assert report["total_calls"] >= 1

    # ── from_config ──

    def test_from_config_creates_instance(self):
        config = {"max_context_tokens": 4096, "reserve_output_tokens": 1024}
        opt = SmallModelOptimizer.from_config(config)
        assert opt is not None

    # ── 组件暴露 ──

    def test_sub_components_accessible(self):
        assert self.optimizer.template_selector is not None
        assert self.optimizer.invocation_strategy is not None
        assert self.optimizer.layer_compressor is not None
