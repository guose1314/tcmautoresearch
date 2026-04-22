"""TCMReasoningTrace 字段合同 — 中医推理链条的唯一权威定义。

- ``TCMReasoningPremise``  : 推理输入的最小单元（证据/关系/上下文）
- ``TCMReasoningStep``     : 单条规则触发后的推理步骤
- ``TCMReasoningTrace``    : 一次 ``run_tcm_reasoning`` 的完整可审计输出

设计目标:
  - 与 ``topic_proposal-v1`` / ``authenticity-verdict-v1`` / ``self-refine-v1``
    保持同样的 dataclass + ``to_dict`` / ``from_dict`` 风格
  - 不依赖 LLM、Neo4j、PhaseOrchestrator；可独立序列化与回归
  - reflect 阶段可直接消费 ``TCMReasoningTrace`` 进行打分

五大核心范式:
  - 同病异治  ：同一疾病在不同证候下采用不同治法
  - 异病同治  ：不同疾病若证候相同则可用同一治法
  - 三因制宜  ：因时 / 因地 / 因人调整治法
  - 方证对应  ：方剂与证候之间的对应规律
  - 君臣佐使  ：方剂内部的配伍角色
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

CONTRACT_VERSION = "tcm-reasoning-trace-v1"
TCM_REASONING_CONTRACT_VERSION = CONTRACT_VERSION

# ── Reasoning patterns ────────────────────────────────────────────────

PATTERN_TONGBING_YIZHI = "tongbing_yizhi"          # 同病异治
PATTERN_YIBING_TONGZHI = "yibing_tongzhi"          # 异病同治
PATTERN_SANYIN_ZHIYI = "sanyin_zhiyi"              # 三因制宜
PATTERN_FANGZHENG_DUIYING = "fangzheng_duiying"    # 方证对应
PATTERN_JUNCHEN_ZUOSHI = "junchen_zuoshi"          # 君臣佐使

REASONING_PATTERNS: tuple[str, ...] = (
    PATTERN_TONGBING_YIZHI,
    PATTERN_YIBING_TONGZHI,
    PATTERN_SANYIN_ZHIYI,
    PATTERN_FANGZHENG_DUIYING,
    PATTERN_JUNCHEN_ZUOSHI,
)

PATTERN_LABELS: Dict[str, str] = {
    PATTERN_TONGBING_YIZHI: "同病异治",
    PATTERN_YIBING_TONGZHI: "异病同治",
    PATTERN_SANYIN_ZHIYI: "三因制宜",
    PATTERN_FANGZHENG_DUIYING: "方证对应",
    PATTERN_JUNCHEN_ZUOSHI: "君臣佐使",
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _clamp_unit(value: Any) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


@dataclass
class TCMReasoningPremise:
    """推理前提 — 一条进入推理引擎的最小输入。"""

    premise_kind: str = ""        # symptom / syndrome / formula / herb / context
    canonical: str = ""           # 规范化名称
    label: str = ""               # 原文出现形式
    source_ref: str = ""          # 引用键（catalog_id / urn / phase）
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TCMReasoningPremise":
        d = dict(data) if isinstance(data, Mapping) else {}
        return cls(
            premise_kind=_as_text(d.get("premise_kind")),
            canonical=_as_text(d.get("canonical")),
            label=_as_text(d.get("label")),
            source_ref=_as_text(d.get("source_ref")),
            note=_as_text(d.get("note")),
        )


@dataclass
class TCMReasoningStep:
    """单条规则触发产生的推理步骤。"""

    rule_id: str = ""
    pattern: str = ""             # 必须取自 REASONING_PATTERNS
    premises: List[TCMReasoningPremise] = field(default_factory=list)
    conclusion: str = ""
    confidence: float = 0.0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "pattern": self.pattern,
            "premises": [p.to_dict() for p in self.premises],
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TCMReasoningStep":
        d = dict(data) if isinstance(data, Mapping) else {}
        raw_premises: Sequence[Any] = d.get("premises") or []
        return cls(
            rule_id=_as_text(d.get("rule_id")),
            pattern=_as_text(d.get("pattern")),
            premises=[TCMReasoningPremise.from_dict(p) for p in raw_premises if isinstance(p, Mapping)],
            conclusion=_as_text(d.get("conclusion")),
            confidence=_clamp_unit(d.get("confidence")),
            rationale=_as_text(d.get("rationale")),
        )


@dataclass
class TCMReasoningTrace:
    """一次推理引擎运行的完整可审计 trace。"""

    seed: str = ""
    premises: List[TCMReasoningPremise] = field(default_factory=list)
    steps: List[TCMReasoningStep] = field(default_factory=list)
    overall_confidence: float = 0.0
    pattern_coverage: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "premises": [p.to_dict() for p in self.premises],
            "steps": [s.to_dict() for s in self.steps],
            "overall_confidence": self.overall_confidence,
            "pattern_coverage": list(self.pattern_coverage),
            "notes": self.notes,
            "contract_version": CONTRACT_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TCMReasoningTrace":
        d = dict(data) if isinstance(data, Mapping) else {}
        raw_premises: Sequence[Any] = d.get("premises") or []
        raw_steps: Sequence[Any] = d.get("steps") or []
        coverage = d.get("pattern_coverage") or []
        return cls(
            seed=_as_text(d.get("seed")),
            premises=[TCMReasoningPremise.from_dict(p) for p in raw_premises if isinstance(p, Mapping)],
            steps=[TCMReasoningStep.from_dict(s) for s in raw_steps if isinstance(s, Mapping)],
            overall_confidence=_clamp_unit(d.get("overall_confidence")),
            pattern_coverage=[_as_text(x) for x in coverage if _as_text(x)],
            notes=_as_text(d.get("notes")),
        )


__all__ = [
    "CONTRACT_VERSION",
    "TCM_REASONING_CONTRACT_VERSION",
    "PATTERN_TONGBING_YIZHI",
    "PATTERN_YIBING_TONGZHI",
    "PATTERN_SANYIN_ZHIYI",
    "PATTERN_FANGZHENG_DUIYING",
    "PATTERN_JUNCHEN_ZUOSHI",
    "REASONING_PATTERNS",
    "PATTERN_LABELS",
    "TCMReasoningPremise",
    "TCMReasoningStep",
    "TCMReasoningTrace",
]
