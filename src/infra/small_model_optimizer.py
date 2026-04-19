"""小模型优化协调器 — 统一 ReasoningTemplateSelector / DynamicInvocationStrategy / DossierLayerCompressor。

SmallModelOptimizer 是 Phase E 三大组件的门面层，为调用方提供：
- 一站式 "prepare_call" 接口：根据阶段、任务类型、上下文 sections 生成完整的优化调用方案
- 成本追踪与报告
- 与 PolicyAdjuster.template_preferences 的桥接

用法::

    optimizer = SmallModelOptimizer.from_config(llm_config)
    plan = optimizer.prepare_call(
        phase="hypothesis",
        task_type="hypothesis_generation",
        dossier_sections={"objective": "...", "evidence": "..."},
        template_preferences={"analytical": 0.8},
    )
    # plan.action → "proceed" | "decompose" | "skip"
    # plan.context_text → 已按层级压缩的上下文
    # plan.reasoning_directive → 注入 system prompt 的推理引导
    # plan.output_scaffold → 结构化输出脚手架
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.infra.dossier_layer_compressor import DossierLayerCompressor, LayeredDossier
from src.infra.dynamic_invocation_strategy import (
    CostMetrics,
    DynamicInvocationStrategy,
    InvocationDecision,
)
from src.infra.reasoning_template_selector import (
    ReasoningFramework,
    ReasoningTemplateSelector,
    SelectionResult,
)

logger = logging.getLogger(__name__)


@dataclass
class CallPlan:
    """优化后的 LLM 调用方案。"""

    action: str  # "proceed" | "decompose" | "skip" | "retry_simplified"
    context_text: str
    reasoning_directive: str
    output_scaffold: str
    framework_name: str
    layer_used: int
    estimated_tokens: int
    decision_reason: str
    degradation_hints: Dict[str, Any] = field(default_factory=dict)
    sub_contexts: List[str] = field(default_factory=list)  # decompose 时的子上下文

    @property
    def should_call_llm(self) -> bool:
        return self.action in ("proceed", "retry_simplified")


class SmallModelOptimizer:
    """统一协调小模型优化三组件。

    Parameters
    ----------
    model_context_window :
        模型上下文窗口大小（token）。
    output_reserve :
        为输出预留的 token 数。
    layer_budgets :
        可选覆盖 DossierLayerCompressor 各层预算。
    """

    def __init__(
        self,
        model_context_window: int = 4096,
        output_reserve: int = 1024,
        layer_budgets: Optional[Dict[int, int]] = None,
    ) -> None:
        self._template_selector = ReasoningTemplateSelector()
        self._invocation_strategy = DynamicInvocationStrategy(
            model_context_window=model_context_window,
            output_reserve=output_reserve,
        )
        self._layer_compressor = DossierLayerCompressor(layer_budgets=layer_budgets)
        self._context_window = model_context_window
        self._output_reserve = output_reserve

    @classmethod
    def from_config(cls, llm_config: Dict[str, Any]) -> "SmallModelOptimizer":
        """从 LLM 配置创建实例。"""
        context_window = int(llm_config.get("max_context_tokens", 4096))
        output_reserve = int(llm_config.get("reserve_output_tokens", 1024))
        return cls(model_context_window=context_window, output_reserve=output_reserve)

    @property
    def template_selector(self) -> ReasoningTemplateSelector:
        return self._template_selector

    @property
    def invocation_strategy(self) -> DynamicInvocationStrategy:
        return self._invocation_strategy

    @property
    def layer_compressor(self) -> DossierLayerCompressor:
        return self._layer_compressor

    def prepare_call(
        self,
        *,
        phase: str,
        task_type: str,
        dossier_sections: Dict[str, str],
        template_preferences: Optional[Dict[str, float]] = None,
        cache_hit_likelihood: float = 0.0,
        retry_count: int = 0,
    ) -> CallPlan:
        """生成完整的优化调用方案。

        流程：
        1. DossierLayerCompressor 压缩上下文为多层
        2. ReasoningTemplateSelector 选择推理框架
        3. DynamicInvocationStrategy 决定调用动作
        4. 根据决策选择合适的 dossier 层级
        5. 组装 CallPlan
        """
        # Step 1: 压缩上下文
        layered = self._layer_compressor.compress(dossier_sections)

        # Step 2: 选择推理框架
        effective_budget = self._context_window - self._output_reserve
        selection = self._template_selector.select(
            phase=phase,
            task_complexity=self._infer_complexity(task_type),
            template_preferences=template_preferences,
            available_budget_tokens=effective_budget,
        )
        framework = selection.framework

        # Step 3: 估算总 input tokens（context + framework overhead）
        # 先按 Layer 1 估算
        layer_1 = layered.get_layer(1)
        estimated_input = (layer_1.estimated_tokens if layer_1 else 0) + framework.token_overhead

        # Step 4: 调用策略决策
        decision = self._invocation_strategy.decide(
            task_type=task_type,
            input_tokens=estimated_input,
            cache_hit_likelihood=cache_hit_likelihood,
            retry_count=retry_count,
        )

        # Step 5: 根据决策选层
        if decision.action == "skip":
            return CallPlan(
                action="skip",
                context_text="",
                reasoning_directive="",
                output_scaffold="",
                framework_name=framework.name,
                layer_used=-1,
                estimated_tokens=0,
                decision_reason=decision.reason,
                degradation_hints=decision.degradation_hints,
            )

        if decision.action == "decompose":
            # 拆分：每个 sub-context 用 Layer 0
            layer_0 = layered.get_layer(0)
            context_text = layer_0.text if layer_0 else ""
            sub_count = decision.degradation_hints.get("recommended_sub_count", 2)
            sub_contexts = self._split_context_for_decompose(dossier_sections, sub_count)
            return CallPlan(
                action="decompose",
                context_text=context_text,
                reasoning_directive=framework.system_directive,
                output_scaffold=framework.output_scaffold,
                framework_name=framework.name,
                layer_used=0,
                estimated_tokens=decision.estimated_cost_tokens,
                decision_reason=decision.reason,
                degradation_hints=decision.degradation_hints,
                sub_contexts=sub_contexts,
            )

        if decision.action == "retry_simplified":
            # 重试：用更低层级，移除脚手架
            remove_scaffold = decision.degradation_hints.get("remove_scaffold", False)
            layer = layered.select_for_budget(effective_budget - 100)
            return CallPlan(
                action="retry_simplified",
                context_text=layer.text,
                reasoning_directive=framework.system_directive if not remove_scaffold else "",
                output_scaffold="" if remove_scaffold else framework.output_scaffold,
                framework_name=framework.name,
                layer_used=layer.level,
                estimated_tokens=decision.estimated_cost_tokens,
                decision_reason=decision.reason,
                degradation_hints=decision.degradation_hints,
            )

        # proceed: 选择最佳层级
        available_for_context = effective_budget - framework.token_overhead
        layer = layered.select_for_budget(available_for_context)

        return CallPlan(
            action="proceed",
            context_text=layer.text,
            reasoning_directive=framework.system_directive,
            output_scaffold=framework.output_scaffold,
            framework_name=framework.name,
            layer_used=layer.level,
            estimated_tokens=layer.estimated_tokens + framework.token_overhead,
            decision_reason=decision.reason,
            degradation_hints=decision.degradation_hints,
        )

    def get_cost_report(self) -> Dict[str, Any]:
        """返回成本追踪报告。"""
        return self._invocation_strategy.get_cost_report()

    def _infer_complexity(self, task_type: str) -> str:
        """从 task_type 推断复杂度。"""
        from src.infra.dynamic_invocation_strategy import _TASK_COMPLEXITY
        return _TASK_COMPLEXITY.get(task_type, "medium")

    def _split_context_for_decompose(
        self, sections: Dict[str, str], sub_count: int
    ) -> List[str]:
        """将 sections 拆分为 sub_count 个子上下文。"""
        # 简单策略：按 section 均分
        section_items = [(k, v) for k, v in sections.items() if v.strip()]
        if not section_items:
            return [""] * sub_count

        chunk_size = max(1, len(section_items) // sub_count)
        result: List[str] = []
        for i in range(0, len(section_items), chunk_size):
            chunk = section_items[i: i + chunk_size]
            text = "\n\n".join(f"### {k}\n{v}" for k, v in chunk)
            result.append(text)

        # 确保恰好 sub_count 个
        while len(result) < sub_count:
            result.append("")
        return result[:sub_count]
