import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.generation.report_generator import ReportFormat, ReportGenerator


def _build_session_result():
    return {
        "session_id": "session_report_001",
        "question": "小柴胡汤的方剂配伍规律研究",
        "metadata": {
            "title": "小柴胡汤配伍规律与证据链分析报告",
            "research_field": "中医方剂学",
        },
        "phase_results": {
            "observe": {
                "observations": [
                    "小柴胡汤核心药物集中于和解少阳相关配伍单元",
                    "柴胡与黄芩在人群研究与古籍记载中均表现出高频共现",
                    "现代文献更关注疗效结局而较少系统描述配伍层级结构",
                ],
                "findings": [
                    "方剂配伍表现出主药-辅药-调和药的层次特征",
                    "古籍描述与现代临床应用之间存在术语映射需求",
                ],
                "literature_pipeline": {
                    "records": [
                        {
                            "source": "pubmed",
                            "title": "Randomized controlled trial of Xiao Chai Hu Tang in functional dyspepsia",
                            "abstract": "研究提示小柴胡汤可改善功能性消化不良症状，并对胃肠动力指标有积极影响。",
                        },
                        {
                            "source": "cnki",
                            "title": "小柴胡汤临床应用与配伍规律综述",
                            "abstract": "综述指出柴胡、黄芩、半夏、生姜等药物具有稳定核心结构。",
                        },
                    ],
                    "summaries": [
                        "现有研究认为小柴胡汤兼具和解少阳、调畅气机与兼顾脾胃的特点",
                        "部分临床综述指出该方在消化系统、感染后综合征等场景中具有广泛应用",
                    ],
                    "evidence_matrix": [
                        {
                            "intervention": "小柴胡汤",
                            "outcome": "症状缓解",
                            "evidence_level": "moderate",
                        },
                        {
                            "intervention": "柴胡-黄芩配伍",
                            "outcome": "和解少阳相关机制",
                            "evidence_level": "emerging",
                        },
                    ],
                },
                "ingestion_pipeline": {
                    "entities": [
                        {"name": "小柴胡汤", "type": "formula"},
                        {"name": "柴胡", "type": "herb"},
                        {"name": "黄芩", "type": "herb"},
                        {"name": "半夏", "type": "herb"},
                        {"name": "少阳证", "type": "syndrome"},
                    ],
                    "semantic_graph": {
                        "nodes": ["小柴胡汤", "柴胡", "黄芩", "半夏", "少阳证"],
                        "edges": [
                            ["小柴胡汤", "柴胡"],
                            ["小柴胡汤", "黄芩"],
                            ["小柴胡汤", "半夏"],
                            ["小柴胡汤", "少阳证"],
                        ],
                    },
                },
            },
            "experiment": {
                "study_protocol": {
                    "study_type": "systematic_review",
                    "pico": {
                        "population": "功能性消化不良及少阳证相关患者",
                        "intervention": "小柴胡汤或其加减方",
                        "comparison": "常规治疗或安慰剂",
                        "outcome": "症状改善、复发率与安全性",
                    },
                    "sample_size": {
                        "estimated_n": 240,
                        "method": "基于系统综述纳入研究规模估算",
                    },
                    "eligibility": {
                        "inclusion": ["RCT", "明确诊断标准", "报告主要结局"],
                        "exclusion": ["重复发表", "无全文", "数据不完整"],
                    },
                },
            },
            "analyze": {
                "analysis_methods": [
                    "文本预处理与术语标准化",
                    "实体抽取与关系归并",
                    "知识图谱统计与结构分析",
                    "基于证据线索的规则推理",
                ],
                "comparison_with_literature": [
                    "当前结果更强调配伍层级结构，而非仅报告临床有效率",
                    "图谱结果补充了方剂-证候-药物之间的中介关系表达",
                ],
                "limitations": [
                    "当前文献样本量有限，尚未覆盖全部古籍与现代试验",
                    "自动抽取结果仍需专家复核以减少概念映射偏差",
                ],
                "reasoning_results": [
                    {
                        "title": "核心配伍规律",
                        "description": "柴胡与黄芩构成和解少阳的核心药对，半夏与生姜承担和胃降逆作用。",
                    },
                    {
                        "title": "结构性解释",
                        "description": "方剂内部分工呈现主轴药对加调和药的分层结构，与现代网络药理结果具有可比性。",
                    },
                ],
            },
            "reflect": {
                "future_directions": [
                    "扩展至更多病种和剂量分层的证据综合",
                    "引入机制实验与高质量 RCT 验证配伍推断",
                ],
                "recommendations": [
                    "构建可重复更新的小柴胡汤证据库",
                ],
            },
        },
    }


class TestReportGenerator(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.generator = ReportGenerator({"output_dir": self.tmpdir.name})
        self.session_result = _build_session_result()

    def test_generate_markdown_report_has_imrd_sections_and_min_length(self):
        report = self.generator.generate_report(self.session_result, "markdown")

        self.assertEqual(report.format, ReportFormat.MARKDOWN.value)
        self.assertGreaterEqual(len(report.content), 500)
        self.assertIn("## Introduction", report.content)
        self.assertIn("## Methods", report.content)
        self.assertIn("## Results", report.content)
        self.assertIn("## Discussion", report.content)
        self.assertIn("小柴胡汤的方剂配伍规律研究", report.content)

    def test_markdown_report_includes_entities_and_reasoning(self):
        report = self.generator.generate_report(self.session_result, ReportFormat.MARKDOWN)

        self.assertIn("柴胡", report.content)
        self.assertIn("黄芩", report.content)
        self.assertIn("核心配伍规律", report.content)
        self.assertEqual(set(report.sections.keys()), {"introduction", "methods", "results", "discussion"})

    def test_generate_docx_report_writes_output_file(self):
        report = self.generator.generate_report(self.session_result, "docx")

        self.assertEqual(report.format, ReportFormat.DOCX.value)
        self.assertTrue(report.output_path.endswith(".docx"))
        output_path = Path(report.output_path)
        self.assertTrue(output_path.exists())
        self.assertGreater(output_path.stat().st_size, 0)

    def test_execute_returns_report_payload(self):
        self.assertTrue(self.generator.initialize())
        result = self.generator.execute({"session_result": self.session_result, "format": "markdown"})

        self.assertIn("report", result)
        self.assertEqual(result["report"]["format"], "markdown")
        self.assertGreaterEqual(result["report"]["metadata"]["char_count"], 500)
        self.assertTrue(self.generator.cleanup())

    def test_invalid_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.generator.generate_report(self.session_result, "pdf")


if __name__ == "__main__":
    unittest.main()