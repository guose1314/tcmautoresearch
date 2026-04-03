import importlib
import os
import tempfile
import unittest

from src.collector.literature_retriever import LiteratureRecord
from src.output.citation_manager import CitationManager
from src.research.research_pipeline import ResearchPhase, ResearchPipeline

DOCX_AVAILABLE = True
try:
    importlib.import_module("docx")
except ImportError:
    DOCX_AVAILABLE = False


class TestCitationManager(unittest.TestCase):
    def setUp(self):
        self.manager = CitationManager({"include_abstract": False})
        self.manager.initialize()

    def tearDown(self):
        self.manager.cleanup()

    def test_generate_bibtex_from_article_records(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "title": "Large Language Models for TCM Research",
                        "authors": ["Alice Smith", "Bob Chen"],
                        "year": 2024,
                        "journal": "Journal of TCM Informatics",
                        "doi": "10.1000/tcm.2024.1",
                        "url": "https://example.com/paper",
                        "abstract": "unused",
                    }
                ]
            }
        )
        self.assertEqual(result["citation_count"], 1)
        bibtex = result["bibtex"]
        self.assertIn("@article{Smith2024Large", bibtex)
        self.assertIn("author = {Smith, Alice and Chen, Bob}", bibtex)
        self.assertIn("journal = {Journal of TCM Informatics}", bibtex)
        self.assertIn("doi = {10.1000/tcm.2024.1}", bibtex)

    def test_duplicate_keys_gain_suffix(self):
        result = self.manager.execute(
            {
                "records": [
                    {"title": "TCM Study A", "authors": ["Alice Smith"], "year": 2024, "journal": "J1"},
                    {"title": "TCM Study B", "authors": ["Alice Smith"], "year": 2024, "journal": "J2"},
                ]
            }
        )
        keys = [entry["citation_key"] for entry in result["entries"]]
        self.assertEqual(keys[0], "Smith2024TCM")
        self.assertEqual(keys[1], "Smith2024TCMb")

    def test_chinese_author_and_arxiv_misc(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "title": "中医方剂知识图谱预印本",
                        "authors": "张三, 李四",
                        "publish_date": "2023-08-01",
                        "source": "arxiv",
                        "url": "https://arxiv.org/abs/1234.5678",
                    }
                ]
            }
        )
        entry = result["entries"][0]
        self.assertEqual(entry["entry_type"], "misc")
        self.assertEqual(entry["year"], "2023")
        self.assertIn("author = {张三 and 李四}", result["bibtex"])

    def test_normalize_record_field_fallbacks(self):
        result = self.manager.execute(
            {
                "records": [
                    {
                        "name": "Fallback Title",
                        "author": "Ada Lovelace",
                        "published": "2022-02-01",
                        "venue": "Fallback Venue",
                        "link": "https://example.org/fallback",
                        "page": "12-18",
                        "issue": "9",
                    }
                ]
            }
        )
        entry = result["entries"][0]
        self.assertEqual(entry["title"], "Fallback Title")
        self.assertEqual(entry["journal"], "Fallback Venue")
        self.assertEqual(entry["url"], "https://example.org/fallback")
        self.assertEqual(entry["pages"], "12-18")
        self.assertEqual(entry["number"], "9")

    def test_generate_gbt7714_from_article_record(self):
        manager = CitationManager({"format": "GB/T 7714-2015"})
        manager.initialize()
        try:
            result = manager.execute(
                {
                    "records": [
                        {
                            "title": "Large Language Models for TCM Research",
                            "authors": ["Alice Smith", "Bob Chen"],
                            "year": 2024,
                            "journal": "Journal of TCM Informatics",
                            "volume": "12",
                            "number": "3",
                            "pages": "100-120",
                            "doi": "10.1000/tcm.2024.1",
                        }
                    ]
                }
            )
            self.assertEqual(result["format"], "GB/T 7714-2015")
            self.assertIn("[1]", result["gbt7714"])
            self.assertIn("[J]", result["gbt7714"])
            self.assertIn("DOI: 10.1000/tcm.2024.1", result["gbt7714"])
            self.assertEqual(result["formatted_references"], result["gbt7714"])
        finally:
            manager.cleanup()

    def test_generate_gbt7714_with_chinese_authors(self):
        manager = CitationManager({"format": "gbt"})
        manager.initialize()
        try:
            result = manager.execute(
                {
                    "records": [
                        {
                            "title": "中医方剂知识图谱预印本",
                            "authors": "张三, 李四",
                            "publish_date": "2023-08-01",
                            "source": "arxiv",
                            "url": "https://arxiv.org/abs/1234.5678",
                        }
                    ]
                }
            )
            self.assertIn("张三, 李四", result["gbt7714"])
            self.assertIn("[EB/OL]", result["gbt7714"])
        finally:
            manager.cleanup()

    def test_format_citation_accepts_literature_record(self):
        record = LiteratureRecord(
            source="pubmed",
            title="Large Language Models for TCM Research",
            authors=["Alice Smith", "Bob Chen"],
            year=2024,
            doi="10.1000/tcm.2024.1",
            url="https://pubmed.ncbi.nlm.nih.gov/example",
            abstract="unused",
            citation_count=12,
            external_id="pmid-1",
        )

        citation = self.manager.format_citation(record)

        self.assertIn("Smith Alice, Chen Bob", citation)
        self.assertIn("Large Language Models for TCM Research[J]", citation)
        self.assertIn("pubmed, 2024", citation)
        self.assertIn("DOI: 10.1000/tcm.2024.1", citation)

    def test_generate_bibliography_deduplicates_sorts_and_numbers(self):
        records = [
            LiteratureRecord(
                source="pubmed",
                title="Beta Study",
                authors=["Bob Chen"],
                year=2023,
                doi="",
                url="https://example.org/beta",
                abstract="",
                citation_count=3,
                external_id="beta-1",
            ),
            LiteratureRecord(
                source="pubmed",
                title="Alpha Study",
                authors=["Alice Smith"],
                year=2024,
                doi="",
                url="https://example.org/alpha",
                abstract="",
                citation_count=8,
                external_id="alpha-1",
            ),
            LiteratureRecord(
                source="pubmed",
                title="Alpha Study",
                authors=["Alice Smith"],
                year=2024,
                doi="",
                url="https://example.org/alpha-copy",
                abstract="",
                citation_count=8,
                external_id="alpha-2",
            ),
        ]

        bibliography = self.manager.generate_bibliography(records)

        self.assertIn("[1]", bibliography)
        self.assertIn("[2]", bibliography)
        self.assertEqual(bibliography.count("Alpha Study[J]"), 1)
        self.assertLess(bibliography.index("Alpha Study[J]"), bibliography.index("Beta Study[J]"))

    def test_insert_inline_citation_appends_numeric_marker(self):
        record = LiteratureRecord(
            source="pubmed",
            title="Inline Citation Study",
            authors=["Alice Smith"],
            year=2024,
            doi="",
            url="https://example.org/inline",
            abstract="",
            citation_count=1,
            external_id="inline-1",
        )

        cited = self.manager.insert_inline_citation("该研究提示疗效显著。", record)
        cited_again = self.manager.insert_inline_citation("另一句继续引用", record)

        self.assertEqual(cited, "该研究提示疗效显著[1]。")
        self.assertTrue(cited_again.endswith("[1]"))

    def test_supports_book_thesis_and_electronic_types(self):
        records = [
            {
                "title": "中医方剂学",
                "authors": ["张三"],
                "year": 2020,
                "publisher": "人民卫生出版社",
                "entry_type": "book",
            },
            {
                "title": "基于知识图谱的中医方剂研究",
                "authors": ["李四"],
                "year": 2022,
                "publisher": "北京中医药大学",
                "entry_type": "thesis",
            },
            {
                "title": "中医药数字化资源平台",
                "authors": ["王五"],
                "year": 2025,
                "url": "https://example.org/tcm-resource",
                "entry_type": "electronic",
            },
        ]

        bibliography = self.manager.generate_bibliography(records)

        self.assertIn("[M]", bibliography)
        self.assertIn("[D]", bibliography)
        self.assertIn("[EB/OL]", bibliography)


class TestCitationManagerPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.pipeline = ResearchPipeline(
            {
                "paper_writing": {
                    "output_dir": self.tempdir.name,
                    "output_formats": ["markdown", "docx"],
                },
                "report_generation": {
                    "output_dir": self.tempdir.name,
                    "output_formats": ["markdown", "docx"],
                }
            }
        )

    def tearDown(self):
        self.pipeline.cleanup()
        self.tempdir.cleanup()

    def test_publish_phase_generates_bibtex_from_observe_literature(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-citation-cycle",
            description="publish citation test",
            objective="citation generation",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        cycle.phase_executions[ResearchPhase.OBSERVE] = {
            "result": {
                "literature_pipeline": {
                    "records": [
                        {
                            "title": "Semantic Retrieval for TCM Formulae",
                            "authors": ["Ada Lovelace", "张仲景"],
                            "year": 2025,
                            "journal": "TCM AI Review",
                            "doi": "10.1000/example.doi",
                            "url": "https://example.org/retrieval",
                        }
                    ]
                }
            }
        }

        result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.PUBLISH, {})
        self.assertEqual(result["phase"], "publish")
        self.assertEqual(result["metadata"]["citation_count"], 1)
        self.assertIn("BibTeX 参考文献", result["deliverables"])
        self.assertIn("@article{Lovelace2025Semantic", result["bibtex"])

    def test_publish_phase_prefers_context_citation_records(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-context-citation-cycle",
            description="publish citation override test",
            objective="citation override",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.PUBLISH,
            {
                "citation_records": [
                    {
                        "title": "Custom Citation Record",
                        "authors": ["Grace Hopper"],
                        "year": 2026,
                        "journal": "Custom Journal",
                    }
                ]
            },
        )
        self.assertEqual(result["metadata"]["citation_count"], 1)
        self.assertIn("Custom Citation Record", result["bibtex"])

    def test_publish_phase_includes_gbt_output(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-gbt-citation-cycle",
            description="publish gbt citation test",
            objective="citation gbt",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        result = self.pipeline.execute_research_phase(
            cycle.cycle_id,
            ResearchPhase.PUBLISH,
            {
                "citation_records": [
                    {
                        "title": "GB/T Citation Record",
                        "authors": ["Grace Hopper"],
                        "year": 2026,
                        "journal": "Custom Journal",
                    }
                ]
            },
        )
        self.assertIn("GB/T 7714 参考文献", result["deliverables"])
        self.assertIn("[1]", result["gbt7714"])

    def test_publish_phase_generates_real_paper_outputs(self):
        cycle = self.pipeline.create_research_cycle(
            cycle_name="publish-paper-cycle",
            description="publish paper integration test",
            objective="桂枝汤证据整合",
            scope="src/output",
            researchers=["tester"],
        )
        self.pipeline.start_research_cycle(cycle.cycle_id)
        cycle.phase_executions[ResearchPhase.OBSERVE] = {
            "result": {
                "literature_pipeline": {
                    "records": [
                        {
                            "title": "桂枝汤证据整合研究",
                            "authors": ["Ada Lovelace"],
                            "year": 2025,
                            "journal": "TCM Evidence Review",
                        }
                    ]
                },
                "ingestion_pipeline": {
                    "documents": [
                        {"title": "桂枝汤", "urn": "doc-1"},
                        {"title": "太阳中风证", "urn": "doc-2"},
                    ]
                },
            }
        }
        cycle.phase_executions[ResearchPhase.HYPOTHESIS] = {
            "result": {
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp-1",
                        "title": "桂枝汤调和营卫假设",
                        "statement": "桂枝汤可能通过调和营卫改善太阳中风证相关症状。",
                        "domain": "formula_research",
                        "keywords": ["桂枝汤", "营卫", "太阳中风证"],
                        "validation_plan": "结合古籍文献与现代临床证据进行验证。",
                    }
                ],
                "metadata": {"selected_hypothesis_id": "hyp-1"},
            }
        }
        cycle.phase_executions[ResearchPhase.ANALYZE] = {
            "result": {
                "results": {
                    "statistical_significance": True,
                    "confidence_level": 0.95,
                    "effect_size": 0.76,
                    "p_value": 0.003,
                    "interpretation": "桂枝汤核心配伍与营卫调和证据之间存在稳定关联",
                    "limitations": ["样本量有限"],
                    "evidence_grade": {
                        "overall_grade": "moderate",
                        "overall_score": 0.67,
                        "study_count": 1,
                        "bias_risk_distribution": {"low": 1},
                        "summary": [
                            "纳入 1 项研究进行 GRADE 评估",
                            "整体证据等级为 moderate，平均评分 0.67",
                        ],
                    },
                    "evidence_grade_summary": {
                        "overall_grade": "moderate",
                        "overall_score": 0.67,
                        "study_count": 1,
                        "bias_risk_distribution": {"low": 1},
                        "summary": ["纳入 1 项研究进行 GRADE 评估"],
                    },
                    "data_mining_result": {
                        "methods_executed": ["association_rules", "clustering"],
                        "association_rules": {
                            "rules": [
                                {
                                    "antecedent": ["桂枝"],
                                    "consequent": ["白芍"],
                                    "support": 0.62,
                                    "confidence": 0.81,
                                    "lift": 1.18,
                                }
                            ]
                        },
                        "clustering": {
                            "cluster_summary": [
                                {
                                    "cluster": 0,
                                    "size": 2,
                                    "top_items": [
                                        {"item": "桂枝", "count": 2},
                                        {"item": "白芍", "count": 2},
                                    ],
                                }
                            ]
                        },
                    },
                    "research_perspectives": {
                        "桂枝汤": {
                            "integrated": {
                                "similar_formula_matches": [
                                    {
                                        "formula_name": "桂麻各半汤",
                                        "similarity_score": 0.87,
                                        "retrieval_sources": ["embedding", "relationship_reasoning"],
                                        "graph_evidence": {
                                            "source": "neo4j+relationship_reasoning",
                                            "evidence_score": 0.91,
                                            "shared_herbs": [{"herb": "桂枝"}, {"herb": "白芍"}],
                                            "shared_syndromes": ["营卫不和"],
                                            "shared_herb_count": 2,
                                        },
                                    }
                                ]
                            }
                        }
                    },
                },
                "metadata": {"analysis_type": "integrated_analysis"},
            }
        }

        result = self.pipeline.execute_research_phase(cycle.cycle_id, ResearchPhase.PUBLISH, {})

        self.assertIn("paper_draft", result)
        self.assertTrue(result["paper_draft"].get("sections"))
        self.assertIn("output_files", result)
        self.assertIn("markdown", result["output_files"])
        self.assertTrue(os.path.exists(result["output_files"]["markdown"]))
        markdown_text = open(result["output_files"]["markdown"], "r", encoding="utf-8").read()
        self.assertIn("统计分析提示当前结果具有稳定信号", markdown_text)
        self.assertIn("综合解释认为：桂枝汤核心配伍与营卫调和证据之间存在稳定关联", markdown_text)
        self.assertIn("GRADE 证据分级显示", markdown_text)
        self.assertIn("整体证据等级为中等", markdown_text)
        self.assertIn("类方图谱证据", markdown_text)
        self.assertIn("桂枝汤 与 桂麻各半汤", markdown_text)
        self.assertEqual(result["analysis_results"]["evidence_grade_summary"]["overall_grade"], "moderate")
        self.assertEqual(result["research_artifact"]["evidence_grade_summary"]["overall_grade"], "moderate")
        self.assertIn("Markdown 论文初稿", result["deliverables"])
        self.assertIn("imrd_reports", result)
        self.assertIn("report_output_files", result)
        self.assertIn("imrd_markdown", result["report_output_files"])
        self.assertTrue(os.path.exists(result["report_output_files"]["imrd_markdown"]))
        imrd_markdown_text = open(result["report_output_files"]["imrd_markdown"], "r", encoding="utf-8").read()
        self.assertIn("## Introduction", imrd_markdown_text)
        self.assertIn("## Methods", imrd_markdown_text)
        self.assertIn("## Results", imrd_markdown_text)
        self.assertIn("## Discussion", imrd_markdown_text)
        self.assertIn("Markdown IMRD 报告", result["deliverables"])
        if DOCX_AVAILABLE:
            self.assertIn("docx", result["output_files"])
            self.assertTrue(os.path.exists(result["output_files"]["docx"]))
            self.assertIn("DOCX 论文初稿", result["deliverables"])
            self.assertIn("imrd_docx", result["report_output_files"])
            self.assertTrue(os.path.exists(result["report_output_files"]["imrd_docx"]))
            self.assertIn("DOCX IMRD 报告", result["deliverables"])


if __name__ == "__main__":
    unittest.main()