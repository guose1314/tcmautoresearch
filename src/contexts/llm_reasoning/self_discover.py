"""Self-Discover reasoning plan builder for LLM gateway calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

from src.research.reasoning_template_selector import select_reasoning_framework

SUPPORTED_SELF_DISCOVER_TASKS = (
    "philology_exegesis",
    "formula_lineage",
    "pathogenesis_reasoning",
    "citation_synthesis",
)


@dataclass(frozen=True)
class SelfDiscoverStep:
    """One auditable step in a Self-Discover reasoning plan."""

    step_id: str
    title: str
    instruction: str
    required_evidence: List[str] = field(default_factory=list)
    failure_fallback: str = ""
    output_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "instruction": self.instruction,
            "required_evidence": list(self.required_evidence),
            "failure_fallback": self.failure_fallback,
            "output_key": self.output_key,
        }


@dataclass(frozen=True)
class SelfDiscoverPlan:
    """Self-Discover plan used to constrain a complex LLM reasoning task."""

    question: str
    task_type: str
    framework_id: str
    framework_display_name: str
    selected_modules: List[str] = field(default_factory=list)
    reasoning_steps: List[SelfDiscoverStep] = field(default_factory=list)
    evidence_slots: List[str] = field(default_factory=list)
    output_schema_hint: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "task_type": self.task_type,
            "framework_id": self.framework_id,
            "framework_display_name": self.framework_display_name,
            "selected_modules": list(self.selected_modules),
            "reasoning_steps": [step.to_dict() for step in self.reasoning_steps],
            "evidence_slots": list(self.evidence_slots),
            "output_schema_hint": dict(self.output_schema_hint),
            "warnings": list(self.warnings),
        }


def build_self_discover_plan(
    question: str,
    evidence_context: Mapping[str, Any] | None = None,
    task_type: str = "",
) -> SelfDiscoverPlan:
    """Build an auditable Self-Discover plan for a complex TCM literature task."""

    normalized_question = str(question or "").strip()
    context = dict(evidence_context or {})
    normalized_task_type, warnings = _normalize_task_type(task_type, context)
    framework = select_reasoning_framework(normalized_question, context)
    template = _TASK_TEMPLATES[normalized_task_type]

    steps = [
        SelfDiscoverStep(
            step_id=str(item["step_id"]),
            title=str(item["title"]),
            instruction=str(item["instruction"]),
            required_evidence=_normalize_strings(item.get("required_evidence") or []),
            failure_fallback=str(item["failure_fallback"]),
            output_key=str(item["output_key"]),
        )
        for item in template["steps"]
    ]
    evidence_slots = _merge_evidence_slots(steps, template.get("evidence_slots") or [])
    selected_modules = _merge_strings(
        [f"framework:{framework.framework_id}"],
        template.get("selected_modules") or [],
        [f"evidence_slot:{slot}" for slot in evidence_slots],
    )
    output_schema_hint = _build_output_schema_hint(
        normalized_task_type,
        framework.framework_id,
        evidence_slots,
        [step.output_key for step in steps],
    )

    return SelfDiscoverPlan(
        question=normalized_question,
        task_type=normalized_task_type,
        framework_id=framework.framework_id,
        framework_display_name=framework.display_name,
        selected_modules=selected_modules,
        reasoning_steps=steps,
        evidence_slots=evidence_slots,
        output_schema_hint=output_schema_hint,
        warnings=warnings,
    )


def _normalize_task_type(
    task_type: str,
    context: Mapping[str, Any],
) -> tuple[str, List[str]]:
    text = str(task_type or context.get("task_type") or "").strip().lower()
    aliases = {
        "exegesis": "philology_exegesis",
        "philology": "philology_exegesis",
        "textual_exegesis": "philology_exegesis",
        "formula": "formula_lineage",
        "lineage": "formula_lineage",
        "formula_evolution": "formula_lineage",
        "pathogenesis": "pathogenesis_reasoning",
        "tcm_reasoning": "pathogenesis_reasoning",
        "syndrome_reasoning": "pathogenesis_reasoning",
        "citation": "citation_synthesis",
        "grounding": "citation_synthesis",
        "literature_review": "citation_synthesis",
    }
    normalized = aliases.get(text, text)
    if normalized in SUPPORTED_SELF_DISCOVER_TASKS:
        return normalized, []
    return "citation_synthesis", [f"unsupported_task_type:{text or 'empty'}"]


def _merge_evidence_slots(
    steps: Sequence[SelfDiscoverStep],
    configured_slots: Sequence[Any],
) -> List[str]:
    return _merge_strings(
        configured_slots,
        *(step.required_evidence for step in steps),
    )


def _build_output_schema_hint(
    task_type: str,
    framework_id: str,
    evidence_slots: Sequence[str],
    step_output_keys: Sequence[str],
) -> Dict[str, Any]:
    return {
        "type": "object",
        "task_type": task_type,
        "framework_id": framework_id,
        "required": [
            "answer",
            "reasoning_trace",
            "evidence_usage",
            "uncertainty_note",
        ],
        "properties": {
            "answer": {"type": "string"},
            "reasoning_trace": {
                "type": "object",
                "required_step_outputs": list(step_output_keys),
            },
            "evidence_usage": {
                "type": "object",
                "required_evidence_slots": list(evidence_slots),
            },
            "uncertainty_note": {"type": "string"},
        },
    }


def _merge_strings(*groups: Sequence[Any]) -> List[str]:
    merged: List[str] = []
    for group in groups:
        for item in _normalize_strings(group):
            if item not in merged:
                merged.append(item)
    return merged


def _normalize_strings(values: Sequence[Any]) -> List[str]:
    return [str(item).strip() for item in values if str(item).strip()]


_TASK_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "philology_exegesis": {
        "selected_modules": [
            "contextual_term_disambiguation",
            "variant_reading_check",
            "source_attribution",
            "philology_review_gate",
        ],
        "evidence_slots": [
            "term_context",
            "version_witness",
            "collation_note",
            "exegesis_history",
        ],
        "steps": [
            {
                "step_id": "philology_exegesis.resolve_term_scope",
                "title": "界定义项语境",
                "instruction": "识别待释术语、上下文窗口、朝代与学派语境，避免脱离原文释义。",
                "required_evidence": ["term_context", "source_text"],
                "failure_fallback": "若缺少上下文，只输出候选义项并标记 needs_context_review。",
                "output_key": "term_scope",
            },
            {
                "step_id": "philology_exegesis.compare_witnesses",
                "title": "核对版本异文",
                "instruction": "比较 witness 与校勘记录，判断释义是否受异文、脱文或衍文影响。",
                "required_evidence": ["version_witness", "collation_note"],
                "failure_fallback": "若无 witness，降级为 single_text_interpretation 并降低置信度。",
                "output_key": "variant_impact",
            },
            {
                "step_id": "philology_exegesis.ground_exegesis",
                "title": "形成训诂依据",
                "instruction": "把义项判断绑定到注疏、引文或版本证据，输出可复核依据。",
                "required_evidence": ["exegesis_history", "citation_ref"],
                "failure_fallback": "若无注疏或引文，仅给出解释假设并标记 unsupported_exegesis。",
                "output_key": "grounded_exegesis",
            },
        ],
    },
    "formula_lineage": {
        "selected_modules": [
            "formula_identity_resolution",
            "version_lineage_mapping",
            "composition_delta_analysis",
            "lineage_claim_grounding",
        ],
        "evidence_slots": [
            "formula_name",
            "version_witness",
            "herb_composition",
            "lineage_edge",
        ],
        "steps": [
            {
                "step_id": "formula_lineage.resolve_formula_identity",
                "title": "识别方名与同名异方",
                "instruction": "先判断方名、别名、同名异方和出处，避免把不同方剂沿革混为一谈。",
                "required_evidence": ["formula_name", "source_ref"],
                "failure_fallback": "若方名来源不清，输出 identity_ambiguous 并停止生成强沿革结论。",
                "output_key": "formula_identity",
            },
            {
                "step_id": "formula_lineage.map_lineage",
                "title": "映射版本沿革",
                "instruction": "按版本 witness、时代和引用关系排列方剂沿革路径。",
                "required_evidence": ["version_witness", "lineage_edge"],
                "failure_fallback": "若沿革边不足，降级为 unordered_source_comparison。",
                "output_key": "lineage_path",
            },
            {
                "step_id": "formula_lineage.compare_composition",
                "title": "比较药味变化",
                "instruction": "比较药味增删、剂量或配伍结构变化，并区分文本异文与真实方义变化。",
                "required_evidence": ["herb_composition", "collation_note"],
                "failure_fallback": "若缺少组成证据，只报告来源差异，不推断配伍演变。",
                "output_key": "composition_delta",
            },
        ],
    },
    "pathogenesis_reasoning": {
        "selected_modules": [
            "syndrome_signal_extraction",
            "pathomechanism_chain_builder",
            "treatment_principle_mapping",
            "premise_consistency_check",
        ],
        "evidence_slots": [
            "syndrome",
            "symptom",
            "pathogenesis_factor",
            "treatment_principle",
            "formula_or_herb",
        ],
        "steps": [
            {
                "step_id": "pathogenesis_reasoning.extract_syndrome_signals",
                "title": "抽取证候信号",
                "instruction": "从症状、舌脉、病位病性中抽取证候信号，并标出冲突证据。",
                "required_evidence": ["syndrome", "symptom"],
                "failure_fallback": "若证候证据不足，只输出 possible_patterns 并要求人工复核。",
                "output_key": "syndrome_signals",
            },
            {
                "step_id": "pathogenesis_reasoning.build_causal_chain",
                "title": "构建病机链",
                "instruction": "把病因、病位、病性与传变关系串成因果链，避免跳步推断。",
                "required_evidence": ["pathogenesis_factor", "source_text"],
                "failure_fallback": "若病机因果链缺失，降级为 correlation_only。",
                "output_key": "pathomechanism_chain",
            },
            {
                "step_id": "pathogenesis_reasoning.map_treatment",
                "title": "映射治法方药",
                "instruction": "将证候和病机映射到治则治法、方剂或药物前提，并检查方证一致性。",
                "required_evidence": ["treatment_principle", "formula_or_herb"],
                "failure_fallback": "若治法证据不足，不输出确定性推荐，只给出候选治法。",
                "output_key": "treatment_mapping",
            },
        ],
    },
    "citation_synthesis": {
        "selected_modules": [
            "claim_extraction",
            "citation_retrieval",
            "support_level_assessment",
            "unsupported_claim_guard",
        ],
        "evidence_slots": [
            "claim",
            "citation_ref",
            "evidence_claim",
            "version_witness",
            "support_level",
        ],
        "steps": [
            {
                "step_id": "citation_synthesis.extract_claims",
                "title": "拆分待支持观点",
                "instruction": "把问题或段落拆成可验证 claim，避免一个引用支撑多个不同观点。",
                "required_evidence": ["claim"],
                "failure_fallback": "若 claim 不可拆分，输出 claim_too_broad 并要求重写。",
                "output_key": "claim_units",
            },
            {
                "step_id": "citation_synthesis.match_citations",
                "title": "匹配出处与证据声明",
                "instruction": "为每个 claim 匹配 citation、EvidenceClaim 与版本 witness，记录无法匹配项。",
                "required_evidence": [
                    "citation_ref",
                    "evidence_claim",
                    "version_witness",
                ],
                "failure_fallback": "若缺少证据链，标记 unsupported_claim，不生成强结论。",
                "output_key": "citation_matches",
            },
            {
                "step_id": "citation_synthesis.grade_support",
                "title": "评估支持强度",
                "instruction": "按 strong/moderate/weak/unsupported 评估每条 claim 的证据支持。",
                "required_evidence": ["support_level", "evidence_claim"],
                "failure_fallback": "若支持等级无法判断，默认为 weak 并写明 uncertainty_note。",
                "output_key": "support_assessment",
            },
        ],
    },
}


__all__ = [
    "SUPPORTED_SELF_DISCOVER_TASKS",
    "SelfDiscoverPlan",
    "SelfDiscoverStep",
    "build_self_discover_plan",
]
