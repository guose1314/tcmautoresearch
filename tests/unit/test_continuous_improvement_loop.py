import unittest

from tools.continuous_improvement_loop import build_cycle_report


class TestContinuousImprovementLoop(unittest.TestCase):
    def test_build_cycle_report_with_failed_dimensions(self):
        assessment = {
            "overall_score": 78.5,
            "grade": "C",
            "passed": False,
            "dimension_scores": {
                "gate_stability": 80.0,
                "test_reliability": 60.0,
                "logic_health": 75.0,
                "code_health": 68.0,
                "architecture_health": 95.0,
            },
            "failed_dimensions": ["test_reliability", "code_health"],
        }
        history = [{"overall_score": 82.0}]

        report = build_cycle_report(assessment, history)
        self.assertEqual(report["trend"]["status"], "regressing")
        self.assertEqual(len(report["action_backlog"]), 2)
        self.assertIn("target_overall_score", report["next_cycle_targets"])

    def test_build_cycle_report_without_failed_dimensions(self):
        assessment = {
            "overall_score": 95.0,
            "grade": "A",
            "passed": True,
            "dimension_scores": {
                "gate_stability": 100.0,
                "test_reliability": 98.0,
                "logic_health": 92.0,
                "code_health": 88.0,
                "architecture_health": 99.0,
            },
            "failed_dimensions": [],
        }

        report = build_cycle_report(assessment, [])
        self.assertEqual(report["trend"]["status"], "stable")
        self.assertGreaterEqual(len(report["action_backlog"]), 1)
        self.assertEqual(report["current_snapshot"]["grade"], "A")


if __name__ == "__main__":
    unittest.main()