from __future__ import annotations

import pickle

import pytest

from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.research.legacy_learning_feedback_backfill import (
    backfill_legacy_learning_feedback,
    build_legacy_learning_feedback_library,
)


@pytest.fixture()
def repo():
    manager = DatabaseManager("sqlite:///:memory:")
    manager.init_db()
    try:
        yield ResearchSessionRepository(manager)
    finally:
        manager.close()


def _make_legacy_learning_payload() -> dict:
    return {
        "records": [
            {
                "task_id": "observe-1",
                "performance": 0.86,
                "timestamp": "2026-04-01T09:00:00",
                "phase": "observe",
                "quality_dimensions": {
                    "completeness": 0.9,
                    "consistency": 0.82,
                    "evidence_quality": 0.85,
                },
            },
            {
                "task_id": "analyze-1",
                "performance": 0.42,
                "timestamp": "2026-04-01T09:10:00",
                "phase": "analyze",
                "quality_dimensions": {
                    "completeness": 0.46,
                    "consistency": 0.4,
                    "evidence_quality": 0.38,
                },
            },
            {
                "task_id": "analyze-2",
                "performance": 0.38,
                "timestamp": "2026-04-01T09:20:00",
                "phase": "analyze",
                "quality_dimensions": {
                    "completeness": 0.42,
                    "consistency": 0.36,
                    "evidence_quality": 0.34,
                },
            },
            {
                "task_id": "raw-1",
                "performance": 0.66,
                "timestamp": "2026-04-01T09:30:00",
            },
        ],
        "performance_history": [0.51, 0.57, 0.64, 0.73],
        "model_improvement_log": [
            {
                "type": "cycle_reflection",
                "overall_score": 0.52,
                "recorded_phases": ["observe", "analyze"],
                "weak_phase_count": 1,
                "timestamp": "2026-04-01T09:15:00",
            },
            {
                "type": "cycle_reflection",
                "overall_score": 0.73,
                "recorded_phases": ["observe", "analyze"],
                "weak_phase_count": 1,
                "timestamp": "2026-04-01T09:35:00",
            },
            {
                "task_id": "analyze-2",
                "feedback_score": 0.2,
                "updated_performance": 0.33,
                "timestamp": "2026-04-01T09:36:00",
            },
        ],
        "ewma_score": 0.71,
        "dimension_trends": {
            "completeness": [0.9, 0.46, 0.42],
            "consistency": [0.82, 0.4, 0.36],
        },
        "tuned_parameters": {
            "quality_threshold": 0.74,
            "max_concurrent_tasks": 6,
        },
    }


def test_build_legacy_learning_feedback_library_aggregates_payload():
    library = build_legacy_learning_feedback_library(
        _make_legacy_learning_payload(),
        source_file="data/learning_data.pkl",
    )

    assert library["contract_version"] == "research-feedback-library.v2"
    assert library["summary"]["record_count"] == 3
    assert library["summary"]["cycle_trend"] == "improving"
    assert library["summary"]["weak_phase_names"] == ["analyze"]

    analyze_record = next(
        record for record in library["records"]
        if record.get("feedback_scope") == "phase_assessment" and record.get("target_phase") == "analyze"
    )
    assert analyze_record["feedback_status"] == "weakness"
    assert analyze_record["issue_count"] == 1

    cycle_record = library["records"][0]
    assert cycle_record["metadata"]["source"] == "legacy_learning_data_pickle"
    assert cycle_record["replay_feedback"]["learning_summary"]["tuned_parameters"]["quality_threshold"] == 0.74
    assert cycle_record["details"]["legacy_stats"]["feedback_event_count"] == 1


def test_backfill_legacy_learning_feedback_imports_into_repository(repo, tmp_path):
    legacy_file = tmp_path / "learning_data.pkl"
    with legacy_file.open("wb") as handle:
        pickle.dump(_make_legacy_learning_payload(), handle)

    summary = backfill_legacy_learning_feedback(
        repo,
        file_path=legacy_file,
        cycle_id="legacy-learning-import",
        cycle_name="Legacy Learning Import",
    )

    session = repo.get_session("legacy-learning-import")
    library = repo.get_learning_feedback_library("legacy-learning-import")

    assert summary["created_session"] is True
    assert summary["imported_record_count"] == 3
    assert session is not None
    assert session["metadata"]["legacy_learning_feedback_backfill"]["source_file"] == str(legacy_file.resolve())
    assert library is not None
    assert library["summary"]["record_count"] == 3
    assert library["summary"]["weak_phase_names"] == ["analyze"]


def test_backfill_legacy_learning_feedback_requires_overwrite_flag(repo, tmp_path):
    legacy_file = tmp_path / "learning_data.pkl"
    with legacy_file.open("wb") as handle:
        pickle.dump(_make_legacy_learning_payload(), handle)

    backfill_legacy_learning_feedback(repo, file_path=legacy_file, cycle_id="legacy-learning-import")

    with pytest.raises(ValueError, match="overwrite_existing=True"):
        backfill_legacy_learning_feedback(repo, file_path=legacy_file, cycle_id="legacy-learning-import")