import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.quality_feedback import build_feedback_report, export_feedback_report


class TestQualityFeedback(unittest.TestCase):
    def _issue_owner(self, item: dict) -> str:
        return str(item["issue_body"]["summary"].get("owner", "unknown"))

    def _issue_reference(self, item: dict, key: str, default=None):
        artifact_references = item["issue_body"].get("artifact_references", {})
        return artifact_references.get(key, default)

    def _assert_issue_body_markdown_matches_item(self, draft_text: str, item: dict) -> None:
        issue_body = item["issue_body"]
        summary = issue_body["summary"]
        inventory_context = issue_body["inventory_context"]
        self.assertIn("## Summary", draft_text)
        self.assertIn("- Owner: {0}".format(summary["owner"]), draft_text)
        self.assertIn("- Quality Score: {0}".format(summary["quality_score"]), draft_text)
        self.assertIn("- Trend: {0}".format(summary["trend_status"]), draft_text)
        self.assertNotIn("quality_score", item)
        self.assertNotIn("trend_status", item)
        self.assertNotIn("inventory_trend_status", item)
        self.assertNotIn("inventory_history_points", item)
        self.assertNotIn("inventory_missing_contract_delta", item)
        self.assertNotIn("inventory_uncategorized_root_script_delta", item)
        self.assertNotIn("inventory_recommended_next_target", item)
        self.assertNotIn("action_items", item)
        self.assertNotIn("acceptance_checks", item)
        self.assertNotIn("owner", item)
        self.assertNotIn("title", item)
        self.assertNotIn("template", item)
        self.assertNotIn("labels", item)
        self.assertNotIn("file", item)
        self.assertNotIn("index_position", item)
        self.assertIn("status", inventory_context)
        self.assertIn("history_points", inventory_context)
        self.assertIn("missing_contract_delta", inventory_context)
        self.assertIn("uncategorized_root_script_delta", inventory_context)
        self.assertIn("recommended_next_target", inventory_context)
        inventory_trend = issue_body.get("inventory_trend")
        if inventory_trend is None:
            self.assertNotIn("## Inventory Trend", draft_text)
        else:
            self.assertIn("## Inventory Trend", draft_text)
            self.assertIn("- Status: {0}".format(inventory_trend["status"]), draft_text)
            self.assertIn("- History Points: {0}".format(inventory_trend["history_points"]), draft_text)
            self.assertIn("- Missing Contract Delta: {0}".format(inventory_trend["missing_contract_delta"]), draft_text)
            self.assertIn(
                "- Uncategorized Root Script Delta: {0}".format(inventory_trend["uncategorized_root_script_delta"]),
                draft_text,
            )
            self.assertIn(
                "- Recommended Next Target: {0}".format(inventory_trend["recommended_next_target"]),
                draft_text,
            )
        for action_item in issue_body["action_items"]:
            self.assertIn(
                "- [{priority}] {dimension}: {action} (score={score})".format(**action_item),
                draft_text,
            )
        for acceptance_check in issue_body["acceptance_checks"]:
            self.assertIn("- [ ] {0}".format(acceptance_check["text"]), draft_text)
        artifact_references = issue_body["artifact_references"]
        self.assertIn("## Artifact References", draft_text)
        self.assertIn("- Issue Index: {0}".format(artifact_references["issue_index_path"]), draft_text)
        self.assertIn("- Issue Directory: {0}".format(artifact_references["issue_dir"]), draft_text)
        self.assertIn("- Issue Draft File: {0}".format(artifact_references["issue_draft_file"]), draft_text)
        self.assertIn("- Owner: {0}".format(artifact_references["owner"]), draft_text)
        self.assertIn("- Title: {0}".format(artifact_references["title"]), draft_text)
        self.assertIn("- Template: {0}".format(artifact_references["template"]), draft_text)
        self.assertIn("- Labels: {0}".format(", ".join(artifact_references["labels"])), draft_text)
        self.assertIn("- Index Position: {0}".format(artifact_references["index_position"]), draft_text)

    def _assert_removed_flat_issue_metadata(self, payload: dict, prefix: str) -> None:
        removed_keys = [
            f"{prefix}_quality_scores",
            f"{prefix}_trend_statuses",
            f"{prefix}_inventory_trend_statuses",
            f"{prefix}_inventory_history_points",
            f"{prefix}_inventory_missing_contract_deltas",
            f"{prefix}_inventory_uncategorized_root_script_deltas",
            f"{prefix}_inventory_recommended_next_targets",
            f"{prefix}_action_items",
            f"{prefix}_acceptance_checks",
        ]
        for key in removed_keys:
            self.assertNotIn(key, payload)

    def _assert_removed_issue_reference_metadata(self, payload: dict, keys: list[str]) -> None:
        for key in keys:
            self.assertNotIn(key, payload)

    def test_build_feedback_report_healthy(self):
        report = build_feedback_report(
            {
                "overall_score": 95.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 95,
                    "code_health": 88,
                    "architecture_health": 98,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_trend": {
                    "status": "stable",
                    "history_points": 3,
                    "missing_contract_delta": 0,
                    "uncategorized_root_script_delta": 0,
                }
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 2,
                    "missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "non_governance_domain_script": 1,
                    },
                },
                "recommendation": {"recommended_path": None},
            },
        )
        self.assertEqual(report["feedback_level"], "healthy")
        self.assertGreaterEqual(report["overall_score"], 90.0)
        self.assertEqual(report["inventory_summary"]["status"], "healthy")
        self.assertEqual(report["inventory_trend"]["status"], "stable")
        self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in report["priority_actions"]))
        self.assertIn("Quality consumer inventory 当前无合同缺口。", report["acknowledgements"])

    def test_build_feedback_report_adds_inventory_trend_followup_when_regressing(self):
        report = build_feedback_report(
            {
                "overall_score": 93.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 96,
                    "code_health": 92,
                    "architecture_health": 97,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                "inventory_trend": {
                    "status": "regressing",
                    "history_points": 4,
                    "missing_contract_delta": 1,
                    "uncategorized_root_script_delta": 0,
                    "recommended_next_target_changed": True,
                },
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "non_governance_domain_script": 1,
                    },
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )

        self.assertEqual(report["inventory_summary"]["status"], "healthy")
        self.assertEqual(report["inventory_trend"]["status"], "regressing")
        self.assertTrue(any(item["dimension"] == "quality_consumer_inventory_trend" for item in report["priority_actions"]))
        self.assertTrue(any(item["owner"] == "quality-governance" for item in report["owner_notifications"]))
        self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in report["issue_drafts"]))

    def test_build_feedback_report_keeps_quiet_when_target_changes_but_inventory_trend_stays_stable(self):
        report = build_feedback_report(
            {
                "overall_score": 93.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 96,
                    "code_health": 92,
                    "architecture_health": 97,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                "inventory_trend": {
                    "status": "stable",
                    "history_points": 4,
                    "missing_contract_delta": 0,
                    "uncategorized_root_script_delta": 0,
                    "recommended_next_target_changed": True,
                },
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "non_governance_domain_script": 1,
                    },
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )

        self.assertEqual(report["inventory_summary"]["status"], "healthy")
        self.assertEqual(report["inventory_trend"]["status"], "stable")
        self.assertTrue(report["inventory_trend"]["recommended_next_target_changed"])
        self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in report["priority_actions"]))
        self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in report["issue_drafts"]))

    def test_build_feedback_report_keeps_quiet_when_target_changes_but_inventory_trend_improves(self):
        report = build_feedback_report(
            {
                "overall_score": 93.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 96,
                    "code_health": 92,
                    "architecture_health": 97,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                "inventory_trend": {
                    "status": "improving",
                    "history_points": 4,
                    "missing_contract_delta": -1,
                    "uncategorized_root_script_delta": 0,
                    "recommended_next_target_changed": True,
                },
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "non_governance_domain_script": 1,
                    },
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )

        self.assertEqual(report["inventory_summary"]["status"], "healthy")
        self.assertEqual(report["inventory_trend"]["status"], "improving")
        self.assertTrue(report["inventory_trend"]["recommended_next_target_changed"])
        self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in report["priority_actions"]))
        self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in report["issue_drafts"]))

    def test_build_feedback_report_keeps_snapshot_risk_loud_when_inventory_trend_improves_but_missing_contracts_remain(self):
        report = build_feedback_report(
            {
                "overall_score": 93.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 96,
                    "code_health": 92,
                    "architecture_health": 97,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                "inventory_trend": {
                    "status": "improving",
                    "history_points": 4,
                    "missing_contract_delta": -1,
                    "uncategorized_root_script_delta": 0,
                    "recommended_next_target_changed": True,
                },
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 1,
                    "eligible_missing_contract_count": 1,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "non_governance_domain_script": 1,
                    },
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )

        self.assertEqual(report["inventory_summary"]["status"], "critical")
        self.assertEqual(report["inventory_trend"]["status"], "improving")
        self.assertTrue(report["inventory_trend"]["recommended_next_target_changed"])
        self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in report["priority_actions"]))
        self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in report["priority_actions"]))
        self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in report["issue_drafts"]))

    def test_build_feedback_report_keeps_uncategorized_snapshot_risk_loud_when_inventory_trend_improves(self):
        report = build_feedback_report(
            {
                "overall_score": 93.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 96,
                    "code_health": 92,
                    "architecture_health": 97,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_summary": {"recommended_next_target": None},
                "inventory_trend": {
                    "status": "improving",
                    "history_points": 4,
                    "missing_contract_delta": 0,
                    "uncategorized_root_script_delta": -1,
                    "recommended_next_target_changed": False,
                },
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "uncategorized_root_script": 1,
                    },
                },
                "recommendation": {"recommended_path": None},
            },
        )

        self.assertEqual(report["inventory_summary"]["status"], "attention")
        self.assertEqual(report["inventory_trend"]["status"], "improving")
        self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in report["priority_actions"]))
        self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in report["priority_actions"]))
        governance_draft = next(item for item in report["issue_drafts"] if self._issue_owner(item) == "quality-governance")
        self.assertEqual(governance_draft["issue_body"]["summary"]["owner"], "quality-governance")
        self.assertIsNone(governance_draft["issue_body"]["inventory_trend"])
        self.assertTrue(
            any("未归类的根目录脚本补齐 observation 分类" in item["action"] for item in governance_draft["issue_body"]["action_items"])
        )

    def test_build_feedback_report_keeps_mixed_residual_risk_ordered_when_inventory_trend_improves(self):
        report = build_feedback_report(
            {
                "overall_score": 93.0,
                "grade": "A",
                "failed_dimensions": [],
                "dimension_scores": {
                    "gate_stability": 100,
                    "test_reliability": 100,
                    "logic_health": 96,
                    "code_health": 92,
                    "architecture_health": 97,
                },
            },
            {"trend": {"status": "stable", "score_delta": 0.0}},
            {
                "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                "inventory_trend": {
                    "status": "improving",
                    "history_points": 4,
                    "missing_contract_delta": -1,
                    "uncategorized_root_script_delta": -1,
                    "recommended_next_target_changed": True,
                },
            },
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 1,
                    "eligible_missing_contract_count": 1,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {
                        "uncategorized_root_script": 1,
                    },
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )

        self.assertEqual(report["inventory_summary"]["status"], "critical")
        self.assertEqual(report["inventory_trend"]["status"], "improving")
        governance_draft = next(item for item in report["issue_drafts"] if self._issue_owner(item) == "quality-governance")
        action_items = governance_draft["issue_body"]["action_items"]
        self.assertEqual(len(action_items), 2)
        self.assertEqual(action_items[0]["priority"], "P0")
        self.assertIn("补齐缺失合同的质量消费者", action_items[0]["action"])
        self.assertEqual(action_items[1]["priority"], "P1")
        self.assertIn("未归类的根目录脚本补齐 observation 分类", action_items[1]["action"])
        self.assertEqual(governance_draft["issue_body"]["inventory_context"]["status"], "improving")
        self.assertIsNone(governance_draft["issue_body"]["inventory_trend"])

    def test_build_feedback_report_locks_owner_notification_order_for_json_markdown_issue_drafts_and_issue_index(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = build_feedback_report(
                {
                    "overall_score": 91.0,
                    "grade": "A",
                    "failed_dimensions": [],
                    "dimension_scores": {
                        "gate_stability": 100,
                        "test_reliability": 100,
                        "logic_health": 81,
                        "code_health": 84,
                        "architecture_health": 80,
                    },
                },
                {"trend": {"status": "stable", "score_delta": 0.0}},
                {
                    "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                    "inventory_trend": {
                        "status": "regressing",
                        "history_points": 6,
                        "missing_contract_delta": 1,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": True,
                    },
                },
                inventory_report={
                    "analysis_summary": {
                        "scanned_consumer_count": 3,
                        "missing_contract_count": 0,
                        "eligible_missing_contract_count": 0,
                        "root_script_observation_count": 1,
                        "root_script_observation_category_counts": {
                            "non_governance_domain_script": 1,
                        },
                    },
                    "recommendation": {"recommended_path": None},
                },
            )

            owner_notifications = report["owner_notifications"]
            self.assertEqual(
                [item["owner"] for item in owner_notifications],
                ["architecture-maintainers", "module-owners", "quality-governance"],
            )
            self.assertEqual(
                [item["dimension"] for item in owner_notifications[0]["todos"]],
                ["architecture_health", "logic_health"],
            )
            self.assertEqual(
                [item["dimension"] for item in owner_notifications[2]["todos"]],
                ["quality_consumer_inventory_trend"],
            )
            self.assertEqual(
                [self._issue_owner(item) for item in report["issue_drafts"]],
                ["architecture-maintainers", "module-owners", "quality-governance"],
            )

            exported = export_feedback_report(
                report,
                root / "output" / "quality-feedback.json",
                root / "output" / "quality-feedback.md",
                root / "output" / "quality-feedback-issues",
                root / "output" / "quality-feedback-issues.json",
            )
            markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")

            self.assertEqual(
                [item["owner"] for item in exported["owner_notifications"]],
                ["architecture-maintainers", "module-owners", "quality-governance"],
            )
            issue_index = json.loads((root / "output" / "quality-feedback-issues.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [self._issue_owner(item) for item in issue_index["items"]],
                ["architecture-maintainers", "module-owners", "quality-governance"],
            )
            self.assertNotIn("issue_drafts", exported)
            self.assertNotIn("report_metadata", issue_index)
            self._assert_removed_flat_issue_metadata(exported["report_metadata"], "issue_draft")
            self._assert_removed_issue_reference_metadata(
                exported["report_metadata"],
                [
                    "issue_draft_files",
                    "issue_draft_owners",
                    "issue_draft_titles",
                    "issue_draft_templates",
                    "issue_draft_labels",
                    "issue_draft_index_positions",
                    "issue_draft_bodies",
                ],
            )
            self.assertNotIn("issue_draft_count", exported["analysis_summary"])
            self.assertIn("## Artifact References", markdown)
            self.assertIn(
                "- Feedback JSON: {0}".format(exported["report_metadata"]["output_path"]),
                markdown,
            )
            self.assertIn(
                "- Feedback Markdown: {0}".format(exported["report_metadata"]["markdown_path"]),
                markdown,
            )
            self.assertIn(
                "- Issue Index: {0}".format(exported["report_metadata"]["issue_index_path"]),
                markdown,
            )
            self.assertIn(
                "- Issue Directory: {0}".format(exported["report_metadata"]["issue_dir"]),
                markdown,
            )
            self.assertIn(
                "  - {0}".format(self._issue_reference(issue_index["items"][0], "issue_draft_file", "")),
                markdown,
            )
            self.assertLess(markdown.index("- architecture-maintainers: 2 items"), markdown.index("- module-owners: 1 items"))
            self.assertLess(markdown.index("- module-owners: 1 items"), markdown.index("- quality-governance: 1 items"))
            self.assertLess(markdown.index("  - [P1] architecture_health"), markdown.index("  - [P1] logic_health"))

            architecture_draft = (root / "output" / "quality-feedback-issues" / "quality-action-architecture-maintainers.md").read_text(encoding="utf-8")
            self._assert_issue_body_markdown_matches_item(architecture_draft, issue_index["items"][0])
            self.assertLess(
                architecture_draft.index("- [P1] architecture_health: 保持依赖图与架构约束一致。"),
                architecture_draft.index("- [P1] logic_health: 清理逻辑类风险并补充结构性约束。"),
            )

    def test_build_feedback_report_critical(self):
        report = build_feedback_report(
            {
                "overall_score": 72.0,
                "grade": "C",
                "failed_dimensions": ["test_reliability"],
                "dimension_scores": {
                    "gate_stability": 80,
                    "test_reliability": 50,
                    "logic_health": 75,
                    "code_health": 70,
                    "architecture_health": 85,
                },
            },
            {"trend": {"status": "regressing", "score_delta": -2.5}},
            {},
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 3,
                    "missing_contract_count": 1,
                    "root_script_observation_count": 0,
                    "root_script_observation_category_counts": {},
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )
        self.assertEqual(report["feedback_level"], "critical")
        self.assertGreaterEqual(len(report["priority_actions"]), 1)
        self.assertGreaterEqual(len(report["owner_notifications"]), 1)
        self.assertGreaterEqual(len(report["issue_drafts"]), 1)
        self.assertTrue(any(item["owner"] == "qa-engineering" for item in report["owner_notifications"]))
        self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in report["priority_actions"]))
        first_draft = report["issue_drafts"][0]
        self.assertIn("issue_body", first_draft)
        self.assertNotIn("template", first_draft)
        self.assertNotIn("output_file", first_draft)

    def test_build_feedback_report_includes_governance_metadata(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            config_path.write_text(
                "governance:\n"
                "  quality_feedback:\n"
                "    minimum_stable_overall_score: 85.0\n"
                "    export_contract_version: \"d77.v1\"\n",
                encoding="utf-8",
            )
            report = build_feedback_report(
                {
                    "overall_score": 91.0,
                    "grade": "A",
                    "failed_dimensions": [],
                    "dimension_scores": {"gate_stability": 100, "code_health": 88},
                },
                {"trend": {"status": "stable", "score_delta": 0.0}},
                {},
                config_path,
                {"analysis_summary": {"missing_contract_count": 0, "root_script_observation_category_counts": {}}},
            )

        self.assertIn("metadata", report)
        self.assertIn("report_metadata", report)
        self.assertIn("analysis_summary", report)
        self.assertIn("failed_operations", report)
        self.assertEqual(report["report_metadata"]["contract_version"], "d77.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "build_feedback_report")
        self.assertNotIn("issue_draft_count", report["analysis_summary"])

    def test_export_feedback_report_updates_export_phase(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = {
                "timestamp": "2026-03-29T00:00:00+00:00",
                "feedback_level": "healthy",
                "headline": "ok",
                "overall_score": 95.0,
                "grade": "A",
                "trend_status": "stable",
                "trend_delta": 0.0,
                "failed_dimensions": [],
                "dimension_feedback": [],
                "priority_actions": [],
                "owner_notifications": [],
                "issue_drafts": [],
                "acknowledgements": ["x"],
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["build_feedback_report"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "build_feedback_report",
                },
                "failed_operations": [],
                "report_metadata": {"contract_version": "d77.v1"},
            }

            exported = export_feedback_report(
                report,
                root / "output" / "quality-feedback.json",
                root / "output" / "quality-feedback.md",
                root / "output" / "quality-feedback-issues",
                root / "output" / "quality-feedback-issues.json",
            )

            self.assertEqual(exported["metadata"]["last_completed_phase"], "export_quality_feedback_report")
            self.assertEqual(exported["report_metadata"]["contract_version"], "d77.v1")
            self.assertTrue((root / "output" / "quality-feedback.json").exists())
            self.assertTrue((root / "output" / "quality-feedback.md").exists())
            self.assertTrue((root / "output" / "quality-feedback-issues.json").exists())
            self.assertNotIn("issue_index_payload", exported)
            self.assertNotIn("issue_drafts", exported)
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["output_path"],
                exported["report_metadata"]["output_path"],
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["markdown_path"],
                exported["report_metadata"]["markdown_path"],
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["issue_dir"],
                exported["report_metadata"]["issue_dir"],
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["issue_index"],
                exported["report_metadata"]["issue_index_path"],
            )
            self.assertNotIn("issue_draft_count", exported["metadata"]["phase_history"][-1]["details"])
            markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            feedback_json = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            issue_index = json.loads((root / "output" / "quality-feedback-issues.json").read_text(encoding="utf-8"))
            self.assertNotIn("issue_index_payload", feedback_json)
            self.assertNotIn("issue_drafts", feedback_json)
            self.assertNotIn("issue_draft_count", feedback_json["analysis_summary"])
            self.assertNotIn("issue_draft_count", feedback_json["metadata"]["phase_history"][-1]["details"])
            self.assertIn(
                "- Feedback JSON: {0}".format(exported["report_metadata"]["output_path"]),
                markdown,
            )
            self.assertIn(
                "- Issue Index: {0}".format(exported["report_metadata"]["issue_index_path"]),
                markdown,
            )
            self.assertNotIn("report_metadata", issue_index)
            self._assert_removed_issue_reference_metadata(
                exported["report_metadata"],
                ["issue_draft_bodies"],
            )
            self._assert_removed_issue_reference_metadata(
                exported["report_metadata"],
                [
                    "issue_draft_files",
                    "issue_draft_owners",
                    "issue_draft_titles",
                    "issue_draft_templates",
                    "issue_draft_labels",
                    "issue_draft_index_positions",
                    "issue_draft_bodies",
                ],
            )
            self._assert_removed_flat_issue_metadata(exported["report_metadata"], "issue_draft")


if __name__ == "__main__":
    unittest.main()
