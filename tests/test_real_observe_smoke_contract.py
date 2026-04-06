import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.research.real_observe_smoke import (
    DEFAULT_PROFILE_PATH,
    execute_real_observe_smoke,
    load_smoke_profile,
    resolve_include_paths,
    validate_smoke_summary,
)


class TestRealObserveSmokeContract(unittest.TestCase):
    def test_profile_locks_verified_20_file_config(self):
        profile = load_smoke_profile(DEFAULT_PROFILE_PATH)

        self.assertEqual(profile.profile_name, "real_observe_local_formula_20x3000")
        self.assertEqual(len(profile.include_paths), 20)
        self.assertEqual(profile.phase_context["max_chars_per_text"], 3000)
        self.assertEqual(profile.thresholds.processed_document_count, 20)
        self.assertAlmostEqual(profile.thresholds.max_p_value or 0.0, 0.05)
        self.assertIn("data/伤寒论方剂(113种).txt", profile.include_paths)

        resolved_paths = resolve_include_paths(profile)
        self.assertTrue(all(path.exists() for path in resolved_paths))

    def test_validate_summary_accepts_verified_baseline(self):
        profile = load_smoke_profile(DEFAULT_PROFILE_PATH)
        summary = {
            "processed_document_count": 20,
            "total_entities": 3874,
            "semantic_graph_nodes": 990,
            "semantic_graph_edges": 7684,
            "semantic_relationship_count": 830,
            "observe_reasoning_confidence": 0.5828,
            "record_count": 16,
            "p_value": 0.029345,
            "effect_size": 0.5447,
            "statistical_significance": True,
            "reasoning_confidence": 0.6613,
            "kg_path_count": 50,
            "association_rule_count": 20,
            "frequency_signal_count": 15,
            "used_llm_generation": False,
            "experiment_protocol_source": "template",
            "publish_alias_fields": {
                "analysis_results": {
                    "primary_association": True,
                    "data_mining_summary": True,
                    "data_mining_methods": True,
                    "frequency_chi_square": True,
                    "association_rules": True,
                },
                "research_artifact": {
                    "primary_association": True,
                    "data_mining_summary": True,
                    "data_mining_methods": True,
                    "frequency_chi_square": True,
                    "association_rules": True,
                },
            },
        }

        self.assertEqual(validate_smoke_summary(summary, profile.thresholds), [])

    def test_validate_summary_flags_alias_and_significance_regressions(self):
        profile = load_smoke_profile(DEFAULT_PROFILE_PATH)
        summary = {
            "processed_document_count": 20,
            "total_entities": 3000,
            "semantic_graph_nodes": 700,
            "semantic_graph_edges": 4000,
            "semantic_relationship_count": 400,
            "observe_reasoning_confidence": 0.5,
            "record_count": 14,
            "p_value": 0.2,
            "effect_size": 0.52,
            "statistical_significance": False,
            "reasoning_confidence": 0.6,
            "kg_path_count": 30,
            "association_rule_count": 20,
            "frequency_signal_count": 15,
            "used_llm_generation": False,
            "experiment_protocol_source": "template",
            "publish_alias_fields": {
                "analysis_results": {
                    "primary_association": False,
                    "data_mining_summary": True,
                    "data_mining_methods": True,
                    "frequency_chi_square": True,
                    "association_rules": True,
                },
                "research_artifact": {
                    "primary_association": True,
                    "data_mining_summary": True,
                    "data_mining_methods": True,
                    "frequency_chi_square": True,
                    "association_rules": True,
                },
            },
        }

        violations = validate_smoke_summary(summary, profile.thresholds)
        self.assertTrue(any("p_value" in item for item in violations))
        self.assertTrue(any("statistical_significance" in item for item in violations))
        self.assertTrue(any("analysis_results missing publish aliases" in item for item in violations))

    @unittest.skipUnless(
        os.getenv("TCM_RUN_REAL_OBSERVE_SMOKE") == "1",
        "set TCM_RUN_REAL_OBSERVE_SMOKE=1 to execute the real local-corpus smoke test",
    )
    def test_real_observe_smoke_profile_executes_successfully(self):
        output_dir = Path(tempfile.mkdtemp())
        try:
            summary = execute_real_observe_smoke(output_dir=output_dir)
            self.assertEqual(summary["validation_status"], "passed", summary.get("violations"))
            self.assertTrue((output_dir / "latest.json").exists())
            self.assertTrue((output_dir / "dossier.md").exists())
            self.assertTrue((output_dir / "timeline.jsonl").exists())
        finally:
            shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()