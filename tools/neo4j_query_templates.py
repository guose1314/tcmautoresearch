"""Neo4j Cypher 查询规范模板 — Canonical Query Templates.

本文件是仓库级 Cypher 查询写法的权威参考。所有文档、README、诊断脚本、
运维手册中出现的 Neo4j 示例，都应与此模板一致。

治理规则:
  1. 关系创建必须使用 split MATCH（先 MATCH 源节点，再 MATCH 目标节点）。
  2. 批量操作 UNWIND 内部仍保持 split MATCH。
  3. 查询中出现的 label / relationship type 插值必须通过 _safe_cypher_label() 验证。
  4. ID / 属性值必须用参数 ($param) 传入，不得字符串拼接。
  5. 关系类型过滤必须使用 WHERE type(r) IN [...] 白名单。
  6. 子图遍历必须使用 Neo4j 5 scoped CALL 语法。
  7. 任何会触发 planner/cartesian-product 信息级通知的查询不得进入文档。

用法::

    from tools.neo4j_query_templates import (
        CANONICAL_READ_TEMPLATES,
        CANONICAL_WRITE_TEMPLATES,
        ANTI_PATTERNS,
        validate_cypher_snippet,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

# ───────────────────────────────────────────────────────────────────────
# 反模式检测正则
# ───────────────────────────────────────────────────────────────────────

# MATCH (a ...), (b ...) — 逗号分隔的断开 MATCH（会触发 cartesian product 通知）
_RE_COMMA_MATCH = re.compile(
    r"MATCH\s*\([^)]+\)\s*,\s*\(",
    re.IGNORECASE,
)

# 字符串拼接代替参数化（f"...{var}..." 或 "..." + var + "..."）
_RE_STRING_CONCAT = re.compile(
    r"""(?:f['"].*?\{[^}]+\}.*?['"]|['"].*?\+\s*\w+\s*\+.*?['"])""",
    re.IGNORECASE,
)

# 在 Cypher 字符串中直接拼接标签而不经 _safe_cypher_label
_RE_UNSAFE_LABEL_INTERP = re.compile(
    r"f['\"].*(?:MATCH|MERGE|CREATE)\s*\(\w+:\{(?!_safe_cypher_label)",
    re.IGNORECASE,
)


@dataclass
class AntiPattern:
    """一种已知的 Cypher 反模式。"""
    name: str
    description: str
    regex: re.Pattern[str]
    severity: str  # "error" | "warning"


ANTI_PATTERNS: List[AntiPattern] = [
    AntiPattern(
        name="comma_separated_match",
        description="MATCH (a), (b) MERGE ... — 逗号分隔的断开 MATCH，触发 cartesian product 通知",
        regex=_RE_COMMA_MATCH,
        severity="error",
    ),
    AntiPattern(
        name="unsafe_label_interpolation",
        description="f-string 中 label 插值未经 _safe_cypher_label() 验证",
        regex=_RE_UNSAFE_LABEL_INTERP,
        severity="error",
    ),
]


# ───────────────────────────────────────────────────────────────────────
# 规范读查询模板
# ───────────────────────────────────────────────────────────────────────

CANONICAL_READ_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "formula_composition": {
        "description": "方剂组成查询 — OPTIONAL MATCH + type 白名单",
        "cypher": (
            "MATCH (f:Formula {name: $formula_name})\n"
            "OPTIONAL MATCH (f)-[r]->(h:Herb)\n"
            "WHERE type(r) IN ['SOVEREIGN', 'MINISTER', 'ASSISTANT', 'ENVOY']\n"
            "WITH f, collect(DISTINCT {role: type(r), herb: h.name}) AS role_pairs\n"
            "RETURN f,\n"
            "       [pair IN role_pairs WHERE pair.role = 'SOVEREIGN' AND pair.herb IS NOT NULL | pair.herb] AS sovereign,\n"
            "       [pair IN role_pairs WHERE pair.role = 'MINISTER' AND pair.herb IS NOT NULL | pair.herb] AS minister,\n"
            "       [pair IN role_pairs WHERE pair.role = 'ASSISTANT' AND pair.herb IS NOT NULL | pair.herb] AS assistant,\n"
            "       [pair IN role_pairs WHERE pair.role = 'ENVOY' AND pair.herb IS NOT NULL | pair.herb] AS envoy;"
        ),
        "rules": [
            "使用 OPTIONAL MATCH 避免缺失关系导致结果为空",
            "WHERE type(r) IN [...] 白名单过滤",
            "单次聚合，不做多次 MATCH 相同节点",
        ],
    },
    "subgraph_extraction": {
        "description": "子图提取 — Neo4j 5 scoped CALL",
        "cypher": (
            "MATCH (start {id: $node_id})\n"
            "CALL (start) {\n"
            "  WITH start\n"
            "  MATCH p = (start)-[*..2]-(neighbor)\n"
            "  RETURN collect(DISTINCT nodes(p)) AS node_sets,\n"
            "         collect(DISTINCT relationships(p)) AS edge_sets\n"
            "}\n"
            "RETURN node_sets, edge_sets;"
        ),
        "rules": [
            "使用 CALL (var) { ... } scoped 语法（Neo4j 5+）",
            "不使用旧版 CALL { WITH start ... } 形式",
        ],
    },
    "node_statistics": {
        "description": "节点统计 — 简单聚合",
        "cypher": (
            "MATCH (n)\n"
            "RETURN labels(n)[0] AS label, count(*) AS count\n"
            "ORDER BY count DESC;"
        ),
        "rules": ["无关系操作，直接聚合"],
    },
    "philology_asset_graph": {
        "description": "文献学资产子图查询 — catalog -> witness -> fragment / exegesis，复用 dashboard/workbench 过滤字段",
        "cypher": (
            "MATCH (w:VersionWitness {cycle_id: $cycle_id})\n"
            "OPTIONAL MATCH (w)-[:BELONGS_TO_LINEAGE]->(l:VersionLineage)\n"
            "OPTIONAL MATCH (w)-[catalog_rel]->(catalog_node)\n"
            "WHERE type(catalog_rel) = 'CATALOGED_IN' AND 'Catalog' IN labels(catalog_node)\n"
            "OPTIONAL MATCH (phase:ResearchPhaseExecution {id: w.phase_execution_id})\n"
            "WHERE coalesce(phase.cycle_id, '') = $cycle_id\n"
            "WITH catalog_node, phase, w, l\n"
            "WHERE ($work_title = '' OR coalesce(w.work_title, l.work_title, '') = $work_title)\n"
            "  AND ($version_lineage_key = '' OR coalesce(l.version_lineage_key, w.version_lineage_key, '') = $version_lineage_key)\n"
            "  AND ($witness_key = '' OR w.witness_key = $witness_key)\n"
            "OPTIONAL MATCH (w)-[asset_rel]->(asset_node)\n"
            "WHERE type(asset_rel) IN ['HAS_FRAGMENT_CANDIDATE', 'ATTESTS_TO']\n"
            "WITH catalog_node, phase, w, l, collect(DISTINCT asset_node) AS primary_assets\n"
            "OPTIONAL MATCH (phase)-[:CAPTURED]->(legacy_entity)\n"
            "WHERE coalesce(legacy_entity.document_id, '') = coalesce(w.document_id, '')\n"
            "WITH catalog_node, w, l, primary_assets, collect(DISTINCT legacy_entity) AS legacy_entities\n"
            "WITH catalog_node, w, l,\n"
            "     [fragment IN primary_assets WHERE fragment IS NOT NULL AND 'FragmentCandidate' IN labels(fragment) AND ($review_status = '' OR coalesce(fragment.review_status, '') = $review_status) | {\n"
            "         id: fragment.id,\n"
            "         candidate_id: coalesce(fragment.candidate_id, fragment.id, ''),\n"
            "         fragment_title: coalesce(fragment.fragment_title, fragment.title, w.fragment_title, w.document_title, ''),\n"
            "         version_lineage_key: coalesce(fragment.version_lineage_key, w.version_lineage_key, ''),\n"
            "         witness_key: coalesce(fragment.witness_key, w.witness_key, ''),\n"
            "         review_status: coalesce(fragment.review_status, ''),\n"
            "         needs_manual_review: coalesce(fragment.needs_manual_review, false)\n"
            "     }] AS fragments,\n"
            "     [term IN primary_assets WHERE term IS NOT NULL AND 'ExegesisTerm' IN labels(term) AND ($review_status = '' OR coalesce(term.review_status, '') = $review_status) | {\n"
            "         id: term.id,\n"
            "         exegesis_id: coalesce(term.exegesis_id, term.id, ''),\n"
            "         canonical: coalesce(term.canonical, term.name, ''),\n"
            "         semantic_scope: coalesce(term.semantic_scope, term.entity_type, ''),\n"
            "         version_lineage_key: coalesce(term.version_lineage_key, w.version_lineage_key, ''),\n"
            "         witness_key: coalesce(term.witness_key, w.witness_key, ''),\n"
            "         review_status: coalesce(term.review_status, ''),\n"
            "         needs_manual_review: coalesce(term.needs_manual_review, false),\n"
            "         source: 'g3'\n"
            "     }] +\n"
            "     [legacy IN legacy_entities WHERE legacy IS NOT NULL AND $review_status = '' | {\n"
            "         id: legacy.id,\n"
            "         exegesis_id: coalesce(legacy.entity_id, legacy.id, ''),\n"
            "         canonical: coalesce(legacy.name, ''),\n"
            "         semantic_scope: coalesce(legacy.entity_type, labels(legacy)[0], ''),\n"
            "         version_lineage_key: coalesce(w.version_lineage_key, ''),\n"
            "         witness_key: coalesce(w.witness_key, ''),\n"
            "         review_status: 'legacy_unreviewed',\n"
            "         needs_manual_review: true,\n"
            "         source: 'legacy_captured'\n"
            "     }] AS exegesis_terms\n"
            "WHERE size(fragments) > 0 OR size(exegesis_terms) > 0\n"
            "RETURN coalesce(catalog_node.catalog_id, w.catalog_id, w.document_urn, w.document_id, '') AS catalog_id,\n"
            "       coalesce(catalog_node.title, w.fragment_title, w.work_title, w.document_title, '') AS catalog_title,\n"
            "       coalesce(catalog_node.review_status, '') AS catalog_review_status,\n"
            "       coalesce(w.work_title, l.work_title, '') AS work_title,\n"
            "       coalesce(l.version_lineage_key, w.version_lineage_key, '') AS version_lineage_key,\n"
            "       w.witness_key AS witness_key,\n"
            "       w.document_title AS witness_title,\n"
            "       coalesce(w.review_status, '') AS witness_review_status,\n"
            "       CASE\n"
            "           WHEN size([fragment IN fragments | 1]) > 0 OR size([term IN exegesis_terms WHERE coalesce(term.source, '') = 'g3' | 1]) > 0 THEN 'g3'\n"
            "           ELSE 'legacy'\n"
            "       END AS graph_source,\n"
            "       fragments,\n"
            "       exegesis_terms\n"
            "ORDER BY work_title, version_lineage_key, witness_title\n"
            "LIMIT $limit;"
        ),
        "rules": [
            "从 VersionWitness 起手，避免 Catalog 无 cycle_id 时误扫全图",
            "新图 fragment / exegesis 资产优先读取；历史图通过 phase_execution_id + document_id 回退到 CAPTURED 语义节点",
            "复用 work_title/version_lineage_key/witness_key/review_status 四类 dashboard 过滤字段",
            "review_status 过滤仅作用于下游 G-3 philology 资产节点；legacy 回退仅在不过滤 review_status 时启用",
        ],
    },
}


# ───────────────────────────────────────────────────────────────────────
# 规范写查询模板
# ───────────────────────────────────────────────────────────────────────

CANONICAL_WRITE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "create_relationship": {
        "description": "单条关系写入 — split MATCH + 参数化",
        "cypher": (
            "MATCH (source:ResearchSession {id: $source_id})\n"
            "MATCH (target:ResearchPhaseExecution {id: $target_id})\n"
            "MERGE (source)-[r:HAS_PHASE]->(target)\n"
            "SET r += $properties\n"
            "RETURN r;"
        ),
        "rules": [
            "先 MATCH 源节点，再 MATCH 目标节点（split MATCH）",
            "不使用 MATCH (a), (b) 逗号连接",
            "ID 通过 $param 传入，不拼接字符串",
        ],
    },
    "batch_create_relationships": {
        "description": "批量关系写入 — UNWIND + split MATCH",
        "cypher": (
            "UNWIND $rows AS row\n"
            "MATCH (a:ResearchPhaseExecution {id: row.source_id})\n"
            "MATCH (b:ResearchArtifact {id: row.target_id})\n"
            "MERGE (a)-[r:GENERATED]->(b)\n"
            "SET r += row.properties\n"
            "RETURN count(r) AS written_count;"
        ),
        "rules": [
            "UNWIND 内部仍保持 split MATCH",
            "不为省一行而使用逗号连接",
        ],
    },
    "merge_node": {
        "description": "节点 MERGE — 参数化 + safe label",
        "cypher": (
            "MERGE (n:Label {id: $id})\n"
            "SET n += $properties\n"
            "RETURN n;"
        ),
        "rules": [
            "Label 在 Python 代码中必须经 _safe_cypher_label() 验证",
            "属性通过 $properties map 传入",
        ],
    },
}


# ───────────────────────────────────────────────────────────────────────
# 排障模板
# ───────────────────────────────────────────────────────────────────────

TROUBLESHOOTING_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "cartesian_product_notification": {
        "symptom": "Neo4j 返回 'cartesian product' 信息级通知",
        "cause": "使用了 MATCH (a), (b) 逗号分隔的断开 MATCH 模式",
        "fix": "改为 split MATCH：先 MATCH (a)，再 MATCH (b)",
        "correct_example": CANONICAL_WRITE_TEMPLATES["create_relationship"]["cypher"],
    },
    "deprecated_call_syntax": {
        "symptom": "Neo4j 5 返回 CALL 子查询 deprecation warning",
        "cause": "使用了旧版 CALL { WITH start ... } 语法",
        "fix": "改为 CALL (start) { ... } scoped 语法",
        "correct_example": CANONICAL_READ_TEMPLATES["subgraph_extraction"]["cypher"],
    },
    "missing_relationship_type": {
        "symptom": "关系查询返回意外类型的关系",
        "cause": "未对 relationship type 做白名单过滤",
        "fix": "添加 WHERE type(r) IN ['TYPE1', 'TYPE2', ...] 条件",
        "correct_example": CANONICAL_READ_TEMPLATES["formula_composition"]["cypher"],
    },
}


# ───────────────────────────────────────────────────────────────────────
# 验证 API
# ───────────────────────────────────────────────────────────────────────

@dataclass
class LintViolation:
    """Cypher 规范违规。"""
    pattern_name: str
    severity: str
    description: str
    line: int = 0
    snippet: str = ""


def validate_cypher_snippet(text: str) -> List[LintViolation]:
    """对一段文本中的 Cypher 片段执行反模式检测。

    Args:
        text: 可以是完整文件内容或单段 Cypher 查询。

    Returns:
        检测到的违规列表；空列表表示通过。
    """
    violations: List[LintViolation] = []
    for ap in ANTI_PATTERNS:
        for m in ap.regex.finditer(text):
            # 估算行号
            line = text[:m.start()].count("\n") + 1
            snippet = text[m.start():m.end()].strip()[:120]
            violations.append(LintViolation(
                pattern_name=ap.name,
                severity=ap.severity,
                description=ap.description,
                line=line,
                snippet=snippet,
            ))
    return violations


def validate_file(filepath: str) -> List[LintViolation]:
    """对文件执行反模式检测。"""
    from pathlib import Path
    p = Path(filepath)
    if not p.is_file():
        return [LintViolation(
            pattern_name="file_not_found",
            severity="error",
            description=f"文件不存在: {filepath}",
        )]
    content = p.read_text(encoding="utf-8")
    violations = validate_cypher_snippet(content)
    for v in violations:
        v.snippet = f"{filepath}:{v.line}"
    return violations
