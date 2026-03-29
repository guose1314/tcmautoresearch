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
        )
        self.assertEqual(entry["quality_grade"], "B")
        self.assertIn("code_quality", entry["failed_gates"])
        self.assertEqual(entry["action_backlog_count"], 1)

    def test_build_archive_entry_includes_governance_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yml"
            config_path.write_text(
                "governance:\n"
                "  quality_improvement_archive:\n"
                "    minimum_stable_quality_score: 85.0\n"
                "    export_contract_version: \"d51.v1\"\n",
                encoding="utf-8",
            )
            entry = build_archive_entry(
                {"overall_success": True, "results": [{"name": "logic_checks", "success": True}]},
                {"overall_score": 92.0, "grade": "A", "failed_dimensions": []},
                {"trend": {"status": "stable", "score_delta": 0.0}, "action_backlog": [], "next_cycle_targets": {}},
                config_path,
            )

        self.assertIn("metadata", entry)
        self.assertIn("report_metadata", entry)
        self.assertIn("analysis_summary", entry)
        self.assertIn("failed_operations", entry)
        self.assertEqual(entry["report_metadata"]["contract_version"], "d51.v1")
        self.assertEqual(entry["metadata"]["last_completed_phase"], "build_archive_entry")

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
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["build_archive_entry"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "build_archive_entry",
                },
                "failed_operations": [],
                "report_metadata": {"contract_version": "d51.v1"},
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
            self.assertEqual(latest_payload["report_metadata"]["contract_version"], "d51.v1")


if __name__ == "__main__":
    unittest.main()
