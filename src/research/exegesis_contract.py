"""统一训诂字段合同 — Exegesis Field Contract

本模块是训诂 / 释义字段的唯一权威定义。所有层（PhilologyService /
observe_philology / dashboard / artifact）都应引用此处的常量与函数。

训诂核心流程:
  术语标准化 →  义项判别 (polysemy disambiguation) → 释义生成 → 时代表达映射

义项判别三分流:
  herb  — 药名义项（四气五味、功效、归经）
  syndrome — 证候义项（病机、典型表现）
  theory — 理论术语义项（概念定义）

释义来源优先级:
  4 config_terminology_standard  — 用户配置 / 标准参考
  3 structured_tcm_knowledge     — TCMRelationshipDefinitions 结构化知识
  2 terminology_note             — 术语附注推导
  1 canonical_fallback           — 机器归并兜底

可配置字典协议:
  任何实现 ExegesisDictionary 协议的对象均可注入为释义来源。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Protocol, Sequence, runtime_checkable

# ---------------------------------------------------------------------------
# 训诂核心字段名 — terminology_rows 上应携带的释义字段
# ---------------------------------------------------------------------------
FIELD_DEFINITION = "definition"
FIELD_DEFINITION_SOURCE = "definition_source"
FIELD_SEMANTIC_SCOPE = "semantic_scope"
FIELD_DYNASTY_USAGE = "dynasty_usage"
FIELD_DISAMBIGUATION_BASIS = "disambiguation_basis"

EXEGESIS_FIELDS: frozenset[str] = frozenset(
    {
        FIELD_DEFINITION,
        FIELD_DEFINITION_SOURCE,
        FIELD_SEMANTIC_SCOPE,
        FIELD_DYNASTY_USAGE,
        FIELD_DISAMBIGUATION_BASIS,
    }
)

# ---------------------------------------------------------------------------
# 义项判别三分流类别
# ---------------------------------------------------------------------------
POLYSEMY_CATEGORY_HERB = "herb"
POLYSEMY_CATEGORY_FORMULA = "formula"
POLYSEMY_CATEGORY_SYNDROME = "syndrome"
POLYSEMY_CATEGORY_THEORY = "theory"
POLYSEMY_CATEGORY_EFFICACY = "efficacy"
POLYSEMY_CATEGORY_COMMON = "common"

POLYSEMY_DISAMBIGUATION_CATEGORIES: frozenset[str] = frozenset(
    {
        POLYSEMY_CATEGORY_HERB,
        POLYSEMY_CATEGORY_SYNDROME,
        POLYSEMY_CATEGORY_THEORY,
    }
)

LABEL_TO_CATEGORY: Dict[str, str] = {
    "本草药名": POLYSEMY_CATEGORY_HERB,
    "方剂名": POLYSEMY_CATEGORY_FORMULA,
    "证候术语": POLYSEMY_CATEGORY_SYNDROME,
    "理论术语": POLYSEMY_CATEGORY_THEORY,
    "功效术语": POLYSEMY_CATEGORY_EFFICACY,
    "通用术语": POLYSEMY_CATEGORY_COMMON,
}

CATEGORY_TO_LABEL: Dict[str, str] = {v: k for k, v in LABEL_TO_CATEGORY.items()}

# ---------------------------------------------------------------------------
# 释义来源优先级
# ---------------------------------------------------------------------------
DEFINITION_SOURCE_CONFIG = "config_terminology_standard"
DEFINITION_SOURCE_STRUCTURED = "structured_tcm_knowledge"
DEFINITION_SOURCE_NOTE = "terminology_note"
DEFINITION_SOURCE_FALLBACK = "canonical_fallback"

DEFINITION_SOURCE_RANK: Dict[str, int] = {
    DEFINITION_SOURCE_CONFIG: 4,
    DEFINITION_SOURCE_STRUCTURED: 3,
    DEFINITION_SOURCE_NOTE: 2,
    DEFINITION_SOURCE_FALLBACK: 1,
}


def definition_source_rank(source: Any) -> int:
    """返回释义来源的优先级数值，未知来源返回 0。"""
    return DEFINITION_SOURCE_RANK.get(str(source or "").strip(), 0)


# ---------------------------------------------------------------------------
# 可配置字典协议
# ---------------------------------------------------------------------------
@runtime_checkable
class ExegesisDictionary(Protocol):
    """可注入的释义字典协议。

    任何实现 ``lookup`` 方法的对象都可以作为释义来源。
    """

    def lookup(self, canonical: str, *, category: str = "") -> Dict[str, Any]:
        """查询术语释义。

        返回字典应包含 ``definition``, ``definition_source``, ``source_refs`` 等字段。
        未找到时返回空字典。
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# 义项判别 (polysemy disambiguation)
# ---------------------------------------------------------------------------
def resolve_polysemy_category(
    row: Mapping[str, Any],
    label: str = "",
) -> str:
    """从 terminology row 推断该术语的义项类别。

    优先使用 row["category"]，其次用 label 做反查。
    返回 herb / syndrome / theory / formula / efficacy / common / ""。
    """
    category = str(row.get("category") or "").strip().lower()
    if category in LABEL_TO_CATEGORY.values():
        return category
    return LABEL_TO_CATEGORY.get(label, "")


HIGH_POLYSEMY_TERMS: frozenset[str] = frozenset({"风", "水", "伤寒", "白虎"})

def disambiguate_polysemy(
    canonical: str,
    category: str,
    *,
    dictionaries: Sequence[ExegesisDictionary] = (),
    context_terms: Sequence[str] = (),
    document_context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """对多义术语执行义项判别，返回释义载荷。

    按 dictionaries 注入顺序查词典，用评分机制选取最优匹配。
    针对高频多义词（如“风”、“水”、“伤寒”、“白虎”），将会拦截请求，
    结合上下文窗口 (document_context) 及预查候选列表，让大语言模型进行推演。
    """
    candidates: List[tuple[float, int, Dict[str, Any]]] = []
    for idx, dictionary in enumerate(dictionaries):
        payload = dictionary.lookup(canonical, category=category)
        if not payload or not payload.get("definition"):
            continue
        score = 0.0
        # 来源优先级
        source = str(payload.get("definition_source") or "").strip()
        score += definition_source_rank(source) * 10.0
        # category 匹配
        payload_category = str(payload.get("category") or "").strip()
        if payload_category and payload_category == category:
            score += 5.0
        # context 命中
        definition_text = str(payload.get("definition") or "")
        context_hits = 0
        for term in context_terms:
            term_str = str(term or "").strip()
            if term_str and term_str in definition_text:
                context_hits += 1
        score += context_hits * 2.0
        # 字典注入顺序作为次要排序 (越靠前越优)
        candidates.append((score, -idx, payload))

    # ==== [增强] 高频歧义词 LLM Context 推演 ====
    if canonical in HIGH_POLYSEMY_TERMS and document_context:
        # 如果命中了高频多义词，并且有附带的上下文，交由 LLM 判断
        doc_ctx = document_context or {}
        raw_window = doc_ctx.get("raw_text_window", "")
        dynasty = doc_ctx.get("dynasty", "未知")
        author = doc_ctx.get("author", "未知")

        # 整理已有的字典候选提供给 LLM 参考
        candidate_defs = [c[2].get("definition") for c in sorted(candidates, key=lambda t: (t[0], t[1]), reverse=True)]
        candidates_str = "\n".join(f"- {d}" for d in candidate_defs) if candidate_defs else "无预设字典候选"

        prompt = f"""[任务] 中医古籍高频多义词消歧义
[目标术语] {canonical}
[类型分类] {category}
[原文窗口] {raw_window}
[文献朝代] {dynasty}
[文献作者] {author}

[候选释义列表]
{candidates_str}

请根据[原文窗口]和[文献朝代]的历史厚度，在上述候选释义中选择最恰当的一项，或者给出你在当前语境下更为准确的总结性释义。
要求仅输出结果的纯文本释义，不要任何额外的分析："""

        from src.llm.llm_service import CachedLLMService
        try:
            llm_res = CachedLLMService().generate(prompt).strip()
            if llm_res:
                return {
                    "definition": llm_res,
                    "definition_source": "llm_disambiguation",
                    "source_refs": ["llm_inference"],
                    "dynasty_usage": dynasty,
                    "disambiguation_basis": [f"LLM Reasoning ({dynasty})"]
                }
        except Exception:
            pass # 回退到普通 O(1) 字典查找机制

    if not candidates:
        return {}
    candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
    best = candidates[0][2]
    # 记录判别依据
    if context_terms and "disambiguation_basis" not in best:
        basis_terms = [t for t in context_terms if str(t or "").strip() in str(best.get("definition") or "")]
        if basis_terms:
            best = dict(best)
            best.setdefault("disambiguation_basis", [f"上下文关联:{t}" for t in basis_terms[:3]])
    return best


# ---------------------------------------------------------------------------
# 释义完整度评估
# ---------------------------------------------------------------------------
def assess_exegesis_completeness(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """评估 terminology_rows 的训诂完整度。"""
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "with_definition": 0,
            "definition_coverage": 0.0,
            "source_distribution": {},
            "category_distribution": {},
            "disambiguation_count": 0,
            "needs_disambiguation": 0,
        }
    with_definition = 0
    source_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    disambiguation_count = 0
    needs_disambiguation = 0

    for row in rows:
        definition = str(row.get(FIELD_DEFINITION) or "").strip()
        if definition:
            with_definition += 1
        source = str(row.get(FIELD_DEFINITION_SOURCE) or "").strip()
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        category = str(row.get("category") or "").strip()
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1
        basis = row.get(FIELD_DISAMBIGUATION_BASIS)
        if isinstance(basis, (list, tuple)) and len(basis) > 0:
            disambiguation_count += 1
        if category in POLYSEMY_DISAMBIGUATION_CATEGORIES and not definition:
            needs_disambiguation += 1

    return {
        "total": total,
        "with_definition": with_definition,
        "definition_coverage": round(with_definition / total, 4) if total else 0.0,
        "source_distribution": {k: source_counts[k] for k in sorted(source_counts)},
        "category_distribution": {k: category_counts[k] for k in sorted(category_counts)},
        "disambiguation_count": disambiguation_count,
        "needs_disambiguation": needs_disambiguation,
    }


# ---------------------------------------------------------------------------
# 训诂摘要 (用于 dashboard / API)
# ---------------------------------------------------------------------------
def build_exegesis_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """构建训诂摘要卡片数据。"""
    completeness = assess_exegesis_completeness(rows)
    dynasty_terms: Dict[str, int] = {}
    for row in rows:
        dynasty_usage = row.get(FIELD_DYNASTY_USAGE)
        if isinstance(dynasty_usage, (list, tuple)):
            for dynasty in dynasty_usage:
                dynasty_str = str(dynasty or "").strip()
                if dynasty_str:
                    dynasty_terms[dynasty_str] = dynasty_terms.get(dynasty_str, 0) + 1
    return {
        **completeness,
        "dynasty_term_counts": {k: dynasty_terms[k] for k in sorted(dynasty_terms)},
    }


# ---------------------------------------------------------------------------
# exegesis_notes 生成 — 记录 "选择此释义的理由"
# ---------------------------------------------------------------------------
def build_exegesis_note(
    canonical: str,
    definition_source: str,
    category: str = "",
    disambiguation_basis: Sequence[str] = (),
) -> str:
    """为单条术语生成训诂备注 (exegesis_notes)，说明释义选择理由。"""
    parts: list[str] = []
    source_label = {
        DEFINITION_SOURCE_CONFIG: "配置标准",
        DEFINITION_SOURCE_STRUCTURED: "结构化知识库",
        DEFINITION_SOURCE_NOTE: "附注推导",
        DEFINITION_SOURCE_FALLBACK: "机器归并",
    }.get(definition_source, definition_source or "未知来源")

    parts.append(f"「{canonical}」释义来源：{source_label}")
    if category in POLYSEMY_DISAMBIGUATION_CATEGORIES:
        category_label = CATEGORY_TO_LABEL.get(category, category)
        parts.append(f"义项判别：分流至{category_label}")
    if disambiguation_basis:
        basis_text = "、".join(str(b) for b in disambiguation_basis[:3])
        parts.append(f"判别依据：{basis_text}")
    return "；".join(parts)
