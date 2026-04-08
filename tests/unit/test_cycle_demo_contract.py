import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import run_cycle_demo
from src.cycle.cycle_runner import execute_real_module_pipeline, run_iteration_cycle
from src.research.study_session_manager import ResearchPhase


class TestCycleDemoContract(unittest.TestCase):
    def test_run_iteration_cycle_includes_governance_contract(self):
        """System A run_iteration_cycle 契约验证（直接测试 cycle_runner）。"""
        fake_pipeline = lambda input_data, modules=None, manage_module_lifecycle=False, optional_modules=None: [
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

        result = run_iteration_cycle(
            1,
            {"raw_text": "demo", "metadata": {"source": "unit-test"}},
            max_iterations=2,
            shared_modules=[],
            governance_config={"export_contract_version": "d58.v1", "minimum_stable_quality_score": 0.85, "persist_failed_operations": True},
            execute_pipeline=fake_pipeline,
        )

        self.assertEqual(result["status"], "completed")
        self.assertIn("metadata", result)
        self.assertIn("analysis_summary", result)
        self.assertIn("failed_operations", result)
        self.assertEqual(result["metadata"]["last_completed_phase"], "assemble_iteration_cycle_summary")
        self.assertEqual(result["analysis_summary"]["module_count"], 1)
        self.assertEqual(result["analysis_summary"]["failed_operation_count"], 0)

    def test_run_full_cycle_demo_exports_governed_report(self):
        original_run_research_session = run_cycle_demo.run_research_session
        try:
            run_cycle_demo.run_research_session = lambda question, config, phase_names=None, export_report_formats=None, report_output_dir=None: {
                "status": "completed",
                "session_id": "fake_session_1",
                "cycle_id": "fake_session_1",
                "question": question,
                "executed_phases": phase_names or ["observe"],
                "phase_results": {p: {"phase": p} for p in (phase_names or ["observe"])},
                "metadata": {},
                "cycle_snapshot": {},
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
            run_cycle_demo.run_research_session = original_run_research_session

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


    def test_pipeline_iteration_returns_iteration_contract(self):
        """6 阶段桥接函数返回与 run_iteration_cycle 兼容的契约。"""
        from src.cycle.cycle_pipeline_bridge import run_pipeline_iteration
        from src.cycle.cycle_reporter import summarize_module_quality

        fake_session = lambda question, config, phase_names=None, **kw: {
            "status": "completed",
            "session_id": "bridge_test",
            "executed_phases": phase_names or [],
            "phase_results": {
                "observe": {"phase": "observe", "status": "completed"},
                "reflect": {
                    "phase": "reflect",
                    "reflections": [{"topic": "t", "reflection": "r", "action": "a", "source": "quality_assessor"}],
                    "quality_assessment": {"overall_cycle_score": 0.85},
                    "improvement_plan": ["计划一"],
                },
            },
        }

        result = run_pipeline_iteration(
            1,
            {"raw_text": "test", "objective": "小柴胡汤分析"},
            run_research_session_fn=fake_session,
            summarize_module_quality_fn=summarize_module_quality,
            max_iterations=2,
        )

        # 返回契约: 必须包含 run_iteration_cycle 合同字段
        self.assertEqual(result["iteration_id"], "iter_1")
        self.assertEqual(result["iteration_number"], 1)
        self.assertEqual(result["status"], "completed")
        self.assertIn("duration", result)
        self.assertIn("modules", result)
        self.assertIn("academic_insights", result)
        self.assertIn("recommendations", result)
        self.assertIn("metadata", result)
        self.assertTrue(result["metadata"]["pipeline_mode"])
        self.assertIn("analysis_summary", result)
        self.assertEqual(result["analysis_summary"]["module_count"], 2)

    def test_pipeline_iteration_handles_session_failure(self):
        """run_research_session 抛异常时桥接函数返回 failed。"""
        from src.cycle.cycle_pipeline_bridge import run_pipeline_iteration
        from src.cycle.cycle_reporter import summarize_module_quality

        result = run_pipeline_iteration(
            1,
            {"raw_text": "test"},
            run_research_session_fn=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")),
            summarize_module_quality_fn=summarize_module_quality,
            max_iterations=1,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("boom", result["error"])


if __name__ == "__main__":
    unittest.main()