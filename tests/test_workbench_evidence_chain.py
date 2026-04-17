"""Tests for evidence_chain integration into the philology review workbench.

Covers:
- Evidence chain items appear as a workbench section in dashboard payload
- Workbench review decisions propagate to evidence chain items via normalize
- Upsert round-trip: decision persists via review_workbench artifact
- Review status filter: client-side filtering data attributes
"""

from __future__ import annotations

import unittest
from typing import Any, Dict


class TestEvidenceChainWorkbenchSection(unittest.TestCase):
    """Verify evidence_chain section is built inside the review workbench."""

    def _build_payload_with_evidence_chains(
        self,
        evidence_chains: list[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        from src.api.research_utils import build_research_dashboard_payload

        chains = evidence_chains if evidence_chains is not None else [
            {
                "evidence_chain_id": "ec-001",
                "claim_type": "authorship_attribution",
                "claim_statement": "《本草纲目》黄芪条作者归属李时珍",
                "confidence": 0.72,
                "basis_summary": "版本纪年吻合",
                "judgment_type": "needs_review",
                "counter_evidence": ["部分清抄本署名不同"],
                "needs_manual_review": True,
                "review_status": "pending",
                "review_reasons": ["置信度不足，需人工确认"],
                "source_refs": ["catalog:001"],
            },
            {
                "evidence_chain_id": "ec-002",
                "claim_type": "version_chronology",
                "claim_statement": "宋本早于明刻本",
                "confidence": 0.88,
                "basis_summary": "刻工行间距与字体一致",
                "judgment_type": "rule_based",
                "counter_evidence": [],
                "needs_manual_review": False,
                "review_status": "accepted",
                "review_reasons": [],
                "source_refs": ["collation:003"],
            },
        ]
        snapshot = {
            "job_id": "job-ec-wb",
            "topic": "考据工作台",
            "status": "completed",
            "progress": 100,
            "current_phase": "observe",
            "result": {
                "cycle_id": "cycle-ec-wb",
                "phases": [{"phase": "observe", "status": "completed", "duration_sec": 2.0}],
                "pipeline_metadata": {"cycle_name": "ec-demo"},
                "observe_philology": {
                    "evidence_chains": chains,
                },
            },
        }
        return build_research_dashboard_payload(snapshot)

    def test_evidence_chain_section_appears_in_workbench(self):
        payload = self._build_payload_with_evidence_chains()
        wb = payload["evidence_board"]["review_workbench"]
        section_map = {s["asset_type"]: s for s in wb["sections"]}
        self.assertIn("evidence_chain", section_map)
        self.assertEqual(section_map["evidence_chain"]["count"], 2)

    def test_evidence_chain_item_fields(self):
        payload = self._build_payload_with_evidence_chains()
        wb = payload["evidence_board"]["review_workbench"]
        section_map = {s["asset_type"]: s for s in wb["sections"]}
        items = section_map["evidence_chain"]["items"]
        item_0 = items[0]
        self.assertEqual(item_0["asset_type"], "evidence_chain")
        self.assertEqual(item_0["evidence_chain_id"], "ec-001")
        self.assertEqual(item_0["claim_type"], "authorship_attribution")
        self.assertIn("作者归属", item_0["subtitle"])
        self.assertTrue(item_0["needs_manual_review"])
        self.assertTrue(len(item_0["summary_lines"]) >= 3)

    def test_evidence_chain_item_has_asset_key(self):
        payload = self._build_payload_with_evidence_chains()
        wb = payload["evidence_board"]["review_workbench"]
        section_map = {s["asset_type"]: s for s in wb["sections"]}
        items = section_map["evidence_chain"]["items"]
        for item in items:
            self.assertTrue(item["asset_key"].startswith("evidence_chain::"))

    def test_empty_evidence_chains_produces_no_items(self):
        payload = self._build_payload_with_evidence_chains(evidence_chains=[])
        wb = payload["evidence_board"]["review_workbench"]
        section_map = {s["asset_type"]: s for s in wb["sections"]}
        self.assertEqual(section_map["evidence_chain"]["count"], 0)

    def test_section_meta_title(self):
        from src.api.research_utils import REVIEW_WORKBENCH_SECTION_META

        self.assertIn("evidence_chain", REVIEW_WORKBENCH_SECTION_META)
        self.assertIn("考据", REVIEW_WORKBENCH_SECTION_META["evidence_chain"]["title"])


class TestEvidenceChainReviewDecisionWriteback(unittest.TestCase):
    """Verify workbench review decisions propagate to evidence chain items."""

    def test_evidence_chain_gets_review_status_from_workbench_decision(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "evidence_chains": [
                {
                    "evidence_chain_id": "ec-010",
                    "claim_type": "citation_source",
                    "claim_statement": "此段引自《神农本草经》",
                    "confidence": 0.65,
                    "basis_summary": "用词比对匹配",
                    "judgment_type": "needs_review",
                    "needs_manual_review": True,
                    "review_status": "pending",
                },
            ],
            "review_workbench_decisions": [
                {
                    "asset_type": "evidence_chain",
                    "asset_key": "evidence_chain::evidence_chain_id=ec-010|claim_type=citation_source|claim_statement=此段引自《神农本草经》",
                    "review_status": "accepted",
                    "reviewer": "考据师D",
                    "reviewed_at": "2026-04-16T12:00:00",
                    "decision_basis": "经文段落原文比对确认",
                },
            ],
        }
        result = normalize_observe_philology_assets(raw)
        chains = result["evidence_chains"]
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["review_status"], "accepted")
        self.assertEqual(chains[0]["reviewer"], "考据师D")
        self.assertEqual(chains[0]["decision_basis"], "经文段落原文比对确认")

    def test_unmatched_decision_leaves_evidence_chain_unchanged(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "evidence_chains": [
                {
                    "evidence_chain_id": "ec-020",
                    "claim_type": "authorship_attribution",
                    "claim_statement": "作者为张仲景",
                    "confidence": 0.90,
                    "review_status": "pending",
                },
            ],
            "review_workbench_decisions": [
                {
                    "asset_type": "evidence_chain",
                    "asset_key": "evidence_chain::evidence_chain_id=ec-999|claim_type=wrong|claim_statement=无此条",
                    "review_status": "accepted",
                },
            ],
        }
        result = normalize_observe_philology_assets(raw)
        chains = result["evidence_chains"]
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["review_status"], "pending")

    def test_empty_decisions_leaves_evidence_chains_unchanged(self):
        from src.research.observe_philology import normalize_observe_philology_assets

        raw = {
            "evidence_chains": [
                {
                    "evidence_chain_id": "ec-030",
                    "claim_type": "version_chronology",
                    "claim_statement": "版本甲早于版本乙",
                    "confidence": 0.75,
                    "review_status": "pending",
                },
            ],
            "review_workbench_decisions": [],
        }
        result = normalize_observe_philology_assets(raw)
        chains = result["evidence_chains"]
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["review_status"], "pending")


class TestEvidenceChainUpsertRoundTrip(unittest.TestCase):
    """Verify evidence_chain review decision round-trip via the review_workbench module."""

    def test_upsert_evidence_chain_decision_persists(self):
        from src.research.review_workbench import (
            upsert_observe_review_workbench_artifact_content,
        )

        result = upsert_observe_review_workbench_artifact_content({}, {
            "asset_type": "evidence_chain",
            "asset_key": "evidence_chain::evidence_chain_id=ec-100|claim_type=authorship_attribution",
            "review_status": "accepted",
            "reviewer": "考据审核员",
            "decision_basis": "多版本纪年交叉验证",
        })
        self.assertEqual(result["decision_count"], 1)
        decisions = result["decisions"]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["asset_type"], "evidence_chain")
        self.assertEqual(decisions[0]["review_status"], "accepted")
        self.assertEqual(decisions[0]["reviewer"], "考据审核员")

    def test_upsert_evidence_chain_preserves_audit_trail(self):
        from src.research.review_workbench import (
            upsert_observe_review_workbench_artifact_content,
        )

        v1 = upsert_observe_review_workbench_artifact_content({}, {
            "asset_type": "evidence_chain",
            "asset_key": "evidence_chain::evidence_chain_id=ec-200|claim_type=citation_source",
            "review_status": "pending",
            "reviewer": "初审员",
        })
        v2 = upsert_observe_review_workbench_artifact_content(v1, {
            "asset_type": "evidence_chain",
            "asset_key": "evidence_chain::evidence_chain_id=ec-200|claim_type=citation_source",
            "review_status": "accepted",
            "reviewer": "终审员",
            "decision_basis": "原文比对确认引自《伤寒论》",
        })
        self.assertEqual(v2["decision_count"], 1)
        decision = v2["decisions"][0]
        self.assertEqual(decision["review_status"], "accepted")
        self.assertEqual(decision["reviewer"], "终审员")
        self.assertIsInstance(decision.get("decision_history"), list)
        self.assertGreaterEqual(len(decision["decision_history"]), 1)
        self.assertEqual(decision["decision_history"][0]["review_status"], "pending")
        self.assertEqual(decision["decision_history"][0]["reviewer"], "初审员")


class TestReviewableAssetTypes(unittest.TestCase):
    """Verify evidence_chain is registered in _REVIEWABLE_ASSET_TYPES."""

    def test_evidence_chain_in_reviewable_types(self):
        from src.research.review_workbench import _REVIEWABLE_ASSET_TYPES

        self.assertIn("evidence_chain", _REVIEWABLE_ASSET_TYPES)

    def test_evidence_chain_optional_fields_present(self):
        from src.research.review_workbench import _REVIEWABLE_OPTIONAL_FIELDS

        self.assertIn("evidence_chain_id", _REVIEWABLE_OPTIONAL_FIELDS)
        self.assertIn("claim_type", _REVIEWABLE_OPTIONAL_FIELDS)
        self.assertIn("claim_statement", _REVIEWABLE_OPTIONAL_FIELDS)
        self.assertIn("judgment_type", _REVIEWABLE_OPTIONAL_FIELDS)


if __name__ == "__main__":
    unittest.main()
