import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


class _ExperimentPhaseFakeLLM:
        def generate(self, prompt: str, system_prompt: str = "") -> str:
                return """{
    "title": "学习策略增强实验协议",
    "objective": "验证实验协议增强路径",
    "primary_outcome": "主要结局变化",
    "secondary_outcomes": ["安全性"],
    "pico": {
        "population": "脾气虚证患者",
        "intervention": "四君子汤",
        "comparison": "常规治疗",
        "outcome": "主要结局变化"
    },
    "sample_size": {
        "estimated_n": 72,
        "outcome_type": "continuous",
        "effect_size": 0.5,
        "dropout_rate": 0.1
    }
}"""


class TestResearchPipelineExperimentPhase(unittest.TestCase):

    def setUp(self):
        self.pipeline = ResearchPipeline(
            {
                "hypothesis_engine_config": {
                    "max_hypotheses": 2,
                    "max_validation_iterations": 1,
                }
            }
        )

    def tearDown(self):
        self.pipeline.cleanup()

    def test_experiment_phase_uses_selected_hypothesis_id(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-cycle",
            description="experiment integration",
            objective="验证方剂配伍与证候关联",
            scope="中医古籍方剂研究",
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
        hypothesis_result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.HYPOTHESIS,
            {
                "entities": [
                    {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                    {"name": "补气", "type": "efficacy", "confidence": 0.84},
                ],
                "contradictions": ["部分案例剂量记录不完整"],
            },
        )

        selected_id = hypothesis_result["metadata"]["selected_hypothesis_id"]
        experiment_result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.EXPERIMENT,
            {},
        )

        self.assertEqual(experiment_result["phase"], "experiment")
        self.assertEqual(experiment_result["metadata"]["selected_hypothesis_id"], selected_id)
        self.assertEqual(experiment_result["metadata"]["phase_semantics"], "protocol_design")
        self.assertEqual(experiment_result["metadata"]["phase_display_name"], "实验方案阶段")
        self.assertTrue(experiment_result["metadata"]["protocol_design_only"])
        self.assertEqual(experiment_result["metadata"]["execution_status"], "not_executed")
        self.assertEqual(experiment_result["metadata"]["real_world_validation_status"], "not_started")
        self.assertEqual(len(experiment_result["results"]["experiments"]), 1)
        self.assertEqual(experiment_result["results"]["experiments"][0]["hypothesis_id"], selected_id)
        self.assertEqual(len(experiment_result["results"]["protocol_designs"]), 1)
        self.assertEqual(experiment_result["results"]["protocol_design"]["hypothesis_id"], selected_id)
        self.assertEqual(experiment_result["results"]["protocol_design"]["execution_status"], "not_executed")
        self.assertIn("study_protocol", experiment_result["results"])
        self.assertIn("sample_size", experiment_result["results"]["study_protocol"])
        self.assertIn("validation_plan", experiment_result["results"])
        self.assertIn("study_protocol", experiment_result["results"])
        self.assertEqual(experiment_result["results"]["design_completion_rate"], 1.0)
        self.assertNotIn("experiments", experiment_result)
        self.assertNotIn("study_protocol", experiment_result)
        self.assertNotIn("design_completion_rate", experiment_result)
        self.assertNotIn("selected_hypothesis", experiment_result)

    def test_experiment_execution_phase_is_skipped_without_external_inputs(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-execution-skip-cycle",
            description="experiment execution skip integration",
            objective="验证方剂配伍与证候关联",
            scope="中医古籍方剂研究",
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
        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.HYPOTHESIS,
            {
                "entities": [
                    {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                ],
            },
        )
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT, {})

        execution_result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.EXPERIMENT_EXECUTION,
            {},
        )

        self.assertEqual(execution_result["phase"], "experiment_execution")
        self.assertEqual(execution_result["status"], "skipped")
        self.assertEqual(execution_result["metadata"]["phase_semantics"], "experiment_execution")
        self.assertEqual(execution_result["metadata"]["phase_display_name"], "实验执行阶段")
        self.assertEqual(execution_result["metadata"]["execution_status"], "not_executed")
        self.assertEqual(execution_result["results"]["analysis_records"], [])
        self.assertEqual(execution_result["results"]["analysis_relationships"], [])

    def test_experiment_execution_phase_imports_records_for_analyze(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-execution-import-cycle",
            description="experiment execution import integration",
            objective="验证方剂配伍与证候关联",
            scope="中医古籍方剂研究",
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
        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.HYPOTHESIS,
            {
                "entities": [
                    {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                ],
            },
        )
        self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT, {})

        execution_result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.EXPERIMENT_EXECUTION,
            {
                "analysis_records": [
                    {
                        "formula": "四君子汤",
                        "syndrome": "脾气虚证",
                        "herbs": ["党参", "白术", "茯苓", "甘草"],
                    }
                ],
                "analysis_relationships": [
                    {
                        "source": "四君子汤",
                        "target": "党参",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.92, "source": "observe_semantic_graph"},
                    }
                ],
                "sampling_events": [{"batch": "batch-1", "size": 24}],
                "output_files": {"csv": "output/experiment_execution.csv"},
            },
        )
        analyze_result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.ANALYZE, {})

        self.assertEqual(execution_result["status"], "completed")
        self.assertEqual(execution_result["metadata"]["imported_record_count"], 1)
        self.assertEqual(execution_result["metadata"]["imported_relationship_count"], 1)
        self.assertEqual(execution_result["metadata"]["sampling_event_count"], 1)
        self.assertEqual(analyze_result["metadata"]["record_count"], 1)

    def test_hypothesis_context_prefers_observe_semantic_relationships(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="semantic-gap-cycle",
            description="semantic gap integration",
            objective="从语义图路径中发现潜在机制缺口",
            scope="中医语义图研究",
            researchers=["tester"],
        )

        cycle.phase_executions[self.pipeline.ResearchPhase.OBSERVE] = {
            "result": {
                "phase": "observe",
                "observations": ["语义图已发现公式到通路的两跳路径"],
                "findings": ["可基于真实语义边推导缺失直接关系"],
                "ingestion_pipeline": {
                    "aggregate": {
                        "semantic_relationships": [
                            {
                                "source": "补中益气汤",
                                "target": "IL6",
                                "type": "associated_target",
                                "source_type": "formula",
                                "target_type": "target",
                                "metadata": {"confidence": 0.82},
                            },
                            {
                                "source": "IL6",
                                "target": "JAK-STAT",
                                "type": "participates_in",
                                "source_type": "target",
                                "target_type": "pathway",
                                "metadata": {"confidence": 0.79},
                            },
                        ]
                    }
                },
                "literature_pipeline": {},
                "corpus_collection": {},
            }
        }

        hypothesis_context = self.pipeline.phase_handlers.build_hypothesis_context(
            cycle,
            {
                "entities": [
                    {"name": "补中益气汤", "type": "formula", "confidence": 0.95},
                    {"name": "IL6", "type": "target", "confidence": 0.9},
                    {"name": "JAK-STAT", "type": "pathway", "confidence": 0.88},
                ]
            },
        )

        self.assertEqual(hypothesis_context["knowledge_gap"]["gap_type"], "missing_direct_relation")
        self.assertEqual(hypothesis_context["knowledge_gap"]["entities"], ["补中益气汤", "JAK-STAT"])
        self.assertGreaterEqual(len(hypothesis_context["relationships"]), 2)

    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_experiment_phase_uses_observe_evidence_weights(self, mock_search, mock_close):
        mock_close.return_value = None
        mock_search.return_value = {
            "query": "四君子汤 脾气虚",
            "sources": ["pubmed", "arxiv"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "Traditional chinese medicine formula improves efficacy and safety",
                    "authors": ["A"],
                    "year": 2023,
                    "doi": "10.1000/test1",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "abstract": "Randomized cohort study of traditional chinese medicine formula shows efficacy safety response and machine learning support.",
                },
                {
                    "source": "arxiv",
                    "title": "Machine learning network for TCM syndrome response",
                    "authors": ["B"],
                    "year": 2024,
                    "doi": "",
                    "url": "https://arxiv.org/abs/1234",
                    "abstract": "Network analysis for herb formula response with risk and effectiveness outcomes.",
                },
            ],
            "query_plans": [],
            "source_stats": {
                "pubmed": {"count": 1, "mode": "open_api", "source_name": "PubMed"},
                "arxiv": {"count": 1, "mode": "open_api", "source_name": "arXiv"},
            },
            "errors": [],
        }

        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-evidence-cycle",
            description="experiment evidence integration",
            objective="验证方剂配伍与证候关联",
            scope="中医古籍方剂研究",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": True,
                "literature_query": "四君子汤 脾气虚",
                "run_preprocess_and_extract": False,
                "use_ctext_whitelist": False,
            },
        )
        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.HYPOTHESIS,
            {
                "entities": [
                    {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                ],
                "contradictions": ["存在个别样本偏差"],
            },
        )

        experiment_result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT, {})

        self.assertEqual(experiment_result["metadata"]["evidence_record_count"], 2)
        self.assertGreater(experiment_result["metadata"]["weighted_evidence_score"], 0.0)
        self.assertIn("evidence_profile", experiment_result["results"])
        self.assertEqual(experiment_result["results"]["evidence_profile"]["record_count"], 2)
        self.assertEqual(len(experiment_result["results"]["source_weights"]), 2)
        self.assertIn(experiment_result["results"]["methodology"], {
            "evidence_weighted_analysis",
            "multisource_weighted_comparative_analysis",
            "gap_informed_evidence_weighted_analysis",
        })
        self.assertNotEqual(experiment_result["results"]["sample_size"], 100)
        self.assertIn("PubMed", experiment_result["results"]["data_sources"])

    @patch("src.research.research_pipeline.ResearchPipeline._run_clinical_gap_analysis")
    @patch("src.research.research_pipeline.LiteratureRetriever.close")
    @patch("src.research.research_pipeline.LiteratureRetriever.search")
    def test_experiment_phase_escalates_design_for_high_priority_gap(self, mock_search, mock_close, mock_gap):
        mock_close.return_value = None
        mock_search.return_value = {
            "query": "四君子汤 脾气虚",
            "sources": ["pubmed", "arxiv"],
            "records": [
                {
                    "source": "pubmed",
                    "title": "Traditional chinese medicine formula improves efficacy and safety",
                    "authors": ["A"],
                    "year": 2023,
                    "doi": "10.1000/test1",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "abstract": "Randomized cohort study of traditional chinese medicine formula shows efficacy safety response and machine learning support.",
                },
                {
                    "source": "arxiv",
                    "title": "Machine learning network for TCM syndrome response",
                    "authors": ["B"],
                    "year": 2024,
                    "doi": "",
                    "url": "https://arxiv.org/abs/1234",
                    "abstract": "Network analysis for herb formula response with risk and effectiveness outcomes.",
                },
            ],
            "query_plans": [],
            "source_stats": {
                "pubmed": {"count": 1, "mode": "open_api", "source_name": "PubMed"},
                "arxiv": {"count": 1, "mode": "open_api", "source_name": "arXiv"},
            },
            "errors": [],
        }
        mock_gap.return_value = {
            "report": "gap report",
            "gaps": [
                {"dimension": "outcome", "title": "关键结局覆盖不足", "limitation": "安全性证据弱", "priority": "高"},
                {"dimension": "method", "title": "研究设计单一", "limitation": "缺少多中心对照", "priority": "中"},
            ],
            "priority_summary": {
                "counts": {"高": 1, "中": 1, "低": 0},
                "highest_priority": "高",
                "total_gaps": 2,
            },
        }

        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-gap-priority-cycle",
            description="experiment high priority gap integration",
            objective="验证方剂配伍与证候关联",
            scope="中医古籍方剂研究",
            researchers=["tester"],
        )
        self.assertTrue(self.pipeline.start_research_cycle(cycle.cycle_id))

        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.OBSERVE,
            {
                "run_literature_retrieval": True,
                "run_clinical_gap_analysis": True,
                "literature_query": "四君子汤 脾气虚",
                "run_preprocess_and_extract": False,
                "use_ctext_whitelist": False,
            },
        )
        self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.HYPOTHESIS,
            {
                "entities": [
                    {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.88},
                ],
                "contradictions": ["存在个别样本偏差"],
            },
        )

        experiment_result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.EXPERIMENT, {})

        self.assertEqual(experiment_result["results"]["methodology"], "high_priority_gap_escalated_validation")
        self.assertEqual(experiment_result["results"]["gap_priority_summary"]["highest_priority"], "高")
        self.assertEqual(experiment_result["metadata"]["highest_gap_priority"], "高")
        self.assertGreaterEqual(experiment_result["results"]["sample_size"], 100)

    def test_experiment_phase_learning_strategy_can_disable_llm_protocol_generation(self):
        pipeline = ResearchPipeline({"llm_engine": _ExperimentPhaseFakeLLM()})
        self.addCleanup(pipeline.cleanup)

        cycle = pipeline.create_research_cycle(
            cycle_name="experiment-learning-strategy-llm-off",
            description="experiment learning strategy llm disable",
            objective="验证实验协议 LLM 开关",
            scope="中医古籍方剂研究",
            researchers=["tester"],
        )
        cycle.phase_executions[pipeline.ResearchPhase.OBSERVE] = {
            "result": {
                "phase": "observe",
                "results": {
                    "literature_pipeline": {
                        "evidence_matrix": {"records": [], "dimension_count": 0, "record_count": 0},
                        "clinical_gap_analysis": {},
                    }
                },
            }
        }
        cycle.phase_executions[pipeline.ResearchPhase.HYPOTHESIS] = {
            "result": {
                "phase": "hypothesis",
                "results": {
                    "hypotheses": [
                        {
                            "hypothesis_id": "hyp-1",
                            "title": "四君子汤改善脾气虚证",
                            "statement": "四君子汤可改善脾气虚证主要结局",
                            "validation_plan": "对照验证",
                            "domain": "formula_research",
                            "confidence": 0.82,
                            "keywords": ["四君子汤", "脾气虚证"],
                        }
                    ]
                },
                "metadata": {"selected_hypothesis_id": "hyp-1"},
            }
        }

        experiment_result = pipeline.phase_handlers.execute_experiment_phase(
            cycle,
            {
                "learning_strategy": {
                    "experiment_use_llm_protocol_generation": False,
                }
            },
        )

        self.assertEqual(experiment_result["results"]["study_protocol"]["protocol_source"], "template")
        self.assertFalse(experiment_result["metadata"]["protocol_llm_generation_enabled"])
        self.assertTrue(experiment_result["metadata"]["learning_strategy_applied"])

    def test_experiment_phase_learning_strategy_expands_sample_size_and_duration(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-learning-strategy-sizing",
            description="experiment learning strategy sizing",
            objective="验证实验协议样本量与时长调节",
            scope="中医古籍方剂研究",
            researchers=["tester"],
        )
        cycle.phase_executions[self.pipeline.ResearchPhase.OBSERVE] = {
            "result": {
                "phase": "observe",
                "results": {
                    "literature_pipeline": {
                        "evidence_matrix": {
                            "records": [
                                {"title": "e1", "source": "pubmed", "coverage_score": 4.0},
                                {"title": "e2", "source": "arxiv", "coverage_score": 3.0},
                            ],
                            "dimension_count": 4,
                            "record_count": 2,
                        },
                        "source_stats": {
                            "pubmed": {"count": 1, "source_name": "PubMed"},
                            "arxiv": {"count": 1, "source_name": "arXiv"},
                        },
                        "clinical_gap_analysis": {},
                    }
                },
            }
        }
        cycle.phase_executions[self.pipeline.ResearchPhase.HYPOTHESIS] = {
            "result": {
                "phase": "hypothesis",
                "results": {
                    "hypotheses": [
                        {
                            "hypothesis_id": "hyp-2",
                            "title": "四君子汤改善脾气虚证",
                            "statement": "四君子汤可改善脾气虚证主要结局",
                            "validation_plan": "对照验证",
                            "domain": "formula_research",
                            "confidence": 0.8,
                            "keywords": ["四君子汤", "脾气虚证"],
                            "contradiction_signals": ["存在个别样本偏差"],
                        }
                    ]
                },
                "metadata": {"selected_hypothesis_id": "hyp-2"},
            }
        }

        baseline_result = self.pipeline.phase_handlers.execute_experiment_phase(cycle, {})
        strategy_result = self.pipeline.phase_handlers.execute_experiment_phase(
            cycle,
            {
                "learning_strategy": {
                    "tuned_parameters": {
                        "quality_threshold": 0.84,
                        "confidence_threshold": 0.83,
                    }
                }
            },
        )

        self.assertGreater(strategy_result["results"]["sample_size"], baseline_result["results"]["sample_size"])
        self.assertGreater(strategy_result["results"]["duration_days"], baseline_result["results"]["duration_days"])
        self.assertEqual(strategy_result["results"]["methodology"], "multisource_weighted_comparative_analysis")
        self.assertTrue(strategy_result["metadata"]["learning_strategy_applied"])

    def test_experiment_execution_learning_strategy_filters_relationships_and_caps_imports(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-execution-learning-strategy-caps",
            description="experiment execution learning strategy caps",
            objective="验证实验执行导入策略过滤与限流",
            scope="中医古籍方剂研究",
            researchers=["tester"],
        )
        cycle.phase_executions[self.pipeline.ResearchPhase.EXPERIMENT] = {
            "result": {
                "phase": "experiment",
                "status": "completed",
                "results": {
                    "protocol_design": {
                        "hypothesis_id": "hyp-exec-1",
                        "protocol_source": "template",
                    },
                    "selected_hypothesis": {
                        "hypothesis_id": "hyp-exec-1",
                        "title": "四君子汤改善脾气虚证",
                    },
                    "study_protocol": {"protocol_source": "template"},
                },
                "metadata": {"protocol_source": "template"},
                "error": None,
            }
        }

        execution_result = self.pipeline.phase_handlers.execute_experiment_execution_phase(
            cycle,
            {
                "analysis_records": [
                    {"formula": "四君子汤", "syndrome": "脾气虚证", "herbs": ["党参", "白术"]},
                    {"formula": "补中益气汤", "syndrome": "中气下陷", "herbs": ["黄芪", "人参"]},
                    {"formula": "理中汤", "syndrome": "脾胃虚寒", "herbs": ["干姜", "人参"]},
                ],
                "analysis_relationships": [
                    {
                        "source": "四君子汤",
                        "target": "党参",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.61, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": "补中益气汤",
                        "target": "黄芪",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.86, "source": "observe_semantic_graph"},
                    },
                    {
                        "source": "理中汤",
                        "target": "干姜",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "metadata": {"confidence": 0.91, "source": "observe_semantic_graph"},
                    },
                ],
                "sampling_events": [
                    {"batch": "b1", "size": 12},
                    {"batch": "b2", "size": 10},
                ],
                "learning_strategy": {
                    "tuned_parameters": {"confidence_threshold": 0.8},
                    "experiment_execution_max_records": 2,
                    "experiment_execution_max_relationships": 1,
                    "experiment_execution_max_sampling_events": 1,
                },
            },
        )

        cycle.phase_executions[self.pipeline.ResearchPhase.EXPERIMENT_EXECUTION] = {
            "result": execution_result,
        }
        analyze_result = self.pipeline.phase_handlers.execute_analyze_phase(cycle, {})

        self.assertEqual(execution_result["status"], "completed")
        self.assertEqual(len(execution_result["results"]["analysis_records"]), 2)
        self.assertEqual(len(execution_result["results"]["analysis_relationships"]), 1)
        self.assertEqual(len(execution_result["results"]["sampling_events"]), 1)
        self.assertTrue(execution_result["metadata"]["learning_strategy_applied"])
        self.assertEqual(analyze_result["metadata"]["record_count"], 2)

    def test_experiment_execution_learning_strategy_can_disable_document_fallback_import(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="experiment-execution-learning-strategy-doc-fallback",
            description="experiment execution learning strategy document fallback",
            objective="验证实验执行 document fallback 开关",
            scope="中医古籍方剂研究",
            researchers=["tester"],
        )
        cycle.phase_executions[self.pipeline.ResearchPhase.EXPERIMENT] = {
            "result": {
                "phase": "experiment",
                "status": "completed",
                "results": {
                    "protocol_design": {
                        "hypothesis_id": "hyp-exec-2",
                        "protocol_source": "template",
                    },
                    "selected_hypothesis": {
                        "hypothesis_id": "hyp-exec-2",
                        "title": "四君子汤改善脾气虚证",
                    },
                    "study_protocol": {"protocol_source": "template"},
                },
                "metadata": {"protocol_source": "template"},
                "error": None,
            }
        }

        execution_result = self.pipeline.phase_handlers.execute_experiment_execution_phase(
            cycle,
            {
                "documents": [
                    {
                        "title": "外部实验文档",
                        "semantic_relationships": [
                            {
                                "source": "四君子汤",
                                "target": "党参",
                                "type": "contains",
                                "source_type": "formula",
                                "target_type": "herb",
                            },
                            {
                                "source": "四君子汤",
                                "target": "脾气虚证",
                                "type": "targets",
                                "source_type": "formula",
                                "target_type": "syndrome",
                            },
                        ],
                    }
                ],
                "learning_strategy": {
                    "experiment_execution_allow_document_fallback_import": False,
                },
            },
        )

        self.assertEqual(execution_result["status"], "skipped")
        self.assertEqual(execution_result["results"]["analysis_records"], [])
        self.assertEqual(execution_result["results"]["analysis_relationships"], [])
        self.assertFalse(execution_result["metadata"]["document_fallback_import_enabled"])
        self.assertTrue(execution_result["metadata"]["learning_strategy_applied"])
