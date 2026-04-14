import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import run_cycle_demo
from src.cycle.cycle_runner import run_iteration_cycle


class TestCycleDemoContract(unittest.TestCase):
    def test_describe_cycle_demo_export_contract_exposes_required_fields(self):
        contract = run_cycle_demo.describe_cycle_demo_export_contract()

        self.assertEqual(contract["result_schema"], "cycle_demo_report")
        self.assertEqual(contract["export_contract_version"], run_cycle_demo.DEFAULT_CYCLE_DEMO_GOVERNANCE["export_contract_version"])
        self.assertEqual(
            contract["required_fields"],
            ["metadata", "report_metadata", "analysis_summary", "failed_operations"],
        )

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
        captured = {}

        class _FakeRuntimeResult(SimpleNamespace):
            @property
            def session_result(self):
                publish_result = self.phase_results.get("publish") if isinstance(self.phase_results.get("publish"), dict) else {}
                publish_output_files = dict(publish_result.get("output_files") or {}) if isinstance(publish_result, dict) else {}
                question = str(self.orchestration_result.topic or "")
                return {
                    "status": self.orchestration_result.status,
                    "session_id": self.orchestration_result.cycle_id,
                    "cycle_id": self.orchestration_result.cycle_id,
                    "title": f"中医科研 IMRD 报告：{question}",
                    "question": question,
                    "research_question": question,
                    "executed_phases": list(self.phase_results.keys()),
                    "phase_results": dict(self.phase_results),
                    "metadata": {
                        "research_question": question,
                        "cycle_name": self.orchestration_result.pipeline_metadata.get("cycle_name"),
                    },
                    "cycle_snapshot": dict(self.cycle_snapshot),
                    "report_outputs": publish_output_files,
                }

        class FakeRuntimeService:
            def __init__(self, config=None):
                self.config = config or {}
                self.phase_names = list(self.config.get("phases") or ["observe"])

            def run(self, topic, **kwargs):
                captured["config"] = dict(self.config)
                captured["topic"] = topic
                captured["kwargs"] = dict(kwargs)
                output_path = Path(kwargs["report_output_dir"]) / "report.md"
                output_path.write_text(
                    "## Introduction\n\n## Methods\n\n## Results\n\n## Discussion\n",
                    encoding="utf-8",
                )
                return _FakeRuntimeResult(
                    orchestration_result=SimpleNamespace(
                        status="completed",
                        cycle_id="cycle_demo_research",
                        pipeline_metadata={"cycle_name": "research_demo"},
                        observe_philology={},
                        topic=topic,
                    ),
                    phase_results={
                        "observe": {"phase": "observe", "status": "completed"},
                        "publish": {
                            "phase": "publish",
                            "status": "completed",
                            "output_files": {"markdown": str(output_path)},
                        },
                    },
                    cycle_snapshot={"cycle_id": "cycle_demo_research"},
                )

        with patch("src.cycle.cycle_research_session.ResearchRuntimeService", FakeRuntimeService):
            with TemporaryDirectory() as tmp:
                result = run_cycle_demo.run_research_session(
                    question="小柴胡汤的方剂配伍规律研究",
                    config={
                        "pipeline_config": {},
                        "runtime_profile": "demo_research",
                    },
                    export_report_formats=["markdown"],
                    report_output_dir=tmp,
                )

                self.assertEqual(result["status"], "completed")
                self.assertIn("report_outputs", result)
                self.assertIn("markdown", result["report_outputs"])
                self.assertEqual(result["question"], "小柴胡汤的方剂配伍规律研究")
                self.assertEqual(captured["config"]["runtime_profile"], "demo_research")
                self.assertNotIn("phases", captured["config"])
                self.assertNotIn("cycle_name", captured["kwargs"])
                self.assertNotIn("scope", captured["kwargs"])
                self.assertNotIn("description", captured["kwargs"])
                self.assertTrue(Path(result["report_outputs"]["markdown"]).exists())
                markdown_text = Path(result["report_outputs"]["markdown"]).read_text(encoding="utf-8")
                self.assertIn("## Introduction", markdown_text)
                self.assertIn("## Methods", markdown_text)
                self.assertIn("## Results", markdown_text)
                self.assertIn("## Discussion", markdown_text)

    def test_run_research_session_does_not_inject_local_runtime_profile(self):
        captured = {}

        class _FakeRuntimeResult(SimpleNamespace):
            @property
            def session_result(self):
                return {
                    "status": self.orchestration_result.status,
                    "question": self.orchestration_result.topic,
                    "metadata": {},
                    "phase_results": {},
                    "cycle_snapshot": {},
                }

        class FakeRuntimeService:
            def __init__(self, config=None):
                self.config = config or {}
                self.phase_names = list(self.config.get("phases") or ["observe"])
                captured["config"] = dict(self.config)

            def run(self, topic, **kwargs):
                captured["topic"] = topic
                captured["kwargs"] = dict(kwargs)
                return _FakeRuntimeResult(
                    orchestration_result=SimpleNamespace(
                        status="completed",
                        topic=topic,
                    ),
                )

        with patch("src.cycle.cycle_research_session.ResearchRuntimeService", FakeRuntimeService):
            result = run_cycle_demo.run_research_session(
                question="桂枝汤的配伍规律",
                config={"models": {"llm": {"provider": "local"}}},
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(captured["topic"], "桂枝汤的配伍规律")
        self.assertEqual(
            captured["config"],
            {"pipeline_config": {"models": {"llm": {"provider": "local"}}}},
        )
        self.assertNotIn("runtime_profile", captured["config"])
        self.assertNotIn("cycle_name", captured["kwargs"])
        self.assertNotIn("description", captured["kwargs"])
        self.assertNotIn("scope", captured["kwargs"])

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

        captured = {}

        def fake_session(question, config, phase_names=None, **kw):
            captured.update({"question": question, "config": config, "phase_names": phase_names, **kw})
            return {
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
            {
                "raw_text": "test",
                "objective": "小柴胡汤分析",
                "previous_feedback": {"quality_assessment": {"overall_cycle_score": 0.82}},
            },
            run_research_session_fn=fake_session,
            summarize_module_quality_fn=summarize_module_quality,
            max_iterations=2,
            runtime_config={"models": {"llm": {"provider": "local"}}},
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
        self.assertEqual(captured["config"]["models"]["llm"]["provider"], "local")
        self.assertEqual(
            captured["config"]["previous_iteration_feedback"]["quality_assessment"]["overall_cycle_score"],
            0.82,
        )

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

    def test_run_full_cycle_demo_builds_runtime_config_once_for_default_pipeline(self):
        from src.cycle.cycle_runner import ModuleLifecycle, run_full_cycle_demo

        captured = {}

        def fake_default_pipeline_iteration(
            iteration_number,
            input_data,
            max_iterations=5,
            shared_modules=None,
            governance_config=None,
            runtime_config=None,
        ):
            captured["iteration_number"] = iteration_number
            captured["runtime_config"] = runtime_config
            return {
                "iteration_id": f"iter_{iteration_number}",
                "iteration_number": iteration_number,
                "status": "completed",
                "duration": 0.1,
                "modules": [],
                "academic_insights": [{"type": "quality_assessment", "confidence": 0.9}],
                "recommendations": [],
                "failed_operations": [],
                "analysis_summary": {"module_count": 0, "failed_operation_count": 0},
                "metadata": {"max_iterations": max_iterations, "pipeline_mode": True},
            }

        with patch(
            "src.cycle.cycle_runner.build_cycle_runtime_config",
            return_value={"runtime": {"environment": "test"}},
        ) as runtime_builder, patch(
            "src.cycle.cycle_runner._default_pipeline_iteration",
            side_effect=fake_default_pipeline_iteration,
        ):
            with patch("src.cycle.cycle_runner.time.sleep"):
                run_full_cycle_demo(
                    max_iterations=1,
                    sample_data=["测试方剂"],
                    config_path="./config/test.yml",
                    environment="test",
                    module_lifecycle=ModuleLifecycle(
                        build=lambda: [],
                        initialize=lambda _: None,
                        cleanup=lambda _: None,
                    ),
                )

        runtime_builder.assert_called_once_with(
            config_path="./config/test.yml",
            environment="test",
        )
        self.assertEqual(captured["iteration_number"], 1)
        self.assertEqual(captured["runtime_config"], {"runtime": {"environment": "test"}})


if __name__ == "__main__":
    unittest.main()