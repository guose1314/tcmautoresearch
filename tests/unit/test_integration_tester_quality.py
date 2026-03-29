import json
import os
import tempfile
import unittest

from src.test.integration_tester import (
    IntegrationTestPriority,
    IntegrationTester,
    IntegrationTestType,
)


class TestIntegrationTesterQuality(unittest.TestCase):
    def test_integration_tester_tracks_phase_history_and_analysis_summary(self):
        tester = IntegrationTester({"minimum_stable_pass_rate": 0.8, "export_contract_version": "d24.v1"})
        integration_test = tester.add_integration_test(
            test_name="module-link",
            test_type=IntegrationTestType.MODULE_INTEGRATION,
            test_priority=IntegrationTestPriority.HIGH,
            description="module integration smoke",
            components_involved=["reader", "parser"],
            test_steps=[{"step": "run"}],
            expected_results={"integration_status": "successful"},
        )

        result = tester.run_integration_test(integration_test.test_id)
        report = tester.get_integration_performance_report()

        self.assertEqual(result.status.value, "passed")
        self.assertEqual(report["analysis_summary"]["status"], "stable")
        self.assertEqual(
            [phase["phase"] for phase in report["metadata"]["phase_history"]],
            ["add_integration_test", "run_integration_test"],
        )
        self.assertEqual(report["metadata"]["completed_phases"][-1], "run_integration_test")
        self.assertEqual(report["report_metadata"]["contract_version"], "d24.v1")

    def test_integration_tester_export_uses_json_safe_contract(self):
        tester = IntegrationTester({"export_contract_version": "d24.v1"})
        integration_test = tester.add_integration_test(
            test_name="academic-link",
            test_type=IntegrationTestType.ACADEMIC_INTEGRATION,
            test_priority=IntegrationTestPriority.CRITICAL,
            description="academic integration smoke",
            components_involved=["knowledge_graph", "reasoning"],
            test_steps=[{"step": "validate"}],
            expected_results={"academic_standards_met": True},
        )
        tester.run_integration_test(integration_test.test_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "integration-tester.json")
            exported = tester.export_integration_results(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d24.v1")
        self.assertEqual(payload["detailed_results"][0]["test_type"], "academic_integration")
        self.assertEqual(payload["detailed_results"][0]["status"], "passed")
        self.assertIn("analysis_summary", payload)

    def test_integration_tester_failure_tracks_failed_phase(self):
        tester = IntegrationTester({"export_contract_version": "d24.v1"})

        with self.assertRaises(ValueError):
            tester.run_integration_test("missing-test")

        report = tester.get_integration_performance_report()
        self.assertEqual(report["metadata"]["failed_phase"], "run_integration_test")
        self.assertEqual(report["analysis_summary"]["failed_operation_count"], 1)
        self.assertEqual(report["metadata"]["phase_history"][-1]["status"], "failed")

    def test_integration_tester_cleanup_keeps_shared_executor_available(self):
        tester1 = IntegrationTester()
        tester2 = IntegrationTester()

        self.assertIs(tester1.executor, tester2.executor)
        executor = tester1.executor

        cleaned = tester1.cleanup()

        self.assertTrue(cleaned)
        self.assertFalse(getattr(executor, "_shutdown", False))


if __name__ == "__main__":
    unittest.main()