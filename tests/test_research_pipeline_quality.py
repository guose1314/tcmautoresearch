import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.research import research_pipeline
from src.research.research_pipeline import (
    ResearchCycleStatus,
    ResearchPhase,
    ResearchPipeline,
)


class TestResearchPipelineQuality(unittest.TestCase):
    def setUp(self):
        self.pipeline = ResearchPipeline({})

    def tearDown(self):
        self.pipeline.cleanup()

    def test_execute_all_phases_and_complete_cycle(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="quality-cycle",
            description="quality test",
            objective="full phase execution",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        observe_result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": False,
                "run_preprocess_and_extract": False,
                "use_ctext_whitelist": False,
                "data_source": "manual",
            },
        )
        self.assertEqual(observe_result["phase"], "observe")

        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS)["phase"],
            "hypothesis",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT)["phase"],
            "experiment",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT_EXECUTION)["phase"],
            "experiment_execution",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE)["phase"],
            "analyze",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.PUBLISH)["phase"],
            "publish",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.REFLECT)["phase"],
            "reflect",
        )

        self.assertTrue(self.pipeline.complete_research_cycle(cycle.cycle_id))
        status = self.pipeline.get_cycle_status(cycle.cycle_id)
        self.assertEqual(status["status"], ResearchCycleStatus.COMPLETED.value)
        self.assertEqual(
            [phase["phase"] for phase in status["metadata"]["phase_history"]],
            [
                ResearchPhase.OBSERVE.value,
                ResearchPhase.HYPOTHESIS.value,
                ResearchPhase.EXPERIMENT.value,
                ResearchPhase.EXPERIMENT_EXECUTION.value,
                ResearchPhase.ANALYZE.value,
                ResearchPhase.PUBLISH.value,
                ResearchPhase.REFLECT.value,
            ],
        )
        self.assertEqual(status["metadata"]["analysis_summary"]["status"], "stable")
        self.assertEqual(status["metadata"]["analysis_summary"]["final_status"], ResearchCycleStatus.COMPLETED.value)

        summary = self.pipeline.get_pipeline_summary()["pipeline_summary"]
        self.assertEqual(summary["total_cycles"], 1)
        self.assertEqual(summary["completed_cycles"], 1)
        self.assertIn("report_metadata", summary)
        self.assertEqual(summary["report_metadata"]["contract_version"], "d44.v1")
        self.assertEqual(summary["report_metadata"]["final_status"], "completed")
        self.assertIn("analysis_summary", summary)
        self.assertEqual(summary["metadata"]["final_status"], "completed")
        all_cycles = self.pipeline.get_all_cycles()
        self.assertEqual(len(all_cycles), 1)

    def test_completed_six_phase_cycle_keeps_reflect_as_current_phase(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="quality-cycle-current-phase",
            description="quality current phase regression",
            objective="full phase current phase regression",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        self.assertEqual(
            self.pipeline.execute_research_phase(
                cycle.cycle_id,
                ResearchPhase.OBSERVE,
                {
                    "run_literature_retrieval": False,
                    "run_preprocess_and_extract": False,
                    "use_ctext_whitelist": False,
                    "data_source": "manual",
                },
            )["phase"],
            "observe",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS)["phase"],
            "hypothesis",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT)["phase"],
            "experiment",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT_EXECUTION)["phase"],
            "experiment_execution",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE)["phase"],
            "analyze",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.PUBLISH)["phase"],
            "publish",
        )
        self.assertEqual(
            self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.REFLECT)["phase"],
            "reflect",
        )

        self.assertTrue(self.pipeline.complete_research_cycle(cycle.cycle_id))

        status = self.pipeline.get_cycle_status(cycle.cycle_id)
        snapshot = self.pipeline._serialize_cycle(self.pipeline.research_cycles[cycle.cycle_id])
        all_cycles = self.pipeline.get_all_cycles()

        self.assertEqual(status["status"], ResearchCycleStatus.COMPLETED.value)
        self.assertEqual(status["current_phase"], ResearchPhase.REFLECT.value)
        self.assertEqual(status["metadata"]["last_completed_phase"], ResearchPhase.REFLECT.value)
        self.assertEqual(
            status["metadata"]["analysis_summary"]["last_phase"],
            ResearchPhase.REFLECT.value,
        )
        self.assertEqual(snapshot["current_phase"], ResearchPhase.REFLECT.value)
        self.assertEqual(snapshot["metadata"]["last_completed_phase"], ResearchPhase.REFLECT.value)
        self.assertEqual(all_cycles[0]["current_phase"], ResearchPhase.REFLECT.value)

    def test_skipped_experiment_execution_advances_to_analyze_without_marking_completed(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="quality-cycle-skipped-execution",
            description="skipped execution regression",
            objective="phase status regression",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": False,
                "run_preprocess_and_extract": False,
                "use_ctext_whitelist": False,
                "data_source": "manual",
            },
        )
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS)
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT)

        execution_result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.EXPERIMENT_EXECUTION,
            {},
        )
        status = self.pipeline.get_cycle_status(cycle.cycle_id)

        self.assertEqual(execution_result["status"], "skipped")
        self.assertEqual(status["current_phase"], ResearchPhase.ANALYZE.value)
        self.assertNotIn(
            ResearchPhase.EXPERIMENT_EXECUTION.value,
            status["metadata"]["completed_phases"],
        )
        self.assertEqual(
            status["metadata"]["last_completed_phase"],
            ResearchPhase.EXPERIMENT.value,
        )

    def test_invalid_cycle_paths_and_suspend_resume(self):
        self.assertFalse(self.pipeline.start_research_cycle("missing"))
        missing_result = self.pipeline.execute_research_phase("missing", ResearchPhase.OBSERVE)
        self.assertIn("error", missing_result)
        self.assertFalse(self.pipeline.suspend_research_cycle("missing"))
        self.assertFalse(self.pipeline.resume_research_cycle("missing"))

        cycle = self.pipeline.create_research_cycle(
            cycle_name="state-cycle",
            description="state test",
            objective="state transitions",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))
        self.assertTrue(self.pipeline.suspend_research_cycle(cycle.cycle_id))
        self.assertTrue(self.pipeline.resume_research_cycle(cycle.cycle_id))

    def test_execute_requires_active_cycle(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="inactive-cycle",
            description="inactive",
            objective="inactive",
            scope="src/research",
            researchers=["tester"],
        )
        result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.OBSERVE)
        self.assertIn("error", result)

    def test_analyze_phase_generates_evidence_grade_from_observe_literature(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="analyze-grade-cycle",
            description="analyze evidence grade",
            objective="GRADE evidence synthesis",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))
        cycle.phase_executions[ResearchPhase.OBSERVE] = {
            "result": {
                "literature_pipeline": {
                    "records": [
                        {
                            "source": "pubmed",
                            "title": "Systematic review and meta-analysis of 桂枝汤 randomized controlled trials",
                            "authors": ["Alice"],
                            "year": 2025,
                            "doi": "10.1000/meta-grade",
                            "url": "https://example.org/meta",
                            "abstract": "This systematic review and meta-analysis included 16 randomized controlled trials and 1260 patients with low heterogeneity and stable results.",
                            "citation_count": 36,
                            "external_id": "meta-grade",
                        },
                        {
                            "source": "semantic_scholar",
                            "title": "Prospective cohort study of 桂枝汤 in chronic fatigue",
                            "authors": ["Bob"],
                            "year": 2024,
                            "doi": "10.1000/cohort-grade",
                            "url": "https://example.org/cohort",
                            "abstract": "This prospective cohort study included 210 patients and produced generally consistent outcome estimates over 12 months.",
                            "citation_count": 12,
                            "external_id": "cohort-grade",
                        },
                    ]
                }
            }
        }

        result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE, {})

        self.assertEqual(result["phase"], "analyze")
        self.assertIn("evidence_grade", result["results"])
        self.assertIn("evidence_grade_summary", result["results"])
        self.assertEqual(result["results"]["evidence_grade"]["study_count"], 2)
        self.assertTrue(result["metadata"]["evidence_grade_generated"])
        self.assertEqual(result["metadata"]["evidence_study_count"], 2)

    def test_analyze_phase_uses_reasoning_engine_and_real_statistical_signal(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="analyze-real-modules-cycle",
            description="analyze real modules",
            objective="connect analyze phase to reasoning engine",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        def _build_document(title, formula, syndrome, sovereign_herb, minister_herb, efficacy):
            return {
                "urn": title,
                "title": title,
                "semantic_relationships": [
                    {
                        "source": formula,
                        "target": sovereign_herb,
                        "type": "sovereign",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.95, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": formula,
                        "target": minister_herb,
                        "type": "minister",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.91, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": formula,
                        "target": syndrome,
                        "type": "treats",
                        "source_type": "formula",
                        "target_type": "syndrome",
                        "metadata": {"confidence": 0.89, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": sovereign_herb,
                        "target": efficacy,
                        "type": "efficacy",
                        "source_type": "herb",
                        "target_type": "efficacy",
                        "metadata": {"confidence": 0.87, "source": "observe_semantic_graph"},
                    },
                ],
            }

        documents = [
            _build_document(f"gz-{index}", "桂枝汤", "太阳中风证", "桂枝", "白芍", "解肌发表")
            for index in range(5)
        ] + [
            _build_document(f"hq-{index}", "黄芩汤", "少阳热证", "黄芩", "黄连", "清热燥湿")
            for index in range(5)
        ]
        cycle.phase_executions[ResearchPhase.OBSERVE] = {
            "result": {
                "ingestion_pipeline": {
                    "documents": documents,
                }
            }
        }

        result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE, {})

        self.assertEqual(result["phase"], "analyze")
        self.assertIn("reasoning_results", result["results"])
        self.assertIn("data_mining_result", result["results"])
        self.assertIn("reasoning_engine", result["metadata"]["analysis_modules"])
        self.assertIn("statistical_data_miner", result["metadata"]["analysis_modules"])
        self.assertIn("frequency_chi_square", result["results"]["data_mining_result"]["methods_executed"])

        statistical_analysis = result["results"]["statistical_analysis"]
        self.assertTrue(statistical_analysis["statistical_significance"])
        self.assertIsNotNone(statistical_analysis["p_value"])
        self.assertLess(statistical_analysis["p_value"], 0.05)
        self.assertNotEqual(statistical_analysis["p_value"], 0.003)
        self.assertGreater(statistical_analysis["effect_size"], 0.0)
        self.assertIn("桂枝", statistical_analysis["interpretation"])
        for legacy_key in (
            "statistical_significance",
            "confidence_level",
            "effect_size",
            "p_value",
            "interpretation",
            "limitations",
            "primary_association",
        ):
            self.assertNotIn(legacy_key, result["results"])

        reasoning_payload = result["results"]["reasoning_results"]
        self.assertTrue(reasoning_payload.get("kg_paths"))
        self.assertGreater(
            float((reasoning_payload.get("reasoning_results") or {}).get("inference_confidence") or 0.0),
            0.0,
        )
        self.assertNotIn("reasoning_results", result)
        self.assertNotIn("data_mining_result", result)

    def test_publish_phase_keeps_nested_analysis_and_omits_publish_mining_aliases(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-analysis-alias-cycle",
            description="publish aliases",
            objective="expose publish analysis aliases",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        def _build_document(title, formula, syndrome, herbs, efficacy):
            relationships = [
                {
                    "source": formula,
                    "target": syndrome,
                    "type": "treats",
                    "source_type": "formula",
                    "target_type": "syndrome",
                    "metadata": {"confidence": 0.93, "source": "observe_semantic_graph"},
                }
            ]
            for herb_index, herb in enumerate(herbs):
                relationships.append(
                    {
                        "source": formula,
                        "target": herb,
                        "type": "ingredient",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {
                            "confidence": 0.9 - herb_index * 0.05,
                            "source": "observe_semantic_graph",
                        },
                    }
                )
            relationships.append(
                {
                    "source": herbs[0],
                    "target": efficacy,
                    "type": "efficacy",
                    "source_type": "herb",
                    "target_type": "efficacy",
                    "metadata": {"confidence": 0.88, "source": "observe_semantic_graph"},
                }
            )
            return {
                "urn": title,
                "title": title,
                "semantic_relationships": relationships,
            }

        documents = [
            _build_document(f"gz-{index}", "桂枝汤", "太阳中风证", ["桂枝", "白芍"], "解肌发表")
            for index in range(6)
        ] + [
            _build_document(f"sx-{index}", "四物汤", "血虚证", ["当归", "白芍"], "养血调经")
            for index in range(4)
        ]
        cycle.phase_executions[ResearchPhase.OBSERVE] = {
            "result": {
                "ingestion_pipeline": {
                    "documents": documents,
                }
            }
        }

        analyze_result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE, {})
        self.assertEqual(analyze_result["phase"], "analyze")

        with tempfile.TemporaryDirectory() as temp_dir:
            publish_result = self.pipeline.execute_research_phase(
                cycle.cycle_id,
                ResearchPhase.PUBLISH,
                {
                    "paper_output_dir": temp_dir,
                    "output_dir": temp_dir,
                    "paper_output_formats": ["markdown"],
                    "report_output_formats": ["markdown"],
                },
            )

        self.assertEqual(publish_result["phase"], "publish")
        self.assertNotIn("paper_draft", publish_result["results"])
        self.assertNotIn("imrd_reports", publish_result["results"])
        analysis_results = publish_result["results"]["analysis_results"]
        research_artifact = publish_result["results"]["research_artifact"]
        statistical_analysis = analysis_results["statistical_analysis"]

        self.assertIsInstance(statistical_analysis.get("primary_association"), dict)
        self.assertNotIn("statistical_analysis", statistical_analysis)
        for removed_key in (
            "primary_association",
            "data_mining_summary",
            "data_mining_methods",
            "frequency_chi_square",
            "association_rules",
            "clustering",
        ):
            self.assertNotIn(removed_key, analysis_results)
            self.assertNotIn(removed_key, research_artifact)

        self.assertIn("data_mining_result", analysis_results)
        self.assertIn("frequency_chi_square", analysis_results["data_mining_result"])
        self.assertIn("association_rules", analysis_results["data_mining_result"])
        self.assertEqual(
            research_artifact["data_mining_result"],
            analysis_results["data_mining_result"],
        )

        self.assertEqual(
            research_artifact["statistical_analysis"]["primary_association"],
            statistical_analysis["primary_association"],
        )
        self.assertIn("data_mining_result", research_artifact)
        self.assertEqual(
            research_artifact["data_mining_result"]["record_count"],
            analysis_results["data_mining_result"]["record_count"],
        )
        self.assertNotIn("analysis_results", publish_result)
        self.assertNotIn("research_artifact", publish_result)

    def test_collect_and_resolve_ctext_config(self):
        pipeline = ResearchPipeline(
            {
                "ctext_corpus": {
                    "enabled": True,
                    "whitelist": {"enabled": True, "default_groups": ["jing"]},
                }
            }
        )
        self.assertTrue(pipeline._should_collect_ctext_corpus({}))
        self.assertEqual(pipeline._resolve_observe_data_source({}), "ctext_whitelist")
        self.assertEqual(pipeline._resolve_whitelist_groups({}), ["jing"])
        pipeline.cleanup()

    def test_collect_observe_corpus_prefers_bundle_over_fallback_error(self):
        local_bundle = {
            "schema_version": "1.0",
            "bundle_id": "local-bundle",
            "sources": ["local"],
            "collected_at": "2026-03-31T00:00:00",
            "stats": {"total_documents": 1},
            "errors": [],
            "documents": [],
        }

        with patch.object(self.pipeline, "_should_collect_ctext_corpus", return_value=True), patch.object(
            self.pipeline, "_should_collect_local_corpus", return_value=True
        ), patch.object(self.pipeline, "_collect_ctext_observation_corpus", return_value={"error": "ctext failed"}), patch.object(
            self.pipeline, "_collect_local_observation_corpus", return_value=local_bundle
        ):
            result = self.pipeline._collect_observe_corpus_if_enabled({})

        self.assertIsNotNone(result)
        self.assertEqual(result.get("sources"), ["local"])
        self.assertNotIn("error", result)

    def test_module_factory_recovers_semantic_graph_builder_after_placeholder_import(self):
        fallback_class = research_pipeline._build_unavailable_module("SemanticGraphBuilder")

        with patch.object(research_pipeline, "SemanticGraphBuilder", fallback_class):
            pipeline = research_pipeline.ResearchPipeline({})
            builder = None
            try:
                builder = pipeline.create_module("semantic_graph_builder", {})

                self.assertFalse(
                    bool(getattr(builder.__class__, "_copilot_unavailable_placeholder", False))
                )
                self.assertEqual(builder.__class__.__module__, "src.analysis.semantic_graph")
                self.assertTrue(builder.initialize())
                self.assertEqual(pipeline.SemanticGraphBuilder.__module__, "src.analysis.semantic_graph")
            finally:
                if builder is not None:
                    builder.cleanup()
                pipeline.cleanup()

    def test_build_observe_metadata_marks_local_bundle_without_ctext(self):
        local_bundle = {
            "schema_version": "1.0",
            "bundle_id": "local-bundle",
            "sources": ["local"],
            "collected_at": "2026-03-31T00:00:00",
            "stats": {"total_documents": 2},
            "errors": [],
            "documents": [],
        }

        metadata = self.pipeline._build_observe_metadata(
            context={"data_source": "local"},
            observations=["o1"],
            findings=["f1"],
            corpus_result=local_bundle,
            ingestion_result=None,
            literature_result=None,
        )

        self.assertFalse(metadata["auto_collected_ctext"])
        self.assertTrue(metadata["auto_collected_corpus"])
        self.assertEqual(metadata["corpus_schema"], "bundle")

    @patch("src.research.research_pipeline.CTextCorpusCollector.cleanup")
    @patch("src.research.research_pipeline.CTextCorpusCollector.execute", side_effect=RuntimeError("x"))
    @patch("src.research.research_pipeline.CTextCorpusCollector.initialize", return_value=True)
    def test_collect_ctext_observation_exception(self, _init, _execute, _cleanup):
        result = self.pipeline._collect_ctext_observation_corpus({})
        self.assertIn("error", result)

    @patch("src.research.research_pipeline.CTextCorpusCollector.initialize", return_value=False)
    def test_collect_ctext_observation_init_fail(self, _init):
        result = self.pipeline._collect_ctext_observation_corpus({})
        self.assertIn("error", result)

    def test_run_ingestion_empty_entries(self):
        with patch.object(self.pipeline, "_extract_corpus_text_entries", return_value=[]):
            result = self.pipeline._run_observe_ingestion_pipeline({"documents": []}, {})
        self.assertEqual(result["processed_document_count"], 0)

    @patch("src.research.research_pipeline.DocumentPreprocessor.initialize", return_value=False)
    def test_run_ingestion_preprocessor_init_fail(self, _pre_init):
        with patch.object(
            self.pipeline,
            "_extract_corpus_text_entries",
            return_value=[{"urn": "u", "title": "t", "text": "abc"}],
        ):
            result = self.pipeline._run_observe_ingestion_pipeline({"documents": [{}]}, {})
        self.assertIn("error", result)

    def test_execute_phase_internal_unknown_phase(self):
        class _FakePhase:
            value = "unknown"

        cycle = self.pipeline.create_research_cycle(
            cycle_name="unknown-phase",
            description="d",
            objective="o",
            scope="s",
            researchers=["tester"],
        )
        result = self.pipeline._execute_phase_internal(_FakePhase(), cycle, {})  # type: ignore[arg-type]
        self.assertIn("error", result)

    def test_should_run_flag_branches(self):
        pipeline = ResearchPipeline(
            {
                "observe_pipeline": {"enabled": True},
                "literature_retrieval": {"enabled": False},
                "clinical_gap_analysis": {"enabled": True},
            }
        )
        self.assertTrue(pipeline._should_run_observe_ingestion({}))
        self.assertFalse(pipeline._should_run_observe_literature({}))
        self.assertTrue(pipeline._should_run_clinical_gap_analysis({}))
        self.assertFalse(pipeline._should_run_observe_ingestion({"run_preprocess_and_extract": False}))
        self.assertTrue(pipeline._should_run_observe_literature({"run_literature_retrieval": True}))
        self.assertFalse(pipeline._should_run_clinical_gap_analysis({"run_clinical_gap_analysis": False}))
        pipeline.cleanup()

    def test_should_collect_local_corpus_accepts_collect_alias(self):
        self.assertTrue(self.pipeline._should_collect_local_corpus({"collect_local_corpus": True}))
        self.assertFalse(self.pipeline._should_collect_local_corpus({"collect_local_corpus": False}))

    @patch("src.research.research_pipeline.SemanticGraphBuilder.initialize", return_value=False)
    @patch("src.research.research_pipeline.AdvancedEntityExtractor.initialize", return_value=True)
    @patch("src.research.research_pipeline.DocumentPreprocessor.initialize", return_value=True)
    def test_run_ingestion_semantic_init_fail(self, _pre, _ext, _sem):
        with patch.object(
            self.pipeline,
            "_extract_corpus_text_entries",
            return_value=[{"urn": "u", "title": "t", "text": "abc"}],
        ):
            result = self.pipeline._run_observe_ingestion_pipeline({"documents": [{}]}, {})
        self.assertIn("error", result)

    def test_run_clinical_gap_analysis_success_and_error(self):
        from src.infra.llm_service import CachedLLMService

        class _GoodService:
            def load(self): return None
            def generate(self, prompt, system_prompt=""): return "ok"
            def unload(self): return None
            def cache_stats(self): return {"session_hits": 0, "session_misses": 1}

        class _BadService(_GoodService):
            def load(self): raise RuntimeError("load failed")

        with patch.object(CachedLLMService, "from_gap_config", return_value=_GoodService()):
            ok = self.pipeline._run_clinical_gap_analysis({}, [], {})
            self.assertEqual(ok.get("report"), "ok")
            self.assertIn("gaps", ok)
            self.assertIn("priority_summary", ok)
            self.assertEqual(ok.get("output_language"), "zh")

        with patch.object(CachedLLMService, "from_gap_config", return_value=_BadService()):
            bad = self.pipeline._run_clinical_gap_analysis({}, [], {})
            self.assertIn("error", bad)

    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    @patch.object(ResearchPipeline, "_run_clinical_gap_analysis")
    def test_literature_pipeline_with_clinical_gap(self, mock_gap, mock_search, mock_close):
        mock_close.return_value = None
        mock_gap.return_value = {"report": "ok"}
        mock_search.return_value = {
            "query": "q",
            "sources": ["pubmed"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "t",
                    "year": 2024,
                    "doi": "",
                    "url": "u",
                    "abstract": "randomized efficacy",
                }
            ],
            "query_plans": [],
            "source_stats": {"pubmed": {"count": 1}},
            "errors": [],
        }
        pipeline = ResearchPipeline({"literature_retrieval": {"enabled": True}, "clinical_gap_analysis": {"enabled": True}})
        result = pipeline._run_observe_literature_pipeline({"run_clinical_gap_analysis": True})
        self.assertIn("clinical_gap_analysis", result)
        self.assertEqual(result["clinical_gap_analysis"], {"report": "ok"})
        pipeline.cleanup()

    def test_run_ingestion_happy_path_with_mocks(self):
        pre = Mock()
        pre.initialize.return_value = True
        pre.execute.return_value = {"processed_text": "p"}
        pre.cleanup.return_value = None

        ext = Mock()
        ext.initialize.return_value = True
        ext.execute.return_value = {
            "entities": [{"confidence": 0.8}],
            "statistics": {"by_type": {"herb": 1}},
            "confidence_scores": {"average_confidence": 0.8},
        }
        ext.cleanup.return_value = None

        sem = Mock()
        sem.initialize.return_value = True
        sem.execute.return_value = {
            "graph_statistics": {"nodes_count": 2, "edges_count": 1, "relationships_by_type": {"r": 1}}
        }
        sem.cleanup.return_value = None

        pipeline = ResearchPipeline({}, preprocessor=pre, extractor=ext, graph_builder=sem)
        try:
            with patch.object(
                pipeline,
                "_extract_corpus_text_entries",
                return_value=[{"urn": "u", "title": "t", "text": "abc"}],
            ):
                result = pipeline._run_observe_ingestion_pipeline({"documents": [{}]}, {})

            self.assertEqual(result["processed_document_count"], 1)
            self.assertEqual(result["aggregate"]["total_entities"], 1)
        finally:
            pipeline.cleanup()

    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_literature_max_results_is_clamped(self, mock_search, mock_close):
        mock_close.return_value = None
        mock_search.return_value = {
            "query": "q",
            "sources": ["pubmed"],
            "records": [],
            "query_plans": [],
            "source_stats": {},
            "errors": [],
        }

        pipeline = ResearchPipeline({"literature_retrieval": {"enabled": True}})
        pipeline._run_observe_literature_pipeline(
            {
                "run_literature_retrieval": True,
                "literature_query": "q",
                "literature_max_results": 999,
            }
        )

        self.assertEqual(mock_search.call_args.kwargs["max_results_per_source"], 50)
        pipeline.cleanup()

    def test_extract_entries_export_and_history(self):
        entries = self.pipeline._extract_corpus_text_entries(
            {
                "documents": [
                    {
                        "urn": "u1",
                        "title": "t1",
                        "text": "a",
                        "children": [{"urn": "u2", "title": "t2", "text": "b"}],
                    }
                ]
            }
        )
        self.assertEqual(len(entries), 2)

        cycle = self.pipeline.create_research_cycle(
            cycle_name="export-cycle",
            description="export test",
            objective="export",
            scope="src/research",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.HYPOTHESIS)

        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            self.assertTrue(self.pipeline.export_pipeline_data(output_path))
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["report_metadata"]["contract_version"], "d44.v1")
            self.assertIn("pipeline_info", data)
            self.assertIn("research_cycles", data)
            self.assertIn("metadata", data)
            self.assertIn("failed_operations", data)
            self.assertIn("report_metadata", data["pipeline_info"]["pipeline_summary"]["pipeline_summary"])
            self.assertIn("failed_operations", data["pipeline_info"]["pipeline_summary"]["pipeline_summary"])
            self.assertEqual(data["metadata"]["final_status"], "completed")
            history = self.pipeline.get_cycle_history(cycle.cycle_id)
            self.assertTrue(len(history) >= 2)
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)

    def test_complete_cycle_without_start_fails(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="not-started",
            description="d",
            objective="o",
            scope="s",
            researchers=["tester"],
        )
        self.assertFalse(self.pipeline.complete_research_cycle(cycle.cycle_id))

    def test_phase_failure_tracks_failed_cycle_and_failed_phase(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="failing-cycle",
            description="failing",
            objective="track failed phase",
            scope="src/research",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        with patch.object(self.pipeline, "_execute_phase_internal", side_effect=RuntimeError("observe exploded")):
            result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.OBSERVE)

        self.assertIn("error", result)
        status = self.pipeline.get_cycle_status(cycle.cycle_id)
        self.assertEqual(status["status"], ResearchCycleStatus.FAILED.value)
        self.assertEqual(status["metadata"]["failed_phase"], ResearchPhase.OBSERVE.value)
        self.assertEqual(status["metadata"]["phase_history"][-1]["status"], "failed")
        self.assertEqual(status["metadata"]["analysis_summary"]["status"], "needs_followup")
        self.assertEqual(status["metadata"]["failed_operations"][-1]["operation"], ResearchPhase.OBSERVE.value)
        self.assertIn("details", status["metadata"]["failed_operations"][-1])
        self.assertEqual(status["metadata"]["failed_operations"][-1]["details"]["cycle_id"], cycle.cycle_id)
        summary = self.pipeline.get_pipeline_summary()["pipeline_summary"]
        self.assertEqual(summary["failed_operations"][-1]["operation"], ResearchPhase.OBSERVE.value)
        self.assertEqual(summary["failed_operations"][-1]["details"]["cycle_id"], cycle.cycle_id)
        self.assertEqual(len(self.pipeline.failed_cycles), 1)

    def test_cleanup_keeps_shared_executor_available(self):
        pipeline = ResearchPipeline({})
        executor = pipeline.executor
        self.assertTrue(pipeline.cleanup())
        self.assertFalse(getattr(executor, "_shutdown", False))
        self.assertEqual(pipeline._metadata["final_status"], "cleaned")
        self.assertEqual(pipeline.get_pipeline_summary()["pipeline_summary"]["analysis_summary"]["status"], "idle")


if __name__ == "__main__":
    unittest.main()
