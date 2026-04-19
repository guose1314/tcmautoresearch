"""LLM 任务适配性策略 — Task Suitability Policy for Local 7B Models.

将审计文档 §10.1 的职责分配固化为可执行策略：

  适合 (SUITABLE)
      假说生成、研究问题重写、术语解释、结构化摘要、Discussion 初稿、
      Reflect 诊断。

  谨慎使用 (CAUTIOUS)
      长文整篇直接生成、复杂图谱全量推理、无检索支撑的结论生成。

  不建议单独承担 (UNSUITABLE_SOLO)
      大规模证据整合、无中间结构的端到端科研判定。

使用方式::

    from src.infra.llm_task_policy import evaluate_task, TaskVerdict

    verdict = evaluate_task("hypothesis_generation")
    if verdict.tier == "unsuitable_solo":
        logger.warning(verdict.guidance)

集成点: get_llm_service() 调用时可通过 purpose → task 映射获取建议。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────
# 适配层级
# ───────────────────────────────────────────────────────────────────────

class SuitabilityTier(str, Enum):
    """本地 7B 模型的任务适配层级。"""
    SUITABLE = "suitable"
    CAUTIOUS = "cautious"
    UNSUITABLE_SOLO = "unsuitable_solo"


# ───────────────────────────────────────────────────────────────────────
# 任务评估结果
# ───────────────────────────────────────────────────────────────────────

@dataclass
class TaskVerdict:
    """对一个 LLM 任务的适配性评估。"""
    task: str
    tier: SuitabilityTier
    guidance: str
    recommended_max_tokens: Optional[int] = None
    recommended_temperature: Optional[float] = None


# ───────────────────────────────────────────────────────────────────────
# 权威任务清单 — 来源: 审计文档 §10.1
# ───────────────────────────────────────────────────────────────────────

@dataclass
class TaskSpec:
    """单个任务的适配规格。"""
    tier: SuitabilityTier
    guidance: str
    recommended_max_tokens: Optional[int] = None
    recommended_temperature: Optional[float] = None


TASK_POLICY: Dict[str, TaskSpec] = {
    # ━━━ SUITABLE: 7B 擅长，可放心使用 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "hypothesis_generation": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="假说生成是 7B 模型的强项，可在结构化上下文下直接使用",
        recommended_max_tokens=1024,
        recommended_temperature=0.7,
    ),
    "question_rewrite": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="研究问题重写/精化，7B 可胜任",
        recommended_max_tokens=512,
        recommended_temperature=0.3,
    ),
    "terminology_explanation": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="中医术语解释与跨时代对照，7B 在有上下文时表现良好",
        recommended_max_tokens=768,
        recommended_temperature=0.3,
    ),
    "structured_summary": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="结构化摘要（方剂、证候、本草条目），7B 擅长",
        recommended_max_tokens=1024,
        recommended_temperature=0.3,
    ),
    "discussion_draft": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="Discussion 初稿生成，7B 在有 dossier 支撑时可用",
        recommended_max_tokens=1500,
        recommended_temperature=0.5,
    ),
    "reflect_diagnosis": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="Reflect 阶段诊断与质量反馈，7B 可稳定执行",
        recommended_max_tokens=1024,
        recommended_temperature=0.3,
    ),
    "translation": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="古文-现代文/中-英翻译，7B 可胜任短段落",
        recommended_max_tokens=2048,
        recommended_temperature=0.1,
    ),
    "entity_extraction": TaskSpec(
        tier=SuitabilityTier.SUITABLE,
        guidance="实体抽取（药名、方名、证候名），适合 7B",
        recommended_max_tokens=512,
        recommended_temperature=0.1,
    ),

    # ━━━ CAUTIOUS: 可用但需注意质量 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "long_form_generation": TaskSpec(
        tier=SuitabilityTier.CAUTIOUS,
        guidance="长文整篇生成超出 7B 稳定上下文，建议分段生成或增加中间结构",
        recommended_max_tokens=2048,
        recommended_temperature=0.5,
    ),
    "graph_reasoning": TaskSpec(
        tier=SuitabilityTier.CAUTIOUS,
        guidance="复杂图谱全量推理对 7B 认知负荷过高，建议限定子图范围并提供结构化前置信息",
        recommended_max_tokens=1024,
        recommended_temperature=0.3,
    ),
    "unsupported_conclusion": TaskSpec(
        tier=SuitabilityTier.CAUTIOUS,
        guidance="无检索支撑的结论生成易产生幻觉，必须先经 dossier 压缩再生成",
        recommended_max_tokens=1024,
        recommended_temperature=0.3,
    ),
    "paper_full_section": TaskSpec(
        tier=SuitabilityTier.CAUTIOUS,
        guidance="论文完整章节一次性生成，建议拆分为子任务逐段完成",
        recommended_max_tokens=1500,
        recommended_temperature=0.5,
    ),

    # ━━━ UNSUITABLE_SOLO: 不建议单独承担 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    "large_evidence_synthesis": TaskSpec(
        tier=SuitabilityTier.UNSUITABLE_SOLO,
        guidance="大规模证据整合超出 7B 能力边界，需 dossier 预压缩 + 分层证据 + 人工复核",
        recommended_max_tokens=2048,
        recommended_temperature=0.3,
    ),
    "end_to_end_research_judgment": TaskSpec(
        tier=SuitabilityTier.UNSUITABLE_SOLO,
        guidance="无中间结构的端到端科研判定不适合 7B 单独执行，需阶段分解 + 证据链支撑",
        recommended_max_tokens=2048,
        recommended_temperature=0.3,
    ),
}


# ───────────────────────────────────────────────────────────────────────
# purpose → task 映射（将现有 get_llm_service purpose 关联到任务）
# ───────────────────────────────────────────────────────────────────────

PURPOSE_TASK_MAP: Dict[str, str] = {
    "default": "structured_summary",
    "translation": "translation",
    "paper_plugin": "paper_full_section",
    "assistant": "question_rewrite",
    "hypothesis": "hypothesis_generation",
    "reflect": "reflect_diagnosis",
    "discussion": "discussion_draft",
    "entity_extraction": "entity_extraction",
    "evidence_synthesis": "large_evidence_synthesis",
}


# ───────────────────────────────────────────────────────────────────────
# 评估 API
# ───────────────────────────────────────────────────────────────────────

def evaluate_task(task: str) -> TaskVerdict:
    """评估指定任务在本地 7B 模型上的适配性。

    Args:
        task: 任务标识（TASK_POLICY 中的键）或 purpose 名称。

    Returns:
        TaskVerdict: 评估结果，包含层级和建议。
    """
    # 先尝试直接查找 task
    spec = TASK_POLICY.get(task)
    if spec is None:
        # 尝试 purpose → task 映射
        mapped_task = PURPOSE_TASK_MAP.get(task)
        if mapped_task:
            spec = TASK_POLICY.get(mapped_task)
    if spec is None:
        # 未知任务默认为 cautious
        return TaskVerdict(
            task=task,
            tier=SuitabilityTier.CAUTIOUS,
            guidance=f"未知任务 '{task}'，默认按 cautious 处理，建议补充到 TASK_POLICY",
        )
    return TaskVerdict(
        task=task,
        tier=spec.tier,
        guidance=spec.guidance,
        recommended_max_tokens=spec.recommended_max_tokens,
        recommended_temperature=spec.recommended_temperature,
    )


def evaluate_purpose(purpose: str) -> TaskVerdict:
    """通过 get_llm_service 的 purpose 参数评估适配性。"""
    task = PURPOSE_TASK_MAP.get(purpose, purpose)
    return evaluate_task(task)


def check_suitability(purpose: str) -> None:
    """检查 purpose 的适配性并发出日志警告（如需要）。

    设计为在 get_llm_service() 内部调用的轻量检查。
    """
    verdict = evaluate_purpose(purpose)
    if verdict.tier == SuitabilityTier.UNSUITABLE_SOLO:
        logger.warning(
            "LLM 任务适配性警告 [%s → %s]: %s",
            purpose, verdict.tier.value, verdict.guidance,
        )
    elif verdict.tier == SuitabilityTier.CAUTIOUS:
        logger.info(
            "LLM 任务适配性提示 [%s → %s]: %s",
            purpose, verdict.tier.value, verdict.guidance,
        )


def get_policy_summary() -> Dict[str, Any]:
    """返回策略汇总统计。"""
    counts: Dict[str, int] = {t.value: 0 for t in SuitabilityTier}
    for spec in TASK_POLICY.values():
        counts[spec.tier.value] += 1
    return {
        "total_tasks": len(TASK_POLICY),
        "counts": counts,
        "purposes_mapped": len(PURPOSE_TASK_MAP),
    }
