import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import run_cycle_demo


class TestCycleDemoContract(unittest.TestCase):
    def test_run_iteration_cycle_includes_governance_contract(self):
        original_execute = run_cycle_demo.execute_real_module_pipeline
        try:
            run_cycle_demo.execute_real_module_pipeline = lambda input_data, modules=None, manage_module_lifecycle=False: [
                {
                    "module": "DemoModule",
                    "status": "completed",
                    "execution_time": 0.01,
                    "timestamp": "2026-03-29T00:00:00",
                    "input_data": input_data,
                    "output_data": {"result": "ok"},
                    "quality_metrics": {"completeness": 0.9, "accuracy": 0.92, "consistency": 0.91},
                }
            ]

            result = run_cycle_demo.run_iteration_cycle(
                1,
                {"raw_text": "demo", "metadata": {"source": "unit-test"}},
                max_iterations=2,
                shared_modules=[],
                governance_config={"export_contract_version": "d58.v1", "minimum_stable_quality_score": 0.85, "persist_failed_operations": True},
            )

            self.assertEqual(result["status"], "completed")
            self.assertIn("metadata", result)
            self.assertIn("analysis_summary", result)
            self.assertIn("failed_operations", result)
            self.assertEqual(result["metadata"]["last_completed_phase"], "assemble_iteration_cycle_summary")
            self.assertEqual(result["analysis_summary"]["module_count"], 1)
            self.assertEqual(result["analysis_summary"]["failed_operation_count"], 0)
        finally:
            run_cycle_demo.execute_real_module_pipeline = original_execute

    def test_run_full_cycle_demo_exports_governed_report(self):
        original_build = run_cycle_demo.build_real_modules
        original_init = run_cycle_demo.initialize_real_modules
        original_cleanup = run_cycle_demo.cleanup_real_modules
        original_iteration = run_cycle_demo.run_iteration_cycle
        try:
            run_cycle_demo.build_real_modules = lambda: []
            run_cycle_demo.initialize_real_modules = lambda modules: None
            run_cycle_demo.cleanup_real_modules = lambda modules: None
            run_cycle_demo.run_iteration_cycle = lambda iteration_number, input_data, max_iterations=5, shared_modules=None, governance_config=None: {
                "iteration_id": f"iter_{iteration_number}",
                "iteration_number": iteration_number,
                "status": "completed",
                "start_time": "2026-03-29T00:00:00",
                "end_time": "2026-03-29T00:00:01",
                "duration": 0.1,
                "modules": [],
                "quality_metrics": {"avg_completeness": 0.91},
                "confidence_scores": {},
                "academic_insights": [],
                "recommendations": [],
                "metadata": {"last_completed_phase": "assemble_iteration_cycle_summary"},
                "failed_operations": [],
                "analysis_summary": {"module_count": 0, "failed_operation_count": 0},
            }

            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                config_path = root / "config.yml"
                output_path = root / "output" / "cycle-demo-report.json"
                config_path.write_text(
                    "governance:\n"
                    "  cycle_demo:\n"
                    "    minimum_stable_quality_score: 0.85\n"
                    "    export_contract_version: \"d58.v1\"\n",
                    encoding="utf-8",
                )

                result = run_cycle_demo.run_full_cycle_demo(
                    max_iterations=2,
                    sample_data=["小柴胡汤方：柴胡半斤。"],
                    config_path=str(config_path),
                    output_path=str(output_path),
                )

                self.assertTrue(output_path.exists())
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                self.assertEqual(result["report_metadata"]["contract_version"], "d58.v1")
                self.assertEqual(payload["report_metadata"]["contract_version"], "d58.v1")
                self.assertEqual(payload["metadata"]["last_completed_phase"], "export_cycle_demo_report")
                self.assertIn("analysis_summary", payload)
                self.assertIn("failed_operations", payload)
                self.assertEqual(payload["analysis_summary"]["iteration_count"], 2)
        finally:
            run_cycle_demo.build_real_modules = original_build
            run_cycle_demo.initialize_real_modules = original_init
            run_cycle_demo.cleanup_real_modules = original_cleanup
            run_cycle_demo.run_iteration_cycle = original_iteration


if __name__ == "__main__":
    unittest.main()