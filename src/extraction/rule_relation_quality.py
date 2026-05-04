"""Quality tiering for rule-derived semantic relationships."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional

RULE_RELATION_QUALITY_VERSION = "rule-relation-quality-v1"
PROMOTABLE_RULE_TIERS = frozenset({"strong_rule", "weak_rule"})
CANDIDATE_RULE_TIERS = frozenset({"candidate_rule", "rejected_rule"})

_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]")
_TRIGGER_KEYWORDS = {
    "composition": ("组成", "含", "由", "君", "臣", "佐", "使"),
    "treats": ("主治", "治", "治疗", "疗", "宜"),
    "efficacy": ("功效", "能", "可", "补", "清", "活血", "解毒", "健脾"),
    "property": ("味", "气", "性", "归经"),
}
_COMPATIBLE_PAIRS = {
    ("formula", "herb", "sovereign"),
    ("formula", "herb", "minister"),
    ("formula", "herb", "assistant"),
    ("formula", "herb", "envoy"),
    ("formula", "herb", "contains"),
    ("herb", "efficacy", "efficacy"),
    ("herb", "efficacy", "has_efficacy"),
    ("formula", "efficacy", "efficacy"),
    ("formula", "efficacy", "has_efficacy"),
    ("formula", "syndrome", "treats"),
    ("formula", "symptom", "treats"),
    ("formula", "disease", "treats"),
    ("herb", "syndrome", "treats"),
    ("herb", "symptom", "treats"),
    ("herb", "disease", "treats"),
}


@dataclass(frozen=True)
class RuleRelationQualityScore:
    contract_version: str
    tier: str
    score: float
    cooccurrence_distance: Optional[int]
    trigger_word_type: str
    entity_type_compatibility: str
    cross_sentence: bool
    source_section: str
    has_text_evidence: bool
    evidence_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def tier_rule_edges(
    edges: Iterable[Mapping[str, Any]],
    entities: Iterable[Mapping[str, Any]],
    raw_text: str = "",
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    entity_lookup = _build_entity_lookup(entities)
    scored_edges: list[dict[str, Any]] = []
    tier_counts: Counter[str] = Counter()
    for edge in edges or []:
        item = dict(edge)
        attrs = dict(item.get("attributes") or {})
        source_name = _plain_name(item.get("source") or item.get("from"))
        target_name = _plain_name(item.get("target") or item.get("to"))
        relation_type = str(
            item.get("relation")
            or item.get("rel_type")
            or attrs.get("relationship_type")
            or item.get("label")
            or "related"
        ).strip()
        source_entity = entity_lookup.get(source_name, {})
        target_entity = entity_lookup.get(target_name, {})
        confidence_value = attrs.get("confidence")
        if confidence_value is None:
            confidence_value = item.get("confidence")
        if confidence_value is None:
            confidence_value = 0.5
        score = score_rule_relation(
            source_name=source_name,
            target_name=target_name,
            relation_type=relation_type,
            source_entity=source_entity,
            target_entity=target_entity,
            confidence=float(confidence_value),
            raw_text=raw_text,
        )
        attrs["rule_quality"] = score.to_dict()
        attrs.setdefault("source_method", "rule_extractor")
        attrs.setdefault("relationship_type", relation_type)
        attrs.setdefault(
            "confidence",
            min(float(confidence_value), 0.72 if score.tier == "weak_rule" else 1.0),
        )
        item["attributes"] = attrs
        item["rule_quality"] = score.to_dict()
        item.setdefault("relation", relation_type)
        item.setdefault("source_method", "rule_extractor")
        tier_counts[score.tier] += 1
        scored_edges.append(item)
    return scored_edges, _complete_tier_counts(tier_counts)


def score_rule_relation(
    *,
    source_name: str,
    target_name: str,
    relation_type: str,
    source_entity: Mapping[str, Any],
    target_entity: Mapping[str, Any],
    confidence: float,
    raw_text: str,
) -> RuleRelationQualityScore:
    source_pos = _entity_position(source_entity, source_name, raw_text)
    target_pos = _entity_position(target_entity, target_name, raw_text)
    cooccurrence_distance: Optional[int] = None
    if source_pos is not None and target_pos is not None:
        cooccurrence_distance = abs(source_pos - target_pos)

    has_text_evidence = source_pos is not None or target_pos is not None
    cross_sentence = _cross_sentence(source_pos, target_pos, raw_text)
    source_section = _source_section(source_pos, raw_text)
    trigger_word_type = _trigger_word_type(
        relation_type, source_pos, target_pos, raw_text
    )
    compatibility = _entity_type_compatibility(
        str(source_entity.get("type") or source_entity.get("entity_type") or "generic"),
        str(target_entity.get("type") or target_entity.get("entity_type") or "generic"),
        relation_type,
    )

    distance_score = _distance_score(cooccurrence_distance)
    trigger_score = _trigger_score(trigger_word_type)
    compatibility_score = _compatibility_score(compatibility)
    section_adjustment = (
        0.03
        if source_section == "body"
        else (-0.04 if source_section == "comment" else 0.0)
    )
    sentence_penalty = 0.08 if cross_sentence else 0.0
    raw_score = (
        _clamp(confidence) * 0.34
        + distance_score * 0.22
        + trigger_score * 0.18
        + compatibility_score * 0.22
        + section_adjustment
        - sentence_penalty
    )
    if not has_text_evidence:
        raw_score = min(raw_score, 0.49)
    final_score = round(max(0.0, min(1.0, raw_score)), 4)
    tier = _tier_for_score(final_score, has_text_evidence, compatibility)
    reason = _evidence_reason(has_text_evidence, compatibility, trigger_word_type)
    return RuleRelationQualityScore(
        contract_version=RULE_RELATION_QUALITY_VERSION,
        tier=tier,
        score=final_score,
        cooccurrence_distance=cooccurrence_distance,
        trigger_word_type=trigger_word_type,
        entity_type_compatibility=compatibility,
        cross_sentence=cross_sentence,
        source_section=source_section,
        has_text_evidence=has_text_evidence,
        evidence_reason=reason,
    )


def is_promotable_rule_edge(edge: Mapping[str, Any]) -> bool:
    quality = _quality_payload(edge)
    if not quality:
        return True
    return str(quality.get("tier") or "").strip() in PROMOTABLE_RULE_TIERS and bool(
        quality.get("has_text_evidence")
    )


def rule_quality_tier_counts(edges: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for edge in edges or []:
        quality = _quality_payload(edge)
        if quality:
            counts[str(quality.get("tier") or "candidate_rule")] += 1
    return _complete_tier_counts(counts)


def _quality_payload(edge: Mapping[str, Any]) -> dict[str, Any]:
    direct = edge.get("rule_quality")
    if isinstance(direct, Mapping):
        return dict(direct)
    attrs = (
        edge.get("attributes") if isinstance(edge.get("attributes"), Mapping) else {}
    )
    nested = attrs.get("rule_quality")
    return dict(nested) if isinstance(nested, Mapping) else {}


def _build_entity_lookup(
    entities: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entity in entities or []:
        if not isinstance(entity, Mapping):
            continue
        name = str(
            entity.get("name") or entity.get("text") or entity.get("value") or ""
        ).strip()
        if name:
            lookup[name] = dict(entity)
    return lookup


def _entity_position(
    entity: Mapping[str, Any], name: str, raw_text: str
) -> Optional[int]:
    for key in ("position", "char_start", "start"):
        value = entity.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                pass
    if name and raw_text:
        pos = raw_text.find(name)
        if pos >= 0:
            return pos
    return None


def _cross_sentence(left: Optional[int], right: Optional[int], raw_text: str) -> bool:
    if left is None or right is None or not raw_text:
        return False
    return _sentence_index(left, raw_text) != _sentence_index(right, raw_text)


def _sentence_index(position: int, raw_text: str) -> int:
    return len(_SENTENCE_SPLIT_RE.findall(raw_text[: max(0, position)]))


def _source_section(position: Optional[int], raw_text: str) -> str:
    if position is None or not raw_text:
        return "unknown"
    line_start = raw_text.rfind("\n", 0, position) + 1
    line_end = raw_text.find("\n", position)
    line = raw_text[line_start : line_end if line_end >= 0 else len(raw_text)].strip()
    first_non_empty = next(
        (value.strip() for value in raw_text.splitlines() if value.strip()), ""
    )
    if line and line == first_non_empty and (len(line) <= 40 or line.startswith("《")):
        return "title"
    if (
        line.startswith(("注", "按", "案", "注文", "校注"))
        or "注:" in line
        or "注：" in line
    ):
        return "comment"
    return "body"


def _trigger_word_type(
    relation_type: str, left: Optional[int], right: Optional[int], raw_text: str
) -> str:
    normalized = str(relation_type or "").strip().lower()
    if normalized in {"sovereign", "minister", "assistant", "envoy", "contains"}:
        fallback = "structured_formula_composition"
    elif normalized in {"efficacy", "has_efficacy"}:
        fallback = "structured_herb_efficacy"
    elif normalized == "treats":
        fallback = "textual_treatment_trigger"
    else:
        fallback = "generic_rule"
    if left is None or right is None or not raw_text:
        return fallback
    start, end = sorted((left, right))
    window = raw_text[max(0, start - 20) : min(len(raw_text), end + 20)]
    for trigger_type, keywords in _TRIGGER_KEYWORDS.items():
        if any(keyword in window for keyword in keywords):
            return trigger_type
    return fallback


def _entity_type_compatibility(
    source_type: str, target_type: str, relation_type: str
) -> str:
    normalized = (source_type.lower(), target_type.lower(), relation_type.lower())
    if normalized in _COMPATIBLE_PAIRS:
        return "compatible"
    relation = normalized[2]
    if relation in {"related", "combines_with"}:
        return "weak"
    if "generic" in normalized[:2] or "unknown" in normalized[:2]:
        return "weak"
    return "incompatible"


def _distance_score(distance: Optional[int]) -> float:
    if distance is None:
        return 0.2
    if distance <= 80:
        return 1.0
    if distance <= 300:
        return 0.82
    if distance <= 800:
        return 0.58
    return 0.32


def _trigger_score(trigger_word_type: str) -> float:
    if trigger_word_type.startswith("structured_"):
        return 0.78
    if trigger_word_type in {
        "composition",
        "treats",
        "efficacy",
        "property",
        "textual_treatment_trigger",
    }:
        return 0.82
    if trigger_word_type == "generic_rule":
        return 0.45
    return 0.58


def _compatibility_score(value: str) -> float:
    if value == "compatible":
        return 1.0
    if value == "weak":
        return 0.55
    return 0.1


def _tier_for_score(score: float, has_text_evidence: bool, compatibility: str) -> str:
    if not has_text_evidence or compatibility == "incompatible":
        return "candidate_rule" if score >= 0.35 else "rejected_rule"
    if score >= 0.78:
        return "strong_rule"
    if score >= 0.6:
        return "weak_rule"
    if score >= 0.35:
        return "candidate_rule"
    return "rejected_rule"


def _evidence_reason(
    has_text_evidence: bool, compatibility: str, trigger_word_type: str
) -> str:
    if not has_text_evidence:
        return "missing_text_segment"
    if compatibility == "incompatible":
        return "entity_type_incompatible"
    return trigger_word_type


def _plain_name(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if ":" in text else text


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))


def _complete_tier_counts(counts: Counter[str]) -> dict[str, int]:
    return {
        "strong_rule": int(counts.get("strong_rule", 0)),
        "weak_rule": int(counts.get("weak_rule", 0)),
        "candidate_rule": int(counts.get("candidate_rule", 0)),
        "rejected_rule": int(counts.get("rejected_rule", 0)),
    }


__all__ = [
    "CANDIDATE_RULE_TIERS",
    "PROMOTABLE_RULE_TIERS",
    "RULE_RELATION_QUALITY_VERSION",
    "RuleRelationQualityScore",
    "is_promotable_rule_edge",
    "rule_quality_tier_counts",
    "score_rule_relation",
    "tier_rule_edges",
]
