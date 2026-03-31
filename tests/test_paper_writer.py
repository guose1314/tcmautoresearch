import importlib
import os
import tempfile
import unittest

from src.generation import PaperWriter

DOCX_AVAILABLE = True
try:
    importlib.import_module("docx")
except ImportError:
    DOCX_AVAILABLE = False


class TestPaperWriter(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.writer = PaperWriter({"output_dir": self.tempdir.name, "output_formats": ["markdown", "docx"]})
        self.assertTrue(self.writer.initialize())

    def tearDown(self):
        self.writer.cleanup()
        self.tempdir.cleanup()

    def test_generate_imrd_markdown_and_docx(self):
        context = {
            "title": "中医古籍证据整合研究",
            "author": "张三",
            "affiliation": "某某大学中医学院",
            "objective": "构建古籍证据到现代科研叙事的统一写作流程",
            "keywords": ["中医古籍", "IMRD", "证据整合"],
            "entities": [{"name": "黄芪"}, {"name": "党参"}, {"name": "白术"}],
            "reasoning_results": {
                "evidence_records": [
                    {"evidence_id": "ev-1", "source_entity": "黄芪", "target_entity": "气虚"},
                    {"evidence_id": "ev-2", "source_entity": "党参", "target_entity": "脾虚"},
                ]
            },
            "data_mining_result": {
                "methods_executed": ["association_rules", "clustering"],
                "association_rules": {
                    "rules": [
                        {
                            "antecedent": ["黄芪"],
                            "consequent": ["党参"],
                            "support": 0.66,
                            "confidence": 0.8,
                            "lift": 1.2,
                        }
                    ]
                },
                "clustering": {
                    "cluster_summary": [
                        {
                            "cluster": 0,
                            "size": 3,
                            "top_items": [
                                {"item": "黄芪", "count": 3},
                                {"item": "党参", "count": 2},
                            ],
                        }
                    ]
                },
            },
            "citation_records": [
                {
                    "title": "TCM Evidence Integration",
                    "authors": ["Alice Smith", "Bob Chen"],
                    "year": 2024,
                    "journal": "Journal of TCM Informatics",
                    "doi": "10.1000/tcm.2024.1",
                }
            ],
            "figure_paths": [os.path.join(self.tempdir.name, "figure1.png")],
        }

        result = self.writer.execute(context)

        self.assertTrue(result["success"])
        self.assertEqual(result["section_count"], 5)
        self.assertIn("markdown", result["output_files"])
        self.assertTrue(os.path.exists(result["output_files"]["markdown"]))
        markdown_text = open(result["output_files"]["markdown"], "r", encoding="utf-8").read()
        self.assertIn("## 1 引言（Introduction）", markdown_text)
        self.assertIn("## 5 结论（Conclusion）", markdown_text)
        self.assertIn("参考文献", markdown_text)
        self.assertIn("TCM Evidence Integration", markdown_text)

        if DOCX_AVAILABLE:
            self.assertIn("docx", result["output_files"])
            self.assertTrue(os.path.exists(result["output_files"]["docx"]))

    def test_section_overrides_are_preserved(self):
        result = self.writer.execute(
            {
                "title": "自定义章节测试",
                "output_format": "markdown",
                "sections": [
                    {"section_type": "methods", "content": "这是自定义方法部分。"},
                ],
            }
        )

        self.assertTrue(result["success"])
        sections = result["paper_draft"]["sections"]
        methods_section = next(section for section in sections if section["section_type"] == "methods")
        self.assertEqual(methods_section["content"], "这是自定义方法部分。")

    def test_markdown_only_export(self):
        result = self.writer.execute(
            {
                "title": "Markdown 导出测试",
                "output_format": "markdown",
                "author": "李四",
            }
        )

        self.assertTrue(result["success"])
        self.assertEqual(sorted(result["output_files"].keys()), ["markdown"])
        self.assertTrue(os.path.exists(result["output_files"]["markdown"]))

    def test_results_section_includes_similar_formula_graph_evidence_chapter(self):
        result = self.writer.execute(
            {
                "title": "类方图谱证据测试",
                "output_format": "markdown",
                "similar_formula_graph_evidence_summary": {
                    "formula_count": 1,
                    "match_count": 1,
                    "matches": [
                        {
                            "formula_name": "四君子汤",
                            "similar_formula_name": "六君子汤",
                            "similarity_score": 0.91,
                            "evidence_score": 0.92,
                            "shared_herbs": ["人参", "白术"],
                            "shared_syndromes": ["脾气虚证"],
                        }
                    ],
                },
            }
        )

        self.assertTrue(result["success"])
        markdown_text = open(result["output_files"]["markdown"], "r", encoding="utf-8").read()
        self.assertIn("类方图谱证据", markdown_text)
        self.assertIn("四君子汤 与 六君子汤", markdown_text)
        self.assertIn("共享药物包括 人参、白术", markdown_text)
        self.assertIn("共享证候包括 脾气虚证", markdown_text)

    def test_sections_include_analysis_results_and_research_artifact_details(self):
        result = self.writer.execute(
            {
                "title": "分析上下文增强测试",
                "output_format": "markdown",
                "analysis_results": {
                    "statistical_analysis": {
                        "statistical_significance": True,
                        "confidence_level": 0.95,
                        "effect_size": 0.72,
                        "p_value": 0.004,
                        "interpretation": "桂枝汤核心配伍与营卫调和证据之间存在稳定关联",
                        "limitations": ["样本规模有限", "仍需专家复核"],
                    },
                    "quality_metrics": {
                        "confidence_score": 0.92,
                        "completeness": 0.88,
                    },
                },
                "recommendations": ["建议增加更多样本以提高准确性"],
                "research_artifact": {
                    "hypothesis": [{"title": "桂枝汤调和营卫假设"}],
                    "evidence": [{"evidence_id": "ev-1", "source_entity": "桂枝汤", "target_entity": "营卫"}],
                    "data_mining_result": {
                        "association_rules": {"rules": [{"antecedent": ["桂枝"], "consequent": ["白芍"]}]},
                        "clustering": {
                            "cluster_summary": [
                                {"top_items": [{"item": "桂枝"}, {"item": "白芍"}]}
                            ]
                        },
                    },
                    "similar_formula_graph_evidence_summary": {
                        "matches": [
                            {
                                "formula_name": "桂枝汤",
                                "similar_formula_name": "桂麻各半汤",
                                "similarity_score": 0.87,
                                "evidence_score": 0.91,
                                "shared_herbs": ["桂枝", "白芍"],
                                "shared_syndromes": ["营卫不和"],
                            }
                        ]
                    },
                },
            }
        )

        self.assertTrue(result["success"])
        markdown_text = open(result["output_files"]["markdown"], "r", encoding="utf-8").read()
        self.assertIn("统计分析提示当前结果具有稳定信号", markdown_text)
        self.assertIn("综合解释认为：桂枝汤核心配伍与营卫调和证据之间存在稳定关联", markdown_text)
        self.assertIn("质量评估显示当前输出的置信分数 0.92、完整度 0.88", markdown_text)
        self.assertIn("后续建议优先关注：建议增加更多样本以提高准确性", markdown_text)
        self.assertIn("桂枝汤 与 桂麻各半汤", markdown_text)

    @unittest.skipUnless(DOCX_AVAILABLE, "python-docx 未安装")
    def test_docx_export_renders_similar_formula_graph_evidence_as_heading(self):
        result = self.writer.execute(
            {
                "title": "DOCX 类方图谱证据测试",
                "output_format": "docx",
                "similar_formula_graph_evidence_summary": {
                    "formula_count": 1,
                    "match_count": 1,
                    "matches": [
                        {
                            "formula_name": "四君子汤",
                            "similar_formula_name": "六君子汤",
                            "similarity_score": 0.91,
                            "evidence_score": 0.92,
                            "shared_herbs": ["人参", "白术"],
                            "shared_syndromes": ["脾气虚证"],
                        }
                    ],
                },
            }
        )

        document = importlib.import_module("docx").Document(result["output_files"]["docx"])
        matching = [paragraph for paragraph in document.paragraphs if paragraph.text.strip() == "类方图谱证据"]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].style.name, "Heading 2")


if __name__ == "__main__":
    unittest.main()