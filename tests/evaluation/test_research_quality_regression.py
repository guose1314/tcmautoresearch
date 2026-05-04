from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.run_research_quality_regression import evaluate_gold_set, main

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden"


class ResearchQualityRegressionTest(unittest.TestCase):
    def test_gold_set_regression_metrics_pass_baseline(self) -> None:
        summary = evaluate_gold_set(GOLDEN_DIR)

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["case_count"], 4)
        for metric in (
            "precision",
            "recall",
            "grounding_score",
            "candidate_acceptance_rate",
            "unsupported_claim_rate",
        ):
            self.assertIn(metric, summary)
            self.assertGreaterEqual(summary[metric], 0.0)
            self.assertLessEqual(summary[metric], 1.0)
        self.assertEqual(summary["precision"], 1.0)
        self.assertEqual(summary["recall"], 1.0)
        self.assertGreater(summary["grounding_score"], 0.8)
        self.assertEqual(summary["unsupported_claim_count"], 1)
        self.assertGreaterEqual(summary["citation_mismatch_count"], 1)

    def test_cli_outputs_json_and_zero_exit(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--golden-dir", str(GOLDEN_DIR)])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["contract_version"], "research-quality-regression-v1")
        self.assertEqual(payload["status"], "passed")

    def test_vscode_task_is_registered(self) -> None:
        tasks_path = Path(__file__).resolve().parents[2] / ".vscode" / "tasks.json"
        payload = json.loads(tasks_path.read_text(encoding="utf-8"))
        tasks = {task["label"]: task for task in payload["tasks"]}

        self.assertIn("research quality regression", tasks)
        self.assertIn(
            "tools/run_research_quality_regression.py",
            tasks["research quality regression"]["args"],
        )


if __name__ == "__main__":
    unittest.main()
