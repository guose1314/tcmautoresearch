"""动态调用策略 — 为 7B 小模型优化 LLM 调用决策。

DynamicInvocationStrategy 负责：
- 决定是否需要 LLM 调用（skip / proceed / decompose）
- 对复杂任务自动拆分为小模型可处理的子任务
- 失败重试时简化 prompt（降级策略）
- 跟踪调用成本与效率指标

用法::

    strategy = DynamicInvocationStrategy(model_context_window=4096)
    decision = strategy.decide(
        task_type="hypothesis_generation",
        input_tokens=2800,
        cache_hit_likelihood=0.3,
    )
    if decision.action == "decompose":
        sub_prompts = decision.sub_prompts
    elif decision.action == "proceed":
        ...  # 正常调用
    elif decision.action == "skip":
        ...  # 使用规则引擎 fallback
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────────────

# 模型能力边界（7B 模型经验值）
_DEFAULT_CONTEXT_WINDOW = 4096
_SAFE_OUTPUT_RESERVE = 1024
_DECOMPOSE_THRESHOLD_RATIO = 0.85  # input/context > 85% → decompose
_SKIP_CONFIDENCE_THRESHOLD = 0.9  # cache_hit_likelihood > 90% → can skip

# 任务复杂度映射
_TASK_COMPLEXITY: Dict[str, str] = {
    "entity_extraction": "low",
    "text_classification": "low",
    "summarization": "medium",
    "translation": "medium",
    "quality_assessment": "medium",
    "hypothesis_generation": "high",
    "evidence_synthesis": "high",
    "reflection": "high",
    "protocol_design": "high",
    "discussion_generation": "high",
    "paper_section": "high",
}

# 可分解任务（支持 sub-prompt 拆分）
_DECOMPOSABLE_TASKS = frozenset({
    "hypothesis_generation",
    "evidence_synthesis",
    "discussion_generation",
    "paper_section",
})

# 重试降级步骤
_RETRY_DEGRADATION_STEPS = (
    "simplify_prompt",  # 第 1 次重试：移除脚手架、缩短上下文
    "reduce_output_schema",  # 第 2 次重试：简化输出 schema
    "fallback_to_rules",  # 第 3 次重试：放弃 LLM，走规则引擎
)


@dataclass
class InvocationDecision:
    """单次调用决策。"""

    action: str  # "proceed" | "decompose" | "skip" | "retry_simplified"
    reason: str
    estimated_cost_tokens: int = 0
    sub_prompts: List[str] = field(default_factory=list)
    degradation_hints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CostMetrics:
    """成本追踪指标。"""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    skipped_calls: int = 0
    decomposed_calls: int = 0
    cache_hits: int = 0
    retries: int = 0
    fallbacks_to_rules: int = 0

    @property
    def effective_call_rate(self) -> float:
        """实际执行调用比率。"""
        if self.total_calls == 0:
            return 0.0
        return (self.total_calls - self.skipped_calls) / self.total_calls

    @property
    def avg_input_tokens(self) -> float:
        effective = self.total_calls - self.skipped_calls
        if effective == 0:
            return 0.0
        return self.total_input_tokens / effective

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "skipped_calls": self.skipped_calls,
            "decomposed_calls": self.decomposed_calls,
            "cache_hits": self.cache_hits,
            "retries": self.retries,
            "fallbacks_to_rules": self.fallbacks_to_rules,
            "effective_call_rate": round(self.effective_call_rate, 4),
            "avg_input_tokens": round(self.avg_input_tokens, 1),
        }


class DynamicInvocationStrategy:
    """为 7B 小模型优化的动态调用策略。

    核心决策树：
    1. cache_hit_likelihood >= 0.9 → skip（大概率命中缓存，无需调用）
    2. input_tokens / context_window > 0.85 → decompose（输入过长，拆分）
    3. task_complexity == "low" + input_tokens < budget → proceed（简单任务直接执行）
    4. task_complexity == "high" + 可分解 → decompose
    5. 否则 → proceed

    线程安全：metrics 通过 Lock 保护。
    """

    def __init__(
        self,
        model_context_window: int = _DEFAULT_CONTEXT_WINDOW,
        output_reserve: int = _SAFE_OUTPUT_RESERVE,
    ) -> None:
        self._context_window = model_context_window
        self._output_reserve = output_reserve
        self._effective_budget = model_context_window - output_reserve
        self._metrics = CostMetrics()
        self._lock = threading.Lock()

    @property
    def metrics(self) -> CostMetrics:
        with self._lock:
            return self._metrics

    def decide(
        self,
        *,
        task_type: str,
        input_tokens: int,
        cache_hit_likelihood: float = 0.0,
        retry_count: int = 0,
    ) -> InvocationDecision:
        """做出调用决策。

        Parameters
        ----------
        task_type :
            任务类型（对应 _TASK_COMPLEXITY 映射）。
        input_tokens :
            预估输入 token 数。
        cache_hit_likelihood :
            缓存命中概率（0.0-1.0，由调用方基于历史估计）。
        retry_count :
            当前重试次数（0 = 首次调用）。
        """
        with self._lock:
            self._metrics.total_calls += 1

        # 重试降级路径
        if retry_count > 0:
            return self._handle_retry(task_type, input_tokens, retry_count)

        # 缓存命中概率高 → skip
        if cache_hit_likelihood >= _SKIP_CONFIDENCE_THRESHOLD:
            with self._lock:
                self._metrics.skipped_calls += 1
            return InvocationDecision(
                action="skip",
                reason=f"cache_hit_likelihood={cache_hit_likelihood:.2f} >= {_SKIP_CONFIDENCE_THRESHOLD}",
                estimated_cost_tokens=0,
            )

        # 输入超出安全预算 → decompose
        budget_ratio = input_tokens / self._effective_budget if self._effective_budget > 0 else 1.0
        if budget_ratio > _DECOMPOSE_THRESHOLD_RATIO:
            if task_type in _DECOMPOSABLE_TASKS:
                with self._lock:
                    self._metrics.decomposed_calls += 1
                sub_count = max(2, int(budget_ratio / 0.7) + 1)
                return InvocationDecision(
                    action="decompose",
                    reason=f"budget_ratio={budget_ratio:.2f} > {_DECOMPOSE_THRESHOLD_RATIO}, task decomposable",
                    estimated_cost_tokens=input_tokens,
                    degradation_hints={
                        "recommended_sub_count": sub_count,
                        "max_tokens_per_sub": self._effective_budget // sub_count,
                    },
                )
            else:
                # 不可分解但超预算 → 仍 proceed，依赖 token budget 截断
                return InvocationDecision(
                    action="proceed",
                    reason=f"budget_ratio={budget_ratio:.2f} over limit but not decomposable, will trim",
                    estimated_cost_tokens=min(input_tokens, self._effective_budget),
                    degradation_hints={"will_be_trimmed": True},
                )

        # 高复杂度可分解任务 → decompose（即使未超预算）
        complexity = _TASK_COMPLEXITY.get(task_type, "medium")
        if complexity == "high" and task_type in _DECOMPOSABLE_TASKS and input_tokens > self._effective_budget * 0.6:
            with self._lock:
                self._metrics.decomposed_calls += 1
            return InvocationDecision(
                action="decompose",
                reason=f"high complexity + decomposable + input_ratio={budget_ratio:.2f} > 0.6",
                estimated_cost_tokens=input_tokens,
                degradation_hints={
                    "recommended_sub_count": 2,
                    "max_tokens_per_sub": self._effective_budget // 2,
                },
            )

        # 默认 → proceed
        with self._lock:
            self._metrics.total_input_tokens += input_tokens
        return InvocationDecision(
            action="proceed",
            reason=f"task={task_type}, complexity={complexity}, budget_ratio={budget_ratio:.2f}",
            estimated_cost_tokens=input_tokens,
        )

    def record_completion(self, output_tokens: int, cache_hit: bool = False) -> None:
        """记录调用完成。"""
        with self._lock:
            self._metrics.total_output_tokens += output_tokens
            if cache_hit:
                self._metrics.cache_hits += 1

    def get_cost_report(self) -> Dict[str, Any]:
        """返回成本报告。"""
        with self._lock:
            return self._metrics.to_dict()

    def _handle_retry(self, task_type: str, input_tokens: int, retry_count: int) -> InvocationDecision:
        """处理重试降级逻辑。"""
        with self._lock:
            self._metrics.retries += 1

        step_idx = min(retry_count - 1, len(_RETRY_DEGRADATION_STEPS) - 1)
        step = _RETRY_DEGRADATION_STEPS[step_idx]

        if step == "fallback_to_rules":
            with self._lock:
                self._metrics.fallbacks_to_rules += 1
            return InvocationDecision(
                action="skip",
                reason=f"retry #{retry_count} → fallback_to_rules",
                estimated_cost_tokens=0,
                degradation_hints={"fallback": "rules_engine", "reason": "max_retries_exceeded"},
            )

        # simplify_prompt 或 reduce_output_schema
        reduction_factor = 0.7 if step == "simplify_prompt" else 0.85
        return InvocationDecision(
            action="retry_simplified",
            reason=f"retry #{retry_count} → {step}",
            estimated_cost_tokens=int(input_tokens * reduction_factor),
            degradation_hints={
                "step": step,
                "reduction_factor": reduction_factor,
                "remove_scaffold": step == "simplify_prompt",
                "simplify_schema": step == "reduce_output_schema",
            },
        )
