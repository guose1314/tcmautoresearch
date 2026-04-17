"""Tests for src/research/catalog_contract.py — 目录学字段合同 (Phase 2)。"""

from __future__ import annotations

import unittest


class TestNormalizeDynasty(unittest.TestCase):
    """朝代归一化函数。"""

    def test_canonical_passthrough(self):
        from src.research.catalog_contract import normalize_dynasty

        self.assertEqual(normalize_dynasty("唐"), "唐")
        self.assertEqual(normalize_dynasty("明"), "明")
        self.assertEqual(normalize_dynasty("清"), "清")

    def test_broad_synonyms(self):
        from src.research.catalog_contract import normalize_dynasty

        self.assertEqual(normalize_dynasty("前汉"), "西汉")
        self.assertEqual(normalize_dynasty("后汉"), "五代")  # "后汉" 在宽泛模式映射 → 五代
        self.assertEqual(normalize_dynasty("五代十国"), "五代")
        self.assertEqual(normalize_dynasty("唐代"), "唐")
        self.assertEqual(normalize_dynasty("北宋"), "宋")
        self.assertEqual(normalize_dynasty("南宋"), "宋")
        self.assertEqual(normalize_dynasty("刘宋"), "南朝")
        self.assertEqual(normalize_dynasty("曹魏"), "三国")

    def test_precise_mode(self):
        from src.research.catalog_contract import normalize_dynasty

        self.assertEqual(normalize_dynasty("前汉", precise=True), "西汉")
        self.assertEqual(normalize_dynasty("唐代", precise=True), "唐")
        self.assertEqual(normalize_dynasty("刘宋", precise=True), "南朝宋")
        self.assertEqual(normalize_dynasty("萧齐", precise=True), "南朝齐")
        self.assertEqual(normalize_dynasty("曹魏", precise=True), "魏")

    def test_empty_input(self):
        from src.research.catalog_contract import normalize_dynasty

        self.assertEqual(normalize_dynasty(""), "")
        self.assertEqual(normalize_dynasty(None), "")  # type: ignore[arg-type]

    def test_unknown_passthrough(self):
        from src.research.catalog_contract import normalize_dynasty

        self.assertEqual(normalize_dynasty("不存在的朝代"), "不存在的朝代")


class TestValidateLineageConsistency(unittest.TestCase):
    """跨作品谱系一致性校验。"""

    def test_consistent_documents(self):
        from src.research.catalog_contract import validate_lineage_consistency

        docs = [
            {"work_title": "本草纲目", "dynasty": "明", "author": "李时珍", "version_lineage_key": "lin-1"},
            {"work_title": "本草纲目", "dynasty": "明代", "author": "李时珍", "version_lineage_key": "lin-1"},
        ]
        result = validate_lineage_consistency(docs)
        # "明" and "明代" both normalize to "明" in precise mode
        self.assertEqual(result["inconsistencies"], [])
        self.assertGreater(result["consistency_score"], 0.9)

    def test_dynasty_conflict(self):
        from src.research.catalog_contract import validate_lineage_consistency

        docs = [
            {"work_title": "伤寒论", "dynasty": "东汉", "author": "张仲景", "version_lineage_key": "lin-2"},
            {"work_title": "伤寒论", "dynasty": "唐", "author": "张仲景", "version_lineage_key": "lin-2"},
        ]
        result = validate_lineage_consistency(docs)
        dynasty_conflicts = [i for i in result["inconsistencies"] if i["type"] == "dynasty_conflict"]
        self.assertEqual(len(dynasty_conflicts), 1)
        self.assertEqual(dynasty_conflicts[0]["work_title"], "伤寒论")

    def test_author_conflict(self):
        from src.research.catalog_contract import validate_lineage_consistency

        docs = [
            {"work_title": "黄帝内经", "dynasty": "先秦", "author": "黄帝", "version_lineage_key": "lin-3"},
            {"work_title": "黄帝内经", "dynasty": "先秦", "author": "岐伯", "version_lineage_key": "lin-3"},
        ]
        result = validate_lineage_consistency(docs)
        author_conflicts = [i for i in result["inconsistencies"] if i["type"] == "author_conflict"]
        self.assertEqual(len(author_conflicts), 1)

    def test_lineage_shared_across_works(self):
        from src.research.catalog_contract import validate_lineage_consistency

        docs = [
            {"work_title": "本草纲目", "dynasty": "明", "author": "李时珍", "version_lineage_key": "shared-lin"},
            {"work_title": "神农本草经", "dynasty": "先秦", "author": "不详", "version_lineage_key": "shared-lin"},
        ]
        result = validate_lineage_consistency(docs)
        shared = [i for i in result["inconsistencies"] if i["type"] == "lineage_shared_across_works"]
        self.assertEqual(len(shared), 1)
        self.assertIn("shared-lin", shared[0]["version_lineage_key"])

    def test_empty_documents(self):
        from src.research.catalog_contract import validate_lineage_consistency

        result = validate_lineage_consistency([])
        self.assertEqual(result["inconsistencies"], [])
        self.assertEqual(result["works_checked"], 0)

    def test_documents_without_work_title_skipped(self):
        from src.research.catalog_contract import validate_lineage_consistency

        docs = [{"dynasty": "明", "author": "x"}, {"work_title": "", "dynasty": "清"}]
        result = validate_lineage_consistency(docs)
        self.assertEqual(result["works_checked"], 0)


class TestAssessCatalogCompleteness(unittest.TestCase):
    def test_complete_entry(self):
        from src.research.catalog_contract import assess_catalog_completeness

        entry = {
            "catalog_id": "cat-001",
            "work_title": "本草纲目",
            "fragment_title": "卷一",
            "version_lineage_key": "lin-001",
            "witness_key": "wit-001",
        }
        result = assess_catalog_completeness(entry)
        self.assertEqual(result["missing_core_fields"], [])
        self.assertEqual(result["metadata_completeness"], 1.0)
        self.assertFalse(result["needs_backfill"])

    def test_partial_entry(self):
        from src.research.catalog_contract import assess_catalog_completeness

        entry = {"work_title": "本草纲目"}
        result = assess_catalog_completeness(entry)
        self.assertIn("catalog_id", result["missing_core_fields"])
        self.assertLess(result["metadata_completeness"], 1.0)
        self.assertTrue(result["needs_backfill"])


class TestNormalizeCatalogEntry(unittest.TestCase):
    def test_alias_mapping(self):
        from src.research.catalog_contract import normalize_catalog_entry

        entry = {"title": "本草纲目", "id": "doc-1", "urn": "urn:1"}
        normalized = normalize_catalog_entry(entry)
        self.assertEqual(normalized["document_title"], "本草纲目")
        self.assertEqual(normalized["document_id"], "doc-1")
        self.assertEqual(normalized["document_urn"], "urn:1")


class TestBuildCatalogHierarchy(unittest.TestCase):
    def test_basic_hierarchy(self):
        from src.research.catalog_contract import build_catalog_hierarchy

        docs = [
            {"work_title": "本草纲目", "fragment_title": "卷一", "version_lineage_key": "lin-A", "witness_key": "w1"},
            {"work_title": "本草纲目", "fragment_title": "卷一", "version_lineage_key": "lin-A", "witness_key": "w2"},
            {"work_title": "本草纲目", "fragment_title": "卷二", "version_lineage_key": "lin-B", "witness_key": "w3"},
        ]
        result = build_catalog_hierarchy(docs)
        self.assertEqual(result["work_count"], 1)
        self.assertEqual(result["fragment_count"], 2)
        self.assertEqual(result["witness_count"], 3)

    def test_empty_documents(self):
        from src.research.catalog_contract import build_catalog_hierarchy

        result = build_catalog_hierarchy([])
        self.assertEqual(result["work_count"], 0)


class TestBuildBackfillSummary(unittest.TestCase):
    def test_all_complete_no_backfill(self):
        from src.research.catalog_contract import build_backfill_summary

        docs = [
            {"catalog_id": "c1", "work_title": "w1", "fragment_title": "f1", "version_lineage_key": "l1", "witness_key": "k1"},
        ]
        result = build_backfill_summary(docs)
        self.assertEqual(result["needs_backfill_count"], 0)

    def test_missing_fields_detected(self):
        from src.research.catalog_contract import build_backfill_summary

        docs = [{"work_title": "w1"}]
        result = build_backfill_summary(docs)
        self.assertGreater(result["needs_backfill_count"], 0)
        self.assertIn("catalog_id", result["field_gap_counts"])


class TestHasBaselineFields(unittest.TestCase):
    def test_has_one_baseline(self):
        from src.research.catalog_contract import has_baseline_fields

        self.assertTrue(has_baseline_fields({"work_title": "本草纲目"}))

    def test_no_baseline(self):
        from src.research.catalog_contract import has_baseline_fields

        self.assertFalse(has_baseline_fields({"random_field": "x"}))

    def test_empty_entry(self):
        from src.research.catalog_contract import has_baseline_fields

        self.assertFalse(has_baseline_fields({}))


if __name__ == "__main__":
    unittest.main()
