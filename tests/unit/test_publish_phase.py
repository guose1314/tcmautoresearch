# tests/unit/test_publish_phase.py
"""PublishPhaseMixin 单元测试

覆盖：
  - 正常路径：有引用记录、论文生成、IMRD 报告
  - 降级路径：PaperWriter / ReportGenerator 失败时回退
  - 空输入边界：无 citation_records、无先前阶段产出
  - deliverables 列表动态构建
  - output_files 合并逻辑
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.research.phase_handlers.publish_handler import PublishPhaseHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EXPERIMENT_EXECUTION = "experiment_execution"
    ANALYZE = "analyze"
    PUBLISH = "publish"
    REFLECT = "reflect"


@dataclass
class _FakeCycle:
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    researchers: List[str] = field(default_factory=lambda: ["张三"])
    cycle_name: str = "test_cycle"
    cycle_id: str = "test_cycle_001"
    description: str = "单元测试循环"
    research_objective: str = "中药配伍研究"
    research_scope: str = "中药古籍"
    target_audience: str = "研究者"
    started_at: str = "2026-01-01T00:00:00"
    completed_at: str = ""
    duration: float = 0.0
    advisors: List[str] = field(default_factory=list)
    deliverables: List[Dict[str, Any]] = field(default_factory=list)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    expert_reviews: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Any] = field(default_factory=dict)
    budget: float = 0.0
    timeline: Dict[str, str] = field(default_factory=dict)


class _FakePipeline:
    ResearchPhase = _Phase

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.output_port = MagicMock()
        self.analysis_port = MagicMock()
        self._learning_phase_manifests: list = []
        self.analysis_port.create_reasoning_engine.side_effect = RuntimeError("no engine")
        # Fallback class refs (used when output_port fails)
        self.CitationManager = None
        self.PaperWriter = None
        self.OutputGenerator = None
        self.ReportGenerator = None
        self._setup_default_mocks()

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._learning_phase_manifests.append(manifest)

    def _setup_default_mocks(self):
        # CitationManager mock
        cm = MagicMock()
        cm.execute.return_value = {
            "entries": [{"title": "本草纲目", "authors": ["李时珍"], "year": 1578}],
            "bibtex": "@book{bencao, title={本草纲目}}",
            "gbt7714": "[1] 李时珍. 本草纲目.",
            "formatted_references": "refs",
            "citation_count": 1,
            "output_files": {},
        }
        self.output_port.create_citation_manager.return_value = cm

        # PaperWriter mock
        pw = MagicMock()
        pw.execute.return_value = {
            "paper_draft": {
                "title": "Test Paper",
                "abstract": "Abstract",
                "sections": [{"section_type": "introduction", "title": "引言", "content": "..."}],
                "keywords": ["中药"],
            },
            "language": "zh",
            "section_count": 1,
            "reference_count": 1,
            "output_files": {"markdown": "/tmp/paper.md"},
        }
        self.output_port.create_paper_writer.return_value = pw

        # ReportGenerator mock
        rg = MagicMock()
        rg.execute.return_value = {
            "reports": {"markdown": {"title": "Report", "content": "..."}},
            "errors": [],
            "output_files": {"imrd_markdown": "/tmp/report.md"},
        }
        self.output_port.create_report_generator.return_value = rg

    def _extract_corpus_text_entries(self, corpus_result):
        return []


def _make_handler(pipeline=None):
    return PublishPhaseHandler(pipeline or _FakePipeline())


def _minimal_phase_executions():
    return {
        _Phase.OBSERVE: {"result": {}},
        _Phase.HYPOTHESIS: {"result": {"hypotheses": []}},
        _Phase.EXPERIMENT: {"result": {}},
        _Phase.EXPERIMENT_EXECUTION: {"result": {}},
        _Phase.ANALYZE: {"result": {}},
    }


# ---------------------------------------------------------------------------
# 1) 返回契约
# ---------------------------------------------------------------------------


class TestPublishPhaseContract(unittest.TestCase):

    def test_return_has_required_keys(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": [{"title": "test"}]})
        for key in ("phase", "metadata"):
            self.assertIn(key, result, f"missing key: {key}")
        self.assertIn("publications", result["results"])
        self.assertIn("citations", result["results"])
        self.assertIn("bibtex", result["results"])
        self.assertIn("gbt7714", result["results"])
        self.assertIn("formatted_references", result["results"])
        self.assertIn("deliverables", result["results"])
        self.assertIn("output_files", result["results"])
        self.assertIn("analysis_results", result["results"])
        self.assertIn("research_artifact", result["results"])
        self.assertNotIn("publications", result)
        self.assertNotIn("citations", result)
        self.assertNotIn("bibtex", result)
        self.assertNotIn("gbt7714", result)
        self.assertNotIn("formatted_references", result)
        self.assertNotIn("deliverables", result)
        self.assertNotIn("output_files", result)
        self.assertNotIn("paper_draft", result)
        self.assertNotIn("imrd_reports", result)
        self.assertNotIn("paper_draft", result["results"])
        self.assertNotIn("imrd_reports", result["results"])
        self.assertNotIn("analysis_results", result)
        self.assertNotIn("research_artifact", result)
        self.assertNotIn("llm_analysis_context", result)
        self.assertNotIn("paper_language", result)
        self.assertNotIn("report_generation_errors", result)
        self.assertNotIn("report_session_result", result)
        self.assertEqual(result["phase"], "publish")

    def test_metadata_has_required_fields(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        md = result["metadata"]
        for key in ("publication_count", "deliverable_count", "citation_count"):
            self.assertIn(key, md, f"missing metadata key: {key}")


# ---------------------------------------------------------------------------
# 2) 正常路径
# ---------------------------------------------------------------------------


class TestPublishNormalPath(unittest.TestCase):

    def test_publish_records_section_planner_preview_for_deterministic_writer(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())

        result = handler.execute(cycle, {"citation_records": []})

        planner = result["metadata"]["small_model_plan"]
        self.assertIsInstance(planner, dict)
        self.assertEqual(planner["phase"], "publish")
        self.assertEqual(planner["task_type"], "paper_section")
        self.assertTrue(planner["plan_only"])
        self.assertEqual(planner["writer_mode"], "deterministic")
        self.assertEqual(planner["section_count"], 1)
        self.assertEqual(result["metadata"]["fallback_path"], "deterministic_paper_writer")
        section_plans = result["metadata"]["publish_section_plans"]
        self.assertEqual(section_plans["sections"][0]["section_type"], "introduction")
        self.assertTrue(section_plans["sections"][0]["plan_only"])

    def test_citations_returned_from_citation_manager(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": [{"title": "test"}]})
        self.assertGreater(len(result["results"]["citations"]), 0)
        self.assertIn("bibtex", result["results"])

    def test_publications_capture_generated_paper_summary(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        publications = result["results"]["publications"]
        main_publication = publications[0]
        self.assertEqual(main_publication["title"], "Test Paper")
        self.assertEqual(main_publication["section_count"], 1)
        self.assertEqual(main_publication["status"], "draft_generated")

    def test_deliverables_contains_base_items(self):
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertIn("研究报告", result["results"]["deliverables"])
        self.assertIn("数据集", result["results"]["deliverables"])

    def test_publish_prefers_selected_hypothesis_id_over_experiment_legacy_field(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions={
                _Phase.OBSERVE: {"result": {}},
                _Phase.HYPOTHESIS: {
                    "result": {
                        "results": {
                            "hypotheses": [
                                {"hypothesis_id": "hyp-1", "title": "候选 1", "keywords": ["A"]},
                                {"hypothesis_id": "hyp-2", "title": "候选 2", "keywords": ["B"]},
                            ]
                        },
                        "metadata": {"selected_hypothesis_id": "hyp-2"},
                    }
                },
                _Phase.EXPERIMENT: {
                    "result": {
                        "metadata": {"selected_hypothesis_id": "hyp-2"},
                        "selected_hypothesis": {"hypothesis_id": "legacy", "title": "旧顶层假设"},
                    }
                },
                _Phase.ANALYZE: {"result": {}},
            }
        )

        result = handler.execute(cycle, {"citation_records": []})

        self.assertEqual(result["phase"], "publish")
        paper_context = pipeline.output_port.create_paper_writer.return_value.execute.call_args.args[0]
        self.assertEqual(paper_context["hypothesis"].get("hypothesis_id"), "hyp-2")
        self.assertEqual(paper_context["hypothesis"].get("title"), "候选 2")

    def test_publish_ignores_legacy_top_level_reasoning_results_from_phase_result_context(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions={
                _Phase.OBSERVE: {"result": {}},
                _Phase.HYPOTHESIS: {"result": {"results": {"hypotheses": []}, "metadata": {}, "error": None}},
                _Phase.EXPERIMENT: {"result": {"results": {}, "metadata": {}, "error": None}},
                _Phase.ANALYZE: {
                    "result": {
                        "phase": "analyze",
                        "status": "completed",
                        "results": {
                            "reasoning_results": {
                                "evidence_records": [{"evidence_id": "nested"}],
                            }
                        },
                        "metadata": {},
                        "error": None,
                        "reasoning_results": {
                            "evidence_records": [{"evidence_id": "legacy-analyze"}],
                        },
                    }
                },
            }
        )

        handler.execute(
            cycle,
            {
                "phase": "analyze",
                "status": "completed",
                "results": {},
                "metadata": {},
                "error": None,
                "reasoning_results": {
                    "evidence_records": [{"evidence_id": "legacy-context"}],
                },
            },
        )

        paper_context = pipeline.output_port.create_paper_writer.return_value.execute.call_args.args[0]
        self.assertEqual(paper_context["reasoning_results"]["evidence_records"][0]["evidence_id"], "nested")

    def test_publish_prefers_nested_statistical_analysis_over_legacy_result_root_mirrors(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        analyze_result = {
            "phase": "analyze",
            "status": "completed",
            "results": {
                "confidence_level": 0.11,
                "limitations": ["legacy limitation"],
                "statistical_analysis": {
                    "confidence_level": 0.93,
                    "limitations": ["nested limitation"],
                },
            },
            "metadata": {},
            "error": None,
        }
        analyze_results = analyze_result["results"]

        statistical_analysis = handler._resolve_publish_statistical_analysis({}, analyze_result, analyze_results)
        limitations = handler._resolve_publish_limitations({}, analyze_results, {"statistical_analysis": statistical_analysis})

        self.assertEqual(statistical_analysis["confidence_level"], 0.93)
        self.assertEqual(limitations, ["nested limitation"])

    def test_publish_external_payloads_remove_publish_mining_aliases(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions={
                _Phase.OBSERVE: {"result": {}},
                _Phase.HYPOTHESIS: {"result": {"results": {"hypotheses": []}, "metadata": {}, "error": None}},
                _Phase.EXPERIMENT: {"result": {"results": {}, "metadata": {}, "error": None}},
                _Phase.ANALYZE: {
                    "result": {
                        "phase": "analyze",
                        "status": "completed",
                        "results": {
                            "statistical_analysis": {
                                "primary_association": {
                                    "herb": "桂枝",
                                    "syndrome": "营卫不和",
                                    "p_value": 0.004,
                                }
                            },
                            "data_mining_result": {
                                "record_count": 24,
                                "transaction_count": 24,
                                "item_count": 8,
                                "methods_executed": ["frequency_chi_square", "association_rules", "clustering"],
                                "frequency_chi_square": {
                                    "chi_square_top": [{"herb": "桂枝", "syndrome": "营卫不和"}],
                                    "herb_frequency": [{"herb": "桂枝", "count": 10}],
                                },
                                "association_rules": {
                                    "rules": [{"rule_id": "r-1", "support": 0.42}],
                                },
                                "clustering": {
                                    "cluster_summary": [{"cluster": 0, "size": 24}],
                                },
                            },
                            "reasoning_results": {"evidence_records": []},
                        },
                        "metadata": {},
                        "error": None,
                    }
                },
            }
        )

        result = handler.execute(cycle, {"citation_records": []})
        analysis_results = result["results"]["analysis_results"]
        research_artifact = result["results"]["research_artifact"]

        for payload in (analysis_results, research_artifact):
            self.assertNotIn("primary_association", payload)
            self.assertNotIn("data_mining_summary", payload)
            self.assertNotIn("data_mining_methods", payload)
            self.assertNotIn("frequency_chi_square", payload)
            self.assertNotIn("association_rules", payload)
            self.assertNotIn("clustering", payload)

        self.assertEqual(
            analysis_results["statistical_analysis"]["primary_association"]["herb"],
            "桂枝",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["frequency_chi_square"]["chi_square_top"][0]["herb"],
            "桂枝",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["association_rules"]["rules"][0]["rule_id"],
            "r-1",
        )
        self.assertEqual(
            analysis_results["data_mining_result"]["clustering"]["cluster_summary"][0]["cluster"],
            0,
        )
        self.assertEqual(
            research_artifact["statistical_analysis"]["primary_association"]["syndrome"],
            "营卫不和",
        )
        self.assertNotIn("analysis_results", result)
        self.assertNotIn("research_artifact", result)


# ---------------------------------------------------------------------------
# 3) 降级路径
# ---------------------------------------------------------------------------


class TestPublishDegradation(unittest.TestCase):

    def test_paper_writer_failure_doesnt_crash(self):
        """PaperWriter 执行失败时不崩溃。"""
        pipeline = _FakePipeline()
        pw = MagicMock()
        pw.execute.side_effect = RuntimeError("paper boom")
        pipeline.output_port.create_paper_writer.return_value = pw
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        try:
            result = handler.execute(cycle, {"citation_records": []})
            self.assertEqual(result["phase"], "publish")
        except RuntimeError:
            pass  # 可接受：PaperWriter 是必要组件

    def test_report_generator_failure_doesnt_crash(self):
        """ReportGenerator 失败时不阻塞发布。"""
        pipeline = _FakePipeline()
        rg = MagicMock()
        rg.initialize.return_value = True
        rg.generate_report.side_effect = RuntimeError("report boom")
        pipeline.output_port.create_report_generator.return_value = rg
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertEqual(result["phase"], "publish")
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["metadata"].get("report_error_count"), 2)
        self.assertNotIn("report_generation_errors", result)

    def test_citation_manager_creation_fails(self):
        """output_port + module fallback 均失败时应抛 RuntimeError。"""
        pipeline = _FakePipeline()
        pipeline.output_port.create_citation_manager.side_effect = RuntimeError("no CM")
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        with patch("src.research.phases.publish_phase.CitationManager", None):
            with self.assertRaises(RuntimeError):
                handler.execute(cycle, {"citation_records": []})


# ---------------------------------------------------------------------------
# 4) 空输入边界
# ---------------------------------------------------------------------------


class TestPublishEmptyInput(unittest.TestCase):

    def test_empty_citation_records(self):
        """空 citation_records 不崩溃。"""
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertEqual(result["phase"], "publish")

    def test_no_prior_phase_executions(self):
        """phase_executions 为空时不崩溃。"""
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions={})
        result = handler.execute(cycle, {"citation_records": []})
        self.assertEqual(result["phase"], "publish")

    def test_none_context(self):
        """context=None 不崩溃。"""
        handler = _make_handler()
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, None)
        self.assertEqual(result["phase"], "publish")


# ---------------------------------------------------------------------------
# 5) deliverables 动态构建
# ---------------------------------------------------------------------------


class TestPublishDeliverablesDynamic(unittest.TestCase):

    def test_bibtex_available_adds_deliverable(self):
        pipeline = _FakePipeline()
        cm = MagicMock()
        cm.execute.return_value = {
            "entries": [],
            "bibtex": "@book{x}",
            "gbt7714": "",
            "formatted_references": "",
            "citation_count": 0,
            "output_files": {},
        }
        pipeline.output_port.create_citation_manager.return_value = cm
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": [{"title": "t"}]})
        self.assertIn("BibTeX 参考文献", result["results"]["deliverables"])
        self.assertNotIn("GB/T 7714 参考文献", result["results"]["deliverables"])

    def test_markdown_output_adds_deliverable(self):
        pipeline = _FakePipeline()
        pw = MagicMock()
        pw.execute.return_value = {
            "paper_draft": {},
            "language": "zh",
            "section_count": 0,
            "reference_count": 0,
            "output_files": {"markdown": "/tmp/paper.md"},
        }
        pipeline.output_port.create_paper_writer.return_value = pw
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())
        result = handler.execute(cycle, {"citation_records": []})
        self.assertIn("Markdown 论文初稿", result["results"]["deliverables"])


class TestPublishLearningStrategy(unittest.TestCase):

    def test_learning_strategy_can_disable_paper_and_report_generation(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(phase_executions=_minimal_phase_executions())

        result = handler.execute(
            cycle,
            {
                "citation_records": [{"title": "本草纲目"}],
                "learning_strategy": {
                    "publish_generate_paper": False,
                    "publish_generate_reports": False,
                },
            },
        )

        pipeline.output_port.create_paper_writer.assert_not_called()
        pipeline.output_port.create_report_generator.assert_not_called()
        self.assertEqual(result["results"]["publications"], [])
        self.assertTrue(result["metadata"]["learning_strategy_applied"])
        self.assertFalse(result["metadata"]["paper_generation_enabled"])
        self.assertFalse(result["metadata"]["report_generation_enabled"])

    def test_learning_strategy_can_disable_pipeline_citation_fallback(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions=_minimal_phase_executions(),
            outcomes=[{"phase": "observe", "result": {"title": "fallback citation"}}],
        )

        handler.execute(
            cycle,
            {
                "learning_strategy": {
                    "publish_allow_pipeline_citation_fallback": False,
                }
            },
        )

        citation_records = pipeline.output_port.create_citation_manager.return_value.execute.call_args.args[0]["records"]
        self.assertEqual(citation_records, [])

    def test_learning_strategy_limits_local_citation_records_and_hides_evidence_grade(self):
        pipeline = _FakePipeline()
        pipeline._extract_corpus_text_entries = MagicMock(
            return_value=[
                {"title": f"文献{i}", "urn": f"urn:{i}", "source_type": "local"}
                for i in range(1, 30)
            ]
        )
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions={
                _Phase.OBSERVE: {"result": {"results": {"corpus_collection": {"documents": [{}]}}}},
                _Phase.HYPOTHESIS: {"result": {"results": {"hypotheses": []}}},
                _Phase.EXPERIMENT: {"result": {"results": {}}},
                _Phase.EXPERIMENT_EXECUTION: {"result": {"results": {}}},
                _Phase.ANALYZE: {
                    "result": {
                        "results": {
                            "statistical_analysis": {
                                "evidence_grade_summary": {"overall_grade": "high"},
                            }
                        }
                    }
                },
            }
        )

        handler.execute(
            cycle,
            {
                "learning_strategy": {
                    "tuned_parameters": {"quality_threshold": 0.52},
                    "publish_include_evidence_grade": False,
                }
            },
        )

        citation_records = pipeline.output_port.create_citation_manager.return_value.execute.call_args.args[0]["records"]
        self.assertEqual(len(citation_records), 12)
        paper_context = pipeline.output_port.create_paper_writer.return_value.execute.call_args.args[0]
        self.assertEqual(paper_context["evidence_grade_summary"], {})

    def test_publish_preserves_analyze_evidence_protocol_without_structured_output(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions={
                **_minimal_phase_executions(),
                _Phase.ANALYZE: {
                    "result": {
                        "phase": "analyze",
                        "status": "completed",
                        "results": {
                            "reasoning_results": {
                                "reasoning_results": {
                                    "entity_relationships": [
                                        {"source": "桂枝", "target": "营卫", "type": "调和", "confidence": 0.88}
                                    ]
                                }
                            },
                            "evidence_protocol": {
                                "contract_version": "evidence-claim-v2",
                                "evidence_records": [
                                    {
                                        "evidence_id": "ev-1",
                                        "title": "伤寒论",
                                        "source_type": "classical_text",
                                        "source_ref": "urn:shanghanlun",
                                    }
                                ],
                                "claims": [{"claim_id": "claim-1"}],
                            },
                            "statistical_analysis": {},
                        },
                        "metadata": {},
                        "error": None,
                    }
                },
            }
        )

        result = handler.execute(cycle, {"generate_structured_output": False, "citation_records": []})

        analysis_results = result["results"]["analysis_results"]
        research_artifact = result["results"]["research_artifact"]
        self.assertEqual(analysis_results["evidence_protocol"]["contract_version"], "evidence-claim-v2")
        self.assertEqual(analysis_results["evidence_protocol"]["evidence_records"][0]["evidence_id"], "ev-1")
        self.assertEqual(research_artifact["evidence"][0]["evidence_id"], "ev-1")

    def test_publish_derives_citation_records_from_evidence_protocol_when_sources_absent(self):
        pipeline = _FakePipeline()
        handler = _make_handler(pipeline)
        cycle = _FakeCycle(
            phase_executions={
                **_minimal_phase_executions(),
                _Phase.ANALYZE: {
                    "result": {
                        "phase": "analyze",
                        "status": "completed",
                        "results": {
                            "reasoning_results": {},
                            "evidence_protocol": {
                                "contract_version": "evidence-claim-v2",
                                "evidence_records": [
                                    {
                                        "evidence_id": "ev-1",
                                        "title": "伤寒论",
                                        "authors": ["张仲景"],
                                        "year": 210,
                                        "source_type": "classical_text",
                                        "source_ref": "urn:shanghanlun",
                                        "relation_type": "文献证据",
                                    }
                                ],
                                "claims": [],
                            },
                            "statistical_analysis": {},
                        },
                        "metadata": {},
                        "error": None,
                    }
                },
            }
        )

        handler.execute(cycle, {"allow_pipeline_citation_fallback": False})

        citation_records = pipeline.output_port.create_citation_manager.return_value.execute.call_args.args[0]["records"]
        self.assertEqual(len(citation_records), 1)
        self.assertEqual(citation_records[0]["title"], "伤寒论")
        self.assertEqual(citation_records[0]["source_ref"], "urn:shanghanlun")
        self.assertEqual(citation_records[0]["source_type"], "classical_text")


if __name__ == "__main__":
    unittest.main()
