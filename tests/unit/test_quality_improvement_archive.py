import json
import tempfile
import unittest
from pathlib import Path

from tools.quality_improvement_archive import build_archive_entry, write_archive


class TestQualityImprovementArchive(unittest.TestCase):
    def test_build_archive_entry(self):
        entry = build_archive_entry(
            {
                "overall_success": True,
                "results": [
                    {"name": "logic_checks", "success": True},
                    {"name": "code_quality", "success": False},
                ],
            },
            {"overall_score": 88.2, "grade": "B", "failed_dimensions": ["code_health"]},
            {"trend": {"status": "stable", "score_delta": 0.0}, "action_backlog": [{"priority": "P1"}]},
            inventory_report={
                "analysis_summary": {
                    "scanned_consumer_count": 4,
                    "missing_contract_count": 1,
                    "eligible_missing_contract_count": 1,
                    "root_script_observation_count": 2,
                    "root_script_observation_category_counts": {"uncategorized_root_script": 1},
                },
                "recommendation": {"recommended_path": "tools/missing_consumer.py"},
            },
        )
        self.assertEqual(entry["quality_grade"], "B")
        self.assertIn("code_quality", entry["failed_gates"])
        self.assertEqual(entry["action_backlog_count"], 1)
        self.assertEqual(entry["inventory_summary"]["missing_contract_count"], 1)
        self.assertEqual(entry["inventory_summary"]["recommended_next_target"], "tools/missing_consumer.py")

    def test_build_archive_entry_includes_governance_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            config_path.write_text(
                "governance:\n"
                "  quality_improvement_archive:\n"
                "    minimum_stable_quality_score: 85.0\n"
                "    export_contract_version: \"d65.v1\"\n",
                encoding="utf-8",
            )
            entry = build_archive_entry(
                {"overall_success": True, "results": [{"name": "logic_checks", "success": True}]},
                {"overall_score": 92.0, "grade": "A", "failed_dimensions": []},
                {"trend": {"status": "stable", "score_delta": 0.0}, "action_backlog": [], "next_cycle_targets": {}},
                config_path,
                {"analysis_summary": {"missing_contract_count": 0, "root_script_observation_category_counts": {}}, "recommendation": {"recommended_path": None}},
            )

        self.assertIn("metadata", entry)
        self.assertIn("report_metadata", entry)
        self.assertIn("analysis_summary", entry)
        self.assertIn("failed_operations", entry)
        self.assertEqual(entry["report_metadata"]["contract_version"], "d65.v1")
        self.assertEqual(entry["metadata"]["last_completed_phase"], "build_archive_entry")
        self.assertIn("inventory_missing_contract_count", entry["analysis_summary"])

    def test_write_archive_outputs_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = {
                "timestamp": "2026-03-28T00:00:00+00:00",
                "quality_score": 95.0,
                "quality_grade": "A",
                "trend_status": "improving",
                "trend_delta": 1.2,
                "overall_success": True,
                "failed_gates": [],
                "failed_dimensions": [],
                "action_backlog_count": 2,
                "next_cycle_targets": {"target_overall_score": 97.0},
                "inventory_summary": {
                    "status": "healthy",
                    "scanned_consumer_count": 9,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {"non_governance_domain_script": 1},
                    "recommended_next_target": None,
                },
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["build_archive_entry"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "build_archive_entry",
                },
                "failed_operations": [],
                "report_metadata": {"contract_version": "d65.v1"},
            }
            outputs = write_archive(
                entry,
                root / "output" / "archive.jsonl",
                root / "docs" / "quality-archive",
                root / "output" / "latest.json",
            )
            self.assertTrue(outputs["history"].exists())
            self.assertTrue(outputs["dossier"].exists())
            self.assertTrue(outputs["latest"].exists())
            latest_payload = json.loads(outputs["latest"].read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["metadata"]["last_completed_phase"], "export_quality_improvement_archive")
            self.assertEqual(latest_payload["report_metadata"]["contract_version"], "d65.v1")
            self.assertEqual(
                latest_payload["report_metadata"]["artifact_reference_labels"],
                ["history", "latest_output", "dossier"],
            )
            self.assertEqual(
                latest_payload["report_metadata"]["artifact_reference_paths"],
                [
                    str(outputs["history"]).replace("\\", "/"),
                    str(outputs["latest"]).replace("\\", "/"),
                    str(outputs["dossier"]).replace("\\", "/"),
                ],
            )
            self.assertEqual(
                latest_payload["metadata"]["phase_history"][-1]["details"]["history_path"],
                latest_payload["report_metadata"]["history_path"],
            )
            self.assertEqual(
                latest_payload["metadata"]["phase_history"][-1]["details"]["latest_output"],
                latest_payload["report_metadata"]["latest_output_path"],
            )
            self.assertEqual(
                latest_payload["metadata"]["phase_history"][-1]["details"]["dossier_path"],
                latest_payload["report_metadata"]["dossier_path"],
            )
            self.assertEqual(latest_payload["inventory_summary"]["status"], "healthy")
            dossier_text = outputs["dossier"].read_text(encoding="utf-8")
            self.assertIn("Inventory Governance", dossier_text)
            self.assertEqual(latest_payload["inventory_trend"]["status"], "baseline")
            self.assertIn("Inventory Trend", dossier_text)
            self.assertIn("## Artifact References", dossier_text)
            self.assertIn(
                "- History Path: {0}".format(latest_payload["report_metadata"]["history_path"]),
                dossier_text,
            )
            self.assertIn(
                "- Latest Output Path: {0}".format(latest_payload["report_metadata"]["latest_output_path"]),
                dossier_text,
            )
            self.assertIn(
                "- Dossier Path: {0}".format(latest_payload["report_metadata"]["dossier_path"]),
                dossier_text,
            )

    def test_write_archive_builds_inventory_trend_from_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history_path = root / "output" / "archive.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-03-29T00:00:00+00:00",
                        "inventory_summary": {
                            "status": "needs_followup",
                            "scanned_consumer_count": 8,
                            "missing_contract_count": 2,
                            "eligible_missing_contract_count": 2,
                            "root_script_observation_count": 1,
                            "root_script_observation_category_counts": {"uncategorized_root_script": 1},
                            "recommended_next_target": "tools/legacy_consumer.py",
                        },
                    },
                    ensure_ascii=False,
                ) + "\n",
                encoding="utf-8",
            )
            entry = {
                "timestamp": "2026-03-30T00:00:00+00:00",
                "quality_score": 95.0,
                "quality_grade": "A",
                "trend_status": "stable",
                "trend_delta": 0.0,
                "overall_success": True,
                "failed_gates": [],
                "failed_dimensions": [],
                "action_backlog_count": 1,
                "next_cycle_targets": {"target_overall_score": 97.0},
                "inventory_summary": {
                    "status": "healthy",
                    "scanned_consumer_count": 9,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {"non_governance_domain_script": 1},
                    "recommended_next_target": None,
                },
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["build_archive_entry"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "build_archive_entry",
                },
                "failed_operations": [],
                "report_metadata": {"contract_version": "d65.v1"},
            }

            outputs = write_archive(
                entry,
                history_path,
                root / "docs" / "quality-archive",
                root / "output" / "latest.json",
            )

            latest_payload = json.loads(outputs["latest"].read_text(encoding="utf-8"))
            self.assertEqual(latest_payload["inventory_trend"]["status"], "improving")
            self.assertEqual(latest_payload["inventory_trend"]["missing_contract_delta"], -2)
            self.assertEqual(latest_payload["inventory_trend"]["uncategorized_root_script_delta"], -1)
            self.assertTrue(latest_payload["inventory_trend"]["recommended_next_target_changed"])
            self.assertEqual(latest_payload["analysis_summary"]["inventory_trend_status"], "improving")
            self.assertEqual(
                latest_payload["report_metadata"]["artifact_reference_labels"],
                ["history", "latest_output", "dossier"],
            )
            dossier_text = outputs["dossier"].read_text(encoding="utf-8")
            self.assertIn(
                "- Dossier Path: {0}".format(latest_payload["report_metadata"]["dossier_path"]),
                dossier_text,
            )


if __name__ == "__main__":
    unittest.main()
