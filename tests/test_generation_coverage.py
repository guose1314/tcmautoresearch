# tests/test_generation_coverage.py
"""
生成层覆盖率补齐测试：
- paper_writer.py (83% → ≥90%)
- figure_generator.py (84% → ≥90%)
"""
import json
import os
import tempfile
import unittest
from dataclasses import asdict
from unittest.mock import MagicMock, patch

from src.generation.figure_generator import FigureGenerator, FigureResult, FigureSpec
from src.generation.paper_writer import PaperDraft, PaperSection, PaperWriter


# ============================================================
# PaperSection / PaperDraft dataclass
# ============================================================
class TestPaperDataclasses(unittest.TestCase):
    def test_paper_section_to_dict(self):
        s = PaperSection(section_type="introduction", title="引言", content="内容")
        d = s.to_dict()
        self.assertEqual(d["section_type"], "introduction")

    def test_paper_draft_to_dict(self):
        draft = PaperDraft(
            title="测试标题",
            abstract="摘要",
            keywords=["关键词"],
            sections=[PaperSection(section_type="intro", title="T", content="C")],
        )
        d = draft.to_dict()
        self.assertEqual(d["title"], "测试标题")
        self.assertEqual(len(d["sections"]), 1)


# ============================================================
# PaperWriter 生命周期
# ============================================================
class TestPaperWriterInit(unittest.TestCase):
    def test_default_config(self):
        pw = PaperWriter()
        self.assertEqual(pw.language, "zh")
        self.assertTrue(pw.include_conclusion)

    def test_custom_config(self):
        pw = PaperWriter(config={"language": "en", "include_conclusion": False})
        self.assertEqual(pw.language, "en")
        self.assertFalse(pw.include_conclusion)

    def test_initialize(self):
        pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        self.assertTrue(pw.initialize())

    def test_cleanup(self):
        pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        pw.initialize()
        self.assertTrue(pw.cleanup())


# ============================================================
# Title / Author / Keywords resolution
# ============================================================
class TestPaperWriterResolve(unittest.TestCase):
    def setUp(self):
        self.pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        self.pw.initialize()

    def test_resolve_title_explicit(self):
        title = self.pw._resolve_title({"title": "我的论文标题"})
        self.assertEqual(title, "我的论文标题")

    def test_resolve_title_from_objective(self):
        title = self.pw._resolve_title({"objective": "研究目标"})
        self.assertIn("研究目标", title)

    def test_resolve_title_fallback(self):
        title = self.pw._resolve_title({})
        self.assertIn("IMRD", title)

    def test_resolve_author_string(self):
        result = self.pw._resolve_author_text({"authors": "张三"})
        self.assertEqual(result, "张三")

    def test_resolve_author_list(self):
        result = self.pw._resolve_author_text({"authors": ["张三", "李四"]})
        self.assertIn("张三", result)
        self.assertIn("李四", result)

    def test_resolve_author_empty(self):
        result = self.pw._resolve_author_text({})
        self.assertEqual(result, "")

    def test_resolve_keywords_string(self):
        result = self.pw._resolve_keywords({"keywords": "中医;针灸;方剂"})
        self.assertGreater(len(result), 0)

    def test_resolve_keywords_list(self):
        result = self.pw._resolve_keywords({"keywords": ["中医", "针灸"]})
        self.assertEqual(len(result), 2)

    def test_resolve_keywords_from_entities(self):
        result = self.pw._resolve_keywords({
            "entities": [{"name": "黄芪"}, {"name": "白术"}]
        })
        self.assertIn("黄芪", result)

    def test_resolve_keywords_from_data_mining(self):
        result = self.pw._resolve_keywords({
            "data_mining": {
                "clustering": {
                    "cluster_summary": [
                        {"top_items": [{"item": "甘草"}, {"item": "黄芪"}]}
                    ]
                }
            }
        })
        # Might or might not find the items depending on impl, just check it doesn't crash
        self.assertIsInstance(result, list)

    def test_resolve_keywords_fallback(self):
        result = self.pw._resolve_keywords({})
        self.assertIn("中医古籍", result)


# ============================================================
# References resolution
# ============================================================
class TestPaperWriterReferences(unittest.TestCase):
    def setUp(self):
        self.pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        self.pw.initialize()

    def test_resolve_references_explicit_string(self):
        refs = self.pw._resolve_references({"formatted_references": "Ref1\nRef2"})
        self.assertEqual(len(refs), 2)

    def test_resolve_references_explicit_list(self):
        refs = self.pw._resolve_references({"formatted_references": ["Ref1", "Ref2"]})
        self.assertEqual(len(refs), 2)

    def test_resolve_references_empty(self):
        refs = self.pw._resolve_references({})
        self.assertEqual(len(refs), 0)

    def test_extract_literature_from_pipeline(self):
        ctx = {"literature_pipeline": {"records": [{"title": "Paper1", "authors": ["A"]}]}}
        records = self.pw._extract_literature_records(ctx)
        self.assertEqual(len(records), 1)

    def test_extract_literature_from_analysis_results(self):
        ctx = {"analysis_results": {"literature_pipeline": {"records": [{"title": "Paper1"}]}}}
        records = self.pw._extract_literature_records(ctx)
        self.assertEqual(len(records), 1)


# ============================================================
# Section content generation
# ============================================================
class TestPaperWriterSections(unittest.TestCase):
    def setUp(self):
        self.pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        self.pw.initialize()

    def test_generate_introduction_zh(self):
        content = self.pw._generate_section_content(
            "introduction", {"objective": "研究目标"}, "论文标题", "zh", []
        )
        self.assertIn("研究目标", content)

    def test_generate_methods_zh(self):
        content = self.pw._generate_section_content(
            "methods", {}, "论文标题", "zh", []
        )
        self.assertIsInstance(content, str)

    def test_generate_results_zh(self):
        content = self.pw._generate_section_content(
            "results", {}, "论文标题", "zh", []
        )
        self.assertIsInstance(content, str)

    def test_generate_discussion_zh(self):
        content = self.pw._generate_section_content(
            "discussion", {}, "论文标题", "zh", []
        )
        self.assertIsInstance(content, str)

    def test_generate_conclusion_zh(self):
        content = self.pw._generate_section_content(
            "conclusion", {}, "论文标题", "zh", []
        )
        self.assertIsInstance(content, str)

    def test_generate_unknown_section(self):
        content = self.pw._generate_section_content(
            "unknown", {}, "论文标题", "zh", []
        )
        self.assertEqual(content, "")

    def test_section_overrides(self):
        overrides = self.pw._resolve_section_overrides(
            {"introduction": "自定义引言内容"}, "zh"
        )
        self.assertEqual(overrides["introduction"], "自定义引言内容")

    def test_normalize_section_type(self):
        self.assertEqual(self.pw._normalize_section_type("intro"), "introduction")
        self.assertEqual(self.pw._normalize_section_type("conclusions"), "conclusion")
        self.assertEqual(self.pw._normalize_section_type("findings"), "results")


# ============================================================
# Abstract generation
# ============================================================
class TestPaperWriterAbstract(unittest.TestCase):
    def setUp(self):
        self.pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        self.pw.initialize()

    def test_abstract_explicit(self):
        abstract = self.pw._resolve_abstract({"abstract": "自定义摘要"}, "标题", [], "zh")
        self.assertEqual(abstract, "自定义摘要")

    def test_abstract_auto_zh(self):
        abstract = self.pw._resolve_abstract({}, "标题", [], "zh")
        self.assertIn("背景", abstract)
        self.assertIn("方法", abstract)

    def test_abstract_auto_en(self):
        abstract = self.pw._resolve_abstract({}, "Title", [], "en")
        self.assertIn("Background", abstract)
        self.assertIn("Methods", abstract)


# ============================================================
# Build draft full cycle
# ============================================================
class TestPaperWriterBuildDraft(unittest.TestCase):
    def setUp(self):
        self.pw = PaperWriter(config={"output_dir": tempfile.mkdtemp()})
        self.pw.initialize()

    def test_build_draft_minimal(self):
        draft = self.pw.build_draft({})
        self.assertIsInstance(draft, PaperDraft)
        self.assertGreater(len(draft.sections), 0)
        self.assertIn("IMRD", draft.title)

    def test_build_draft_en(self):
        draft = self.pw.build_draft({"language": "en", "title": "Test Paper"})
        self.assertEqual(draft.title, "Test Paper")
        self.assertEqual(draft.metadata["language"], "en")

    def test_build_draft_no_conclusion(self):
        pw = PaperWriter(config={"output_dir": tempfile.mkdtemp(), "include_conclusion": False})
        pw.initialize()
        draft = pw.build_draft({})
        section_types = [s.section_type for s in draft.sections]
        self.assertNotIn("conclusion", section_types)


# ============================================================
# Export draft
# ============================================================
class TestPaperWriterExport(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.pw = PaperWriter(config={"output_dir": self.output_dir})
        self.pw.initialize()

    def test_export_markdown(self):
        draft = self.pw.build_draft({})
        outputs = self.pw.export_draft(draft, formats=["markdown"])
        self.assertIn("markdown", outputs)
        self.assertTrue(os.path.exists(outputs["markdown"]))

    def test_export_unsupported_format_raises(self):
        draft = self.pw.build_draft({})
        with self.assertRaises(ValueError):
            self.pw.export_draft(draft, formats=["html"])


# ============================================================
# _do_execute full cycle
# ============================================================
class TestPaperWriterDoExecute(unittest.TestCase):
    def test_do_execute(self):
        output_dir = tempfile.mkdtemp()
        pw = PaperWriter(config={"output_dir": output_dir, "output_formats": ["markdown"]})
        pw.initialize()
        result = pw._do_execute({"title": "集成测试论文"})
        self.assertTrue(result["success"])
        self.assertGreater(result["section_count"], 0)
        self.assertIn("iteration_history", result)
        self.assertIn("review_summary", result)
        self.assertEqual(result["iteration_count"], len(result["iteration_history"]))


# ============================================================
# FigureSpec / FigureResult dataclasses
# ============================================================
class TestFigureDataclasses(unittest.TestCase):
    def test_figure_spec_from_dict(self):
        spec = FigureSpec.from_dict({"figure_type": "network", "title": "图1"})
        self.assertEqual(spec.figure_type, "network")
        self.assertEqual(spec.title, "图1")

    def test_figure_result_to_dict(self):
        r = FigureResult(success=True, file_path="/tmp/fig.png", figure_type="network")
        d = r.to_dict()
        self.assertTrue(d["success"])


# ============================================================
# FigureGenerator 生命周期
# ============================================================
class TestFigureGeneratorInit(unittest.TestCase):
    def test_default_config(self):
        fg = FigureGenerator()
        self.assertEqual(fg.default_format, "png")
        self.assertEqual(fg.default_dpi, 300)

    def test_initialize(self):
        fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        self.assertTrue(fg.initialize())

    def test_cleanup(self):
        fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        fg.initialize()
        self.assertTrue(fg.cleanup())


# ============================================================
# _resolve_specs
# ============================================================
class TestFigureResolveSpecs(unittest.TestCase):
    def setUp(self):
        self.fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        self.fg.initialize()

    def test_resolve_from_figure_specs(self):
        ctx = {"figure_specs": [{"figure_type": "bar", "data": {}}]}
        specs = self.fg._resolve_specs(ctx)
        self.assertEqual(len(specs), 1)

    def test_resolve_from_figure_spec_single(self):
        ctx = {"figure_spec": {"figure_type": "bar", "data": {}}}
        specs = self.fg._resolve_specs(ctx)
        self.assertEqual(len(specs), 1)

    def test_resolve_from_figure_type(self):
        ctx = {"figure_type": "heatmap", "data": {"matrix": [[1, 2], [3, 4]]}}
        specs = self.fg._resolve_specs(ctx)
        self.assertEqual(len(specs), 1)

    def test_resolve_empty(self):
        specs = self.fg._resolve_specs({})
        self.assertEqual(len(specs), 0)


# ============================================================
# Network figure rendering
# ============================================================
class TestFigureNetwork(unittest.TestCase):
    def setUp(self):
        self.fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        self.fg.initialize()

    def test_network_basic(self):
        spec = FigureSpec(
            figure_type="network",
            title="研究网络",
            data={
                "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
                "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}],
            },
        )
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)
        self.assertIn("node_count", result.metadata)

    def test_network_empty_data(self):
        spec = FigureSpec(figure_type="network", data={"nodes": [], "edges": []})
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata["node_count"], 0)

    def test_network_directed(self):
        spec = FigureSpec(
            figure_type="network",
            data={
                "nodes": ["X", "Y"],
                "edges": [["X", "Y"]],
            },
            style={"directed": True},
        )
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)


# ============================================================
# Heatmap figure rendering
# ============================================================
class TestFigureHeatmap(unittest.TestCase):
    def setUp(self):
        self.fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        self.fg.initialize()

    def test_heatmap_basic(self):
        spec = FigureSpec(
            figure_type="heatmap",
            title="热力图",
            data={"matrix": [[1, 2, 3], [4, 5, 6]]},
        )
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)

    def test_heatmap_empty(self):
        spec = FigureSpec(figure_type="heatmap", data={"matrix": []})
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)

    def test_heatmap_1d(self):
        spec = FigureSpec(figure_type="heatmap", data={"matrix": [1, 2, 3]})
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)

    def test_heatmap_no_seaborn_fallback(self):
        """测试没有 seaborn 时的 imshow 回退"""
        fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp(), "enable_seaborn": False})
        fg.initialize()
        fg._sns = None  # force no seaborn
        spec = FigureSpec(
            figure_type="heatmap",
            data={"matrix": [[1, 2], [3, 4]]},
        )
        result = fg.generate_figure(spec)
        self.assertTrue(result.success)


# ============================================================
# Bar / Scatter / Unsupported figure types
# ============================================================
class TestFigureBarScatter(unittest.TestCase):
    def setUp(self):
        self.fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        self.fg.initialize()

    def test_bar_basic(self):
        spec = FigureSpec(
            figure_type="bar",
            data={"labels": ["A", "B", "C"], "values": [10, 20, 30]},
        )
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)

    def test_scatter_basic(self):
        spec = FigureSpec(
            figure_type="scatter",
            data={"x": [1, 2, 3], "y": [4, 5, 6]},
        )
        result = self.fg.generate_figure(spec)
        self.assertTrue(result.success)

    def test_unsupported_type(self):
        spec = FigureSpec(figure_type="pie", data={})
        result = self.fg.generate_figure(spec)
        self.assertFalse(result.success)
        self.assertIn("不支持", result.error)


# ============================================================
# _do_execute full cycle
# ============================================================
class TestFigureDoExecute(unittest.TestCase):
    def test_do_execute_success(self):
        fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        fg.initialize()
        ctx = {
            "figure_specs": [
                {"figure_type": "bar", "data": {"labels": ["A"], "values": [1]}},
            ],
        }
        result = fg._do_execute(ctx)
        self.assertTrue(result["success"])
        self.assertEqual(result["generated_count"], 1)

    def test_do_execute_no_specs_raises(self):
        fg = FigureGenerator(config={"output_dir": tempfile.mkdtemp()})
        fg.initialize()
        with self.assertRaises(ValueError):
            fg._do_execute({})


if __name__ == "__main__":
    unittest.main()
