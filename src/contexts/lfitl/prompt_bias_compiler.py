"""PromptBiasCompiler：把 :class:`PromptBiasAction` 编译成可注入
``SelfRefineRunner.run(inputs=...)`` 的 ``bias_block``。

约定：``inputs["bias"]`` 由 SelfRefineRunner 的 prompt 模板侧消费（可选字段）。
本编译器仅产出 ``{purpose -> bias_block}``，调用方在调用 ``run(...)`` 前 merge：

    inputs.setdefault("bias", bias_blocks.get(purpose, ""))

``bias_block`` 形态::

    {
        "bias_text": "...",
        "avoid_fields": [...],
        "severity": "high",
    }

亦提供 :meth:`inject` 帮助方法，一行把 bias 写入 inputs 字典。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .feedback_translator import PromptBiasAction, TranslationPlan

LEARNING_INSIGHT_PROMPT_TYPES = frozenset(
    {"prompt_bias", "evidence_weight", "method_policy"}
)

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class PromptBiasCompiler:
    """编译 ``TranslationPlan`` → ``{purpose: bias_block}``。"""

    def compile(self, plan: TranslationPlan) -> Dict[str, Dict[str, Any]]:
        compiled: Dict[str, Dict[str, Any]] = {}
        for action in plan.prompt_bias_actions:
            compiled[action.purpose] = {
                "bias_text": action.bias_text,
                "avoid_fields": list(action.avoid_fields),
                "severity": action.severity,
            }
        return compiled

    def build_plan_from_learning_insights(
        self,
        insights: Sequence[Mapping[str, Any]],
        *,
        min_confidence: float = 0.0,
        now: Optional[datetime] = None,
        allowed_insight_types: Optional[Sequence[str]] = None,
        max_items_per_phase: int = 8,
    ) -> TranslationPlan:
        """Convert active LearningInsight rows into a LFITL TranslationPlan."""
        allowed_types = {
            str(item).strip().lower()
            for item in (allowed_insight_types or LEARNING_INSIGHT_PROMPT_TYPES)
            if str(item).strip()
        }
        effective_now = _coerce_datetime(now) or datetime.now(timezone.utc)
        confidence_threshold = _clamp_confidence(min_confidence)
        eligible = [
            dict(item)
            for item in insights or []
            if _is_eligible_learning_insight(
                item,
                allowed_types=allowed_types,
                min_confidence=confidence_threshold,
                now=effective_now,
            )
        ]

        per_phase: Dict[str, List[Mapping[str, Any]]] = {}
        for item in eligible:
            phase = str(item.get("target_phase") or "").strip() or "hypothesis"
            per_phase.setdefault(phase, []).append(item)

        actions: List[PromptBiasAction] = []
        for phase, phase_insights in sorted(per_phase.items()):
            descriptions = []
            for index, item in enumerate(phase_insights[:max_items_per_phase], start=1):
                insight_type = str(item.get("insight_type") or "").strip()
                description = str(item.get("description") or "").strip()
                if not description:
                    continue
                descriptions.append(f"{index}. [{insight_type}] {description}")
            if not descriptions:
                continue
            avoid_fields = sorted(
                {
                    str(item.get("insight_type") or "").strip()
                    for item in phase_insights
                    if str(item.get("insight_type") or "").strip()
                }
            )
            actions.append(
                PromptBiasAction(
                    purpose=phase,
                    bias_text="学习洞察提示：" + " ".join(descriptions),
                    avoid_fields=avoid_fields,
                    severity=_max_learning_insight_severity(phase_insights),
                )
            )

        return TranslationPlan(
            prompt_bias_actions=actions,
            summary={
                "learning_insight_count": len(list(insights or [])),
                "eligible_learning_insight_count": len(eligible),
                "prompt_bias_count": len(actions),
                "min_confidence": confidence_threshold,
                "allowed_insight_types": sorted(allowed_types),
                "phases_touched": sorted(per_phase),
            },
        )

    def compile_learning_insights(
        self,
        insights: Sequence[Mapping[str, Any]],
        *,
        min_confidence: float = 0.0,
        now: Optional[datetime] = None,
        allowed_insight_types: Optional[Sequence[str]] = None,
        max_items_per_phase: int = 8,
    ) -> Dict[str, Dict[str, Any]]:
        """Compile LearningInsight rows directly into phase prompt-bias blocks."""
        plan = self.build_plan_from_learning_insights(
            insights,
            min_confidence=min_confidence,
            now=now,
            allowed_insight_types=allowed_insight_types,
            max_items_per_phase=max_items_per_phase,
        )
        return self.compile(plan)

    def inject(
        self,
        inputs: Dict[str, Any],
        purpose: str,
        bias_blocks: Mapping[str, Mapping[str, Any]],
    ) -> Dict[str, Any]:
        block = bias_blocks.get(purpose) if bias_blocks else None
        if not block:
            return inputs
        # 不覆盖调用方主动传入的 bias
        if "bias" not in inputs:
            inputs["bias"] = block.get("bias_text", "")
        if "avoid_fields" not in inputs:
            inputs["avoid_fields"] = list(block.get("avoid_fields") or [])
        return inputs


def _is_eligible_learning_insight(
    insight: Mapping[str, Any],
    *,
    allowed_types: set[str],
    min_confidence: float,
    now: datetime,
) -> bool:
    if str(insight.get("status") or "active").strip().lower() not in {
        "active",
        "accepted",
    }:
        return False
    insight_type = str(insight.get("insight_type") or "").strip().lower()
    if insight_type not in allowed_types:
        return False
    if _clamp_confidence(insight.get("confidence")) < min_confidence:
        return False
    expires_at = _coerce_datetime(insight.get("expires_at"))
    if expires_at is not None and _as_aware_utc(expires_at) <= _as_aware_utc(now):
        return False
    return bool(str(insight.get("target_phase") or "").strip()) and bool(
        str(insight.get("description") or "").strip()
    )


def _max_learning_insight_severity(insights: Sequence[Mapping[str, Any]]) -> str:
    candidates: List[str] = []
    for item in insights:
        explicit = str(item.get("severity") or "").strip().lower()
        if explicit:
            candidates.append(explicit)
    max_confidence = max(
        (_clamp_confidence(item.get("confidence")) for item in insights), default=0.0
    )
    if max_confidence >= 0.85:
        candidates.append("high")
    elif max_confidence >= 0.5:
        candidates.append("medium")
    else:
        candidates.append("low")
    return max(candidates, key=lambda item: _SEVERITY_ORDER.get(item, 0))


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1.0:
        confidence = confidence / 100.0
    return max(0.0, min(1.0, confidence))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["LEARNING_INSIGHT_PROMPT_TYPES", "PromptBiasCompiler"]
