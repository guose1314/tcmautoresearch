"""Tests for version lineage diff and variant reading contracts."""

from __future__ import annotations

import unittest


class TestVersionLineageContract(unittest.TestCase):
    def _readings(self):
        return [
            {
                "base_witness": "宋本",
                "target_witness": "明抄本",
                "base_text": "桂枝二两",
                "variant_text": "桂枝三两",
                "normalized_meaning": "剂量异文，可能影响方剂配伍强度",
                "impact_level": "high",
                "evidence_ref": "collation:001",
            },
            {
                "base_witness": "宋本",
                "target_witness": "明抄本",
                "variant_text": "去生姜",
                "normalized_meaning": "药物组成异文",
                "impact_level": "medium",
                "evidence_ref": "collation:002",
            },
        ]

    def test_variant_readings_generate_diff_summary(self):
        from src.research.version_lineage_contract import (
            build_lineage_diff_from_variant_readings,
        )

        diff = build_lineage_diff_from_variant_readings(
            "宋本",
            "明抄本",
            self._readings(),
            version_lineage_key="桂枝汤|太阳篇",
        )
        summary = diff.summary().to_dict()
        self.assertEqual(summary["diff_count"], 1)
        self.assertEqual(summary["variant_reading_count"], 2)
        self.assertEqual(summary["witness_pair_count"], 1)
        self.assertEqual(summary["impact_distribution"], {"high": 1, "medium": 1})
        self.assertIn("collation:001", summary["evidence_refs"])

    def test_diff_summary_converts_to_neo4j_payload(self):
        from src.research.version_lineage_contract import (
            VARIANT_READING_NODE_LABEL,
            VERSION_LINEAGE_DIFF_NODE_LABEL,
            build_lineage_diff_from_variant_readings,
            build_lineage_diff_graph_payload,
        )

        diff = build_lineage_diff_from_variant_readings(
            "宋本",
            "明抄本",
            self._readings(),
            version_lineage_key="桂枝汤|太阳篇",
        )
        payload = build_lineage_diff_graph_payload("cycle-001", [diff])
        labels = {node["label"] for node in payload["nodes"]}
        rel_types = {edge["relationship_type"] for edge in payload["edges"]}
        self.assertIn(VERSION_LINEAGE_DIFF_NODE_LABEL, labels)
        self.assertIn(VARIANT_READING_NODE_LABEL, labels)
        self.assertIn("VersionWitness", labels)
        self.assertIn("HAS_VARIANT_READING", rel_types)
        self.assertIn("COMPARES_WITNESS", rel_types)
        self.assertEqual(payload["summary"]["variant_reading_count"], 2)

    def test_observe_philology_normalizes_artifacts_and_graph_assets(self):
        from src.research.observe_philology import (
            OBSERVE_PHILOLOGY_VERSION_LINEAGE_DIFF_ARTIFACT,
            build_observe_philology_artifact_payloads,
            build_observe_philology_graph_assets,
            extract_observe_philology_assets_from_artifacts,
            normalize_observe_philology_assets,
        )
        from src.research.version_lineage_contract import (
            build_lineage_diff_from_variant_readings,
        )

        diff = build_lineage_diff_from_variant_readings(
            "宋本",
            "明抄本",
            self._readings(),
            version_lineage_key="桂枝汤|太阳篇",
        )
        assets = {"version_lineage_diffs": [diff.to_dict()]}
        normalized = normalize_observe_philology_assets(assets)
        self.assertTrue(normalized["available"])
        self.assertEqual(normalized["version_lineage_diff_count"], 1)
        self.assertEqual(normalized["variant_reading_count"], 2)

        graph_assets = build_observe_philology_graph_assets("cycle-001", assets)
        labels = {node["label"] for node in graph_assets["philology_subgraph"]["nodes"]}
        self.assertIn("VersionLineageDiff", labels)
        self.assertIn("VariantReading", labels)

        artifacts = build_observe_philology_artifact_payloads(assets)
        self.assertTrue(
            any(
                item["name"] == OBSERVE_PHILOLOGY_VERSION_LINEAGE_DIFF_ARTIFACT
                for item in artifacts
            )
        )
        restored = extract_observe_philology_assets_from_artifacts(artifacts)
        self.assertEqual(restored["version_lineage_diff_count"], 1)


if __name__ == "__main__":
    unittest.main()
