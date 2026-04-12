import unittest

from src.research.phase_result import (
    get_phase_artifact_map,
    get_phase_deprecated_fallbacks,
    get_phase_value,
    normalize_phase_result,
)
from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class TestPhaseResultContract(unittest.TestCase):
    def test_normalize_phase_result_adds_standard_keys(self):
        normalized = normalize_phase_result(
            "observe",
            {
                "observations": ["o1"],
                "metadata": {"source": "test"},
            },
        )

        self.assertEqual(normalized["phase"], "observe")
        self.assertEqual(normalized["status"], "completed")
        self.assertEqual(normalized["results"]["observations"], ["o1"])
        self.assertEqual(normalized["artifacts"], [])
        self.assertIsNone(normalized["error"])
        self.assertEqual(normalized["metadata"]["contract_version"], "phase_result.v1")

    def test_research_pipeline_phases_return_standard_contract(self):
        pipeline = ResearchPipeline({})
        self.addCleanup(pipeline.cleanup)

        cycle = pipeline.create_research_cycle(
            cycle_name="phase-result-contract",
            description="phase contract",
            objective="ensure all research phases expose PhaseResult",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(pipeline.start_research_cycle(cycle.cycle_id))

        observe_result = pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": False,
                "run_preprocess_and_extract": False,
                "use_ctext_whitelist": False,
                "data_source": "manual",
            },
        )
        results = {
            "observe": observe_result,
            "hypothesis": pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS, {}),
            "experiment": pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT, {}),
            "analyze": pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE, {}),
            "publish": pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.PUBLISH, {}),
            "reflect": pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.REFLECT, {}),
        }

        for phase_name, result in results.items():
            with self.subTest(phase=phase_name):
                self.assertEqual(result["phase"], phase_name)
                self.assertIn("status", result)
                self.assertIn("results", result)
                self.assertIn("artifacts", result)
                self.assertIn("metadata", result)
                self.assertIn("error", result)
                self.assertIsInstance(result["results"], dict)
                self.assertIsInstance(result["artifacts"], list)
                self.assertIsInstance(result["metadata"], dict)
                self.assertEqual(result["metadata"].get("contract_version"), "phase_result.v1")

    def test_deprecated_top_level_fallbacks_are_marked(self):
        legacy_result = {
            "phase": "publish",
            "metadata": {},
            "deliverables": ["研究报告"],
            "output_files": {"markdown": "output/demo.md"},
        }

        deliverables = get_phase_value(legacy_result, "deliverables", [])
        artifact_map = get_phase_artifact_map(legacy_result)

        self.assertEqual(deliverables, ["研究报告"])
        self.assertEqual(artifact_map["markdown"], "output/demo.md")
        self.assertEqual(
            get_phase_deprecated_fallbacks(legacy_result),
            ["deliverables", "output_files"],
        )

    def test_standard_results_and_artifacts_do_not_mark_fallbacks(self):
        normalized = {
            "phase": "publish",
            "status": "completed",
            "results": {
                "deliverables": ["研究报告"],
            },
            "artifacts": [
                {"name": "markdown", "path": "output/demo.md", "type": "file"},
            ],
            "metadata": {},
            "error": None,
            "deliverables": ["旧兼容字段"],
            "output_files": {"markdown": "output/legacy.md"},
        }

        deliverables = get_phase_value(normalized, "deliverables", [])
        artifact_map = get_phase_artifact_map(normalized)

        self.assertEqual(deliverables, ["研究报告"])
        self.assertEqual(artifact_map["markdown"], "output/demo.md")
        self.assertEqual(get_phase_deprecated_fallbacks(normalized), [])

    def test_normalize_publish_legacy_fields_moves_data_into_results_without_root_mirrors(self):
        normalized = normalize_phase_result(
            "publish",
            {
                "deliverables": ["研究报告"],
                "output_files": {"markdown": "output/demo.md"},
                "report_output_files": {"imrd_markdown": "output/imrd.md"},
                "paper_language": "zh",
                "report_generation_errors": [{"markdown": "boom"}],
                "report_session_result": {"session_id": "legacy-session"},
                "bibtex": "@article{demo}",
                "gbt7714": "[1] demo",
                "formatted_references": "demo-ref",
                "metadata": {"source": "legacy"},
            },
        )

        self.assertEqual(normalized["results"]["deliverables"], ["研究报告"])
        self.assertEqual(normalized["results"]["output_files"]["markdown"], "output/demo.md")
        self.assertEqual(normalized["results"]["bibtex"], "@article{demo}")
        self.assertEqual(normalized["results"]["gbt7714"], "[1] demo")
        self.assertEqual(normalized["results"]["formatted_references"], "demo-ref")
        self.assertEqual(get_phase_artifact_map(normalized)["markdown"], "output/demo.md")
        self.assertEqual(get_phase_artifact_map(normalized)["imrd_markdown"], "output/imrd.md")
        self.assertNotIn("deliverables", normalized)
        self.assertNotIn("output_files", normalized)
        self.assertNotIn("report_output_files", normalized)
        self.assertNotIn("paper_language", normalized)
        self.assertNotIn("report_generation_errors", normalized)
        self.assertNotIn("report_session_result", normalized)
        self.assertNotIn("bibtex", normalized)
        self.assertNotIn("gbt7714", normalized)
        self.assertNotIn("formatted_references", normalized)
        self.assertNotIn("paper_language", normalized["results"])
        self.assertNotIn("report_output_files", normalized["results"])
        self.assertNotIn("report_generation_errors", normalized["results"])
        self.assertNotIn("report_session_result", normalized["results"])
        self.assertEqual(get_phase_deprecated_fallbacks(normalized), [])

    def test_normalize_publish_removed_root_compat_fields_do_not_resurface_in_results(self):
        normalized = normalize_phase_result(
            "publish",
            {
                "paper_draft": {"title": "legacy draft"},
                "imrd_reports": {"markdown": {"title": "legacy imrd"}},
                "paper_language": "zh",
                "report_output_files": {"imrd_markdown": "output/imrd.md"},
                "report_generation_errors": [{"markdown": "boom"}],
                "report_session_result": {"session_id": "legacy-session"},
                "metadata": {"source": "legacy-only-compat"},
            },
        )

        self.assertEqual(normalized["results"], {})
        self.assertEqual(get_phase_artifact_map(normalized)["imrd_markdown"], "output/imrd.md")
        self.assertNotIn("paper_draft", normalized)
        self.assertNotIn("imrd_reports", normalized)
        self.assertNotIn("paper_language", normalized)
        self.assertNotIn("report_output_files", normalized)
        self.assertNotIn("report_generation_errors", normalized)
        self.assertNotIn("report_session_result", normalized)

    def test_normalize_publish_removed_large_result_payloads_do_not_survive_results(self):
        normalized = normalize_phase_result(
            "publish",
            {
                "results": {
                    "paper_draft": {"title": "legacy draft"},
                    "imrd_reports": {"markdown": {"title": "legacy imrd"}},
                    "deliverables": ["研究报告"],
                },
                "output_files": {"markdown": "output/demo.md"},
                "metadata": {"source": "legacy-large-results"},
            },
        )

        self.assertEqual(normalized["results"]["deliverables"], ["研究报告"])
        self.assertNotIn("paper_draft", normalized["results"])
        self.assertNotIn("imrd_reports", normalized["results"])
        self.assertNotIn("paper_draft", normalized)
        self.assertNotIn("imrd_reports", normalized)

    def test_publish_analysis_results_and_research_artifact_move_into_results(self):
        analysis_results = {
            "statistical_analysis": {"p_value": 0.003, "primary_association": {"herb": "桂枝"}},
            "data_mining_result": {"record_count": 24},
        }
        research_artifact = {
            "hypothesis": [{"title": "桂枝汤调和营卫假设"}],
            "similar_formula_graph_evidence_summary": {"match_count": 1},
        }

        normalized = normalize_phase_result(
            "publish",
            {
                "analysis_results": analysis_results,
                "research_artifact": research_artifact,
                "paper_language": "zh",
                "report_session_result": {"session_id": "legacy-session"},
                "metadata": {"source": "publish-dto-contract"},
            },
        )

        self.assertNotIn("analysis_results", normalized)
        self.assertNotIn("research_artifact", normalized)
        self.assertEqual(normalized["results"]["analysis_results"], analysis_results)
        self.assertEqual(normalized["results"]["research_artifact"], research_artifact)
        self.assertNotIn("paper_language", normalized)
        self.assertNotIn("report_session_result", normalized)
        self.assertEqual(get_phase_value(normalized, "analysis_results"), analysis_results)
        self.assertEqual(get_phase_value(normalized, "research_artifact"), research_artifact)
