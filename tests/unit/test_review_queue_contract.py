"""H-1 Review queue contract tests.

Pin the dashboard payload `evidence_board.review_queue` / `queue_summary` /
`queue_filters` shape and the batch-audit schema fields so the queue contract
cannot regress silently.
"""

from __future__ import annotations

import copy
import unittest
from typing import Any, Dict, List

from src.api.research_utils import (
    REVIEW_QUEUE_FILTER_FIELDS,
    REVIEW_QUEUE_PRIORITY_LABELS,
    REVIEW_WORKBENCH_SECTION_META,
    REVIEW_WORKBENCH_STATUS_LABELS,
    _normalize_review_queue_filters,
    _resolve_review_queue_priority,
    build_research_dashboard_payload,
)
from src.api.schemas import (
    ResearchBatchCatalogReviewRequest,
    ResearchBatchPhilologyReviewRequest,
)


def _build_review_queue_snapshot(
    *,
    decisions: List[Dict[str, Any]] | None = None,
    audit_trail: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "job_id": "job-review-queue-contract",
        "topic": "review queue contract",
        "status": "completed",
        "progress": 100,
        "current_phase": "observe",
        "result": {
            "cycle_id": "cycle-review-queue-contract",
            "phases": [
                {
                    "phase": "observe",
                    "status": "completed",
                    "duration_sec": 1.0,
                    "summary": {"observation_count": 1},
                }
            ],
            "pipeline_metadata": {"cycle_name": "queue-contract-demo"},
            "observe_philology": {
                "terminology_standard_table": [
                    {
                        "document_title": "补血汤宋本",
                        "document_urn": "doc:queue:1",
                        "canonical": "黄芪",
                        "label": "本草药名",
                    },
                    {
                        "document_title": "补血汤宋本",
                        "document_urn": "doc:queue:1",
                        "canonical": "当归",
                        "label": "本草药名",
                    },
                ],
                "catalog_summary": {
                    "documents": [
                        {
                            "document_title": "补血汤宋本",
                            "document_urn": "doc:queue:1",
                            "source_type": "local",
                            "catalog_id": "local:catalog:queue:1",
                            "work_title": "补血汤",
                            "fragment_title": "补血汤",
                            "work_fragment_key": "补血汤|补血汤",
                            "version_lineage_key": "补血汤|补血汤|明|李时珍|宋本",
                            "witness_key": "local:witness:queue:1",
                            "dynasty": "明",
                            "author": "李时珍",
                            "edition": "宋本",
                        }
                    ]
                },
            },
        },
    }
    if decisions is not None:
        snapshot["result"]["observe_philology"]["review_workbench_decisions"] = decisions
    if audit_trail is not None:
        snapshot["result"]["observe_philology"]["review_workbench_batch_audit_trail"] = audit_trail
    return snapshot


def _terminology_asset_keys(payload: Dict[str, Any]) -> List[str]:
    sections = payload["evidence_board"]["review_workbench"]["sections"]
    for section in sections:
        if section.get("asset_type") == "terminology_row":
            return [item["asset_key"] for item in section.get("items") or []]
    return []


class ReviewQueueContractTests(unittest.TestCase):
    def setUp(self) -> None:
        baseline = build_research_dashboard_payload(_build_review_queue_snapshot())
        self.terminology_keys = _terminology_asset_keys(baseline)
        self.assertGreaterEqual(
            len(self.terminology_keys),
            2,
            "fixture should expose at least two terminology rows for filtering tests",
        )

    # ---- queue_summary / queue_filters / review_queue contract ----

    def test_review_queue_summary_exposes_required_keys(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        evidence_board = payload["evidence_board"]
        review_workbench = evidence_board["review_workbench"]

        for key in (
            "queue_summary",
            "queue_filters",
            "review_queue",
            "selection_supported",
            "batch_audit_supported",
        ):
            self.assertIn(key, review_workbench, f"review_workbench missing {key}")

        queue_summary = review_workbench["queue_summary"]
        for key in (
            "all_item_count",
            "visible_item_count",
            "total_pending",
            "section_counts",
            "priority_distribution",
            "review_status_distribution",
            "reviewer_distribution",
        ):
            self.assertIn(key, queue_summary, f"queue_summary missing {key}")

    def test_review_queue_propagates_to_evidence_board_root(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        evidence_board = payload["evidence_board"]
        self.assertIn("review_queue", evidence_board)
        self.assertIn("queue_summary", evidence_board)
        self.assertIn("queue_filters", evidence_board)
        self.assertEqual(
            evidence_board["review_queue"]["visible_item_count"],
            evidence_board["review_workbench"]["review_queue"]["visible_item_count"],
        )

    def test_queue_filter_options_cover_required_axes(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        options = payload["evidence_board"]["review_workbench"]["queue_filters"]["options"]
        for axis in REVIEW_QUEUE_FILTER_FIELDS:
            self.assertIn(axis, options, f"queue_filters.options missing {axis}")
            self.assertIsInstance(options[axis], list)

    def test_queue_filter_options_label_terminology_section(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        asset_options = payload["evidence_board"]["review_workbench"]["queue_filters"]["options"]["asset_type"]
        terminology = next((opt for opt in asset_options if opt["value"] == "terminology_row"), None)
        self.assertIsNotNone(terminology, "terminology_row should appear as filter option")
        self.assertEqual(
            terminology["label"],
            REVIEW_WORKBENCH_SECTION_META["terminology_row"]["title"],
        )
        self.assertGreaterEqual(terminology["count"], 2)

    def test_review_queue_includes_items_and_workload(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        review_queue = payload["evidence_board"]["review_workbench"]["review_queue"]
        self.assertIn("items", review_queue)
        self.assertIn("reviewer_workload", review_queue)
        self.assertIn("recent_batch_operations", review_queue)
        self.assertIn("last_batch_summary", review_queue)
        self.assertGreater(len(review_queue["items"]), 0)

    def test_unassigned_pending_items_show_in_reviewer_workload(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        workload = payload["evidence_board"]["review_workbench"]["review_queue"]["reviewer_workload"]
        unassigned = next((bucket for bucket in workload if bucket["reviewer_label"] == "未认领"), None)
        self.assertIsNotNone(unassigned, "unassigned reviewer bucket should be present")
        self.assertGreaterEqual(unassigned["open"], 1)

    def test_selection_and_batch_audit_flags_advertised(self) -> None:
        payload = build_research_dashboard_payload(_build_review_queue_snapshot())
        review_workbench = payload["evidence_board"]["review_workbench"]
        self.assertTrue(review_workbench["selection_supported"])
        self.assertTrue(review_workbench["batch_audit_supported"])

    # ---- philology_filters wiring ----

    def test_philology_filter_asset_type_narrows_queue(self) -> None:
        payload = build_research_dashboard_payload(
            _build_review_queue_snapshot(),
            philology_filters={"asset_type": "terminology_row"},
        )
        review_workbench = payload["evidence_board"]["review_workbench"]
        self.assertEqual(
            review_workbench["queue_filters"]["active_filters"]["asset_type"],
            "terminology_row",
        )
        sections = review_workbench["sections"]
        non_terminology_with_items = [
            section for section in sections
            if section.get("asset_type") != "terminology_row" and (section.get("items") or [])
        ]
        self.assertEqual(non_terminology_with_items, [], "non-terminology sections should be empty under filter")

    def test_philology_filter_review_status_narrows_queue(self) -> None:
        keys = self.terminology_keys
        decisions = [
            {
                "asset_type": "terminology_row",
                "asset_key": keys[0],
                "review_status": "accepted",
                "reviewer": "tester",
                "decision_basis": "queue contract",
            }
        ]
        payload = build_research_dashboard_payload(
            _build_review_queue_snapshot(decisions=decisions),
            philology_filters={"review_status": "accepted"},
        )
        review_workbench = payload["evidence_board"]["review_workbench"]
        self.assertEqual(
            review_workbench["queue_filters"]["active_filters"]["review_status"],
            "accepted",
        )
        for section in review_workbench["sections"]:
            for item in section.get("items") or []:
                self.assertEqual(item["review_status"], "accepted")

    def test_philology_filter_priority_bucket_normalized(self) -> None:
        payload = build_research_dashboard_payload(
            _build_review_queue_snapshot(),
            philology_filters={"priority_bucket": "MEDIUM"},
        )
        active = payload["evidence_board"]["review_workbench"]["queue_filters"]["active_filters"]
        self.assertEqual(active.get("priority_bucket"), "medium")

    def test_philology_filter_reviewer_unassigned_matches_open_items(self) -> None:
        payload = build_research_dashboard_payload(
            _build_review_queue_snapshot(),
            philology_filters={"reviewer": "unassigned"},
        )
        review_queue = payload["evidence_board"]["review_workbench"]["review_queue"]
        self.assertGreater(review_queue["visible_item_count"], 0)
        for item in review_queue["items"]:
            self.assertEqual(item.get("reviewer_label") or "未认领", "未认领")

    def test_invalid_priority_bucket_filter_dropped(self) -> None:
        normalized = _normalize_review_queue_filters({"priority_bucket": "URGENT"})
        self.assertNotIn("priority_bucket", normalized)

    # ---- batch audit trail surface ----

    def test_recent_batch_operations_preserve_selection_snapshot(self) -> None:
        keys = self.terminology_keys
        decisions = [
            {
                "asset_type": "terminology_row",
                "asset_key": keys[0],
                "review_status": "accepted",
                "reviewer": "tester",
                "decision_basis": "批量术语复核",
                "review_reasons": ["reviewer_batch"],
            }
        ]
        audit_trail = [
            {
                "applied_at": "2026-04-20T12:00:00",
                "applied_count": 1,
                "reviewer": "tester",
                "shared_decision_basis": "批量术语复核",
                "shared_review_reasons": ["reviewer_batch"],
                "selection_snapshot": {
                    "selection_strategy": "current_filtered_selection",
                    "selected_count": 1,
                    "asset_types": ["terminology_row"],
                },
            }
        ]
        payload = build_research_dashboard_payload(
            _build_review_queue_snapshot(decisions=decisions, audit_trail=audit_trail)
        )
        review_queue = payload["evidence_board"]["review_workbench"]["review_queue"]
        recent = review_queue["recent_batch_operations"]
        self.assertGreater(len(recent), 0)
        self.assertEqual(recent[0]["shared_decision_basis"], "批量术语复核")
        self.assertEqual(recent[0]["shared_review_reasons"], ["reviewer_batch"])
        self.assertEqual(recent[0]["selection_snapshot"]["selected_count"], 1)
        self.assertEqual(review_queue["last_batch_summary"], recent[0])

    # ---- helper invariants ----

    def test_priority_resolution_promotes_needs_source(self) -> None:
        priority = _resolve_review_queue_priority(
            {
                "asset_type": "terminology_row",
                "review_status": "needs_source",
                "needs_manual_review": True,
            }
        )
        self.assertEqual(priority, "high")

    def test_priority_resolution_marks_closed_items_low(self) -> None:
        priority = _resolve_review_queue_priority(
            {
                "asset_type": "terminology_row",
                "review_status": "accepted",
                "needs_manual_review": False,
            }
        )
        self.assertEqual(priority, "low")
        self.assertIn("low", REVIEW_QUEUE_PRIORITY_LABELS)
        self.assertIn("accepted", REVIEW_WORKBENCH_STATUS_LABELS)

    # ---- batch audit schema contract (H-1-4) ----

    def test_batch_philology_schema_accepts_selection_snapshot(self) -> None:
        request = ResearchBatchPhilologyReviewRequest(
            decisions=[
                {
                    "asset_type": "terminology_row",
                    "asset_key": "k1",
                    "review_status": "accepted",
                    "reviewer": "tester",
                }
            ],
            selection_snapshot={"selected_count": 1, "asset_types": ["terminology_row"]},
            shared_decision_basis="批量复核",
            shared_review_reasons=["reviewer_batch"],
        )
        self.assertEqual(request.selection_snapshot["selected_count"], 1)
        self.assertEqual(request.shared_decision_basis, "批量复核")
        self.assertEqual(request.shared_review_reasons, ["reviewer_batch"])

    def test_batch_catalog_schema_mirrors_audit_fields(self) -> None:
        request = ResearchBatchCatalogReviewRequest(
            decisions=[
                {
                    "catalog_id": "c1",
                    "review_status": "accepted",
                    "reviewer": "tester",
                }
            ],
            selection_snapshot={"selected_count": 2},
            shared_decision_basis="catalog batch",
            shared_review_reasons=["reviewer_batch"],
        )
        self.assertEqual(request.selection_snapshot["selected_count"], 2)
        self.assertEqual(request.shared_decision_basis, "catalog batch")
        self.assertEqual(request.shared_review_reasons, ["reviewer_batch"])

    def test_batch_philology_schema_defaults_audit_fields(self) -> None:
        request = ResearchBatchPhilologyReviewRequest(
            decisions=[
                {
                    "asset_type": "terminology_row",
                    "asset_key": "k1",
                    "review_status": "pending",
                }
            ]
        )
        self.assertEqual(request.selection_snapshot, {})
        self.assertIsNone(request.shared_decision_basis)
        self.assertEqual(request.shared_review_reasons, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
