"""统一考据字段合同 — Evidence Chain Contract

本模块是考据（文献学证据链）的唯一权威定义。所有层（PhilologyService /
textual_evidence_chain / observe_philology / analyze_phase / dashboard / artifact）
都应引用此处的常量与函数。

考据核心流程:
  文献学资产（目录学 + 校勘 + 辑佚 + 训诂） → 证据提取 → claim 生成 →
  置信度计算 → 冲突检测 → 人工待核清单

claim 三分类:
  authorship_attribution  — 作者归属（"此书作者为 X"的证据链）
  version_chronology      — 版本先后（"版本甲早于版本乙"的推断）
  citation_source         — 引文来源（"此段引自 Y 典籍"的线索）

判断类型:
  rule_based     — 规则/元数据直接判定
  needs_review   — 证据不充分，需人工复核

置信度区间: 0.30 – 0.95
  base 按 claim_type 不同 + evidence_count bonus + consistency bonus
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

# ---------------------------------------------------------------------------
# Claim 类型常量
# ---------------------------------------------------------------------------
CLAIM_TYPE_AUTHORSHIP = "authorship_attribution"
CLAIM_TYPE_VERSION_CHRONOLOGY = "version_chronology"
CLAIM_TYPE_CITATION_SOURCE = "citation_source"

CLAIM_TYPES: tuple[str, ...] = (
    CLAIM_TYPE_AUTHORSHIP,
    CLAIM_TYPE_VERSION_CHRONOLOGY,
    CLAIM_TYPE_CITATION_SOURCE,
)

CLAIM_TYPE_LABELS: Dict[str, str] = {
    CLAIM_TYPE_AUTHORSHIP: "作者归属",
    CLAIM_TYPE_VERSION_CHRONOLOGY: "版本先后",
    CLAIM_TYPE_CITATION_SOURCE: "引文来源",
}

# ---------------------------------------------------------------------------
# 判断类型常量
# ---------------------------------------------------------------------------
JUDGMENT_RULE_BASED = "rule_based"
JUDGMENT_NEEDS_REVIEW = "needs_review"

JUDGMENT_TYPES: frozenset[str] = frozenset(
    {JUDGMENT_RULE_BASED, JUDGMENT_NEEDS_REVIEW}
)

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
# Claim 核心字段名
# ---------------------------------------------------------------------------
FIELD_EVIDENCE_CHAIN_ID = "evidence_chain_id"
FIELD_CLAIM_TYPE = "claim_type"
FIELD_CLAIM_STATEMENT = "claim_statement"
FIELD_CONFIDENCE = "confidence"
FIELD_BASIS_SUMMARY = "basis_summary"
FIELD_JUDGMENT_TYPE = "judgment_type"
FIELD_COUNTER_EVIDENCE = "counter_evidence"
FIELD_NEEDS_MANUAL_REVIEW = "needs_manual_review"
FIELD_REVIEW_STATUS = "review_status"
FIELD_REVIEW_REASONS = "review_reasons"
FIELD_SOURCE_REFS = "source_refs"

EVIDENCE_CHAIN_FIELDS: frozenset[str] = frozenset(
    {
        FIELD_EVIDENCE_CHAIN_ID,
        FIELD_CLAIM_TYPE,
        FIELD_CLAIM_STATEMENT,
        FIELD_CONFIDENCE,
        FIELD_BASIS_SUMMARY,
        FIELD_JUDGMENT_TYPE,
        FIELD_COUNTER_EVIDENCE,
        FIELD_NEEDS_MANUAL_REVIEW,
        FIELD_REVIEW_STATUS,
        FIELD_REVIEW_REASONS,
        FIELD_SOURCE_REFS,
    }
)

# ---------------------------------------------------------------------------
# 置信度常量
# ---------------------------------------------------------------------------
CONFIDENCE_MIN = 0.30
CONFIDENCE_MAX = 0.95
CONFIDENCE_REVIEW_THRESHOLD = 0.60

# ---------------------------------------------------------------------------
# 考据完整度评估
# ---------------------------------------------------------------------------

def assess_evidence_chain_completeness(
    claims: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """评估考据 claim 集合的完整度与质量。"""
    total = len(claims)
    if total == 0:
        return {
            "total": 0,
            "claim_type_distribution": {},
            "judgment_type_distribution": {},
            "review_status_distribution": {},
            "needs_review_count": 0,
            "high_confidence_count": 0,
            "low_confidence_count": 0,
            "conflict_count": 0,
            "avg_confidence": 0.0,
            "has_counter_evidence_count": 0,
            "has_basis_summary_count": 0,
        }

    claim_type_counts: Dict[str, int] = {}
    judgment_counts: Dict[str, int] = {}
    review_counts: Dict[str, int] = {}
    needs_review = 0
    high_confidence = 0
    low_confidence = 0
    conflict_count = 0
    confidence_sum = 0.0
    has_counter = 0
    has_basis = 0

    for claim in claims:
        ct = str(claim.get(FIELD_CLAIM_TYPE) or "").strip()
        if ct:
            claim_type_counts[ct] = claim_type_counts.get(ct, 0) + 1

        jt = str(claim.get(FIELD_JUDGMENT_TYPE) or "").strip()
        if jt:
            judgment_counts[jt] = judgment_counts.get(jt, 0) + 1

        rs = str(claim.get(FIELD_REVIEW_STATUS) or "").strip()
        if rs:
            review_counts[rs] = review_counts.get(rs, 0) + 1

        if claim.get(FIELD_NEEDS_MANUAL_REVIEW):
            needs_review += 1

        conf = _safe_float(claim.get(FIELD_CONFIDENCE))
        confidence_sum += conf
        if conf >= 0.75:
            high_confidence += 1
        elif conf < CONFIDENCE_REVIEW_THRESHOLD:
            low_confidence += 1

        counter = claim.get(FIELD_COUNTER_EVIDENCE)
        if isinstance(counter, (list, tuple)) and len(counter) > 0:
            has_counter += 1
            conflict_count += 1
        elif isinstance(counter, str) and counter.strip():
            has_counter += 1
            conflict_count += 1

        basis = str(claim.get(FIELD_BASIS_SUMMARY) or "").strip()
        if basis:
            has_basis += 1

    return {
        "total": total,
        "claim_type_distribution": {k: claim_type_counts[k] for k in sorted(claim_type_counts)},
        "judgment_type_distribution": {k: judgment_counts[k] for k in sorted(judgment_counts)},
        "review_status_distribution": {k: review_counts[k] for k in sorted(review_counts)},
        "needs_review_count": needs_review,
        "high_confidence_count": high_confidence,
        "low_confidence_count": low_confidence,
        "conflict_count": conflict_count,
        "avg_confidence": round(confidence_sum / total, 4) if total else 0.0,
        "has_counter_evidence_count": has_counter,
        "has_basis_summary_count": has_basis,
    }


# ---------------------------------------------------------------------------
# 考据摘要 (用于 dashboard / artifact / API)
# ---------------------------------------------------------------------------

def build_evidence_chain_summary(
    claims: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """构建考据摘要卡片数据。"""
    return assess_evidence_chain_completeness(claims)


# ---------------------------------------------------------------------------
# Claim 构造辅助
# ---------------------------------------------------------------------------

def build_claim(
    *,
    evidence_chain_id: str,
    claim_type: str,
    claim_statement: str,
    confidence: float,
    basis_summary: str,
    judgment_type: str = "",
    counter_evidence: Sequence[str] = (),
    source_refs: Sequence[str] = (),
    review_reasons: Sequence[str] = (),
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """构造一条规范化的考据 claim。"""
    conf = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, confidence))
    needs_review = (
        judgment_type == JUDGMENT_NEEDS_REVIEW
        or conf < CONFIDENCE_REVIEW_THRESHOLD
        or len(counter_evidence) > 0
    )
    if not judgment_type:
        judgment_type = JUDGMENT_NEEDS_REVIEW if needs_review else JUDGMENT_RULE_BASED

    claim: Dict[str, Any] = {
        FIELD_EVIDENCE_CHAIN_ID: evidence_chain_id,
        FIELD_CLAIM_TYPE: claim_type,
        FIELD_CLAIM_STATEMENT: claim_statement,
        FIELD_CONFIDENCE: round(conf, 4),
        FIELD_BASIS_SUMMARY: basis_summary,
        FIELD_JUDGMENT_TYPE: judgment_type,
        FIELD_COUNTER_EVIDENCE: list(counter_evidence),
        FIELD_NEEDS_MANUAL_REVIEW: needs_review,
        FIELD_REVIEW_STATUS: REVIEW_STATUS_PENDING if needs_review else REVIEW_STATUS_ACCEPTED,
        FIELD_REVIEW_REASONS: list(review_reasons) if review_reasons else (
            ["存在反证待复核"] if counter_evidence else
            (["置信度不足，需人工确认"] if conf < CONFIDENCE_REVIEW_THRESHOLD else [])
        ),
        FIELD_SOURCE_REFS: list(source_refs),
    }
    if extra:
        claim.update(extra)
    return claim


# ---------------------------------------------------------------------------
# 冲突检测
# ---------------------------------------------------------------------------

def detect_claim_conflicts(
    claims: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """检测互相矛盾的 claim，返回冲突对列表。

    冲突定义: 同一 claim_type 内，存在不同 claim_statement 且都有较高置信度。
    """
    conflicts: List[Dict[str, Any]] = []
    by_type: Dict[str, List[Mapping[str, Any]]] = {}
    for claim in claims:
        ct = str(claim.get(FIELD_CLAIM_TYPE) or "").strip()
        if ct:
            by_type.setdefault(ct, []).append(claim)

    for ct, group in by_type.items():
        if len(group) < 2:
            continue
        statements: Dict[str, List[Mapping[str, Any]]] = {}
        for claim in group:
            stmt = str(claim.get(FIELD_CLAIM_STATEMENT) or "").strip()
            if stmt:
                statements.setdefault(stmt, []).append(claim)
        unique_statements = list(statements.keys())
        if len(unique_statements) < 2:
            continue
        for i in range(len(unique_statements)):
            for j in range(i + 1, len(unique_statements)):
                stmt_a = unique_statements[i]
                stmt_b = unique_statements[j]
                claims_a = statements[stmt_a]
                claims_b = statements[stmt_b]
                max_conf_a = max(_safe_float(c.get(FIELD_CONFIDENCE)) for c in claims_a)
                max_conf_b = max(_safe_float(c.get(FIELD_CONFIDENCE)) for c in claims_b)
                if max_conf_a >= 0.40 and max_conf_b >= 0.40:
                    conflicts.append({
                        "claim_type": ct,
                        "statement_a": stmt_a,
                        "statement_b": stmt_b,
                        "confidence_a": round(max_conf_a, 4),
                        "confidence_b": round(max_conf_b, 4),
                        "claim_ids_a": [str(c.get(FIELD_EVIDENCE_CHAIN_ID) or "") for c in claims_a],
                        "claim_ids_b": [str(c.get(FIELD_EVIDENCE_CHAIN_ID) or "") for c in claims_b],
                    })
    return conflicts


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
