import json
import os
import tempfile
import unittest
from importlib.util import find_spec

from src.core import __all__ as core_all
from src.core.architecture import ModuleInfo, ModuleType, SystemArchitecture
from src.core.module_base import BaseModule, ModuleContext, ModuleStatus
from src.cycle.fixing_stage import FixingStage
from src.cycle.iteration_cycle import CycleStatus, IterationConfig, IterationCycle
from src.cycle.module_iteration import ModuleIterationCycle
from src.cycle.system_iteration import SystemIterationCycle
from src.cycle.test_driven_iteration import TestDrivenIterationManager


class DemoGovernedBaseModule(BaseModule):
    def __init__(self, module_name="demo", config=None, fail_execute=False):
        super().__init__(module_name, config)
        self.fail_execute = fail_execute

    def _do_initialize(self) -> bool:
        return True

    def _do_execute(self, context):
        if self.fail_execute:
            raise RuntimeError("base module execution failed")
        return {
            "success": True,
            "quality_score": 0.92,
            "performance_score": 0.87,
            "academic_relevance": 0.9,
            "payload": context,
        }

    def _do_cleanup(self) -> bool:
        return True


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

    def test_base_module_tracks_phase_history_and_analysis_summary(self):
        module = DemoGovernedBaseModule(config={"export_contract_version": "d46.v1", "minimum_stable_success_rate": 0.5})

        self.assertTrue(module.initialize())
        result = module.execute({"source": "unit-test"})
        report = module.get_performance_report()

        self.assertTrue(result["success"])
        self.assertEqual([phase["phase"] for phase in report["metadata"]["phase_history"]], ["initialize", "execute"])
        self.assertEqual(report["analysis_summary"]["status"], "stable")
        self.assertEqual(report["analysis_summary"]["final_status"], "completed")
        self.assertEqual(report["report_metadata"]["contract_version"], "d46.v1")
        self.assertEqual(report["metadata"]["last_completed_phase"], "execute")

    def test_base_module_failure_tracks_failed_operation(self):
        module = DemoGovernedBaseModule(config={"export_contract_version": "d46.v1"}, fail_execute=True)
        self.assertTrue(module.initialize())

        with self.assertRaises(RuntimeError):
            module.execute({"source": "failure-test"})

        report = module.get_performance_report()
        self.assertEqual(report["analysis_summary"]["status"], "needs_followup")
        self.assertEqual(report["failed_operations"][0]["operation"], "execute")
        self.assertEqual(report["failed_operations"][0]["details"]["module_name"], "demo")
        self.assertEqual(report["metadata"]["failed_phase"], "execute")

    def test_base_module_export_uses_json_safe_contract(self):
        module = DemoGovernedBaseModule(config={"export_contract_version": "d46.v1"})
        self.assertTrue(module.initialize())
        module.execute({"source": "export-test"})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "base-module-report.json")
            exported = module.export_module_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d46.v1")
        self.assertEqual(payload["metadata"]["last_completed_phase"], "export_module_data")
        self.assertIn("failed_operations", payload)
        self.assertIn("report_metadata", payload["performance_report"])

    def test_base_module_cleanup_resets_runtime_state(self):
        module = DemoGovernedBaseModule(config={"export_contract_version": "d46.v1"})
        executor = module.executor
        self.assertTrue(module.initialize())
        module.execute({"source": "cleanup-test"})

        cleaned = module.cleanup()
        report = module.get_performance_report()

        self.assertTrue(cleaned)
        self.assertFalse(getattr(executor, "_shutdown", False))
        self.assertEqual(report["metadata"]["final_status"], "cleaned")
        self.assertEqual(report["message"], "没有执行历史记录")

    def test_test_driven_iteration_tracks_phase_history_and_analysis_summary(self):
        manager = TestDrivenIterationManager({"minimum_stable_pass_rate": 0.85, "export_contract_version": "d33.v1"})
        manager.add_test_suite(
            "core-suite",
            [
                {
                    "name": "smoke-test",
                    "type": "academic_test",
                    "framework": "custom",
                    "function": lambda context: {"ok": True},
                }
            ],
        )

        iteration = manager.run_test_driven_iteration({})

        self.assertEqual(iteration.status, "completed")
        self.assertEqual([phase["phase"] for phase in iteration.metadata["phase_history"]], ["execute_tests", "validate_results", "analyze_results"])
        self.assertEqual(iteration.metadata["analysis_summary"]["iteration_status"], "stable")
        self.assertEqual(iteration.metadata["analysis_summary"]["final_status"], "completed")
        self.assertEqual(iteration.metadata["analysis_summary"]["failed_operation_count"], 0)
        self.assertGreaterEqual(iteration.confidence_scores["overall"], 0.0)
        self.assertEqual(manager.get_test_performance_report()["analysis_summary"]["status"], "stable")

    def test_test_driven_iteration_export_uses_json_safe_contract(self):
        manager = TestDrivenIterationManager({"export_contract_version": "d33.v1"})
        manager.add_test_suite(
            "export-suite",
            [
                {
                    "name": "json-safe",
                    "type": "validation_test",
                    "framework": "custom",
                    "function": lambda context: {"value": 1},
                }
            ],
        )
        manager.run_test_driven_iteration({})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "test-iteration.json")
            exported = manager.export_test_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d33.v1")
        self.assertEqual(payload["test_suites"]["export-suite"]["test_cases"][0]["function_name"], "<lambda>")
        self.assertIn("report_metadata", payload["test_performance_report"])
        self.assertIn("failed_operations", payload)
        self.assertEqual(payload["test_performance_report"]["analysis_summary"]["final_status"], "completed")

    def test_test_driven_iteration_failure_tracks_failed_phase(self):
        manager = TestDrivenIterationManager({"export_contract_version": "d33.v1"})
        manager.add_test_suite(
            "failure-suite",
            [
                {
                    "name": "will-fail",
                    "type": "validation_test",
                    "framework": "custom",
                    "function": lambda context: {"value": 0},
                }
            ],
        )

        original_validate = manager._validate_test_results

        def raise_validation_error(test_results):
            raise RuntimeError("validation phase failed")

        manager._validate_test_results = raise_validation_error

        with self.assertRaises(RuntimeError):
            manager.run_test_driven_iteration({})

        manager._validate_test_results = original_validate
        self.assertEqual(len(manager.failed_iterations), 1)
        failed_iteration = manager.failed_iterations[0]
        self.assertEqual(failed_iteration.metadata["failed_phase"], "validate_results")
        self.assertEqual(failed_iteration.metadata["phase_history"][-1]["status"], "failed")
        self.assertEqual(failed_iteration.metadata["analysis_summary"]["final_status"], "failed")
        self.assertEqual(manager.failed_operations[0]["operation"], "validate_results")
        self.assertEqual(manager.get_test_performance_report()["analysis_summary"]["status"], "needs_followup")

    def test_test_driven_iteration_cleanup_resets_runtime_state(self):
        manager = TestDrivenIterationManager({"export_contract_version": "d33.v1"})
        manager.add_test_suite(
            "cleanup-suite",
            [
                {
                    "name": "cleanup-test",
                    "type": "validation_test",
                    "framework": "custom",
                    "function": lambda context: {"ok": True},
                }
            ],
        )
        manager.run_test_driven_iteration({})

        cleaned = manager.cleanup()

        self.assertTrue(cleaned)
        self.assertEqual(manager.iteration_metadata["final_status"], "cleaned")
        self.assertEqual(manager.get_test_performance_report()["message"], "还没有执行任何测试驱动迭代")

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
        cycle = SystemIterationCycle({"export_contract_version": "d42.v1", "minimum_stable_quality": 0.85})
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
        self.assertEqual(result.metadata["analysis_summary"]["status"], "stable")
        self.assertEqual(result.metadata["analysis_summary"]["final_status"], "completed")
        self.assertEqual(result.metadata["analysis_summary"]["failed_operation_count"], 0)
        report = cycle.get_system_performance_report()
        self.assertEqual(report["report_metadata"]["contract_version"], "d42.v1")
        self.assertEqual(report["report_metadata"]["final_status"], "completed")
        self.assertEqual(report["metadata"]["final_status"], "completed")

    def test_iteration_cycle_execute_records_phase_history_and_analysis_summary(self):
        cycle = IterationCycle(IterationConfig(confidence_threshold=0.7, export_contract_version="d40.v1"))
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
        self.assertEqual(result.metadata["analysis_summary"]["final_status"], "completed")
        self.assertEqual(result.metadata["analysis_summary"]["failed_operation_count"], 0)
        self.assertEqual(cycle.get_cycle_summary()["report_metadata"]["contract_version"], "d40.v1")
        self.assertEqual(cycle.get_cycle_summary()["analysis_summary"]["status"], "stable")

    def test_iteration_cycle_failure_tracks_failed_phase_and_operation(self):
        cycle = IterationCycle(IterationConfig(export_contract_version="d40.v1"))
        cycle.generate_artifacts = lambda context: {"artifact_id": "broken"}

        def raise_test_error(artifacts):
            raise RuntimeError("test phase failed")

        cycle.test_artifacts = raise_test_error

        with self.assertRaises(RuntimeError):
            cycle.execute_iteration({})

        self.assertEqual(len(cycle.failed_iterations), 1)
        failed_result = cycle.failed_iterations[0]
        self.assertEqual(failed_result.metadata["failed_phase"], "test")
        self.assertEqual(failed_result.metadata["analysis_summary"]["final_status"], "failed")
        self.assertEqual(cycle.failed_operations[0]["operation"], "test")
        self.assertEqual(cycle.failed_operations[0]["details"]["iteration_id"], failed_result.iteration_id)
        self.assertEqual(cycle.failed_operations[0]["details"]["cycle_number"], failed_result.cycle_number)
        self.assertEqual(cycle.get_cycle_summary()["analysis_summary"]["status"], "needs_followup")

    def test_system_iteration_failure_tracks_failed_phase(self):
        cycle = SystemIterationCycle({"export_contract_version": "d42.v1"})
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
        self.assertEqual(failed_result.metadata["analysis_summary"]["final_status"], "failed")
        self.assertEqual(cycle.failed_operations[0]["operation"], "test_system")
        self.assertEqual(cycle.failed_operations[0]["details"]["iteration_id"], failed_result.iteration_id)
        self.assertEqual(cycle.failed_operations[0]["details"]["cycle_number"], failed_result.cycle_number)
        self.assertEqual(cycle.failed_operations[-1]["operation"], "execute_system_iteration")
        self.assertEqual(cycle.get_system_performance_report()["analysis_summary"]["status"], "needs_followup")

    def test_iteration_cycle_export_results_serializes_status_as_string(self):
        cycle = IterationCycle(IterationConfig(export_contract_version="d40.v1"))
        cycle.results.append(
            cycle.execute_iteration({"mock_mode": True})
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "iteration-results.json")
            exported = cycle.export_results(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d40.v1")
        self.assertIsInstance(payload["iteration_results"][0]["status"], str)
        self.assertEqual(payload["iteration_results"][0]["status"], "completed")
        self.assertIn("report_metadata", payload["cycle_summary"])
        self.assertIn("failed_operations", payload)
        self.assertEqual(payload["metadata"]["final_status"], "completed")
        self.assertEqual(payload["cycle_summary"]["analysis_summary"]["final_status"], "completed")

    def test_system_iteration_export_system_data_contains_failed_iterations_and_metadata(self):
        cycle = SystemIterationCycle({"export_contract_version": "d42.v1"})
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

        self.assertEqual(payload["report_metadata"]["contract_version"], "d42.v1")
        self.assertEqual(len(payload["failed_iterations"]), 1)
        self.assertIn("report_metadata", payload["system_report"])
        self.assertEqual(payload["failed_operations"][0]["operation"], "test_system")
        self.assertEqual(payload["failed_operations"][0]["details"]["iteration_id"], payload["failed_iterations"][0]["iteration_id"])
        self.assertIn("metadata", payload)
        self.assertEqual(payload["report_metadata"]["final_status"], "failed")
        self.assertEqual(payload["metadata"]["final_status"], "failed")

    def test_system_iteration_cleanup_resets_runtime_state(self):
        cycle = SystemIterationCycle({"export_contract_version": "d42.v1"})
        cycle._execute_module_iterations = lambda context: {"module_a": {"status": "completed", "quality_assessment": {"overall_quality": 0.91}, "confidence_scores": {"overall": 0.89}}}
        cycle._test_system_level = lambda context, module_results: {"system_health": "healthy", "performance_score": 0.88, "reliability": 0.95, "quality_assurance": {"academic_compliance": True, "quality_metrics": {"completeness": 0.92, "accuracy": 0.9, "consistency": 0.91}}}
        cycle.execute_system_iteration({})

        cleaned = cycle.cleanup()

        self.assertTrue(cleaned)
        self.assertEqual(cycle.system_metadata["final_status"], "cleaned")
        self.assertEqual(cycle.get_system_performance_report()["message"], "还没有执行任何系统迭代")

    def test_module_iteration_tracks_phase_history_and_summary(self):
        cycle = ModuleIterationCycle("entity_extraction", {"minimum_stable_quality": 0.85, "export_contract_version": "d43.v1"})
        cycle._generate_module_artifact = lambda context: {"artifact_id": "m1", "quality_metrics": {"completeness": 0.92, "accuracy": 0.9, "consistency": 0.91, "reliability": 0.89}}
        cycle._test_module_artifact = lambda artifacts: {"passed": True, "failures": [], "metrics": {"confidence_score": 0.87}}
        cycle._repair_module_artifact = lambda artifacts, test_results: []

        result = cycle.execute_module_iteration({})

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.recommendations, [])
        self.assertEqual([phase["phase"] for phase in result.metadata["phase_history"]], ["generate", "test", "repair", "analyze"])
        self.assertEqual(result.metadata["analysis_summary"]["module_status"], "stable")
        self.assertEqual(result.metadata["analysis_summary"]["final_status"], "completed")
        self.assertEqual(result.metadata["analysis_summary"]["failed_operation_count"], 0)
        self.assertAlmostEqual(result.quality_assessment["quality_score"], result.quality_assessment["overall_quality"])
        report = cycle.get_module_performance_report()
        self.assertEqual(report["analysis_summary"]["status"], "stable")
        self.assertEqual(report["report_metadata"]["contract_version"], "d43.v1")
        self.assertEqual(report["metadata"]["final_status"], "completed")

    def test_module_iteration_failure_tracks_failed_phase_and_operation(self):
        cycle = ModuleIterationCycle("entity_extraction", {"export_contract_version": "d43.v1"})
        cycle._generate_module_artifact = lambda context: {"artifact_id": "m1"}

        def raise_test_error(artifacts):
            raise RuntimeError("module test failed")

        cycle._test_module_artifact = raise_test_error

        with self.assertRaises(RuntimeError):
            cycle.execute_module_iteration({})

        self.assertEqual(len(cycle.failed_iterations), 1)
        failed_result = cycle.failed_iterations[0]
        self.assertEqual(failed_result.metadata["failed_phase"], "test")
        self.assertEqual(failed_result.metadata["analysis_summary"]["final_status"], "failed")
        self.assertEqual(cycle.failed_operations[0]["operation"], "test")
        self.assertEqual(cycle.failed_operations[0]["details"]["module_name"], "entity_extraction")
        self.assertEqual(cycle.failed_operations[0]["details"]["iteration_id"], failed_result.iteration_id)
        self.assertEqual(cycle.failed_operations[-1]["operation"], "execute_module_iteration")
        self.assertEqual(cycle.get_module_performance_report()["analysis_summary"]["status"], "needs_followup")

    def test_module_iteration_export_module_data_uses_stable_contract(self):
        cycle = ModuleIterationCycle("reasoning_engine", {"export_contract_version": "d43.v1", "mock_mode": True})
        cycle.execute_module_iteration({"mock_mode": True})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "module-data.json")
            exported = cycle.export_module_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d43.v1")
        self.assertIn("module_report", payload)
        self.assertIsInstance(payload["iteration_history"][0]["recommendations"], list)
        self.assertIn("failed_operations", payload)
        self.assertEqual(payload["metadata"]["final_status"], "completed")
        self.assertEqual(payload["module_report"]["analysis_summary"]["final_status"], "completed")

    def test_module_iteration_cleanup_resets_runtime_state(self):
        cycle = ModuleIterationCycle("reasoning_engine", {"export_contract_version": "d43.v1", "mock_mode": True})
        cycle.execute_module_iteration({"mock_mode": True})

        cleaned = cycle.cleanup()

        self.assertTrue(cleaned)
        self.assertEqual(cycle.module_metadata["final_status"], "cleaned")
        self.assertEqual(cycle.get_module_performance_report()["message"], "还没有执行任何迭代")

    def test_iteration_cycle_cleanup_keeps_shared_executor_available(self):
        cycle = IterationCycle()
        executor = cycle.executor
        cycle.execute_iteration({"mock_mode": True})

        cleaned = cycle._do_cleanup()

        self.assertTrue(cleaned)
        self.assertFalse(getattr(executor, "_shutdown", False))
        self.assertEqual(cycle.cycle_metadata["final_status"], "cleaned")
        self.assertEqual(cycle.get_cycle_summary()["message"], "还没有执行任何迭代")

    def test_fixing_stage_tracks_phase_history_and_analysis_summary(self):
        stage = FixingStage({"minimum_stable_success_rate": 0.8, "export_contract_version": "d41.v1"})

        result = stage.run_fixing_stage(
            [{"message": "Input parameter mismatch detected", "affected_components": ["parser"]}],
            {"source": "unit-test"},
            iteration_id="iter-d18",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            [phase["phase"] for phase in result.metadata["phase_history"]],
            ["identify_repairs", "execute_repairs", "validate_repairs", "analyze_repairs"],
        )
        self.assertEqual(result.metadata["analysis_summary"]["stage_status"], "stable")
        self.assertEqual(result.metadata["analysis_summary"]["final_status"], "completed")
        self.assertEqual(result.metadata["analysis_summary"]["failed_operation_count"], 0)
        self.assertEqual(result.iteration_id, "iter-d18")
        self.assertEqual(len(stage.repair_history), 1)
        self.assertEqual(stage.get_repair_performance_report()["report_metadata"]["contract_version"], "d41.v1")
        self.assertEqual(stage.get_repair_performance_report()["analysis_summary"]["status"], "stable")

    def test_fixing_stage_export_uses_json_safe_contract(self):
        stage = FixingStage({"export_contract_version": "d41.v1"})
        stage.run_fixing_stage(
            [{"message": "security vulnerability found", "affected_components": ["api"]}],
            {"source": "export-test"},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "fixing-stage.json")
            exported = stage.export_repair_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d41.v1")
        self.assertEqual(payload["repair_actions"][0]["priority"], "critical")
        self.assertEqual(payload["repair_actions"][0]["repair_type"], "security")
        self.assertIn("report_metadata", payload["repair_performance_report"])
        self.assertIn("failed_operations", payload)
        self.assertEqual(payload["metadata"]["final_status"], "completed")
        self.assertEqual(payload["repair_performance_report"]["analysis_summary"]["final_status"], "completed")

    def test_fixing_stage_failure_tracks_failed_phase(self):
        stage = FixingStage({})
        original_validate = stage.validate_repair_effects

        def raise_validation_error(repair_actions):
            raise RuntimeError("repair validation failed")

        stage.validate_repair_effects = raise_validation_error

        with self.assertRaises(RuntimeError):
            stage.run_fixing_stage(
                [{"message": "timeout on task", "affected_components": ["scheduler"]}],
                {"source": "failure-test"},
            )

        stage.validate_repair_effects = original_validate
        self.assertEqual(len(stage.failed_stages), 1)
        failed_stage = stage.failed_stages[0]
        self.assertEqual(failed_stage.metadata["failed_phase"], "validate_repairs")
        self.assertEqual(failed_stage.metadata["phase_history"][-1]["status"], "failed")
        self.assertEqual(failed_stage.metadata["analysis_summary"]["final_status"], "failed")
        self.assertEqual(stage.failed_operations[0]["operation"], "validate_repairs")
        self.assertEqual(stage.failed_operations[0]["details"]["iteration_id"], failed_stage.iteration_id)
        self.assertEqual(stage.get_repair_performance_report()["analysis_summary"]["status"], "needs_followup")

    def test_fixing_stage_cleanup_resets_runtime_state(self):
        stage = FixingStage({"export_contract_version": "d41.v1"})
        stage.run_fixing_stage(
            [{"message": "timeout on task", "affected_components": ["scheduler"]}],
            {"source": "cleanup-test"},
        )

        cleaned = stage.cleanup()

        self.assertTrue(cleaned)
        self.assertEqual(stage.stage_metadata["final_status"], "cleaned")
        self.assertEqual(stage.get_repair_performance_report()["message"], "还没有执行任何修复行动")

    def test_system_architecture_tracks_phase_history_and_analysis_summary(self):
        architecture = SystemArchitecture({"minimum_stable_health_score": 0.5, "export_contract_version": "d45.v1"})
        module_info = ModuleInfo(
            module_id="preprocess",
            module_name="PreprocessModule",
            module_type=ModuleType.PREPROCESSING,
            version="1.0.0",
            status=ModuleStatus.CREATED,
            created_at="2024-01-01T00:00:00",
        )

        self.assertTrue(architecture.register_module(module_info))
        self.assertTrue(architecture.initialize_system())
        self.assertTrue(architecture.activate_module("preprocess"))

        pipeline_result = architecture.execute_pipeline({"source": "unit-test"})
        system_status = architecture.get_system_status()

        self.assertEqual(pipeline_result["analysis_summary"]["status"], "stable")
        self.assertEqual(system_status["analysis_summary"]["status"], "stable")
        self.assertEqual(
            [phase["phase"] for phase in system_status["metadata"]["phase_history"]],
            ["register_module", "initialize_system", "activate_module", "execute_pipeline"],
        )
        self.assertEqual(system_status["metadata"]["completed_phases"][-1], "execute_pipeline")
        self.assertEqual(pipeline_result["report_metadata"]["contract_version"], "d45.v1")
        self.assertEqual(pipeline_result["report_metadata"]["last_completed_phase"], "execute_pipeline")
        self.assertEqual(pipeline_result["metadata"]["last_completed_phase"], "execute_pipeline")
        self.assertEqual(system_status["report_metadata"]["contract_version"], "d45.v1")
        self.assertEqual(system_status["report_metadata"]["final_status"], "pipeline_completed")

    def test_system_architecture_failure_tracks_failed_phase(self):
        architecture = SystemArchitecture({"export_contract_version": "d45.v1"})
        module_info = ModuleInfo(
            module_id="reasoning",
            module_name="ReasoningModule",
            module_type=ModuleType.REASONING,
            version="1.0.0",
            status=ModuleStatus.CREATED,
            created_at="2024-01-01T00:00:00",
        )
        architecture.register_module(module_info)
        architecture.initialize_system()
        architecture.activate_module("reasoning")

        def raise_module_error(module_info, context):
            raise RuntimeError("execution failed")

        architecture._execute_single_module = raise_module_error
        result = architecture.execute_pipeline({"source": "failure-test"})
        system_status = architecture.get_system_status()

        self.assertEqual(result["analysis_summary"]["status"], "needs_followup")
        self.assertEqual(system_status["analysis_summary"]["failed_operation_count"], 1)
        self.assertEqual(system_status["failed_operations"][0]["operation"], "execute_module")
        self.assertIn("duration_seconds", system_status["failed_operations"][0])
        self.assertEqual(system_status["failed_operations"][0]["details"]["module_id"], "reasoning")
        self.assertIsNone(system_status["metadata"]["failed_phase"])

    def test_system_architecture_export_uses_json_safe_contract(self):
        architecture = SystemArchitecture({"export_contract_version": "d45.v1"})
        module_info = ModuleInfo(
            module_id="output",
            module_name="OutputModule",
            module_type=ModuleType.OUTPUT,
            version="1.0.0",
            status=ModuleStatus.CREATED,
            created_at="2024-01-01T00:00:00",
        )
        architecture.register_module(module_info)
        architecture.initialize_system()
        architecture.activate_module("output")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "architecture-report.json")
            exported = architecture.export_system_info(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d45.v1")
        self.assertEqual(payload["report_metadata"]["last_completed_phase"], "export_system_info")
        self.assertEqual(payload["module_registry"]["modules"][0]["module_type"], "output")
        self.assertEqual(payload["module_registry"]["modules"][0]["status"], "active")
        self.assertIn("report_metadata", payload["architecture_summary"])
        self.assertEqual(payload["metadata"]["last_completed_phase"], "export_system_info")
        self.assertIn("metadata", payload)

    def test_system_architecture_cleanup_resets_runtime_state(self):
        architecture = SystemArchitecture({"export_contract_version": "d45.v1"})
        module_info = ModuleInfo(
            module_id="cleanup",
            module_name="CleanupModule",
            module_type=ModuleType.OUTPUT,
            version="1.0.0",
            status=ModuleStatus.CREATED,
            created_at="2024-01-01T00:00:00",
        )
        architecture.register_module(module_info)
        architecture.initialize_system()

        cleaned = architecture.cleanup()

        self.assertTrue(cleaned)
        self.assertEqual(architecture.get_system_status()["metadata"]["final_status"], "cleaned")
        self.assertEqual(architecture.get_system_status()["system_info"]["status"], "cleaned")


if __name__ == "__main__":
    unittest.main()
