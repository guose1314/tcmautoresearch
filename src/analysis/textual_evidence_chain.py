"""文献学考据证据链构建器 — Textual Evidence Chain Builder

从 PhilologyService 产出的校勘、辑佚、训诂、目录学资产中提取考据 claim，
生成带证据链、反证信息和置信度的考据判断列表。

支持三类 claim:
  1. 作者归属 (authorship_attribution) — 从目录学元数据推断作者一致性
  2. 版本先后 (version_chronology) — 从校勘条目推断版本时间关系
  3. 引文来源 (citation_source) — 从引文来源候选推断引用出处

入口函数: build_evidence_chains()
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from src.research.evidence_chain_contract import (
    CLAIM_TYPE_AUTHORSHIP,
    CLAIM_TYPE_CITATION_SOURCE,
    CLAIM_TYPE_VERSION_CHRONOLOGY,
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    CONFIDENCE_REVIEW_THRESHOLD,
    JUDGMENT_NEEDS_REVIEW,
    JUDGMENT_RULE_BASED,
    build_claim,
    detect_claim_conflicts,
)


def build_evidence_chains(
    *,
    catalog_documents: Sequence[Mapping[str, Any]] = (),
    version_lineages: Sequence[Mapping[str, Any]] = (),
    collation_entries: Sequence[Mapping[str, Any]] = (),
    fragment_candidates: Sequence[Mapping[str, Any]] = (),
    lost_text_candidates: Sequence[Mapping[str, Any]] = (),
    citation_source_candidates: Sequence[Mapping[str, Any]] = (),
    terminology_rows: Sequence[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    """从文献学资产构建考据证据链。

    Returns:
        {
            "evidence_chains": [...],
            "conflict_claims": [...],
            "evidence_chain_count": int,
            "conflict_count": int,
        }
    """
    claims: List[Dict[str, Any]] = []

    # 1. 作者归属 claims
    claims.extend(
        _build_authorship_claims(catalog_documents, version_lineages)
    )

    # 2. 版本先后 claims
    claims.extend(
        _build_version_chronology_claims(collation_entries, version_lineages)
    )

    # 3. 引文来源 claims
    claims.extend(
        _build_citation_source_claims(citation_source_candidates)
    )

    # 冲突检测
    conflicts = detect_claim_conflicts(claims)
    # 把冲突标记回 claim
    conflict_ids = set()
    for conflict in conflicts:
        for cid in conflict.get("claim_ids_a", []):
            conflict_ids.add(cid)
        for cid in conflict.get("claim_ids_b", []):
            conflict_ids.add(cid)
    for claim in claims:
        if claim.get("evidence_chain_id") in conflict_ids:
            claim["has_conflict"] = True
            if not claim.get("needs_manual_review"):
                claim["needs_manual_review"] = True
                claim["review_status"] = "pending"
                if "存在冲突claim待复核" not in (claim.get("review_reasons") or []):
                    claim.setdefault("review_reasons", []).append("存在冲突claim待复核")

    return {
        "evidence_chains": claims,
        "conflict_claims": conflicts,
        "evidence_chain_count": len(claims),
        "conflict_count": len(conflicts),
    }


# ---------------------------------------------------------------------------
# 作者归属 claims
# ---------------------------------------------------------------------------

def _build_authorship_claims(
    catalog_documents: Sequence[Mapping[str, Any]],
    version_lineages: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """从目录学文档和版本谱系推断作者归属。"""
    claims: List[Dict[str, Any]] = []
    seen_work_authors: Dict[str, Dict[str, int]] = {}  # work_title -> {author: count}
    seen_work_dynasties: Dict[str, Dict[str, int]] = {}

    sources = list(catalog_documents) or list(version_lineages)
    for item in sources:
        work_title = _text(item.get("work_title"))
        author = _text(item.get("author"))
        dynasty = _text(item.get("dynasty"))
        if not work_title:
            continue
        if author:
            seen_work_authors.setdefault(work_title, {})
            seen_work_authors[work_title][author] = seen_work_authors[work_title].get(author, 0) + 1
        if dynasty:
            seen_work_dynasties.setdefault(work_title, {})
            seen_work_dynasties[work_title][dynasty] = seen_work_dynasties[work_title].get(dynasty, 0) + 1

    for work_title, author_counts in seen_work_authors.items():
        if not author_counts:
            continue
        dominant_author = max(author_counts, key=author_counts.get)  # type: ignore[arg-type]
        total = sum(author_counts.values())
        dominant_count = author_counts[dominant_author]
        consistency = dominant_count / total if total > 0 else 0
        dynasty_str = ""
        if work_title in seen_work_dynasties:
            dynasty_counts = seen_work_dynasties[work_title]
            dominant_dynasty = max(dynasty_counts, key=dynasty_counts.get)  # type: ignore[arg-type]
            dynasty_str = dominant_dynasty

        # 基础置信度: 0.50 单来源, +consistency bonus, +dynasty bonus
        confidence = 0.50
        if total > 1:
            confidence += 0.15 * consistency
        if dynasty_str:
            confidence += 0.08

        counter_evidence: List[str] = []
        if len(author_counts) > 1:
            for alt_author, alt_count in author_counts.items():
                if alt_author != dominant_author:
                    counter_evidence.append(
                        f"另有 {alt_count} 条记录标注作者为「{alt_author}」"
                    )
            confidence -= 0.10 * (len(author_counts) - 1)

        confidence = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, confidence))
        judgment = JUDGMENT_RULE_BASED if confidence >= CONFIDENCE_REVIEW_THRESHOLD and not counter_evidence else JUDGMENT_NEEDS_REVIEW

        dynasty_note = f"（{dynasty_str}）" if dynasty_str else ""
        statement = f"「{work_title}」作者为{dynasty_note}「{dominant_author}」"
        basis_parts = [f"基于 {total} 条目录学记录"]
        if total > 1:
            basis_parts.append(f"其中 {dominant_count} 条一致标注此作者（一致度 {consistency:.0%}）")
        if dynasty_str:
            basis_parts.append(f"时代标注为「{dynasty_str}」")

        claims.append(build_claim(
            evidence_chain_id=f"authorship::{work_title}::{dominant_author}",
            claim_type=CLAIM_TYPE_AUTHORSHIP,
            claim_statement=statement,
            confidence=confidence,
            basis_summary="；".join(basis_parts),
            judgment_type=judgment,
            counter_evidence=counter_evidence,
            source_refs=[f"catalog:{work_title}"],
            extra={
                "work_title": work_title,
                "author": dominant_author,
                "dynasty": dynasty_str,
                "witness_count": total,
            },
        ))

    return claims


# ---------------------------------------------------------------------------
# 版本先后 claims
# ---------------------------------------------------------------------------

def _build_version_chronology_claims(
    collation_entries: Sequence[Mapping[str, Any]],
    version_lineages: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """从校勘条目推断版本先后关系。"""
    claims: List[Dict[str, Any]] = []
    if not collation_entries:
        return claims

    # 按 version_lineage_key 分组，统计差异模式
    lineage_diffs: Dict[str, Dict[str, int]] = {}
    lineage_pairs: Dict[str, set] = {}
    for entry in collation_entries:
        lineage_key = _text(entry.get("version_lineage_key"))
        diff_type = _text(entry.get("difference_type"))
        base_title = _text(entry.get("document_title") or entry.get("base_title"))
        witness_title = _text(entry.get("witness_title"))
        if not lineage_key or not diff_type:
            continue
        lineage_diffs.setdefault(lineage_key, {})
        lineage_diffs[lineage_key][diff_type] = lineage_diffs[lineage_key].get(diff_type, 0) + 1
        if base_title and witness_title and base_title != witness_title:
            lineage_pairs.setdefault(lineage_key, set()).add((base_title, witness_title))

    for lineage_key, diff_counts in lineage_diffs.items():
        total_diffs = sum(diff_counts.values())
        if total_diffs < 1:
            continue

        insert_count = diff_counts.get("insert", 0)
        delete_count = diff_counts.get("delete", 0)
        replace_count = diff_counts.get("replace", 0)

        # 推断文本演化方向
        pairs = lineage_pairs.get(lineage_key, set())
        if not pairs:
            continue

        for base_title, witness_title in pairs:
            # 确定推断方向:当 insert > delete 时可能 witness 有额外内容 (later/expanded)
            counter_evidence: List[str] = []
            if insert_count > delete_count * 2:
                statement = f"版本谱系「{lineage_key}」中，「{witness_title}」可能较「{base_title}」为增补本"
                confidence = 0.45 + min(0.25, insert_count * 0.03)
                basis = f"校勘发现 {insert_count} 处新增、{delete_count} 处删除、{replace_count} 处替换，新增显著多于删除"
            elif delete_count > insert_count * 2:
                statement = f"版本谱系「{lineage_key}」中，「{witness_title}」可能较「{base_title}」为删节本"
                confidence = 0.45 + min(0.25, delete_count * 0.03)
                basis = f"校勘发现 {delete_count} 处删除、{insert_count} 处新增、{replace_count} 处替换，删除显著多于新增"
            elif replace_count > (insert_count + delete_count):
                statement = f"版本谱系「{lineage_key}」中，「{base_title}」与「{witness_title}」存在大量改写"
                confidence = 0.40 + min(0.20, replace_count * 0.02)
                basis = f"校勘发现 {replace_count} 处替换、{insert_count} 处新增、{delete_count} 处删除，改写为主"
                counter_evidence.append("改写主导的差异模式难以判定版本先后")
            else:
                statement = f"版本谱系「{lineage_key}」中，「{base_title}」与「{witness_title}」存在混合差异"
                confidence = 0.35
                basis = f"校勘发现 {total_diffs} 处差异（新增 {insert_count}、删除 {delete_count}、替换 {replace_count}），无明确方向"
                counter_evidence.append("差异模式无法明确判定版本先后关系")

            confidence = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, confidence))
            claims.append(build_claim(
                evidence_chain_id=f"chronology::{lineage_key}::{base_title}::{witness_title}",
                claim_type=CLAIM_TYPE_VERSION_CHRONOLOGY,
                claim_statement=statement,
                confidence=confidence,
                basis_summary=basis,
                counter_evidence=counter_evidence,
                source_refs=[f"collation:{lineage_key}"],
                extra={
                    "version_lineage_key": lineage_key,
                    "base_title": base_title,
                    "witness_title": witness_title,
                    "diff_counts": dict(diff_counts),
                    "total_diffs": total_diffs,
                },
            ))

    return claims


# ---------------------------------------------------------------------------
# 引文来源 claims
# ---------------------------------------------------------------------------

def _build_citation_source_claims(
    citation_source_candidates: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """从引文来源候选构建引文出处 claim。"""
    claims: List[Dict[str, Any]] = []
    for candidate in citation_source_candidates:
        cid = _text(candidate.get("fragment_candidate_id") or candidate.get("candidate_id"))
        if not cid:
            continue
        doc_title = _text(candidate.get("document_title"))
        witness_title = _text(candidate.get("witness_title") or candidate.get("title"))
        witness_text = _text(candidate.get("witness_text"))
        match_score = _safe_float(candidate.get("match_score"))
        basis = _text(candidate.get("reconstruction_basis"))
        source_refs = candidate.get("source_refs")
        if not isinstance(source_refs, (list, tuple)):
            source_refs = [str(source_refs)] if source_refs else []

        # 构建 statement
        text_preview = witness_text[:60] + "…" if len(witness_text) > 60 else witness_text
        if doc_title and witness_title:
            statement = f"「{doc_title}」中存在可能引自「{witness_title}」的段落"
        elif doc_title:
            statement = f"「{doc_title}」中存在疑似引文段落"
        else:
            statement = f"存在疑似引文来源候选（{text_preview}）"

        # 置信度: 基于 match_score 映射
        confidence = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, match_score * 0.85 + 0.10))

        counter_evidence: List[str] = []
        review_reasons_list: List[str] = []
        if candidate.get("needs_manual_review"):
            review_reasons_list = list(candidate.get("review_reasons") or [])

        claims.append(build_claim(
            evidence_chain_id=f"citation::{cid}",
            claim_type=CLAIM_TYPE_CITATION_SOURCE,
            claim_statement=statement,
            confidence=confidence,
            basis_summary=basis or f"异文对比得分 {match_score:.2f}",
            counter_evidence=counter_evidence,
            source_refs=[str(r) for r in source_refs],
            review_reasons=review_reasons_list,
            extra={
                "document_title": doc_title,
                "witness_title": witness_title,
                "text_preview": text_preview,
                "original_match_score": match_score,
            },
        ))

    return claims


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
