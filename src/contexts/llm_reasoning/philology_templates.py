"""Philology task templates for Self-Discover style LLM reasoning."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

PHILOLOGY_REASONING_TEMPLATE_LIBRARY_VERSION = "philology-self-discover-templates-v1"

SUPPORTED_PHILOLOGY_TEMPLATE_TASKS: Tuple[str, ...] = (
    "entity_extraction",
    "relation_judgement",
    "variant_comparison",
    "evidence_grading",
    "hypothesis_generation",
    "counter_evidence_retrieval",
)

_TASK_ALIASES = {
    "entity": "entity_extraction",
    "entities": "entity_extraction",
    "entity_extract": "entity_extraction",
    "relation": "relation_judgement",
    "relationship": "relation_judgement",
    "relation_judgment": "relation_judgement",
    "relationship_judgement": "relation_judgement",
    "variant": "variant_comparison",
    "variant_reading": "variant_comparison",
    "evidence": "evidence_grading",
    "grade_evidence": "evidence_grading",
    "hypothesis": "hypothesis_generation",
    "counter_evidence": "counter_evidence_retrieval",
    "refutation": "counter_evidence_retrieval",
}


@dataclass(frozen=True)
class PhilologyReasoningTemplate:
    task_type: str
    template_id: str
    version: str
    role: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    forbidden_items: Tuple[str, ...]
    evidence_requirements: Tuple[str, ...]
    system_prompt: str
    user_prompt_template: str
    description: str = ""
    tags: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["contract_version"] = PHILOLOGY_REASONING_TEMPLATE_LIBRARY_VERSION
        return payload

    def metadata(self) -> Dict[str, Any]:
        return {
            "contract_version": PHILOLOGY_REASONING_TEMPLATE_LIBRARY_VERSION,
            "task_type": self.task_type,
            "template_id": self.template_id,
            "template_version": self.version,
            "version": self.version,
            "role": self.role,
        }


@dataclass(frozen=True)
class PhilologyRenderedPrompt:
    system_prompt: str
    user_prompt: str
    metadata: Dict[str, Any]
    template: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_philology_reasoning_template(task_type: str) -> PhilologyReasoningTemplate:
    normalized = _normalize_task_type(task_type)
    return _PHILOLOGY_TEMPLATES[normalized]


def select_philology_reasoning_template(
    task_type: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> PhilologyReasoningTemplate:
    context = context or {}
    requested = (
        task_type
        or context.get("philology_reasoning_task")
        or context.get("llm_reasoning_task")
        or context.get("llm_task_type")
        or "entity_extraction"
    )
    return get_philology_reasoning_template(str(requested))


def render_philology_reasoning_prompt(
    task_type: Optional[str] = None,
    payload: Optional[Mapping[str, Any]] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> PhilologyRenderedPrompt:
    template = select_philology_reasoning_template(task_type, context)
    payload = dict(payload or {})
    context_payload = dict(context or {})
    user_prompt = template.user_prompt_template.format(
        payload_json=_json_dumps(payload),
        context_json=_json_dumps(context_payload),
        input_schema_json=_json_dumps(template.input_schema),
        output_schema_json=_json_dumps(template.output_schema),
        forbidden_items="\n".join(f"- {item}" for item in template.forbidden_items),
        evidence_requirements="\n".join(
            f"- {item}" for item in template.evidence_requirements
        ),
    )
    return PhilologyRenderedPrompt(
        system_prompt=template.system_prompt,
        user_prompt=user_prompt,
        metadata=template.metadata(),
        template=template.to_dict(),
    )


def _normalize_task_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = _TASK_ALIASES.get(text, text)
    if text not in SUPPORTED_PHILOLOGY_TEMPLATE_TASKS:
        return "entity_extraction"
    return text


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _schema(required: Tuple[str, ...], properties: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "type": "object",
        "required": list(required),
        "properties": dict(properties),
    }


_BASE_USER_TEMPLATE = """请按指定文献学任务执行，不要泛化为普通知识抽取。

任务上下文：
{context_json}

输入 schema：
{input_schema_json}

输出 schema：
{output_schema_json}

禁止项：
{forbidden_items}

证据要求：
{evidence_requirements}

输入：
{payload_json}

只输出符合 output schema 的 JSON。"""


_PHILOLOGY_TEMPLATES: Dict[str, PhilologyReasoningTemplate] = {
    "entity_extraction": PhilologyReasoningTemplate(
        task_type="entity_extraction",
        template_id="philology.entity_extraction.v1",
        version="1.0.0",
        role="中医文献实体抽取与训诂标注审校员",
        input_schema=_schema(
            ("text",),
            {
                "text": {"type": "string"},
                "source_file": {"type": "string"},
                "dynasty": {"type": "string"},
                "known_terms": {"type": "array", "items": {"type": "string"}},
            },
        ),
        output_schema=_schema(
            ("entities", "relations"),
            {
                "entities": {"type": "array", "items": {"type": "object"}},
                "relations": {"type": "array", "items": {"type": "object"}},
            },
        ),
        forbidden_items=(
            "不得抽取无原文片段支持的实体",
            "同词多义时保留 sense_candidates，不强行给 sense_id",
            "不得把现代外推结论当作古籍原文实体",
        ),
        evidence_requirements=(
            "实体需能定位到原文短语",
            "关系必须来自同句或相邻语义片段",
            "版本、异文、校注类信息需保留来源字段",
        ),
        system_prompt="你是中医古籍知识蒸馏专家，严格按文献证据抽取实体与关系，只输出 JSON。",
        user_prompt_template=_BASE_USER_TEMPLATE,
        description="Extract TCM philology entities with source-bound evidence.",
        tags=("distill", "entity", "philology"),
    ),
    "relation_judgement": PhilologyReasoningTemplate(
        task_type="relation_judgement",
        template_id="philology.relation_judgement.v1",
        version="1.0.0",
        role="中医文献关系判定审查员",
        input_schema=_schema(
            ("candidate_relations", "evidence_segments"),
            {
                "candidate_relations": {"type": "array"},
                "evidence_segments": {"type": "array"},
            },
        ),
        output_schema=_schema(("judgements",), {"judgements": {"type": "array"}}),
        forbidden_items=(
            "不得把共现直接判作治疗、因果或组成关系",
            "不得忽略候选边的低置信度标记",
            "不得使用输入外知识补强关系",
        ),
        evidence_requirements=(
            "每条支持关系必须给出 evidence_quote 或 segment_id",
            "强关系需说明触发词、实体距离和证据等级",
            "证据不足时输出 candidate 或 unsupported",
        ),
        system_prompt="你是中医知识图谱关系审查员，负责把候选边分为支持、候选或不支持。",
        user_prompt_template=_BASE_USER_TEMPLATE,
        description="Judge whether candidate relations are supported by cited text.",
        tags=("relation", "evidence", "graph"),
    ),
    "variant_comparison": PhilologyReasoningTemplate(
        task_type="variant_comparison",
        template_id="philology.variant_comparison.v1",
        version="1.0.0",
        role="中医古籍异文比较与版本谱系审校员",
        input_schema=_schema(
            ("readings",),
            {"readings": {"type": "array"}, "edition_lineages": {"type": "array"}},
        ),
        output_schema=_schema(
            ("variant_groups",),
            {"variant_groups": {"type": "array"}, "lineage_notes": {"type": "array"}},
        ),
        forbidden_items=(
            "不得把不同版本文本合并为单一平文本",
            "不得在无 witness/source_ref 时断言版本先后",
            "不得删除可疑异文，只能标为待审",
        ),
        evidence_requirements=(
            "每个异文必须保留 witness_key、source_ref 或 segment_id",
            "说明 base_text 与 variant_text 的差异类型",
            "谱系判断需引用 base_witness_key 或明确标为 unknown",
        ),
        system_prompt="你是中医古籍校勘专家，专注异文、版本谱系和来源证据。",
        user_prompt_template=_BASE_USER_TEMPLATE,
        description="Compare variant readings across witnesses and editions.",
        tags=("variant", "edition", "lineage"),
    ),
    "evidence_grading": PhilologyReasoningTemplate(
        task_type="evidence_grading",
        template_id="philology.evidence_grading.v1",
        version="1.0.0",
        role="中医文献证据分级审查员",
        input_schema=_schema(
            ("claims", "evidence"),
            {
                "claims": {"type": "array"},
                "evidence": {"type": "array"},
                "counter_evidence": {"type": "array"},
            },
        ),
        output_schema=_schema(("graded_claims",), {"graded_claims": {"type": "array"}}),
        forbidden_items=(
            "不得用流畅表述替代证据等级",
            "不得把 candidate_observation 写成 formal_conclusion",
            "不得忽略反证或引用不匹配",
        ),
        evidence_requirements=(
            "A级证据需要原文、版本或专家复核至少两类支持",
            "存在反证时最高只能给 contested/候选结论，除非解释冲突",
            "缺引用或引用不匹配必须降级",
        ),
        system_prompt="你是中医科研证据分级审查员，输出可复核的证据等级 JSON。",
        user_prompt_template=_BASE_USER_TEMPLATE,
        description="Grade evidence strength and citation grounding.",
        tags=("evidence", "grading", "citation"),
    ),
    "hypothesis_generation": PhilologyReasoningTemplate(
        task_type="hypothesis_generation",
        template_id="philology.hypothesis_generation.v1",
        version="1.0.0",
        role="中医文献学假说生成研究员",
        input_schema=_schema(
            ("research_objective", "knowledge_gap"),
            {
                "research_objective": {"type": "string"},
                "knowledge_gap": {"type": "object"},
                "evidence_packages": {"type": "array"},
            },
        ),
        output_schema=_schema(("hypotheses",), {"hypotheses": {"type": "array"}}),
        forbidden_items=(
            "不得把知识缺口写成已证实结论",
            "不得忽略异文、版本差异和反证",
            "不得提出不可验证或无证据入口的假说",
        ),
        evidence_requirements=(
            "每条假说必须指向至少一个证据入口或待补证入口",
            "候选关系只能表述为假说、待证或需复核",
            "需要记录 evidence_grade 和 counter_evidence_handling",
        ),
        system_prompt="你是中医文献学科研假说生成专家，必须保持候选性和证据边界。",
        user_prompt_template=_BASE_USER_TEMPLATE,
        description="Generate cautious hypotheses from evidence gaps.",
        tags=("research_pipeline", "hypothesis", "self_discover"),
    ),
    "counter_evidence_retrieval": PhilologyReasoningTemplate(
        task_type="counter_evidence_retrieval",
        template_id="philology.counter_evidence_retrieval.v1",
        version="1.0.0",
        role="中医文献反证检索与冲突证据审查员",
        input_schema=_schema(
            ("claim", "search_context"),
            {
                "claim": {"type": "object"},
                "search_context": {"type": "object"},
                "known_evidence": {"type": "array"},
            },
        ),
        output_schema=_schema(
            ("counter_evidence",),
            {"counter_evidence": {"type": "array"}, "search_gaps": {"type": "array"}},
        ),
        forbidden_items=(
            "不得只检索支持性证据",
            "不得把沉默证据当作反证",
            "不得省略检索范围和未命中原因",
        ),
        evidence_requirements=(
            "反证需说明冲突点、来源和文本片段",
            "未找到反证时需返回 search_gaps",
            "版本差异导致的冲突必须保留 witness/source_ref",
        ),
        system_prompt="你是中医文献反证检索员，优先寻找能削弱或限定原主张的证据。",
        user_prompt_template=_BASE_USER_TEMPLATE,
        description="Retrieve and structure possible counter-evidence.",
        tags=("counter_evidence", "review", "retrieval"),
    ),
}


__all__ = [
    "PHILOLOGY_REASONING_TEMPLATE_LIBRARY_VERSION",
    "SUPPORTED_PHILOLOGY_TEMPLATE_TASKS",
    "PhilologyReasoningTemplate",
    "PhilologyRenderedPrompt",
    "get_philology_reasoning_template",
    "render_philology_reasoning_prompt",
    "select_philology_reasoning_template",
]
