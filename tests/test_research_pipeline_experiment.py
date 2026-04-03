import unittest
from unittest.mock import patch

from src.research.research_pipeline import ResearchPhase, ResearchPipeline


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
        self.assertEqual(len(experiment_result["experiments"]), 1)
        self.assertEqual(experiment_result["experiments"][0]["hypothesis_id"], selected_id)
        self.assertIn("validation_plan", experiment_result["results"])
        self.assertEqual(experiment_result["success_rate"], 1.0)

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

        hypothesis_context = self.pipeline.phase_handlers._build_hypothesis_context(
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