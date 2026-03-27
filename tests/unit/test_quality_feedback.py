import unittest

from tools.quality_feedback import build_feedback_report


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


if __name__ == "__main__":
    unittest.main()
