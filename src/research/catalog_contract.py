"""统一目录学字段合同 — Catalog Field Contract

本模块是目录学字段的唯一权威定义，所有层（Observe / repo snapshot /
dashboard / artifact）都应引用此处的常量和归一化函数。

层级模型:
  作品 (Work) → 卷篇 (Fragment) → 版本谱系 (Version Lineage) → 见证本 (Witness)

核心字段: catalog_id, work_title, fragment_title, version_lineage_key, witness_key
扩展字段: work_key, fragment_key, work_fragment_key, dynasty, author, edition
来源字段: source_type, source_name, source_ref, lineage_source
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# 核心字段名常量 — 所有层层字段名与此处保持一致
# ─────────────────────────────────────────────────────────────────────────────

FIELD_CATALOG_ID = "catalog_id"
FIELD_WORK_TITLE = "work_title"
FIELD_FRAGMENT_TITLE = "fragment_title"
FIELD_VERSION_LINEAGE_KEY = "version_lineage_key"
FIELD_WITNESS_KEY = "witness_key"

FIELD_WORK_KEY = "work_key"
FIELD_FRAGMENT_KEY = "fragment_key"
FIELD_WORK_FRAGMENT_KEY = "work_fragment_key"
FIELD_DYNASTY = "dynasty"
FIELD_AUTHOR = "author"
FIELD_EDITION = "edition"

FIELD_SOURCE_TYPE = "source_type"
FIELD_SOURCE_NAME = "source_name"
FIELD_SOURCE_REF = "source_ref"
FIELD_LINEAGE_SOURCE = "lineage_source"

# ─────────────────────────────────────────────────────────────────────────────
# 字段组 — 最小必填字段与完整字段清单
# ─────────────────────────────────────────────────────────────────────────────

CATALOG_CORE_FIELDS: tuple[str, ...] = (
    FIELD_CATALOG_ID,
    FIELD_WORK_TITLE,
    FIELD_FRAGMENT_TITLE,
    FIELD_VERSION_LINEAGE_KEY,
    FIELD_WITNESS_KEY,
)

CATALOG_EXTENDED_FIELDS: tuple[str, ...] = (
    FIELD_WORK_KEY,
    FIELD_FRAGMENT_KEY,
    FIELD_WORK_FRAGMENT_KEY,
    FIELD_DYNASTY,
    FIELD_AUTHOR,
    FIELD_EDITION,
)

CATALOG_SOURCE_FIELDS: tuple[str, ...] = (
    FIELD_SOURCE_TYPE,
    FIELD_SOURCE_NAME,
    FIELD_SOURCE_REF,
    FIELD_LINEAGE_SOURCE,
)

CATALOG_ALL_FIELDS: tuple[str, ...] = (
    *CATALOG_CORE_FIELDS,
    *CATALOG_EXTENDED_FIELDS,
    *CATALOG_SOURCE_FIELDS,
)

CATALOG_BASELINE_FIELDS: tuple[str, ...] = (
    FIELD_CATALOG_ID,
    FIELD_WORK_TITLE,
    FIELD_FRAGMENT_TITLE,
    FIELD_WORK_FRAGMENT_KEY,
    FIELD_VERSION_LINEAGE_KEY,
    FIELD_WITNESS_KEY,
    FIELD_DYNASTY,
    FIELD_AUTHOR,
    FIELD_EDITION,
)

CATALOG_FILTER_FIELDS: tuple[str, ...] = (
    "document_title",
    FIELD_WORK_TITLE,
    FIELD_VERSION_LINEAGE_KEY,
    FIELD_WITNESS_KEY,
)

# ─────────────────────────────────────────────────────────────────────────────
# 回填规则 — 每个核心字段的可恢复回填来源
# ─────────────────────────────────────────────────────────────────────────────

BACKFILL_RULES: Dict[str, List[Dict[str, str]]] = {
    FIELD_CATALOG_ID: [
        {"source": "source_ref", "strategy": "fallback_to_source_ref"},
        {"source": "document_urn", "strategy": "fallback_to_urn"},
    ],
    FIELD_WORK_TITLE: [
        {"source": "filename", "strategy": "infer_from_filename_regex"},
        {"source": "root_title", "strategy": "fallback_to_root_title"},
        {"source": "document_title", "strategy": "fallback_to_document_title"},
    ],
    FIELD_FRAGMENT_TITLE: [
        {"source": "section_title", "strategy": "copy_from_section_title"},
        {"source": "work_title", "strategy": "fallback_to_work_title"},
    ],
    FIELD_VERSION_LINEAGE_KEY: [
        {"source": "work_fragment_key+dynasty+author+edition", "strategy": "compute_from_components"},
    ],
    FIELD_WITNESS_KEY: [
        {"source": "catalog_id+source_ref", "strategy": "compute_namespace_ref"},
        {"source": "source_type+source_ref", "strategy": "compute_source_ref"},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# 字段归一化函数
# ─────────────────────────────────────────────────────────────────────────────


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def assess_catalog_completeness(
    entry: Mapping[str, Any],
) -> Dict[str, Any]:
    """评估单条目录学条目的完整性及回填需求。

    返回值包含:
      - missing_core_fields: 缺失的核心字段列表
      - metadata_completeness: 0..1 完整性比例
      - needs_backfill: 是否有可回填的缺失字段
      - backfill_candidates: 可回填字段的规则清单
    """
    missing_core: list[str] = []
    for field_name in CATALOG_CORE_FIELDS:
        if not _as_text(entry.get(field_name)):
            missing_core.append(field_name)

    completeness = round(
        (len(CATALOG_CORE_FIELDS) - len(missing_core)) / len(CATALOG_CORE_FIELDS),
        3,
    ) if CATALOG_CORE_FIELDS else 1.0

    backfill_candidates: list[dict[str, str]] = []
    for field_name in missing_core:
        rules = BACKFILL_RULES.get(field_name, [])
        for rule in rules:
            backfill_candidates.append({
                "field": field_name,
                "source": rule["source"],
                "strategy": rule["strategy"],
            })

    needs_backfill = bool(backfill_candidates)

    return {
        "missing_core_fields": missing_core,
        "metadata_completeness": completeness,
        "needs_backfill": needs_backfill,
        "backfill_candidates": backfill_candidates,
    }


def normalize_catalog_entry(
    entry: Mapping[str, Any],
) -> Dict[str, Any]:
    """将任意来源的字段名映射到规范目录学字段合同。

    统一处理各层可能出现的别名:
      - document_title / title
      - document_urn / urn
      - document_id / id
    """
    normalized: Dict[str, Any] = {
        "document_id": _as_text(entry.get("document_id") or entry.get("id")),
        "document_title": _as_text(entry.get("document_title") or entry.get("title")),
        "document_urn": _as_text(entry.get("document_urn") or entry.get("urn")),
    }
    for field_name in CATALOG_ALL_FIELDS:
        normalized[field_name] = _as_text(entry.get(field_name))

    completeness = assess_catalog_completeness(normalized)
    normalized.update(completeness)
    return normalized


def has_baseline_fields(entry: Mapping[str, Any]) -> bool:
    """检查条目是否至少包含一个基线字段。"""
    for key in CATALOG_BASELINE_FIELDS:
        if _as_text(entry.get(key)):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 层级摘要构建
# ─────────────────────────────────────────────────────────────────────────────


def build_catalog_hierarchy(
    documents: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """构建 作品→卷篇→版本谱系→见证本 四级层级摘要。

    输出结构:
      works:
        - work_title: "本草纲目"
          fragments:
            - fragment_title: "卷一·序例"
              lineages:
                - version_lineage_key: "..."
                  witness_count: 2
              lineage_count: 1
          fragment_count: 1
      work_count: 1
      fragment_count: 1
      lineage_count: 1
      witness_count: 2
    """
    work_map: Dict[str, Dict[str, Any]] = {}

    for doc in documents:
        work = _as_text(doc.get(FIELD_WORK_TITLE)) or "(未知作品)"
        fragment = _as_text(doc.get(FIELD_FRAGMENT_TITLE)) or work
        lineage = _as_text(doc.get(FIELD_VERSION_LINEAGE_KEY)) or "(未知版本)"
        witness = _as_text(
            doc.get(FIELD_WITNESS_KEY)
            or doc.get("document_id")
            or doc.get("document_urn")
            or doc.get("document_title")
        )

        work_node = work_map.setdefault(work, {
            "work_title": work,
            "_fragments": {},
        })
        fragment_node = work_node["_fragments"].setdefault(fragment, {
            "fragment_title": fragment,
            "_lineages": {},
        })
        lineage_node = fragment_node["_lineages"].setdefault(lineage, {
            "version_lineage_key": lineage,
            "_witnesses": set(),
        })
        if witness:
            lineage_node["_witnesses"].add(witness)

    works: list[dict[str, Any]] = []
    total_fragments = 0
    total_lineages = 0
    total_witnesses = 0

    for work_title in sorted(work_map):
        work_node = work_map[work_title]
        fragments: list[dict[str, Any]] = []
        for frag_title in sorted(work_node["_fragments"]):
            frag_node = work_node["_fragments"][frag_title]
            lineages: list[dict[str, Any]] = []
            for lin_key in sorted(frag_node["_lineages"]):
                lin_node = frag_node["_lineages"][lin_key]
                wc = len(lin_node["_witnesses"])
                lineages.append({
                    "version_lineage_key": lin_key,
                    "witness_count": wc,
                })
                total_witnesses += wc
            fragments.append({
                "fragment_title": frag_title,
                "lineages": lineages,
                "lineage_count": len(lineages),
            })
            total_lineages += len(lineages)
        works.append({
            "work_title": work_title,
            "fragments": fragments,
            "fragment_count": len(fragments),
        })
        total_fragments += len(fragments)

    return {
        "works": works,
        "work_count": len(works),
        "fragment_count": total_fragments,
        "lineage_count": total_lineages,
        "witness_count": total_witnesses,
    }


def build_backfill_summary(
    documents: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """汇总缺失目录学元数据的文档，以及各字段的回填候选数。"""
    needs_backfill_entries: list[dict[str, Any]] = []
    field_gap_counts: Dict[str, int] = {}

    for doc in documents:
        completeness = assess_catalog_completeness(doc)
        if not completeness["needs_backfill"]:
            continue

        identity = _as_text(
            doc.get("document_id")
            or doc.get("witness_key")
            or doc.get("document_urn")
            or doc.get("document_title")
        )
        needs_backfill_entries.append({
            "identity": identity,
            "missing_core_fields": completeness["missing_core_fields"],
            "backfill_candidates": completeness["backfill_candidates"],
        })
        for field_name in completeness["missing_core_fields"]:
            field_gap_counts[field_name] = field_gap_counts.get(field_name, 0) + 1

    return {
        "needs_backfill_count": len(needs_backfill_entries),
        "field_gap_counts": {k: field_gap_counts[k] for k in sorted(field_gap_counts)},
        "entries": needs_backfill_entries,
    }
