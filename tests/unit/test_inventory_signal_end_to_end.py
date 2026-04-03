import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_SOURCE = REPO_ROOT / "tools" / "quality_feedback.py"
STAGE1_RUNNER_SOURCE = REPO_ROOT / "tools" / "stage1_d1_d10_runner.ps1"
STAGE2_RUNNER_SOURCE = REPO_ROOT / "tools" / "stage2_s2_1_s2_6_runner.ps1"


class TestInventorySignalEndToEnd(unittest.TestCase):
    def _issue_owner(self, item: dict) -> str:
        return str(((item.get("issue_body") or {}).get("summary") or {}).get("owner", "unknown"))

    def _find_issue_by_owner(self, items: list[dict], owner: str) -> dict:
        return next(item for item in items if self._issue_owner(item) == owner)

    def _load_issue_index(self, root: Path, feedback: dict) -> dict:
        return json.loads(Path(feedback["report_metadata"]["issue_index_path"]).read_text(encoding="utf-8"))

    def _prepare_workspace(self, root: Path, archive_latest: dict) -> None:
        (root / "tools").mkdir(parents=True)
        (root / "output").mkdir(parents=True)
        shutil.copy2(FEEDBACK_SOURCE, root / "tools" / "quality_feedback.py")
        shutil.copy2(STAGE1_RUNNER_SOURCE, root / "tools" / "stage1_d1_d10_runner.ps1")
        shutil.copy2(STAGE2_RUNNER_SOURCE, root / "tools" / "stage2_s2_1_s2_6_runner.ps1")
        (root / "config.yml").write_text(
            "governance:\n"
            "  quality_feedback:\n"
            "    minimum_stable_overall_score: 85.0\n"
            "    export_contract_version: \"d77.v1\"\n"
            "  stage1_runner:\n"
            "    minimum_stable_pass_rate: 85.0\n"
            "    export_contract_version: \"d67.v1\"\n"
            "  stage2_runner:\n"
            "    minimum_stable_pass_rate: 85.0\n"
            "    export_contract_version: \"d67.v1\"\n",
            encoding="utf-8",
        )
        (root / "output" / "quality-assessment.json").write_text(
            json.dumps(
                {
                    "overall_score": 95.0,
                    "grade": "A",
                    "failed_dimensions": [],
                    "dimension_scores": {
                        "gate_stability": 100,
                        "test_reliability": 100,
                        "logic_health": 96,
                        "code_health": 94,
                        "architecture_health": 97,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "output" / "continuous-improvement.json").write_text(
            json.dumps(
                {"trend": {"status": "stable", "score_delta": 0.0}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "output" / "quality-consumer-inventory.json").write_text(
            json.dumps(
                {
                    "analysis_summary": {
                        "scanned_consumer_count": 9,
                        "missing_contract_count": 0,
                        "eligible_missing_contract_count": 0,
                        "root_script_observation_count": 1,
                        "root_script_observation_category_counts": {
                            "non_governance_domain_script": 1,
                        },
                    },
                    "recommendation": {"recommended_path": archive_latest.get("inventory_summary", {}).get("recommended_next_target")},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "output" / "quality-improvement-archive-latest.json").write_text(
            json.dumps(archive_latest, ensure_ascii=False),
            encoding="utf-8",
        )

    def _run_feedback(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(root / "tools" / "quality_feedback.py")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def _run_stage1(self, root: Path) -> subprocess.CompletedProcess[str]:
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

    def _run_stage2(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "tools" / "stage2_s2_1_s2_6_runner.ps1"),
                "-All",
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

    def _load_stage_global(self, root: Path, stage_name: str) -> dict:
        return json.loads(sorted((root / "logs" / stage_name).glob(f"{stage_name}_all_*.json"))[-1].read_text(encoding="utf-8-sig"))

    def test_stable_archive_latest_keeps_feedback_and_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {"recommended_next_target": None},
                    "inventory_trend": {
                        "status": "stable",
                        "history_points": 5,
                        "missing_contract_delta": 0,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": False,
                    },
                },
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            issue_index = self._load_issue_index(root, feedback)
            stage1_reports = sorted((root / "logs" / "stage1").glob("stage1_all_*.json"))
            stage2_reports = sorted((root / "logs" / "stage2").glob("stage2_all_*.json"))
            self.assertTrue(stage1_reports)
            self.assertTrue(stage2_reports)
            stage1_global = json.loads(stage1_reports[-1].read_text(encoding="utf-8-sig"))
            stage2_global = json.loads(stage2_reports[-1].read_text(encoding="utf-8-sig"))

            self.assertEqual(feedback["inventory_trend"]["status"], "stable")
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in issue_index["items"]))
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_stable_archive_latest_with_target_change_still_keeps_governance_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                    "inventory_trend": {
                        "status": "stable",
                        "history_points": 5,
                        "missing_contract_delta": 0,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": True,
                    },
                },
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            issue_index = self._load_issue_index(root, feedback)
            feedback_markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_trend"]["status"], "stable")
            self.assertTrue(feedback["inventory_trend"]["recommended_next_target_changed"])
            self.assertEqual(feedback["inventory_summary"]["recommended_next_target"], "tools/missing_consumer.py")
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in issue_index["items"]))
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", feedback_markdown)
            self.assertNotIn("quality_consumer_inventory_trend", feedback_markdown)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_improving_archive_latest_with_target_change_still_keeps_governance_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                    "inventory_trend": {
                        "status": "improving",
                        "history_points": 5,
                        "missing_contract_delta": -1,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": True,
                    },
                },
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            issue_index = self._load_issue_index(root, feedback)
            feedback_markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_trend"]["status"], "improving")
            self.assertTrue(feedback["inventory_trend"]["recommended_next_target_changed"])
            self.assertEqual(feedback["inventory_summary"]["recommended_next_target"], "tools/missing_consumer.py")
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in issue_index["items"]))
            self.assertIn("- Status: improving", feedback_markdown)
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", feedback_markdown)
            self.assertNotIn("quality_consumer_inventory_trend", feedback_markdown)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_improving_archive_latest_with_target_cleared_still_keeps_governance_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {
                        "recommended_next_target": None,
                        "previous_recommended_next_target": "tools/missing_consumer.py",
                        "current_recommended_next_target": None,
                    },
                    "inventory_trend": {
                        "status": "improving",
                        "history_points": 5,
                        "missing_contract_delta": -1,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": True,
                        "previous_recommended_next_target": "tools/missing_consumer.py",
                        "current_recommended_next_target": None,
                    },
                },
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            issue_index = self._load_issue_index(root, feedback)
            feedback_markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_trend"]["status"], "improving")
            self.assertTrue(feedback["inventory_trend"]["recommended_next_target_changed"])
            self.assertIsNone(feedback["inventory_summary"]["recommended_next_target"])
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in issue_index["items"]))
            self.assertIn("- Status: improving", feedback_markdown)
            self.assertIn("- Recommended Next Target: none", feedback_markdown)
            self.assertNotIn("quality_consumer_inventory_trend", feedback_markdown)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_improving_archive_latest_with_residual_missing_contract_keeps_feedback_loud_but_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                    "inventory_trend": {
                        "status": "improving",
                        "history_points": 5,
                        "missing_contract_delta": -1,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": True,
                    },
                },
            )

            inventory_path = root / "output" / "quality-consumer-inventory.json"
            inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory_payload.setdefault("analysis_summary", {})["missing_contract_count"] = 1
            inventory_payload["analysis_summary"]["eligible_missing_contract_count"] = 1
            inventory_payload.setdefault("recommendation", {})["recommended_path"] = "tools/missing_consumer.py"
            inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False), encoding="utf-8")

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            feedback_markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            issue_index = json.loads((root / "output" / "quality-feedback-issues.json").read_text(encoding="utf-8"))
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_summary"]["status"], "critical")
            self.assertEqual(feedback["inventory_trend"]["status"], "improving")
            self.assertTrue(feedback["inventory_trend"]["recommended_next_target_changed"])
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in feedback["priority_actions"]))
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in issue_index["items"]))
            self.assertIn("- Status: improving", feedback_markdown)
            self.assertIn("- Missing Contracts: 1", feedback_markdown)
            self.assertIn("补齐缺失合同的质量消费者", feedback_markdown)
            self.assertNotIn("quality_consumer_inventory_trend", feedback_markdown)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_improving_archive_latest_with_residual_uncategorized_root_script_keeps_feedback_loud_but_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {"recommended_next_target": None},
                    "inventory_trend": {
                        "status": "improving",
                        "history_points": 5,
                        "missing_contract_delta": 0,
                        "uncategorized_root_script_delta": -1,
                        "recommended_next_target_changed": False,
                    },
                },
            )

            inventory_path = root / "output" / "quality-consumer-inventory.json"
            inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory_payload.setdefault("analysis_summary", {})["root_script_observation_count"] = 1
            inventory_payload["analysis_summary"]["root_script_observation_category_counts"] = {
                "uncategorized_root_script": 1,
            }
            inventory_payload.setdefault("recommendation", {})["recommended_path"] = None
            inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False), encoding="utf-8")

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            feedback_markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            issue_index = json.loads((root / "output" / "quality-feedback-issues.json").read_text(encoding="utf-8"))
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_summary"]["status"], "attention")
            self.assertEqual(feedback["inventory_trend"]["status"], "improving")
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in feedback["priority_actions"]))
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            governance_item = self._find_issue_by_owner(issue_index["items"], "quality-governance")
            self.assertIsNone(governance_item["issue_body"]["inventory_trend"])
            self.assertTrue(
                any(
                    "未归类的根目录脚本补齐 observation 分类" in item["action"]
                    for item in governance_item["issue_body"]["action_items"]
                )
            )
            self.assertIn("- Status: improving", feedback_markdown)
            self.assertIn("为未归类的根目录脚本补齐 observation 分类", feedback_markdown)
            self.assertNotIn("quality_consumer_inventory_trend", feedback_markdown)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_improving_archive_latest_with_mixed_residual_risk_keeps_feedback_loud_but_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "stable",
                    "trend_delta": 0.0,
                    "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                    "inventory_trend": {
                        "status": "improving",
                        "history_points": 5,
                        "missing_contract_delta": -1,
                        "uncategorized_root_script_delta": -1,
                        "recommended_next_target_changed": True,
                    },
                },
            )

            inventory_path = root / "output" / "quality-consumer-inventory.json"
            inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory_payload.setdefault("analysis_summary", {})["missing_contract_count"] = 1
            inventory_payload["analysis_summary"]["eligible_missing_contract_count"] = 1
            inventory_payload["analysis_summary"]["root_script_observation_count"] = 1
            inventory_payload["analysis_summary"]["root_script_observation_category_counts"] = {
                "uncategorized_root_script": 1,
            }
            inventory_payload.setdefault("recommendation", {})["recommended_path"] = "tools/missing_consumer.py"
            inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False), encoding="utf-8")

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            issue_index = json.loads((root / "output" / "quality-feedback-issues.json").read_text(encoding="utf-8"))
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_summary"]["status"], "critical")
            self.assertEqual(feedback["inventory_trend"]["status"], "improving")
            self.assertEqual(len([item for item in feedback["priority_actions"] if item["dimension"] == "quality_consumer_inventory"]), 2)
            governance_item = self._find_issue_by_owner(issue_index["items"], "quality-governance")
            self.assertEqual(governance_item["issue_body"]["inventory_context"]["status"], "improving")
            self.assertIsNone(governance_item["issue_body"]["inventory_trend"])
            self.assertEqual(governance_item["issue_body"]["action_items"][0]["priority"], "P0")
            self.assertIn("补齐缺失合同的质量消费者", governance_item["issue_body"]["action_items"][0]["action"])
            self.assertEqual(governance_item["issue_body"]["action_items"][1]["priority"], "P1")
            self.assertIn("未归类的根目录脚本补齐 observation 分类", governance_item["issue_body"]["action_items"][1]["action"])
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_trend_only_regressing_archive_latest_raises_feedback_and_runner_signals_together(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(
                root,
                {
                    "trend_status": "regressing",
                    "trend_delta": -1.0,
                    "inventory_summary": {"recommended_next_target": "tools/missing_consumer.py"},
                    "inventory_trend": {
                        "status": "regressing",
                        "history_points": 5,
                        "missing_contract_delta": 1,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": True,
                    },
                },
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            feedback = json.loads((root / "output" / "quality-feedback.json").read_text(encoding="utf-8"))
            feedback_markdown = (root / "output" / "quality-feedback.md").read_text(encoding="utf-8")
            stage1_global = self._load_stage_global(root, "stage1")
            stage2_global = self._load_stage_global(root, "stage2")

            self.assertEqual(feedback["inventory_trend"]["status"], "regressing")
            self.assertEqual(feedback["inventory_summary"]["status"], "healthy")
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback["priority_actions"]))
            self.assertNotIn("issue_drafts", feedback)
            issue_index = self._load_issue_index(root, feedback)
            self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in issue_index["items"]))
            self.assertEqual(
                [item["owner"] for item in feedback["owner_notifications"]],
                ["quality-governance"],
            )
            self.assertEqual(
                [item["dimension"] for item in feedback["owner_notifications"][0]["todos"]],
                ["quality_consumer_inventory_trend"],
            )
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", feedback_markdown)
            self.assertIn("- quality-governance: 1 items", feedback_markdown)
            self.assertIn("  - [P1] quality_consumer_inventory_trend: inventory 历史趋势出现回退", feedback_markdown)
            self.assertIn("governance_alerts", stage1_global)
            self.assertIn("governance_alerts", stage2_global)
            self.assertEqual(stage1_global["governance_alerts"][0]["alert_type"], "inventory_trend_regressing")
            self.assertEqual(stage2_global["governance_alerts"][0]["recommended_next_target"], "tools/missing_consumer.py")


if __name__ == "__main__":
    unittest.main()