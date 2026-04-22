"""Phase H / H-3 — dispute archive board contract tests.

Covers:
* `build_dispute_archive_board` shape (supported flag, summary, views).
* `build_research_dashboard_payload` propagation of `review_disputes`
  into the evidence board payload.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.api.research_utils import (
    build_dispute_archive_board,
    build_research_dashboard_payload,
)


def _dispute(
    *,
    case_id: str = "DISP-0001",
    asset_type: str = "catalog",
    asset_key: str = "k-1",
    dispute_status: str = "open",
    arbitrator: str | None = None,
    opened_by: str = "李研究员",
    resolution: str | None = None,
) -> Dict[str, Any]:
    return {
        "id": f"id-{case_id}",
        "cycle_id": "cycle-h3",
        "case_id": case_id,
        "asset_type": asset_type,
        "asset_key": asset_key,
        "dispute_status": dispute_status,
        "arbitrator": arbitrator,
        "opened_by": opened_by,
        "resolution": resolution,
        "summary": "test",
        "events": [],
        "metadata": {},
    }


@pytest.fixture()
def mixed_disputes() -> List[Dict[str, Any]]:
    return [
        _dispute(case_id="DISP-0001", dispute_status="open"),
        _dispute(case_id="DISP-0002", dispute_status="assigned", arbitrator="张专家"),
        _dispute(case_id="DISP-0003", dispute_status="assigned", arbitrator="王专家"),
        _dispute(case_id="DISP-0004", dispute_status="resolved", arbitrator="张专家", resolution="accepted"),
        _dispute(case_id="DISP-0005", dispute_status="withdrawn"),
    ]


class TestBuildDisputeArchiveBoard:
    def test_returns_unsupported_for_non_list(self):
        result = build_dispute_archive_board(None)
        assert result["supported"] is False
        assert result["views"] == {"inbox": [], "mine": [], "history": []}
        assert result["summary"] == {}

    def test_returns_unsupported_for_dict(self):
        result = build_dispute_archive_board({"foo": "bar"})
        assert result["supported"] is False

    def test_empty_list_is_supported_with_zero_summary(self):
        result = build_dispute_archive_board([])
        assert result["supported"] is True
        assert result["summary"]["total"] == 0
        assert result["summary"]["inbox"] == 0
        assert result["summary"]["history"] == 0

    def test_summary_counts_by_status(self, mixed_disputes):
        result = build_dispute_archive_board(mixed_disputes)
        assert result["supported"] is True
        s = result["summary"]
        assert s["total"] == 5
        assert s["open"] == 1
        assert s["assigned"] == 2
        assert s["resolved"] == 1
        assert s["withdrawn"] == 1
        assert s["inbox"] == 3
        assert s["history"] == 2

    def test_inbox_collects_open_and_assigned(self, mixed_disputes):
        result = build_dispute_archive_board(mixed_disputes)
        case_ids = {d["case_id"] for d in result["views"]["inbox"]}
        assert case_ids == {"DISP-0001", "DISP-0002", "DISP-0003"}

    def test_history_collects_resolved_and_withdrawn(self, mixed_disputes):
        result = build_dispute_archive_board(mixed_disputes)
        case_ids = {d["case_id"] for d in result["views"]["history"]}
        assert case_ids == {"DISP-0004", "DISP-0005"}

    def test_mine_filters_by_arbitrator(self, mixed_disputes):
        result = build_dispute_archive_board(mixed_disputes, current_reviewer="张专家")
        case_ids = {d["case_id"] for d in result["views"]["mine"]}
        # Only inbox + arbitrator==张专家 → DISP-0002 (resolved excluded)
        assert case_ids == {"DISP-0002"}
        assert result["summary"]["mine"] == 1
        assert result["current_reviewer"] == "张专家"

    def test_mine_empty_when_no_match(self, mixed_disputes):
        result = build_dispute_archive_board(mixed_disputes, current_reviewer="不存在")
        assert result["views"]["mine"] == []
        assert result["summary"]["mine"] == 0

    def test_unknown_status_excluded_from_views(self):
        result = build_dispute_archive_board([
            _dispute(case_id="DISP-X", dispute_status="weird"),
        ])
        assert result["supported"] is True
        assert result["views"]["inbox"] == []
        assert result["views"]["history"] == []
        assert result["summary"]["total"] == 1


class TestDashboardPayloadIntegration:
    def _snapshot(self) -> Dict[str, Any]:
        return {
            "job_id": "job-1",
            "topic": "test",
            "status": "completed",
            "progress": 100.0,
            "result": {"cycle_id": "cycle-h3"},
        }

    def test_dashboard_includes_dispute_board_when_disputes_provided(self, mixed_disputes):
        payload = build_research_dashboard_payload(
            self._snapshot(),
            review_disputes=mixed_disputes,
            current_reviewer="张专家",
        )
        evidence_board = payload["evidence_board"]
        dispute_board = evidence_board["dispute_board"]
        assert dispute_board["supported"] is True
        assert dispute_board["summary"]["total"] == 5
        assert dispute_board["summary"]["mine"] == 1

    def test_dashboard_dispute_board_unsupported_when_omitted(self):
        payload = build_research_dashboard_payload(self._snapshot())
        dispute_board = payload["evidence_board"]["dispute_board"]
        assert dispute_board["supported"] is False

    def test_review_workbench_exposes_dispute_board(self, mixed_disputes):
        payload = build_research_dashboard_payload(
            self._snapshot(),
            review_disputes=mixed_disputes,
            current_reviewer="王专家",
        )
        review_queue = payload["evidence_board"]["review_queue"]
        assert review_queue["dispute_board"]["supported"] is True
        assert review_queue["dispute_board"]["summary"]["mine"] == 1
