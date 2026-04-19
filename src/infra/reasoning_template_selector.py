"""推理模板选择器 — 根据任务特征与模型能力动态选择最佳推理框架。

ReasoningTemplateSelector 负责：
- 维护推理框架库（analytical / dialectical / comparative / evidential）
- 根据阶段类型、任务复杂度、历史表现动态选择框架
- 支持从 PolicyAdjuster.template_preferences 接收权重偏好
- 为 7B 小模型提供结构化约束以提升输出稳定性

用法::

    selector = ReasoningTemplateSelector()
    framework = selector.select(
        phase="hypothesis",
        task_complexity="medium",
        template_preferences={"analytical": 0.8, "evidential": 0.6},
    )
    # framework.name == "analytical"
    # framework.system_directive → 注入 system prompt 的推理引导
    # framework.output_scaffold → 结构化输出脚手架
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 推理框架定义 ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReasoningFramework:
    """单个推理框架配置。"""

    name: str
    display_name: str
    system_directive: str
    output_scaffold: str
    suited_phases: tuple
    complexity_affinity: str  # "low" | "medium" | "high"
    token_overhead: int  # 框架自身占用的近似 token 数


_FRAMEWORKS: Dict[str, ReasoningFramework] = {
    "analytical": ReasoningFramework(
        name="analytical",
        display_name="分析式推理",
        system_directive=(
            "请使用分析式推理方法：先分解问题要素，逐一考察证据，"
            "再综合得出结论。每步标注【分解】【证据】【综合】。"
        ),
        output_scaffold=(
            "## 分析\n### 问题分解\n- \n### 证据考察\n- \n### 综合结论\n"
        ),
        suited_phases=("observe", "analyze", "hypothesis"),
        complexity_affinity="medium",
        token_overhead=80,
    ),
    "dialectical": ReasoningFramework(
        name="dialectical",
        display_name="辩证式推理",
        system_directive=(
            "请使用辩证式推理方法：先列出正反两方面论据，"
            "考察矛盾与统一，再形成辩证结论。标注【正论】【反论】【统一】。"
        ),
        output_scaffold=(
            "## 辩证分析\n### 正论\n- \n### 反论\n- \n### 辩证统一\n"
        ),
        suited_phases=("hypothesis", "discuss", "reflect"),
        complexity_affinity="high",
        token_overhead=90,
    ),
    "comparative": ReasoningFramework(
        name="comparative",
        display_name="比较式推理",
        system_directive=(
            "请使用比较式推理方法：明确比较维度，列表对比各方案或观点，"
            "总结异同与优劣。标注【维度】【对比】【结论】。"
        ),
        output_scaffold=(
            "## 比较分析\n### 比较维度\n- \n### 对比表\n| 维度 | A | B |\n### 结论\n"
        ),
        suited_phases=("analyze", "experiment", "discuss"),
        complexity_affinity="medium",
        token_overhead=85,
    ),
    "evidential": ReasoningFramework(
        name="evidential",
        display_name="证据链式推理",
        system_directive=(
            "请使用证据链式推理方法：从原始证据出发，逐步构建推理链条，"
            "每步标注证据来源与置信度。标注【证据】【推理】【置信度】。"
        ),
        output_scaffold=(
            "## 证据链\n### 核心证据\n- \n### 推理链条\n1. \n### 置信度评估\n"
        ),
        suited_phases=("observe", "analyze", "experiment_execution"),
        complexity_affinity="low",
        token_overhead=75,
    ),
    "concise": ReasoningFramework(
        name="concise",
        display_name="精简直答",
        system_directive=(
            "请直接、简洁地回答问题。不需要展开论证过程，"
            "仅给出核心结论与关键依据。"
        ),
        output_scaffold="",
        suited_phases=("observe", "publish"),
        complexity_affinity="low",
        token_overhead=30,
    ),
}

# ── 阶段→默认框架映射 ────────────────────────────────────────────────────

_PHASE_DEFAULT_FRAMEWORK: Dict[str, str] = {
    "observe": "evidential",
    "analyze": "analytical",
    "hypothesis": "analytical",
    "experiment": "comparative",
    "experiment_execution": "evidential",
    "discuss": "dialectical",
    "reflect": "dialectical",
    "publish": "concise",
}

# ── 复杂度→框架适配权重 ──────────────────────────────────────────────────

_COMPLEXITY_WEIGHT: Dict[str, Dict[str, float]] = {
    "low": {"concise": 1.5, "evidential": 1.2, "analytical": 0.8, "comparative": 0.8, "dialectical": 0.6},
    "medium": {"analytical": 1.3, "comparative": 1.2, "evidential": 1.0, "dialectical": 0.9, "concise": 0.7},
    "high": {"dialectical": 1.4, "analytical": 1.2, "comparative": 1.1, "evidential": 1.0, "concise": 0.4},
}


@dataclass
class SelectionResult:
    """框架选择结果。"""

    framework: ReasoningFramework
    score: float
    alternatives: List[str] = field(default_factory=list)
    reason: str = ""


class ReasoningTemplateSelector:
    """根据任务上下文动态选择最佳推理框架。

    评分公式：
        score = phase_affinity × complexity_weight × preference_weight

    其中：
    - phase_affinity: 框架是否适配当前阶段 (1.5 适配 / 1.0 中性)
    - complexity_weight: 框架与任务复杂度的匹配权重
    - preference_weight: 来自 PolicyAdjuster 的学习偏好 (0.0 ~ 1.0，默认 0.5)
    """

    def __init__(self, frameworks: Optional[Dict[str, ReasoningFramework]] = None) -> None:
        self._frameworks = frameworks or dict(_FRAMEWORKS)

    @property
    def available_frameworks(self) -> List[str]:
        return list(self._frameworks.keys())

    def select(
        self,
        *,
        phase: str,
        task_complexity: str = "medium",
        template_preferences: Optional[Dict[str, float]] = None,
        available_budget_tokens: Optional[int] = None,
    ) -> SelectionResult:
        """选择最佳推理框架。

        Parameters
        ----------
        phase :
            当前研究阶段名。
        task_complexity :
            任务复杂度 ("low" / "medium" / "high")。
        template_preferences :
            学习偏好权重（来自 PolicyAdjuster）。
        available_budget_tokens :
            可用 token 预算（若过小则偏向低开销框架）。
        """
        preferences = template_preferences or {}
        complexity = task_complexity if task_complexity in _COMPLEXITY_WEIGHT else "medium"
        complexity_weights = _COMPLEXITY_WEIGHT[complexity]

        scores: Dict[str, float] = {}
        for name, fw in self._frameworks.items():
            # 1. 阶段适配
            phase_affinity = 1.5 if phase in fw.suited_phases else 1.0

            # 2. 复杂度权重
            cw = complexity_weights.get(name, 1.0)

            # 3. 阶段默认加成（防止边缘计算偏离设计意图）
            default_fw_name = _PHASE_DEFAULT_FRAMEWORK.get(phase)
            default_boost = 1.4 if name == default_fw_name else 1.0

            # 4. 学习偏好
            pref = preferences.get(name, 0.5)
            # 归一化到 [0.5, 1.5] 范围
            pref_weight = 0.5 + pref

            # 5. token 预算约束
            budget_penalty = 1.0
            if available_budget_tokens is not None and available_budget_tokens < 800:
                # 预算紧张时惩罚高开销框架
                if fw.token_overhead > 80:
                    budget_penalty = 0.6

            scores[name] = phase_affinity * cw * default_boost * pref_weight * budget_penalty

        # 排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_name = ranked[0][0]
        best_fw = self._frameworks[best_name]

        alternatives = [name for name, _ in ranked[1:3]]
        default_fw = _PHASE_DEFAULT_FRAMEWORK.get(phase, "analytical")
        reason = (
            f"phase={phase}, complexity={complexity}, "
            f"top_score={ranked[0][1]:.2f}, default={default_fw}"
        )

        return SelectionResult(
            framework=best_fw,
            score=ranked[0][1],
            alternatives=alternatives,
            reason=reason,
        )

    def get_framework(self, name: str) -> Optional[ReasoningFramework]:
        """按名称获取框架。"""
        return self._frameworks.get(name)

    def get_phase_default(self, phase: str) -> str:
        """获取阶段默认框架名。"""
        return _PHASE_DEFAULT_FRAMEWORK.get(phase, "analytical")
