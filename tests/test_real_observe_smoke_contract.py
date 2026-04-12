import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src.research.real_observe_smoke import (
    DEFAULT_PROFILE_PATH,
    SmokeProfile,
    SmokeThresholds,
    build_smoke_summary,
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
        self.assertEqual(profile.thresholds.require_publish_aliases, [])
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
        }

        self.assertEqual(validate_smoke_summary(summary, profile.thresholds), [])

    def test_validate_summary_flags_significance_regressions_without_alias_contract(self):
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
        }

        violations = validate_smoke_summary(summary, profile.thresholds)
        self.assertTrue(any("p_value" in item for item in violations))
        self.assertTrue(any("statistical_significance" in item for item in violations))
        self.assertFalse(any("missing publish aliases" in item for item in violations))

    def test_build_smoke_summary_reads_protocol_source_from_phase_results(self):
        profile = SmokeProfile(
            profile_name="contract-test",
            description="contract-test",
            cycle_name="contract-test",
            objective="contract-test",
            scope="contract-test",
            researchers=["tester"],
            pipeline_config={},
            phase_context={},
            include_paths=["data/demo.txt"],
            thresholds=SmokeThresholds(processed_document_count=1),
        )
        publish_payload = {
            "statistical_analysis": {
                "primary_association": {"herb": "桂枝", "syndrome": "营卫不和"},
            },
            "data_mining_result": {
                "frequency_chi_square": {"chi_square_top": []},
                "association_rules": {"rules": []},
                "clustering": {"cluster_summary": [{"cluster": 0}]},
            },
        }

        summary = build_smoke_summary(
            profile,
            phase_context={},
            include_paths=[Path("data/demo.txt")],
            observe={
                "results": {
                    "ingestion_pipeline": {
                        "processed_document_count": 1,
                        "aggregate": {
                            "total_entities": 0,
                            "semantic_graph_nodes": 0,
                            "semantic_graph_edges": 0,
                            "semantic_relationships": [],
                            "reasoning_summary": {"inference_confidence": 0.0},
                        },
                    }
                }
            },
            hypothesis={"metadata": {"used_llm_generation": False}},
            experiment={
                "results": {
                    "study_protocol": {
                        "protocol_source": "template",
                    }
                }
            },
            analyze={
                "results": {
                    "statistical_analysis": {},
                    "reasoning_results": {
                        "kg_paths": [],
                        "reasoning_results": {"inference_confidence": 0.0},
                    },
                },
                "metadata": {
                    "analysis_modules": [],
                    "record_count": 0,
                },
            },
            publish={
                "results": {
                    "analysis_results": publish_payload,
                    "research_artifact": publish_payload,
                }
            },
            reflect={"metadata": {"reflection_count": 1}},
            started_at="2026-04-11T00:00:00",
        )

        self.assertEqual(summary["experiment_protocol_source"], "template")
        self.assertEqual(summary["primary_association"]["herb"], "桂枝")
        self.assertNotIn("publish_alias_fields", summary)
        self.assertNotIn("publish_aliases_present", summary)
        self.assertEqual(summary["association_rule_count"], 0)
        self.assertEqual(summary["frequency_signal_count"], 0)

    def test_build_smoke_summary_ignores_legacy_top_level_analyze_reasoning_results(self):
        profile = SmokeProfile(
            profile_name="contract-test",
            description="contract-test",
            cycle_name="contract-test",
            objective="contract-test",
            scope="contract-test",
            researchers=["tester"],
            pipeline_config={},
            phase_context={},
            include_paths=["data/demo.txt"],
            thresholds=SmokeThresholds(processed_document_count=1),
        )
        publish_payload = {
            "statistical_analysis": {
                "primary_association": {"herb": "桂枝", "syndrome": "营卫不和"},
            },
            "data_mining_result": {
                "frequency_chi_square": {"chi_square_top": []},
                "association_rules": {"rules": []},
            },
        }

        summary = build_smoke_summary(
            profile,
            phase_context={},
            include_paths=[Path("data/demo.txt")],
            observe={
                "results": {
                    "ingestion_pipeline": {
                        "processed_document_count": 1,
                        "aggregate": {
                            "total_entities": 0,
                            "semantic_graph_nodes": 0,
                            "semantic_graph_edges": 0,
                            "semantic_relationships": [],
                            "reasoning_summary": {"inference_confidence": 0.0},
                        },
                    }
                }
            },
            hypothesis={"metadata": {"used_llm_generation": False}},
            experiment={"results": {"study_protocol": {"protocol_source": "template"}}},
            analyze={
                "phase": "analyze",
                "status": "completed",
                "results": {
                    "statistical_analysis": {},
                },
                "metadata": {
                    "analysis_modules": [],
                    "record_count": 0,
                },
                "error": None,
                "reasoning_results": {
                    "kg_paths": ["legacy"],
                    "reasoning_results": {"inference_confidence": 0.9},
                },
            },
            publish={
                "results": {
                    "analysis_results": publish_payload,
                    "research_artifact": publish_payload,
                }
            },
            reflect={"metadata": {"reflection_count": 1}},
            started_at="2026-04-11T00:00:00",
        )

        self.assertEqual(summary["kg_path_count"], 0)
        self.assertIsNone(summary["reasoning_confidence"])

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