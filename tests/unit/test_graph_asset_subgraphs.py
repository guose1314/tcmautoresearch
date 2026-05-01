from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.research.graph_asset_contract import (
    MANIFESTATION_SOURCE_STRUCTURED,
    PATHOGENESIS_PROPERTY_TYPE,
    SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION,
    EfficacyNodeContract,
    FormulaComponentNodeContract,
    FormulaProvenanceEdgeContract,
    HerbProvenanceEdgeContract,
    PathogenesisNodeContract,
    SymptomNodeContract,
)
from src.research.graph_assets import (
    build_evidence_subgraph,
    build_graph_assets_payload,
    build_hypothesis_subgraph,
    build_philology_subgraph,
)
from src.research.phases.analyze_phase import AnalyzePhaseMixin
from src.research.phases.hypothesis_phase import HypothesisPhaseMixin


class _Phase(Enum):
    OBSERVE = "observe"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EXPERIMENT_EXECUTION = "experiment_execution"
    ANALYZE = "analyze"


@dataclass
class _FakeCycle:
    cycle_id: str = "cycle-001"
    cycle_name: str = "test cycle"
    description: str = "test description"
    research_objective: str = "验证黄芪补气假说"
    research_scope: str = "中医方药研究"
    started_at: str = ""
    completed_at: str = ""
    duration: float = 0.0
    phase_executions: Dict[Any, Dict[str, Any]] = field(default_factory=dict)
    status: Any = field(default_factory=lambda: SimpleNamespace(value="completed"))
    metadata: Dict[str, Any] = field(default_factory=dict)


class _FakeHypothesisEngine:
    def execute(self, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "completed",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp-1",
                    "title": "黄芪补气增强免疫",
                    "statement": "黄芪可能通过补气机制改善免疫功能",
                    "domain": "herb_research",
                    "confidence": 0.83,
                    "status": "draft",
                    "validation_plan": "检索现代实验与古籍方解证据",
                    "source_entities": ["黄芪", "补气"],
                    "supporting_signals": ["古籍多处记载补气"],
                    "contradiction_signals": ["现代证据有限"],
                    "methodology_tag": "evidence_based",
                    "evidence_grade": "C",
                }
            ],
            "metadata": {},
        }


class _FakeHypothesisPipeline:
    ResearchPhase = _Phase

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.hypothesis_engine = _FakeHypothesisEngine()
        self._learning_phase_manifests: list[Dict[str, Any]] = []

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._learning_phase_manifests.append(manifest)


class _HypothesisMixin(HypothesisPhaseMixin):
    def __init__(self, pipeline: _FakeHypothesisPipeline):
        self.pipeline = pipeline

    def _merge_reasoning_summaries(self, summaries):
        return summaries[0] if summaries else {}

    def _deduplicate_relationships(self, items):
        return list(items)


class _FakeAnalysisPort:
    def __init__(self):
        self.create_reasoning_engine = MagicMock(side_effect=RuntimeError("no engine"))


class _FakeAnalyzePipeline:
    ResearchPhase = _Phase

    def __init__(self):
        self.config: Dict[str, Any] = {}
        self.logger = MagicMock()
        self.analysis_port = _FakeAnalysisPort()
        self._learning_phase_manifests: list[Dict[str, Any]] = []

    def register_phase_learning_manifest(self, manifest: Dict[str, Any]) -> None:
        self._learning_phase_manifests.append(manifest)


class _AnalyzeMixin(AnalyzePhaseMixin):
    _RELATION_SOURCE_PRIORITY = {
        "observe_reasoning_engine": 3,
        "observe_semantic_graph": 2,
        "pipeline_hypothesis_context": 1,
    }

    def __init__(self, pipeline: _FakeAnalyzePipeline):
        self.pipeline = pipeline


def _sample_evidence_protocol() -> Dict[str, Any]:
    return {
        "contract_version": "evidence-claim-v2",
        "phase_origin": "analyze",
        "evidence_records": [
            {
                "evidence_id": "ev-1",
                "source_entity": "黄芪",
                "target_entity": "补气",
                "relation_type": "treats",
                "confidence": 0.9,
                "evidence_grade": "moderate",
                "source_type": "literature",
                "source_ref": "doc-1",
                "document_title": "本草纲目",
                "work_title": "本草纲目",
                "version_lineage_key": "vl-1",
                "witness_key": "w-1",
                "excerpt": "黄芪，补气。",
                "title": "本草纲目",
            }
        ],
        "claims": [
            {
                "claim_id": "claim-1",
                "source_entity": "黄芪",
                "target_entity": "补气",
                "relation_type": "treats",
                "confidence": 0.88,
                "support_count": 1,
                "evidence_ids": ["ev-1"],
            }
        ],
        "evidence_grade_summary": {"overall_grade": "moderate"},
        "summary": {
            "evidence_record_count": 1,
            "claim_count": 1,
            "linked_claim_count": 1,
        },
    }


def _sample_observe_philology() -> Dict[str, Any]:
    return {
        "catalog_summary": {
            "summary": {
                "catalog_document_count": 1,
                "version_lineage_count": 1,
                "witness_count": 1,
            },
            "documents": [
                {
                    "document_title": "补中益气汤宋本",
                    "document_urn": "doc:1",
                    "source_type": "local",
                    "catalog_id": "local:catalog:1",
                    "work_title": "补中益气汤",
                    "fragment_title": "补中益气汤",
                    "work_fragment_key": "补中益气汤|补中益气汤",
                    "version_lineage_key": "补中益气汤|补中益气汤|明|李时珍|宋本",
                    "witness_key": "local:doc:1",
                    "dynasty": "明",
                    "author": "李时珍",
                    "edition": "宋本",
                    "exegesis_entries": [
                        {
                            "canonical": "黄芪",
                            "label": "本草药名",
                            "definition": "补气固表",
                            "definition_source": "structured_tcm_knowledge",
                            "semantic_scope": "本草药名",
                            "observed_forms": ["黃芪"],
                            "configured_variants": ["黃耆"],
                            "sources": ["structured_tcm_knowledge"],
                            "source_refs": [
                                "TCMRelationshipDefinitions.HERB_EFFICACY_MAP"
                            ],
                            "notes": ["结构化释义"],
                            "dynasty_usage": ["明"],
                            "disambiguation_basis": ["structured_tcm_knowledge"],
                            "review_status": "pending",
                            "needs_manual_review": True,
                            "exegesis_notes": "「黄芪」释义来源：结构化知识库",
                        },
                        {
                            "canonical": "补中益气汤",
                            "label": "方剂名",
                            "definition": "补中益气汤为方剂名，常见组成包含黄芪、人参与白术",
                            "definition_source": "structured_tcm_knowledge",
                            "semantic_scope": "方剂名",
                            "sources": ["structured_tcm_knowledge"],
                            "source_refs": [
                                "TCMRelationshipDefinitions.FORMULA_COMPOSITIONS"
                            ],
                            "review_status": "pending",
                            "needs_manual_review": True,
                            "exegesis_notes": "「补中益气汤」释义来源：结构化知识库",
                        },
                        {
                            "canonical": "气虚证",
                            "label": "证候术语",
                            "definition": "气虚证指元气不足，常见表现为少气懒言与神疲乏力",
                            "definition_source": "structured_tcm_knowledge",
                            "semantic_scope": "证候术语",
                            "sources": ["structured_tcm_knowledge"],
                            "source_refs": [
                                "TCMRelationshipDefinitions.SYNDROME_DEFINITIONS"
                            ],
                            "review_status": "pending",
                            "needs_manual_review": True,
                            "exegesis_notes": "「气虚证」释义来源：结构化知识库",
                        },
                    ],
                }
            ],
            "version_lineages": [
                {
                    "version_lineage_key": "补中益气汤|补中益气汤|明|李时珍|宋本",
                    "work_fragment_key": "补中益气汤|补中益气汤",
                    "work_title": "补中益气汤",
                    "fragment_title": "补中益气汤",
                    "dynasty": "明",
                    "author": "李时珍",
                    "edition": "宋本",
                    "witnesses": [
                        {
                            "title": "补中益气汤宋本",
                            "urn": "doc:1",
                            "source_type": "local",
                            "catalog_id": "local:catalog:1",
                            "witness_key": "local:doc:1",
                        }
                    ],
                }
            ],
        },
        "fragment_candidates": [
            {
                "fragment_candidate_id": "frag-1",
                "candidate_kind": "fragment_candidates",
                "fragment_title": "佚文甲",
                "document_title": "补中益气汤宋本",
                "document_urn": "doc:1",
                "source_type": "local",
                "work_title": "补中益气汤",
                "version_lineage_key": "补中益气汤|补中益气汤|明|李时珍|宋本",
                "witness_key": "local:doc:1",
                "match_score": 0.86,
                "review_status": "pending",
                "needs_manual_review": True,
                "reconstruction_basis": "与明本异文比对后推断为佚文",
                "source_refs": ["collation:补中益气汤|补中益气汤|明|李时珍|宋本"],
            }
        ],
        "lost_text_candidates": [],
        "citation_source_candidates": [],
        "evidence_chains": [
            {
                "evidence_chain_id": "chronology::补中益气汤|补中益气汤|明|李时珍|宋本::补中益气汤宋本::补中益气汤明本",
                "claim_type": "version_chronology",
                "claim_statement": "版本谱系中补中益气汤明本可能较补中益气汤宋本为增补本",
                "confidence": 0.72,
                "basis_summary": "校勘显示明本新增内容更多",
                "review_status": "pending",
                "needs_manual_review": True,
                "version_lineage_key": "补中益气汤|补中益气汤|明|李时珍|宋本",
                "witness_title": "补中益气汤宋本",
                "source_refs": ["collation:补中益气汤|补中益气汤|明|李时珍|宋本"],
            }
        ],
        "conflict_claims": [
            {
                "claim_id": "conflict-1",
                "claim_statement": "补血汤作者归属存在分歧",
                "confidence": 0.51,
                "basis_summary": "目录学记录存在不同作者标注",
                "review_status": "pending",
                "needs_manual_review": True,
                "work_title": "补血汤",
                "source_refs": ["catalog:补血汤"],
            }
        ],
    }


class TestHypothesisGraphAssetBuilder(unittest.TestCase):
    def test_hypothesis_subgraph_has_nodes_and_edges(self):
        payload = build_hypothesis_subgraph(
            "cycle-001",
            [
                {
                    "hypothesis_id": "hyp-1",
                    "title": "A",
                    "statement": "A",
                    "source_entities": ["黄芪", "补气"],
                }
            ],
        )
        self.assertGreater(payload["node_count"], 0)
        self.assertGreater(payload["edge_count"], 0)

    def test_hypothesis_subgraph_contains_hypothesis_node(self):
        payload = build_hypothesis_subgraph(
            "cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A"}]
        )
        labels = {node["label"] for node in payload["nodes"]}
        self.assertIn("Hypothesis", labels)

    def test_hypothesis_subgraph_deduplicates_entities(self):
        payload = build_hypothesis_subgraph(
            "cycle-001",
            [
                {
                    "hypothesis_id": "hyp-1",
                    "title": "A",
                    "statement": "A",
                    "source_entities": ["黄芪", "黄芪"],
                }
            ],
        )
        entity_nodes = [node for node in payload["nodes"] if node["label"] == "Entity"]
        self.assertEqual(len(entity_nodes), 1)

    def test_hypothesis_subgraph_summary_tracks_count(self):
        payload = build_hypothesis_subgraph(
            "cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A"}]
        )
        self.assertEqual(payload["summary"]["hypothesis_count"], 1)

    def test_graph_assets_payload_contains_summary(self):
        payload = build_graph_assets_payload(
            hypothesis_subgraph={"node_count": 2, "edge_count": 1}
        )
        self.assertIn("summary", payload)
        self.assertEqual(payload["summary"]["hypothesis_subgraph"]["node_count"], 2)

    def test_hypothesis_phase_emits_graph_assets(self):
        mixin = _HypothesisMixin(_FakeHypothesisPipeline())
        result = mixin.execute_hypothesis_phase(_FakeCycle(), {})
        graph_assets = result["results"]["graph_assets"]
        self.assertIn("hypothesis_subgraph", graph_assets)
        self.assertGreater(graph_assets["hypothesis_subgraph"]["node_count"], 0)
        self.assertGreater(graph_assets["hypothesis_subgraph"]["edge_count"], 0)


class TestEvidenceGraphAssetBuilder(unittest.TestCase):
    def test_evidence_subgraph_has_evidence_and_claim_nodes(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        labels = {node["label"] for node in payload["nodes"]}
        self.assertIn("Evidence", labels)
        self.assertIn("EvidenceClaim", labels)

    def test_claim_links_back_to_evidence_node(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        relation_types = {edge["relationship_type"] for edge in payload["edges"]}
        self.assertIn("EVIDENCE_FOR", relation_types)
        self.assertIn("SUPPORTED_BY", relation_types)

    def test_claim_without_explicit_evidence_ids_can_be_inferred(self):
        protocol = _sample_evidence_protocol()
        protocol["claims"] = [
            {
                "claim_id": "claim-2",
                "source_entity": "黄芪",
                "target_entity": "补气",
                "relation_type": "treats",
                "confidence": 0.7,
                "evidence_ids": [],
            }
        ]
        payload = build_evidence_subgraph("cycle-001", protocol)
        support_edges = [
            edge
            for edge in payload["edges"]
            if edge["relationship_type"] == "EVIDENCE_FOR"
        ]
        self.assertEqual(len(support_edges), 1)

    def test_claim_node_contains_derived_claim_text(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        claim_node = next(
            node for node in payload["nodes"] if node["label"] == "EvidenceClaim"
        )
        self.assertIn("黄芪", claim_node["properties"]["claim_text"])

    def test_claim_endpoints_emit_entity_nodes(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        entity_nodes = [node for node in payload["nodes"] if node["label"] == "Entity"]
        self.assertGreaterEqual(len(entity_nodes), 2)

    def test_evidence_edge_keeps_provenance_properties(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        evidence_for_edge = next(
            edge
            for edge in payload["edges"]
            if edge["relationship_type"] == "EVIDENCE_FOR"
        )
        self.assertEqual(evidence_for_edge["properties"]["version_lineage_key"], "vl-1")
        self.assertEqual(evidence_for_edge["properties"]["witness_key"], "w-1")

    def test_evidence_subgraph_summary_counts_records_and_claims(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        self.assertEqual(payload["summary"]["evidence_record_count"], 1)
        self.assertEqual(payload["summary"]["claim_count"], 1)

    def test_analyze_phase_emits_evidence_subgraph(self):
        mixin = _AnalyzeMixin(_FakeAnalyzePipeline())
        cycle = _FakeCycle()
        with patch(
            "src.research.phases.analyze_phase.build_evidence_protocol",
            return_value=_sample_evidence_protocol(),
        ):
            result = mixin.execute_analyze_phase(
                cycle,
                {
                    "analysis_records": [
                        {"formula": "黄芪汤", "syndrome": "气虚", "herbs": ["黄芪"]}
                    ]
                },
            )
        graph_assets = result["results"]["graph_assets"]
        self.assertIn("evidence_subgraph", graph_assets)
        self.assertGreater(graph_assets["evidence_subgraph"]["node_count"], 0)


class TestPhilologyGraphAssetBuilder(unittest.TestCase):
    def test_philology_subgraph_contains_catalog_lineage_witness_and_claim_nodes(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        labels = {node["label"] for node in payload["nodes"]}
        self.assertIn("Catalog", labels)
        self.assertIn("VersionLineage", labels)
        self.assertIn("VersionWitness", labels)
        self.assertIn("EvidenceClaim", labels)
        self.assertIn("ExegesisEntry", labels)
        self.assertIn("FragmentCandidate", labels)
        self.assertIn("Herb", labels)
        self.assertIn("Formula", labels)
        self.assertIn("Syndrome", labels)
        self.assertIn("Symptom", labels)
        self.assertIn("Efficacy", labels)
        self.assertIn("Property", labels)

    def test_philology_subgraph_contains_witness_and_claim_edges(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        relation_types = {edge["relationship_type"] for edge in payload["edges"]}
        self.assertIn("CATALOGED_IN", relation_types)
        self.assertIn("WITNESSED_BY", relation_types)
        self.assertIn("BELONGS_TO_LINEAGE", relation_types)
        self.assertIn("EVIDENCED_BY", relation_types)
        self.assertIn("HAS_EXEGESIS", relation_types)
        self.assertIn("HAS_FRAGMENT_CANDIDATE", relation_types)
        self.assertIn("EXPLAINS_HERB", relation_types)
        self.assertIn("EXPLAINS_FORMULA", relation_types)
        self.assertIn("EXPLAINS_SYNDROME", relation_types)
        self.assertIn("EXPLAINS_EFFICACY", relation_types)
        self.assertIn("EXPLAINS_FORMULA_COMPONENT", relation_types)
        self.assertIn("EXPLAINS_PATHOGENESIS", relation_types)
        self.assertIn("EXPLAINS_SYMPTOM", relation_types)
        self.assertIn("HAS_EFFICACY", relation_types)
        self.assertIn("SYMPTOM_OF", relation_types)
        self.assertIn("SOVEREIGN", relation_types)

    def test_philology_subgraph_summary_tracks_claims(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        self.assertEqual(payload["summary"]["catalog_count"], 1)
        self.assertEqual(payload["summary"]["version_lineage_count"], 1)
        self.assertEqual(payload["summary"]["exegesis_entry_count"], 3)
        self.assertEqual(payload["summary"]["fragment_candidate_count"], 1)
        self.assertEqual(payload["summary"]["evidence_chain_count"], 1)
        self.assertEqual(payload["summary"]["conflict_claim_count"], 1)

    def test_exegesis_node_links_to_domain_terms_with_explicit_semantic_edges(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        exegesis_nodes = [
            node for node in payload["nodes"] if node["label"] == "ExegesisEntry"
        ]
        self.assertEqual(len(exegesis_nodes), 3)
        semantic_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "ExegesisEntry"
            and edge["relationship_type"]
            in {"EXPLAINS_HERB", "EXPLAINS_FORMULA", "EXPLAINS_SYNDROME"}
        ]
        relation_types = {edge["relationship_type"] for edge in semantic_edges}
        self.assertEqual(
            relation_types, {"EXPLAINS_HERB", "EXPLAINS_FORMULA", "EXPLAINS_SYNDROME"}
        )
        herb_edge = next(
            edge
            for edge in semantic_edges
            if edge["relationship_type"] == "EXPLAINS_HERB"
        )
        formula_edge = next(
            edge
            for edge in semantic_edges
            if edge["relationship_type"] == "EXPLAINS_FORMULA"
        )
        self.assertEqual(
            set(herb_edge["properties"]).intersection(
                HerbProvenanceEdgeContract.required_fields
            ),
            HerbProvenanceEdgeContract.required_fields,
        )
        self.assertEqual(herb_edge["properties"]["herb_canonical"], "黄芪")
        self.assertEqual(herb_edge["properties"]["source_herb"], "黄芪")
        self.assertTrue(herb_edge["properties"]["source_exegesis_id"])
        self.assertEqual(
            set(formula_edge["properties"]).intersection(
                FormulaProvenanceEdgeContract.required_fields
            ),
            FormulaProvenanceEdgeContract.required_fields,
        )
        self.assertEqual(formula_edge["properties"]["formula_canonical"], "补中益气汤")
        self.assertEqual(formula_edge["properties"]["source_formula"], "补中益气汤")
        self.assertTrue(formula_edge["properties"]["source_exegesis_id"])

    def test_herb_exegesis_projects_efficacy_nodes(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        efficacy_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "ExegesisEntry"
            and edge["relationship_type"] == "EXPLAINS_EFFICACY"
        ]
        herb_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "Herb"
            and edge["relationship_type"] == "HAS_EFFICACY"
        ]
        self.assertGreaterEqual(len(efficacy_edges), 1)
        self.assertGreaterEqual(len(herb_edges), 1)
        efficacy_nodes = [
            node
            for node in payload["nodes"]
            if node["label"] == "Efficacy"
            and node["properties"].get("type") == EfficacyNodeContract.node_type
        ]
        self.assertGreaterEqual(len(efficacy_nodes), 1)
        self.assertEqual(
            set(efficacy_nodes[0]["properties"]).intersection(
                EfficacyNodeContract.required_fields
            ),
            EfficacyNodeContract.required_fields,
        )
        self.assertEqual(efficacy_nodes[0]["properties"]["herb_canonical"], "黄芪")
        self.assertEqual(efficacy_nodes[0]["properties"]["source_herb"], "黄芪")
        self.assertTrue(efficacy_nodes[0]["properties"]["source_exegesis_id"])

    def test_formula_exegesis_projects_component_herbs(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        composition_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "ExegesisEntry"
            and edge["relationship_type"] == "EXPLAINS_FORMULA_COMPONENT"
        ]
        role_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "Formula"
            and edge["relationship_type"]
            in {"SOVEREIGN", "MINISTER", "ASSISTANT", "ENVOY"}
        ]
        self.assertGreaterEqual(len(composition_edges), 1)
        self.assertGreaterEqual(len(role_edges), 1)
        component_nodes = [
            node
            for node in payload["nodes"]
            if node["label"] == "Herb"
            and node["properties"].get("type") == FormulaComponentNodeContract.node_type
        ]
        self.assertGreaterEqual(len(component_nodes), 1)
        self.assertEqual(
            set(component_nodes[0]["properties"]).intersection(
                FormulaComponentNodeContract.required_fields
            ),
            FormulaComponentNodeContract.required_fields,
        )
        self.assertEqual(
            component_nodes[0]["properties"]["formula_canonical"], "补中益气汤"
        )
        self.assertEqual(
            component_nodes[0]["properties"]["source_formula"], "补中益气汤"
        )
        self.assertTrue(component_nodes[0]["properties"]["source_exegesis_id"])

    def test_syndrome_exegesis_projects_pathogenesis_node(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        pathogenesis_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "ExegesisEntry"
            and edge["relationship_type"] == "EXPLAINS_PATHOGENESIS"
        ]
        pathogenesis_nodes = [
            node
            for node in payload["nodes"]
            if node["label"] == "Property"
            and node["properties"].get("type") == PATHOGENESIS_PROPERTY_TYPE
        ]
        self.assertEqual(len(pathogenesis_edges), 1)
        self.assertEqual(len(pathogenesis_nodes), 1)
        self.assertTrue(pathogenesis_nodes[0]["properties"]["source_exegesis_id"])
        self.assertEqual(
            pathogenesis_nodes[0]["properties"]["syndrome_canonical"], "气虚证"
        )
        self.assertEqual(
            pathogenesis_nodes[0]["properties"]["source_syndrome"], "气虚证"
        )
        self.assertEqual(
            set(pathogenesis_nodes[0]["properties"]).intersection(
                PathogenesisNodeContract.required_fields
            ),
            PathogenesisNodeContract.required_fields,
        )

    def test_syndrome_exegesis_projects_symptom_nodes(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        symptom_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "ExegesisEntry"
            and edge["relationship_type"] == "EXPLAINS_SYMPTOM"
        ]
        symptom_of_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "Symptom"
            and edge["relationship_type"] == "SYMPTOM_OF"
        ]
        symptom_nodes = [
            node for node in payload["nodes"] if node["label"] == "Symptom"
        ]
        self.assertGreaterEqual(len(symptom_edges), 1)
        self.assertGreaterEqual(len(symptom_of_edges), 1)
        self.assertGreaterEqual(len(symptom_nodes), 1)
        self.assertEqual(
            symptom_nodes[0]["properties"]["symptom_category"],
            SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION,
        )
        self.assertEqual(
            symptom_nodes[0]["properties"]["manifestation_source"],
            MANIFESTATION_SOURCE_STRUCTURED,
        )
        self.assertEqual(symptom_nodes[0]["properties"]["syndrome_canonical"], "气虚证")
        self.assertEqual(symptom_nodes[0]["properties"]["source_syndrome"], "气虚证")
        self.assertTrue(symptom_nodes[0]["properties"]["source_exegesis_id"])
        self.assertEqual(
            set(symptom_nodes[0]["properties"]).intersection(
                SymptomNodeContract.required_fields
            ),
            SymptomNodeContract.required_fields,
        )

    def test_fragment_candidate_links_to_witness(self):
        payload = build_philology_subgraph("cycle-001", _sample_observe_philology())
        derived_edges = [
            edge
            for edge in payload["edges"]
            if edge["source_label"] == "FragmentCandidate"
            and edge["relationship_type"] == "DERIVED_FROM"
        ]
        self.assertGreaterEqual(len(derived_edges), 1)


class TestGraphAssetProjection(unittest.TestCase):
    def _make_orchestrator(self):
        from src.research.phase_orchestrator import PhaseOrchestrator

        orchestrator = PhaseOrchestrator.__new__(PhaseOrchestrator)
        orchestrator.pipeline = SimpleNamespace(logger=MagicMock())
        return orchestrator

    class _OutboxSession:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

    def test_project_cycle_to_neo4j_reports_hypothesis_and_evidence_counts(self):
        orchestrator = self._make_orchestrator()
        cycle = _FakeCycle(
            phase_executions={
                _Phase.HYPOTHESIS: {
                    "result": {
                        "phase": "hypothesis",
                        "results": {
                            "graph_assets": build_graph_assets_payload(
                                hypothesis_subgraph=build_hypothesis_subgraph(
                                    "cycle-001",
                                    [
                                        {
                                            "hypothesis_id": "hyp-1",
                                            "title": "A",
                                            "statement": "A",
                                            "source_entities": ["黄芪"],
                                        }
                                    ],
                                )
                            )
                        },
                    }
                },
                _Phase.ANALYZE: {
                    "result": {
                        "phase": "analyze",
                        "results": {
                            "graph_assets": build_graph_assets_payload(
                                evidence_subgraph=build_evidence_subgraph(
                                    "cycle-001", _sample_evidence_protocol()
                                )
                            )
                        },
                    }
                },
                _Phase.OBSERVE: {
                    "result": {
                        "phase": "observe",
                        "results": {
                            "graph_assets": build_graph_assets_payload(
                                philology_subgraph=build_philology_subgraph(
                                    "cycle-001", _sample_observe_philology()
                                )
                            )
                        },
                    }
                },
            }
        )

        class _Txn:
            def __init__(self):
                self.pg_session = TestGraphAssetProjection._OutboxSession()

            def neo4j_batch_nodes(self, nodes):
                raise AssertionError("transaction path must enqueue graph outbox")

            def neo4j_batch_edges(self, edges):
                raise AssertionError("transaction path must enqueue graph outbox")

        txn = _Txn()
        report = orchestrator._project_cycle_to_neo4j(
            neo4j_driver=MagicMock(),
            cycle=cycle,
            session_record={"current_phase": "analyze"},
            phase_records={
                "hypothesis": {"id": "phase-h"},
                "analyze": {"id": "phase-a"},
            },
            artifact_records=[],
            observe_documents=[],
            transaction=txn,
        )
        self.assertGreater(report["hypothesis_node_count"], 0)
        self.assertGreater(report["evidence_node_count"], 0)
        self.assertGreater(report["hypothesis_edge_count"], 0)
        self.assertGreater(report["evidence_edge_count"], 0)
        self.assertGreater(report["philology_node_count"], 0)
        self.assertGreater(report["philology_edge_count"], 0)
        self.assertGreater(report["philology_traceable_node_count"], 0)
        self.assertGreater(report["philology_traceable_edge_count"], 0)
        self.assertGreater(report["herb_provenance_edge_count"], 0)
        self.assertGreater(report["formula_provenance_edge_count"], 0)
        self.assertGreater(report["efficacy_traceable_node_count"], 0)
        self.assertGreater(report["formula_component_traceable_node_count"], 0)
        self.assertGreater(report["symptom_traceable_node_count"], 0)
        self.assertGreater(report["pathogenesis_traceable_node_count"], 0)
        self.assertGreater(report["exegesis_term_node_count"], 0)
        self.assertGreater(report["textual_evidence_chain_node_count"], 0)
        self.assertEqual(report["status"], "queued")
        self.assertEqual(report["graph_projection_mode"], "outbox")
        self.assertEqual(len(txn.pg_session.rows), 1)
        payload = txn.pg_session.rows[0].payload
        self.assertEqual(payload["contract_version"], "graph-projection-outbox-v1")
        self.assertEqual(payload["cycle_id"], "cycle-001")
        self.assertGreater(len(payload["graph_payload"]["nodes"]), 0)
        self.assertGreater(len(payload["graph_payload"]["edges"]), 0)

    def test_project_cycle_to_neo4j_raises_when_outbox_enqueue_fails(self):
        orchestrator = self._make_orchestrator()
        cycle = _FakeCycle(
            phase_executions={
                _Phase.HYPOTHESIS: {
                    "result": {
                        "phase": "hypothesis",
                        "results": {
                            "graph_assets": build_graph_assets_payload(
                                hypothesis_subgraph=build_hypothesis_subgraph(
                                    "cycle-001",
                                    [
                                        {
                                            "hypothesis_id": "hyp-1",
                                            "title": "A",
                                            "statement": "A",
                                            "source_entities": ["黄芪"],
                                        }
                                    ],
                                )
                            )
                        },
                    }
                },
            }
        )

        class _FailingOutboxSession:
            def add(self, _row):
                raise RuntimeError("outbox write failed")

        class _FailTxn:
            pg_session = _FailingOutboxSession()

            def neo4j_batch_nodes(self, _nodes):
                raise AssertionError("transaction path must enqueue graph outbox")

            def neo4j_batch_edges(self, _edges):
                raise AssertionError("transaction path must enqueue graph outbox")

        with self.assertRaises(RuntimeError):
            orchestrator._project_cycle_to_neo4j(
                neo4j_driver=MagicMock(),
                cycle=cycle,
                session_record={"current_phase": "hypothesis"},
                phase_records={"hypothesis": {"id": "phase-h"}},
                artifact_records=[],
                observe_documents=[],
                transaction=_FailTxn(),
            )

    def test_project_cycle_to_neo4j_adds_phase_link_edges(self):
        orchestrator = self._make_orchestrator()
        cycle = _FakeCycle(
            phase_executions={
                _Phase.HYPOTHESIS: {
                    "result": {
                        "phase": "hypothesis",
                        "results": {
                            "graph_assets": build_graph_assets_payload(
                                hypothesis_subgraph=build_hypothesis_subgraph(
                                    "cycle-001",
                                    [
                                        {
                                            "hypothesis_id": "hyp-1",
                                            "title": "A",
                                            "statement": "A",
                                            "source_entities": ["黄芪"],
                                        }
                                    ],
                                )
                            )
                        },
                    }
                },
            }
        )

        class _Txn:
            def __init__(self):
                self.pg_session = TestGraphAssetProjection._OutboxSession()

            def neo4j_batch_nodes(self, _nodes):
                raise AssertionError("transaction path must enqueue graph outbox")

            def neo4j_batch_edges(self, edges):
                raise AssertionError("transaction path must enqueue graph outbox")

        txn = _Txn()
        orchestrator._project_cycle_to_neo4j(
            neo4j_driver=MagicMock(),
            cycle=cycle,
            session_record={"current_phase": "hypothesis"},
            phase_records={"hypothesis": {"id": "phase-h"}},
            artifact_records=[],
            observe_documents=[],
            transaction=txn,
        )
        payload = txn.pg_session.rows[0].payload
        relationship_types = {
            edge["relationship_type"] for edge in payload["graph_payload"]["edges"]
        }
        self.assertIn("HAS_HYPOTHESIS", relationship_types)


if __name__ == "__main__":
    unittest.main()
