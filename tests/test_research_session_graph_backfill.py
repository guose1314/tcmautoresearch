from __future__ import annotations

from datetime import datetime

from src.infrastructure.persistence import DatabaseManager
from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.research.research_session_graph_backfill import (
    backfill_research_session_nodes,
    backfill_structured_research_graph,
    build_observe_entity_graph_properties,
    build_observe_version_witness_graph_properties,
    build_research_artifact_graph_properties,
    build_research_phase_execution_graph_properties,
    build_research_session_graph_properties,
)


class _FakeNeo4jDriver:
    def __init__(self) -> None:
        self.batches = []
        self.relationship_batches = []

    def batch_create_nodes(self, nodes):
        self.batches.append(list(nodes))
        return True

    def batch_create_relationships(self, edges):
        self.relationship_batches.append(list(edges))
        return True


def test_build_research_session_graph_properties_omits_empty_values():
    payload = build_research_session_graph_properties(
        {
            "cycle_id": "cycle-001",
            "cycle_name": "测试会话",
            "status": "completed",
            "created_at": "2026-04-12T16:45:10",
            "updated_at": None,
            "research_scope": "",
            "duration": 12.5,
        }
    )

    assert payload == {
        "cycle_id": "cycle-001",
        "cycle_name": "测试会话",
        "status": "completed",
        "created_at": "2026-04-12T16:45:10",
        "duration": 12.5,
    }


def test_build_research_phase_execution_graph_properties_omits_empty_values():
    payload = build_research_phase_execution_graph_properties(
        {
            "phase": "observe",
            "status": "completed",
            "cycle_id": "cycle-001",
            "created_at": "2026-04-12T16:45:11",
            "error_detail": "",
            "duration": 3.0,
        }
    )

    assert payload == {
        "phase": "observe",
        "status": "completed",
        "cycle_id": "cycle-001",
        "created_at": "2026-04-12T16:45:11",
        "duration": 3.0,
    }


def test_build_research_artifact_graph_properties_omits_empty_values():
    payload = build_research_artifact_graph_properties(
        {
            "name": "markdown",
            "artifact_type": "paper",
            "cycle_id": "cycle-001",
            "phase_execution_id": "phase-001",
            "created_at": "2026-04-12T16:45:12",
            "updated_at": None,
            "description": "",
            "size_bytes": 0,
        }
    )

    assert payload == {
        "name": "markdown",
        "artifact_type": "paper",
        "cycle_id": "cycle-001",
        "phase_execution_id": "phase-001",
        "created_at": "2026-04-12T16:45:12",
        "size_bytes": 0,
    }


def test_build_observe_entity_graph_properties_omits_empty_values():
    payload = build_observe_entity_graph_properties(
        {
            "id": "entity-001",
            "name": "桂枝汤",
            "type": "other",
            "confidence": 0.95,
            "alternative_names": [],
            "description": "",
            "entity_metadata": {
                "raw_type": "formula",
                "cycle_id": "cycle-001",
                "document_urn": "doc:1",
            },
        }
    )

    assert payload == {
        "entity_id": "entity-001",
        "name": "桂枝汤",
        "entity_type": "formula",
        "confidence": 0.95,
        "cycle_id": "cycle-001",
        "document_urn": "doc:1",
    }


def test_build_observe_version_witness_graph_properties_omits_empty_values():
    payload = build_observe_version_witness_graph_properties(
        {
            "id": "observe-doc-1",
            "urn": "doc:1",
            "title": "伤寒论宋本",
            "source_type": "ctext",
            "version_metadata": {
                "witness_key": "ctext:doc:1",
                "version_lineage_key": "伤寒论|辨脉法|东汉|张仲景|宋本",
                "work_fragment_key": "伤寒论|辨脉法",
                "catalog_id": "ctp:shang-han-lun/bian-mai-fa",
                "work_title": "伤寒论",
                "fragment_title": "辨脉法",
                "dynasty": "东汉",
                "author": "张仲景",
                "edition": "宋本",
            },
        }
    )

    assert payload == {
        "witness_key": "ctext:doc:1",
        "version_lineage_key": "伤寒论|辨脉法|东汉|张仲景|宋本",
        "work_fragment_key": "伤寒论|辨脉法",
        "catalog_id": "ctp:shang-han-lun/bian-mai-fa",
        "work_title": "伤寒论",
        "fragment_title": "辨脉法",
        "dynasty": "东汉",
        "author": "张仲景",
        "edition": "宋本",
        "source_type": "ctext",
        "source_ref": "doc:1",
        "document_id": "observe-doc-1",
        "document_urn": "doc:1",
        "document_title": "伤寒论宋本",
    }


def test_backfill_research_session_nodes_upserts_all_sessions():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    repository.create_session(
        {
            "cycle_id": "cycle-001",
            "cycle_name": "会话一",
            "status": "completed",
            "research_objective": "验证回填",
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    repository.create_session(
        {
            "cycle_id": "cycle-002",
            "cycle_name": "会话二",
            "status": "active",
            "research_scope": "方剂研究",
            "created_at": datetime.utcnow().isoformat(),
        }
    )

    fake_neo4j = _FakeNeo4jDriver()
    summary = backfill_research_session_nodes(repository, fake_neo4j, batch_size=1)

    assert summary["status"] == "active"
    assert summary["batch_count"] == 2
    assert summary["node_count"] == 2
    assert len(fake_neo4j.batches) == 2

    flattened = [node for batch in fake_neo4j.batches for node in batch]
    by_id = {node.id: node for node in flattened}
    assert by_id["cycle-001"].properties["cycle_id"] == "cycle-001"
    assert by_id["cycle-001"].properties["cycle_name"] == "会话一"
    assert by_id["cycle-002"].properties["research_scope"] == "方剂研究"
    assert "created_at" in by_id["cycle-001"].properties

    db_manager.close()


def test_backfill_research_session_nodes_skips_when_neo4j_missing():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    summary = backfill_research_session_nodes(repository, None)

    assert summary == {"status": "skipped", "batch_count": 0, "node_count": 0}

    db_manager.close()


def test_backfill_structured_research_graph_upserts_phase_artifact_nodes_and_edges():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    repository.create_session(
        {
            "cycle_id": "cycle-graph-001",
            "cycle_name": "图谱回填",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    phase = repository.add_phase_execution(
        "cycle-graph-001",
        {
            "phase": "publish",
            "status": "completed",
            "duration": 9.5,
            "error_detail": "",
        },
    )
    assert phase is not None

    repository.add_artifact(
        "cycle-graph-001",
        {
            "phase_execution_id": phase["id"],
            "artifact_type": "paper",
            "name": "paper.md",
            "description": "论文草稿",
            "file_path": "./output/paper.md",
            "mime_type": "text/markdown",
            "size_bytes": 128,
        },
    )
    repository.add_artifact(
        "cycle-graph-001",
        {
            "artifact_type": "report",
            "name": "report.json",
            "file_path": "./output/report.json",
            "mime_type": "application/json",
            "size_bytes": 64,
        },
    )

    fake_neo4j = _FakeNeo4jDriver()
    summary = backfill_structured_research_graph(repository, fake_neo4j, batch_size=1)

    assert summary["status"] == "active"
    assert summary["batch_count"] == 1
    assert summary["session_node_count"] == 1
    assert summary["phase_node_count"] == 1
    assert summary["artifact_node_count"] == 2
    assert summary["observe_entity_node_count"] == 0
    assert summary["has_phase_edge_count"] == 1
    assert summary["generated_edge_count"] == 1
    assert summary["has_artifact_edge_count"] == 1
    assert summary["semantic_edge_count"] == 0
    assert summary["captured_edge_count"] == 0
    assert len(fake_neo4j.batches) == 1
    assert len(fake_neo4j.relationship_batches) == 1

    flattened_nodes = [node for batch in fake_neo4j.batches for node in batch]
    phase_nodes = [node for node in flattened_nodes if node.label == "ResearchPhaseExecution"]
    artifact_nodes = [node for node in flattened_nodes if node.label == "ResearchArtifact"]
    assert phase_nodes[0].properties["created_at"]
    assert phase_nodes[0].properties["cycle_id"] == "cycle-graph-001"
    assert {node.properties["name"] for node in artifact_nodes} == {"paper.md", "report.json"}
    by_name = {node.properties["name"]: node for node in artifact_nodes}
    assert by_name["paper.md"].properties["description"] == "论文草稿"
    assert by_name["paper.md"].properties["created_at"]

    flattened_edges = [edge for batch in fake_neo4j.relationship_batches for edge in batch]
    relationship_types = {edge.relationship_type for edge, _, _ in flattened_edges}
    assert relationship_types == {"HAS_PHASE", "GENERATED", "HAS_ARTIFACT"}

    db_manager.close()


def test_backfill_structured_research_graph_upserts_observe_entity_nodes_and_edges():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    repository.create_session(
        {
            "cycle_id": "cycle-observe-001",
            "cycle_name": "观察图谱回填",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    phase = repository.add_phase_execution(
        "cycle-observe-001",
        {
            "phase": "observe",
            "status": "completed",
            "duration": 6.0,
        },
    )
    assert phase is not None

    repository.replace_observe_document_graphs(
        "cycle-observe-001",
        phase["id"],
        [
            {
                "urn": "doc:observe:1",
                "title": "观察文档",
                "source_type": "ctext",
                "raw_text_size": 128,
                "processed_text_size": 120,
                "entity_count": 2,
                "metadata": {
                    "version_metadata": {
                        "work_title": "伤寒论",
                        "fragment_title": "辨脉法",
                        "work_fragment_key": "伤寒论|辨脉法",
                        "version_lineage_key": "伤寒论|辨脉法|东汉|张仲景|宋本",
                        "catalog_id": "ctp:shang-han-lun/bian-mai-fa",
                        "dynasty": "东汉",
                        "author": "张仲景",
                        "edition": "宋本",
                        "witness_key": "ctext:doc:observe:1",
                    }
                },
                "entities": [
                    {"name": "桂枝汤", "type": "formula", "confidence": 0.95, "position": 0, "length": 3},
                    {"name": "桂枝", "type": "herb", "confidence": 0.93, "position": 4, "length": 2},
                ],
                "semantic_relationships": [
                    {
                        "source": "桂枝汤",
                        "target": "桂枝",
                        "type": "contains",
                        "source_type": "formula",
                        "target_type": "herb",
                        "confidence": 0.95,
                    }
                ],
                "output_generation": {"quality_metrics": {"confidence_score": 0.91}},
            }
        ],
    )

    fake_neo4j = _FakeNeo4jDriver()
    summary = backfill_structured_research_graph(repository, fake_neo4j, batch_size=1)

    assert summary["status"] == "active"
    assert summary["session_node_count"] == 1
    assert summary["phase_node_count"] == 1
    assert summary["observe_entity_node_count"] == 2
    assert summary["version_lineage_node_count"] == 1
    assert summary["version_witness_node_count"] == 1
    assert summary["semantic_edge_count"] == 1
    assert summary["captured_edge_count"] == 2
    assert summary["observed_witness_edge_count"] == 1
    assert summary["belongs_to_lineage_edge_count"] == 1

    flattened_nodes = [node for batch in fake_neo4j.batches for node in batch]
    labels = {node.label for node in flattened_nodes}
    assert "Formula" in labels
    assert "Herb" in labels
    assert "VersionWitness" in labels
    assert "VersionLineage" in labels

    flattened_edges = [edge for batch in fake_neo4j.relationship_batches for edge in batch]
    relationship_types = {edge.relationship_type for edge, _, _ in flattened_edges}
    assert {"HAS_PHASE", "CONTAINS", "CAPTURED", "OBSERVED_WITNESS", "BELONGS_TO_LINEAGE"}.issubset(relationship_types)

    db_manager.close()


def test_backfill_structured_research_graph_reprojects_phase_graph_assets():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    repository.create_session(
        {
            "cycle_id": "cycle-asset-001",
            "cycle_name": "资产图回填",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    phase = repository.add_phase_execution(
        "cycle-asset-001",
        {
            "phase": "analyze",
            "status": "completed",
            "duration": 3.2,
            "output": {
                "results": {
                    "graph_assets": {
                        "evidence_subgraph": {
                            "graph_type": "evidence_subgraph",
                            "asset_family": "evidence",
                            "nodes": [
                                {
                                    "id": "evidence::cycle-asset-001::ev-1",
                                    "label": "Evidence",
                                    "properties": {
                                        "cycle_id": "cycle-asset-001",
                                        "phase": "analyze",
                                        "evidence_id": "ev-1",
                                        "title": "证据一",
                                        "document_title": "文献甲",
                                        "work_title": "伤寒论",
                                    },
                                },
                                {
                                    "id": "claim::cycle-asset-001::cl-1",
                                    "label": "EvidenceClaim",
                                    "properties": {
                                        "cycle_id": "cycle-asset-001",
                                        "phase": "analyze",
                                        "claim_id": "cl-1",
                                        "claim_text": "桂枝汤可解表",
                                    },
                                },
                            ],
                            "edges": [
                                {
                                    "source_id": "claim::cycle-asset-001::cl-1",
                                    "target_id": "evidence::cycle-asset-001::ev-1",
                                    "relationship_type": "EVIDENCED_BY",
                                    "source_label": "EvidenceClaim",
                                    "target_label": "Evidence",
                                    "properties": {"cycle_id": "cycle-asset-001"},
                                }
                            ],
                        },
                        "philology_subgraph": {
                            "graph_type": "philology_subgraph",
                            "asset_family": "philology",
                            "nodes": [
                                {
                                    "id": "exegesis::1",
                                    "label": "ExegesisTerm",
                                    "properties": {
                                        "cycle_id": "cycle-asset-001",
                                        "phase": "observe",
                                        "exegesis_id": "ex-1",
                                        "canonical": "营卫",
                                    },
                                },
                                {
                                    "id": "chain::1",
                                    "label": "TextualEvidenceChain",
                                    "properties": {
                                        "cycle_id": "cycle-asset-001",
                                        "phase": "observe",
                                        "claim_id": "claim-1",
                                    },
                                },
                            ],
                            "edges": [
                                {
                                    "source_id": "chain::1",
                                    "target_id": "exegesis::1",
                                    "relationship_type": "ATTESTS_TO",
                                    "source_label": "TextualEvidenceChain",
                                    "target_label": "ExegesisTerm",
                                    "properties": {"cycle_id": "cycle-asset-001"},
                                }
                            ],
                        },
                    }
                }
            },
        },
    )
    assert phase is not None

    fake_neo4j = _FakeNeo4jDriver()
    summary = backfill_structured_research_graph(repository, fake_neo4j, batch_size=1)

    assert summary["status"] == "active"
    assert summary["graph_asset_subgraph_count"] == 2
    assert summary["evidence_node_count"] == 2
    assert summary["evidence_edge_count"] == 1
    assert summary["philology_node_count"] == 2
    assert summary["philology_edge_count"] == 1
    assert summary["exegesis_term_node_count"] == 1
    assert summary["textual_evidence_chain_node_count"] == 1

    flattened_nodes = [node for batch in fake_neo4j.batches for node in batch]
    labels = {node.label for node in flattened_nodes}
    assert "Evidence" in labels
    assert "EvidenceClaim" in labels
    assert "ExegesisTerm" in labels
    assert "TextualEvidenceChain" in labels

    flattened_edges = [edge for batch in fake_neo4j.relationship_batches for edge in batch]
    relationship_types = {edge.relationship_type for edge, _, _ in flattened_edges}
    assert "DERIVED_FROM_PHASE" in relationship_types
    assert "CAPTURED" in relationship_types
    assert "EVIDENCED_BY" in relationship_types
    assert "ATTESTS_TO" in relationship_types

    db_manager.close()


def test_backfill_structured_research_graph_dry_run_reports_projection_without_writing():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    repository.create_session(
        {
            "cycle_id": "cycle-dry-run-001",
            "cycle_name": "Dry Run 图回填",
            "status": "completed",
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    repository.add_phase_execution(
        "cycle-dry-run-001",
        {
            "phase": "hypothesis",
            "status": "completed",
            "output": {
                "results": {
                    "graph_assets": {
                        "hypothesis_subgraph": {
                            "graph_type": "hypothesis_subgraph",
                            "asset_family": "hypothesis",
                            "nodes": [
                                {
                                    "id": "hypothesis::cycle-dry-run-001::h1",
                                    "label": "Hypothesis",
                                    "properties": {
                                        "cycle_id": "cycle-dry-run-001",
                                        "phase": "hypothesis",
                                        "hypothesis_id": "h1",
                                        "title": "假说一",
                                    },
                                }
                            ],
                            "edges": [],
                        }
                    }
                }
            },
        },
    )

    fake_neo4j = _FakeNeo4jDriver()
    summary = backfill_structured_research_graph(repository, fake_neo4j, batch_size=1, dry_run=True)

    assert summary["status"] == "dry_run"
    assert summary["dry_run"] is True
    assert summary["hypothesis_node_count"] == 1
    assert summary["node_count"] > 0
    assert fake_neo4j.batches == []
    assert fake_neo4j.relationship_batches == []

    db_manager.close()


def test_backfill_structured_research_graph_skips_when_neo4j_missing():
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.init_db()
    repository = ResearchSessionRepository(db_manager)

    summary = backfill_structured_research_graph(repository, None)

    assert summary == {
        "status": "skipped",
        "batch_count": 0,
        "node_count": 0,
        "edge_count": 0,
        "session_node_count": 0,
        "phase_node_count": 0,
        "artifact_node_count": 0,
        "observe_entity_node_count": 0,
        "version_lineage_node_count": 0,
        "version_witness_node_count": 0,
        "has_phase_edge_count": 0,
        "generated_edge_count": 0,
        "has_artifact_edge_count": 0,
        "semantic_edge_count": 0,
        "captured_edge_count": 0,
        "observed_witness_edge_count": 0,
        "belongs_to_lineage_edge_count": 0,
        "hypothesis_node_count": 0,
        "hypothesis_edge_count": 0,
        "evidence_node_count": 0,
        "evidence_edge_count": 0,
        "philology_node_count": 0,
        "philology_edge_count": 0,
        "exegesis_term_node_count": 0,
        "textual_evidence_chain_node_count": 0,
        "graph_asset_subgraph_count": 0,
        "dry_run": False,
    }

    db_manager.close()