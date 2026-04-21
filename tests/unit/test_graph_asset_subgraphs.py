from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.research.graph_assets import (
    build_evidence_subgraph,
    build_graph_assets_payload,
    build_hypothesis_subgraph,
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
        "summary": {"evidence_record_count": 1, "claim_count": 1, "linked_claim_count": 1},
    }


class TestHypothesisGraphAssetBuilder(unittest.TestCase):
    def test_hypothesis_subgraph_has_nodes_and_edges(self):
        payload = build_hypothesis_subgraph(
            "cycle-001",
            [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A", "source_entities": ["黄芪", "补气"]}],
        )
        self.assertGreater(payload["node_count"], 0)
        self.assertGreater(payload["edge_count"], 0)

    def test_hypothesis_subgraph_contains_hypothesis_node(self):
        payload = build_hypothesis_subgraph("cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A"}])
        labels = {node["label"] for node in payload["nodes"]}
        self.assertIn("Hypothesis", labels)

    def test_hypothesis_subgraph_deduplicates_entities(self):
        payload = build_hypothesis_subgraph(
            "cycle-001",
            [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A", "source_entities": ["黄芪", "黄芪"]}],
        )
        entity_nodes = [node for node in payload["nodes"] if node["label"] == "Entity"]
        self.assertEqual(len(entity_nodes), 1)

    def test_hypothesis_subgraph_summary_tracks_count(self):
        payload = build_hypothesis_subgraph("cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A"}])
        self.assertEqual(payload["summary"]["hypothesis_count"], 1)

    def test_graph_assets_payload_contains_summary(self):
        payload = build_graph_assets_payload(hypothesis_subgraph={"node_count": 2, "edge_count": 1})
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
        protocol["claims"] = [{
            "claim_id": "claim-2",
            "source_entity": "黄芪",
            "target_entity": "补气",
            "relation_type": "treats",
            "confidence": 0.7,
            "evidence_ids": [],
        }]
        payload = build_evidence_subgraph("cycle-001", protocol)
        support_edges = [edge for edge in payload["edges"] if edge["relationship_type"] == "EVIDENCE_FOR"]
        self.assertEqual(len(support_edges), 1)

    def test_claim_node_contains_derived_claim_text(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        claim_node = next(node for node in payload["nodes"] if node["label"] == "EvidenceClaim")
        self.assertIn("黄芪", claim_node["properties"]["claim_text"])

    def test_claim_endpoints_emit_entity_nodes(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        entity_nodes = [node for node in payload["nodes"] if node["label"] == "Entity"]
        self.assertGreaterEqual(len(entity_nodes), 2)

    def test_evidence_edge_keeps_provenance_properties(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        evidence_for_edge = next(edge for edge in payload["edges"] if edge["relationship_type"] == "EVIDENCE_FOR")
        self.assertEqual(evidence_for_edge["properties"]["version_lineage_key"], "vl-1")
        self.assertEqual(evidence_for_edge["properties"]["witness_key"], "w-1")

    def test_evidence_subgraph_summary_counts_records_and_claims(self):
        payload = build_evidence_subgraph("cycle-001", _sample_evidence_protocol())
        self.assertEqual(payload["summary"]["evidence_record_count"], 1)
        self.assertEqual(payload["summary"]["claim_count"], 1)

    def test_analyze_phase_emits_evidence_subgraph(self):
        mixin = _AnalyzeMixin(_FakeAnalyzePipeline())
        cycle = _FakeCycle()
        with patch("src.research.phases.analyze_phase.build_evidence_protocol", return_value=_sample_evidence_protocol()):
            result = mixin.execute_analyze_phase(cycle, {"analysis_records": [{"formula": "黄芪汤", "syndrome": "气虚", "herbs": ["黄芪"]}]})
        graph_assets = result["results"]["graph_assets"]
        self.assertIn("evidence_subgraph", graph_assets)
        self.assertGreater(graph_assets["evidence_subgraph"]["node_count"], 0)


class TestGraphAssetProjection(unittest.TestCase):
    def _make_orchestrator(self):
        from src.research.phase_orchestrator import PhaseOrchestrator

        orchestrator = PhaseOrchestrator.__new__(PhaseOrchestrator)
        orchestrator.pipeline = SimpleNamespace(logger=MagicMock())
        return orchestrator

    def test_project_cycle_to_neo4j_reports_hypothesis_and_evidence_counts(self):
        orchestrator = self._make_orchestrator()
        cycle = _FakeCycle(
            phase_executions={
                _Phase.HYPOTHESIS: {"result": {"phase": "hypothesis", "results": {"graph_assets": build_graph_assets_payload(hypothesis_subgraph=build_hypothesis_subgraph("cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A", "source_entities": ["黄芪"]}]))}}},
                _Phase.ANALYZE: {"result": {"phase": "analyze", "results": {"graph_assets": build_graph_assets_payload(evidence_subgraph=build_evidence_subgraph("cycle-001", _sample_evidence_protocol()))}}},
            }
        )

        class _Txn:
            def __init__(self):
                self.nodes = []
                self.edges = []

            def neo4j_batch_nodes(self, nodes):
                self.nodes.extend(nodes)

            def neo4j_batch_edges(self, edges):
                self.edges.extend(edges)

        txn = _Txn()
        report = orchestrator._project_cycle_to_neo4j(
            neo4j_driver=MagicMock(),
            cycle=cycle,
            session_record={"current_phase": "analyze"},
            phase_records={"hypothesis": {"id": "phase-h"}, "analyze": {"id": "phase-a"}},
            artifact_records=[],
            observe_documents=[],
            transaction=txn,
        )
        self.assertGreater(report["hypothesis_node_count"], 0)
        self.assertGreater(report["evidence_node_count"], 0)
        self.assertGreater(report["hypothesis_edge_count"], 0)
        self.assertGreater(report["evidence_edge_count"], 0)

    def test_project_cycle_to_neo4j_raises_when_transaction_graph_write_fails(self):
        orchestrator = self._make_orchestrator()
        cycle = _FakeCycle(
            phase_executions={
                _Phase.HYPOTHESIS: {"result": {"phase": "hypothesis", "results": {"graph_assets": build_graph_assets_payload(hypothesis_subgraph=build_hypothesis_subgraph("cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A", "source_entities": ["黄芪"]}]))}}},
            }
        )

        class _FailTxn:
            def neo4j_batch_nodes(self, _nodes):
                raise RuntimeError("neo4j write failed")

            def neo4j_batch_edges(self, _edges):
                return None

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
                _Phase.HYPOTHESIS: {"result": {"phase": "hypothesis", "results": {"graph_assets": build_graph_assets_payload(hypothesis_subgraph=build_hypothesis_subgraph("cycle-001", [{"hypothesis_id": "hyp-1", "title": "A", "statement": "A", "source_entities": ["黄芪"]}]))}}},
            }
        )

        class _Txn:
            def __init__(self):
                self.edges = []

            def neo4j_batch_nodes(self, _nodes):
                return None

            def neo4j_batch_edges(self, edges):
                self.edges.extend(edges)

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
        relationship_types = {edge[0].relationship_type for edge in txn.edges}
        self.assertIn("HAS_HYPOTHESIS", relationship_types)


if __name__ == "__main__":
    unittest.main()