"""Tests for src/research/exegesis_contract.py — 训诂字段合同。"""

from __future__ import annotations

import unittest


class TestFieldConstants(unittest.TestCase):
    def test_exegesis_fields_frozenset(self):
        from src.research.exegesis_contract import EXEGESIS_FIELDS

        self.assertIsInstance(EXEGESIS_FIELDS, frozenset)
        self.assertIn("definition", EXEGESIS_FIELDS)
        self.assertIn("definition_source", EXEGESIS_FIELDS)
        self.assertIn("semantic_scope", EXEGESIS_FIELDS)
        self.assertIn("dynasty_usage", EXEGESIS_FIELDS)
        self.assertIn("disambiguation_basis", EXEGESIS_FIELDS)

    def test_label_to_category_mapping(self):
        from src.research.exegesis_contract import LABEL_TO_CATEGORY

        self.assertEqual(LABEL_TO_CATEGORY["本草药名"], "herb")
        self.assertEqual(LABEL_TO_CATEGORY["证候术语"], "syndrome")
        self.assertEqual(LABEL_TO_CATEGORY["理论术语"], "theory")

    def test_category_to_label_reverse(self):
        from src.research.exegesis_contract import CATEGORY_TO_LABEL

        self.assertEqual(CATEGORY_TO_LABEL["herb"], "本草药名")
        self.assertEqual(CATEGORY_TO_LABEL["syndrome"], "证候术语")


class TestDefinitionSourceRank(unittest.TestCase):
    def test_known_ranks(self):
        from src.research.exegesis_contract import definition_source_rank

        self.assertEqual(definition_source_rank("config_terminology_standard"), 4)
        self.assertEqual(definition_source_rank("structured_tcm_knowledge"), 3)
        self.assertEqual(definition_source_rank("terminology_note"), 2)
        self.assertEqual(definition_source_rank("canonical_fallback"), 1)

    def test_unknown_returns_zero(self):
        from src.research.exegesis_contract import definition_source_rank

        self.assertEqual(definition_source_rank(""), 0)
        self.assertEqual(definition_source_rank(None), 0)
        self.assertEqual(definition_source_rank("unknown_source"), 0)


class TestResolvePolysemyCategory(unittest.TestCase):
    def test_from_row_category(self):
        from src.research.exegesis_contract import resolve_polysemy_category

        row = {"category": "herb"}
        self.assertEqual(resolve_polysemy_category(row, ""), "herb")

    def test_from_label_fallback(self):
        from src.research.exegesis_contract import resolve_polysemy_category

        row = {"category": ""}
        self.assertEqual(resolve_polysemy_category(row, "证候术语"), "syndrome")

    def test_empty_when_unknown(self):
        from src.research.exegesis_contract import resolve_polysemy_category

        row = {}
        self.assertEqual(resolve_polysemy_category(row, "unknown_label"), "")


class TestDisambiguatePolysemy(unittest.TestCase):
    def test_empty_dictionaries_returns_empty(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        result = disambiguate_polysemy("黄芪", "herb", dictionaries=[])
        self.assertEqual(result, {})

    def test_dictionary_hit(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class FakeDict:
            def lookup(self, canonical, *, category=""):
                if canonical == "黄芪":
                    return {"definition": "补气固表", "definition_source": "test_dict"}
                return {}

        result = disambiguate_polysemy("黄芪", "herb", dictionaries=[FakeDict()])
        self.assertEqual(result["definition"], "补气固表")

    def test_dictionary_miss_returns_empty(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class EmptyDict:
            def lookup(self, canonical, *, category=""):
                return {}

        result = disambiguate_polysemy("不存在", "herb", dictionaries=[EmptyDict()])
        self.assertEqual(result, {})

    def test_first_matching_dictionary_wins(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class Dict1:
            def lookup(self, canonical, *, category=""):
                return {"definition": "dict1_def", "definition_source": "dict1"}

        class Dict2:
            def lookup(self, canonical, *, category=""):
                return {"definition": "dict2_def", "definition_source": "dict2"}

        result = disambiguate_polysemy("term", "herb", dictionaries=[Dict1(), Dict2()])
        self.assertEqual(result["definition_source"], "dict1")


class TestAssessExegesisCompleteness(unittest.TestCase):
    def test_empty_rows(self):
        from src.research.exegesis_contract import assess_exegesis_completeness

        result = assess_exegesis_completeness([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["with_definition"], 0)
        self.assertEqual(result["definition_coverage"], 0.0)

    def test_full_coverage(self):
        from src.research.exegesis_contract import assess_exegesis_completeness

        rows = [
            {"definition": "补气固表", "definition_source": "structured_tcm_knowledge", "category": "herb", "disambiguation_basis": ["src1"]},
            {"definition": "血虚之证", "definition_source": "config_terminology_standard", "category": "syndrome", "disambiguation_basis": ["src2"]},
        ]
        result = assess_exegesis_completeness(rows)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["with_definition"], 2)
        self.assertEqual(result["definition_coverage"], 1.0)
        self.assertEqual(result["disambiguation_count"], 2)
        self.assertEqual(result["needs_disambiguation"], 0)

    def test_partial_coverage(self):
        from src.research.exegesis_contract import assess_exegesis_completeness

        rows = [
            {"definition": "补气", "definition_source": "structured_tcm_knowledge", "category": "herb"},
            {"definition": "", "category": "syndrome"},
        ]
        result = assess_exegesis_completeness(rows)
        self.assertEqual(result["with_definition"], 1)
        self.assertEqual(result["definition_coverage"], 0.5)
        self.assertEqual(result["needs_disambiguation"], 1)


class TestBuildExegesisSummary(unittest.TestCase):
    def test_includes_dynasty_counts(self):
        from src.research.exegesis_contract import build_exegesis_summary

        rows = [
            {"definition": "test", "definition_source": "note", "category": "herb", "dynasty_usage": ["唐", "宋"]},
            {"definition": "test2", "definition_source": "note", "category": "herb", "dynasty_usage": ["唐"]},
        ]
        result = build_exegesis_summary(rows)
        self.assertEqual(result["dynasty_term_counts"]["唐"], 2)
        self.assertEqual(result["dynasty_term_counts"]["宋"], 1)

    def test_empty_rows(self):
        from src.research.exegesis_contract import build_exegesis_summary

        result = build_exegesis_summary([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["dynasty_term_counts"], {})


class TestBuildExegesisNote(unittest.TestCase):
    def test_structured_source_note(self):
        from src.research.exegesis_contract import build_exegesis_note

        note = build_exegesis_note("黄芪", "structured_tcm_knowledge", "herb", ["HERB_EFFICACY_MAP"])
        self.assertIn("黄芪", note)
        self.assertIn("结构化知识库", note)
        self.assertIn("药名", note)
        self.assertIn("HERB_EFFICACY_MAP", note)

    def test_fallback_source_note(self):
        from src.research.exegesis_contract import build_exegesis_note

        note = build_exegesis_note("未知术语", "canonical_fallback")
        self.assertIn("机器归并", note)
        self.assertNotIn("义项判别", note)

    def test_config_source_note(self):
        from src.research.exegesis_contract import build_exegesis_note

        note = build_exegesis_note("术语A", "config_terminology_standard", "theory")
        self.assertIn("配置标准", note)
        self.assertIn("理论术语", note)


class TestExegesisDictionaryProtocol(unittest.TestCase):
    def test_protocol_recognizes_compliant_class(self):
        from src.research.exegesis_contract import ExegesisDictionary

        class MyDict:
            def lookup(self, canonical, *, category=""):
                return {}

        self.assertIsInstance(MyDict(), ExegesisDictionary)

    def test_protocol_rejects_non_compliant(self):
        from src.research.exegesis_contract import ExegesisDictionary

        class NotADict:
            pass

        self.assertNotIsInstance(NotADict(), ExegesisDictionary)


class TestPolysemyDisambiguationCategories(unittest.TestCase):
    def test_herb_syndrome_theory_included(self):
        from src.research.exegesis_contract import POLYSEMY_DISAMBIGUATION_CATEGORIES

        self.assertIn("herb", POLYSEMY_DISAMBIGUATION_CATEGORIES)
        self.assertIn("syndrome", POLYSEMY_DISAMBIGUATION_CATEGORIES)
        self.assertIn("theory", POLYSEMY_DISAMBIGUATION_CATEGORIES)

    def test_formula_not_in_disambiguation(self):
        from src.research.exegesis_contract import POLYSEMY_DISAMBIGUATION_CATEGORIES

        self.assertNotIn("formula", POLYSEMY_DISAMBIGUATION_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
