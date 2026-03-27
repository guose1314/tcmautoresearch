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


if __name__ == "__main__":
    unittest.main()
