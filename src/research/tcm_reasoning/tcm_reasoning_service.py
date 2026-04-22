"""TCM reasoning service — 5 条核心规则 + 主入口 + 元数据装配。

规则全部为纯函数，不依赖 LLM；输入 ``TCMReasoningPremise`` 序列，
输出 ``TCMReasoningStep | None``。可注入到 ``run_tcm_reasoning`` 中
形成可审计的 ``TCMReasoningTrace``。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from .trace_contract import (
    CONTRACT_VERSION,
    PATTERN_FANGZHENG_DUIYING,
    PATTERN_JUNCHEN_ZUOSHI,
    PATTERN_LABELS,
    PATTERN_SANYIN_ZHIYI,
    PATTERN_TONGBING_YIZHI,
    PATTERN_YIBING_TONGZHI,
    REASONING_PATTERNS,
    TCMReasoningPremise,
    TCMReasoningStep,
    TCMReasoningTrace,
)

RuleCallable = Callable[[Sequence[TCMReasoningPremise]], Optional[TCMReasoningStep]]


@dataclass(frozen=True)
class TCMReasoningRule:
    """规则注册项：rule_id + pattern + callable。"""

    rule_id: str
    pattern: str
    callable_: RuleCallable
    description: str = ""


def _filter_kind(premises: Sequence[TCMReasoningPremise], kind: str) -> List[TCMReasoningPremise]:
    return [p for p in premises if p.premise_kind == kind]


def _unique_canonicals(premises: Sequence[TCMReasoningPremise]) -> List[str]:
    seen: List[str] = []
    for p in premises:
        if p.canonical and p.canonical not in seen:
            seen.append(p.canonical)
    return seen


# ── 5 条核心规则 ──────────────────────────────────────────────────────


def rule_tongbing_yizhi(
    premises: Sequence[TCMReasoningPremise],
) -> Optional[TCMReasoningStep]:
    """同病异治：同一 symptom + 至少 2 个不同 syndrome → 应分别拟定治法。"""
    symptoms = _filter_kind(premises, "symptom")
    syndromes = _filter_kind(premises, "syndrome")
    if not symptoms:
        return None
    syndrome_names = _unique_canonicals(syndromes)
    if len(syndrome_names) < 2:
        return None
    primary_symptom = symptoms[0].canonical
    confidence = min(0.95, 0.55 + 0.1 * len(syndrome_names))
    conclusion = (
        f"症状『{primary_symptom}』在证候 {('、'.join(syndrome_names))} 下需采用不同治法（同病异治）。"
    )
    return TCMReasoningStep(
        rule_id="tongbing_yizhi",
        pattern=PATTERN_TONGBING_YIZHI,
        premises=[*symptoms, *syndromes],
        conclusion=conclusion,
        confidence=confidence,
        rationale=f"同一症状对应 {len(syndrome_names)} 个证候，触发同病异治范式。",
    )


def rule_yibing_tongzhi(
    premises: Sequence[TCMReasoningPremise],
) -> Optional[TCMReasoningStep]:
    """异病同治：同一 syndrome 出现在 ≥2 个不同 symptom 上 → 可统一治法。"""
    symptoms = _filter_kind(premises, "symptom")
    syndromes = _filter_kind(premises, "syndrome")
    if not syndromes:
        return None
    symptom_names = _unique_canonicals(symptoms)
    if len(symptom_names) < 2:
        return None
    primary_syndrome = syndromes[0].canonical
    confidence = min(0.93, 0.55 + 0.1 * len(symptom_names))
    conclusion = (
        f"证候『{primary_syndrome}』贯穿症状 {('、'.join(symptom_names))}，可施同一治法（异病同治）。"
    )
    return TCMReasoningStep(
        rule_id="yibing_tongzhi",
        pattern=PATTERN_YIBING_TONGZHI,
        premises=[*syndromes, *symptoms],
        conclusion=conclusion,
        confidence=confidence,
        rationale=f"同一证候横跨 {len(symptom_names)} 个症状，触发异病同治范式。",
    )


def rule_sanyin_zhiyi(
    premises: Sequence[TCMReasoningPremise],
) -> Optional[TCMReasoningStep]:
    """三因制宜：context 中含有 因时/因地/因人 任一线索即触发。"""
    contexts = _filter_kind(premises, "context")
    if not contexts:
        return None
    keywords = ("时", "季", "地", "域", "人", "体质", "年龄", "性别")
    hits = [c for c in contexts if any(k in c.canonical or k in c.label for k in keywords)]
    if not hits:
        return None
    factor_text = "、".join(_unique_canonicals(hits)) or "时地人因素"
    confidence = min(0.9, 0.5 + 0.1 * len(hits))
    return TCMReasoningStep(
        rule_id="sanyin_zhiyi",
        pattern=PATTERN_SANYIN_ZHIYI,
        premises=list(hits),
        conclusion=f"治法需结合 {factor_text} 调整（三因制宜）。",
        confidence=confidence,
        rationale=f"上下文命中 {len(hits)} 项时/地/人线索。",
    )


def rule_fangzheng_duiying(
    premises: Sequence[TCMReasoningPremise],
) -> Optional[TCMReasoningStep]:
    """方证对应：同时存在 formula + syndrome → 形成方证关系。"""
    formulas = _filter_kind(premises, "formula")
    syndromes = _filter_kind(premises, "syndrome")
    if not formulas or not syndromes:
        return None
    formula = formulas[0].canonical
    syndrome = syndromes[0].canonical
    confidence = 0.7 + min(0.2, 0.05 * (len(formulas) + len(syndromes)))
    return TCMReasoningStep(
        rule_id="fangzheng_duiying",
        pattern=PATTERN_FANGZHENG_DUIYING,
        premises=[*formulas, *syndromes],
        conclusion=f"方剂『{formula}』与证候『{syndrome}』构成方证对应。",
        confidence=min(0.95, confidence),
        rationale=f"同时具备 {len(formulas)} 个方剂前提与 {len(syndromes)} 个证候前提。",
    )


def rule_junchen_zuoshi(
    premises: Sequence[TCMReasoningPremise],
) -> Optional[TCMReasoningStep]:
    """君臣佐使：≥3 味 herb 出现 → 提示需做君臣佐使配伍分析。"""
    herbs = _filter_kind(premises, "herb")
    herb_names = _unique_canonicals(herbs)
    if len(herb_names) < 3:
        return None
    confidence = min(0.92, 0.5 + 0.06 * len(herb_names))
    head = "、".join(herb_names[:3])
    return TCMReasoningStep(
        rule_id="junchen_zuoshi",
        pattern=PATTERN_JUNCHEN_ZUOSHI,
        premises=list(herbs),
        conclusion=f"涉及药味 {head} 等 {len(herb_names)} 味，需按君臣佐使梳理配伍角色。",
        confidence=confidence,
        rationale=f"前提含 {len(herb_names)} 味独立药材，足以触发君臣佐使范式。",
    )


def build_default_rules() -> List[TCMReasoningRule]:
    """返回 5 条默认规则，顺序与 ``REASONING_PATTERNS`` 对齐。"""
    return [
        TCMReasoningRule("tongbing_yizhi", PATTERN_TONGBING_YIZHI, rule_tongbing_yizhi,
                         description=PATTERN_LABELS[PATTERN_TONGBING_YIZHI]),
        TCMReasoningRule("yibing_tongzhi", PATTERN_YIBING_TONGZHI, rule_yibing_tongzhi,
                         description=PATTERN_LABELS[PATTERN_YIBING_TONGZHI]),
        TCMReasoningRule("sanyin_zhiyi", PATTERN_SANYIN_ZHIYI, rule_sanyin_zhiyi,
                         description=PATTERN_LABELS[PATTERN_SANYIN_ZHIYI]),
        TCMReasoningRule("fangzheng_duiying", PATTERN_FANGZHENG_DUIYING, rule_fangzheng_duiying,
                         description=PATTERN_LABELS[PATTERN_FANGZHENG_DUIYING]),
        TCMReasoningRule("junchen_zuoshi", PATTERN_JUNCHEN_ZUOSHI, rule_junchen_zuoshi,
                         description=PATTERN_LABELS[PATTERN_JUNCHEN_ZUOSHI]),
    ]


DEFAULT_RULE_NAMES: tuple[str, ...] = tuple(r.rule_id for r in build_default_rules())


def apply_rule(
    rule: TCMReasoningRule,
    premises: Sequence[TCMReasoningPremise],
) -> Optional[TCMReasoningStep]:
    """安全地调用单条规则；任何异常均返回 ``None``。"""
    try:
        step = rule.callable_(premises)
    except Exception:
        return None
    if step is None:
        return None
    if step.pattern not in REASONING_PATTERNS:
        return None
    return step


def run_tcm_reasoning(
    premises: Sequence[TCMReasoningPremise],
    *,
    seed: str = "",
    rules: Optional[Sequence[TCMReasoningRule]] = None,
) -> TCMReasoningTrace:
    """运行所有规则并装配 :class:`TCMReasoningTrace`。"""
    rule_seq = list(rules) if rules else build_default_rules()
    premise_list = list(premises)
    steps: List[TCMReasoningStep] = []
    for rule in rule_seq:
        step = apply_rule(rule, premise_list)
        if step is not None:
            steps.append(step)

    coverage = sorted({s.pattern for s in steps})
    overall = (
        sum(s.confidence for s in steps) / len(steps) if steps else 0.0
    )
    notes = (
        f"触发 {len(steps)} 条规则，覆盖范式 {len(coverage)} / {len(REASONING_PATTERNS)}。"
        if steps else "未触发任何规则。"
    )
    return TCMReasoningTrace(
        seed=seed,
        premises=premise_list,
        steps=steps,
        overall_confidence=round(overall, 4),
        pattern_coverage=coverage,
        notes=notes,
    )


def build_tcm_reasoning_metadata(trace: TCMReasoningTrace) -> Dict[str, Any]:
    """把 trace 折叠为 8 个 metadata 字段，便于 reflect 阶段消费。"""
    pattern_counts: Counter[str] = Counter(s.pattern for s in trace.steps)
    return {
        "tcm_reasoning_step_count": len(trace.steps),
        "tcm_reasoning_pattern_coverage": list(trace.pattern_coverage),
        "tcm_reasoning_pattern_count": len(trace.pattern_coverage),
        "tcm_reasoning_overall_confidence": trace.overall_confidence,
        "tcm_reasoning_pattern_distribution": dict(pattern_counts),
        "tcm_reasoning_premise_count": len(trace.premises),
        "tcm_reasoning_notes": trace.notes,
        "tcm_reasoning_contract_version": CONTRACT_VERSION,
    }


__all__ = [
    "DEFAULT_RULE_NAMES",
    "TCMReasoningRule",
    "apply_rule",
    "build_default_rules",
    "build_tcm_reasoning_metadata",
    "rule_fangzheng_duiying",
    "rule_junchen_zuoshi",
    "rule_sanyin_zhiyi",
    "rule_tongbing_yizhi",
    "rule_yibing_tongzhi",
    "run_tcm_reasoning",
]
