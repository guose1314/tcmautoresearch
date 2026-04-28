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

from typing import Any, Dict, Mapping, Optional

from .feedback_translator import PromptBiasAction, TranslationPlan


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


__all__ = ["PromptBiasCompiler"]
