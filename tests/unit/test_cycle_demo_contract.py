import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import run_cycle_demo
from src.research.study_session_manager import ResearchPhase


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

    def test_run_research_session_can_export_markdown_report(self):
        class FakeCycle:
            def __init__(self):
                self.cycle_id = "cycle_demo_research"
                self.cycle_name = "research_demo"
                self.description = "测试问题"
                self.research_objective = "测试问题"
                self.research_scope = "中医药"
                self.researchers = []
                self.phase_executions = {}

        class FakePipeline:
            def __init__(self, config=None):
                self.config = config or {}
                self.cycle = FakeCycle()

            def create_research_cycle(self, **kwargs):
                return self.cycle

            def start_research_cycle(self, cycle_id):
                return True

            def execute_research_phase(self, cycle_id, phase, phase_context=None):
                if phase is ResearchPhase.OBSERVE:
                    result = {
                        "phase": "observe",
                        "observations": ["小柴胡汤配伍具有核心药对特征"],
                        "findings": ["柴胡与黄芩在多来源数据中稳定共现"],
                        "literature_pipeline": {
                            "summaries": ["现有文献认为小柴胡汤具有和解少阳的核心作用"],
                            "evidence_matrix": [{"intervention": "小柴胡汤", "outcome": "症状改善", "evidence_level": "moderate"}],
                        },
                        "ingestion_pipeline": {
                            "entities": [{"name": "小柴胡汤"}, {"name": "柴胡"}, {"name": "黄芩"}],
                            "semantic_graph": {"nodes": ["小柴胡汤", "柴胡", "黄芩"], "edges": [["小柴胡汤", "柴胡"], ["小柴胡汤", "黄芩"]]},
                        },
                    }
                else:
                    result = {"phase": phase.value}
                self.cycle.phase_executions[phase] = {"result": result}
                return result

            def complete_research_cycle(self, cycle_id):
                return True

            def cleanup(self):
                return True

            def _serialize_cycle(self, cycle):
                return {
                    "cycle_id": cycle.cycle_id,
                    "cycle_name": cycle.cycle_name,
                    "phase_executions": {
                        phase.value: payload for phase, payload in cycle.phase_executions.items()
                    },
                }

        import src.research.research_pipeline as research_pipeline_module

        original_pipeline = research_pipeline_module.ResearchPipeline
        try:
            research_pipeline_module.ResearchPipeline = FakePipeline
            with TemporaryDirectory() as tmp:
                result = run_cycle_demo.run_research_session(
                    question="小柴胡汤的方剂配伍规律研究",
                    config={},
                    phase_names=["observe"],
                    export_report_formats=["markdown"],
                    report_output_dir=tmp,
                )

                self.assertEqual(result["status"], "completed")
                self.assertIn("report_outputs", result)
                self.assertIn("markdown", result["report_outputs"])
                self.assertTrue(Path(result["report_outputs"]["markdown"]).exists())
                markdown_text = Path(result["report_outputs"]["markdown"]).read_text(encoding="utf-8")
                self.assertIn("## Introduction", markdown_text)
                self.assertIn("## Methods", markdown_text)
                self.assertIn("## Results", markdown_text)
                self.assertIn("## Discussion", markdown_text)
        finally:
            research_pipeline_module.ResearchPipeline = original_pipeline

    def test_main_forwards_report_switches_to_research_session(self):
        original_run_research_session = run_cycle_demo.run_research_session
        captured = {}

        def fake_run_research_session(**kwargs):
            captured.update(kwargs)
            return {"status": "completed"}

        try:
            run_cycle_demo.run_research_session = fake_run_research_session
            with TemporaryDirectory() as tmp:
                original_argv = list(__import__("sys").argv)
                __import__("sys").argv = [
                    "run_cycle_demo.py",
                    "--mode",
                    "research",
                    "--question",
                    "测试问题",
                    "--export-report",
                    "--report-format",
                    "markdown",
                    "--report-format",
                    "docx",
                    "--report-output-dir",
                    tmp,
                ]
                try:
                    result = run_cycle_demo.main()
                finally:
                    __import__("sys").argv = original_argv

            self.assertEqual(result, 0)
            self.assertEqual(captured["question"], "测试问题")
            self.assertEqual(captured["export_report_formats"], ["markdown", "docx"])
            self.assertEqual(captured["report_output_dir"], tmp)
        finally:
            run_cycle_demo.run_research_session = original_run_research_session


if __name__ == "__main__":
    unittest.main()