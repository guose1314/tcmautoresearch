"""T5.1: LFITL（Learning-Feedback-Into-The-Loop）有界上下文。

把 ``learning_feedback_library`` 风格的 ``FeedbackEntry`` 翻译成三类下游可执行的指令：

1. **图权重更新** —— 通过 ``GraphWeightUpdater`` 写回 Neo4j 节点 ``weight``。
2. **Prompt 偏置** —— 通过 ``PromptBiasCompiler`` 输出 ``{purpose: bias_block}``，
   注入 ``SelfRefineRunner.run(inputs=...)`` 的 ``inputs["bias"]``。
3. **运行模式** —— 在 :class:`TranslationPlan.modes` 内给出 ``conservative / normal /
   aggressive`` 等开关，供调度层调整 ``max_refine_rounds`` 等。

主入口 :class:`FeedbackTranslator.translate(feedbacks) -> TranslationPlan`。
"""

from __future__ import annotations

from .feedback_translator import (
    FeedbackEntry,
    FeedbackTranslator,
    GraphWeightAction,
    PromptBiasAction,
    TranslationPlan,
)
from .graph_weight_updater import GraphWeightUpdater
from .prompt_bias_compiler import PromptBiasCompiler

__all__ = [
    "FeedbackEntry",
    "FeedbackTranslator",
    "GraphWeightAction",
    "GraphWeightUpdater",
    "PromptBiasAction",
    "PromptBiasCompiler",
    "TranslationPlan",
]
