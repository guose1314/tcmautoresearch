"""Token budget policy for local small-model prompt stability.

为本地 7B 模型提供统一的输入预算策略：

- 为不同任务类型设置输入 token 预算上限
- 结合 context window 与输出保留空间计算硬上限
- 在超预算时对用户 prompt 做 head-tail 截断
- 支持保留结构化 prompt 的尾部约束（如 JSON Schema）
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN_CN = 1.5
_CHARS_PER_TOKEN_EN = 4.0

DEFAULT_TOKEN_BUDGET_POLICY_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "default_input_tokens": 1536,
    "min_input_tokens": 512,
    "max_context_tokens": 4096,
    "reserve_output_tokens": 1024,
    "keep_head_ratio": 0.72,
    "keep_tail_ratio": 0.28,
    "trim_notice": "\n\n[... 已按 token budget 截断上下文，保留关键前后文 ...]\n\n",
    "purpose_input_budgets": {
        "default": 1536,
        "assistant": 1536,
        "translation": 1536,
        "paper_plugin": 2048,
        "hypothesis": 1280,
        "reflect": 1280,
        "discussion": 1792,
        "entity_extraction": 1024,
        "evidence_synthesis": 1792,
    },
    "task_input_budgets": {
        "question_rewrite": 768,
        "terminology_explanation": 1024,
        "structured_summary": 1536,
        "hypothesis_generation": 1280,
        "discussion_draft": 1792,
        "reflect_diagnosis": 1280,
        "translation": 1536,
        "entity_extraction": 1024,
        "long_form_generation": 1792,
        "graph_reasoning": 1024,
        "unsupported_conclusion": 1280,
        "paper_full_section": 2048,
        "large_evidence_synthesis": 1792,
        "end_to_end_research_judgment": 1152,
    },
}


@dataclass(frozen=True)
class TokenBudgetResolution:
    enabled: bool
    input_budget_tokens: int
    reserve_output_tokens: int
    context_window_tokens: int
    hard_cap_tokens: int
    source: str
    task: str = ""
    purpose: str = ""


@dataclass(frozen=True)
class TokenBudgetApplication:
    system_prompt: str
    user_prompt: str
    trimmed: bool
    input_budget_tokens: int
    total_input_tokens_before: int
    total_input_tokens_after: int
    system_tokens: int
    suffix_tokens: int
    user_tokens_before: int
    user_tokens_after: int
    task: str = ""
    purpose: str = ""
    resolution_source: str = "default"


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
            continue
        merged[key] = value
    return merged


@lru_cache(maxsize=1)
def load_token_budget_policy_settings() -> Dict[str, Any]:
    """Load token budget settings from config.yml -> models.llm.token_budget_policy."""

    try:
        from src.infrastructure.config_loader import load_settings_section

        payload = load_settings_section("models.llm.token_budget_policy", default={})
    except Exception:
        payload = {}

    if isinstance(payload, Mapping):
        return _deep_merge(DEFAULT_TOKEN_BUDGET_POLICY_SETTINGS, payload)
    return dict(DEFAULT_TOKEN_BUDGET_POLICY_SETTINGS)


def reset_token_budget_policy_settings_cache() -> None:
    """Clear cached settings for tests."""

    load_token_budget_policy_settings.cache_clear()


def estimate_text_tokens(text: str) -> int:
    """Estimate tokens using a lightweight mixed Chinese/Latin heuristic."""

    if not text:
        return 0
    cn_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(text) - cn_chars
    return int(
        math.ceil(cn_chars / _CHARS_PER_TOKEN_CN)
        + math.ceil(other_chars / _CHARS_PER_TOKEN_EN)
    )


def resolve_token_budget(
    *,
    task: str = "",
    purpose: str = "",
    context_window_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    settings: Optional[Mapping[str, Any]] = None,
) -> TokenBudgetResolution:
    """Resolve the effective input token budget for a task/purpose."""

    resolved_settings = dict(load_token_budget_policy_settings() if settings is None else settings)
    if not resolved_settings.get("enabled", True):
        context_tokens = int(context_window_tokens or resolved_settings.get("max_context_tokens", 4096) or 4096)
        return TokenBudgetResolution(
            enabled=False,
            input_budget_tokens=context_tokens,
            reserve_output_tokens=0,
            context_window_tokens=context_tokens,
            hard_cap_tokens=context_tokens,
            source="disabled",
            task=str(task or ""),
            purpose=str(purpose or ""),
        )

    min_input_tokens = max(64, int(resolved_settings.get("min_input_tokens", 512) or 512))
    default_input_tokens = max(min_input_tokens, int(resolved_settings.get("default_input_tokens", 1536) or 1536))
    context_tokens = max(
        min_input_tokens,
        int(context_window_tokens or resolved_settings.get("max_context_tokens", 4096) or 4096),
    )
    reserve_output_tokens = max(
        int(resolved_settings.get("reserve_output_tokens", 1024) or 1024),
        int(max_output_tokens or 0),
    )
    hard_cap_tokens = max(min_input_tokens, context_tokens - reserve_output_tokens)

    task_budgets = resolved_settings.get("task_input_budgets")
    purpose_budgets = resolved_settings.get("purpose_input_budgets")
    source = "default"
    requested_budget = default_input_tokens

    if isinstance(task_budgets, Mapping) and task and task in task_budgets:
        requested_budget = int(task_budgets[task] or default_input_tokens)
        source = "task"
    elif isinstance(purpose_budgets, Mapping) and purpose and purpose in purpose_budgets:
        requested_budget = int(purpose_budgets[purpose] or default_input_tokens)
        source = "purpose"

    effective_budget = max(min_input_tokens, min(requested_budget, hard_cap_tokens))
    return TokenBudgetResolution(
        enabled=True,
        input_budget_tokens=effective_budget,
        reserve_output_tokens=reserve_output_tokens,
        context_window_tokens=context_tokens,
        hard_cap_tokens=hard_cap_tokens,
        source=source,
        task=str(task or ""),
        purpose=str(purpose or ""),
    )


def apply_token_budget_to_prompt(
    user_prompt: str,
    *,
    system_prompt: str = "",
    task: str = "",
    purpose: str = "",
    suffix_prompt: str = "",
    context_window_tokens: Optional[int] = None,
    max_output_tokens: Optional[int] = None,
    settings: Optional[Mapping[str, Any]] = None,
) -> TokenBudgetApplication:
    """Apply the token budget policy and trim only the user prompt body if needed."""

    resolved_settings = dict(load_token_budget_policy_settings() if settings is None else settings)
    suffix_separator = "\n\n" if suffix_prompt.strip() else ""
    suffix_bundle = f"{suffix_separator}{suffix_prompt}" if suffix_prompt.strip() else ""
    suffix_tokens = estimate_text_tokens(suffix_bundle)
    system_tokens = estimate_text_tokens(system_prompt)
    body_tokens_before = estimate_text_tokens(user_prompt)
    total_before = system_tokens + body_tokens_before + suffix_tokens

    resolution = resolve_token_budget(
        task=task,
        purpose=purpose,
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        settings=resolved_settings,
    )

    if not resolution.enabled:
        final_prompt = f"{user_prompt}{suffix_bundle}"
        final_tokens = system_tokens + estimate_text_tokens(final_prompt)
        return TokenBudgetApplication(
            system_prompt=system_prompt,
            user_prompt=final_prompt,
            trimmed=False,
            input_budget_tokens=resolution.input_budget_tokens,
            total_input_tokens_before=total_before,
            total_input_tokens_after=final_tokens,
            system_tokens=system_tokens,
            suffix_tokens=suffix_tokens,
            user_tokens_before=body_tokens_before,
            user_tokens_after=estimate_text_tokens(final_prompt),
            task=str(task or ""),
            purpose=str(purpose or ""),
            resolution_source=resolution.source,
        )

    target_body_budget = max(0, resolution.input_budget_tokens - system_tokens - suffix_tokens)
    trimmed_body, trimmed = _trim_text_to_budget(
        user_prompt,
        target_body_budget,
        trim_notice=str(resolved_settings.get("trim_notice") or DEFAULT_TOKEN_BUDGET_POLICY_SETTINGS["trim_notice"]),
        keep_head_ratio=float(resolved_settings.get("keep_head_ratio", 0.72) or 0.72),
        keep_tail_ratio=float(resolved_settings.get("keep_tail_ratio", 0.28) or 0.28),
    )
    final_prompt = f"{trimmed_body}{suffix_bundle}" if trimmed_body else suffix_prompt.strip()
    user_tokens_after = estimate_text_tokens(final_prompt)
    total_after = system_tokens + user_tokens_after

    if trimmed:
        logger.info(
            "Token budget applied: task=%s purpose=%s source=%s total=%d→%d budget=%d",
            task or "-",
            purpose or "-",
            resolution.source,
            total_before,
            total_after,
            resolution.input_budget_tokens,
        )

    return TokenBudgetApplication(
        system_prompt=system_prompt,
        user_prompt=final_prompt,
        trimmed=trimmed,
        input_budget_tokens=resolution.input_budget_tokens,
        total_input_tokens_before=total_before,
        total_input_tokens_after=total_after,
        system_tokens=system_tokens,
        suffix_tokens=suffix_tokens,
        user_tokens_before=body_tokens_before,
        user_tokens_after=user_tokens_after,
        task=str(task or ""),
        purpose=str(purpose or ""),
        resolution_source=resolution.source,
    )


def _trim_text_to_budget(
    text: str,
    target_tokens: int,
    *,
    trim_notice: str,
    keep_head_ratio: float,
    keep_tail_ratio: float,
) -> tuple[str, bool]:
    if not text:
        return text, False
    estimated = estimate_text_tokens(text)
    if estimated <= target_tokens or target_tokens <= 0:
        return text if target_tokens > 0 else "", estimated > target_tokens

    normalized_head_ratio = max(0.05, min(0.95, keep_head_ratio))
    normalized_tail_ratio = max(0.0, min(0.95, keep_tail_ratio))
    ratio_sum = normalized_head_ratio + normalized_tail_ratio
    if ratio_sum <= 0:
        normalized_head_ratio = 1.0
        normalized_tail_ratio = 0.0
    else:
        normalized_head_ratio = normalized_head_ratio / ratio_sum
        normalized_tail_ratio = normalized_tail_ratio / ratio_sum

    notice_tokens = estimate_text_tokens(trim_notice)
    if target_tokens <= notice_tokens + 24:
        target_chars = _chars_for_token_budget(text, max(8, target_tokens))
        shortened = text[:target_chars].rstrip()
        return (f"{shortened}…" if shortened else "…"), True

    available_tokens = max(24, target_tokens - notice_tokens)
    target_chars = _chars_for_token_budget(text, available_tokens)
    head_chars = max(16, int(target_chars * normalized_head_ratio))
    tail_chars = max(0, target_chars - head_chars)

    if head_chars + tail_chars >= len(text):
        shortened = text[: max(1, target_chars)].rstrip()
        return (f"{shortened}…" if shortened else "…"), True

    head = text[:head_chars].rstrip()
    if tail_chars <= 0:
        return f"{head}{trim_notice.rstrip()}", True

    tail = text[-tail_chars:].lstrip()
    return f"{head}{trim_notice}{tail}", True


def _chars_for_token_budget(text: str, target_tokens: int) -> int:
    estimated = estimate_text_tokens(text)
    if estimated <= 0:
        return 0
    ratio = target_tokens / max(estimated, 1)
    return max(1, int(len(text) * ratio * 0.95))