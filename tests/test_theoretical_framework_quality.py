import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.research.theoretical_framework import HypothesisStatus, ResearchDomain, TheoreticalFramework


class TestTheoreticalFrameworkQuality(unittest.TestCase):
    def setUp(self):
        self.framework = TheoreticalFramework({"export_contract_version": "d20.v1", "minimum_validation_rate": 0.5})

    def test_operation_history_and_analysis_summary(self):
        hypothesis = self.framework.generate_hypothesis(
            {
                "text_content": "方剂与临床理论研究",
                "research_objective": "验证方剂配伍关系",
                "domain": ResearchDomain.FORMULA_RESEARCH,
            }
        )
        experiment = self.framework.design_experiment(hypothesis, {"sample_size": 20})
        self.framework.generate_insight(hypothesis, experiment, {"effect_size": 0.82})
        self.framework.validate_hypothesis(hypothesis.hypothesis_id, True, "通过")

        summary = self.framework.get_research_summary()

        self.assertEqual(
            [phase["phase"] for phase in self.framework.framework_metadata["phase_history"][:4]],
            ["generate_hypothesis", "design_experiment", "generate_insight", "validate_hypothesis"],
        )
        self.assertEqual(summary["analysis_summary"]["status"], "stable")
        self.assertEqual(summary["validated_hypotheses"], 1)
        self.assertEqual(hypothesis.status, HypothesisStatus.VALIDATED)

    def test_failure_is_recorded_in_failed_operations(self):
        with patch.object(self.framework, "_generate_hypothesis_content", side_effect=RuntimeError("content failed")):
            with self.assertRaises(RuntimeError):
                self.framework.generate_hypothesis(
                    {
                        "text_content": "理论",
                        "research_objective": "失败路径",
                        "domain": ResearchDomain.HERB_RESEARCH,
                    }
                )

        summary = self.framework.get_research_summary()
        self.assertEqual(summary["analysis_summary"]["failed_operation_count"], 1)
        self.assertEqual(self.framework.framework_metadata["failed_phase"], "generate_hypothesis")
        self.assertEqual(self.framework.framework_metadata["phase_history"][-1]["status"], "failed")

    def test_export_research_data_uses_json_safe_contract(self):
        hypothesis = self.framework.generate_hypothesis(
            {
                "text_content": "历史与临床研究",
                "research_objective": "导出契约",
                "domain": ResearchDomain.HISTORICAL_RESEARCH,
            }
        )
        experiment = self.framework.design_experiment(hypothesis, {})
        self.framework.generate_insight(hypothesis, experiment, {"confidence": 0.9})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "theoretical-framework.json")
            exported = self.framework.export_research_data(output_path)

            self.assertTrue(exported)
            with open(output_path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)

        self.assertEqual(payload["report_metadata"]["contract_version"], "d20.v1")
        self.assertEqual(payload["hypotheses"][0]["research_domain"], "historical_research")
        self.assertEqual(payload["hypotheses"][0]["status"], "active")
        self.assertIn("report_metadata", payload["research_summary"])


if __name__ == "__main__":
    unittest.main()