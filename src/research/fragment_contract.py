"""统一辑佚字段合同 — Fragment Reconstruction Contract

本模块是辑佚（佚文辑复）候选项的唯一权威定义。所有层（PhilologyService /
observe_philology / dashboard / artifact）都应引用此处的常量与函数。

辑佚核心流程:
  版本校勘 → 异文提取 → 候选项分类 → 评分 → 人工复核

候选项三分类:
  fragment_candidates      — 疑似佚文片段（版本间差异暗示的缺段）
  lost_text_candidates     — 疑似佚失全文（整段仅见于某一见证本）
  citation_source_candidates — 引文来源线索（某版本引用的典籍出处）

评分区间: 0.46 – 0.98
  base 0.46 + diff_type bonus + strategy bonus + text_growth + min_length

候选项元数据:
  fragment_candidate_id, candidate_kind, match_score,
  source_refs, reconstruction_basis, needs_manual_review,
  review_status, review_reasons
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

# ---------------------------------------------------------------------------
# 候选项分类常量
# ---------------------------------------------------------------------------
CANDIDATE_KIND_FRAGMENT = "fragment_candidates"
CANDIDATE_KIND_LOST_TEXT = "lost_text_candidates"
CANDIDATE_KIND_CITATION_SOURCE = "citation_source_candidates"

CANDIDATE_KINDS: tuple[str, ...] = (
    CANDIDATE_KIND_FRAGMENT,
    CANDIDATE_KIND_LOST_TEXT,
    CANDIDATE_KIND_CITATION_SOURCE,
)

CANDIDATE_KIND_LABELS: Dict[str, str] = {
    CANDIDATE_KIND_FRAGMENT: "疑似佚文",
    CANDIDATE_KIND_LOST_TEXT: "疑似佚失",
    CANDIDATE_KIND_CITATION_SOURCE: "引文来源",
}

# ---------------------------------------------------------------------------
# 候选项核心字段名
# ---------------------------------------------------------------------------
FIELD_FRAGMENT_CANDIDATE_ID = "fragment_candidate_id"
FIELD_CANDIDATE_KIND = "candidate_kind"
FIELD_MATCH_SCORE = "match_score"
FIELD_SOURCE_REFS = "source_refs"
FIELD_RECONSTRUCTION_BASIS = "reconstruction_basis"
FIELD_NEEDS_MANUAL_REVIEW = "needs_manual_review"
FIELD_REVIEW_STATUS = "review_status"
FIELD_REVIEW_REASONS = "review_reasons"

FRAGMENT_METADATA_FIELDS: frozenset[str] = frozenset(
    {
        FIELD_FRAGMENT_CANDIDATE_ID,
        FIELD_CANDIDATE_KIND,
        FIELD_MATCH_SCORE,
        FIELD_SOURCE_REFS,
        FIELD_RECONSTRUCTION_BASIS,
        FIELD_NEEDS_MANUAL_REVIEW,
        FIELD_REVIEW_STATUS,
        FIELD_REVIEW_REASONS,
    }
)

# ---------------------------------------------------------------------------
# 评分常量 (与 PhilologyService._score_fragment_candidate 保持一致)
# ---------------------------------------------------------------------------
SCORE_BASE = 0.46
SCORE_MAX = 0.98
SCORE_BONUS_INSERT = 0.22
SCORE_BONUS_REPLACE = 0.14
SCORE_BONUS_DELETE = 0.10

# ---------------------------------------------------------------------------
# 复核状态
# ---------------------------------------------------------------------------
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_ACCEPTED = "accepted"
REVIEW_STATUS_REJECTED = "rejected"

REVIEW_STATUSES: frozenset[str] = frozenset(
    {REVIEW_STATUS_PENDING, REVIEW_STATUS_ACCEPTED, REVIEW_STATUS_REJECTED}
)

# ---------------------------------------------------------------------------
# 辑佚完整度评估
# ---------------------------------------------------------------------------

def assess_fragment_completeness(
    candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """评估辑佚候选项集合的完整度与质量。"""
    total = len(candidates)
    if total == 0:
        return {
            "total": 0,
            "kind_distribution": {},
            "review_status_distribution": {},
            "needs_review_count": 0,
            "high_confidence_count": 0,
            "avg_score": 0.0,
            "has_source_refs_count": 0,
            "has_reconstruction_basis_count": 0,
        }

    kind_counts: Dict[str, int] = {}
    review_counts: Dict[str, int] = {}
    needs_review = 0
    high_confidence = 0
    score_sum = 0.0
    has_source_refs = 0
    has_basis = 0

    for candidate in candidates:
        kind = str(candidate.get(FIELD_CANDIDATE_KIND) or "").strip()
        if kind:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        review_status = str(candidate.get(FIELD_REVIEW_STATUS) or "").strip()
        if review_status:
            review_counts[review_status] = review_counts.get(review_status, 0) + 1

        if candidate.get(FIELD_NEEDS_MANUAL_REVIEW):
            needs_review += 1

        score = _safe_float(candidate.get(FIELD_MATCH_SCORE))
        score_sum += score
        if score >= 0.80:
            high_confidence += 1

        refs = candidate.get(FIELD_SOURCE_REFS)
        if isinstance(refs, (list, tuple)) and len(refs) > 0:
            has_source_refs += 1

        basis = candidate.get(FIELD_RECONSTRUCTION_BASIS)
        basis_str = str(basis or "").strip()
        if basis_str:
            has_basis += 1

    return {
        "total": total,
        "kind_distribution": {k: kind_counts[k] for k in sorted(kind_counts)},
        "review_status_distribution": {k: review_counts[k] for k in sorted(review_counts)},
        "needs_review_count": needs_review,
        "high_confidence_count": high_confidence,
        "avg_score": round(score_sum / total, 4) if total else 0.0,
        "has_source_refs_count": has_source_refs,
        "has_reconstruction_basis_count": has_basis,
    }


# ---------------------------------------------------------------------------
# 辑佚摘要 (用于 dashboard / artifact / API)
# ---------------------------------------------------------------------------

def build_fragment_summary(
    fragment_candidates: Sequence[Mapping[str, Any]],
    lost_text_candidates: Sequence[Mapping[str, Any]],
    citation_source_candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """构建辑佚摘要卡片数据，汇总三类候选项。"""
    all_candidates: List[Mapping[str, Any]] = [
        *fragment_candidates,
        *lost_text_candidates,
        *citation_source_candidates,
    ]
    completeness = assess_fragment_completeness(all_candidates)
    return {
        **completeness,
        "fragment_candidate_count": len(fragment_candidates),
        "lost_text_candidate_count": len(lost_text_candidates),
        "citation_source_candidate_count": len(citation_source_candidates),
    }


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float:
    """安全转换为 float，失败返回 0.0。"""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
