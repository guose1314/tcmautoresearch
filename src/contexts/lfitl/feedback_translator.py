"""FeedbackTranslator：把反馈条目翻译成 TranslationPlan。

三种翻译路径（覆盖在单测里逐项断言）：

- ``graph_weight``：来自 ``feedbacks[i]["graph_targets"]``（node_ids）配合 severity →
  ``GraphWeightAction(ids, factor)``。critical 0.5 / high 0.7 / medium 0.9 / low 1.0。
- ``prompt_bias``：按 ``source_phase`` 聚合 ``issue_fields``、违规规则 → 一段中文偏置短语。
- ``mode``：critical 总数 ≥ 1 ⇒ ``conservative``；high ≥ 3 ⇒ ``cautious``；否则 ``normal``。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

_DEFAULT_SEVERITY_FACTOR = {
    "critical": 0.5,
    "high": 0.7,
    "medium": 0.9,
    "low": 1.0,
}


@dataclass
class FeedbackEntry:
    """``learning_feedback_library`` 风格反馈的归一化形态。"""

    source_phase: str
    issues: List[Dict[str, Any]] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)
    graph_targets: List[str] = field(default_factory=list)
    severity: str = "medium"
    issue_fields: List[str] = field(default_factory=list)
    round_index: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FeedbackEntry":
        violations = list(payload.get("violations") or [])
        # severity 推断：以最严重的违规为准
        severity = str(payload.get("severity") or "").strip().lower()
        if not severity and violations:
            order = ("critical", "high", "medium", "low")
            for level in order:
                if any((v or {}).get("severity") == level for v in violations):
                    severity = level
                    break
        if not severity:
            severity = "medium"
        issue_fields = list(payload.get("issue_fields") or [])
        if not issue_fields and payload.get("issues"):
            issue_fields = sorted(
                {
                    str((it or {}).get("field") or "").strip()
                    for it in payload.get("issues") or []
                    if (it or {}).get("field")
                }
            )
        graph_targets = list(payload.get("graph_targets") or [])
        if not graph_targets:
            # issues 内可能直接附带 entity_id / node_id
            for it in payload.get("issues") or []:
                node_id = (it or {}).get("entity_id") or (it or {}).get("node_id")
                if node_id:
                    graph_targets.append(str(node_id))
        return cls(
            source_phase=str(payload.get("source_phase") or "unknown"),
            issues=list(payload.get("issues") or []),
            violations=violations,
            graph_targets=[str(x) for x in graph_targets if str(x).strip()],
            severity=severity,
            issue_fields=[str(x) for x in issue_fields if str(x).strip()],
            round_index=int(payload.get("round_index") or 0),
            extra={
                k: v
                for k, v in payload.items()
                if k
                not in {
                    "source_phase",
                    "issues",
                    "violations",
                    "graph_targets",
                    "severity",
                    "issue_fields",
                    "round_index",
                }
            },
        )


@dataclass
class GraphWeightAction:
    """对一组 node id 应用 ``weight *= factor``。"""

    node_ids: List[str]
    factor: float
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_ids": list(self.node_ids),
            "factor": self.factor,
            "reason": self.reason,
        }


@dataclass
class PromptBiasAction:
    """注入到 SelfRefineRunner.inputs 的偏置块。"""

    purpose: str
    bias_text: str
    avoid_fields: List[str] = field(default_factory=list)
    severity: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose": self.purpose,
            "bias_text": self.bias_text,
            "avoid_fields": list(self.avoid_fields),
            "severity": self.severity,
        }


@dataclass
class TranslationPlan:
    """``FeedbackTranslator.translate`` 的产物。"""

    graph_weight_actions: List[GraphWeightAction] = field(default_factory=list)
    prompt_bias_actions: List[PromptBiasAction] = field(default_factory=list)
    modes: Dict[str, str] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)
    mined_patterns: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_weight_actions": [a.to_dict() for a in self.graph_weight_actions],
            "prompt_bias_actions": [a.to_dict() for a in self.prompt_bias_actions],
            "modes": dict(self.modes),
            "summary": dict(self.summary),
            "mined_patterns": list(self.mined_patterns),
        }


class FeedbackTranslator:
    """主翻译器。"""

    def __init__(
        self,
        *,
        severity_factor: Optional[Mapping[str, float]] = None,
        critical_mode_threshold: int = 1,
        high_mode_threshold: int = 3,
        pattern_miner: Optional[Any] = None,
        neo4j_driver: Optional[Any] = None,
    ) -> None:
        self._severity_factor = dict(severity_factor or _DEFAULT_SEVERITY_FACTOR)
        self._critical_mode_threshold = int(critical_mode_threshold)
        self._high_mode_threshold = int(high_mode_threshold)
        self._pattern_miner = pattern_miner
        self._neo4j_driver = neo4j_driver

    # ------------------------------------------------------------------ #
    def translate(
        self,
        feedbacks: Sequence[Any],
        *,
        mined_patterns: Optional[Sequence[Any]] = None,
        since_ts: Optional[float] = None,
    ) -> TranslationPlan:
        entries: List[FeedbackEntry] = []
        for item in feedbacks or []:
            if isinstance(item, FeedbackEntry):
                entries.append(item)
            elif isinstance(item, Mapping):
                entries.append(FeedbackEntry.from_dict(item))
            else:
                continue

        # T5.3: 生成 plan 前先调 miner 拿高频负反馈模式
        patterns = list(mined_patterns) if mined_patterns is not None else []
        if (
            not patterns
            and self._pattern_miner is not None
            and self._neo4j_driver is not None
        ):
            try:
                patterns = list(
                    self._pattern_miner.mine(self._neo4j_driver, since_ts=since_ts)
                )
            except Exception:  # noqa: BLE001
                patterns = []

        plan = TranslationPlan()
        plan.graph_weight_actions = self._translate_graph(entries)
        plan.prompt_bias_actions = self._translate_prompt(entries, patterns)
        plan.modes = self._translate_modes(entries)
        plan.mined_patterns = [
            p.to_dict() if hasattr(p, "to_dict") else dict(p) for p in patterns
        ]
        plan.summary = {
            "feedback_count": len(entries),
            "phases_touched": sorted(
                {e.source_phase for e in entries if e.source_phase}
            ),
            "graph_action_count": len(plan.graph_weight_actions),
            "prompt_bias_count": len(plan.prompt_bias_actions),
            "mined_pattern_count": len(plan.mined_patterns),
            "modes": dict(plan.modes),
        }
        return plan

    # ------------------------------------------------------------------ #
    def _translate_graph(
        self, entries: Iterable[FeedbackEntry]
    ) -> List[GraphWeightAction]:
        # 按 (severity, factor) 聚合：同 severity 一次操作
        bucket: Dict[str, List[str]] = defaultdict(list)
        for entry in entries:
            if not entry.graph_targets:
                continue
            sev = (
                entry.severity if entry.severity in self._severity_factor else "medium"
            )
            for nid in entry.graph_targets:
                if nid not in bucket[sev]:
                    bucket[sev].append(nid)
        actions: List[GraphWeightAction] = []
        for sev, ids in bucket.items():
            factor = self._severity_factor.get(sev, 1.0)
            if factor == 1.0 or not ids:
                continue
            actions.append(
                GraphWeightAction(
                    node_ids=ids,
                    factor=factor,
                    reason=f"feedback_severity={sev}",
                )
            )
        return actions

    def _translate_prompt(
        self,
        entries: Iterable[FeedbackEntry],
        patterns: Optional[Sequence[Any]] = None,
    ) -> List[PromptBiasAction]:
        # 按 source_phase 聚合 issue_fields 与最严重 severity
        per_phase: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"avoid": [], "violations": [], "severity": "low"}
        )
        sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        for entry in entries:
            slot = per_phase[entry.source_phase]
            for field_name in entry.issue_fields:
                if field_name and field_name not in slot["avoid"]:
                    slot["avoid"].append(field_name)
            for v in entry.violations:
                rule_id = (v or {}).get("rule_id")
                if rule_id and rule_id not in slot["violations"]:
                    slot["violations"].append(rule_id)
            if sev_order.get(entry.severity, 0) > sev_order.get(slot["severity"], 0):
                slot["severity"] = entry.severity

        actions: List[PromptBiasAction] = []
        for purpose, slot in per_phase.items():
            avoid = slot["avoid"]
            violations = slot["violations"]
            if not avoid and not violations:
                continue
            parts: List[str] = []
            if avoid:
                parts.append(
                    "请避免在以下字段上重复历史问题：" + "、".join(avoid) + "。"
                )
            if violations:
                parts.append(
                    "请严格遵守以下宪法规则（曾被触发）："
                    + "、".join(violations)
                    + "。"
                )
            # T5.3: 把 miner 找出的"高频被纠正模式"也写入 bias_text
            pattern_sentence = self._build_pattern_sentence(patterns or [])
            if pattern_sentence:
                parts.append(pattern_sentence)
            actions.append(
                PromptBiasAction(
                    purpose=purpose,
                    bias_text=" ".join(parts),
                    avoid_fields=avoid,
                    severity=slot["severity"],
                )
            )
        return actions

    @staticmethod
    def _build_pattern_sentence(patterns: Sequence[Any]) -> str:
        if not patterns:
            return ""
        snippets: List[str] = []
        for p in patterns[:5]:
            if hasattr(p, "to_dict"):
                d = p.to_dict()
            elif isinstance(p, Mapping):
                d = dict(p)
            else:
                continue
            labels = list(d.get("node_labels") or [])
            rels = list(d.get("rel_types") or [])
            if len(labels) >= 2 and rels:
                snippets.append(f"({labels[0]})-[{rels[0]}]->({labels[1]})")
            elif labels:
                snippets.append("/".join(labels))
        if not snippets:
            return ""
        return "高频被反馈纠正的图模式（请规避）：" + "；".join(snippets) + "。"

    def _translate_modes(self, entries: Iterable[FeedbackEntry]) -> Dict[str, str]:
        critical = sum(1 for e in entries if e.severity == "critical")
        high = sum(1 for e in entries if e.severity == "high")
        if critical >= self._critical_mode_threshold:
            return {"global": "conservative"}
        if high >= self._high_mode_threshold:
            return {"global": "cautious"}
        return {"global": "normal"}


__all__ = [
    "FeedbackEntry",
    "FeedbackTranslator",
    "GraphWeightAction",
    "PromptBiasAction",
    "TranslationPlan",
]
