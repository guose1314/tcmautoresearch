from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

CONTRACT_VERSION = "research-feedback-library.v1"


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    normalized: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _to_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_score_payload(score: Any) -> Dict[str, Any]:
    if hasattr(score, "overall_score"):
        return {
            "overall_score": _to_optional_float(getattr(score, "overall_score", None)),
            "grade_level": str(getattr(score, "grade_level", "") or "").strip() or None,
            "quality_dimensions": {
                "completeness": float(getattr(score, "completeness", 0.0) or 0.0),
                "consistency": float(getattr(score, "consistency", 0.0) or 0.0),
                "evidence_quality": float(getattr(score, "evidence_quality", 0.0) or 0.0),
            },
        }
    if isinstance(score, Mapping):
        return {
            "overall_score": _to_optional_float(score.get("overall_score")),
            "grade_level": str(score.get("grade_level") or "").strip() or None,
            "quality_dimensions": {
                "completeness": float(score.get("completeness", 0.0) or 0.0),
                "consistency": float(score.get("consistency", 0.0) or 0.0),
                "evidence_quality": float(score.get("evidence_quality", 0.0) or 0.0),
            },
        }
    return {
        "overall_score": _to_optional_float(score),
        "grade_level": None,
        "quality_dimensions": {},
    }


def build_learning_replay_feedback(
    learning_summary: Optional[Mapping[str, Any]],
    quality_assessment: Optional[Mapping[str, Any]],
    replay_feedback: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if isinstance(replay_feedback, Mapping) and replay_feedback:
        return dict(replay_feedback)

    normalized_learning_summary = dict(learning_summary or {})
    normalized_quality_assessment = dict(quality_assessment or {})
    if not normalized_learning_summary and not normalized_quality_assessment:
        return {}

    feedback: Dict[str, Any] = {
        "status": "completed",
        "learning_summary": normalized_learning_summary,
    }
    overall_cycle_score = _to_optional_float(normalized_quality_assessment.get("overall_cycle_score"))
    if overall_cycle_score is not None:
        feedback["cycle_quality_score"] = overall_cycle_score
        feedback["quality_assessment"] = {"overall_cycle_score": overall_cycle_score}
    return feedback


def normalize_learning_feedback_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    details = record.get("details")
    metadata = record.get("metadata")
    quality_dimensions = record.get("quality_dimensions")

    normalized_details = dict(details or {}) if isinstance(details, Mapping) else {}
    normalized_metadata = dict(metadata or {}) if isinstance(metadata, Mapping) else {}
    normalized_quality_dimensions = (
        dict(quality_dimensions or {}) if isinstance(quality_dimensions, Mapping) else {}
    )

    return {
        "feedback_scope": str(record.get("feedback_scope") or "phase_assessment").strip().lower() or "phase_assessment",
        "source_phase": str(record.get("source_phase") or "reflect").strip().lower() or "reflect",
        "target_phase": str(record.get("target_phase") or "").strip().lower() or None,
        "feedback_status": str(record.get("feedback_status") or "tracked").strip().lower() or "tracked",
        "overall_score": _to_optional_float(record.get("overall_score")),
        "grade_level": str(record.get("grade_level") or "").strip() or None,
        "cycle_trend": str(record.get("cycle_trend") or "").strip().lower() or None,
        "issue_count": max(int(record.get("issue_count") or 0), 0),
        "weakness_count": max(int(record.get("weakness_count") or 0), 0),
        "strength_count": max(int(record.get("strength_count") or 0), 0),
        "strategy_changed": bool(record.get("strategy_changed")),
        "strategy_before_fingerprint": str(record.get("strategy_before_fingerprint") or "").strip() or None,
        "strategy_after_fingerprint": str(record.get("strategy_after_fingerprint") or "").strip() or None,
        "recorded_phase_names": _normalize_string_list(record.get("recorded_phase_names") or []),
        "weak_phase_names": _normalize_string_list(record.get("weak_phase_names") or []),
        "quality_dimensions": normalized_quality_dimensions,
        "issues": _normalize_string_list(record.get("issues") or []),
        "improvement_priorities": _normalize_string_list(record.get("improvement_priorities") or []),
        "replay_feedback": (
            dict(record.get("replay_feedback") or {})
            if isinstance(record.get("replay_feedback"), Mapping)
            else {}
        ),
        "details": normalized_details,
        "metadata": normalized_metadata,
    }


def build_learning_feedback_library(
    *,
    cycle_assessment: Mapping[str, Any],
    learning_summary: Optional[Mapping[str, Any]] = None,
    strategy_diff: Optional[Mapping[str, Any]] = None,
    reflections: Optional[Sequence[Mapping[str, Any]]] = None,
    improvement_plan: Optional[Sequence[str]] = None,
    learning_application_summary: Optional[Mapping[str, Any]] = None,
    replay_feedback: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_learning_summary = dict(learning_summary or {})
    normalized_strategy_diff = dict(strategy_diff or {})
    normalized_learning_application_summary = dict(learning_application_summary or {})
    normalized_reflections = [
        dict(item)
        for item in (reflections or [])
        if isinstance(item, Mapping)
    ]
    normalized_improvement_plan = _normalize_string_list(improvement_plan or [])
    phase_assessments = [
        item
        for item in (cycle_assessment.get("phase_assessments") or [])
        if isinstance(item, Mapping)
    ]
    weaknesses = [
        item
        for item in (cycle_assessment.get("weaknesses") or [])
        if isinstance(item, Mapping)
    ]
    strengths = [
        item
        for item in (cycle_assessment.get("strengths") or [])
        if isinstance(item, Mapping)
    ]

    quality_assessment = {
        "overall_cycle_score": float(cycle_assessment.get("overall_cycle_score", 0.0) or 0.0),
        "weaknesses": [dict(item) for item in weaknesses],
        "strengths": [dict(item) for item in strengths],
        "llm_diagnosis": cycle_assessment.get("llm_diagnosis"),
    }

    replay_payload = build_learning_replay_feedback(
        normalized_learning_summary,
        quality_assessment,
        replay_feedback,
    )

    weakness_index = {
        str(item.get("phase") or "").strip().lower(): dict(item)
        for item in weaknesses
        if str(item.get("phase") or "").strip()
    }
    strength_index = {
        str(item.get("phase") or "").strip().lower(): dict(item)
        for item in strengths
        if str(item.get("phase") or "").strip()
    }

    recorded_phase_names = _normalize_string_list(
        normalized_learning_summary.get("recorded_phases")
        or [item.get("phase") for item in phase_assessments]
    )
    raw_weak_phases = normalized_learning_summary.get("weak_phases")
    if isinstance(raw_weak_phases, Sequence) and not isinstance(raw_weak_phases, (str, bytes, bytearray)):
        weak_phase_names = _normalize_string_list(
            [
                item.get("phase") if isinstance(item, Mapping) else item
                for item in raw_weak_phases
            ]
        )
    else:
        weak_phase_names = _normalize_string_list([item.get("phase") for item in weaknesses])
    improvement_priorities = _normalize_string_list(
        normalized_learning_summary.get("improvement_priorities") or normalized_improvement_plan
    )

    cycle_record = normalize_learning_feedback_record(
        {
            "feedback_scope": "cycle_summary",
            "source_phase": "reflect",
            "feedback_status": "summary",
            "overall_score": quality_assessment["overall_cycle_score"],
            "cycle_trend": normalized_learning_summary.get("cycle_trend"),
            "issue_count": sum(len(item.get("issues") or []) for item in weaknesses),
            "weakness_count": len(weaknesses),
            "strength_count": len(strengths),
            "strategy_changed": bool(normalized_strategy_diff.get("changed")),
            "strategy_before_fingerprint": normalized_strategy_diff.get("before_fingerprint"),
            "strategy_after_fingerprint": normalized_strategy_diff.get("after_fingerprint"),
            "recorded_phase_names": recorded_phase_names,
            "weak_phase_names": weak_phase_names,
            "improvement_priorities": improvement_priorities,
            "replay_feedback": replay_payload,
            "details": {
                "reflections": normalized_reflections,
                "improvement_plan": normalized_improvement_plan,
                "learning_summary": normalized_learning_summary,
                "quality_assessment": quality_assessment,
                "strategy_diff": normalized_strategy_diff,
                "tuned_parameters": dict(normalized_learning_summary.get("tuned_parameters") or {}),
                "learning_application_summary": normalized_learning_application_summary,
            },
            "metadata": {"contract_version": CONTRACT_VERSION},
        }
    )

    phase_records: List[Dict[str, Any]] = []
    for assessment in phase_assessments:
        phase_name = str(assessment.get("phase") or "").strip().lower()
        if not phase_name:
            continue
        score_payload = _extract_score_payload(assessment.get("score"))
        weakness_payload = weakness_index.get(phase_name) or {}
        strength_payload = strength_index.get(phase_name) or {}
        feedback_status = "tracked"
        if weakness_payload:
            feedback_status = "weakness"
        elif strength_payload:
            feedback_status = "strength"

        phase_records.append(
            normalize_learning_feedback_record(
                {
                    "feedback_scope": "phase_assessment",
                    "source_phase": "reflect",
                    "target_phase": phase_name,
                    "feedback_status": feedback_status,
                    "overall_score": score_payload.get("overall_score"),
                    "grade_level": score_payload.get("grade_level"),
                    "issue_count": len(weakness_payload.get("issues") or []),
                    "weakness_count": 1 if weakness_payload else 0,
                    "strength_count": 1 if strength_payload else 0,
                    "recorded_phase_names": [phase_name],
                    "weak_phase_names": [phase_name] if weakness_payload else [],
                    "quality_dimensions": score_payload.get("quality_dimensions") or {},
                    "issues": weakness_payload.get("issues") or [],
                    "details": {
                        "weakness": weakness_payload,
                        "strength": strength_payload,
                    },
                    "metadata": {"contract_version": CONTRACT_VERSION},
                }
            )
        )

    records = [cycle_record, *phase_records]
    summary = {
        "record_count": len(records),
        "phase_record_count": len(phase_records),
        "latest_cycle_score": cycle_record.get("overall_score"),
        "cycle_trend": cycle_record.get("cycle_trend"),
        "weak_phase_names": weak_phase_names,
        "recorded_phase_names": recorded_phase_names,
        "strategy_changed": cycle_record.get("strategy_changed", False),
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "summary": summary,
        "replay_feedback": replay_payload,
        "records": records,
    }


__all__ = [
    "CONTRACT_VERSION",
    "build_learning_feedback_library",
    "build_learning_replay_feedback",
    "normalize_learning_feedback_record",
]