from __future__ import annotations

import unittest


def _sample_observe_philology() -> dict:
    return {
        "catalog_summary": {
            "documents": [
                {
                    "catalog_id": "cat-001",
                    "document_title": "本草纲目",
                    "work_title": "本草纲目",
                    "document_urn": "urn:doc:1",
                    "version_lineage_key": "lin-001",
                    "witness_key": "wit-001",
                    "exegesis_entries": [
                        {
                            "canonical": "黄芪",
                            "label": "本草药名",
                            "semantic_scope": "herb",
                            "definition": "补气升阳",
                            "review_status": "pending",
                            "needs_manual_review": True,
                        }
                    ],
                }
            ],
            "version_lineages": [
                {
                    "version_lineage_key": "lin-001",
                    "work_title": "本草纲目",
                    "fragment_title": "卷一",
                    "witnesses": [
                        {
                            "witness_key": "wit-001",
                            "catalog_id": "cat-001",
                            "title": "本草纲目",
                        }
                    ],
                }
            ],
        },
        "terminology_standard_table": [
            {
                "document_urn": "urn:doc:1",
                "document_title": "本草纲目",
                "canonical": "黄芪",
                "semantic_scope": "herb",
                "review_status": "accepted",
                "needs_manual_review": False,
                "decision_basis": "expert_review",
            }
        ],
        "fragment_candidates": [
            {
                "fragment_candidate_id": "frag-001",
                "candidate_kind": "fragment_candidates",
                "document_title": "本草纲目",
                "document_urn": "urn:doc:1",
                "witness_key": "wit-001",
                "source_refs": ["ref:frag-001"],
                "review_status": "accepted",
                "needs_manual_review": False,
            }
        ],
        "evidence_chains": [
            {
                "evidence_chain_id": "chain-001",
                "claim_type": "citation_source",
                "claim_statement": "本草纲目引黄芪条文",
                "document_title": "本草纲目",
                "version_lineage_key": "lin-001",
                "witness_key": "wit-001",
                "source_refs": ["ref:frag-001"],
                "review_status": "accepted",
                "needs_manual_review": False,
                "decision_basis": "collation_alignment",
            }
        ],
    }


class TestPhilologyGraphProjection(unittest.TestCase):
    def test_build_philology_subgraph_registers_g3_nodes_and_edges(self):
        from src.research.graph_assets import build_philology_subgraph

        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        labels = {node["label"] for node in payload["nodes"]}
        edge_types = {edge["relationship_type"] for edge in payload["edges"]}

        self.assertIn("Catalog", labels)
        self.assertIn("ExegesisTerm", labels)
        self.assertIn("FragmentCandidate", labels)
        self.assertIn("TextualEvidenceChain", labels)
        self.assertIn("HAS_VERSION", edge_types)
        self.assertIn("ATTESTS_TO", edge_types)
        self.assertIn("INTERPRETS", edge_types)
        self.assertIn("RECONSTRUCTS", edge_types)
        self.assertIn("CITES_FRAGMENT", edge_types)

    def test_exegesis_term_merges_review_fields_from_terminology_table(self):
        from src.research.graph_assets import build_philology_subgraph

        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        exegesis_term = next(node for node in payload["nodes"] if node["label"] == "ExegesisTerm")
        self.assertEqual(exegesis_term["properties"]["review_status"], "accepted")
        self.assertFalse(exegesis_term["properties"]["needs_manual_review"])
        self.assertEqual(exegesis_term["properties"]["decision_basis"], "expert_review")

    def test_exegesis_term_derived_from_terminology_table_when_no_embedded_exegesis_entries(self):
        """历史 observe phase 输出只有 terminology_standard_table、document 无 exegesis_entries 时，
        build_philology_subgraph 仍应产出 ExegesisTerm 节点和 VersionWitness-[ATTESTS_TO]->ExegesisTerm 边。"""
        from src.research.graph_assets import build_philology_subgraph

        # Document deliberately has NO exegesis_entries
        philology = {
            "catalog_summary": {
                "documents": [
                    {
                        "catalog_id": "cat-hist",
                        "document_title": "神农本草经",
                        "work_title": "神农本草经",
                        "document_urn": "urn:doc:hist",
                        "version_lineage_key": "lin-hist",
                        "witness_key": "wit-hist",
                        # no exegesis_entries key at all
                    }
                ],
                "version_lineages": [
                    {
                        "version_lineage_key": "lin-hist",
                        "work_title": "神农本草经",
                        "witnesses": [
                            {"witness_key": "wit-hist", "catalog_id": "cat-hist", "title": "神农本草经"}
                        ],
                    }
                ],
            },
            "terminology_standard_table": [
                {
                    "document_urn": "urn:doc:hist",
                    "document_title": "神农本草经",
                    "canonical": "人参",
                    "semantic_scope": "herb",
                    "review_status": "accepted",
                    "needs_manual_review": False,
                    "decision_basis": "backfill",
                },
                {
                    "document_urn": "urn:doc:hist",
                    "document_title": "神农本草经",
                    "canonical": "甘草",
                    "semantic_scope": "herb",
                    "review_status": "pending",
                    "needs_manual_review": True,
                },
            ],
        }

        payload = build_philology_subgraph("cycle-hist", philology)
        labels = [node["label"] for node in payload["nodes"]]
        edge_types = [edge["relationship_type"] for edge in payload["edges"]]
        exegesis_term_nodes = [node for node in payload["nodes"] if node["label"] == "ExegesisTerm"]

        # Should have produced ExegesisTerm nodes derived from terminology table
        self.assertGreaterEqual(len(exegesis_term_nodes), 2, "Expected ≥2 ExegesisTerm nodes from terminology_standard_table")
        canonical_names = {node["properties"]["canonical"] for node in exegesis_term_nodes}
        self.assertIn("人参", canonical_names)
        self.assertIn("甘草", canonical_names)

        # Must have ATTESTS_TO edges from VersionWitness to ExegesisTerm
        self.assertIn("ATTESTS_TO", edge_types, "Expected VersionWitness-[ATTESTS_TO]->ExegesisTerm edges")
        attests_edges = [e for e in payload["edges"] if e["relationship_type"] == "ATTESTS_TO"]
        self.assertGreaterEqual(len(attests_edges), 2)

        # Verify review fields are carried from terminology rows
        renshen = next(n for n in exegesis_term_nodes if n["properties"]["canonical"] == "人参")
        self.assertEqual(renshen["properties"]["review_status"], "accepted")
        self.assertFalse(renshen["properties"]["needs_manual_review"])
        self.assertEqual(renshen["properties"]["decision_basis"], "backfill")

    def test_observe_philology_helper_returns_standard_graph_assets_payload(self):
        from src.research.observe_philology import build_observe_philology_graph_assets

        payload = build_observe_philology_graph_assets("cycle-001", _sample_observe_philology())
        self.assertIn("philology_subgraph", payload)
        self.assertEqual(payload["philology_subgraph"]["graph_type"], "philology_subgraph")
        self.assertGreater(payload["philology_subgraph"]["summary"]["textual_evidence_chain_count"], 0)


if __name__ == "__main__":
    unittest.main()
