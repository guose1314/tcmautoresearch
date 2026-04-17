import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_FILES = [
    "code_quality_checks.py",
    "continuous_improvement_loop.py",
    "cypher_injection_scan.py",
    "generate_dependency_graph.py",
    "logic_checks.py",
    "quality_assessment.py",
    "quality_consumer_inventory.py",
    "quality_feedback.py",
    "quality_gate.py",
    "quality_improvement_archive.py",
]
RUNNER_FILES = [
    "stage1_d1_d10_runner.ps1",
    "stage2_s2_1_s2_6_runner.ps1",
]
DEFAULT_TEST_MODULES = [
    "tests.unit.test_logic_checks",
    "tests.unit.test_code_quality_checks",
    "tests.unit.test_continuous_improvement_loop",
    "tests.unit.test_dependency_graph_tool",
    "tests.unit.test_quality_assessment",
    "tests.unit.test_quality_improvement_archive",
    "tests.unit.test_quality_feedback",
    "tests.unit.test_quality_consumer_inventory",
]


class TestInventorySignalQualityGateReplay(unittest.TestCase):
    def _issue_owner(self, item: dict) -> str:
        return str(((item.get("issue_body") or {}).get("summary") or {}).get("owner", "unknown"))

    def _issue_reference(self, item: dict, key: str, default=None):
        artifact_references = ((item.get("issue_body") or {}).get("artifact_references") or {})
        return artifact_references.get(key, default)

    def _load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _load_stage_global(self, root: Path, stage_name: str) -> dict:
        return json.loads(sorted((root / "logs" / stage_name).glob(f"{stage_name}_all_*.json"))[-1].read_text(encoding="utf-8-sig"))

    def _load_dossier_text(self, archive_payload: dict) -> str:
        dossier_path = Path(archive_payload["report_metadata"]["dossier_path"])
        return self._load_text(dossier_path)

    def _load_issue_index(self, feedback_payload: dict) -> dict:
        issue_index_path = Path(feedback_payload["report_metadata"]["issue_index_path"])
        return self._load_json(issue_index_path)

    def _load_issue_draft_texts(self, issue_index_payload: dict) -> dict[str, str]:
        draft_texts: dict[str, str] = {}
        for item in issue_index_payload.get("items", []):
            owner = self._issue_owner(item)
            draft_path = Path(str(self._issue_reference(item, "issue_draft_file", "")))
            draft_texts[owner] = self._load_text(draft_path)
        return draft_texts

    def _assert_issue_reference_order_isomorphic(self, feedback_payload: dict, issue_index_payload: dict) -> None:
        self.assertNotIn("issue_index_payload", feedback_payload)
        self.assertNotIn("issue_drafts", feedback_payload)
        self.assertNotIn("issue_draft_count", feedback_payload.get("analysis_summary") or {})
        self.assertNotIn("report_metadata", issue_index_payload)
        removed_feedback_metadata_keys = [
            "issue_draft_bodies",
            "issue_draft_owners",
            "issue_draft_titles",
            "issue_draft_files",
            "issue_draft_templates",
            "issue_draft_labels",
            "issue_draft_index_positions",
            "issue_draft_quality_scores",
            "issue_draft_trend_statuses",
            "issue_draft_inventory_trend_statuses",
            "issue_draft_inventory_history_points",
            "issue_draft_inventory_missing_contract_deltas",
            "issue_draft_inventory_uncategorized_root_script_deltas",
            "issue_draft_inventory_recommended_next_targets",
            "issue_draft_action_items",
            "issue_draft_acceptance_checks",
        ]
        for item in issue_index_payload.get("items", []):
            self.assertNotIn("owner", item)
            self.assertNotIn("title", item)
            self.assertNotIn("template", item)
            self.assertNotIn("labels", item)
            self.assertNotIn("file", item)
            self.assertNotIn("index_position", item)

        for key in removed_feedback_metadata_keys:
            self.assertNotIn(key, feedback_payload.get("report_metadata") or {})

    def _assert_multimodule_metadata_reference_lists(self, outputs: dict) -> None:
        gate_payload = outputs["gate"]
        improvement_payload = outputs["improvement"]
        archive_payload = outputs["archive"]

        improvement_metadata = improvement_payload.get("report_metadata") or {}
        self.assertEqual(improvement_metadata.get("artifact_reference_labels", []), ["history", "output"])
        self.assertEqual(
            improvement_metadata.get("artifact_reference_paths", []),
            [
                str(improvement_metadata.get("history_path", "")).replace("\\", "/"),
                str(improvement_metadata.get("output_path", "")).replace("\\", "/"),
            ],
        )

        archive_metadata = archive_payload.get("report_metadata") or {}
        self.assertEqual(archive_metadata.get("artifact_reference_labels", []), ["history", "latest_output", "dossier"])
        self.assertEqual(
            archive_metadata.get("artifact_reference_paths", []),
            [
                str(archive_metadata.get("history_path", "")).replace("\\", "/"),
                str(archive_metadata.get("latest_output_path", "")).replace("\\", "/"),
                str(archive_metadata.get("dossier_path", "")).replace("\\", "/"),
            ],
        )

        gate_metadata = gate_payload.get("report_metadata") or {}
        gate_results = gate_payload.get("results", [])
        self.assertEqual(gate_metadata.get("gate_names", []), [item["name"] for item in gate_results])

        artifact_pairs = dict(
            zip(
                gate_metadata.get("artifact_reference_labels", []),
                gate_metadata.get("artifact_reference_paths", []),
            )
        )
        self.assertEqual(
            artifact_pairs.get("dependency_graph.outputs.json"),
            "docs/architecture/dependency-graph.json",
        )
        self.assertEqual(
            artifact_pairs.get("dependency_graph.outputs.mermaid"),
            "docs/architecture/dependency-graph.mmd",
        )
        self.assertEqual(
            artifact_pairs.get("dependency_graph.outputs.markdown"),
            "docs/architecture/dependency-graph.md",
        )
        self.assertEqual(
            artifact_pairs.get("quality_consumer_inventory.inventory_report"),
            "output/quality-consumer-inventory.json",
        )
        self.assertEqual(
            artifact_pairs.get("continuous_improvement.continuous_report"),
            "output/continuous-improvement.json",
        )
        self.assertEqual(
            artifact_pairs.get("continuous_improvement.history_file"),
            "output/quality-history.jsonl",
        )
        self.assertEqual(
            artifact_pairs.get("quality_improvement_archive.history_file"),
            "output/quality-improvement-archive.jsonl",
        )
        self.assertEqual(
            artifact_pairs.get("quality_improvement_archive.latest_file"),
            "output/quality-improvement-archive-latest.json",
        )
        self.assertTrue(
            str(artifact_pairs.get("quality_improvement_archive.dossier_file", "")).startswith("docs/quality-archive/quality-improvement-")
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_json"),
            "output/quality-feedback.json",
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_markdown"),
            "output/quality-feedback.md",
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_issue_index"),
            "output/quality-feedback-issues.json",
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_issue_dir"),
            "output/quality-feedback-issues",
        )

    def _to_root_relative_path(self, root: Path, path_value: str | None) -> str | None:
        if not path_value:
            return None
        path = Path(str(path_value))
        if not path.is_absolute():
            return str(path).replace("\\", "/")
        return str(path.relative_to(root)).replace("\\", "/")

    def _assert_gate_artifact_identity_isomorphic(self, root: Path, outputs: dict) -> None:
        gate_metadata = (outputs["gate"].get("report_metadata") or {})
        assessment_metadata = (outputs["assessment"].get("report_metadata") or {})
        improvement_metadata = (outputs["improvement"].get("report_metadata") or {})
        archive_metadata = (outputs["archive"].get("report_metadata") or {})
        feedback_metadata = (outputs["feedback"].get("report_metadata") or {})

        artifact_pairs = dict(
            zip(
                gate_metadata.get("artifact_reference_labels", []),
                gate_metadata.get("artifact_reference_paths", []),
            )
        )

        self.assertEqual(
            artifact_pairs.get("quality_assessment.assessment_report"),
            self._to_root_relative_path(root, assessment_metadata.get("output_path")),
        )
        self.assertEqual(
            artifact_pairs.get("continuous_improvement.continuous_report"),
            self._to_root_relative_path(root, improvement_metadata.get("output_path")),
        )
        self.assertEqual(
            artifact_pairs.get("continuous_improvement.history_file"),
            self._to_root_relative_path(root, improvement_metadata.get("history_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_improvement_archive.history_file"),
            self._to_root_relative_path(root, archive_metadata.get("history_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_improvement_archive.latest_file"),
            self._to_root_relative_path(root, archive_metadata.get("latest_output_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_improvement_archive.dossier_file"),
            self._to_root_relative_path(root, archive_metadata.get("dossier_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_json"),
            self._to_root_relative_path(root, feedback_metadata.get("output_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_markdown"),
            self._to_root_relative_path(root, feedback_metadata.get("markdown_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_issue_index"),
            self._to_root_relative_path(root, feedback_metadata.get("issue_index_path")),
        )
        self.assertEqual(
            artifact_pairs.get("quality_feedback.feedback_issue_dir"),
            self._to_root_relative_path(root, feedback_metadata.get("issue_dir")),
        )

    def _assert_export_phase_details_isomorphic(self, outputs: dict) -> None:
        assessment_metadata = outputs["assessment"].get("metadata") or {}
        improvement_metadata = outputs["improvement"].get("metadata") or {}
        archive_metadata = outputs["archive"].get("metadata") or {}
        feedback_metadata = outputs["feedback"].get("metadata") or {}
        gate_metadata = outputs["gate"].get("metadata") or {}

        assessment_report_metadata = outputs["assessment"].get("report_metadata") or {}
        improvement_report_metadata = outputs["improvement"].get("report_metadata") or {}
        archive_report_metadata = outputs["archive"].get("report_metadata") or {}
        feedback_report_metadata = outputs["feedback"].get("report_metadata") or {}
        gate_report_metadata = outputs["gate"].get("report_metadata") or {}

        self.assertEqual(
            assessment_metadata.get("phase_history", [])[-1]["details"]["output_path"],
            assessment_report_metadata.get("output_path"),
        )
        self.assertEqual(
            improvement_metadata.get("phase_history", [])[-1]["details"]["history_path"],
            improvement_report_metadata.get("history_path"),
        )
        self.assertEqual(
            improvement_metadata.get("phase_history", [])[-1]["details"]["output_path"],
            improvement_report_metadata.get("output_path"),
        )
        self.assertEqual(
            archive_metadata.get("phase_history", [])[-1]["details"]["history_path"],
            archive_report_metadata.get("history_path"),
        )
        self.assertEqual(
            archive_metadata.get("phase_history", [])[-1]["details"]["latest_output"],
            archive_report_metadata.get("latest_output_path"),
        )
        self.assertEqual(
            archive_metadata.get("phase_history", [])[-1]["details"]["dossier_path"],
            archive_report_metadata.get("dossier_path"),
        )
        self.assertEqual(
            feedback_metadata.get("phase_history", [])[-1]["details"]["output_path"],
            feedback_report_metadata.get("output_path"),
        )
        self.assertEqual(
            feedback_metadata.get("phase_history", [])[-1]["details"]["markdown_path"],
            feedback_report_metadata.get("markdown_path"),
        )
        self.assertEqual(
            feedback_metadata.get("phase_history", [])[-1]["details"]["issue_dir"],
            feedback_report_metadata.get("issue_dir"),
        )
        self.assertEqual(
            feedback_metadata.get("phase_history", [])[-1]["details"]["issue_index"],
            feedback_report_metadata.get("issue_index_path"),
        )
        self.assertNotIn("issue_draft_count", feedback_metadata.get("phase_history", [])[-1]["details"])
        self.assertEqual(
            gate_metadata.get("phase_history", [])[-1]["details"]["output_path"],
            gate_report_metadata.get("output_path"),
        )

    def _assert_human_readable_artifact_references_isomorphic(self, outputs: dict) -> None:
        archive_report_metadata = outputs["archive"].get("report_metadata") or {}
        feedback_report_metadata = outputs["feedback"].get("report_metadata") or {}
        feedback_markdown = outputs["feedback_markdown"]
        dossier_text = outputs["dossier"]

        self.assertIn("## Artifact References", feedback_markdown)
        self.assertIn(
            "- Feedback JSON: {0}".format(feedback_report_metadata.get("output_path", "")),
            feedback_markdown,
        )
        self.assertIn(
            "- Feedback Markdown: {0}".format(feedback_report_metadata.get("markdown_path", "")),
            feedback_markdown,
        )
        self.assertIn(
            "- Issue Index: {0}".format(feedback_report_metadata.get("issue_index_path", "")),
            feedback_markdown,
        )
        self.assertIn(
            "- Issue Directory: {0}".format(feedback_report_metadata.get("issue_dir", "")),
            feedback_markdown,
        )
        for item in outputs["issue_index"].get("items", []):
            draft_file = self._issue_reference(item, "issue_draft_file", "")
            if draft_file:
                self.assertIn("  - {0}".format(draft_file), feedback_markdown)

        self.assertIn("## Artifact References", dossier_text)
        self.assertIn(
            "- History Path: {0}".format(archive_report_metadata.get("history_path", "")),
            dossier_text,
        )
        self.assertIn(
            "- Latest Output Path: {0}".format(archive_report_metadata.get("latest_output_path", "")),
            dossier_text,
        )
        self.assertIn(
            "- Dossier Path: {0}".format(archive_report_metadata.get("dossier_path", "")),
            dossier_text,
        )

    def _assert_issue_body_artifact_references_isomorphic(self, outputs: dict) -> None:
        issue_index_payload = outputs["issue_index"]
        feedback_report_metadata = (outputs["feedback"].get("report_metadata") or {})
        draft_texts = outputs["issue_drafts"]

        for item in issue_index_payload.get("items", []):
            owner = self._issue_owner(item)
            draft_text = draft_texts[owner]
            issue_body = item.get("issue_body", {})
            summary = issue_body.get("summary", {})
            self.assertIn("## Summary", draft_text)
            self.assertIn("- Owner: {0}".format(summary.get("owner", "unknown")), draft_text)
            self.assertIn("- Quality Score: {0}".format(summary.get("quality_score", 0.0)), draft_text)
            self.assertIn("- Trend: {0}".format(summary.get("trend_status", "unknown")), draft_text)
            self.assertNotIn("quality_score", item)
            self.assertNotIn("trend_status", item)
            self.assertNotIn("inventory_trend_status", item)
            self.assertNotIn("inventory_history_points", item)
            self.assertNotIn("inventory_missing_contract_delta", item)
            self.assertNotIn("inventory_uncategorized_root_script_delta", item)
            self.assertNotIn("inventory_recommended_next_target", item)
            self.assertNotIn("action_items", item)
            self.assertNotIn("acceptance_checks", item)
            for action_item in issue_body.get("action_items", []):
                self.assertIn(
                    "- [{priority}] {dimension}: {action} (score={score})".format(**action_item),
                    draft_text,
                )
            for acceptance_check in issue_body.get("acceptance_checks", []):
                self.assertIn(
                    "- [ ] {0}".format(acceptance_check.get("text", "")),
                    draft_text,
                )
            inventory_trend = issue_body.get("inventory_trend")
            if inventory_trend is not None:
                self.assertIn("## Inventory Trend", draft_text)
                self.assertIn(
                    "- Status: {0}".format(inventory_trend.get("status", "unknown")),
                    draft_text,
                )
                self.assertIn(
                    "- History Points: {0}".format(inventory_trend.get("history_points", 0)),
                    draft_text,
                )
                self.assertIn(
                    "- Missing Contract Delta: {0}".format(inventory_trend.get("missing_contract_delta", 0)),
                    draft_text,
                )
                self.assertIn(
                    "- Uncategorized Root Script Delta: {0}".format(
                        inventory_trend.get("uncategorized_root_script_delta", 0)
                    ),
                    draft_text,
                )
                self.assertIn(
                    "- Recommended Next Target: {0}".format(inventory_trend.get("recommended_next_target", "none")),
                    draft_text,
                )
            else:
                self.assertNotIn("## Inventory Trend", draft_text)
            artifact_references = issue_body.get("artifact_references", {})
            self.assertIn("## Artifact References", draft_text)
            self.assertIn(
                "- Issue Index: {0}".format(feedback_report_metadata.get("issue_index_path", "")),
                draft_text,
            )
            self.assertEqual(
                artifact_references.get("issue_index_path", ""),
                feedback_report_metadata.get("issue_index_path", ""),
            )
            self.assertEqual(
                artifact_references.get("issue_dir", ""),
                feedback_report_metadata.get("issue_dir", ""),
            )
            self.assertEqual(artifact_references.get("issue_draft_file", ""), self._issue_reference(item, "issue_draft_file", ""))
            self.assertEqual(artifact_references.get("owner", ""), self._issue_owner(item))
            self.assertEqual(artifact_references.get("title", ""), self._issue_reference(item, "title", ""))
            self.assertEqual(artifact_references.get("template", ""), self._issue_reference(item, "template", ""))
            self.assertEqual(artifact_references.get("labels", []), self._issue_reference(item, "labels", []))
            self.assertEqual(artifact_references.get("index_position", 0), self._issue_reference(item, "index_position", 0))

    def _copy_tools(self, root: Path) -> None:
        (root / "tools").mkdir(parents=True, exist_ok=True)
        (root / "tools" / "__init__.py").write_text("", encoding="utf-8")
        for name in [*TOOL_FILES, *RUNNER_FILES]:
            shutil.copy2(REPO_ROOT / "tools" / name, root / "tools" / name)

    def _write_minimal_source_tree(self, root: Path) -> None:
        (root / "src" / "core").mkdir(parents=True, exist_ok=True)
        (root / "src" / "research").mkdir(parents=True, exist_ok=True)
        (root / "src" / "storage").mkdir(parents=True, exist_ok=True)
        (root / "src" / "core" / "module_base.py").write_text(
            "class BaseModule:\n    pass\n",
            encoding="utf-8",
        )
        (root / "src" / "research" / "pipeline.py").write_text(
            "from src.core.module_base import BaseModule\n\n\nclass ResearchPipeline(BaseModule):\n    pass\n",
            encoding="utf-8",
        )
        (root / "src" / "storage" / "neo4j_driver.py").write_text(
            "# Minimal stub for cypher injection scan target\n",
            encoding="utf-8",
        )

    def _write_default_unit_tests(self, root: Path) -> None:
        (root / "tests" / "unit").mkdir(parents=True, exist_ok=True)
        (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (root / "tests" / "unit" / "__init__.py").write_text("", encoding="utf-8")
        for module_name in DEFAULT_TEST_MODULES:
            file_name = module_name.split(".")[-1] + ".py"
            class_name = "Test" + "".join(part.capitalize() for part in file_name.replace(".py", "").split("_"))
            (root / "tests" / "unit" / file_name).write_text(
                "import unittest\n\n\n"
                f"class {class_name}(unittest.TestCase):\n"
                "    def test_ok(self):\n"
                "        self.assertTrue(True)\n\n\n"
                "if __name__ == \"__main__\":\n"
                "    unittest.main()\n",
                encoding="utf-8",
            )

    def _write_config(self, root: Path) -> None:
        (root / "config.yml").write_text(
            "governance:\n"
            "  quality_gate:\n"
            "    minimum_stable_success_rate: 1.0\n"
            "    export_contract_version: \"d63.v1\"\n"
            "  quality_consumer_inventory:\n"
            "    export_contract_version: \"d62.v1\"\n"
            "  continuous_improvement:\n"
            "    export_contract_version: \"d66.v1\"\n"
            "  quality_improvement_archive:\n"
            "    export_contract_version: \"d65.v1\"\n"
            "  quality_feedback:\n"
            "    minimum_stable_overall_score: 85.0\n"
            "    export_contract_version: \"d77.v1\"\n"
            "  stage1_runner:\n"
            "    minimum_stable_pass_rate: 85.0\n"
            "    export_contract_version: \"d67.v1\"\n"
            "  stage2_runner:\n"
            "    minimum_stable_pass_rate: 85.0\n"
            "    export_contract_version: \"d67.v1\"\n"
            "quality_assessment:\n"
            "  min_overall_score: 80\n"
            "  export_contract_version: \"d49.v1\"\n",
            encoding="utf-8",
        )

    def _seed_archive_history(self, root: Path, inventory_trend_status: str) -> None:
        (root / "output").mkdir(parents=True, exist_ok=True)
        (root / "output" / "quality-improvement-archive.jsonl").write_text(
            json.dumps(
                {
                    "inventory_summary": {
                        "missing_contract_count": 0,
                        "root_script_observation_category_counts": {
                            "non_governance_domain_script": 1,
                        },
                        "recommended_next_target": "tools/missing_consumer.py" if inventory_trend_status == "regressing" else None,
                    },
                    "inventory_trend": {
                        "status": inventory_trend_status,
                        "history_points": 2,
                        "missing_contract_delta": 0,
                        "uncategorized_root_script_delta": 0,
                        "recommended_next_target_changed": inventory_trend_status == "regressing",
                    },
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_regressing_consumer(self, root: Path) -> None:
        (root / "tools" / "missing_consumer.py").write_text(
            "from pathlib import Path\n"
            "import json\n\n"
            "payload = json.loads((Path('output') / 'quality-feedback.json').read_text(encoding='utf-8'))\n"
            "(Path('output') / 'consumer-summary.json').write_text(json.dumps({'level': payload.get('feedback_level')}), encoding='utf-8')\n",
            encoding="utf-8",
        )

    def _write_uncategorized_root_script(self, root: Path) -> None:
        (root / "mystery_root_script.py").write_text(
            "from pathlib import Path\n"
            "import json\n\n"
            "Path('output').mkdir(exist_ok=True)\n"
            "(Path('output') / 'mystery-root-script.json').write_text(json.dumps({'status': 'ok'}), encoding='utf-8')\n",
            encoding="utf-8",
        )

    def _prepare_workspace(self, root: Path, scenario: str) -> None:
        self._copy_tools(root)
        self._write_minimal_source_tree(root)
        self._write_default_unit_tests(root)
        self._write_config(root)
        self._seed_archive_history(root, "regressing" if scenario in {"regressing", "uncategorized_regressing"} else "stable")
        if scenario == "regressing":
            self._write_regressing_consumer(root)
        elif scenario == "uncategorized_regressing":
            self._write_uncategorized_root_script(root)

    def _collect_replay_outputs(self, root: Path) -> dict:
        gate_payload = self._load_json(root / "output" / "quality-gate.json")
        assessment_payload = self._load_json(root / "output" / "quality-assessment.json")
        inventory_payload = self._load_json(root / "output" / "quality-consumer-inventory.json")
        improvement_payload = self._load_json(root / "output" / "continuous-improvement.json")
        archive_payload = self._load_json(root / "output" / "quality-improvement-archive-latest.json")
        feedback_payload = self._load_json(root / "output" / "quality-feedback.json")
        issue_index_payload = self._load_issue_index(feedback_payload)
        return {
            "root": root,
            "gate": gate_payload,
            "assessment": assessment_payload,
            "inventory": inventory_payload,
            "improvement": improvement_payload,
            "archive": archive_payload,
            "feedback": feedback_payload,
            "feedback_markdown": self._load_text(Path(feedback_payload["report_metadata"]["markdown_path"])),
            "issue_index": issue_index_payload,
            "issue_drafts": self._load_issue_draft_texts(issue_index_payload),
            "dossier": self._load_dossier_text(archive_payload),
            "stage1": self._load_stage_global(root, "stage1"),
            "stage2": self._load_stage_global(root, "stage2"),
        }

    def _run_full_replay(self, root: Path) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
        gate_result = self._run_quality_gate(root)
        stage1_result = self._run_stage1(root)
        stage2_result = self._run_stage2(root)
        return gate_result, stage1_result, stage2_result

    def _run_quality_gate(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.quality_gate",
                "--root",
                str(root),
                "--report",
                "output/quality-gate.json",
                "--graph-output",
                "docs/architecture",
            ],
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

    def _run_feedback(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(root / "tools" / "quality_feedback.py")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def _inject_quiet_inventory_target_change(
        self,
        root: Path,
        trend_status: str,
        recommended_next_target: str,
        missing_contract_delta: int,
        uncategorized_root_script_delta: int,
    ) -> None:
        inventory_path = root / "output" / "quality-consumer-inventory.json"
        inventory_payload = self._load_json(inventory_path)
        inventory_payload.setdefault("recommendation", {})["recommended_path"] = recommended_next_target
        inventory_payload.setdefault("analysis_summary", {})["recommended_next_target"] = recommended_next_target
        inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        improvement_path = root / "output" / "continuous-improvement.json"
        improvement_payload = self._load_json(improvement_path)
        improvement_payload.setdefault("inventory_focus", {})["trend_status"] = trend_status
        improvement_payload["inventory_focus"]["summary"] = {
            **(improvement_payload["inventory_focus"].get("summary") or {}),
            "recommended_next_target": recommended_next_target,
        }
        improvement_payload["inventory_focus"]["trend"] = {
            **(improvement_payload["inventory_focus"].get("trend") or {}),
            "status": trend_status,
            "history_points": 3,
            "missing_contract_delta": missing_contract_delta,
            "uncategorized_root_script_delta": uncategorized_root_script_delta,
            "recommended_next_target_changed": True,
        }
        improvement_payload["inventory_focus"]["actions"] = []
        improvement_payload.setdefault("next_cycle_targets", {})["inventory_trend_status"] = trend_status
        improvement_payload["next_cycle_targets"]["inventory_recommended_next_target"] = recommended_next_target
        improvement_path.write_text(json.dumps(improvement_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        archive_path = root / "output" / "quality-improvement-archive-latest.json"
        archive_payload = self._load_json(archive_path)
        archive_payload.setdefault("inventory_summary", {})["recommended_next_target"] = recommended_next_target
        archive_payload.setdefault("inventory_trend", {}).update(
            {
                "status": trend_status,
                "history_points": int((archive_payload.get("inventory_trend") or {}).get("history_points", 3) or 3),
                "missing_contract_delta": missing_contract_delta,
                "uncategorized_root_script_delta": uncategorized_root_script_delta,
                "recommended_next_target_changed": True,
                "previous_recommended_next_target": None,
                "current_recommended_next_target": recommended_next_target,
            }
        )
        archive_payload.setdefault("analysis_summary", {})["inventory_trend_status"] = trend_status
        archive_payload.setdefault("next_cycle_targets", {})["inventory_trend_status"] = trend_status
        archive_payload["next_cycle_targets"]["inventory_recommended_next_target"] = recommended_next_target
        archive_path.write_text(json.dumps(archive_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        dossier_path = Path(str((archive_payload.get("report_metadata") or {}).get("dossier_path", "")))
        dossier_text = self._load_text(dossier_path)
        dossier_text = dossier_text.replace("- Recommended Next Target: none", f"- Recommended Next Target: {recommended_next_target}")
        dossier_text = dossier_text.replace("- Trend Status: stable", f"- Trend Status: {trend_status}")
        dossier_text = dossier_text.replace("- Missing Contract Delta: 0", f"- Missing Contract Delta: {missing_contract_delta}")
        dossier_text = dossier_text.replace("- Uncategorized Root Script Delta: 0", f"- Uncategorized Root Script Delta: {uncategorized_root_script_delta}")
        dossier_text = dossier_text.replace("- Recommended Next Target Changed: False", "- Recommended Next Target Changed: True")
        dossier_path.write_text(dossier_text, encoding="utf-8")

    def _inject_inventory_snapshot_risk(
        self,
        root: Path,
        missing_contract_count: int,
        recommended_next_target: str | None,
    ) -> None:
        inventory_path = root / "output" / "quality-consumer-inventory.json"
        inventory_payload = self._load_json(inventory_path)
        analysis_summary = inventory_payload.setdefault("analysis_summary", {})
        analysis_summary["missing_contract_count"] = missing_contract_count
        analysis_summary["eligible_missing_contract_count"] = missing_contract_count
        analysis_summary["recommended_next_target"] = recommended_next_target
        inventory_payload.setdefault("recommendation", {})["recommended_path"] = recommended_next_target
        inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        archive_path = root / "output" / "quality-improvement-archive-latest.json"
        archive_payload = self._load_json(archive_path)
        archive_payload.setdefault("inventory_summary", {})["missing_contract_count"] = missing_contract_count
        archive_payload["inventory_summary"]["recommended_next_target"] = recommended_next_target
        archive_path.write_text(json.dumps(archive_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        dossier_path = Path(str((archive_payload.get("report_metadata") or {}).get("dossier_path", "")))
        dossier_text = self._load_text(dossier_path)
        dossier_text = dossier_text.replace("- Missing Contracts: 0", f"- Missing Contracts: {missing_contract_count}")
        dossier_text = dossier_text.replace(
            "- Recommended Next Target: none",
            f"- Recommended Next Target: {recommended_next_target or 'none'}",
        )
        dossier_path.write_text(dossier_text, encoding="utf-8")

    def _inject_uncategorized_snapshot_risk(
        self,
        root: Path,
        uncategorized_root_script_count: int,
        recommended_next_target: str | None = None,
    ) -> None:
        inventory_path = root / "output" / "quality-consumer-inventory.json"
        inventory_payload = self._load_json(inventory_path)
        analysis_summary = inventory_payload.setdefault("analysis_summary", {})
        analysis_summary["root_script_observation_count"] = uncategorized_root_script_count
        analysis_summary["root_script_observation_category_counts"] = {
            "uncategorized_root_script": uncategorized_root_script_count,
        }
        analysis_summary["recommended_next_target"] = recommended_next_target
        inventory_payload.setdefault("recommendation", {})["recommended_path"] = recommended_next_target
        inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        archive_path = root / "output" / "quality-improvement-archive-latest.json"
        archive_payload = self._load_json(archive_path)
        archive_payload.setdefault("inventory_summary", {})["recommended_next_target"] = recommended_next_target
        archive_path.write_text(json.dumps(archive_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        dossier_path = Path(str((archive_payload.get("report_metadata") or {}).get("dossier_path", "")))
        dossier_text = self._load_text(dossier_path)
        dossier_text = dossier_text.replace("- Recommended Next Target: none", "- Recommended Next Target: none")
        dossier_path.write_text(dossier_text, encoding="utf-8")

    def test_quality_gate_stable_replay_keeps_nine_endpoints_consistent_and_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "stable")

            gate_result, stage1_result, stage2_result = self._run_full_replay(root)

            self.assertEqual(gate_result.returncode, 0, msg=gate_result.stderr or gate_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            gate_payload = outputs["gate"]
            inventory_payload = outputs["inventory"]
            improvement_payload = outputs["improvement"]
            archive_payload = outputs["archive"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            issue_draft_texts = outputs["issue_drafts"]
            dossier_text = outputs["dossier"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertTrue(gate_payload["overall_success"])
            self.assertEqual(inventory_payload["analysis_summary"]["missing_contract_count"], 0)
            self.assertEqual(improvement_payload["inventory_focus"]["trend_status"], "stable")
            self.assertEqual(archive_payload["inventory_trend"]["status"], "stable")
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "stable")
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            self.assertEqual(issue_index_payload["count"], 1)
            self.assertEqual(self._issue_owner(issue_index_payload["items"][0]), "module-owners")
            self.assertIn("module-owners", issue_draft_texts)
            self.assertIn("## Summary", issue_draft_texts["module-owners"])
            self.assertIn("- Trend: stable", issue_draft_texts["module-owners"])
            self.assertNotIn("## Inventory Trend", issue_draft_texts["module-owners"])
            self.assertIn("## Inventory Trend", dossier_text)
            self.assertIn("- Trend Status: stable", dossier_text)
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback_payload["priority_actions"]))
            self.assertFalse(any(self._issue_owner(item) == "quality-governance" for item in issue_index_payload["items"]))
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_quality_gate_regressing_replay_keeps_nine_endpoints_consistent_and_loud(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "regressing")

            gate_result, stage1_result, stage2_result = self._run_full_replay(root)

            self.assertEqual(gate_result.returncode, 1, msg=gate_result.stderr or gate_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            gate_payload = outputs["gate"]
            inventory_payload = outputs["inventory"]
            improvement_payload = outputs["improvement"]
            archive_payload = outputs["archive"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            issue_draft_texts = outputs["issue_drafts"]
            dossier_text = outputs["dossier"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertFalse(gate_payload["overall_success"])
            self.assertEqual(inventory_payload["analysis_summary"]["missing_contract_count"], 1)
            self.assertEqual(improvement_payload["inventory_focus"]["trend_status"], "regressing")
            self.assertEqual(archive_payload["inventory_trend"]["status"], "regressing")
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "regressing")
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            self.assertGreaterEqual(issue_index_payload["count"], 2)
            self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in issue_index_payload["items"]))
            self.assertIn("module-owners", issue_draft_texts)
            self.assertIn("## Summary", issue_draft_texts["module-owners"])
            self.assertIn("- Owner: module-owners", issue_draft_texts["module-owners"])
            self.assertIn("- Trend: stable", issue_draft_texts["module-owners"])
            self.assertIn("## Inventory Trend", issue_draft_texts["module-owners"])
            self.assertIn("## Action Items", issue_draft_texts["module-owners"])
            self.assertIn("code_health: 分批拆解高复杂函数并持续降告警。", issue_draft_texts["module-owners"])
            self.assertIn("## Acceptance", issue_draft_texts["module-owners"])
            self.assertIn("quality-governance", issue_draft_texts)
            self.assertIn("## Inventory Trend", issue_draft_texts["quality-governance"])
            self.assertIn("- Status: regressing", issue_draft_texts["quality-governance"])
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", issue_draft_texts["quality-governance"])
            self.assertIn("## Action Items", issue_draft_texts["quality-governance"])
            self.assertIn("## Inventory Trend", dossier_text)
            self.assertIn("- Trend Status: regressing", dossier_text)
            self.assertIn("- Missing Contracts: 1", dossier_text)
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in feedback_payload["priority_actions"]))
            self.assertIn("governance_alerts", stage1_global)
            self.assertIn("governance_alerts", stage2_global)
            self.assertEqual(stage1_global["governance_alerts"][0]["alert_type"], "inventory_trend_regressing")
            self.assertEqual(stage2_global["governance_alerts"][0]["recommended_next_target"], "tools/missing_consumer.py")

    def test_regressing_missing_contract_and_uncategorized_routes_keep_issue_draft_bodies_semantically_split(self):
        with TemporaryDirectory() as missing_tmp, TemporaryDirectory() as uncategorized_tmp:
            missing_root = Path(missing_tmp)
            uncategorized_root = Path(uncategorized_tmp)
            self._prepare_workspace(missing_root, "regressing")
            self._prepare_workspace(uncategorized_root, "uncategorized_regressing")

            missing_gate_result, missing_stage1_result, missing_stage2_result = self._run_full_replay(missing_root)
            uncategorized_gate_result, uncategorized_stage1_result, uncategorized_stage2_result = self._run_full_replay(uncategorized_root)

            self.assertEqual(missing_gate_result.returncode, 1, msg=missing_gate_result.stderr or missing_gate_result.stdout)
            self.assertEqual(missing_stage1_result.returncode, 0, msg=missing_stage1_result.stderr or missing_stage1_result.stdout)
            self.assertEqual(missing_stage2_result.returncode, 0, msg=missing_stage2_result.stderr or missing_stage2_result.stdout)
            self.assertEqual(uncategorized_gate_result.returncode, 1, msg=uncategorized_gate_result.stderr or uncategorized_gate_result.stdout)
            self.assertEqual(uncategorized_stage1_result.returncode, 0, msg=uncategorized_stage1_result.stderr or uncategorized_stage1_result.stdout)
            self.assertEqual(uncategorized_stage2_result.returncode, 0, msg=uncategorized_stage2_result.stderr or uncategorized_stage2_result.stdout)

            missing_outputs = self._collect_replay_outputs(missing_root)
            uncategorized_outputs = self._collect_replay_outputs(uncategorized_root)

            missing_inventory = missing_outputs["inventory"]
            uncategorized_inventory = uncategorized_outputs["inventory"]
            self.assertEqual(missing_inventory["analysis_summary"]["missing_contract_count"], 1)
            self.assertEqual((missing_inventory["analysis_summary"]["root_script_observation_category_counts"] or {}).get("uncategorized_root_script", 0), 0)
            self.assertEqual(uncategorized_inventory["analysis_summary"]["missing_contract_count"], 0)
            self.assertEqual((uncategorized_inventory["analysis_summary"]["root_script_observation_category_counts"] or {}).get("uncategorized_root_script", 0), 1)
            self._assert_multimodule_metadata_reference_lists(missing_outputs)
            self._assert_multimodule_metadata_reference_lists(uncategorized_outputs)
            self._assert_gate_artifact_identity_isomorphic(missing_root, missing_outputs)
            self._assert_gate_artifact_identity_isomorphic(uncategorized_root, uncategorized_outputs)
            self._assert_export_phase_details_isomorphic(missing_outputs)
            self._assert_export_phase_details_isomorphic(uncategorized_outputs)
            self._assert_human_readable_artifact_references_isomorphic(missing_outputs)
            self._assert_human_readable_artifact_references_isomorphic(uncategorized_outputs)
            self._assert_issue_body_artifact_references_isomorphic(missing_outputs)
            self._assert_issue_body_artifact_references_isomorphic(uncategorized_outputs)

            missing_feedback = missing_outputs["feedback"]
            uncategorized_feedback = uncategorized_outputs["feedback"]
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" and "补齐缺失合同的质量消费者" in item["action"] for item in missing_feedback["priority_actions"]))
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" and "未归类的根目录脚本补齐 observation 分类" in item["action"] for item in uncategorized_feedback["priority_actions"]))

            missing_feedback_markdown = missing_outputs["feedback_markdown"]
            uncategorized_feedback_markdown = uncategorized_outputs["feedback_markdown"]
            self.assertIn("- Missing Contracts: 1", missing_feedback_markdown)
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", missing_feedback_markdown)
            self.assertIn("quality_consumer_inventory -> 补齐缺失合同的质量消费者", missing_feedback_markdown)
            self.assertIn("- Missing Contract Delta: 1", missing_feedback_markdown)
            self.assertIn("- Uncategorized Root Script Delta: 0", missing_feedback_markdown)
            self.assertIn("- Missing Contracts: 0", uncategorized_feedback_markdown)
            self.assertIn("- Recommended Next Target: none", uncategorized_feedback_markdown)
            self.assertIn("quality_consumer_inventory -> 为未归类的根目录脚本补齐 observation 分类", uncategorized_feedback_markdown)
            self.assertIn("- Missing Contract Delta: 0", uncategorized_feedback_markdown)
            self.assertIn("- Uncategorized Root Script Delta: 1", uncategorized_feedback_markdown)

            missing_module_owners = missing_outputs["issue_drafts"]["module-owners"]
            uncategorized_module_owners = uncategorized_outputs["issue_drafts"]["module-owners"]
            self.assertIn("code_health: 分批拆解高复杂函数并持续降告警。", missing_module_owners)
            self.assertIn("code_health: 分批拆解高复杂函数并持续降告警。", uncategorized_module_owners)
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", missing_module_owners)
            self.assertIn("- Recommended Next Target: none", uncategorized_module_owners)

            missing_quality_governance = missing_outputs["issue_drafts"]["quality-governance"]
            uncategorized_quality_governance = uncategorized_outputs["issue_drafts"]["quality-governance"]
            self.assertIn("补齐缺失合同的质量消费者", missing_quality_governance)
            self.assertNotIn("未归类的根目录脚本补齐 observation 分类", missing_quality_governance)
            self.assertIn("为未归类的根目录脚本补齐 observation 分类", uncategorized_quality_governance)
            self.assertNotIn("补齐缺失合同的质量消费者", uncategorized_quality_governance)
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", missing_quality_governance)
            self.assertIn("- Recommended Next Target: none", uncategorized_quality_governance)

            self.assertIn("- Missing Contracts: 1", missing_outputs["dossier"])
            self.assertIn("- Missing Contracts: 0", uncategorized_outputs["dossier"])
            self.assertIn("- Uncategorized Root Script Delta: 0", missing_outputs["dossier"])
            self.assertIn("- Uncategorized Root Script Delta: 1", uncategorized_outputs["dossier"])
            self._assert_issue_reference_order_isomorphic(missing_outputs["feedback"], missing_outputs["issue_index"])
            self._assert_issue_reference_order_isomorphic(uncategorized_outputs["feedback"], uncategorized_outputs["issue_index"])
            self.assertEqual(missing_outputs["stage2"]["governance_alerts"][0]["recommended_next_target"], "tools/missing_consumer.py")
            self.assertIsNone(uncategorized_outputs["stage2"]["governance_alerts"][0]["recommended_next_target"])

    def test_quality_gate_improving_recovery_replay_keeps_nine_endpoints_consistent_and_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "stable")

            gate_result = self._run_quality_gate(root)
            self.assertEqual(gate_result.returncode, 0, msg=gate_result.stderr or gate_result.stdout)

            self._inject_quiet_inventory_target_change(
                root,
                trend_status="improving",
                recommended_next_target="tools/missing_consumer.py",
                missing_contract_delta=-1,
                uncategorized_root_script_delta=0,
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            gate_payload = outputs["gate"]
            inventory_payload = outputs["inventory"]
            improvement_payload = outputs["improvement"]
            archive_payload = outputs["archive"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            issue_draft_texts = outputs["issue_drafts"]
            dossier_text = outputs["dossier"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertTrue(gate_payload["overall_success"])
            self.assertEqual(inventory_payload["recommendation"]["recommended_path"], "tools/missing_consumer.py")
            self.assertEqual(improvement_payload["inventory_focus"]["trend_status"], "improving")
            self.assertEqual(improvement_payload["next_cycle_targets"]["inventory_recommended_next_target"], "tools/missing_consumer.py")
            self.assertEqual(archive_payload["inventory_trend"]["status"], "improving")
            self.assertTrue(archive_payload["inventory_trend"]["recommended_next_target_changed"])
            self.assertEqual(archive_payload["inventory_summary"]["recommended_next_target"], "tools/missing_consumer.py")
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "improving")
            self.assertTrue(feedback_payload["inventory_trend"]["recommended_next_target_changed"])
            self.assertEqual(feedback_payload["inventory_summary"]["recommended_next_target"], "tools/missing_consumer.py")
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback_payload["priority_actions"]))
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            self.assertEqual(issue_index_payload["count"], 1)
            self.assertEqual(self._issue_owner(issue_index_payload["items"][0]), "module-owners")
            self.assertIn("module-owners", issue_draft_texts)
            self.assertNotIn("## Inventory Trend", issue_draft_texts["module-owners"])
            self.assertIn("- Trend Status: improving", dossier_text)
            self.assertIn("- Recommended Next Target: tools/missing_consumer.py", dossier_text)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_quality_gate_improving_recovery_with_target_cleared_keeps_nine_endpoints_consistent_and_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "stable")

            gate_result = self._run_quality_gate(root)
            self.assertEqual(gate_result.returncode, 0, msg=gate_result.stderr or gate_result.stdout)

            self._inject_quiet_inventory_target_change(
                root,
                trend_status="improving",
                recommended_next_target="none",
                missing_contract_delta=-1,
                uncategorized_root_script_delta=-1,
            )

            inventory_path = root / "output" / "quality-consumer-inventory.json"
            inventory_payload = self._load_json(inventory_path)
            inventory_payload.setdefault("recommendation", {})["recommended_path"] = None
            inventory_payload.setdefault("analysis_summary", {})["recommended_next_target"] = None
            inventory_path.write_text(json.dumps(inventory_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            archive_path = root / "output" / "quality-improvement-archive-latest.json"
            archive_payload = self._load_json(archive_path)
            archive_payload.setdefault("inventory_summary", {})["recommended_next_target"] = None
            archive_payload.setdefault("inventory_trend", {}).update(
                {
                    "previous_recommended_next_target": "tools/missing_consumer.py",
                    "current_recommended_next_target": None,
                    "recommended_next_target_changed": True,
                }
            )
            archive_path.write_text(json.dumps(archive_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            dossier_path = Path(str((archive_payload.get("report_metadata") or {}).get("dossier_path", "")))
            dossier_text = self._load_text(dossier_path).replace("- Recommended Next Target: none", "- Recommended Next Target: none")
            dossier_path.write_text(dossier_text, encoding="utf-8")

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            inventory_payload = outputs["inventory"]
            improvement_payload = outputs["improvement"]
            archive_payload = outputs["archive"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertIsNone(inventory_payload["recommendation"]["recommended_path"])
            self.assertEqual(improvement_payload["inventory_focus"]["trend_status"], "improving")
            self.assertEqual(improvement_payload["next_cycle_targets"]["inventory_recommended_next_target"], "none")
            self.assertEqual(archive_payload["inventory_trend"]["status"], "improving")
            self.assertTrue(archive_payload["inventory_trend"]["recommended_next_target_changed"])
            self.assertIsNone(archive_payload["inventory_summary"]["recommended_next_target"])
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "improving")
            self.assertTrue(feedback_payload["inventory_trend"]["recommended_next_target_changed"])
            self.assertIsNone(feedback_payload["inventory_summary"]["recommended_next_target"])
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback_payload["priority_actions"]))
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_quality_gate_improving_recovery_with_residual_missing_contract_keeps_feedback_loud_and_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "stable")

            gate_result = self._run_quality_gate(root)
            self.assertEqual(gate_result.returncode, 0, msg=gate_result.stderr or gate_result.stdout)

            self._inject_quiet_inventory_target_change(
                root,
                trend_status="improving",
                recommended_next_target="tools/missing_consumer.py",
                missing_contract_delta=-1,
                uncategorized_root_script_delta=0,
            )
            self._inject_inventory_snapshot_risk(
                root,
                missing_contract_count=1,
                recommended_next_target="tools/missing_consumer.py",
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            inventory_payload = outputs["inventory"]
            improvement_payload = outputs["improvement"]
            archive_payload = outputs["archive"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            issue_draft_texts = outputs["issue_drafts"]
            dossier_text = outputs["dossier"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertEqual(inventory_payload["analysis_summary"]["missing_contract_count"], 1)
            self.assertEqual(inventory_payload["recommendation"]["recommended_path"], "tools/missing_consumer.py")
            self.assertEqual(improvement_payload["inventory_focus"]["trend_status"], "improving")
            self.assertEqual(archive_payload["inventory_trend"]["status"], "improving")
            self.assertEqual(archive_payload["inventory_summary"]["missing_contract_count"], 1)
            self.assertEqual(feedback_payload["inventory_summary"]["status"], "critical")
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "improving")
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in feedback_payload["priority_actions"]))
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback_payload["priority_actions"]))
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in issue_index_payload["items"]))
            self.assertIn("quality-governance", issue_draft_texts)
            self.assertIn("补齐缺失合同的质量消费者", issue_draft_texts["quality-governance"])
            self.assertNotIn("## Inventory Trend", issue_draft_texts["quality-governance"])
            self.assertIn("- Missing Contracts: 1", dossier_text)
            self.assertIn("- Trend Status: improving", dossier_text)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_quality_gate_improving_recovery_with_mixed_residual_risk_keeps_feedback_loud_and_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "stable")

            gate_result = self._run_quality_gate(root)
            self.assertEqual(gate_result.returncode, 0, msg=gate_result.stderr or gate_result.stdout)

            self._inject_quiet_inventory_target_change(
                root,
                trend_status="improving",
                recommended_next_target="tools/missing_consumer.py",
                missing_contract_delta=-1,
                uncategorized_root_script_delta=-1,
            )
            self._inject_inventory_snapshot_risk(
                root,
                missing_contract_count=1,
                recommended_next_target="tools/missing_consumer.py",
            )
            self._inject_uncategorized_snapshot_risk(
                root,
                uncategorized_root_script_count=1,
                recommended_next_target="tools/missing_consumer.py",
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            inventory_payload = outputs["inventory"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            issue_draft_texts = outputs["issue_drafts"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertEqual(inventory_payload["analysis_summary"]["missing_contract_count"], 1)
            self.assertEqual(
                (inventory_payload["analysis_summary"]["root_script_observation_category_counts"] or {}).get("uncategorized_root_script", 0),
                1,
            )
            self.assertEqual(feedback_payload["inventory_summary"]["status"], "critical")
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "improving")
            self.assertEqual(len([item for item in feedback_payload["priority_actions"] if item["dimension"] == "quality_consumer_inventory"]), 2)
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            governance_item = next(item for item in issue_index_payload["items"] if self._issue_owner(item) == "quality-governance")
            self.assertEqual(governance_item["issue_body"]["inventory_context"]["status"], "improving")
            self.assertIsNone(governance_item["issue_body"]["inventory_trend"])
            self.assertEqual(governance_item["issue_body"]["action_items"][0]["priority"], "P0")
            self.assertEqual(governance_item["issue_body"]["action_items"][1]["priority"], "P1")
            self.assertIn("补齐缺失合同的质量消费者", issue_draft_texts["quality-governance"])
            self.assertIn("未归类的根目录脚本补齐 observation 分类", issue_draft_texts["quality-governance"])
            self.assertNotIn("## Inventory Trend", issue_draft_texts["quality-governance"])
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)

    def test_quality_gate_improving_recovery_with_residual_uncategorized_root_script_keeps_feedback_loud_and_runners_quiet(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_workspace(root, "stable")

            gate_result = self._run_quality_gate(root)
            self.assertEqual(gate_result.returncode, 0, msg=gate_result.stderr or gate_result.stdout)

            self._inject_quiet_inventory_target_change(
                root,
                trend_status="improving",
                recommended_next_target="none",
                missing_contract_delta=0,
                uncategorized_root_script_delta=-1,
            )
            self._inject_uncategorized_snapshot_risk(
                root,
                uncategorized_root_script_count=1,
            )

            feedback_result = self._run_feedback(root)
            stage1_result = self._run_stage1(root)
            stage2_result = self._run_stage2(root)

            self.assertEqual(feedback_result.returncode, 0, msg=feedback_result.stderr or feedback_result.stdout)
            self.assertEqual(stage1_result.returncode, 0, msg=stage1_result.stderr or stage1_result.stdout)
            self.assertEqual(stage2_result.returncode, 0, msg=stage2_result.stderr or stage2_result.stdout)

            outputs = self._collect_replay_outputs(root)
            inventory_payload = outputs["inventory"]
            improvement_payload = outputs["improvement"]
            archive_payload = outputs["archive"]
            feedback_payload = outputs["feedback"]
            issue_index_payload = outputs["issue_index"]
            issue_draft_texts = outputs["issue_drafts"]
            dossier_text = outputs["dossier"]
            stage1_global = outputs["stage1"]
            stage2_global = outputs["stage2"]

            self.assertEqual(
                (inventory_payload["analysis_summary"]["root_script_observation_category_counts"] or {}).get("uncategorized_root_script", 0),
                1,
            )
            self.assertEqual(improvement_payload["inventory_focus"]["trend_status"], "improving")
            self.assertEqual(archive_payload["inventory_trend"]["status"], "improving")
            self.assertEqual(feedback_payload["inventory_summary"]["status"], "attention")
            self.assertEqual(feedback_payload["inventory_trend"]["status"], "improving")
            self.assertTrue(any(item["dimension"] == "quality_consumer_inventory" for item in feedback_payload["priority_actions"]))
            self.assertFalse(any(item["dimension"] == "quality_consumer_inventory_trend" for item in feedback_payload["priority_actions"]))
            self._assert_multimodule_metadata_reference_lists(outputs)
            self._assert_gate_artifact_identity_isomorphic(root, outputs)
            self._assert_export_phase_details_isomorphic(outputs)
            self._assert_human_readable_artifact_references_isomorphic(outputs)
            self._assert_issue_body_artifact_references_isomorphic(outputs)
            self._assert_issue_reference_order_isomorphic(feedback_payload, issue_index_payload)
            self.assertTrue(any(self._issue_owner(item) == "quality-governance" for item in issue_index_payload["items"]))
            self.assertIn("quality-governance", issue_draft_texts)
            self.assertIn("为未归类的根目录脚本补齐 observation 分类", issue_draft_texts["quality-governance"])
            self.assertNotIn("## Inventory Trend", issue_draft_texts["quality-governance"])
            self.assertIn("- Trend Status: improving", dossier_text)
            self.assertNotIn("governance_alerts", stage1_global)
            self.assertNotIn("governance_alerts", stage2_global)


if __name__ == "__main__":
    unittest.main()