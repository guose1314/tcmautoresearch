import unittest
import json
import os
import tempfile
from importlib.util import find_spec

from src.core import __all__ as core_all
from src.cycle.iteration_cycle import CycleStatus, IterationConfig, IterationCycle
from src.cycle.system_iteration import SystemIterationCycle
from src.cycle.test_driven_iteration import TestDrivenIterationManager


class TestCoreAndCycleQuality(unittest.TestCase):
    def test_core_exports_are_unique(self):
        self.assertEqual(len(core_all), len(set(core_all)))

    def test_iteration_cycle_reuses_global_executor(self):
        c1 = IterationCycle(IterationConfig(max_concurrent_tasks=2))
        c2 = IterationCycle(IterationConfig(max_concurrent_tasks=2))
        self.assertIs(c1.executor, c2.executor)

    def test_iteration_cycle_executor_with_different_max_concurrent_tasks(self):
        c1 = IterationCycle(IterationConfig(max_concurrent_tasks=1))
        c2 = IterationCycle(IterationConfig(max_concurrent_tasks=3))
        self.assertIsNotNone(c1.executor)
        self.assertIsNotNone(c2.executor)
    def test_iteration_manager_framework_registry_contains_expected_frameworks(self):
        manager = TestDrivenIterationManager()
        self.assertIn("unittest", manager.test_frameworks)
        self.assertIn("custom", manager.test_frameworks)

        has_pytest = find_spec("pytest") is not None
        if has_pytest:
            self.assertIn("pytest", manager.test_frameworks)

    def test_iteration_cycle_optimization_generates_ranked_actions(self):
        cycle = IterationCycle(
            IterationConfig(
                optimization_quality_threshold=0.8,
                optimization_confidence_threshold=0.8,
                max_optimization_actions=3,
            )
        )

        result = cycle.optimize_process(
            {
                "quality_metrics": {"quality_score": 0.62},
                "confidence_scores": {"entity": 0.71, "reasoning": 0.69},
            }
        )

        self.assertEqual(result["optimization_status"], "optimization_required")
        self.assertEqual(len(result["optimization_actions"]), 2)
        self.assertEqual(result["optimization_actions"][0]["priority"], "high")
        self.assertEqual(result["optimization_actions"][1]["priority"], "medium")
        self.assertEqual(result["optimization_summary"]["highest_priority"], "high")
        self.assertAlmostEqual(result["optimization_summary"]["quality_threshold"], 0.8)

    def test_iteration_cycle_optimization_handles_empty_analysis_results(self):
        cycle = IterationCycle(IterationConfig())

        result = cycle.optimize_process({})

        self.assertEqual(result["optimization_status"], "no_action_needed")
        self.assertEqual(result["optimization_actions"], [])
        self.assertEqual(result["optimization_summary"]["action_count"], 0)
        self.assertEqual(result["optimization_summary"]["highest_priority"], "none")

    def test_iteration_cycle_optimization_respects_max_actions(self):
        cycle = IterationCycle(
            IterationConfig(
                optimization_quality_threshold=0.9,
                optimization_confidence_threshold=0.95,
                max_optimization_actions=1,
            )
        )

        result = cycle.optimize_process(
            {
                "quality_metrics": {"quality_score": 0.6},
                "confidence_scores": {"entity": 0.7, "reasoning": 0.75},
            }
        )

        self.assertEqual(len(result["optimization_actions"]), 1)
        self.assertEqual(result["optimization_actions"][0]["action"], "process_optimization")

    def test_system_iteration_analysis_returns_stable_structures(self):
        cycle = SystemIterationCycle(
            {
                "max_system_recommendations": 5,
                "academic_insight_min_quality": 0.85,
            }
        )

        result = cycle._analyze_system_results(
            {},
            {
                "module_a": {"status": "completed", "quality_assessment": {"overall_quality": 0.82}, "confidence_scores": {"overall": 0.8}},
                "module_b": {"status": "failed", "error": "timeout"},
            },
            {
                "system_health": "healthy",
                "performance_score": 0.79,
                "reliability": 0.94,
                "quality_assurance": {
                    "academic_compliance": True,
                    "quality_metrics": {
                        "completeness": 0.91,
                        "accuracy": 0.88,
                        "consistency": 0.9,
                    },
                },
            },
        )

        self.assertIsInstance(result["system_insights"], list)
        self.assertIsInstance(result["academic_insights"], list)
        self.assertIsInstance(result["recommendations"], list)
        self.assertEqual(result["analysis_summary"]["failed_module_count"], 1)
        self.assertIn("module_b", result["analysis_summary"]["failed_modules"])

    def test_system_iteration_execute_persists_academic_insights_and_summary(self):
        cycle = SystemIterationCycle()
        cycle._execute_module_iterations = lambda context: {
            "module_a": {
                "status": "completed",
                "quality_assessment": {"overall_quality": 0.9},
                "confidence_scores": {"overall": 0.86},
            }
        }
        cycle._test_system_level = lambda context, module_results: {
            "system_health": "healthy",
            "performance_score": 0.9,
            "reliability": 0.97,
            "quality_assurance": {
                "academic_compliance": True,
                "quality_metrics": {
                    "completeness": 0.93,
                    "accuracy": 0.92,
                    "consistency": 0.94,
                },
            },
        }

        result = cycle.execute_system_iteration({})

        self.assertEqual(result.status, "completed")
        self.assertIsInstance(result.academic_insights, list)
        self.assertGreaterEqual(len(result.academic_insights), 1)
        self.assertIn("analysis_summary", result.metadata)
        self.assertEqual(result.metadata["analysis_summary"]["system_status"], "stable")

    def test_iteration_cycle_execute_records_phase_history_and_analysis_summary(self):
        cycle = IterationCycle(IterationConfig(confidence_threshold=0.7))
        cycle.generate_artifacts = lambda context: {"artifact_id": "a1", "quality_metrics": {"completeness": 0.9, "accuracy": 0.88, "consistency": 0.91}}
        cycle.test_artifacts = lambda artifacts: {"passed": True, "failures": [], "metrics": {"execution_time": 0.2, "memory_usage": 8.0}}
        cycle.repair_artifacts = lambda artifacts, test_results: []
        cycle.analyze_results = lambda artifacts, test_results, repair_actions: {
            "quality_metrics": {"overall_quality": 0.89, "quality_score": 0.89},
            "academic_insights": [{"title": "ok"}],
            "recommendations": [{"title": "keep"}],
            "confidence_scores": {"overall": 0.91},
            "analysis_summary": {"iteration_status": "stable", "quality_score": 0.89},
        }
        cycle.optimize_process = lambda analysis_results: {
            "optimization_actions": [],
            "optimization_summary": {"status": "no_action_needed"},
        }
        cycle.validate_results = lambda artifacts, analysis_results: {"validation_status": "passed"}

        result = cycle.execute_iteration({})

        self.assertEqual(result.status, CycleStatus.COMPLETED)
        self.assertEqual([phase["phase"] for phase in result.metadata["phase_history"]], ["generate", "test", "repair", "analyze", "optimize", "validate"])
        self.assertTrue(all(phase["status"] == "completed" for phase in result.metadata["phase_history"]))
        self.assertIn("analyze", result.metadata["phase_timings"])
        self.assertEqual(result.metadata["analysis_summary"]["iteration_status"], "stable")

    def test_system_iteration_failure_tracks_failed_phase(self):
        cycle = SystemIterationCycle()
        cycle._execute_module_iterations = lambda context: {"module_a": {"status": "completed"}}

        def raise_system_test_error(context, module_results):
            raise RuntimeError("system test failed")

        cycle._test_system_level = raise_system_test_error

        with self.assertRaises(RuntimeError):
            cycle.execute_system_iteration({})

        self.assertEqual(len(cycle.failed_iterations), 1)
        failed_result = cycle.failed_iterations[0]
        self.assertEqual(failed_result.metadata["failed_phase"], "test_system")
        self.assertEqual(failed_result.metadata["phase_history"][-1]["status"], "failed")
        self.assertEqual(failed_result.status, "failed")

    def test_iteration_cycle_export_results_serializes_status_as_string(self):
        cycle = IterationCycle()
        cycle.results.append(
            cycle.execute_iteration({})
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "iteration-results.json")
            exported = cycle.export_results(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d15.v1")
        self.assertIsInstance(payload["iteration_results"][0]["status"], str)
        self.assertEqual(payload["iteration_results"][0]["status"], "completed")
        self.assertIn("report_metadata", payload["cycle_summary"])

    def test_system_iteration_export_system_data_contains_failed_iterations_and_metadata(self):
        cycle = SystemIterationCycle()
        cycle._execute_module_iterations = lambda context: {"module_a": {"status": "completed", "quality_assessment": {"overall_quality": 0.91}, "confidence_scores": {"overall": 0.89}}}
        cycle._test_system_level = lambda context, module_results: {"system_health": "healthy", "performance_score": 0.88, "reliability": 0.95, "quality_assurance": {"academic_compliance": True, "quality_metrics": {"completeness": 0.92, "accuracy": 0.9, "consistency": 0.91}}}
        cycle.execute_system_iteration({})

        def raise_system_test_error(context, module_results):
            raise RuntimeError("system export test failure")

        cycle._test_system_level = raise_system_test_error
        with self.assertRaises(RuntimeError):
            cycle.execute_system_iteration({})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "system-data.json")
            exported = cycle.export_system_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d15.v1")
        self.assertEqual(len(payload["failed_iterations"]), 1)
        self.assertIn("report_metadata", payload["system_report"])


if __name__ == "__main__":
    unittest.main()
