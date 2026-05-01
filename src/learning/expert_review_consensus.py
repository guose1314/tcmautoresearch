from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

EXPERT_REVIEW_CONSENSUS_CONTRACT_VERSION = "expert-review-consensus-v1"
EXPERT_SIGNAL_CONSENSUS = "expert_consensus"
EXPERT_SIGNAL_DISPUTE = "expert_dispute"
EXPERT_SIGNAL_SINGLE = "single_expert_review"

_ALLOWED_GRADES = {"A", "B", "C", "D"}
_GRADE_STRENGTH = {"A": 4, "B": 3, "C": 2, "D": 1}
_DEFAULT_HIGH_CONFIDENCE_THRESHOLD = 0.75
_DEFAULT_AGREEMENT_THRESHOLD = 0.8


def normalize_review_confidence(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence > 1.0 and confidence <= 100.0:
        confidence = confidence / 100.0
    return round(max(0.0, min(1.0, confidence)), 4)


def normalize_dispute_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "dispute", "disputed"}


def normalize_review_grade(value: Any) -> str:
    grade = str(value or "").strip().upper()
    return grade if grade in _ALLOWED_GRADES else ""


def resolve_expert_review_group_key(record: Mapping[str, Any]) -> str:
    cycle_id = _extract_text(record, "cycle_id") or "unknown_cycle"
    target_id = (
        _extract_text(record, "consensus_group_id")
        or _extract_text(record, "claim_id")
        or _extract_text(record, "hypothesis_id")
        or _extract_text(record, "expert_review_id")
        or _extract_text(record, "id")
        or "unknown_review"
    )
    return f"{cycle_id}::{target_id}"


def aggregate_expert_review_consensus(
    records: Sequence[Mapping[str, Any]],
    *,
    high_confidence_threshold: float = _DEFAULT_HIGH_CONFIDENCE_THRESHOLD,
    agreement_threshold: float = _DEFAULT_AGREEMENT_THRESHOLD,
) -> Dict[str, Any]:
    normalized_records = [record for record in records if isinstance(record, Mapping)]
    review_count = len(normalized_records)
    grades = [
        grade
        for grade in (
            normalize_review_grade(_extract_text(record, "expert_grade", "grade_level"))
            for record in normalized_records
        )
        if grade
    ]
    grade_counts = Counter(grades)
    majority_grade = _resolve_majority_grade(grade_counts)
    majority_count = grade_counts.get(majority_grade, 0) if majority_grade else 0
    agreement_rate = majority_count / review_count if review_count else 0.0
    confidence_values = [
        confidence
        for confidence in (
            normalize_review_confidence(_extract_value(record, "confidence"))
            for record in normalized_records
        )
        if confidence is not None
    ]
    average_confidence = (
        round(sum(confidence_values) / len(confidence_values), 4)
        if confidence_values
        else 0.0
    )
    has_dispute = (
        any(
            normalize_dispute_flag(_extract_value(record, "dispute_flag"))
            for record in normalized_records
        )
        or len(grade_counts) > 1
    )
    high_weight_feedback = bool(
        review_count >= 2
        and agreement_rate >= float(agreement_threshold)
        and average_confidence >= float(high_confidence_threshold)
        and not has_dispute
    )
    first_record = normalized_records[0] if normalized_records else {}
    reviewer_ids = sorted(
        {
            reviewer_id
            for reviewer_id in (
                _extract_text(record, "reviewer_id") for record in normalized_records
            )
            if reviewer_id
        }
    )
    return {
        "contract_version": EXPERT_REVIEW_CONSENSUS_CONTRACT_VERSION,
        "consensus_group_id": _extract_text(first_record, "consensus_group_id"),
        "group_key": resolve_expert_review_group_key(first_record)
        if normalized_records
        else "",
        "cycle_id": _extract_text(first_record, "cycle_id"),
        "claim_id": _extract_text(first_record, "claim_id"),
        "hypothesis_id": _extract_text(first_record, "hypothesis_id"),
        "review_count": review_count,
        "reviewer_count": len(reviewer_ids),
        "reviewer_ids": reviewer_ids,
        "agreement_rate": round(agreement_rate, 4),
        "majority_grade": majority_grade,
        "grade_distribution": dict(sorted(grade_counts.items())),
        "average_confidence": average_confidence,
        "confidence_count": len(confidence_values),
        "has_dispute": has_dispute,
        "high_weight_feedback": high_weight_feedback,
    }


def build_expert_review_consensus_index(
    records: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in records or []:
        if isinstance(record, Mapping):
            grouped[resolve_expert_review_group_key(record)].append(record)
    return {
        group_key: aggregate_expert_review_consensus(group_records)
        for group_key, group_records in grouped.items()
    }


def classify_expert_review_signal(
    record: Mapping[str, Any],
    consensus: Optional[Mapping[str, Any]] = None,
) -> str:
    if normalize_dispute_flag(_extract_value(record, "dispute_flag")):
        return EXPERT_SIGNAL_DISPUTE
    if isinstance(consensus, Mapping):
        if consensus.get("has_dispute"):
            return EXPERT_SIGNAL_DISPUTE
        if consensus.get("high_weight_feedback"):
            return EXPERT_SIGNAL_CONSENSUS
    return EXPERT_SIGNAL_SINGLE


def _resolve_majority_grade(grade_counts: Counter[str]) -> str:
    if not grade_counts:
        return ""
    highest_count = max(grade_counts.values())
    candidates = [
        grade for grade, count in grade_counts.items() if count == highest_count
    ]
    return sorted(candidates, key=lambda grade: _GRADE_STRENGTH.get(grade, 0))[0]


def _extract_mapping(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def _extract_value(record: Mapping[str, Any], *keys: str) -> Any:
    metadata = _extract_mapping(record, "metadata")
    details = _extract_mapping(record, "details")
    for key in keys:
        if record.get(key) not in (None, ""):
            return record.get(key)
        if metadata.get(key) not in (None, ""):
            return metadata.get(key)
        if details.get(key) not in (None, ""):
            return details.get(key)
    return None


def _extract_text(record: Mapping[str, Any], *keys: str) -> str:
    value = _extract_value(record, *keys)
    return str(value or "").strip()


__all__ = [
    "EXPERT_REVIEW_CONSENSUS_CONTRACT_VERSION",
    "EXPERT_SIGNAL_CONSENSUS",
    "EXPERT_SIGNAL_DISPUTE",
    "EXPERT_SIGNAL_SINGLE",
    "aggregate_expert_review_consensus",
    "build_expert_review_consensus_index",
    "classify_expert_review_signal",
    "normalize_dispute_flag",
    "normalize_review_confidence",
    "normalize_review_grade",
    "resolve_expert_review_group_key",
]
