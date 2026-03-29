import json
import os
import tempfile
import unittest

from src.test.automated_tester import AutomatedTester, TestPriority, TestType


class TestAutomatedTesterQuality(unittest.TestCase):
    def test_automated_tester_tracks_phase_history_and_analysis_summary(self):
        tester = AutomatedTester({"minimum_stable_pass_rate": 0.8, "export_contract_version": "d35.v1"})
        tester.add_test_suite(
            "stable-suite",
            [
                {
                    "name": "passes",
                    "type": TestType.UNIT,
                    "priority": TestPriority.HIGH,
                    "function": lambda context: {"success": True, "confidence": 0.91, "academic_relevance": 0.87},
                }
            ],
            test_type=TestType.UNIT,
            test_priority=TestPriority.HIGH,
        )
        suite_id = next(iter(tester.test_suites))

        report = tester.run_test_suite(suite_id, {"source": "unit-test"})
        performance_report = tester.get_test_performance_report()

        self.assertEqual(report["analysis_summary"]["suite_status"], "stable")
        self.assertEqual(performance_report["analysis_summary"]["status"], "stable")
        self.assertEqual(
            [phase["phase"] for phase in performance_report["metadata"]["phase_history"]],
            ["add_test_suite", "run_test_suite"],
        )
        self.assertEqual(performance_report["metadata"]["completed_phases"][-1], "run_test_suite")
        self.assertEqual(performance_report["analysis_summary"]["last_completed_phase"], "run_test_suite")
        self.assertEqual(performance_report["report_metadata"]["contract_version"], "d35.v1")
        self.assertEqual(performance_report["report_metadata"]["final_status"], "completed")

    def test_automated_tester_export_uses_json_safe_contract(self):
        tester = AutomatedTester({"export_contract_version": "d35.v1"})
        tester.add_test_suite(
            "export-suite",
            [
                {
                    "name": "json-safe",
                    "function": lambda context: {"success": True, "confidence": 0.9, "academic_relevance": 0.85},
                }
            ],
        )
        tester.run_all_tests({"source": "export-test"})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "automated-tester.json")
            exported = tester.export_test_results(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d35.v1")
        self.assertEqual(payload["test_suites"][0]["test_cases"][0]["function_name"], "<lambda>")
        self.assertEqual(payload["test_results"][0]["status"], "passed")
        self.assertIn("report_metadata", payload)
        self.assertIn("metadata", payload)

    def test_automated_tester_failure_tracks_failed_phase(self):
        tester = AutomatedTester({"export_contract_version": "d35.v1"})

        with self.assertRaises(ValueError):
            tester.run_test_suite("missing-suite", {"source": "failure-test"})

        report = tester.get_test_performance_report()
        self.assertEqual(report["metadata"]["failed_phase"], "run_test_suite")
        self.assertEqual(report["analysis_summary"]["failed_operation_count"], 1)
        self.assertEqual(report["metadata"]["phase_history"][-1]["status"], "failed")
        self.assertIn("duration_seconds", report["failed_operations"][0])

    def test_automated_tester_cleanup_keeps_shared_executor_available(self):
        tester1 = AutomatedTester({"export_contract_version": "d35.v1"})
        tester2 = AutomatedTester()

        self.assertIs(tester1.executor, tester2.executor)
        executor = tester1.executor

        cleaned = tester1.cleanup()

        self.assertTrue(cleaned)
        self.assertFalse(getattr(executor, "_shutdown", False))
        self.assertEqual(tester1.get_test_performance_report()["metadata"]["final_status"], "cleaned")


if __name__ == "__main__":
    unittest.main()