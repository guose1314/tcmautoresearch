"""TopicProposal 字段合同 — 研究选题（环节①）的唯一权威定义。

候选课题结构:
  TopicProposal(
      seed,                      # 原始研究方向 seed（用户输入）
      sub_question,              # 拆解后的子问题（一题一案）
      angle,                     # 研究角度，如 "同病异治"/"考据"/"训诂"
      source_candidates,         # 证据候选来源（catalog/KG/外部数据库）
      falsifiable_hypothesis_hint,
      priority,                  # 0..1, 越高越优先
      rationale,                 # 评分理由文字
  )

设计目标:
  - 与 evidence_contract / catalog_contract 保持同样的 dataclass + to_dict/from_dict 风格
  - 不依赖 KG / LLM / Neo4j；可独立序列化与回归
  - 候选数量受 TOPIC_PROPOSAL_MIN / MAX 约束，便于 J-1 Done 定义校验
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

CONTRACT_VERSION = "topic-proposal-v1"
TOPIC_PROPOSAL_CONTRACT_VERSION = CONTRACT_VERSION

# 文献研究法环节① 要求一次给出 3-5 个候选课题
TOPIC_PROPOSAL_MIN = 3
TOPIC_PROPOSAL_MAX = 5

# 候选研究角度（与 §0 文献研究法 6 环节互文）
ANGLE_TONGBING_YIZHI = "同病异治"
ANGLE_YIBING_TONGZHI = "异病同治"
ANGLE_SANYIN_ZHIYI = "三因制宜"
ANGLE_FANGZHENG = "方证规律"
ANGLE_SCHOOL_LINEAGE = "学派沿革"
ANGLE_TEXTUAL_CRITICISM = "考据辨伪"
ANGLE_EXEGESIS = "训诂注释"
ANGLE_CATALOG_VERSION = "目录版本"

CANDIDATE_ANGLES: tuple[str, ...] = (
    ANGLE_FANGZHENG,
    ANGLE_TONGBING_YIZHI,
    ANGLE_YIBING_TONGZHI,
    ANGLE_SANYIN_ZHIYI,
    ANGLE_TEXTUAL_CRITICISM,
    ANGLE_EXEGESIS,
    ANGLE_SCHOOL_LINEAGE,
    ANGLE_CATALOG_VERSION,
)


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return float(value)


@dataclass
class TopicSourceCandidate:
    """证据候选来源 — 一条课题指向的可能资料源。

    支持三类来源:
      - catalog: 本地目录学条目（catalog_contract）
      - kg:      Neo4j / TCMKnowledgeGraph 子图节点
      - external: arxiv / google_scholar / ctext 等外部库
    """

    source_kind: str = ""           # catalog | kg | external
    source_ref: str = ""            # 引用键（catalog_id / node name / url）
    title: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TopicSourceCandidate":
        d = dict(data) if isinstance(data, Mapping) else {}
        return cls(
            source_kind=_as_text(d.get("source_kind")),
            source_ref=_as_text(d.get("source_ref")),
            title=_as_text(d.get("title")),
            note=_as_text(d.get("note")),
        )


@dataclass
class TopicProposal:
    """单个候选课题 — TopicDiscovery 的最小输出单元。"""

    seed: str = ""
    sub_question: str = ""
    angle: str = ""
    source_candidates: List[TopicSourceCandidate] = field(default_factory=list)
    falsifiable_hypothesis_hint: str = ""
    priority: float = 0.0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "sub_question": self.sub_question,
            "angle": self.angle,
            "source_candidates": [s.to_dict() for s in self.source_candidates],
            "falsifiable_hypothesis_hint": self.falsifiable_hypothesis_hint,
            "priority": self.priority,
            "rationale": self.rationale,
            "contract_version": CONTRACT_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TopicProposal":
        d = dict(data) if isinstance(data, Mapping) else {}
        raw_sources = d.get("source_candidates") or []
        sources: List[TopicSourceCandidate] = []
        for item in raw_sources:
            if isinstance(item, TopicSourceCandidate):
                sources.append(item)
            elif isinstance(item, Mapping):
                sources.append(TopicSourceCandidate.from_dict(item))
        try:
            priority = float(d.get("priority") or 0.0)
        except (TypeError, ValueError):
            priority = 0.0
        return cls(
            seed=_as_text(d.get("seed")),
            sub_question=_as_text(d.get("sub_question")),
            angle=_as_text(d.get("angle")),
            source_candidates=sources,
            falsifiable_hypothesis_hint=_as_text(d.get("falsifiable_hypothesis_hint")),
            priority=_clamp(priority),
            rationale=_as_text(d.get("rationale")),
        )


def normalize_topic_proposals(
    proposals: Sequence[Any],
) -> List[Dict[str, Any]]:
    """将任意输入（dataclass 实例或 dict）规范化为序列化字典列表。"""
    normalized: List[Dict[str, Any]] = []
    for item in proposals or []:
        if isinstance(item, TopicProposal):
            normalized.append(item.to_dict())
        elif isinstance(item, Mapping):
            normalized.append(TopicProposal.from_dict(item).to_dict())
    return normalized


def build_topic_discovery_summary(
    seed: str,
    proposals: Sequence[Any],
) -> Dict[str, Any]:
    """构建 dashboard / artifact 友好的选题摘要卡片数据。"""

    normalized = normalize_topic_proposals(proposals)
    angle_counts: Dict[str, int] = {}
    source_kind_counts: Dict[str, int] = {}
    for item in normalized:
        angle = item.get("angle") or ""
        if angle:
            angle_counts[angle] = angle_counts.get(angle, 0) + 1
        for src in item.get("source_candidates") or []:
            kind = (src or {}).get("source_kind") or ""
            if kind:
                source_kind_counts[kind] = source_kind_counts.get(kind, 0) + 1

    priorities = [float(item.get("priority") or 0.0) for item in normalized]
    avg_priority = round(sum(priorities) / len(priorities), 4) if priorities else 0.0

    meets_contract = TOPIC_PROPOSAL_MIN <= len(normalized) <= TOPIC_PROPOSAL_MAX
    has_evidence = all(
        bool(item.get("source_candidates")) for item in normalized
    ) if normalized else False

    return {
        "seed": _as_text(seed),
        "proposal_count": len(normalized),
        "meets_count_contract": meets_contract,
        "all_have_evidence": has_evidence,
        "angle_distribution": {k: angle_counts[k] for k in sorted(angle_counts)},
        "source_kind_distribution": {
            k: source_kind_counts[k] for k in sorted(source_kind_counts)
        },
        "avg_priority": avg_priority,
        "contract_version": CONTRACT_VERSION,
    }
