"""AuthenticityVerdict 字段合同 — 文献考据学裁定的唯一权威定义。

裁定三维度:
  - date_verdict:   年代裁定（confirmed / range / disputed / legendary / unknown）
  - author_verdict: 作者裁定（confirmed / attributed / anonymous / disputed）
  - authenticity:   真伪裁定（authentic / doubtful / forged / indeterminate）

每条裁定附带:
  - catalog_id:    回指 catalog_contract.catalog_id
  - evidence:      list[VerdictEvidence] — 可追溯的判定依据
    - citation_refs: 目录/版本/引文来源引用键
    - witness_keys:  对勘 witness / version lineage 线索
  - confidence:    0..1
    - review_status: 人工复核状态
    - reviewer:      可选 LLM/人工复核提示

设计目标:
  - 与 evidence_contract / catalog_contract 同款 dataclass + to_dict/from_dict 风格
  - 可独立序列化、可被 dashboard / artifact 复用
  - 不依赖 LLM 与 Neo4j
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

CONTRACT_VERSION = "authenticity-verdict-v1"
VERDICT_CONTRACT_VERSION = CONTRACT_VERSION

# ---------------------------------------------------------------------------
# 年代裁定
# ---------------------------------------------------------------------------
DATE_VERDICT_CONFIRMED = "confirmed"  # 有明确成书时间证据
DATE_VERDICT_RANGE = "range"  # 区间裁定（朝代或世纪）
DATE_VERDICT_DISPUTED = "disputed"  # 学界存在争议
DATE_VERDICT_LEGENDARY = "legendary"  # 托名上古，实际成书晚出
DATE_VERDICT_UNKNOWN = "unknown"  # 无证据

DATE_VERDICTS: tuple[str, ...] = (
    DATE_VERDICT_CONFIRMED,
    DATE_VERDICT_RANGE,
    DATE_VERDICT_DISPUTED,
    DATE_VERDICT_LEGENDARY,
    DATE_VERDICT_UNKNOWN,
)

# ---------------------------------------------------------------------------
# 作者裁定
# ---------------------------------------------------------------------------
AUTHOR_VERDICT_CONFIRMED = "confirmed"  # 作者明确
AUTHOR_VERDICT_ATTRIBUTED = "attributed"  # 旧题某某，存在归属约定
AUTHOR_VERDICT_ANONYMOUS = "anonymous"  # 佚名
AUTHOR_VERDICT_DISPUTED = "disputed"  # 作者争议（如伪托）

AUTHOR_VERDICTS: tuple[str, ...] = (
    AUTHOR_VERDICT_CONFIRMED,
    AUTHOR_VERDICT_ATTRIBUTED,
    AUTHOR_VERDICT_ANONYMOUS,
    AUTHOR_VERDICT_DISPUTED,
)

# ---------------------------------------------------------------------------
# 真伪裁定
# ---------------------------------------------------------------------------
AUTHENTICITY_AUTHENTIC = "authentic"
AUTHENTICITY_DOUBTFUL = "doubtful"
AUTHENTICITY_FORGED = "forged"
AUTHENTICITY_INDETERMINATE = "indeterminate"

AUTHENTICITY_LEVELS: tuple[str, ...] = (
    AUTHENTICITY_AUTHENTIC,
    AUTHENTICITY_DOUBTFUL,
    AUTHENTICITY_FORGED,
    AUTHENTICITY_INDETERMINATE,
)

# ---------------------------------------------------------------------------
# 人工复核状态
# ---------------------------------------------------------------------------
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_ACCEPTED = "accepted"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_NEEDS_SOURCE = "needs_source"

REVIEW_STATUSES: tuple[str, ...] = (
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_ACCEPTED,
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_NEEDS_SOURCE,
)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return float(value)


def _enum_or_default(value: Any, *, allowed: Sequence[str], default: str) -> str:
    text = _as_text(value).lower()
    return text if text in allowed else default


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        text = _as_text(value)
        return [text] if text else []
    normalized: List[str] = []
    for item in value:
        text = _as_text(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _default_needs_review_reasons(
    date_verdict: str,
    author_verdict: str,
    authenticity: str,
) -> List[str]:
    reasons: List[str] = []
    if date_verdict == DATE_VERDICT_DISPUTED:
        reasons.append("年代裁定存在争议")
    if date_verdict == DATE_VERDICT_LEGENDARY:
        reasons.append("年代涉及托名或传说性归属")
    if author_verdict == AUTHOR_VERDICT_ANONYMOUS:
        reasons.append("作者佚名，需人工确认目录归属")
    if author_verdict == AUTHOR_VERDICT_DISPUTED:
        reasons.append("作者归属存在争议")
    if authenticity == AUTHENTICITY_DOUBTFUL:
        reasons.append("真伪裁定为 doubtful")
    if authenticity == AUTHENTICITY_FORGED:
        reasons.append("真伪裁定为 forged")
    if authenticity == AUTHENTICITY_INDETERMINATE:
        reasons.append("真伪裁定未定")
    return reasons


def _infer_needs_review(
    date_verdict: str,
    author_verdict: str,
    authenticity: str,
) -> bool:
    return bool(
        _default_needs_review_reasons(date_verdict, author_verdict, authenticity)
    )


def _normalize_needs_review_reason(
    reason: Any,
    *,
    needs_review: bool,
    date_verdict: str,
    author_verdict: str,
    authenticity: str,
) -> str:
    text = _as_text(reason)
    if text or not needs_review:
        return text
    fallback = _default_needs_review_reasons(
        date_verdict,
        author_verdict,
        authenticity,
    )
    return "；".join(fallback) if fallback else "裁定存在待人工复核要素"


@dataclass
class VerdictEvidence:
    """裁定依据 — 一条考据证据的最小化记录。"""

    kind: str = ""  # date | author | authenticity
    source_ref: str = ""  # 引用键（catalog/url/note）
    excerpt: str = ""  # 关键引文
    weight: float = 0.0  # 0..1，证据强度

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerdictEvidence":
        d = dict(data) if isinstance(data, Mapping) else {}
        try:
            weight = float(d.get("weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        return cls(
            kind=_as_text(d.get("kind")),
            source_ref=_as_text(d.get("source_ref")),
            excerpt=_as_text(d.get("excerpt")),
            weight=_clamp(weight),
        )


@dataclass
class AuthenticityVerdict:
    """单条 catalog 资产的真伪/年代/作者裁定。"""

    catalog_id: str = ""
    work_title: str = ""
    date_verdict: str = DATE_VERDICT_UNKNOWN
    date_estimate: str = ""  # 例如 "东汉" / "公元 200 年前后"
    author_verdict: str = AUTHOR_VERDICT_ANONYMOUS
    author_name: str = ""
    authenticity: str = AUTHENTICITY_INDETERMINATE
    evidence: List[VerdictEvidence] = field(default_factory=list)
    citation_refs: List[str] = field(default_factory=list)
    witness_keys: List[str] = field(default_factory=list)
    confidence: float = 0.0
    review_status: str = REVIEW_STATUS_PENDING
    reviewer: str = ""
    reviewer_decision: str = ""
    reviewed_at: str = ""
    needs_review: bool = False
    needs_review_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        needs_review = bool(self.needs_review)
        needs_review_reason = _normalize_needs_review_reason(
            self.needs_review_reason,
            needs_review=needs_review,
            date_verdict=self.date_verdict,
            author_verdict=self.author_verdict,
            authenticity=self.authenticity,
        )
        return {
            "catalog_id": self.catalog_id,
            "work_title": self.work_title,
            "date_verdict": self.date_verdict,
            "date_estimate": self.date_estimate,
            "author_verdict": self.author_verdict,
            "author_name": self.author_name,
            "authenticity": self.authenticity,
            "evidence": [e.to_dict() for e in self.evidence],
            "citation_refs": list(self.citation_refs),
            "witness_keys": list(self.witness_keys),
            "confidence": self.confidence,
            "review_status": self.review_status,
            "reviewer": self.reviewer,
            "reviewer_decision": self.reviewer_decision,
            "reviewed_at": self.reviewed_at,
            "needs_review": needs_review,
            "needs_review_reason": needs_review_reason,
            "contract_version": CONTRACT_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthenticityVerdict":
        d = dict(data) if isinstance(data, Mapping) else {}
        raw_evidence = d.get("evidence") or []
        evidence: List[VerdictEvidence] = []
        for item in raw_evidence:
            if isinstance(item, VerdictEvidence):
                evidence.append(item)
            elif isinstance(item, Mapping):
                evidence.append(VerdictEvidence.from_dict(item))
        try:
            confidence = float(d.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        date_verdict = _enum_or_default(
            d.get("date_verdict"),
            allowed=DATE_VERDICTS,
            default=DATE_VERDICT_UNKNOWN,
        )
        author_verdict = _enum_or_default(
            d.get("author_verdict"),
            allowed=AUTHOR_VERDICTS,
            default=AUTHOR_VERDICT_ANONYMOUS,
        )
        authenticity = _enum_or_default(
            d.get("authenticity"),
            allowed=AUTHENTICITY_LEVELS,
            default=AUTHENTICITY_INDETERMINATE,
        )
        needs_review = (
            bool(d.get("needs_review"))
            if "needs_review" in d
            else _infer_needs_review(date_verdict, author_verdict, authenticity)
        )
        return cls(
            catalog_id=_as_text(d.get("catalog_id")),
            work_title=_as_text(d.get("work_title")),
            date_verdict=date_verdict,
            date_estimate=_as_text(d.get("date_estimate")),
            author_verdict=author_verdict,
            author_name=_as_text(d.get("author_name")),
            authenticity=authenticity,
            evidence=evidence,
            citation_refs=_as_string_list(d.get("citation_refs")),
            witness_keys=_as_string_list(d.get("witness_keys")),
            confidence=_clamp(confidence),
            review_status=_enum_or_default(
                d.get("review_status"),
                allowed=REVIEW_STATUSES,
                default=REVIEW_STATUS_PENDING,
            ),
            reviewer=_as_text(d.get("reviewer")),
            reviewer_decision=_as_text(d.get("reviewer_decision")),
            reviewed_at=_as_text(d.get("reviewed_at")),
            needs_review=needs_review,
            needs_review_reason=_normalize_needs_review_reason(
                d.get("needs_review_reason") or d.get("review_reason"),
                needs_review=needs_review,
                date_verdict=date_verdict,
                author_verdict=author_verdict,
                authenticity=authenticity,
            ),
        )


def normalize_authenticity_verdicts(
    verdicts: Sequence[Any],
) -> List[Dict[str, Any]]:
    """将任意 dataclass / dict 输入规范化为字典列表。"""
    normalized: List[Dict[str, Any]] = []
    for item in verdicts or []:
        if isinstance(item, AuthenticityVerdict):
            normalized.append(item.to_dict())
        elif isinstance(item, Mapping):
            normalized.append(AuthenticityVerdict.from_dict(item).to_dict())
    return normalized
