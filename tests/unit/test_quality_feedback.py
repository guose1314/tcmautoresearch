import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.quality_feedback import build_feedback_report, export_feedback_report


class TestQualityFeedback(unittest.TestCase):
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
            {},
        )
        self.assertEqual(report["feedback_level"], "healthy")
        self.assertGreaterEqual(report["overall_score"], 90.0)

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
        )
        self.assertEqual(report["feedback_level"], "critical")
        self.assertGreaterEqual(len(report["priority_actions"]), 1)
        self.assertGreaterEqual(len(report["owner_notifications"]), 1)
        self.assertGreaterEqual(len(report["issue_drafts"]), 1)
        self.assertTrue(any(item["owner"] == "qa-engineering" for item in report["owner_notifications"]))
        first_draft = report["issue_drafts"][0]
        self.assertIn("template", first_draft)
        self.assertIn("output_file", first_draft)

    def test_build_feedback_report_includes_governance_metadata(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            config_path.write_text(
                "governance:\n"
                "  quality_feedback:\n"
                "    minimum_stable_overall_score: 85.0\n"
                "    export_contract_version: \"d52.v1\"\n",
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
            )

        self.assertIn("metadata", report)
        self.assertIn("report_metadata", report)
        self.assertIn("analysis_summary", report)
        self.assertIn("failed_operations", report)
        self.assertEqual(report["report_metadata"]["contract_version"], "d52.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "build_feedback_report")

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
                "report_metadata": {"contract_version": "d52.v1"},
            }

            exported = export_feedback_report(
                report,
                root / "output" / "quality-feedback.json",
                root / "output" / "quality-feedback.md",
                root / "output" / "quality-feedback-issues",
                root / "output" / "quality-feedback-issues.json",
            )

            self.assertEqual(exported["metadata"]["last_completed_phase"], "export_quality_feedback_report")
            self.assertEqual(exported["report_metadata"]["contract_version"], "d52.v1")
            self.assertTrue((root / "output" / "quality-feedback.json").exists())
            self.assertTrue((root / "output" / "quality-feedback.md").exists())
            self.assertTrue((root / "output" / "quality-feedback-issues.json").exists())


if __name__ == "__main__":
    unittest.main()
