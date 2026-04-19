# -*- coding: utf-8 -*-
"""Reasoning Template Selector.

借鉴 Self-Discover (Zhou et al., 2024) 思路，在 hypothesis、analyze、reflect
三个阶段之前，先判断当前研究问题最适合走哪条推理框架。

支持框架:
  - formula_compatibility  方剂配伍：围绕药对、组方逻辑推理
  - pathomechanism_evidence  病机证据：围绕证型、病因病机推理
  - textual_criticism  版本考据：围绕文献学、校勘训诂推理
  - systematic_review  循证综述：围绕证据等级、系统评价推理

用法:
    from src.research.reasoning_template_selector import select_reasoning_framework
    framework = select_reasoning_framework(research_objective, context)
    # framework.framework_id -> "formula_compatibility"
    # framework.hypothesis_guidance -> 用于 hypothesis 阶段的 prompt 指导
    # framework.analyze_focus -> 用于 analyze 阶段的分析聚焦
    # framework.reflect_lens -> 用于 reflect 阶段的反思视角
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────

FRAMEWORK_IDS = (
    "formula_compatibility",
    "pathomechanism_evidence",
    "textual_criticism",
    "systematic_review",
)


@dataclass(frozen=True)
class ReasoningFramework:
    """选定的推理框架，携带各阶段所需的指导信息。"""

    framework_id: str
    display_name: str
    confidence: float  # 置信度 [0, 1]

    # hypothesis 阶段
    hypothesis_guidance: str  # 注入到 prompt 的推理指导
    hypothesis_focus_entities: tuple = ()

    # analyze 阶段
    analyze_focus: str = ""  # 分析聚焦方向
    analyze_evidence_priority: tuple = ()  # 证据优先级排序

    # reflect 阶段
    reflect_lens: str = ""  # 反思视角描述
    reflect_quality_dimensions: tuple = ()  # 质量评估维度

    # 选择原因
    selection_reasons: tuple = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework_id": self.framework_id,
            "display_name": self.display_name,
            "confidence": self.confidence,
            "hypothesis_guidance": self.hypothesis_guidance,
            "analyze_focus": self.analyze_focus,
            "reflect_lens": self.reflect_lens,
            "selection_reasons": list(self.selection_reasons),
        }


# ─────────────────────────────────────────────────────────────────────────────

_FRAMEWORK_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "formula_compatibility": {
        "display_name": "方剂配伍推理",
        "hypothesis_guidance": (
            "请从方剂配伍学角度出发，围绕药对协同、"
            "君臣佐使结构、剂量配比逻辑构建假说。"
            "关注组方规律与药物相互作用。"
        ),
        "analyze_focus": (
            "聚焦于药对关联规则、共现频率、"
            "方剂结构模式以及剂量比例证据。"
        ),
        "analyze_evidence_priority": (
            "association_rule", "co_occurrence", "formula_structure",
            "dose_ratio", "synergy_antagonism",
        ),
        "reflect_lens": (
            "从方剂学完整性视角反思：配伍逻辑是否自洽、"
            "药对覆盖是否充分、剂量证据是否可靠。"
        ),
        "reflect_quality_dimensions": (
            "formula_logic_completeness", "drug_pair_coverage",
            "dose_evidence_support", "clinical_formula_validation",
        ),
    },
    "pathomechanism_evidence": {
        "display_name": "病机证据推理",
        "hypothesis_guidance": (
            "请从病因病机角度出发，围绕证型鉴别、"
            "病机传变链、治则治法构建假说。"
            "关注辨证论治的因果逻辑与临床证据。"
        ),
        "analyze_focus": (
            "聚焦于证型模式识别、病机因果链分析，"
            "以及「证-法-方-药」对应关系验证。"
        ),
        "analyze_evidence_priority": (
            "syndrome_pattern", "pathomechanism_chain", "treatment_principle",
            "clinical_outcome", "mechanism_explanation",
        ),
        "reflect_lens": (
            "从辨证论治完整性视角反思：证型判断是否准确、"
            "因果链条是否连贯、治则依据是否充分。"
        ),
        "reflect_quality_dimensions": (
            "syndrome_accuracy", "causal_chain_integrity",
            "treatment_rationale", "clinical_evidence_alignment",
        ),
    },
    "textual_criticism": {
        "display_name": "版本考据推理",
        "hypothesis_guidance": (
            "请从文献学与校勘学角度出发，围绕版本流传、"
            "异文校勘、训诂释义构建假说。"
            "关注文本可靠性与历代注疏演变。"
        ),
        "analyze_focus": (
            "聚焦于校勘异文比对、版本源流考证，"
            "以及历代注家诠释差异分析。"
        ),
        "analyze_evidence_priority": (
            "collation_variant", "version_lineage", "exegesis_history",
            "dynasty_attribution", "textual_reliability",
        ),
        "reflect_lens": (
            "从文献学严谨性视角反思：校勘覆盖是否完整、"
            "版本证据是否充足、训诂释义是否准确。"
        ),
        "reflect_quality_dimensions": (
            "collation_coverage", "version_evidence_sufficiency",
            "exegesis_accuracy", "source_reliability",
        ),
    },
    "systematic_review": {
        "display_name": "循证综述推理",
        "hypothesis_guidance": (
            "请从循证医学角度出发，围绕证据等级、"
            "研究设计质量、结局指标构建假说。"
            "关注系统性与证据分级的客观性。"
        ),
        "analyze_focus": (
            "聚焦于证据等级评估、研究异质性分析，"
            "以及 GRADE 框架下的证据质量判定。"
        ),
        "analyze_evidence_priority": (
            "evidence_grade", "study_design", "outcome_measure",
            "heterogeneity", "publication_bias",
        ),
        "reflect_lens": (
            "从循证完整性视角反思：检索是否全面、"
            "分级是否一致、结论是否与证据相称。"
        ),
        "reflect_quality_dimensions": (
            "search_completeness", "grading_consistency",
            "conclusion_proportionality", "bias_assessment",
        ),
    },
}

# ─────────────────────────────────────────────────────────────────────────────

_SIGNAL_KEYWORDS: Dict[str, List[str]] = {
    "formula_compatibility": [
        "方剂", "配伍", "药对", "组方", "君臣佐使", "剂量", "药味",
        "合方", "协同", "增效", "拮抗", "相须", "相使", "相畏",
        "相杀", "复方", "加减", "汤剂", "散剂",
    ],
    "pathomechanism_evidence": [
        "病机", "证型", "辨证", "论治", "病因", "传变", "证候",
        "脏腑", "气血", "阴阳", "寒热", "虚实", "表里", "治则",
        "治法", "方证", "病证", "标本",
    ],
    "textual_criticism": [
        "版本", "校勘", "异文", "考据", "训诂", "注疏", "原文",
        "古籍", "底本", "刻本", "抄本", "辑佚", "避讳", "衍文",
        "脱文", "讹误", "善本", "类书", "引文",
    ],
    "systematic_review": [
        "系统", "综述", "Meta分析", "Meta", "meta", "证据等级",
        "随机对照", "对照试验", "文献检索", "纳入标准", "排除标准",
        "GRADE", "RCT", "异质性", "发表偏倚", "评价",
    ],
}

# 实体类型信号
_ENTITY_TYPE_SIGNALS: Dict[str, List[str]] = {
    "formula_compatibility": ["formula", "herb", "herb_pair", "drug_pair", "component"],
    "pathomechanism_evidence": ["syndrome", "disease", "symptom", "organ", "pattern"],
    "textual_criticism": ["document", "edition", "variant", "collation", "witness"],
    "systematic_review": ["study", "trial", "outcome", "intervention", "population"],
}


# ─────────────────────────────────────────────────────────────────────────────

def select_reasoning_framework(
    research_objective: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    force_framework: Optional[str] = None,
) -> ReasoningFramework:
    """选择最合适的推理框架。

    Parameters
    ----------
    research_objective :
        研究目标描述
    context :
        上下文信息，含 entities, knowledge_gap, research_domain 等
    force_framework :
        强制使用的框架 ID，用于测试或配置覆盖

    Returns
    -------
    ReasoningFramework
        选定的框架及其各阶段指导
    """
    context = context or {}

    # 强制覆盖
    if force_framework and force_framework in FRAMEWORK_IDS:
        template = _FRAMEWORK_TEMPLATES[force_framework]
        return _build_framework(force_framework, template, 1.0, ("forced_by_config",))

    # 配置覆盖
    config_framework = _resolve_config_framework(context)
    if config_framework and config_framework in FRAMEWORK_IDS:
        template = _FRAMEWORK_TEMPLATES[config_framework]
        return _build_framework(config_framework, template, 0.95, ("config_override",))

    # 自动评分选择
    scores = _score_frameworks(research_objective, context)
    best_id = max(scores, key=scores.get)
    best_score = scores[best_id]

    # 低信号时默认使用 systematic_review 作为兜底
    if best_score < 0.15:
        best_id = "systematic_review"
        best_score = 0.3
        reasons = ("default_fallback_low_signal",)
    else:
        reasons = tuple(_explain_selection(best_id, research_objective, context))

    template = _FRAMEWORK_TEMPLATES[best_id]
    confidence = min(best_score / max(sum(scores.values()), 0.01), 1.0)

    logger.info(
        "推理框架选择: %s (置信度 %.2f, 原因=%s)",
        best_id, confidence, reasons,
    )
    return _build_framework(best_id, template, confidence, reasons)


def _build_framework(
    framework_id: str,
    template: Dict[str, Any],
    confidence: float,
    reasons: tuple,
) -> ReasoningFramework:
    return ReasoningFramework(
        framework_id=framework_id,
        display_name=template["display_name"],
        confidence=confidence,
        hypothesis_guidance=template["hypothesis_guidance"],
        analyze_focus=template["analyze_focus"],
        analyze_evidence_priority=tuple(template.get("analyze_evidence_priority", ())),
        reflect_lens=template["reflect_lens"],
        reflect_quality_dimensions=tuple(template.get("reflect_quality_dimensions", ())),
        selection_reasons=reasons,
    )


def _resolve_config_framework(context: Dict[str, Any]) -> Optional[str]:
    """从 context 或 learning_strategy 中解析配置的框架覆盖。"""
    # 直接指定
    explicit = context.get("reasoning_framework")
    if explicit:
        return str(explicit).strip()
    # learning_strategy 中指定
    strategy = context.get("learning_strategy") or {}
    if isinstance(strategy, dict):
        return str(strategy.get("reasoning_framework") or "").strip() or None
    return None


def _score_frameworks(
    objective: str,
    context: Dict[str, Any],
) -> Dict[str, float]:
    """基于关键词匹配+实体类型+research_domain 评分。"""
    scores: Dict[str, float] = {fid: 0.0 for fid in FRAMEWORK_IDS}
    text_corpus = _build_scoring_text(objective, context)

    # 1. 关键词匹配
    for fid, keywords in _SIGNAL_KEYWORDS.items():
        for kw in keywords:
            count = text_corpus.count(kw)
            if count > 0:
                scores[fid] += min(count * 0.1, 0.5)

    # 2. 实体类型信号
    entities = context.get("entities") or []
    entity_types = set()
    for ent in entities:
        if isinstance(ent, dict):
            etype = str(ent.get("type") or ent.get("entity_type") or "").lower()
            if etype:
                entity_types.add(etype)

    for fid, type_signals in _ENTITY_TYPE_SIGNALS.items():
        for ts in type_signals:
            if ts in entity_types:
                scores[fid] += 0.3

    # 3. research_domain 信号
    domain = str(context.get("research_domain") or "").lower()
    domain_map = {
        "formula_compatibility": ("formula", "compatibility", "配伍", "方剂"),
        "pathomechanism_evidence": ("pathomechanism", "syndrome", "病机", "辨证"),
        "textual_criticism": ("philology", "textual", "校勘", "考据"),
        "systematic_review": ("systematic", "evidence", "循证", "综述"),
    }
    for fid, domain_kws in domain_map.items():
        if any(dk in domain for dk in domain_kws):
            scores[fid] += 0.5

    # 4. knowledge_gap 类型信号
    gap = context.get("knowledge_gap") or {}
    if isinstance(gap, dict):
        gap_type = str(gap.get("gap_type") or "").lower()
        gap_type_map = {
            "formula_compatibility": ("formula", "compatibility", "drug_pair", "synergy"),
            "pathomechanism_evidence": ("mechanism", "syndrome", "pattern", "pathology"),
            "textual_criticism": ("orphan", "textual", "philology", "variant"),
            "systematic_review": ("evidence", "coverage", "literature", "methodology"),
        }
        for fid, gap_kws in gap_type_map.items():
            if any(gk in gap_type for gk in gap_kws):
                scores[fid] += 0.4

    return scores


def _build_scoring_text(objective: str, context: Dict[str, Any]) -> str:
    """拼接用于评分的文本语料。"""
    parts = [objective or ""]
    scope = context.get("research_scope")
    if scope:
        parts.append(str(scope))
    description = context.get("description") or ""
    if isinstance(description, str):
        parts.append(description)
    # 加入 knowledge_gap 描述
    gap = context.get("knowledge_gap") or {}
    if isinstance(gap, dict):
        gap_desc = gap.get("description") or ""
        if gap_desc:
            parts.append(str(gap_desc))
    return " ".join(parts)


def _explain_selection(
    framework_id: str,
    objective: str,
    context: Dict[str, Any],
) -> List[str]:
    """生成选择原因说明。"""
    reasons: List[str] = []
    text_corpus = _build_scoring_text(objective, context)
    keywords = _SIGNAL_KEYWORDS.get(framework_id, [])
    matched = [kw for kw in keywords if kw in text_corpus]
    if matched:
        reasons.append(f"keyword_match: {', '.join(matched[:3])}")
    domain = str(context.get("research_domain") or "")
    if domain:
        reasons.append(f"domain={domain}")
    if not reasons:
        reasons.append("highest_composite_score")
    return reasons
