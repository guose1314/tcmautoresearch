"""Phase H / H-4 — review sampling + QC summary unit tests."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.research.review_sampling import (
    build_review_sample,
    compute_review_quality_summary,
)


def _item(
    *,
    id_: str = "i-1",
    asset_type: str = "catalog",
    asset_key: str = "k-1",
    reviewer: str = "李研究员",
    review_status: str = "pending",
    priority_bucket: str = "medium",
    is_overdue: bool = False,
    backlog_age_seconds: float = 0.0,
) -> Dict[str, Any]:
    return {
        "id": id_,
        "asset_type": asset_type,
        "asset_key": asset_key,
        "reviewer": reviewer,
        "review_status": review_status,
        "priority_bucket": priority_bucket,
        "is_overdue": is_overdue,
        "backlog_age_seconds": backlog_age_seconds,
    }


@pytest.fixture()
def queue_items() -> List[Dict[str, Any]]:
    return [
        _item(id_="i-1", asset_key="k-1", reviewer="李研究员", priority_bucket="high"),
        _item(id_="i-2", asset_key="k-2", reviewer="李研究员", priority_bucket="medium"),
        _item(id_="i-3", asset_key="k-3", reviewer="张研究员", priority_bucket="low", review_status="accepted"),
        _item(id_="i-4", asset_key="k-4", reviewer="张研究员", priority_bucket="high", is_overdue=True, backlog_age_seconds=7200.0),
        _item(id_="i-5", asset_key="k-5", reviewer="王研究员", asset_type="workbench", priority_bucket="medium"),
        _item(id_="i-6", asset_key="k-6", reviewer="王研究员", asset_type="workbench", priority_bucket="medium"),
    ]


def _dispute(
    *,
    case_id: str,
    dispute_status: str = "resolved",
    resolution: str | None = None,
    arbitrator: str | None = None,
    opened_by: str = "李研究员",
    asset_type: str = "catalog",
) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "dispute_status": dispute_status,
        "resolution": resolution,
        "arbitrator": arbitrator,
        "opened_by": opened_by,
        "asset_type": asset_type,
    }


class TestBuildReviewSample:
    def test_empty_input_returns_empty_sample(self):
        result = build_review_sample([], sample_size=5)
        assert result["supported"] is True
        assert result["items"] == []
        assert result["summary"]["input_count"] == 0
        assert result["summary"]["filtered_count"] == 0
        assert result["summary"]["selected_count"] == 0

    def test_negative_sample_size_raises(self, queue_items):
        with pytest.raises(ValueError):
            build_review_sample(queue_items, sample_size=-1)

    def test_sample_size_zero_returns_empty_items(self, queue_items):
        result = build_review_sample(queue_items, sample_size=0)
        assert result["items"] == []
        assert result["summary"]["filtered_count"] == 6

    def test_sample_caps_at_filtered_count(self, queue_items):
        result = build_review_sample(queue_items, sample_size=100)
        assert result["summary"]["selected_count"] == 6
        assert len(result["items"]) == 6

    def test_filter_by_reviewer(self, queue_items):
        result = build_review_sample(queue_items, sample_size=10, reviewer="李研究员")
        keys = {it["asset_key"] for it in result["items"]}
        assert keys == {"k-1", "k-2"}
        assert result["summary"]["filters"]["reviewer"] == "李研究员"

    def test_filter_by_asset_type(self, queue_items):
        result = build_review_sample(queue_items, sample_size=10, asset_type="workbench")
        keys = {it["asset_key"] for it in result["items"]}
        assert keys == {"k-5", "k-6"}

    def test_filter_by_review_status(self, queue_items):
        result = build_review_sample(queue_items, sample_size=10, review_status="accepted")
        assert [it["asset_key"] for it in result["items"]] == ["k-3"]

    def test_filter_by_priority(self, queue_items):
        result = build_review_sample(queue_items, sample_size=10, priority_bucket="high")
        keys = {it["asset_key"] for it in result["items"]}
        assert keys == {"k-1", "k-4"}

    def test_combined_filters(self, queue_items):
        result = build_review_sample(
            queue_items, sample_size=10,
            reviewer="张研究员", priority_bucket="high",
        )
        assert [it["asset_key"] for it in result["items"]] == ["k-4"]

    def test_seed_is_deterministic(self, queue_items):
        a = build_review_sample(queue_items, sample_size=3, seed="seed-A")
        b = build_review_sample(queue_items, sample_size=3, seed="seed-A")
        assert [it["asset_key"] for it in a["items"]] == [it["asset_key"] for it in b["items"]]

    def test_different_seed_changes_selection(self, queue_items):
        a = build_review_sample(queue_items, sample_size=2, seed="seed-A")
        b = build_review_sample(queue_items, sample_size=2, seed="seed-B")
        # With 6 items and only 2 selected, two seeds will almost always
        # produce a different head ordering. Accept either different sets or
        # different orderings as a deterministic-but-distinct signal.
        assert (
            [it["asset_key"] for it in a["items"]]
            != [it["asset_key"] for it in b["items"]]
        )


class TestComputeReviewQualitySummary:
    def test_empty_inputs_return_zero_metrics(self):
        result = compute_review_quality_summary()
        assert result["supported"] is True
        assert result["assignment_count"] == 0
        assert result["dispute_count"] == 0
        assert result["resolved_dispute_count"] == 0
        assert result["agreement_rate"] == 0.0
        assert result["overturn_rate"] == 0.0
        assert result["recheck_count"] == 0
        assert result["overdue_count"] == 0
        assert result["median_backlog_age_hours"] == 0.0

    def test_overdue_and_backlog_metrics(self, queue_items):
        result = compute_review_quality_summary(review_assignments=queue_items)
        assert result["assignment_count"] == 6
        assert result["overdue_count"] == 1
        # Median of [0,0,0,7200,0,0] = 0 hours
        assert result["median_backlog_age_hours"] == 0.0

    def test_agreement_and_overturn_rates(self):
        disputes = [
            _dispute(case_id="A", resolution="accepted"),
            _dispute(case_id="B", resolution="accepted"),
            _dispute(case_id="C", resolution="rejected"),
            _dispute(case_id="D", resolution="needs_source"),
            _dispute(case_id="E", dispute_status="open", resolution=None),
        ]
        result = compute_review_quality_summary(review_disputes=disputes)
        assert result["dispute_count"] == 5
        assert result["resolved_dispute_count"] == 4
        assert result["agreement_rate"] == 0.5
        assert result["overturn_rate"] == 0.5
        assert result["recheck_count"] == 5

    def test_filter_by_reviewer_for_disputes(self):
        disputes = [
            _dispute(case_id="A", resolution="accepted", arbitrator="张专家"),
            _dispute(case_id="B", resolution="rejected", arbitrator="李研究员"),
            _dispute(case_id="C", resolution="accepted", opened_by="张专家"),
        ]
        result = compute_review_quality_summary(
            review_disputes=disputes, reviewer="张专家",
        )
        assert result["dispute_count"] == 2
        assert result["resolved_dispute_count"] == 2
        assert result["agreement_rate"] == 1.0

    def test_filter_by_asset_type(self, queue_items):
        result = compute_review_quality_summary(
            review_assignments=queue_items, asset_type="workbench",
        )
        assert result["assignment_count"] == 2
        assert result["overdue_count"] == 0

    def test_median_backlog_uses_hours(self):
        items = [
            _item(id_="x1", backlog_age_seconds=3600.0),
            _item(id_="x2", backlog_age_seconds=7200.0),
            _item(id_="x3", backlog_age_seconds=10800.0),
        ]
        result = compute_review_quality_summary(review_assignments=items)
        # median seconds = 7200 → 2.0 hours
        assert result["median_backlog_age_hours"] == 2.0
