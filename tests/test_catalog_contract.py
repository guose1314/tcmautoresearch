"""Unit tests for catalog_contract and catalog normalization across layers."""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from src.research.catalog_contract import (
    BACKFILL_RULES,
    CATALOG_BASELINE_FIELDS,
    CATALOG_CORE_FIELDS,
    CATALOG_FILTER_FIELDS,
    FIELD_AUTHOR,
    FIELD_CATALOG_ID,
    FIELD_DYNASTY,
    FIELD_EDITION,
    FIELD_FRAGMENT_TITLE,
    FIELD_LINEAGE_SOURCE,
    FIELD_VERSION_LINEAGE_KEY,
    FIELD_WITNESS_KEY,
    FIELD_WORK_TITLE,
    assess_catalog_completeness,
    build_backfill_summary,
    build_catalog_hierarchy,
    has_baseline_fields,
    normalize_catalog_entry,
)


def _make_complete_document(**overrides: Any) -> Dict[str, Any]:
    base = {
        "document_id": "doc:1",
        "document_title": "补血汤宋本",
        "document_urn": "ctext:supplementblood",
        "catalog_id": "local:catalog:1",
        "work_title": "补血汤",
        "fragment_title": "补血汤·卷一",
        "work_fragment_key": "补血汤|补血汤卷一",
        "version_lineage_key": "补血汤|补血汤卷一|明|李时珍|宋本",
        "witness_key": "local:doc:1",
        "dynasty": "明",
        "author": "李时珍",
        "edition": "宋本",
        "source_type": "local",
        "lineage_source": "explicit_metadata",
    }
    base.update(overrides)
    return base


def _make_incomplete_document(**overrides: Any) -> Dict[str, Any]:
    base = {
        "document_id": "doc:2",
        "document_title": "某未知文献",
        "work_title": "某未知文献",
    }
    base.update(overrides)
    return base


class TestCatalogContract(unittest.TestCase):
    """Tests for the catalog_contract module."""

    def test_core_fields_tuple_contains_expected(self):
        self.assertIn("catalog_id", CATALOG_CORE_FIELDS)
        self.assertIn("work_title", CATALOG_CORE_FIELDS)
        self.assertIn("fragment_title", CATALOG_CORE_FIELDS)
        self.assertIn("version_lineage_key", CATALOG_CORE_FIELDS)
        self.assertIn("witness_key", CATALOG_CORE_FIELDS)

    def test_backfill_rules_defined_for_each_core_field(self):
        for field_name in CATALOG_CORE_FIELDS:
            self.assertIn(field_name, BACKFILL_RULES, f"Missing backfill rules for {field_name}")
            self.assertIsInstance(BACKFILL_RULES[field_name], list)
            self.assertGreater(len(BACKFILL_RULES[field_name]), 0, f"Empty backfill rules for {field_name}")


class TestAssessCatalogCompleteness(unittest.TestCase):

    def test_complete_entry_full_score(self):
        doc = _make_complete_document()
        result = assess_catalog_completeness(doc)
        self.assertEqual(result["missing_core_fields"], [])
        self.assertEqual(result["metadata_completeness"], 1.0)
        self.assertFalse(result["needs_backfill"])
        self.assertEqual(result["backfill_candidates"], [])

    def test_missing_one_field(self):
        doc = _make_complete_document(catalog_id="")
        result = assess_catalog_completeness(doc)
        self.assertIn("catalog_id", result["missing_core_fields"])
        self.assertAlmostEqual(result["metadata_completeness"], 0.8, places=2)
        self.assertTrue(result["needs_backfill"])
        self.assertTrue(any(c["field"] == "catalog_id" for c in result["backfill_candidates"]))

    def test_empty_entry_all_missing(self):
        result = assess_catalog_completeness({})
        self.assertEqual(len(result["missing_core_fields"]), len(CATALOG_CORE_FIELDS))
        self.assertEqual(result["metadata_completeness"], 0.0)
        self.assertTrue(result["needs_backfill"])

    def test_backfill_candidates_contain_strategy(self):
        doc = _make_incomplete_document()
        result = assess_catalog_completeness(doc)
        for candidate in result["backfill_candidates"]:
            self.assertIn("field", candidate)
            self.assertIn("source", candidate)
            self.assertIn("strategy", candidate)


class TestNormalizeCatalogEntry(unittest.TestCase):

    def test_normalizes_aliases(self):
        entry = {
            "id": "doc:1",
            "title": "本草纲目",
            "urn": "ctext:bencao",
            "work_title": "本草纲目",
            "catalog_id": "cat:1",
            "fragment_title": "卷一",
            "version_lineage_key": "本草纲目|卷一|明|李时珍|",
            "witness_key": "cat:1:src",
        }
        result = normalize_catalog_entry(entry)
        self.assertEqual(result["document_id"], "doc:1")
        self.assertEqual(result["document_title"], "本草纲目")
        self.assertEqual(result["document_urn"], "ctext:bencao")

    def test_includes_completeness(self):
        result = normalize_catalog_entry(_make_complete_document())
        self.assertIn("missing_core_fields", result)
        self.assertIn("metadata_completeness", result)
        self.assertIn("needs_backfill", result)
        self.assertIn("backfill_candidates", result)


class TestHasBaselineFields(unittest.TestCase):

    def test_returns_true_with_at_least_one_field(self):
        self.assertTrue(has_baseline_fields({"work_title": "本草纲目"}))
        self.assertTrue(has_baseline_fields({"dynasty": "明"}))
        self.assertTrue(has_baseline_fields({"catalog_id": "cat:1"}))

    def test_returns_false_for_empty(self):
        self.assertFalse(has_baseline_fields({}))
        self.assertFalse(has_baseline_fields({"work_title": "", "dynasty": ""}))

    def test_returns_false_for_none_values(self):
        self.assertFalse(has_baseline_fields({"work_title": None, "catalog_id": None}))


class TestBuildCatalogHierarchy(unittest.TestCase):

    def test_single_document(self):
        docs = [_make_complete_document()]
        result = build_catalog_hierarchy(docs)
        self.assertEqual(result["work_count"], 1)
        self.assertEqual(result["fragment_count"], 1)
        self.assertEqual(result["lineage_count"], 1)
        self.assertEqual(result["witness_count"], 1)
        self.assertEqual(result["works"][0]["work_title"], "补血汤")

    def test_multiple_works(self):
        docs = [
            _make_complete_document(work_title="本草纲目", fragment_title="卷一",
                                    version_lineage_key="lin:1", witness_key="w:1"),
            _make_complete_document(work_title="伤寒论", fragment_title="太阳篇",
                                    version_lineage_key="lin:2", witness_key="w:2"),
        ]
        result = build_catalog_hierarchy(docs)
        self.assertEqual(result["work_count"], 2)
        self.assertEqual(result["fragment_count"], 2)
        work_titles = [w["work_title"] for w in result["works"]]
        self.assertIn("本草纲目", work_titles)
        self.assertIn("伤寒论", work_titles)

    def test_same_work_multiple_fragments(self):
        docs = [
            _make_complete_document(fragment_title="卷一", version_lineage_key="lin:1", witness_key="w:1"),
            _make_complete_document(fragment_title="卷二", version_lineage_key="lin:2", witness_key="w:2"),
        ]
        result = build_catalog_hierarchy(docs)
        self.assertEqual(result["work_count"], 1)
        self.assertEqual(result["fragment_count"], 2)
        self.assertEqual(result["lineage_count"], 2)

    def test_same_lineage_multiple_witnesses(self):
        docs = [
            _make_complete_document(witness_key="w:1"),
            _make_complete_document(witness_key="w:2", document_id="doc:2"),
        ]
        result = build_catalog_hierarchy(docs)
        self.assertEqual(result["work_count"], 1)
        self.assertEqual(result["fragment_count"], 1)
        self.assertEqual(result["lineage_count"], 1)
        self.assertEqual(result["witness_count"], 2)

    def test_empty_input(self):
        result = build_catalog_hierarchy([])
        self.assertEqual(result["work_count"], 0)
        self.assertEqual(result["works"], [])

    def test_missing_work_title_uses_fallback(self):
        docs = [{"fragment_title": "片段A", "version_lineage_key": "lin:1", "witness_key": "w:1"}]
        result = build_catalog_hierarchy(docs)
        self.assertEqual(result["work_count"], 1)
        self.assertEqual(result["works"][0]["work_title"], "(未知作品)")


class TestBuildBackfillSummary(unittest.TestCase):

    def test_no_backfill_needed(self):
        docs = [_make_complete_document()]
        result = build_backfill_summary(docs)
        self.assertEqual(result["needs_backfill_count"], 0)
        self.assertEqual(result["entries"], [])

    def test_detects_missing_fields(self):
        docs = [_make_incomplete_document()]
        result = build_backfill_summary(docs)
        self.assertGreater(result["needs_backfill_count"], 0)
        self.assertIn("catalog_id", result["field_gap_counts"])

    def test_summaries_across_multiple_docs(self):
        docs = [
            _make_complete_document(),
            _make_incomplete_document(),
            _make_incomplete_document(document_id="doc:3", witness_key="", catalog_id=""),
        ]
        result = build_backfill_summary(docs)
        self.assertEqual(result["needs_backfill_count"], 2)


class TestCatalogNormalizationObserveIntegration(unittest.TestCase):
    """验证 observe_philology 层使用合同后的归一化行为。"""

    def test_normalize_catalog_document_has_backfill_info(self):
        from src.research.observe_philology import _normalize_catalog_document

        record = _make_complete_document()
        result = _normalize_catalog_document(record)
        self.assertIn("needs_backfill", result)
        self.assertIn("backfill_candidates", result)
        self.assertFalse(result["needs_backfill"])

    def test_normalize_catalog_document_incomplete_has_candidates(self):
        from src.research.observe_philology import _normalize_catalog_document

        record = _make_incomplete_document()
        result = _normalize_catalog_document(record)
        self.assertTrue(result["needs_backfill"])
        self.assertGreater(len(result["backfill_candidates"]), 0)

    def test_normalize_full_assets_includes_hierarchy(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        assets = {
            "catalog_summary": {
                "documents": [
                    _make_complete_document(),
                    _make_complete_document(
                        document_id="doc:2",
                        work_title="伤寒论",
                        fragment_title="太阳篇",
                        version_lineage_key="lin:2",
                        witness_key="w:2",
                    ),
                ],
            },
        }
        result = normalize_observe_philology_assets(assets)
        catalog_summary = result.get("catalog_summary", {})
        summary = catalog_summary.get("summary", {})
        self.assertIn("catalog_hierarchy", summary)
        hierarchy = summary["catalog_hierarchy"]
        self.assertEqual(hierarchy["work_count"], 2)
        self.assertIn("needs_backfill_count", summary)

    def test_normalize_full_assets_backfill_detection(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        assets = {
            "catalog_summary": {
                "documents": [
                    _make_incomplete_document(),
                ],
            },
        }
        result = normalize_observe_philology_assets(assets)
        catalog_summary = result.get("catalog_summary", {})
        summary = catalog_summary.get("summary", {})
        self.assertGreater(summary.get("needs_backfill_count", 0), 0)

    def test_catalog_entry_has_baseline_fields_delegates(self):
        from src.research.observe_philology import _catalog_entry_has_baseline_fields

        self.assertTrue(_catalog_entry_has_baseline_fields({"work_title": "本草纲目"}))
        self.assertFalse(_catalog_entry_has_baseline_fields({}))


class TestCorpusBundleCatalogContract(unittest.TestCase):
    """验证 corpus_bundle 层使用合同常量后的字段输出。"""

    def test_build_version_metadata_uses_contract_fields(self):
        from src.collector.corpus_bundle import build_document_version_metadata

        result = build_document_version_metadata(
            title="本草纲目",
            source_type="local",
            source_ref="data/013-本草纲目-明-李时珍.txt",
        )
        vm = result.get("version_metadata", {})
        self.assertEqual(vm[FIELD_WORK_TITLE], "本草纲目")
        self.assertEqual(vm[FIELD_DYNASTY], "明")
        self.assertEqual(vm[FIELD_AUTHOR], "李时珍")
        self.assertIn(FIELD_VERSION_LINEAGE_KEY, vm)
        self.assertIn(FIELD_WITNESS_KEY, vm)
        self.assertIn(FIELD_CATALOG_ID, vm)

    def test_build_version_metadata_fallback_chain(self):
        from src.collector.corpus_bundle import build_document_version_metadata

        result = build_document_version_metadata(
            title="未知文献",
            source_type="local",
            source_ref="data/unknown.txt",
        )
        vm = result.get("version_metadata", {})
        self.assertEqual(vm[FIELD_WORK_TITLE], "未知文献")
        self.assertEqual(vm[FIELD_LINEAGE_SOURCE], "title_fallback")

    def test_build_version_metadata_explicit_overrides(self):
        from src.collector.corpus_bundle import build_document_version_metadata

        result = build_document_version_metadata(
            title="原标题",
            source_type="ctext",
            source_ref="ctext:bencao",
            metadata={
                "version_metadata": {
                    "work_title": "显式名称",
                    "dynasty": "清",
                    "author": "显式作者",
                }
            },
        )
        vm = result.get("version_metadata", {})
        self.assertEqual(vm[FIELD_WORK_TITLE], "显式名称")
        self.assertEqual(vm[FIELD_DYNASTY], "清")
        self.assertEqual(vm[FIELD_AUTHOR], "显式作者")


class TestSnapshotDashboardConsistency(unittest.TestCase):
    """验证 snapshot 与 dashboard 对同一目录字段给出一致结果。"""

    def test_observe_and_contract_use_same_core_fields(self):
        from src.research.observe_philology import _CATALOG_CORE_FIELDS

        self.assertEqual(_CATALOG_CORE_FIELDS, CATALOG_CORE_FIELDS)

    def test_observe_and_contract_use_same_filter_fields(self):
        from src.research.observe_philology import _CATALOG_FILTER_FIELDS

        self.assertEqual(_CATALOG_FILTER_FIELDS, CATALOG_FILTER_FIELDS)

    def test_filter_contract_options_match_core_fields(self):
        from src.research.observe_philology import (
            build_observe_philology_filter_contract,
        )

        assets = {
            "catalog_summary": {
                "documents": [_make_complete_document()],
            },
        }
        contract = build_observe_philology_filter_contract(assets, {})
        options = contract.get("options", {})
        self.assertIn("work_title", options)

    def test_catalog_summary_artifact_has_hierarchy(self):
        from src.research.observe_philology import (
            build_observe_philology_artifact_payloads,
        )

        assets = {
            "catalog_summary": {
                "documents": [
                    _make_complete_document(),
                    _make_complete_document(
                        document_id="doc:2",
                        work_title="伤寒论",
                        fragment_title="太阳篇",
                        version_lineage_key="lin:2",
                        witness_key="w:2",
                    ),
                ],
            },
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        catalog_artifact = next(
            (a for a in artifacts if a["name"] == "observe_philology_catalog_summary"),
            None,
        )
        self.assertIsNotNone(catalog_artifact)
        summary = catalog_artifact["content"]["summary"]
        self.assertIn("catalog_hierarchy", summary)
        self.assertEqual(summary["catalog_hierarchy"]["work_count"], 2)
        self.assertIn("needs_backfill_count", summary)


if __name__ == "__main__":
    unittest.main()
