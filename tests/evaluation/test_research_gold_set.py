from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.evaluate_research_quality import (
    REQUIRED_CATEGORIES,
    evaluate_fixture_dir,
    main,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "research_gold_set"


class ResearchGoldSetEvaluationTest(unittest.TestCase):
    def test_gold_set_contains_required_categories(self) -> None:
        summary = evaluate_fixture_dir(FIXTURE_DIR)

        self.assertGreaterEqual(summary["case_count"], 5)
        self.assertTrue(REQUIRED_CATEGORIES <= set(summary["categories"]))
        self.assertEqual(summary["json_schema_pass_rate"], 1.0)

    def test_evaluation_summary_exposes_required_metrics(self) -> None:
        summary = evaluate_fixture_dir(FIXTURE_DIR)

        for metric in (
            "precision",
            "recall",
            "citation_support_rate",
            "citation_grounding_support_rate",
            "json_schema_pass_rate",
        ):
            self.assertIn(metric, summary)
            self.assertGreaterEqual(summary[metric], 0.0)
            self.assertLessEqual(summary[metric], 1.0)
        self.assertEqual(summary["status"], "passed")
        self.assertGreaterEqual(summary["citation_grounding_record_count"], 1)

    def test_threshold_warnings_are_non_blocking_by_default(self) -> None:
        summary = evaluate_fixture_dir(
            FIXTURE_DIR,
            thresholds={
                "precision": 1.01,
                "recall": 1.01,
                "citation_support_rate": 1.01,
                "json_schema_pass_rate": 1.01,
            },
        )

        self.assertEqual(summary["status"], "warning")
        self.assertTrue(summary["warnings"])

    def test_cli_outputs_json_summary(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--fixture-dir", str(FIXTURE_DIR)])

        self.assertEqual(exit_code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertIn("precision", summary)
        self.assertIn("citation_support_rate", summary)


if __name__ == "__main__":
    unittest.main()
