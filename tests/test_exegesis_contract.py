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
            {
                "definition": "补气固表",
                "definition_source": "structured_tcm_knowledge",
                "category": "herb",
                "disambiguation_basis": ["src1"],
            },
            {
                "definition": "血虚之证",
                "definition_source": "config_terminology_standard",
                "category": "syndrome",
                "disambiguation_basis": ["src2"],
            },
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
            {
                "definition": "补气",
                "definition_source": "structured_tcm_knowledge",
                "category": "herb",
            },
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
            {
                "definition": "test",
                "definition_source": "note",
                "category": "herb",
                "dynasty_usage": ["唐", "宋"],
            },
            {
                "definition": "test2",
                "definition_source": "note",
                "category": "herb",
                "dynasty_usage": ["唐"],
            },
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

        note = build_exegesis_note(
            "黄芪", "structured_tcm_knowledge", "herb", ["HERB_EFFICACY_MAP"]
        )
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


class TestDisambiguatePolysemyScoring(unittest.TestCase):
    """Phase 2: 评分机制 — context_terms 与 definition_source 影响选择。"""

    def test_higher_rank_source_wins(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class LowRankDict:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "低优先级",
                    "definition_source": "canonical_fallback",
                }

        class HighRankDict:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "高优先级",
                    "definition_source": "config_terminology_standard",
                }

        result = disambiguate_polysemy(
            "黄芪",
            "herb",
            dictionaries=[LowRankDict(), HighRankDict()],
        )
        self.assertEqual(result["definition"], "高优先级")

    def test_context_terms_boost(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class DictA:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "补气固表",
                    "definition_source": "canonical_fallback",
                }

        class DictB:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "清热解毒利湿",
                    "definition_source": "canonical_fallback",
                }

        # 上下文含"清热"时 DictB 胜出
        result = disambiguate_polysemy(
            "黄芪",
            "herb",
            dictionaries=[DictA(), DictB()],
            context_terms=["清热", "解毒"],
        )
        self.assertEqual(result["definition"], "清热解毒利湿")

    def test_context_terms_populate_disambiguation_basis(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class FakeDict:
            def lookup(self, canonical, *, category=""):
                return {"definition": "含有补气的释义", "definition_source": "note"}

        result = disambiguate_polysemy(
            "x",
            "herb",
            dictionaries=[FakeDict()],
            context_terms=["补气"],
        )
        self.assertIn("disambiguation_basis", result)

    def test_category_match_bonus(self):
        from src.research.exegesis_contract import disambiguate_polysemy

        class DictNoCategory:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "无类别",
                    "definition_source": "canonical_fallback",
                }

        class DictWithCategory:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "有类别",
                    "definition_source": "canonical_fallback",
                    "category": "herb",
                }

        result = disambiguate_polysemy(
            "x",
            "herb",
            dictionaries=[DictNoCategory(), DictWithCategory()],
        )
        self.assertEqual(result["definition"], "有类别")


class TestExegesisContextWindow(unittest.TestCase):
    def test_context_window_basis_references_context_fields(self):
        from src.research.exegesis_contract import (
            ExegesisContextWindow,
            build_contextual_disambiguation_basis,
        )

        window = ExegesisContextWindow(
            term="伤寒",
            left_context="脉浮头项强痛",
            right_context="恶寒发热",
            dynasty="汉",
            school="伤寒学派",
            witness_key="宋本",
            graph_neighbors=("太阳病", "桂枝汤"),
        )
        basis = build_contextual_disambiguation_basis(window)
        self.assertTrue(any(item.startswith("left_context:") for item in basis))
        self.assertTrue(any(item.startswith("dynasty:汉") for item in basis))
        self.assertTrue(any(item.startswith("graph_neighbors:") for item in basis))

    def test_same_term_different_dynasty_context_generates_different_basis(self):
        from src.research.exegesis_contract import (
            ExegesisContextWindow,
            disambiguate_polysemy,
        )

        class FakeDict:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "外感病名，需随上下文判别",
                    "definition_source": "terminology_note",
                }

        han = disambiguate_polysemy(
            "厥",
            "theory",
            dictionaries=[FakeDict()],
            context_window=ExegesisContextWindow(
                term="厥",
                left_context="脉浮头痛",
                dynasty="汉",
                witness_key="宋本",
            ),
        )
        ming = disambiguate_polysemy(
            "厥",
            "theory",
            dictionaries=[FakeDict()],
            context_window=ExegesisContextWindow(
                term="厥",
                right_context="温热暑湿",
                dynasty="明",
                school="温病学派",
                witness_key="明抄本",
            ),
        )
        self.assertNotEqual(han["disambiguation_basis"], ming["disambiguation_basis"])
        self.assertIn("dynasty:汉", han["disambiguation_basis"])
        self.assertIn("dynasty:明", ming["disambiguation_basis"])
        self.assertTrue(
            any(
                item.startswith("right_context:")
                for item in ming["disambiguation_basis"]
            )
        )

    def test_empty_context_window_degrades_without_error(self):
        from src.research.exegesis_contract import (
            ExegesisContextWindow,
            build_contextual_disambiguation_basis,
            disambiguate_polysemy,
        )

        class FakeDict:
            def lookup(self, canonical, *, category=""):
                return {
                    "definition": "兜底释义",
                    "definition_source": "terminology_note",
                }

        self.assertEqual(
            build_contextual_disambiguation_basis(ExegesisContextWindow()), []
        )
        result = disambiguate_polysemy(
            "术语A",
            "theory",
            dictionaries=[FakeDict()],
            context_window=ExegesisContextWindow(),
        )
        self.assertEqual(result["definition"], "兜底释义")


if __name__ == "__main__":
    unittest.main()
