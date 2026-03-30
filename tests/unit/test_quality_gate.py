import json
import tempfile
import unittest
from pathlib import Path

from tools.quality_gate import (
    GateResult,
    build_report,
    export_quality_gate_report,
    run_code_quality_gate,
    run_continuous_improvement_gate,
    run_dependency_graph_gate,
    run_logic_gate,
    run_quality_assessment_gate,
    run_quality_consumer_inventory_gate,
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
        self.assertIn("metadata", report)
        self.assertIn("report_metadata", report)
        self.assertIn("analysis_summary", report)
        self.assertIn("failed_operations", report)
        self.assertEqual(report["report_metadata"]["contract_version"], "d63.v1")
        self.assertEqual(report["report_metadata"]["gate_names"], ["a", "b"])
        self.assertEqual(report["report_metadata"]["artifact_reference_labels"], [])
        self.assertEqual(report["report_metadata"]["artifact_reference_paths"], [])
        self.assertEqual(report["analysis_summary"]["failed_gate_count"], 1)

    def test_export_quality_gate_report_updates_export_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = build_report(
                [
                    GateResult(
                        name="logic_checks",
                        success=True,
                        details={"report_file": "output/logic-checks.json"},
                    ),
                    GateResult(
                        name="code_quality",
                        success=False,
                        details={"outputs": {"json": "docs/architecture/dependency-graph.json"}},
                    ),
                ],
                    governance_config={"export_contract_version": "d63.v1"},
                runtime_metadata={
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["assemble_quality_gate_report"],
                    "failed_phase": None,
                    "final_status": "failed",
                    "last_completed_phase": "assemble_quality_gate_report",
                },
                failed_operations=[
                    {
                        "operation": "code_quality",
                        "error": "Gate reported unsuccessful result",
                        "details": {},
                        "timestamp": "2026-03-29T00:00:00+00:00",
                        "duration_seconds": 0.0,
                    }
                ],
            )

            output_path = root / "output" / "quality-gate.json"
            exported = export_quality_gate_report(report, output_path)

            self.assertTrue(output_path.exists())
            self.assertEqual(exported["metadata"]["last_completed_phase"], "export_quality_gate_report")
            self.assertEqual(exported["report_metadata"]["contract_version"], "d63.v1")
            self.assertEqual(exported["report_metadata"]["gate_names"], ["logic_checks", "code_quality"])
            self.assertEqual(
                exported["report_metadata"]["artifact_reference_labels"],
                ["logic_checks.report_file", "code_quality.outputs.json"],
            )
            self.assertEqual(
                exported["report_metadata"]["artifact_reference_paths"],
                ["output/logic-checks.json", "docs/architecture/dependency-graph.json"],
            )
            self.assertEqual(
                exported["metadata"]["phase_history"][-1]["details"]["output_path"],
                exported["report_metadata"]["output_path"],
            )
            self.assertEqual(exported["analysis_summary"]["failed_gate_count"], 1)

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
            (root / "config.yml").write_text(
                "quality_assessment:\n"
                "  min_overall_score: 80\n"
                "  export_contract_version: \"d49.v1\"\n",
                encoding="utf-8",
            )
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
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["report_metadata"]["contract_version"], "d49.v1")
            self.assertEqual(report["metadata"]["last_completed_phase"], "export_assessment_report")

    def test_run_continuous_improvement_gate_generates_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir(parents=True)
            (root / "config.yml").write_text(
                "governance:\n"
                "  continuous_improvement:\n"
                "    export_contract_version: \"d66.v1\"\n",
                encoding="utf-8",
            )
            (root / "output" / "quality-assessment.json").write_text(
                "{\"overall_score\": 90, \"grade\": \"A\", \"passed\": true, \"dimension_scores\": {\"code_health\": 88}, \"failed_dimensions\": []}",
                encoding="utf-8",
            )
            (root / "output" / "quality-improvement-archive.jsonl").write_text(
                "{\"inventory_summary\": {\"missing_contract_count\": 1, \"root_script_observation_category_counts\": {\"uncategorized_root_script\": 1}, \"recommended_next_target\": \"tools/missing_consumer.py\"}, \"inventory_trend\": {\"status\": \"regressing\", \"history_points\": 2, \"recommended_next_target_changed\": true}}\n",
                encoding="utf-8",
            )

            result = run_continuous_improvement_gate(root)
            self.assertTrue(result.success)
            self.assertIn("history_points", result.metrics)
            self.assertTrue((root / result.details["continuous_report"]).exists())
            self.assertTrue((root / result.details["history_file"]).exists())
            report = json.loads((root / result.details["continuous_report"]).read_text(encoding="utf-8"))
            self.assertEqual(report["report_metadata"]["contract_version"], "d66.v1")
            self.assertEqual(report["metadata"]["last_completed_phase"], "export_continuous_improvement_report")
            self.assertEqual(report["report_metadata"]["artifact_reference_labels"], ["history", "output"])
            self.assertEqual(report["inventory_focus"]["trend_status"], "regressing")

    def test_run_quality_improvement_archive_gate_generates_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir(parents=True)
            (root / "config.yml").write_text(
                "governance:\n"
                "  quality_improvement_archive:\n"
                "    export_contract_version: \"d65.v1\"\n",
                encoding="utf-8",
            )
            (root / "output" / "quality-assessment.json").write_text(
                "{\"overall_score\": 90, \"grade\": \"A\", \"passed\": true, \"failed_dimensions\": [], \"dimension_scores\": {\"code_health\": 88}}",
                encoding="utf-8",
            )
            (root / "output" / "continuous-improvement.json").write_text(
                "{\"trend\": {\"status\": \"stable\", \"score_delta\": 0.0}, \"action_backlog\": [], \"next_cycle_targets\": {}}",
                encoding="utf-8",
            )
            (root / "output" / "quality-consumer-inventory.json").write_text(
                "{\"analysis_summary\": {\"scanned_consumer_count\": 1, \"missing_contract_count\": 0, \"eligible_missing_contract_count\": 0, \"root_script_observation_count\": 1, \"root_script_observation_category_counts\": {\"non_governance_domain_script\": 1}}, \"recommendation\": {\"recommended_path\": null}}",
                encoding="utf-8",
            )
            gate_report = {"overall_success": True, "results": [{"name": "logic_checks", "success": True}]}

            result = run_quality_improvement_archive_gate(root, gate_report)
            self.assertTrue(result.success)
            self.assertEqual(result.metrics["archive_entry_written"], 1)
            self.assertTrue((root / result.details["history_file"]).exists())
            self.assertTrue((root / result.details["dossier_file"]).exists())
            self.assertTrue((root / result.details["latest_file"]).exists())
            latest_payload = json.loads((root / result.details["latest_file"]).read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["report_metadata"]["contract_version"], "d65.v1")
            self.assertEqual(latest_payload["metadata"]["last_completed_phase"], "export_quality_improvement_archive")
            self.assertEqual(
                latest_payload["report_metadata"]["artifact_reference_labels"],
                ["history", "latest_output", "dossier"],
            )
            self.assertEqual(latest_payload["inventory_summary"]["status"], "healthy")
            self.assertIn("inventory_trend", latest_payload)

    def test_run_quality_feedback_gate_generates_feedback_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir(parents=True)
            (root / "config.yml").write_text(
                "governance:\n"
                "  quality_feedback:\n"
                "    export_contract_version: \"d73.v1\"\n",
                encoding="utf-8",
            )
            (root / "output" / "quality-assessment.json").write_text(
                "{\"overall_score\": 82, \"grade\": \"B\", \"failed_dimensions\": [\"code_health\"], \"dimension_scores\": {\"code_health\": 72}}",
                encoding="utf-8",
            )
            (root / "output" / "continuous-improvement.json").write_text(
                "{\"trend\": {\"status\": \"regressing\", \"score_delta\": -1.0}}",
                encoding="utf-8",
            )
            (root / "output" / "quality-improvement-archive-latest.json").write_text(
                "{\"trend_status\": \"regressing\", \"trend_delta\": -1.0, \"inventory_summary\": {\"recommended_next_target\": \"tools/missing_consumer.py\"}, \"inventory_trend\": {\"status\": \"regressing\", \"history_points\": 4, \"missing_contract_delta\": 1, \"uncategorized_root_script_delta\": 0}}",
                encoding="utf-8",
            )
            (root / "output" / "quality-consumer-inventory.json").write_text(
                "{\"analysis_summary\": {\"scanned_consumer_count\": 1, \"missing_contract_count\": 0, \"root_script_observation_count\": 1, \"root_script_observation_category_counts\": {\"non_governance_domain_script\": 1}}, \"recommendation\": {\"recommended_path\": null}}",
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
            feedback = json.loads((root / result.details["feedback_json"]).read_text(encoding="utf-8"))
            self.assertEqual(feedback["report_metadata"]["contract_version"], "d73.v1")
            self.assertEqual(feedback["metadata"]["last_completed_phase"], "export_quality_feedback_report")
            self.assertGreaterEqual(result.metrics["issue_draft_count"], 1)
            self.assertEqual(feedback["inventory_summary"]["status"], "healthy")
            self.assertEqual(feedback["inventory_trend"]["status"], "regressing")

    def test_run_quality_consumer_inventory_gate_generates_inventory_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            (root / "output").mkdir(parents=True)
            (root / "config.yml").write_text(
                "governance:\n"
                "  quality_consumer_inventory:\n"
                "    export_contract_version: \"d62.v1\"\n",
                encoding="utf-8",
            )
            (root / "tools" / "consumer.py").write_text(
                "metadata = {}\n"
                "report_metadata = {}\n"
                "analysis_summary = {}\n"
                "failed_operations = []\n"
                "export_contract_version = 'd63.v1'\n"
                "QUALITY_FEEDBACK_PATH = 'output/quality-feedback.json'\n",
                encoding="utf-8",
            )
            (root / "generate_test_report.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "storage = json.loads((Path('output') / 'storage_test_results.json').read_text(encoding='utf-8'))\n"
                "(Path('output') / 'generic-report.json').write_text(json.dumps({'summary': storage.get('summary')}), encoding='utf-8')\n",
                encoding="utf-8",
            )

            result = run_quality_consumer_inventory_gate(root)

            self.assertTrue(result.success)
            self.assertEqual(result.metrics["missing_contract_count"], 0)
            self.assertTrue((root / result.details["inventory_report"]).exists())
            report = json.loads((root / result.details["inventory_report"]).read_text(encoding="utf-8"))
            self.assertEqual(report["report_metadata"]["contract_version"], "d62.v1")


if __name__ == "__main__":
    unittest.main()