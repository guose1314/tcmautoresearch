import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SOURCE = REPO_ROOT / "tools" / "stage2_s2_1_s2_6_runner.ps1"


class TestStage2RunnerContract(unittest.TestCase):
    def _run_runner(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "tools" / "stage2_s2_1_s2_6_runner.ps1"),
                *args,
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

    def test_stage_report_includes_governance_contract(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            shutil.copy2(RUNNER_SOURCE, root / "tools" / "stage2_s2_1_s2_6_runner.ps1")
            (root / "config.yml").write_text(
                "governance:\n"
                "  stage2_runner:\n"
                "    minimum_stable_pass_rate: 85.0\n"
                "    export_contract_version: \"d67.v1\"\n",
                encoding="utf-8",
            )

            result = self._run_runner(root, "-Stage", "S2-1", "-DryRun")
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            reports = sorted((root / "logs" / "stage2").glob("stage2_S2-1_*.json"))
            self.assertTrue(reports)
            payload = json.loads(reports[-1].read_text(encoding="utf-8-sig"))

            self.assertIn("metadata", payload)
            self.assertIn("analysis_summary", payload)
            self.assertIn("failed_operations", payload)
            self.assertIn("report_metadata", payload)
            self.assertEqual(payload["report_metadata"]["contract_version"], "d67.v1")
            self.assertEqual(payload["metadata"]["last_completed_phase"], "export_stage2_stage_summary")
            self.assertEqual(payload["analysis_summary"]["dry_run"], True)
            self.assertNotIn("governance_alerts", payload)

    def test_global_report_includes_governance_contract(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            shutil.copy2(RUNNER_SOURCE, root / "tools" / "stage2_s2_1_s2_6_runner.ps1")
            (root / "config.yml").write_text(
                "governance:\n"
                "  stage2_runner:\n"
                "    minimum_stable_pass_rate: 85.0\n"
                "    export_contract_version: \"d67.v1\"\n",
                encoding="utf-8",
            )

            result = self._run_runner(root, "-All", "-DryRun")
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            reports = sorted((root / "logs" / "stage2").glob("stage2_all_*.json"))
            self.assertTrue(reports)
            payload = json.loads(reports[-1].read_text(encoding="utf-8-sig"))

            self.assertIn("metadata", payload)
            self.assertIn("analysis_summary", payload)
            self.assertIn("failed_operations", payload)
            self.assertIn("report_metadata", payload)
            self.assertEqual(payload["report_metadata"]["contract_version"], "d67.v1")
            self.assertEqual(payload["metadata"]["last_completed_phase"], "export_stage2_global_summary")
            self.assertEqual(payload["analysis_summary"]["stage_count"], 6)
            self.assertEqual(payload["analysis_summary"]["failed_stage_count"], 0)
            self.assertNotIn("governance_alerts", payload)

    def test_global_report_exposes_governance_alerts_only_when_inventory_trend_regresses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir(parents=True)
            (root / "output").mkdir(parents=True)
            shutil.copy2(RUNNER_SOURCE, root / "tools" / "stage2_s2_1_s2_6_runner.ps1")
            (root / "config.yml").write_text(
                "governance:\n"
                "  stage2_runner:\n"
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
                            "history_points": 5,
                            "missing_contract_delta": 2,
                            "uncategorized_root_script_delta": 1,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = self._run_runner(root, "-All", "-DryRun")
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

            reports = sorted((root / "logs" / "stage2").glob("stage2_all_*.json"))
            self.assertTrue(reports)
            payload = json.loads(reports[-1].read_text(encoding="utf-8-sig"))

            self.assertIn("governance_alerts", payload)
            self.assertEqual(payload["governance_alerts"][0]["alert_type"], "inventory_trend_regressing")
            self.assertEqual(payload["governance_alerts"][0]["history_points"], 5)


if __name__ == "__main__":
    unittest.main()