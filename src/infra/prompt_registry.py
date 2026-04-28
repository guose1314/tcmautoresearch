"""Prompt Registry + JSON Schema 输出约束。

将高价值 LLM prompt 统一注册，并为结构化输出附加轻量 JSON Schema
约束与校验，降低本地 7B 模型自由发挥导致的幻觉与格式漂移。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, Optional

from src.infra.layered_cache import describe_llm_engine, get_layered_task_cache
from src.infra.token_budget_policy import apply_token_budget_to_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptTemplate:
    """单条 prompt 规范定义。

    版本字段说明（T2.1 引入）：

    - ``version``：prompt 自身的语义版本号（默认 ``"v1"``）。
    - ``parent_version``：本版本的上一版（用于追溯演化链；初版为 ``None``）。
    - ``schema_version``：输出 schema 的语义版本号（默认 ``"v1"``）；schema 形态变更时
      必须同时升级该字段，并由 ``call_registered_prompt`` 注入缓存键，避免旧缓存命中。
    """

    name: str
    purpose: str
    task: str
    system_prompt: str
    user_template: str
    output_kind: str = "text"
    output_schema: Optional[Dict[str, Any]] = None
    version: str = "v1"
    parent_version: Optional[str] = None
    schema_version: str = "v1"


@dataclass(frozen=True)
class RenderedPrompt:
    """渲染后的 prompt 载荷。"""

    name: str
    purpose: str
    task: str
    system_prompt: str
    user_prompt: str
    output_kind: str
    output_schema: Optional[Dict[str, Any]] = None
    version: str = "v1"
    schema_version: str = "v1"


@dataclass(frozen=True)
class PromptValidationResult:
    """结构化输出提取与校验结果。"""

    name: str
    parsed: Any = None
    schema_valid: bool = False
    errors: tuple[str, ...] = ()


DEFAULT_PROMPT_REGISTRY_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "include_schema_in_prompt": True,
    "fail_on_schema_validation": False,
    "max_schema_chars": 4000,
}


_RESEARCH_ADVISOR_HYPOTHESIS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": ["hypothesis", "confidence", "rationale", "suggested_methods"],
        "properties": {
            "hypothesis": {"type": "string", "minLength": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "suggested_methods": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
}


_RESEARCH_ADVISOR_EXPERIMENT_SCHEMA = {
    "type": "object",
    "required": [
        "study_type",
        "sample_size",
        "methods",
        "controls",
        "variables",
        "expected_outcomes",
        "statistical_analysis",
        "ethical_considerations",
    ],
    "properties": {
        "study_type": {"type": "string", "minLength": 1},
        "sample_size": {"type": "string", "minLength": 1},
        "methods": {"type": "array", "items": {"type": "string"}},
        "controls": {"type": "string", "minLength": 1},
        "variables": {"type": "object"},
        "expected_outcomes": {"type": "string", "minLength": 1},
        "statistical_analysis": {"type": "string", "minLength": 1},
        "ethical_considerations": {"type": "string", "minLength": 1},
    },
}


_RESEARCH_ADVISOR_NOVELTY_SCHEMA = {
    "type": "object",
    "required": [
        "novelty_score",
        "novelty_level",
        "overlapping_studies",
        "unique_aspects",
        "improvement_suggestions",
    ],
    "properties": {
        "novelty_score": {"type": "number", "minimum": 0, "maximum": 10},
        "novelty_level": {"type": "string", "minLength": 1},
        "overlapping_studies": {"type": "array", "items": {"type": "string"}},
        "unique_aspects": {"type": "array", "items": {"type": "string"}},
        "improvement_suggestions": {"type": "array", "items": {"type": "string"}},
    },
}


_HYPOTHESIS_ENGINE_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "required": [
            "title",
            "statement",
            "rationale",
            "novelty",
            "feasibility",
            "evidence_support",
            "validation_plan",
            "keywords",
        ],
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "statement": {"type": "string", "minLength": 1},
            "rationale": {"type": "string", "minLength": 1},
            "novelty": {"type": "number", "minimum": 0, "maximum": 1},
            "feasibility": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_support": {"type": "number", "minimum": 0, "maximum": 1},
            "validation_plan": {"type": "string", "minLength": 1},
            "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "source_gap_type": {"type": "string"},
            "source_entities": {"type": "array", "items": {"type": "string"}},
            # T2.4: methodology + hypothesis-level evidence grade
            "methodology_tag": {
                "type": "string",
                "enum": ["philology", "classification", "evidence_based"],
            },
            "evidence_grade": {
                "type": ["string", "null"],
                "enum": ["A", "B", "C", "D", None],
            },
        },
    },
}


_GAP_ANALYZER_SCHEMA = {
    "type": "object",
    "required": [
        "clinical_question",
        "coverage_overview",
        "gaps",
        "priority_summary",
        "recommendations",
    ],
    "properties": {
        "clinical_question": {"type": "string", "minLength": 1},
        "coverage_overview": {
            "type": "object",
            "properties": {
                "literature_count": {"type": "integer", "minimum": 0},
                "condition_covered": {"type": "boolean"},
                "intervention_covered": {"type": "boolean"},
                "outcome_count": {"type": "integer", "minimum": 0},
                "method_count": {"type": "integer", "minimum": 0},
                "knowledge_signal_count": {"type": "integer", "minimum": 0},
            },
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension", "title", "limitation", "priority"],
                "properties": {
                    "dimension": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "limitation": {"type": "string"},
                    "priority": {"type": "string", "minLength": 1},
                },
            },
        },
        "priority_summary": {
            "type": "object",
            "required": ["counts", "highest_priority", "total_gaps"],
            "properties": {
                "counts": {"type": "object"},
                "highest_priority": {"type": "string", "minLength": 1},
                "total_gaps": {"type": "integer", "minimum": 0},
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["study_design", "inclusion_criteria", "primary_endpoint"],
                "properties": {
                    "study_design": {"type": "string", "minLength": 1},
                    "inclusion_criteria": {"type": "string", "minLength": 1},
                    "primary_endpoint": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


PROMPT_REGISTRY: Dict[str, PromptTemplate] = {
    "research_advisor.hypothesis_suggestion": PromptTemplate(
        name="research_advisor.hypothesis_suggestion",
        purpose="assistant",
        task="hypothesis_generation",
        system_prompt=(
            "你是一位中医药科研方法学专家。请根据给定主题和已有文献摘要，"
            "生成 2-3 条可检验的科研假说，不得编造证据。"
        ),
        user_template=(
            "【研究主题】\n{topic}\n{literature_section}请生成 2-3 条可检验的科研假说。"
        ),
        output_kind="json_array",
        output_schema=_RESEARCH_ADVISOR_HYPOTHESIS_SCHEMA,
    ),
    "research_advisor.experiment_design": PromptTemplate(
        name="research_advisor.experiment_design",
        purpose="assistant",
        task="structured_summary",
        system_prompt=(
            "你是一位中医药临床与实验研究设计专家。"
            "请围绕给定假说设计完整、可执行、可复核的实验方案。"
        ),
        user_template=("【研究假说】\n{hypothesis}\n\n请设计完整的实验方案。"),
        output_kind="json_object",
        output_schema=_RESEARCH_ADVISOR_EXPERIMENT_SCHEMA,
    ),
    "research_advisor.novelty_evaluation": PromptTemplate(
        name="research_advisor.novelty_evaluation",
        purpose="assistant",
        task="structured_summary",
        system_prompt=(
            "你是一位中医药学术评审专家。请评估给定假说相对于已有文献的创新性，"
            "结论必须有文献摘要支撑。"
        ),
        user_template=(
            "【研究假说】\n{hypothesis}\n{literature_section}请评估该假说的创新性。"
        ),
        output_kind="json_object",
        output_schema=_RESEARCH_ADVISOR_NOVELTY_SCHEMA,
    ),
    "gap_analyzer.structured_report": PromptTemplate(
        name="gap_analyzer.structured_report",
        purpose="default",
        task="structured_summary",
        system_prompt=(
            "你是中医临床研究方法学专家与证据综合分析师。"
            "请基于输入数据与预分析结果形成严谨结论，不得编造文献。"
        ),
        user_template=(
            "请基于以下 JSON 输入执行临床/知识缺口分析。\n"
            "输入数据：\n{analysis_input}\n\n"
            "要求：\n{requirements}"
        ),
        output_kind="json_object",
        output_schema=_GAP_ANALYZER_SCHEMA,
    ),
    "hypothesis_engine.default_hypothesis": PromptTemplate(
        name="hypothesis_engine.default_hypothesis",
        purpose="default",
        task="hypothesis_generation",
        system_prompt=(
            "你是中医科研假设生成专家。"
            "请基于知识图谱缺口、文献线索和上下文，提出可验证、具备创新性的科研假设。"
            "禁止编造不存在的证据，输出必须聚焦中医药研究场景。"
        ),
        user_template=(
            "请围绕以下知识缺口生成 3 条中医科研假设。\n\n"
            "知识缺口类型：{gap_type}\n"
            "核心实体：{entities}\n"
            "缺口描述：{description}\n"
            "上下文摘要：{context_summary}\n\n"
            "{dynamic_few_shot}"
        ),
        output_kind="json_array",
        output_schema=_HYPOTHESIS_ENGINE_SCHEMA,
    ),
    "hypothesis_engine.kg_enhanced": PromptTemplate(
        name="hypothesis_engine.kg_enhanced",
        purpose="default",
        task="graph_reasoning",
        system_prompt=(
            "你是中医科研假设生成专家。请基于知识图谱缺口分析与结构证据生成高质量研究假设，"
            "并为每条假设标注来源缺口类型与相关实体。"
        ),
        user_template=(
            "你是中医科研假设生成专家。请基于以下知识图谱缺口分析生成高质量研究假设。\n\n"
            "## 知识图谱缺口分析\n\n"
            "共发现 {gap_count} 个知识缺口：\n{gap_details}\n\n"
            "## 图谱结构摘要\n\n"
            "{kg_structure_summary}\n\n"
            "## 研究上下文\n\n"
            "{context_summary}\n\n"
            "{dynamic_few_shot}"
            "## 要求\n\n"
            "请基于上述图谱缺口和结构信息，生成 {num_hypotheses} 条可验证的中医科研假设。"
        ),
        output_kind="json_array",
        output_schema=_HYPOTHESIS_ENGINE_SCHEMA,
    ),
    # ------------------------------------------------------------------ #
    # T4.3 Self-Refine 通用模板：<purpose>.draft / .critique / .refine
    # ``purpose`` 字段在此处仅用于注册表分桶；运行时由 SelfRefineRunner 按
    # 实际业务 purpose 动态选择不同 prompt name 前缀（如 "self_refine.draft"
    # 即默认通用模板，业务方亦可注册 "<purpose>.draft" 覆盖之）。
    # ------------------------------------------------------------------ #
    "self_refine.draft": PromptTemplate(
        name="self_refine.draft",
        purpose="self_refine",
        task="draft",
        system_prompt=(
            "你是该任务的领域专家。请根据用户输入产出高质量初稿，"
            "结构化、有据可依，避免空泛与编造。"
        ),
        user_template=(
            "【任务】\n{task_description}\n\n"
            "【输入】\n{input_payload}\n\n"
            "请输出初稿。"
        ),
        output_kind="text",
    ),
    "self_refine.critique": PromptTemplate(
        name="self_refine.critique",
        purpose="self_refine",
        task="critique",
        system_prompt=(
            "你是严格的同行评审。请对给定初稿做逐条批判，"
            "聚焦事实准确性、字段完整性、医学合规性与逻辑一致性。"
            "只指出问题，不要重写答案。"
        ),
        user_template=(
            "【任务】\n{task_description}\n\n"
            "【初稿】\n{draft}\n\n"
            "请逐条列出 issues（每条包含 field 与 issue 描述），"
            "按严重度从高到低排序，使用 JSON 数组输出。"
        ),
        output_kind="json_array",
        output_schema={
            "type": "array",
            "items": {
                "type": "object",
                "required": ["field", "issue"],
                "properties": {
                    "field": {"type": "string"},
                    "issue": {"type": "string"},
                    "severity": {"type": "string"},
                },
            },
        },
    ),
    "self_refine.refine": PromptTemplate(
        name="self_refine.refine",
        purpose="self_refine",
        task="refine",
        system_prompt=(
            "你是任务的最终交付者。请基于初稿与同行评审 issues 给出修订版，"
            "必须显式覆盖 issues 中提到的每个 field，并保持其余部分不退化。"
        ),
        user_template=(
            "【任务】\n{task_description}\n\n"
            "【初稿】\n{draft}\n\n"
            "【同行评审 Issues（必须逐条解决）】\n{issues}\n\n"
            "请输出修订后的最终版本。"
        ),
        output_kind="text",
    ),
}


def _build_versioned_registry(
    flat: Dict[str, PromptTemplate],
) -> Dict[str, Dict[str, PromptTemplate]]:
    """把扁平 ``name -> template`` 注册表展开为 ``name -> version -> template``。"""

    versioned: Dict[str, Dict[str, PromptTemplate]] = {}
    for name, spec in flat.items():
        versioned.setdefault(name, {})[spec.version] = spec
    return versioned


# ``name -> version -> PromptTemplate``；``PROMPT_REGISTRY`` 始终指向每个 name 的 latest。
_VERSIONED_PROMPT_REGISTRY: Dict[str, Dict[str, PromptTemplate]] = (
    _build_versioned_registry(PROMPT_REGISTRY)
)


def _latest_version(name: str) -> str:
    """返回某 prompt 的最新版本号（按字典序倒序，约定 ``vN`` 形式可比较）。"""

    versions = _VERSIONED_PROMPT_REGISTRY.get(name)
    if not versions:
        raise KeyError(f"未注册的 prompt: {name}")
    return sorted(versions.keys())[-1]


def register_prompt_version(template: PromptTemplate) -> None:
    """注册某 prompt 的新版本；同时更新扁平注册表为最新版。

    主要用于运行时扩展或测试注入（如 T2.1 单测）。生产代码请直接在
    ``PROMPT_REGISTRY`` 字面量中追加新版本。
    """

    bucket = _VERSIONED_PROMPT_REGISTRY.setdefault(template.name, {})
    bucket[template.version] = template
    PROMPT_REGISTRY[template.name] = bucket[_latest_version(template.name)]


def get_prompt_template(name: str, version: str = "latest") -> PromptTemplate:
    """获取注册表中的 prompt 定义。

    - ``version="latest"``（默认）：返回该 name 当前最新版本，与历史调用兼容。
    - 显式版本号：返回对应版本，找不到则抛 ``KeyError``。
    """

    versions = _VERSIONED_PROMPT_REGISTRY.get(name)
    if not versions:
        raise KeyError(f"未注册的 prompt: {name}")
    if version == "latest":
        return versions[_latest_version(name)]
    try:
        return versions[version]
    except KeyError as exc:
        available = sorted(versions.keys())
        raise KeyError(
            f"prompt {name!r} 不存在版本 {version!r}，可选: {available}"
        ) from exc


def list_prompt_versions(name: str) -> list[str]:
    """返回某 prompt 已注册的所有版本号（升序）。"""

    versions = _VERSIONED_PROMPT_REGISTRY.get(name)
    if not versions:
        raise KeyError(f"未注册的 prompt: {name}")
    return sorted(versions.keys())


def list_prompt_names() -> list[str]:
    """返回所有已注册 prompt 名称。"""

    return sorted(PROMPT_REGISTRY)


def get_registry_summary() -> Dict[str, Any]:
    """返回注册表摘要。"""

    kinds: Dict[str, int] = {}
    for spec in PROMPT_REGISTRY.values():
        kinds[spec.output_kind] = kinds.get(spec.output_kind, 0) + 1
    return {
        "total_prompts": len(PROMPT_REGISTRY),
        "output_kinds": kinds,
        "purposes": sorted({spec.purpose for spec in PROMPT_REGISTRY.values()}),
    }


def export_prompt_registry_snapshot() -> Dict[str, Any]:
    """导出 benchmark replay 用的确定性 prompt registry 快照。

    Phase I / I-2: 用于让 phase benchmark 在 JSON 报告中固化当时使用的
    prompt 模板版本，从而支持 "同一 case 多次 replay 得到一致 prompt 结构"
    的判定，并方便回归对比。返回结构按名字稳定排序，每条携带 system + user
    模板的 sha256 指纹与是否带 schema。
    """

    import hashlib

    entries: list[Dict[str, Any]] = []
    for name in sorted(PROMPT_REGISTRY):
        spec = PROMPT_REGISTRY[name]
        body = "\n--\n".join([spec.system_prompt or "", spec.user_template or ""])
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        entries.append(
            {
                "name": name,
                "purpose": spec.purpose,
                "task": spec.task,
                "output_kind": spec.output_kind,
                "has_schema": spec.output_schema is not None,
                "fingerprint": digest,
                "version": spec.version,
                "schema_version": spec.schema_version,
            }
        )
    aggregate = "\n".join(
        f"{e['name']}@{e['version']}/{e['schema_version']}:{e['fingerprint']}"
        for e in entries
    )
    return {
        "total_prompts": len(entries),
        "fingerprint": hashlib.sha256(aggregate.encode("utf-8")).hexdigest(),
        "entries": entries,
    }


@lru_cache(maxsize=1)
def load_prompt_registry_settings() -> Dict[str, Any]:
    """从配置加载 Prompt Registry 行为开关。"""

    try:
        from src.infrastructure.config_loader import load_settings_section

        payload = load_settings_section("models.llm.prompt_registry", default={})
    except Exception:
        payload = {}
    resolved = dict(DEFAULT_PROMPT_REGISTRY_SETTINGS)
    if isinstance(payload, dict):
        resolved.update(payload)
    return resolved


def reset_prompt_registry_settings_cache() -> None:
    """清空配置缓存，供测试使用。"""

    load_prompt_registry_settings.cache_clear()


def render_prompt(
    name: str,
    *,
    system_prompt_override: Optional[str] = None,
    user_template_override: Optional[str] = None,
    **variables: Any,
) -> RenderedPrompt:
    """渲染注册 prompt，并在需要时自动追加 JSON Schema 约束。"""

    spec = get_prompt_template(name)
    system_prompt = (
        spec.system_prompt if system_prompt_override is None else system_prompt_override
    )
    user_template = (
        spec.user_template if user_template_override is None else user_template_override
    )
    user_prompt = user_template.format(**variables).rstrip()
    schema_instruction = ""

    settings = load_prompt_registry_settings()
    if (
        settings.get("enabled", True)
        and settings.get("include_schema_in_prompt", True)
        and spec.output_schema
    ):
        schema_instruction = _build_schema_instruction(
            spec.output_kind, spec.output_schema, settings
        )

    budgeted = apply_token_budget_to_prompt(
        user_prompt,
        system_prompt=str(system_prompt or "").strip(),
        task=spec.task,
        purpose=spec.purpose,
        suffix_prompt=schema_instruction,
    )

    return RenderedPrompt(
        name=spec.name,
        purpose=spec.purpose,
        task=spec.task,
        system_prompt=budgeted.system_prompt,
        user_prompt=budgeted.user_prompt,
        output_kind=spec.output_kind,
        output_schema=spec.output_schema,
        version=spec.version,
        schema_version=spec.schema_version,
    )


def call_registered_prompt(
    llm_engine: Any,
    name: str,
    *,
    rendered: Optional[RenderedPrompt] = None,
    system_prompt_override: Optional[str] = None,
    user_template_override: Optional[str] = None,
    **variables: Any,
) -> str:
    """使用注册 prompt 调用任意支持 generate() 的 LLM 引擎。"""

    if llm_engine is None or not hasattr(llm_engine, "generate"):
        raise RuntimeError(
            "Prompt Registry 需要支持 generate(prompt, system_prompt) 的 llm_engine"
        )

    resolved_prompt = rendered or render_prompt(
        name,
        system_prompt_override=system_prompt_override,
        user_template_override=user_template_override,
        **variables,
    )
    llm_descriptor = describe_llm_engine(llm_engine)
    cache_payload = {
        "cache_version": "prompt-cache-v1",
        "prompt_name": resolved_prompt.name,
        "prompt_version": resolved_prompt.version,
        "schema_version": resolved_prompt.schema_version,
        "purpose": resolved_prompt.purpose,
        "task": resolved_prompt.task,
        "output_kind": resolved_prompt.output_kind,
        "output_schema": resolved_prompt.output_schema,
        "system_prompt": resolved_prompt.system_prompt,
        "user_prompt": resolved_prompt.user_prompt,
        "llm": llm_descriptor,
    }

    task_cache = get_layered_task_cache()
    cached = task_cache.get_text("prompt", resolved_prompt.name, cache_payload)
    if cached is not None:
        return cached

    response = str(
        llm_engine.generate(
            resolved_prompt.user_prompt, system_prompt=resolved_prompt.system_prompt
        )
    )
    task_cache.put_text(
        "prompt",
        resolved_prompt.name,
        cache_payload,
        response,
        meta={
            "purpose": resolved_prompt.purpose,
            "task": resolved_prompt.task,
            "output_kind": resolved_prompt.output_kind,
            "llm": llm_descriptor,
        },
    )
    return response


def parse_registered_output(name: str, raw: Any) -> PromptValidationResult:
    """按注册表 schema 提取并校验结构化输出。"""

    spec = get_prompt_template(name)
    expected_root = None
    if spec.output_kind == "json_object":
        expected_root = "object"
    elif spec.output_kind == "json_array":
        expected_root = "array"

    parsed = _extract_json_payload(raw, expected_root=expected_root)
    if parsed is None:
        errors = ("未提取到合法 JSON",)
        return PromptValidationResult(
            name=name, parsed=None, schema_valid=False, errors=errors
        )

    if not spec.output_schema:
        return PromptValidationResult(
            name=name, parsed=parsed, schema_valid=True, errors=()
        )

    errors = tuple(_validate_schema(parsed, spec.output_schema))
    if errors:
        logger.info("Prompt %s 输出未完全匹配 schema: %s", name, "; ".join(errors[:3]))
    return PromptValidationResult(
        name=name,
        parsed=parsed,
        schema_valid=not errors,
        errors=errors,
    )


def _build_schema_instruction(
    output_kind: str, schema: Dict[str, Any], settings: Dict[str, Any]
) -> str:
    root_name = {
        "json_object": "JSON 对象",
        "json_array": "JSON 数组",
    }.get(output_kind, "JSON")
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
    max_chars = max(256, int(settings.get("max_schema_chars", 4000) or 4000))
    if len(schema_text) > max_chars:
        schema_text = f"{schema_text[:max_chars].rstrip()}\n..."
    return (
        "输出约束：\n"
        f"1. 只输出单个 {root_name}，不要输出 Markdown、代码围栏、解释或额外前后缀。\n"
        "2. 字段名必须严格遵守下方 JSON Schema。\n"
        "3. 不确定时使用空字符串、空数组、空对象或 0，不要发明新字段。\n"
        "4. 所有输出必须是合法 JSON。\n"
        "JSON Schema:\n"
        f"{schema_text}"
    )


def _extract_json_payload(raw: Any, *, expected_root: Optional[str] = None) -> Any:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return raw

    text = str(raw or "").strip()
    if not text:
        return None

    for candidate in _candidate_json_texts(text, expected_root=expected_root):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if expected_root == "object" and not isinstance(payload, dict):
            continue
        if expected_root == "array" and not isinstance(payload, list):
            continue
        return payload
    return None


def _candidate_json_texts(
    text: str, *, expected_root: Optional[str] = None
) -> Iterable[str]:
    candidates: list[str] = [text]

    for match in re.finditer(
        r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL
    ):
        fenced = str(match.group(1) or "").strip()
        if fenced:
            candidates.append(fenced)

    if expected_root in (None, "object"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidates.append(text[start : end + 1].strip())

    if expected_root in (None, "array"):
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            candidates.append(text[start : end + 1].strip())

    seen: set[str] = set()
    for item in candidates:
        if not item or item in seen:
            continue
        seen.add(item)
        yield item


def _validate_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        errors.append(f"{path}: 期望 {expected_type}，实际 {type(value).__name__}")
        return errors

    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        errors.append(f"{path}: 值 {value!r} 不在 enum 中")

    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: 缺少必填字段")
        for key, subschema in properties.items():
            if key in value and isinstance(subschema, dict):
                errors.extend(_validate_schema(value[key], subschema, f"{path}.{key}"))

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: 至少需要 {min_items} 个元素")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: 最多允许 {max_items} 个元素")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(_validate_schema(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path}: 字符串长度小于 {min_length}")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(f"{path}: 字符串长度大于 {max_length}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: 数值小于最小值 {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: 数值大于最大值 {maximum}")

    return errors


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    return True
