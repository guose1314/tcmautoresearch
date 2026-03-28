import tempfile
import unittest
from pathlib import Path

from tools.quality_gate import (
    GateResult,
    build_report,
    run_code_quality_gate,
    run_continuous_improvement_gate,
    run_dependency_graph_gate,
    run_logic_gate,
    run_quality_assessment_gate,
    run_quality_feedback_gate,
    run_quality_improvement_archive_gate,
    run_unit_test_gate,
)


class TestQualityGate(unittest.TestCase):
    def test_build_report_marks_failure_when_any_gate_fails(self):
        report = build_report(
            [
                GateResult(name="a", success=True),
                GateResult(name="b", success=False),
            ]
        )
        self.assertFalse(report["overall_success"])
        self.assertEqual(len(report["results"]), 2)

    def test_run_logic_gate_detects_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir(parents=True)
            (root / "src" / "bad.py").write_text(
                "class A:\n    pass\n\nclass A:\n    pass\n",
                encoding="utf-8",
            )
            result = run_logic_gate(root)
            self.assertFalse(result.success)
            self.assertEqual(result.metrics["error_count"], 1)

    def test_run_dependency_graph_gate_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "core").mkdir(parents=True)
            (root / "src" / "research").mkdir(parents=True)
            (root / "src" / "core" / "module_base.py").write_text("class BaseModule: pass\n", encoding="utf-8")
            (root / "src" / "research" / "pipeline.py").write_text(
                "from src.core.module_base import BaseModule\n",
                encoding="utf-8",
            )
            result = run_dependency_graph_gate(root, root / "docs" / "architecture")
            self.assertTrue(result.success)
            outputs = result.details["outputs"]
            self.assertIn("json", outputs)
            self.assertTrue((root / outputs["json"]).exists())

    def test_run_code_quality_gate_detects_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir(parents=True)
            (root / "src" / "bad.py").write_text("def oops(:\n    pass\n", encoding="utf-8")
            result = run_code_quality_gate(root)
            self.assertFalse(result.success)
            self.assertEqual(result.metrics["error_count"], 1)

    def test_run_unit_test_gate_executes_requested_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests" / "unit").mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "unit" / "__init__.py").write_text("", encoding="utf-8")
            (root / "tests" / "unit" / "test_sample.py").write_text(
                "import unittest\n\n"
                "class TestSample(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            result = run_unit_test_gate(root, ["tests.unit.test_sample"])
            self.assertTrue(result.success)
            self.assertEqual(result.metrics["return_code"], 0)

    def test_run_quality_assessment_gate_generates_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.yml").write_text("quality_assessment:\n  min_overall_score: 80\n", encoding="utf-8")
            gates = [
                GateResult(name="logic_checks", success=True, metrics={"issue_count": 0, "error_count": 0}),
                GateResult(name="dependency_graph", success=True, metrics={}),
                GateResult(name="code_quality", success=True, metrics={"issue_count": 0, "error_count": 0, "warning_count": 0}),
                GateResult(name="quality_unit_tests", success=True, metrics={"return_code": 0}),
            ]
            result = run_quality_assessment_gate(root, gates)
            self.assertTrue(result.success)
            self.assertIn("overall_score", result.metrics)
            report_path = root / result.details["assessment_report"]
            self.assertTrue(report_path.exists())

    def test_run_continuous_improvement_gate_generates_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir(parents=True)
            (root / "output" / "quality-assessment.json").write_text(
                "{\"overall_score\": 90, \"grade\": \"A\", \"passed\": true, \"dimension_scores\": {\"code_health\": 88}, \"failed_dimensions\": []}",
                encoding="utf-8",
            )

            result = run_continuous_improvement_gate(root)
            self.assertTrue(result.success)
            self.assertIn("history_points", result.metrics)
            self.assertTrue((root / result.details["continuous_report"]).exists())
            self.assertTrue((root / result.details["history_file"]).exists())

    def test_run_quality_improvement_archive_gate_generates_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir(parents=True)
            (root / "output" / "quality-assessment.json").write_text(
                "{\"overall_score\": 90, \"grade\": \"A\", \"passed\": true, \"failed_dimensions\": [], \"dimension_scores\": {\"code_health\": 88}}",
                encoding="utf-8",
            )
            (root / "output" / "continuous-improvement.json").write_text(
                "{\"trend\": {\"status\": \"stable\", \"score_delta\": 0.0}, \"action_backlog\": [], \"next_cycle_targets\": {}}",
                encoding="utf-8",
            )
            gate_report = {"overall_success": True, "results": [{"name": "logic_checks", "success": True}]}

            result = run_quality_improvement_archive_gate(root, gate_report)
            self.assertTrue(result.success)
            self.assertEqual(result.metrics["archive_entry_written"], 1)
            self.assertTrue((root / result.details["history_file"]).exists())
            self.assertTrue((root / result.details["dossier_file"]).exists())
            self.assertTrue((root / result.details["latest_file"]).exists())

    def test_run_quality_feedback_gate_generates_feedback_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir(parents=True)
            (root / "output" / "quality-assessment.json").write_text(
                "{\"overall_score\": 82, \"grade\": \"B\", \"failed_dimensions\": [], \"dimension_scores\": {\"code_health\": 72}}",
                encoding="utf-8",
            )
            (root / "output" / "continuous-improvement.json").write_text(
                "{\"trend\": {\"status\": \"regressing\", \"score_delta\": -1.0}}",
                encoding="utf-8",
            )
            (root / "output" / "quality-improvement-archive-latest.json").write_text(
                "{\"trend_status\": \"regressing\", \"trend_delta\": -1.0}",
                encoding="utf-8",
            )

            result = run_quality_feedback_gate(root)
            self.assertTrue(result.success)
            self.assertIn("feedback_level", result.metrics)
            self.assertTrue((root / result.details["feedback_json"]).exists())
            self.assertTrue((root / result.details["feedback_markdown"]).exists())
            self.assertTrue((root / result.details["feedback_issue_index"]).exists())
            self.assertTrue((root / result.details["feedback_issue_dir"]).exists())
            self.assertGreaterEqual(result.metrics["owner_count"], 1)
            self.assertGreaterEqual(result.metrics["issue_draft_count"], 1)


if __name__ == "__main__":
    unittest.main()