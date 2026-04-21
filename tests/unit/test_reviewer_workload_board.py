"""Phase H / H-2 — reviewer workload board contract tests.

Covers:
* `build_reviewer_workload_board` shape (supported flag, summary,
  views, by_reviewer, current_reviewer).
* `build_research_dashboard_payload` propagation of `review_assignments`
  and `current_reviewer` into the evidence board payload.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.api.research_utils import (
    build_research_dashboard_payload,
    build_reviewer_workload_board,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _assignment(
    *,
    asset_type: str = "catalog",
    asset_key: str = "k-1",
    assignee: str = "李研究员",
    queue_status: str = "claimed",
    priority_bucket: str = "medium",
    is_overdue: bool = False,
    backlog_age_seconds: float = 0.0,
    due_at: str | None = None,
    assignment_id: str = "assign-1",
) -> Dict[str, Any]:
    return {
        "id": assignment_id,
        "cycle_id": "cycle-h2",
        "asset_type": asset_type,
        "asset_key": asset_key,
        "assignee": assignee,
        "reviewer_label": assignee or "未认领",
        "queue_status": queue_status,
        "priority_bucket": priority_bucket,
        "is_overdue": is_overdue,
        "backlog_age_seconds": backlog_age_seconds,
        "due_at": due_at,
    }


@pytest.fixture()
def mixed_assignments() -> List[Dict[str, Any]]:
    return [
        _assignment(asset_key="k-1", assignee="李研究员", priority_bucket="high"),
        _assignment(asset_key="k-2", assignee="李研究员", queue_status="completed"),
        _assignment(asset_key="k-3", assignee="张研究员"),
        _assignment(
            asset_key="k-4",
            assignee="张研究员",
            is_overdue=True,
            due_at="2020-01-01T00:00:00",
        ),
        _assignment(asset_key="k-5", assignee=""),
    ]


# ---------------------------------------------------------------------------
# build_reviewer_workload_board contract
# ---------------------------------------------------------------------------


class TestBuildReviewerWorkloadBoard:
    def test_returns_unsupported_when_input_not_a_list(self):
        result = build_reviewer_workload_board(None)
        assert result["supported"] is False
        assert result["summary"] == {}
        assert result["views"] == {}
        assert result["assignments"] == []
        assert result["current_reviewer"] == ""

    def test_returns_supported_with_zero_summary_for_empty_list(self):
        result = build_reviewer_workload_board([])
        assert result["supported"] is True
        assert result["summary"] == {
            "total": 0,
            "unassigned": 0,
            "overdue": 0,
            "completed": 0,
            "mine": 0,
            "high_priority": 0,
        }
        assert result["views"]["mine"] == []
        assert result["views"]["unassigned"] == []
        assert result["views"]["overdue"] == []
        assert result["by_reviewer"] == {}

    def test_summary_counts_match_inputs(self, mixed_assignments):
        result = build_reviewer_workload_board(mixed_assignments)
        summary = result["summary"]
        assert summary["total"] == 5
        assert summary["unassigned"] == 1
        assert summary["overdue"] == 1
        assert summary["completed"] == 1
        assert summary["high_priority"] == 1
        assert summary["mine"] == 0  # no current_reviewer provided

    def test_current_reviewer_filters_mine_view(self, mixed_assignments):
        result = build_reviewer_workload_board(
            mixed_assignments, current_reviewer="李研究员"
        )
        mine_keys = [item["asset_key"] for item in result["views"]["mine"]]
        # Completed items must NOT appear in 我负责 view.
        assert mine_keys == ["k-1"]
        assert result["summary"]["mine"] == 1
        assert result["current_reviewer"] == "李研究员"

    def test_unassigned_view_collects_blank_assignees(self, mixed_assignments):
        result = build_reviewer_workload_board(mixed_assignments)
        assert [item["asset_key"] for item in result["views"]["unassigned"]] == ["k-5"]

    def test_overdue_view_collects_overdue_items(self, mixed_assignments):
        result = build_reviewer_workload_board(mixed_assignments)
        assert [item["asset_key"] for item in result["views"]["overdue"]] == ["k-4"]

    def test_overdue_excludes_completed_items(self):
        rows = [
            _assignment(
                asset_key="k-completed-overdue",
                queue_status="completed",
                is_overdue=True,
                due_at="2020-01-01T00:00:00",
            ),
        ]
        result = build_reviewer_workload_board(rows)
        assert result["views"]["overdue"] == []
        assert result["summary"]["overdue"] == 0
        assert result["summary"]["completed"] == 1

    def test_by_reviewer_groups_by_assignee(self, mixed_assignments):
        result = build_reviewer_workload_board(mixed_assignments)
        by_reviewer = result["by_reviewer"]
        assert set(by_reviewer.keys()) == {"李研究员", "张研究员"}
        assert {row["asset_key"] for row in by_reviewer["李研究员"]} == {"k-1", "k-2"}
        assert {row["asset_key"] for row in by_reviewer["张研究员"]} == {"k-3", "k-4"}

    def test_assignments_passthrough_preserves_inputs(self, mixed_assignments):
        result = build_reviewer_workload_board(mixed_assignments)
        assert len(result["assignments"]) == len(mixed_assignments)
        assert {item["asset_key"] for item in result["assignments"]} == {
            item["asset_key"] for item in mixed_assignments
        }


# ---------------------------------------------------------------------------
# Dashboard payload integration
# ---------------------------------------------------------------------------


def _minimal_snapshot() -> Dict[str, Any]:
    return {
        "job_id": "job-h2",
        "topic": "H-2 reviewer board",
        "status": "running",
        "progress": 25,
        "current_phase": "observe",
        "result": {
            "cycle_id": "cycle-h2",
            "phases": [],
            "pipeline_metadata": {},
        },
    }


class TestDashboardPayloadIntegration:
    def test_dashboard_payload_includes_workload_board_in_evidence(self):
        payload = build_research_dashboard_payload(
            _minimal_snapshot(),
            review_assignments=[_assignment()],
            current_reviewer="李研究员",
        )
        evidence = payload["evidence_board"]
        assert "reviewer_workload_board" in evidence
        board = evidence["reviewer_workload_board"]
        assert board["supported"] is True
        assert board["current_reviewer"] == "李研究员"
        assert board["summary"]["total"] == 1

    def test_dashboard_payload_marks_unsupported_when_no_assignments(self):
        payload = build_research_dashboard_payload(_minimal_snapshot())
        board = payload["evidence_board"]["reviewer_workload_board"]
        assert board["supported"] is False

    def test_dashboard_payload_propagates_current_reviewer_to_views(self):
        payload = build_research_dashboard_payload(
            _minimal_snapshot(),
            review_assignments=[
                _assignment(asset_key="k-1", assignee="李研究员"),
                _assignment(asset_key="k-2", assignee="张研究员"),
            ],
            current_reviewer="李研究员",
        )
        board = payload["evidence_board"]["reviewer_workload_board"]
        mine_keys = [item["asset_key"] for item in board["views"]["mine"]]
        assert mine_keys == ["k-1"]
