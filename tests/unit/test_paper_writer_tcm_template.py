"""Phase K / K-3 tests: PaperWriter TCM template adds 方义/证治/按语 sections."""

from __future__ import annotations

import unittest

from src.generation.paper_writer import (
    PAPER_TEMPLATE_DEFAULT,
    PAPER_TEMPLATE_TCM,
    SUPPORTED_PAPER_TEMPLATES,
    PaperWriter,
)


def _make_writer(**config):
    writer = PaperWriter(config or None)
    return writer


class TestTemplateConstants(unittest.TestCase):
    def test_supported_templates_include_imrd_and_tcm(self):
        self.assertIn(PAPER_TEMPLATE_DEFAULT, SUPPORTED_PAPER_TEMPLATES)
        self.assertIn(PAPER_TEMPLATE_TCM, SUPPORTED_PAPER_TEMPLATES)

    def test_default_template_is_imrd(self):
        self.assertEqual(PAPER_TEMPLATE_DEFAULT, "imrd")


class TestCoerceTemplate(unittest.TestCase):
    def test_unknown_falls_back_to_default(self):
        w = _make_writer()
        self.assertEqual(w._coerce_template("garbage"), PAPER_TEMPLATE_DEFAULT)

    def test_uppercase_normalized(self):
        w = _make_writer()
        self.assertEqual(w._coerce_template("TCM"), PAPER_TEMPLATE_TCM)


class TestBuildDraftDefaultTemplate(unittest.TestCase):
    def test_default_draft_excludes_tcm_sections(self):
        w = _make_writer()
        draft = w.build_draft({"title": "测试", "objective": "obj"})
        section_types = [s.section_type for s in draft.sections]
        for tcm in ("formula_interpretation", "pattern_analysis", "commentary"):
            self.assertNotIn(tcm, section_types)
        self.assertEqual(draft.metadata.get("template"), PAPER_TEMPLATE_DEFAULT)


class TestBuildDraftTCMTemplate(unittest.TestCase):
    def test_tcm_draft_includes_three_extra_sections(self):
        w = _make_writer()
        draft = w.build_draft({
            "title": "桂枝汤研究",
            "objective": "厘清桂枝汤方义",
            "template": "tcm",
            "formulas": [{"name": "桂枝汤"}],
            "herbs": [{"name": "桂枝"}, {"name": "白芍"}, {"name": "甘草"}],
            "syndromes": [{"name": "太阳中风"}],
        })
        section_types = [s.section_type for s in draft.sections]
        self.assertIn("formula_interpretation", section_types)
        self.assertIn("pattern_analysis", section_types)
        self.assertIn("commentary", section_types)
        self.assertEqual(draft.metadata.get("template"), PAPER_TEMPLATE_TCM)

    def test_formula_interpretation_mentions_formula(self):
        w = _make_writer()
        draft = w.build_draft({
            "title": "测试", "template": "tcm",
            "formulas": [{"name": "麻黄汤"}],
            "herbs": [{"name": "麻黄"}, {"name": "桂枝"}, {"name": "杏仁"}],
        })
        section = next(s for s in draft.sections if s.section_type == "formula_interpretation")
        self.assertIn("麻黄汤", section.content)
        self.assertIn("麻黄", section.content)

    def test_pattern_analysis_mentions_syndrome(self):
        w = _make_writer()
        draft = w.build_draft({
            "title": "测试", "template": "tcm",
            "syndromes": ["脾胃虚寒"],
        })
        section = next(s for s in draft.sections if s.section_type == "pattern_analysis")
        self.assertIn("脾胃虚寒", section.content)

    def test_commentary_uses_override_when_provided(self):
        w = _make_writer()
        draft = w.build_draft({
            "title": "测试", "template": "tcm",
            "commentary": "本研究按语：注重源流。",
        })
        section = next(s for s in draft.sections if s.section_type == "commentary")
        self.assertIn("注重源流", section.content)

    def test_tcm_template_section_count_extends_default(self):
        w = _make_writer()
        default_draft = w.build_draft({"title": "T1"})
        tcm_draft = w.build_draft({"title": "T2", "template": "tcm"})
        self.assertEqual(len(tcm_draft.sections), len(default_draft.sections) + 3)


class TestConfigDrivenTemplate(unittest.TestCase):
    def test_writer_constructed_with_template_config(self):
        w = _make_writer(template="tcm")
        self.assertEqual(w.template, PAPER_TEMPLATE_TCM)
        draft = w.build_draft({"title": "T"})
        types = [s.section_type for s in draft.sections]
        self.assertIn("commentary", types)


if __name__ == "__main__":
    unittest.main()
