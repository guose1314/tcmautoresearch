import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.quality_consumer_inventory import (
    build_quality_consumer_inventory,
    export_quality_consumer_inventory,
)


class TestQualityConsumerInventory(unittest.TestCase):
    def test_build_inventory_identifies_missing_contract_consumers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools_dir = root / "tools"
            tools_dir.mkdir(parents=True)

            (tools_dir / "quality_gate.py").write_text(
                "metadata = {}\n"
                "report_metadata = {}\n"
                "analysis_summary = {}\n"
                "failed_operations = []\n"
                "export_contract_version = 'd49.v1'\n"
                "assessment = json.loads((root / 'output' / 'quality-assessment.json').read_text(encoding='utf-8'))\n",
                encoding="utf-8",
            )
            (tools_dir / "quality_sync.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "assessment = json.loads((Path('output') / 'quality-assessment.json').read_text(encoding='utf-8'))\n"
                "archive = json.loads((Path('output') / 'quality-improvement-archive-latest.json').read_text(encoding='utf-8'))\n"
                "(Path('output') / 'quality-sync.json').write_text(json.dumps({'ok': True}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            (tools_dir / "stage2_runner.ps1").write_text(
                "& '{python}' tools/quality_assessment.py --gates-report output/quality-gate.json\n"
                "& '{python}' tools/quality_feedback.py --output output/quality-feedback.json\n",
                encoding="utf-8",
            )
            (root / "run_cycle_demo.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "report_metadata = {'result_schema': 'cycle_demo_report'}\n"
                "(Path('output') / 'cycle-demo-report.json').write_text(json.dumps({'report_metadata': report_metadata}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            (root / "aggregate_autorresearch.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "report = json.loads((Path('output') / 'autorresearch_report.json').read_text(encoding='utf-8'))\n"
                "(Path('output') / 'autorresearch-summary.json').write_text(json.dumps({'best': report.get('best_val_bpb')}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            (root / "generate_test_report.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "storage = json.loads((Path('output') / 'storage_test_results.json').read_text(encoding='utf-8'))\n"
                "Path('output').mkdir(exist_ok=True)\n"
                "(Path('output') / 'generic-report.json').write_text(json.dumps({'summary': storage.get('summary')}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            (root / "test_inventory_fixture.py").write_text(
                "from pathlib import Path\n"
                "Path('output').mkdir(exist_ok=True)\n",
                encoding="utf-8",
            )

            report = build_quality_consumer_inventory(root)

        inventory = {item["path"]: item for item in report["inventory"]}
        self.assertIn("tools/quality_sync.py", inventory)
        self.assertIn("tools/stage2_runner.ps1", inventory)
        self.assertIn("run_cycle_demo.py", inventory)
        self.assertIn("aggregate_autorresearch.py", inventory)
        self.assertNotIn("test_inventory_fixture.py", inventory)
        self.assertEqual(inventory["tools/quality_gate.py"]["contract_status"], "governed")
        self.assertEqual(inventory["tools/quality_gate.py"]["target_scope"], "out_of_scope")
        self.assertEqual(inventory["tools/quality_sync.py"]["contract_status"], "missing_contract")
        self.assertEqual(inventory["tools/quality_sync.py"]["consumption_mode"], "direct_artifact_read")
        self.assertEqual(inventory["tools/stage2_runner.ps1"]["consumption_mode"], "command_orchestration")
        self.assertEqual(inventory["run_cycle_demo.py"]["contract_status"], "missing_contract")
        self.assertIn("cycle_demo_report", inventory["run_cycle_demo.py"]["artifact_inputs"])
        self.assertEqual(inventory["aggregate_autorresearch.py"]["consumption_mode"], "direct_artifact_read")
        self.assertIn("autorresearch_report", inventory["aggregate_autorresearch.py"]["artifact_inputs"])
        self.assertEqual(report["analysis_summary"]["eligible_missing_contract_count"], 4)
        self.assertEqual(report["analysis_summary"]["scan_scope"], ["tools", "root_scripts"])
        self.assertEqual(report["analysis_summary"]["root_script_observation_count"], 1)
        self.assertEqual(report["analysis_summary"]["root_script_observation_category_counts"], {"non_governance_domain_script": 1})
        observations = {item["path"]: item for item in report["root_script_observations"]}
        self.assertIn("generate_test_report.py", observations)
        self.assertEqual(observations["generate_test_report.py"]["observation_status"], "no_artifact_match")
        self.assertEqual(observations["generate_test_report.py"]["observation_category"], "non_governance_domain_script")
        self.assertEqual(observations["generate_test_report.py"]["observation_category_label"], "非治理域脚本")
        self.assertEqual(report["recommendation"]["recommended_path"], "tools/quality_sync.py")
        self.assertEqual(report["report_metadata"]["contract_version"], "d62.v1")

    def test_export_inventory_updates_export_phase(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = {
                "timestamp": "2026-03-29T00:00:00+00:00",
                "inventory": [],
                "root_script_observations": [
                    {
                        "path": "generate_test_report.py",
                        "observation_status": "no_artifact_match",
                        "observation_category": "non_governance_domain_script",
                        "observation_category_label": "非治理域脚本",
                        "reason": "Root script belongs to a separate reporting or validation domain and does not consume quality governance artifacts.",
                        "output_targets": [],
                        "evidence": [],
                    }
                ],
                "recommendation": {"recommended_path": None, "reason": "none", "candidate_count": 0},
                "analysis_summary": {
                    "scanned_consumer_count": 0,
                    "missing_contract_count": 0,
                    "eligible_missing_contract_count": 0,
                    "governed_consumer_count": 0,
                    "recommended_next_target": None,
                    "scan_scope": ["tools", "root_scripts"],
                    "root_script_observation_count": 1,
                    "root_script_observation_category_counts": {"non_governance_domain_script": 1},
                },
                "metadata": {
                    "phase_history": [],
                    "phase_timings": {},
                    "completed_phases": ["build_quality_consumer_inventory"],
                    "failed_phase": None,
                    "final_status": "completed",
                    "last_completed_phase": "build_quality_consumer_inventory",
                },
                "failed_operations": [],
                "report_metadata": {
                    "contract_version": "d62.v1",
                    "generated_at": "2026-03-29T00:00:00+00:00",
                    "result_schema": "quality_consumer_inventory_report",
                    "failed_operation_count": 0,
                    "final_status": "completed",
                    "last_completed_phase": "build_quality_consumer_inventory",
                },
            }

            exported = export_quality_consumer_inventory(
                report,
                root / "output" / "quality-consumer-inventory.json",
                root / "output" / "quality-consumer-inventory.md",
            )

            self.assertEqual(exported["metadata"]["last_completed_phase"], "export_quality_consumer_inventory")
            self.assertTrue((root / "output" / "quality-consumer-inventory.json").exists())
            self.assertTrue((root / "output" / "quality-consumer-inventory.md").exists())

            payload = json.loads((root / "output" / "quality-consumer-inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["report_metadata"]["contract_version"], "d62.v1")
            self.assertIn("Root Script Observations", (root / "output" / "quality-consumer-inventory.md").read_text(encoding="utf-8"))
            self.assertIn("非治理域脚本", (root / "output" / "quality-consumer-inventory.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()