import unittest

from tools.quality_assessment import (
    AssessmentThresholds,
    assess_quality_metrics,
    metrics_from_gate_results,
)


class TestQualityAssessment(unittest.TestCase):
    def test_metrics_from_gate_results(self):
        metrics = metrics_from_gate_results(
            [
                {"name": "logic_checks", "success": True, "metrics": {"issue_count": 2, "error_count": 0}},
                {"name": "code_quality", "success": True, "metrics": {"issue_count": 10, "error_count": 0, "warning_count": 5}},
                {"name": "dependency_graph", "success": True, "metrics": {}},
                {"name": "quality_unit_tests", "success": True, "metrics": {}},
            ]
        )
        self.assertGreaterEqual(metrics["gate_stability"], 0.9)
        self.assertGreaterEqual(metrics["test_reliability"], 1.0)
        self.assertGreaterEqual(metrics["architecture_health"], 1.0)

    def test_assess_quality_metrics_pass(self):
        report = assess_quality_metrics(
            {
                "gate_stability": 1.0,
                "test_reliability": 1.0,
                "logic_health": 0.95,
                "code_health": 0.90,
                "architecture_health": 1.0,
            },
            AssessmentThresholds(min_overall_score=85.0, min_dimension_score=70.0),
        )
        self.assertTrue(report["passed"])
        self.assertIn(report["grade"], {"A", "B"})

    def test_assess_quality_metrics_fail(self):
        report = assess_quality_metrics(
            {
                "gate_stability": 0.8,
                "test_reliability": 0.0,
                "logic_health": 0.5,
                "code_health": 0.4,
                "architecture_health": 1.0,
            },
            AssessmentThresholds(min_overall_score=85.0, min_dimension_score=70.0),
        )
        self.assertFalse(report["passed"])
        self.assertGreaterEqual(len(report["failed_dimensions"]), 1)


if __name__ == "__main__":
    unittest.main()