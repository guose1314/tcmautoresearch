"""AuthenticityVerdict 字段合同 — 文献考据学裁定的唯一权威定义。

裁定三维度:
  - date_verdict:   年代裁定（confirmed / range / disputed / legendary / unknown）
  - author_verdict: 作者裁定（confirmed / attributed / anonymous / disputed）
  - authenticity:   真伪裁定（authentic / doubtful / forged / indeterminate）

每条裁定附带:
  - catalog_id:    回指 catalog_contract.catalog_id
  - evidence:      list[VerdictEvidence] — 可追溯的判定依据
  - confidence:    0..1
  - reviewer:      留给后续人工复核

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
DATE_VERDICT_CONFIRMED = "confirmed"      # 有明确成书时间证据
DATE_VERDICT_RANGE = "range"              # 区间裁定（朝代或世纪）
DATE_VERDICT_DISPUTED = "disputed"        # 学界存在争议
DATE_VERDICT_LEGENDARY = "legendary"      # 托名上古，实际成书晚出
DATE_VERDICT_UNKNOWN = "unknown"          # 无证据

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
AUTHOR_VERDICT_CONFIRMED = "confirmed"        # 作者明确
AUTHOR_VERDICT_ATTRIBUTED = "attributed"      # 旧题某某，存在归属约定
AUTHOR_VERDICT_ANONYMOUS = "anonymous"        # 佚名
AUTHOR_VERDICT_DISPUTED = "disputed"          # 作者争议（如伪托）

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


@dataclass
class VerdictEvidence:
    """裁定依据 — 一条考据证据的最小化记录。"""

    kind: str = ""             # date | author | authenticity
    source_ref: str = ""       # 引用键（catalog/url/note）
    excerpt: str = ""          # 关键引文
    weight: float = 0.0        # 0..1，证据强度

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
    date_estimate: str = ""             # 例如 "东汉" / "公元 200 年前后"
    author_verdict: str = AUTHOR_VERDICT_ANONYMOUS
    author_name: str = ""
    authenticity: str = AUTHENTICITY_INDETERMINATE
    evidence: List[VerdictEvidence] = field(default_factory=list)
    confidence: float = 0.0
    reviewer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "work_title": self.work_title,
            "date_verdict": self.date_verdict,
            "date_estimate": self.date_estimate,
            "author_verdict": self.author_verdict,
            "author_name": self.author_name,
            "authenticity": self.authenticity,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "reviewer": self.reviewer,
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
        return cls(
            catalog_id=_as_text(d.get("catalog_id")),
            work_title=_as_text(d.get("work_title")),
            date_verdict=_enum_or_default(
                d.get("date_verdict"),
                allowed=DATE_VERDICTS,
                default=DATE_VERDICT_UNKNOWN,
            ),
            date_estimate=_as_text(d.get("date_estimate")),
            author_verdict=_enum_or_default(
                d.get("author_verdict"),
                allowed=AUTHOR_VERDICTS,
                default=AUTHOR_VERDICT_ANONYMOUS,
            ),
            author_name=_as_text(d.get("author_name")),
            authenticity=_enum_or_default(
                d.get("authenticity"),
                allowed=AUTHENTICITY_LEVELS,
                default=AUTHENTICITY_INDETERMINATE,
            ),
            evidence=evidence,
            confidence=_clamp(confidence),
            reviewer=_as_text(d.get("reviewer")),
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
