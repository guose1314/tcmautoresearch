"""T4.5: 把 ``SelfRefineRunner``（T4.3）应用到一个 phase 的产物文本上，
返回需写入 ``metadata`` 的字段。

设计目标：
- ``enable_self_refine=False`` 时直接跳过（返回空 dict），保留旧路径作 fallback。
- 估算 token usage（以字符数代理），便于断言 "增幅 ≤ 2.5×"。
- 异常不抛出 —— phase 不会因 self-refine 失败而退出失败。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


def resolve_enable_self_refine(
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None,
    *,
    default: bool = False,
) -> bool:
    """优先级：context > pipeline.config.self_refine.enable_self_refine > default。"""

    if context and "enable_self_refine" in context:
        return bool(context["enable_self_refine"])
    if pipeline_config:
        sr_cfg = pipeline_config.get("self_refine") or {}
        if isinstance(sr_cfg, Mapping) and "enable_self_refine" in sr_cfg:
            return bool(sr_cfg["enable_self_refine"])
    return default


def resolve_self_refine_runner(
    context: Mapping[str, Any] | None,
    pipeline: Any,
) -> Any:
    """优先 ``context["self_refine_runner"]``，否则 ``pipeline.self_refine_runner``。"""

    if context and context.get("self_refine_runner") is not None:
        return context["self_refine_runner"]
    return getattr(pipeline, "self_refine_runner", None)


def apply_self_refine_v2(
    *,
    runner: Any,
    purpose: str,
    draft_text: str,
    extra_inputs: Optional[Mapping[str, Any]] = None,
    max_refine_rounds: int = 1,
) -> Dict[str, Any]:
    """跑 SelfRefineRunner 并返回 metadata 增量字段。

    返回字段（命名前缀 ``self_refine_v2_`` 以与旧 ``self_refine_*`` 区分）：

    - ``self_refine_v2``：``RefineResult.to_dict()`` 完整轨迹
    - ``self_refine_v2_succeeded``：bool
    - ``self_refine_v2_round_count``：int
    - ``self_refine_v2_token_usage_baseline``：int（draft 字符数）
    - ``self_refine_v2_token_usage_estimate``：int（draft + 各轮 critique/refined 字符总和）
    - ``self_refine_v2_token_usage_ratio``：float（estimate / baseline，保留 2 位）
    - ``self_refine_v2_violation_count``：int

    异常时返回 ``{"self_refine_v2_error": "..."}``。
    """

    draft = (draft_text or "").strip()
    if runner is None:
        return {"self_refine_v2_error": "runner unavailable"}
    if not draft:
        return {"self_refine_v2_error": "empty draft"}

    inputs: Dict[str, Any] = {
        "task_description": f"对 {purpose} 阶段产物做 self-refine（draft → critique → refine）",
        "input_payload": draft,
    }
    if extra_inputs:
        for k, v in extra_inputs.items():
            inputs.setdefault(str(k), v)

    try:
        result = runner.run(
            purpose=purpose, inputs=inputs, max_refine_rounds=max_refine_rounds
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("self_refine_v2 purpose=%s failed: %s", purpose, exc)
        return {"self_refine_v2_error": f"{type(exc).__name__}: {exc}"}

    baseline_tokens = max(1, len(draft))
    extra_tokens = 0
    for r in getattr(result, "rounds", []) or []:
        extra_tokens += len(getattr(r, "critique_raw", "") or "")
        extra_tokens += len(getattr(r, "refined", "") or "")
    estimate_tokens = baseline_tokens + extra_tokens
    ratio = round(estimate_tokens / baseline_tokens, 3)

    payload: Dict[str, Any] = {
        "self_refine_v2_succeeded": bool(getattr(result, "succeeded", True)),
        "self_refine_v2_round_count": len(getattr(result, "rounds", []) or []),
        "self_refine_v2_token_usage_baseline": baseline_tokens,
        "self_refine_v2_token_usage_estimate": estimate_tokens,
        "self_refine_v2_token_usage_ratio": ratio,
        "self_refine_v2_violation_count": len(
            getattr(result, "last_violations", []) or []
        ),
    }
    try:
        payload["self_refine_v2"] = result.to_dict()
    except Exception:
        payload["self_refine_v2"] = {
            "purpose": purpose,
            "final_output": str(getattr(result, "final_output", "")),
        }
    return payload


__all__ = [
    "apply_self_refine_v2",
    "resolve_enable_self_refine",
    "resolve_self_refine_runner",
]
