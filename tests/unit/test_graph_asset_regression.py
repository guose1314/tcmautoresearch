from __future__ import annotations

from tools.backfill_research_session_nodes import _build_backfill_report


def test_backfill_report_includes_graph_schema_and_dry_run_summary():
    settings = type(
        "SettingsStub",
        (),
        {
            "environment": "production",
            "loaded_files": ["config.yml"],
            "loaded_secret_files": ["secrets.yml"],
        },
    )()

    report = _build_backfill_report(
        settings=settings,
        init_report={"pg_status": "active", "neo4j_status": "active"},
        consistency_state={"mode": "dual_write"},
        schema_summary={
            "expected_version": "1.1.0",
            "stored_version": "1.1.0",
            "matches_expected": True,
            "bootstrap_version": "1.1.0",
            "drift_report": {"drift_detected": False},
        },
        writeback_summary={"status": "skipped", "reason": "dry_run"},
        philology_artifact_writeback_summary={"status": "skipped", "reason": "dry_run"},
        phase_graph_assets_writeback_summary={"status": "dry_run", "dry_run": True, "updated_phase_count": 2},
        graph_summary={
            "status": "dry_run",
            "dry_run": True,
            "node_count": 12,
            "edge_count": 18,
            "graph_asset_subgraph_count": 3,
            "philology_node_count": 4,
        },
    )

    assert report["graph_schema"]["expected_version"] == "1.1.0"
    assert report["graph_schema"]["matches_expected"] is True
    assert report["phase_graph_assets_writeback"]["status"] == "dry_run"
    assert report["phase_graph_assets_writeback"]["updated_phase_count"] == 2
    assert report["backfill"]["status"] == "dry_run"
    assert report["backfill"]["dry_run"] is True
    assert report["backfill"]["graph_asset_subgraph_count"] == 3


def test_backfill_report_marks_g3_fields_written_contract():
    settings = type(
        "SettingsStub",
        (),
        {
            "environment": "production",
            "loaded_files": [],
            "loaded_secret_files": [],
        },
    )()

    report = _build_backfill_report(
        settings=settings,
        init_report={},
        consistency_state={},
        schema_summary={},
        writeback_summary=None,
        philology_artifact_writeback_summary=None,
        phase_graph_assets_writeback_summary=None,
        graph_summary={"status": "active", "node_count": 1, "edge_count": 1},
    )

    fields_written = report["backfill"]["fields_written"]
    assert "Hypothesis_nodes" in fields_written
    assert "Evidence_nodes" in fields_written
    assert "Catalog_nodes" in fields_written
    assert "ExegesisTerm_nodes" in fields_written
    assert "TextualEvidenceChain_nodes" in fields_written


def test_backfill_report_preserves_storage_consistency_snapshot():
    settings = type(
        "SettingsStub",
        (),
        {
            "environment": "production",
            "loaded_files": [],
            "loaded_secret_files": [],
        },
    )()

    report = _build_backfill_report(
        settings=settings,
        init_report={"schema_completeness": {"status": "ok"}},
        consistency_state={"mode": "dual_write", "schema_drift_detected": False},
        schema_summary={"expected_version": "1.1.0"},
        writeback_summary={"status": "active"},
        philology_artifact_writeback_summary={"status": "active"},
        phase_graph_assets_writeback_summary={"status": "active", "updated_phase_count": 4},
        graph_summary={"status": "active", "node_count": 10, "edge_count": 11},
    )

    assert report["storage"]["schema_completeness"]["status"] == "ok"
    assert report["storage"]["consistency_state"]["mode"] == "dual_write"
    assert report["graph_schema"]["expected_version"] == "1.1.0"
    assert report["phase_graph_assets_writeback"]["updated_phase_count"] == 4


# ───────────────────────────────────────────────────────────────────────
# Phase G / G-4 扩展回归
# ───────────────────────────────────────────────────────────────────────

import inspect  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Mapping  # noqa: E402

_WORKSPACE = Path(__file__).resolve().parents[2]
_SRC = _WORKSPACE / "src"


# ── Schema registry 完整性 ──────────────────────────────────────────


def test_schema_registry_covers_required_node_labels():
    from src.storage.graph_schema import get_registered_labels

    labels = get_registered_labels()
    for required in (
        "ResearchSession", "ResearchPhaseExecution", "ResearchArtifact",
        "Hypothesis", "Evidence", "EvidenceClaim",
        "Catalog", "VersionLineage", "VersionWitness",
        "ExegesisTerm", "FragmentCandidate", "TextualEvidenceChain",
        "GraphSchemaMeta",
    ):
        assert required in labels, f"NodeLabel 缺失: {required}"


def test_schema_registry_covers_required_rel_types():
    from src.storage.graph_schema import get_registered_rel_types

    rel_types = get_registered_rel_types()
    for required in (
        "HAS_PHASE", "GENERATED", "HAS_ARTIFACT", "CAPTURED",
        "HAS_HYPOTHESIS", "EVIDENCE_FOR", "DERIVED_FROM_PHASE",
        "BELONGS_TO_LINEAGE", "OBSERVED_WITNESS",
        "ATTESTS_TO", "HAS_FRAGMENT_CANDIDATE", "CATALOGED_IN",
    ):
        assert required in rel_types, f"RelType 缺失: {required}"


def test_schema_drift_detection_handles_three_paths():
    from src.storage.graph_schema import GRAPH_SCHEMA_VERSION, detect_schema_drift

    none_drift = detect_schema_drift(None)
    assert none_drift["drift_detected"] is True
    assert none_drift["expected_version"] == GRAPH_SCHEMA_VERSION

    ok = detect_schema_drift(GRAPH_SCHEMA_VERSION)
    assert ok["drift_detected"] is False

    mismatch = detect_schema_drift("0.0.1")
    assert mismatch["drift_detected"] is True
    assert mismatch["stored_version"] == "0.0.1"


# ── backfill_structured_research_graph dry-run 契约 ──────────────────


_BACKFILL_REQUIRED_KEYS = (
    "status", "batch_count", "node_count", "edge_count",
    "session_node_count", "phase_node_count", "artifact_node_count",
    "observe_entity_node_count",
    "version_lineage_node_count", "version_witness_node_count",
    "has_phase_edge_count", "generated_edge_count", "has_artifact_edge_count",
    "captured_edge_count", "observed_witness_edge_count",
    "belongs_to_lineage_edge_count",
    "hypothesis_node_count", "hypothesis_edge_count",
    "evidence_node_count", "evidence_edge_count",
    "philology_node_count", "philology_edge_count",
    "exegesis_term_node_count", "textual_evidence_chain_node_count",
    "graph_asset_subgraph_count", "dry_run",
)


def test_backfill_structured_research_graph_dry_run_contract():
    """G-4-1：dry-run 即便 driver 缺失也必须返回完整资产计数字段。"""
    from src.research.research_session_graph_backfill import (
        backfill_structured_research_graph,
    )

    summary = backfill_structured_research_graph(
        repository=object(),
        neo4j_driver=None,
        batch_size=10,
        dry_run=True,
    )
    for key in _BACKFILL_REQUIRED_KEYS:
        assert key in summary, f"dry-run summary 缺字段: {key}"


def test_backfill_structured_research_graph_supports_dry_run_kwarg():
    from src.research.research_session_graph_backfill import (
        backfill_structured_research_graph,
    )

    sig = inspect.signature(backfill_structured_research_graph)
    assert "dry_run" in sig.parameters
    assert "batch_size" in sig.parameters


# ── _build_phase_graph_asset_nodes_and_edges 资产族分类 ───────────────


def _make_phase(phase: str, asset_family: str, label: str, edge_rel: str = "RELATED_TO") -> Mapping[str, Any]:
    return {
        "id": f"phase-{phase}-1",
        "phase": phase,
        "output": {
            "results": {
                "graph_assets": {
                    f"{asset_family}_subgraph": {
                        "graph_type": f"{asset_family}_graph",
                        "asset_family": asset_family,
                        "nodes": [
                            {"id": f"{asset_family}-n1", "label": label,
                             "properties": {"cycle_id": "cycle-x", "name": "n1"}},
                            {"id": f"{asset_family}-n2", "label": label,
                             "properties": {"cycle_id": "cycle-x", "name": "n2"}},
                        ],
                        "edges": [
                            {
                                "source_id": f"{asset_family}-n1",
                                "target_id": f"{asset_family}-n2",
                                "source_label": label,
                                "target_label": label,
                                "relationship_type": edge_rel,
                                "properties": {"cycle_id": "cycle-x"},
                            }
                        ],
                    }
                }
            }
        },
    }


def test_hypothesis_subgraph_classification():
    from src.research.research_session_graph_backfill import (
        _build_phase_graph_asset_nodes_and_edges,
    )

    phase = _make_phase("hypothesis", "hypothesis", "Hypothesis", edge_rel="SUPPORTED_BY")
    nodes, edges, counts = _build_phase_graph_asset_nodes_and_edges("cycle-x", [phase])

    assert counts["hypothesis_node_count"] == 2
    assert counts["hypothesis_edge_count"] == 1
    assert counts["evidence_node_count"] == 0
    assert counts["philology_node_count"] == 0
    assert counts["graph_asset_subgraph_count"] == 1
    rel_types = {edge.relationship_type for edge, _, _ in edges}
    assert "HAS_HYPOTHESIS" in rel_types
    assert "SUPPORTED_BY" in rel_types


def test_evidence_subgraph_classification():
    from src.research.research_session_graph_backfill import (
        _build_phase_graph_asset_nodes_and_edges,
    )

    phase = _make_phase("analyze", "evidence", "EvidenceClaim", edge_rel="EVIDENCE_FOR")
    _, edges, counts = _build_phase_graph_asset_nodes_and_edges("cycle-x", [phase])

    assert counts["evidence_node_count"] == 2
    assert counts["evidence_edge_count"] == 1
    rel_types = {edge.relationship_type for edge, _, _ in edges}
    assert "DERIVED_FROM_PHASE" in rel_types
    assert "EVIDENCE_FOR" in rel_types


def test_philology_subgraph_classification_emits_exegesis_term():
    from src.research.research_session_graph_backfill import (
        _build_phase_graph_asset_nodes_and_edges,
    )

    phase = _make_phase("observe", "philology", "ExegesisTerm", edge_rel="ATTESTS_TO")
    _, edges, counts = _build_phase_graph_asset_nodes_and_edges("cycle-x", [phase])

    assert counts["philology_node_count"] == 2
    assert counts["philology_edge_count"] == 1
    assert counts["exegesis_term_node_count"] == 2
    rel_types = {edge.relationship_type for edge, _, _ in edges}
    assert "CAPTURED" in rel_types
    assert "ATTESTS_TO" in rel_types


def test_phase_without_assets_yields_zero_counts():
    from src.research.research_session_graph_backfill import (
        _build_phase_graph_asset_nodes_and_edges,
    )

    nodes, edges, counts = _build_phase_graph_asset_nodes_and_edges(
        "cycle-y",
        [{"id": "phase-x", "phase": "observe", "output": {"results": {}}}],
    )
    assert nodes == []
    assert edges == []
    assert counts["graph_asset_subgraph_count"] == 0
    assert counts["hypothesis_node_count"] == 0


# ── PG backfill_phase_graph_assets force 参数 ────────────────────────


def test_pg_backfill_phase_graph_assets_supports_force():
    from src.infrastructure.research_session_repo import ResearchSessionRepository

    sig = inspect.signature(ResearchSessionRepository.backfill_phase_graph_assets)
    for param in ("batch_size", "dry_run", "force"):
        assert param in sig.parameters, f"backfill_phase_graph_assets 缺参数: {param}"


# ── PS1 dry-run 摘要表面 ─────────────────────────────────────────────


def test_ps1_preflight_summary_writes_projected_breakdown():
    source = (_WORKSPACE / ".vscode" / "production-local-backfill.ps1").read_text(encoding="utf-8")
    assert "ExpectedGraphSchemaVersion" in source
    assert "--dry-run" in source
    assert "--expected-graph-schema-version" in source
    assert "PREFLIGHT SUMMARY" in source
    assert "projected nodes" in source
    assert "projected edges" in source
    assert "projected assets" in source
    assert "ForceGraphAssetsRegen" in source


# ── KG stats / Neo4j driver schema 输出 ───────────────────────────────


def test_kg_stats_endpoint_exposes_schema_info():
    source = (_SRC / "web" / "routes" / "analysis.py").read_text(encoding="utf-8")
    assert "_get_graph_schema_info" in source
    assert "schema_version" in source


def test_neo4j_driver_statistics_includes_asset_counts():
    source = (_SRC / "storage" / "neo4j_driver.py").read_text(encoding="utf-8")
    for required in (
        "schema_version", "schema_drift_detected",
        "hypothesis_node_count", "evidence_node_count", "evidence_claim_node_count",
        "has_hypothesis_edge_count", "evidence_for_edge_count", "derived_from_phase_edge_count",
    ):
        assert required in source, f"get_graph_statistics 缺字段: {required}"


# ── neo4j_query_templates：philology_asset_graph 模板 ─────────────────


def test_philology_asset_graph_template_registered():
    from tools.neo4j_query_templates import CANONICAL_READ_TEMPLATES

    assert "philology_asset_graph" in CANONICAL_READ_TEMPLATES
    cypher = CANONICAL_READ_TEMPLATES["philology_asset_graph"]["cypher"]
    for token in ("VersionWitness", "ATTESTS_TO", "ExegesisTerm",
                   "FragmentCandidate", "graph_source"):
        assert token in cypher
