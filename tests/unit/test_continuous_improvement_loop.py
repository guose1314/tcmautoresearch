import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.continuous_improvement_loop import build_cycle_report, export_cycle_report


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
        self.assertEqual(report["inventory_focus"]["trend_status"], "none")

    def test_build_cycle_report_adds_inventory_followup_actions_from_archive_history(self):
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
        archive_history = [
            {
                "inventory_summary": {
                    "missing_contract_count": 2,
                    "root_script_observation_category_counts": {"uncategorized_root_script": 1},
                    "recommended_next_target": "tools/missing_consumer.py",
                },
                "inventory_trend": {
                    "status": "regressing",
                    "history_points": 3,
                    "recommended_next_target_changed": True,
                },
            }
        ]

        report = build_cycle_report(assessment, [], archive_history=archive_history)

        self.assertEqual(report["inventory_focus"]["trend_status"], "regressing")
        self.assertGreaterEqual(len(report["inventory_focus"]["actions"]), 2)
        self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in report["action_backlog"]))
        self.assertEqual(report["next_cycle_targets"]["target_inventory_missing_contract_count"], 0)
        self.assertEqual(report["next_cycle_targets"]["inventory_recommended_next_target"], "tools/missing_consumer.py")

    def test_build_cycle_report_includes_governance_metadata(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            config_path.write_text(
                "governance:\n"
                "  continuous_improvement:\n"
                "    minimum_stable_overall_score: 85.0\n"
                "    export_contract_version: \"d66.v1\"\n",
                encoding="utf-8",
            )
            report = build_cycle_report(
                {
                    "overall_score": 91.0,
                    "grade": "A",
                    "passed": True,
                    "dimension_scores": {"code_health": 88.0, "logic_health": 95.0},
                    "failed_dimensions": [],
                },
                [],
                config_path,
            )

        self.assertIn("metadata", report)
        self.assertIn("report_metadata", report)
        self.assertIn("analysis_summary", report)
        self.assertIn("failed_operations", report)
        self.assertEqual(report["report_metadata"]["contract_version"], "d66.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "build_cycle_report")
        self.assertIn("inventory_trend_status", report["analysis_summary"])

    def test_export_cycle_report_updates_export_phase_and_history(self):
        with TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "quality-history.jsonl"
            output_path = Path(tmp) / "continuous-improvement.json"
            report = {
                "current_snapshot": {
                    "timestamp": "2026-03-29T00:00:00+00:00",
                    "overall_score": 90.0,
                    "grade": "A",
                    "passed": True,
                    "dimension_scores": {"code_health": 88.0},
                    "failed_dimensions": [],
                },
                "trend": {"status": "stable", "score_delta": 0.0, "history_points": 1},
                "action_backlog": [{"priority": "P1", "dimension": "code_health", "action": "continue"}],
                "next_cycle_targets": {"target_overall_score": 92.0, "focus_dimensions": ["code_health"], "max_new_warnings": 0},
                "inventory_focus": {"trend_status": "none", "summary": {}, "trend": {}, "actions": []},
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["build_cycle_report"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "build_cycle_report",
                },
                "failed_operations": [],
                "report_metadata": {"contract_version": "d66.v1"},
            }

            exported = export_cycle_report(report, history_path, output_path)

            self.assertTrue(output_path.exists())
            self.assertTrue(history_path.exists())
            self.assertEqual(exported["metadata"]["last_completed_phase"], "export_continuous_improvement_report")
            self.assertEqual(exported["report_metadata"]["contract_version"], "d66.v1")
            self.assertEqual(exported["report_metadata"]["artifact_reference_labels"], ["history", "output"])
            self.assertEqual(
                exported["report_metadata"]["artifact_reference_paths"],
                [
                    str(history_path).replace("\\", "/"),
                    str(output_path).replace("\\", "/"),
                ],
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["history_path"],
                exported["report_metadata"]["history_path"],
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["output_path"],
                exported["report_metadata"]["output_path"],
            )


if __name__ == "__main__":
    unittest.main()