"""Tests for fragment reconstruction artifact export and dashboard integration."""

from __future__ import annotations

import unittest

from src.research.observe_philology import (
    OBSERVE_PHILOLOGY_ARTIFACT_NAMES,
    OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT,
    build_observe_philology_artifact_payloads,
    extract_observe_philology_assets_from_artifacts,
    normalize_observe_philology_assets,
)


def _make_fragment_candidate(**overrides):
    base = {
        "fragment_candidate_id": "urn:test::witness1::insert:0:0",
        "candidate_kind": "fragment_candidates",
        "title": "补血汤",
        "document_title": "补血汤宋本",
        "document_urn": "ctext:supplementblood",
        "source_type": "local",
        "base_text": "原文",
        "witness_text": "原文加上新增文字",
        "difference_type": "insert",
        "match_score": 0.82,
        "source_refs": ["witness1"],
        "reconstruction_basis": "异文比对：基础本无此段，见证本新增",
        "needs_manual_review": True,
        "review_status": "pending",
        "review_reasons": ["新增段落"],
    }
    base.update(overrides)
    return base


def _make_lost_text_candidate(**overrides):
    base = _make_fragment_candidate(
        fragment_candidate_id="urn:test::witness2::insert:1:0",
        candidate_kind="lost_text_candidates",
        difference_type="insert",
        match_score=0.68,
        reconstruction_basis="整段仅见于此见证本",
    )
    base.update(overrides)
    return base


def _make_citation_source_candidate(**overrides):
    base = _make_fragment_candidate(
        fragment_candidate_id="urn:test::witness3::citation:0:0",
        candidate_kind="citation_source_candidates",
        difference_type="replace",
        match_score=0.75,
        reconstruction_basis="引文来源对比",
    )
    base.update(overrides)
    return base


class TestFragmentReconstructionArtifactConstant(unittest.TestCase):
    def test_constant_defined(self):
        self.assertEqual(
            OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT,
            "observe_philology_fragment_reconstruction",
        )

    def test_constant_in_artifact_names_set(self):
        self.assertIn(
            OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT,
            OBSERVE_PHILOLOGY_ARTIFACT_NAMES,
        )


class TestFragmentReconstructionArtifactExport(unittest.TestCase):
    def test_artifact_generated_when_candidates_present(self):
        assets = {
            "terminology_standard_table": [{"canonical": "黄芪", "label": "本草药名"}],
            "fragment_candidates": [_make_fragment_candidate()],
            "lost_text_candidates": [_make_lost_text_candidate()],
            "citation_source_candidates": [_make_citation_source_candidate()],
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        fragment_artifacts = [
            a for a in artifacts
            if a.get("name") == OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT
        ]
        self.assertEqual(len(fragment_artifacts), 1)
        artifact = fragment_artifacts[0]
        self.assertEqual(artifact["artifact_type"], "analysis")
        self.assertEqual(artifact["mime_type"], "application/json")
        content = artifact["content"]
        self.assertEqual(content["asset_kind"], "fragment_reconstruction")
        self.assertEqual(len(content["fragment_candidates"]), 1)
        self.assertEqual(len(content["lost_text_candidates"]), 1)
        self.assertEqual(len(content["citation_source_candidates"]), 1)
        summary = content["summary"]
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["fragment_candidate_count"], 1)
        self.assertEqual(summary["lost_text_candidate_count"], 1)
        self.assertEqual(summary["citation_source_candidate_count"], 1)
        metadata = artifact["metadata"]
        self.assertEqual(metadata["asset_kind"], "fragment_reconstruction")
        self.assertEqual(metadata["fragment_candidate_count"], 1)

    def test_no_artifact_when_no_candidates(self):
        assets = {
            "terminology_standard_table": [{"canonical": "黄芪", "label": "本草药名"}],
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        fragment_artifacts = [
            a for a in artifacts
            if a.get("name") == OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT
        ]
        self.assertEqual(len(fragment_artifacts), 0)

    def test_artifact_disabled_via_config(self):
        assets = {
            "terminology_standard_table": [{"canonical": "黄芪"}],
            "fragment_candidates": [_make_fragment_candidate()],
        }
        artifacts = build_observe_philology_artifact_payloads(
            assets, {"include_fragment_reconstruction": False}
        )
        fragment_artifacts = [
            a for a in artifacts
            if a.get("name") == OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT
        ]
        self.assertEqual(len(fragment_artifacts), 0)


class TestFragmentReconstructionArtifactRoundtrip(unittest.TestCase):
    def test_roundtrip_via_extract_from_artifacts(self):
        assets = {
            "fragment_candidates": [_make_fragment_candidate()],
            "lost_text_candidates": [_make_lost_text_candidate()],
            "citation_source_candidates": [_make_citation_source_candidate()],
        }
        artifacts = build_observe_philology_artifact_payloads(assets)
        fragment_artifacts = [
            a for a in artifacts
            if a.get("name") == OBSERVE_PHILOLOGY_FRAGMENT_RECONSTRUCTION_ARTIFACT
        ]
        if not fragment_artifacts:
            self.skipTest("No fragment artifact generated")
        restored = extract_observe_philology_assets_from_artifacts(fragment_artifacts)
        self.assertEqual(len(restored.get("fragment_candidates", [])), 1)
        self.assertEqual(len(restored.get("lost_text_candidates", [])), 1)
        self.assertEqual(len(restored.get("citation_source_candidates", [])), 1)


class TestNormalizeWithFragmentMetrics(unittest.TestCase):
    def test_fragment_metrics_in_catalog_summary(self):
        assets = {
            "fragment_candidates": [_make_fragment_candidate(match_score=0.85)],
            "lost_text_candidates": [_make_lost_text_candidate(match_score=0.60)],
            "citation_source_candidates": [],
        }
        normalized = normalize_observe_philology_assets(assets)
        self.assertEqual(normalized["fragment_candidate_count"], 2)
        catalog_summary = normalized.get("catalog_summary") or {}
        summary = catalog_summary.get("summary") or {}
        self.assertEqual(summary.get("fragment_candidate_count"), 1)
        self.assertEqual(summary.get("lost_text_candidate_count"), 1)
        self.assertEqual(summary.get("fragment_total_count"), 2)
        self.assertGreater(summary.get("fragment_avg_score", 0), 0)

    def test_no_fragment_metrics_when_empty(self):
        assets = {
            "terminology_standard_table": [{"canonical": "黄芪"}],
        }
        normalized = normalize_observe_philology_assets(assets)
        self.assertEqual(normalized["fragment_candidate_count"], 0)
        catalog_summary = normalized.get("catalog_summary") or {}
        summary = catalog_summary.get("summary") or {}
        self.assertNotIn("fragment_total_count", summary)


class TestDashboardFragmentSummaryCard(unittest.TestCase):
    def test_card_renders_with_data(self):
        from src.web.routes.dashboard import _render_fragment_summary_card

        metrics = {
            "fragment_total_count": 5,
            "fragment_candidate_count": 2,
            "lost_text_candidate_count": 1,
            "citation_source_candidate_count": 2,
            "fragment_needs_review_count": 3,
            "fragment_high_confidence_count": 2,
            "fragment_avg_score": 0.76,
            "fragment_review_status_distribution": {"pending": 3, "accepted": 2},
        }
        html = _render_fragment_summary_card(metrics)
        self.assertIn("辑佚摘要", html)
        self.assertIn("疑似佚文", html)
        self.assertIn("疑似佚失", html)
        self.assertIn("引文来源", html)
        self.assertIn("0.76", html)
        self.assertIn("待复核", html)
        self.assertIn("已采纳", html)

    def test_card_empty_when_no_data(self):
        from src.web.routes.dashboard import _render_fragment_summary_card

        html = _render_fragment_summary_card({})
        self.assertEqual(html, "")

    def test_card_empty_when_total_zero(self):
        from src.web.routes.dashboard import _render_fragment_summary_card

        html = _render_fragment_summary_card({"fragment_total_count": 0})
        self.assertEqual(html, "")


if __name__ == "__main__":
    unittest.main()
