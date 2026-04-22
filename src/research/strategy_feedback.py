"""Reflect 策略建议回流（Phase M-4）。

把上一轮 reflect 阶段产生的策略建议，沉淀为下一轮 topic_discovery /
observe / hypothesis 阶段可消费的"结构化提示"。

公开 API：
  - STRATEGY_FEEDBACK_CONTRACT_VERSION
  - StrategySuggestion / StrategyFeedback / StrategyFeedbackStore
  - build_strategy_feedback_from_reflect(reflect_result)
  - apply_strategy_feedback_to_context(feedback, context)

设计原则：
  - 纯数据契约 + 内存 store，落库由调用方决定
  - 不破坏现有 reflect/learning 流，仅提供"次轮消费"路径
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional

STRATEGY_FEEDBACK_CONTRACT_VERSION = "strategy-feedback-v1"

VALID_TARGET_PHASES = frozenset(
    {"topic_discovery", "observe", "hypothesis", "experiment", "analyze", "publish"}
)


@dataclass
class StrategySuggestion:
    """单条策略建议。"""

    target_phase: str
    suggestion: str
    priority: float = 0.5
    rationale: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_phase not in VALID_TARGET_PHASES:
            raise ValueError(
                f"target_phase 必须为 {sorted(VALID_TARGET_PHASES)}，收到 {self.target_phase!r}"
            )
        if not self.suggestion:
            raise ValueError("suggestion 不能为空")
        try:
            self.priority = float(self.priority)
        except (TypeError, ValueError) as exc:
            raise ValueError("priority 必须可转 float") from exc
        if not (0.0 <= self.priority <= 1.0):
            raise ValueError("priority 必须 ∈ [0,1]")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_phase": self.target_phase,
            "suggestion": self.suggestion,
            "priority": self.priority,
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategySuggestion":
        return cls(
            target_phase=str(payload["target_phase"]),
            suggestion=str(payload["suggestion"]),
            priority=float(payload.get("priority", 0.5)),
            rationale=payload.get("rationale"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class StrategyFeedback:
    """一轮 reflect 产出的全部策略建议。"""

    cycle_id: str
    suggestions: List[StrategySuggestion] = field(default_factory=list)
    contract_version: str = STRATEGY_FEEDBACK_CONTRACT_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def suggestions_for(self, phase: str) -> List[StrategySuggestion]:
        return [s for s in self.suggestions if s.target_phase == phase]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "cycle_id": self.cycle_id,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StrategyFeedback":
        return cls(
            cycle_id=str(payload["cycle_id"]),
            suggestions=[
                StrategySuggestion.from_dict(s) for s in payload.get("suggestions") or []
            ],
            contract_version=str(
                payload.get("contract_version") or STRATEGY_FEEDBACK_CONTRACT_VERSION
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


class StrategyFeedbackStore:
    """跨 cycle 的反馈池（线程安全）。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_cycle: Dict[str, StrategyFeedback] = {}

    def append(self, feedback: StrategyFeedback) -> None:
        with self._lock:
            self._by_cycle[feedback.cycle_id] = feedback

    def get(self, cycle_id: str) -> Optional[StrategyFeedback]:
        with self._lock:
            return self._by_cycle.get(cycle_id)

    def latest(self) -> Optional[StrategyFeedback]:
        with self._lock:
            if not self._by_cycle:
                return None
            return list(self._by_cycle.values())[-1]

    def all(self) -> List[StrategyFeedback]:
        with self._lock:
            return list(self._by_cycle.values())


def build_strategy_feedback_from_reflect(
    reflect_result: Mapping[str, Any],
    *,
    cycle_id: str,
) -> StrategyFeedback:
    """从 reflect phase 输出抽取策略建议。

    兼容形态（按出现顺序逐项尝试）：
      1. results.improvement_plan: list[{target_phase|phase, suggestion|action, priority, rationale}]
      2. results.reflections: list[{phase, suggestion}]
      3. results.learning_summary.suggestions: list[...]
    """
    if not isinstance(reflect_result, Mapping):
        raise TypeError("reflect_result 必须为 Mapping")
    results = reflect_result.get("results")
    results = results if isinstance(results, Mapping) else {}

    suggestions: List[StrategySuggestion] = []
    seen: set = set()

    def _add(target_phase: Any, suggestion: Any, priority: Any, rationale: Any) -> None:
        if not target_phase or not suggestion:
            return
        phase = str(target_phase)
        text = str(suggestion)
        if phase not in VALID_TARGET_PHASES:
            return
        key = (phase, text)
        if key in seen:
            return
        try:
            prio = float(priority) if priority is not None else 0.5
        except (TypeError, ValueError):
            prio = 0.5
        prio = max(0.0, min(1.0, prio))
        suggestions.append(
            StrategySuggestion(
                target_phase=phase,
                suggestion=text,
                priority=prio,
                rationale=str(rationale) if rationale else None,
            )
        )
        seen.add(key)

    plan = results.get("improvement_plan")
    if isinstance(plan, list):
        for item in plan:
            if not isinstance(item, Mapping):
                continue
            _add(
                item.get("target_phase") or item.get("phase"),
                item.get("suggestion") or item.get("action"),
                item.get("priority"),
                item.get("rationale"),
            )

    reflections = results.get("reflections")
    if isinstance(reflections, list):
        for item in reflections:
            if not isinstance(item, Mapping):
                continue
            _add(
                item.get("phase") or item.get("target_phase"),
                item.get("suggestion") or item.get("note"),
                item.get("priority"),
                item.get("rationale"),
            )

    learning = results.get("learning_summary")
    if isinstance(learning, Mapping):
        for item in learning.get("suggestions") or []:
            if not isinstance(item, Mapping):
                continue
            _add(
                item.get("target_phase") or item.get("phase"),
                item.get("suggestion") or item.get("action"),
                item.get("priority"),
                item.get("rationale"),
            )

    return StrategyFeedback(cycle_id=str(cycle_id), suggestions=suggestions)


def apply_strategy_feedback_to_context(
    feedback: StrategyFeedback,
    context: Dict[str, Any],
    *,
    target_phase: str,
) -> Dict[str, Any]:
    """把指定 phase 的建议写入 context（若已有则合并不覆盖）。

    返回更新后的 context（同一个对象）。
    """
    if target_phase not in VALID_TARGET_PHASES:
        raise ValueError(f"未知 target_phase: {target_phase}")
    bucket = context.setdefault("strategy_feedback", {})
    if not isinstance(bucket, dict):
        raise TypeError("context['strategy_feedback'] 必须为 dict")
    phase_bucket = bucket.setdefault(target_phase, [])
    if not isinstance(phase_bucket, list):
        raise TypeError(f"context['strategy_feedback'][{target_phase}] 必须为 list")
    existing_texts = {item.get("suggestion") for item in phase_bucket if isinstance(item, dict)}
    for s in feedback.suggestions_for(target_phase):
        if s.suggestion in existing_texts:
            continue
        phase_bucket.append(s.to_dict())
    bucket["_source_cycle_id"] = feedback.cycle_id
    bucket["_contract_version"] = feedback.contract_version
    return context
