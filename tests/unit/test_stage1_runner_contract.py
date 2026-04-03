import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = REPO_ROOT / "tools" / "stage1_d1_d10_runner.ps1"


class TestStage1RunnerContract(unittest.TestCase):
    def _run_dry_runner(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "tools" / "stage1_d1_d10_runner.ps1"),
                "-Day",
                "D1",
                "-DryRun",
                "-RepoPath",
                str(root),
                "-PythonExe",
                sys.executable,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_day_report_includes_governance_contract(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            shutil.copy2(RUNNER_SOURCE, root / "tools" / "stage1_d1_d10_runner.ps1")
            (root / "config.yml").write_text(
                "governance:\n"
                "  stage1_runner:\n"
                "    minimum_stable_pass_rate: 85.0\n"
                "    export_contract_version: \"d67.v1\"\n",
                encoding="utf-8",
            )

            result = self._run_dry_runner(root)
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            day_reports = sorted((root / "logs" / "stage1").glob("stage1_D1_*.json"))
            self.assertTrue(day_reports)
            payload = json.loads(day_reports[-1].read_text(encoding="utf-8-sig"))

            self.assertIn("metadata", payload)
            self.assertIn("analysis_summary", payload)
            self.assertIn("failed_operations", payload)
            self.assertIn("report_metadata", payload)
            self.assertEqual(payload["report_metadata"]["contract_version"], "d67.v1")
            self.assertEqual(payload["metadata"]["last_completed_phase"], "export_stage1_day_summary")
            self.assertEqual(payload["analysis_summary"]["pass_rate_band"], "critical")
            self.assertEqual(payload["failed_operations"], [])
            self.assertNotIn("governance_alerts", payload)

    def test_global_report_includes_governance_contract(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            shutil.copy2(RUNNER_SOURCE, root / "tools" / "stage1_d1_d10_runner.ps1")
            (root / "config.yml").write_text(
                "governance:\n"
                "  stage1_runner:\n"
                "    minimum_stable_pass_rate: 85.0\n"
                "    export_contract_version: \"d67.v1\"\n",
                encoding="utf-8",
            )

            result = self._run_dry_runner(root)
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            global_reports = sorted((root / "logs" / "stage1").glob("stage1_all_*.json"))
            self.assertTrue(global_reports)
            payload = json.loads(global_reports[-1].read_text(encoding="utf-8-sig"))

            self.assertIn("metadata", payload)
            self.assertIn("analysis_summary", payload)
            self.assertIn("failed_operations", payload)
            self.assertIn("report_metadata", payload)
            self.assertEqual(payload["report_metadata"]["contract_version"], "d67.v1")
            self.assertEqual(payload["metadata"]["last_completed_phase"], "export_stage1_global_summary")
            self.assertEqual(payload["analysis_summary"]["day_count"], 1)
            self.assertEqual(payload["analysis_summary"]["failed_day_count"], 0)
            self.assertNotIn("governance_alerts", payload)

    def test_global_report_exposes_governance_alerts_only_when_inventory_trend_regresses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            (root / "output").mkdir(parents=True)
            shutil.copy2(RUNNER_SOURCE, root / "tools" / "stage1_d1_d10_runner.ps1")
            (root / "config.yml").write_text(
                "governance:\n"
                "  stage1_runner:\n"
                "    minimum_stable_pass_rate: 85.0\n"
                "    export_contract_version: \"d67.v1\"\n",
                encoding="utf-8",
            )
            (root / "output" / "quality-improvement-archive-latest.json").write_text(
                json.dumps(
                    {
                        "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                        "inventory_trend": {
                            "status": "regressing",
                            "history_points": 4,
                            "missing_contract_delta": 1,
                            "uncategorized_root_script_delta": 0,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = self._run_dry_runner(root)
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            global_reports = sorted((root / "logs" / "stage1").glob("stage1_all_*.json"))
            self.assertTrue(global_reports)
            payload = json.loads(global_reports[-1].read_text(encoding="utf-8-sig"))

            self.assertIn("governance_alerts", payload)
            self.assertEqual(payload["governance_alerts"][0]["alert_type"], "inventory_trend_regressing")
            self.assertEqual(payload["governance_alerts"][0]["recommended_next_target"], "tools/missing_consumer.py")


if __name__ == "__main__":
    unittest.main()