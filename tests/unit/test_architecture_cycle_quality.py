import json
import os
import tempfile
import unittest

import src.cycle as cycle_package
from src.core import __all__ as core_all
from src.core.architecture import ModuleInfo, ModuleType, SystemArchitecture
from src.core.module_base import BaseModule, ModuleStatus


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


class TestCoreAndArchitectureQuality(unittest.TestCase):
    def test_core_exports_are_unique(self):
        self.assertEqual(len(core_all), len(set(core_all)))

    def test_cycle_package_exports_current_runtime_entrypoints(self):
        exported = set(cycle_package.__all__)
        self.assertEqual(
            exported,
            {
                "build_cycle_demo_arg_parser",
                "execute_cycle_demo_command",
                "execute_real_module_pipeline",
                "run_full_cycle_demo",
                "run_research_session",
            },
        )
        for name in exported:
            self.assertTrue(callable(getattr(cycle_package, name)))

    def test_base_module_tracks_phase_history_and_analysis_summary(self):
        module = DemoGovernedBaseModule(
            config={"export_contract_version": "d46.v1", "minimum_stable_success_rate": 0.5}
        )

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
