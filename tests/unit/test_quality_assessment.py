import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.quality_assessment import (
    AssessmentThresholds,
    assess_from_gate_results,
    assess_quality_metrics,
    export_assessment_report,
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

    def test_metrics_from_gate_results_warning_only_code_quality_stays_passable(self):
        metrics = metrics_from_gate_results(
            [
                {"name": "logic_checks", "success": True, "metrics": {"issue_count": 1, "error_count": 0}},
                {"name": "code_quality", "success": True, "metrics": {"issue_count": 54, "error_count": 0, "warning_count": 54}},
                {"name": "dependency_graph", "success": True, "metrics": {}},
                {"name": "quality_unit_tests", "success": True, "metrics": {}},
            ]
        )

        self.assertGreaterEqual(metrics["code_health"], 0.7)

    def test_assess_quality_metrics_passes_when_only_warning_debt_exists(self):
        report = assess_quality_metrics(
            {
                "gate_stability": 1.0,
                "test_reliability": 1.0,
                "logic_health": 1.0,
                "code_health": 0.75,
                "architecture_health": 1.0,
            },
            AssessmentThresholds(min_overall_score=85.0, min_dimension_score=70.0),
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["failed_dimensions"], [])

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

    def test_assess_from_gate_results_includes_governance_metadata(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            config_path.write_text(
                "quality_assessment:\n"
                "  min_overall_score: 80\n"
                "  min_dimension_score: 70\n"
                "  export_contract_version: \"d49.v1\"\n",
                encoding="utf-8",
            )
            report = assess_from_gate_results(
                [
                    {"name": "logic_checks", "success": True, "metrics": {"issue_count": 0, "error_count": 0}},
                    {"name": "code_quality", "success": True, "metrics": {"issue_count": 10, "error_count": 0, "warning_count": 3}},
                    {"name": "dependency_graph", "success": True, "metrics": {}},
                    {"name": "quality_unit_tests", "success": True, "metrics": {"return_code": 0}},
                ],
                config_path,
            )

        self.assertIn("metadata", report)
        self.assertIn("report_metadata", report)
        self.assertIn("analysis_summary", report)
        self.assertIn("failed_operations", report)
        self.assertEqual(report["report_metadata"]["contract_version"], "d49.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "assess_quality_metrics")

    def test_export_assessment_report_updates_export_phase(self):
        with TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "quality-assessment.json"
            report = {
                "passed": True,
                "overall_score": 95.0,
                "grade": "A",
                "failed_dimensions": [],
                "thresholds": {"min_overall_score": 85.0, "min_dimension_score": 70.0},
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["assess_quality_metrics"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "assess_quality_metrics",
                },
                "failed_operations": [],
                "report_metadata": {"contract_version": "d49.v1"},
            }

            exported = export_assessment_report(report, output_path)

            self.assertTrue(output_path.exists())
            self.assertEqual(exported["metadata"]["last_completed_phase"], "export_assessment_report")
            self.assertEqual(exported["report_metadata"]["contract_version"], "d49.v1")
            self.assertEqual(
                exported["report_metadata"]["output_path"],
                str(output_path).replace("\\", "/"),
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["output_path"],
                exported["report_metadata"]["output_path"],
            )


if __name__ == "__main__":
    unittest.main()