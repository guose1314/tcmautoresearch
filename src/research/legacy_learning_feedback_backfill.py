from __future__ import annotations

import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.research.learning_feedback_contract import (
    CONTRACT_VERSION,
    build_learning_feedback_library,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEGACY_LEARNING_DATA_FILE = WORKSPACE_ROOT / "data" / "learning_data.pkl"

_CYCLE_ID_SANITIZER = re.compile(r"[^0-9A-Za-z]+")
_WEAK_PHASE_THRESHOLD = 0.6
_STRONG_PHASE_THRESHOLD = 0.8
_GRADE_THRESHOLDS = (
    (0.8, "high"),
    (0.6, "moderate"),
    (0.4, "low"),
)


def resolve_legacy_learning_data_path(
    file_path: str | Path | None = None,
    *,
    base_path: Path | None = None,
) -> Path:
    candidate = Path(file_path).expanduser() if file_path else DEFAULT_LEGACY_LEARNING_DATA_FILE
    if not candidate.is_absolute():
        candidate = (base_path or WORKSPACE_ROOT) / candidate
    return candidate.resolve()


def derive_legacy_learning_cycle_id(file_path: str | Path | None = None) -> str:
    resolved_path = resolve_legacy_learning_data_path(file_path)
    normalized_stem = _CYCLE_ID_SANITIZER.sub("-", resolved_path.stem).strip("-").lower()
    if not normalized_stem:
        normalized_stem = "learning-data"
    return f"legacy-{normalized_stem}"


def load_legacy_learning_data(
    file_path: str | Path | None = None,
    *,
    base_path: Path | None = None,
) -> Dict[str, Any]:
    resolved_path = resolve_legacy_learning_data_path(file_path, base_path=base_path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"未找到 legacy learning data 文件: {resolved_path}")

    with resolved_path.open("rb") as handle:
        payload = pickle.load(handle)

    if not isinstance(payload, Mapping):
        raise ValueError("legacy learning data 必须是 dict-like payload")
    return dict(payload)


def build_legacy_learning_feedback_library(
    payload: Mapping[str, Any],
    *,
    source_file: str | Path,
) -> Dict[str, Any]:
    imported_at = _normalize_timestamp(None)
    raw_records = _normalize_records(payload.get("records"))
    performance_history = _normalize_float_list(payload.get("performance_history"))
    model_improvement_log = _normalize_mapping_list(payload.get("model_improvement_log"))
    tuned_parameters = _normalize_mapping(payload.get("tuned_parameters"))
    dimension_trends = _normalize_dimension_trends(payload.get("dimension_trends"))
    ewma_score = _to_float(payload.get("ewma_score"))

    phase_summaries = _build_phase_summaries(raw_records)
    cycle_scores = [
        score
        for score in (
            _to_float(entry.get("overall_score"))
            for entry in model_improvement_log
            if str(entry.get("type") or "").strip().lower() == "cycle_reflection"
        )
        if score is not None
    ]
    overall_score = _resolve_overall_score(raw_records, performance_history, cycle_scores, ewma_score)
    cycle_trend = _compute_cycle_trend(cycle_scores or performance_history)

    weaknesses = []
    strengths = []
    phase_assessments = []
    recorded_phase_names = [summary["phase"] for summary in phase_summaries]

    for summary in phase_summaries:
        phase_name = summary["phase"]
        avg_score = summary["avg_score"]
        latest_score = summary["latest_score"]
        avg_dimensions = dict(summary["avg_dimensions"])
        issues = []
        if avg_score < _WEAK_PHASE_THRESHOLD:
            issues.append(f"历史平均分 {avg_score:.2f} 低于 {_WEAK_PHASE_THRESHOLD:.2f} 基线")
            weaknesses.append(
                {
                    "phase": phase_name,
                    "score": avg_score,
                    "issues": issues,
                }
            )
        elif avg_score >= _STRONG_PHASE_THRESHOLD:
            strengths.append(
                {
                    "phase": phase_name,
                    "score": avg_score,
                    "highlights": [f"历史平均分 {avg_score:.2f} 达到稳定高质量区间"],
                }
            )

        phase_assessments.append(
            {
                "phase": phase_name,
                "score": {
                    "overall_score": avg_score,
                    "grade_level": _score_to_grade(avg_score),
                    "completeness": avg_dimensions.get("completeness", 0.0),
                    "consistency": avg_dimensions.get("consistency", 0.0),
                    "evidence_quality": avg_dimensions.get("evidence_quality", 0.0),
                },
                "details": {
                    "latest_score": latest_score,
                    "latest_recorded_at": summary["latest_recorded_at"],
                    "record_count": summary["record_count"],
                },
            }
        )

    improvement_priorities = _derive_improvement_priorities(weaknesses, overall_score)
    learning_summary = {
        "recorded_phases": recorded_phase_names,
        "weak_phase_count": len(weaknesses),
        "weak_phases": [dict(item) for item in weaknesses],
        "improvement_priorities": list(improvement_priorities),
        "cycle_trend": cycle_trend,
        "tuned_parameters": tuned_parameters,
    }
    replay_feedback = {
        "status": "completed",
        "iteration_number": len(cycle_scores) or (1 if raw_records or performance_history or model_improvement_log else 0),
        "learning_summary": dict(learning_summary),
    }
    if overall_score is not None:
        replay_feedback["cycle_quality_score"] = overall_score
        replay_feedback["quality_assessment"] = {"overall_cycle_score": overall_score}

    library = build_learning_feedback_library(
        cycle_assessment={
            "overall_cycle_score": overall_score or 0.0,
            "phase_assessments": phase_assessments,
            "weaknesses": weaknesses,
            "strengths": strengths,
            "llm_diagnosis": None,
        },
        learning_summary=learning_summary,
        strategy_diff={"changed": False},
        reflections=[
            {
                "source": "legacy_learning_data_pickle",
                "message": "legacy learning_data.pkl 已聚合导入 canonical learning_feedback_library",
                "imported_at": imported_at,
            }
        ],
        improvement_plan=improvement_priorities,
        learning_application_summary={
            "source": "legacy_learning_data_pickle",
            "source_file": str(Path(source_file)),
            "imported_at": imported_at,
            "legacy_record_count": len(raw_records),
            "legacy_phase_record_count": len([record for record in raw_records if record.get("phase")]),
            "legacy_unscoped_record_count": len([record for record in raw_records if not record.get("phase")]),
            "legacy_performance_point_count": len(performance_history),
            "legacy_improvement_log_count": len(model_improvement_log),
        },
        replay_feedback=replay_feedback,
    )

    base_metadata = {
        "contract_version": CONTRACT_VERSION,
        "source": "legacy_learning_data_pickle",
        "source_file": str(Path(source_file)),
        "imported_at": imported_at,
    }
    cycle_record = None
    for record in library.get("records") or []:
        if not isinstance(record, dict):
            continue
        metadata = dict(record.get("metadata") or {})
        metadata.update(base_metadata)
        record["metadata"] = metadata
        if str(record.get("feedback_scope") or "") == "cycle_summary":
            cycle_record = record

    if isinstance(cycle_record, dict):
        details = dict(cycle_record.get("details") or {})
        details["legacy_stats"] = {
            "record_count": len(raw_records),
            "phase_record_count": len([record for record in raw_records if record.get("phase")]),
            "feedback_event_count": len(
                [
                    entry for entry in model_improvement_log
                    if str(entry.get("feedback_score") or "") not in ("", "None")
                ]
            ),
            "cycle_reflection_count": len(cycle_scores),
            "dimension_trends": dimension_trends,
            "ewma_score": ewma_score,
            "recent_performance": performance_history[-10:],
        }
        details["quality_assessment"] = {
            **dict(details.get("quality_assessment") or {}),
            "overall_cycle_score": overall_score,
            "grade_level": _score_to_grade(overall_score or 0.0),
        }
        cycle_record["details"] = details

    return library


def backfill_legacy_learning_feedback(
    repository: ResearchSessionRepository,
    *,
    file_path: str | Path | None = None,
    cycle_id: str | None = None,
    cycle_name: str | None = None,
    overwrite_existing: bool = False,
) -> Dict[str, Any]:
    resolved_path = resolve_legacy_learning_data_path(file_path)
    payload = load_legacy_learning_data(resolved_path)
    resolved_cycle_id = str(cycle_id or derive_legacy_learning_cycle_id(resolved_path)).strip()
    if not resolved_cycle_id:
        raise ValueError("cycle_id 不能为空")

    existing_session = repository.get_session(resolved_cycle_id)
    existing_library = repository.get_learning_feedback_library(resolved_cycle_id) if existing_session else None
    existing_record_count = int(
        ((existing_library or {}).get("summary") or {}).get("record_count") or 0
    )
    if existing_record_count and not overwrite_existing:
        raise ValueError("目标 cycle 已存在 learning feedback 记录；如需覆盖请显式指定 overwrite_existing=True")

    imported_at = _normalize_timestamp(None)
    session_metadata = dict((existing_session or {}).get("metadata") or {})
    session_metadata["legacy_learning_feedback_backfill"] = {
        "source_file": str(resolved_path),
        "imported_at": imported_at,
        "contract_version": CONTRACT_VERSION,
    }

    created_session = False
    if existing_session is None:
        repository.create_session(
            {
                "cycle_id": resolved_cycle_id,
                "cycle_name": str(cycle_name or f"Legacy Learning Import {resolved_path.stem}"),
                "description": f"Imported from legacy learning data file {resolved_path.name}",
                "research_objective": "将历史自学习资产并入 canonical learning feedback 查询面",
                "status": "completed",
                "current_phase": "reflect",
                "metadata": session_metadata,
            }
        )
        created_session = True
    else:
        updates: Dict[str, Any] = {"metadata": session_metadata}
        if cycle_name:
            updates["cycle_name"] = str(cycle_name)
        repository.update_session(resolved_cycle_id, updates)

    library = build_legacy_learning_feedback_library(payload, source_file=resolved_path)
    saved_library = repository.replace_learning_feedback_library(resolved_cycle_id, library)
    if saved_library is None:
        raise RuntimeError(f"写入 learning feedback 失败: {resolved_cycle_id}")

    return {
        "cycle_id": resolved_cycle_id,
        "cycle_name": str((repository.get_session(resolved_cycle_id) or {}).get("cycle_name") or ""),
        "source_file": str(resolved_path),
        "created_session": created_session,
        "overwrote_existing_records": bool(existing_record_count and overwrite_existing),
        "legacy_record_count": len(_normalize_records(payload.get("records"))),
        "legacy_performance_point_count": len(_normalize_float_list(payload.get("performance_history"))),
        "legacy_improvement_log_count": len(_normalize_mapping_list(payload.get("model_improvement_log"))),
        "imported_record_count": int(((saved_library.get("summary") or {}).get("record_count") or 0)),
        "fields_written": ["research_sessions.metadata", "research_learning_feedback"],
        "library": saved_library,
    }


def _normalize_records(value: Any) -> List[Dict[str, Any]]:
    items = _normalize_mapping_list(value)
    indexed_items = list(enumerate(items))
    indexed_items.sort(key=lambda pair: _record_sort_key(pair[0], pair[1]))
    return [item for _, item in indexed_items]


def _record_sort_key(index: int, item: Mapping[str, Any]) -> tuple[int, str, int]:
    timestamp = str(item.get("timestamp") or "").strip()
    return (1 if not timestamp else 0, timestamp, index)


def _normalize_mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _normalize_mapping_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _normalize_float_list(value: Any) -> List[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: List[float] = []
    for item in value:
        number = _to_float(item)
        if number is not None:
            result.append(number)
    return result


def _normalize_dimension_trends(value: Any) -> Dict[str, List[float]]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, List[float]] = {}
    for key, item in value.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        values = _normalize_float_list(item)
        if values:
            result[normalized_key] = values
    return result


def _build_phase_summaries(raw_records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for record in raw_records:
        phase = str(record.get("phase") or "").strip().lower()
        score = _to_float(record.get("performance"))
        if not phase or score is None:
            continue
        if phase not in grouped:
            grouped[phase] = []
            order.append(phase)
        grouped[phase].append(
            {
                "performance": score,
                "timestamp": _normalize_timestamp(record.get("timestamp")),
                "quality_dimensions": _normalize_mapping(record.get("quality_dimensions")),
            }
        )

    summaries: List[Dict[str, Any]] = []
    for phase in order:
        phase_records = grouped.get(phase) or []
        scores = [record["performance"] for record in phase_records]
        latest = phase_records[-1]
        dimension_buckets: Dict[str, List[float]] = {}
        for record in phase_records:
            for name, raw_value in dict(record.get("quality_dimensions") or {}).items():
                value = _to_float(raw_value)
                if value is None:
                    continue
                normalized_name = str(name or "").strip()
                if not normalized_name:
                    continue
                dimension_buckets.setdefault(normalized_name, []).append(value)
        summaries.append(
            {
                "phase": phase,
                "record_count": len(phase_records),
                "avg_score": round(sum(scores) / len(scores), 4),
                "latest_score": round(latest["performance"], 4),
                "latest_recorded_at": latest.get("timestamp"),
                "avg_dimensions": {
                    name: round(sum(values) / len(values), 4)
                    for name, values in dimension_buckets.items()
                    if values
                },
            }
        )
    return summaries


def _resolve_overall_score(
    raw_records: Sequence[Mapping[str, Any]],
    performance_history: Sequence[float],
    cycle_scores: Sequence[float],
    ewma_score: float | None,
) -> float:
    for candidate in (
        cycle_scores[-1] if cycle_scores else None,
        ewma_score,
        performance_history[-1] if performance_history else None,
        _to_float(raw_records[-1].get("performance")) if raw_records else None,
    ):
        if candidate is not None:
            return round(candidate, 4)
    return 0.0


def _compute_cycle_trend(scores: Sequence[float]) -> str:
    normalized_scores = [score for score in scores if score is not None]
    if len(normalized_scores) < 2:
        return "insufficient_data"
    recent_scores = normalized_scores[-6:]
    split_index = len(recent_scores) // 2
    first_half = recent_scores[:split_index]
    second_half = recent_scores[split_index:]
    if not first_half or not second_half:
        return "insufficient_data"
    diff = (sum(second_half) / len(second_half)) - (sum(first_half) / len(first_half))
    if diff > 0.05:
        return "improving"
    if diff < -0.05:
        return "declining"
    return "stable"


def _derive_improvement_priorities(weaknesses: Sequence[Mapping[str, Any]], overall_score: float) -> List[str]:
    priorities: List[str] = []
    ordered = sorted(
        weaknesses,
        key=lambda item: _to_float(item.get("score")) if _to_float(item.get("score")) is not None else 1.0,
    )
    for weakness in ordered:
        phase = str(weakness.get("phase") or "unknown").strip() or "unknown"
        score = _to_float(weakness.get("score")) or 0.0
        if score < 0.4:
            priorities.append(f"紧急: 重构{phase}阶段输出规范 (评分 {score:.2f})")
        elif score < 0.6:
            priorities.append(f"优先: 提升{phase}阶段数据完整性 (评分 {score:.2f})")
        else:
            priorities.append(f"建议: 优化{phase}阶段细节 (评分 {score:.2f})")
    if overall_score < 0.6 and not priorities:
        priorities.append("整体评分偏低，建议全局质量基线提升")
    return priorities


def _score_to_grade(score: float) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "very_low"


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return datetime.utcnow().replace(microsecond=0).isoformat()


__all__ = [
    "DEFAULT_LEGACY_LEARNING_DATA_FILE",
    "backfill_legacy_learning_feedback",
    "build_legacy_learning_feedback_library",
    "derive_legacy_learning_cycle_id",
    "load_legacy_learning_data",
    "resolve_legacy_learning_data_path",
]