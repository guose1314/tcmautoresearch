#!/usr/bin/env python3
"""Backfill structured research graph nodes in Neo4j from PostgreSQL session data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.infrastructure.config_loader import load_settings
from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.research.research_session_graph_backfill import (
    backfill_structured_research_graph,
)
from src.storage import StorageBackendFactory
from src.storage.graph_schema import GRAPH_SCHEMA_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill historical ResearchSession graph data into Neo4j and persist Observe metadata/artifacts into PostgreSQL"
    )
    parser.add_argument("--environment", default="production", help="Target configuration environment")
    parser.add_argument("--config", dest="config_path", default=None, help="Optional config file path")
    parser.add_argument("--batch-size", type=int, default=200, help="Number of sessions to backfill per Neo4j batch")
    parser.add_argument(
        "--skip-pg-version-writeback",
        action="store_true",
        help="Skip writing inferred Observe version_metadata back into PostgreSQL documents columns before graph backfill",
    )
    parser.add_argument(
        "--skip-pg-philology-artifact-writeback",
        action="store_true",
        help="Skip writing inferred Observe philology ResearchArtifact rows back into PostgreSQL before graph backfill",
    )
    parser.add_argument(
        "--skip-pg-graph-assets-writeback",
        action="store_true",
        help="Skip writing inferred phase graph_assets back into PostgreSQL PhaseExecution.output before Neo4j graph backfill",
    )
    parser.add_argument(
        "--force-pg-graph-assets-regen",
        action="store_true",
        help="Force regeneration of phase graph_assets even for phases that already have graph_assets written (re-derives from source data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute projected graph backfill summary without writing PostgreSQL or Neo4j",
    )
    parser.add_argument(
        "--expected-graph-schema-version",
        default=GRAPH_SCHEMA_VERSION,
        help="Expected graph schema version for preflight/backfill validation",
    )
    return parser.parse_args()


def _annotate_writeback(summary, *, fields_written):
    """为 writeback/backfill 报告追加 fields_written 标注。"""
    if summary is None:
        return None
    result = dict(summary)
    result["fields_written"] = fields_written
    return result


def _build_backfill_report(
    *,
    settings,
    init_report,
    consistency_state,
    schema_summary,
    writeback_summary,
    philology_artifact_writeback_summary,
    phase_graph_assets_writeback_summary,
    graph_summary,
):
    """构建统一的 backfill 报告载荷。"""
    return {
        "environment": settings.environment,
        "loaded_files": list(settings.loaded_files),
        "loaded_secret_files": list(settings.loaded_secret_files),
        "storage": {
            **dict(init_report),
            "consistency_state": dict(consistency_state),
        },
        "graph_schema": dict(schema_summary),
        "observe_version_metadata_writeback": _annotate_writeback(
            writeback_summary,
            fields_written=["version_metadata", "witness_key", "version_lineage_key"],
        ),
        "observe_philology_artifact_writeback": _annotate_writeback(
            philology_artifact_writeback_summary,
            fields_written=["observe_philology_artifacts"],
        ),
        "phase_graph_assets_writeback": _annotate_writeback(
            phase_graph_assets_writeback_summary,
            fields_written=[
                "PhaseExecution.output.results.graph_assets",
                "PhaseExecution.output.metadata.graph_asset_subgraphs",
                "PhaseExecution.output.metadata.graph_asset_node_count",
                "PhaseExecution.output.metadata.graph_asset_edge_count",
            ],
        ),
        "backfill": _annotate_writeback(
            graph_summary,
            fields_written=[
                "VersionLineage_nodes", "VersionWitness_nodes",
                "OBSERVED_WITNESS_edges", "BELONGS_TO_LINEAGE_edges",
                "ResearchSession_nodes", "ResearchPhaseExecution_nodes",
                "ResearchArtifact_nodes", "Entity_nodes",
                "Hypothesis_nodes", "Evidence_nodes", "EvidenceClaim_nodes",
                "Catalog_nodes", "ExegesisTerm_nodes", "FragmentCandidate_nodes",
                "TextualEvidenceChain_nodes",
            ],
        ),
    }


def main() -> int:
    args = parse_args()
    settings = load_settings(
        root_path=WORKSPACE_ROOT,
        config_path=args.config_path,
        environment=args.environment,
    )
    runtime_config = settings.materialize_runtime_config()

    factory = StorageBackendFactory(runtime_config)
    try:
        init_report = factory.initialize()
        consistency_state = factory.get_consistency_state().to_dict()
        if factory.db_manager is None:
            raise RuntimeError("PostgreSQL backend is not initialized")
        if factory.neo4j_driver is None:
            raise RuntimeError("Neo4j backend is not initialized")

        stored_schema_version = factory.neo4j_driver.get_schema_version()
        expected_schema_version = str(args.expected_graph_schema_version or GRAPH_SCHEMA_VERSION).strip() or GRAPH_SCHEMA_VERSION
        schema_summary = {
            "expected_version": expected_schema_version,
            "stored_version": stored_schema_version,
            "matches_expected": stored_schema_version == expected_schema_version,
            "bootstrap_version": GRAPH_SCHEMA_VERSION,
            "drift_report": factory.neo4j_driver.ensure_schema_version(),
        }

        repository = ResearchSessionRepository(factory.db_manager)
        writeback_summary = None
        philology_artifact_writeback_summary = None
        phase_graph_assets_writeback_summary = None
        if args.dry_run:
            writeback_summary = {
                "status": "skipped",
                "reason": "dry_run",
                "batch_size": args.batch_size,
            }
            philology_artifact_writeback_summary = {
                "status": "skipped",
                "reason": "dry_run",
                "batch_size": args.batch_size,
            }
        if args.dry_run:
            phase_graph_assets_writeback_summary = repository.backfill_phase_graph_assets(
                batch_size=args.batch_size,
                dry_run=True,
            )
        elif not args.skip_pg_version_writeback:
            writeback_summary = repository.backfill_observe_document_version_metadata(batch_size=args.batch_size)
        if not args.dry_run and not args.skip_pg_philology_artifact_writeback:
            philology_artifact_writeback_summary = repository.backfill_observe_philology_artifacts(
                batch_size=args.batch_size,
                artifact_output=((runtime_config.get("philology_service") or {}).get("artifact_output") or {}),
            )
        if not args.dry_run and not args.skip_pg_graph_assets_writeback:
            phase_graph_assets_writeback_summary = repository.backfill_phase_graph_assets(
                batch_size=args.batch_size,
                dry_run=False,
                force=bool(getattr(args, "force_pg_graph_assets_regen", False)),
            )
        elif not args.dry_run:
            phase_graph_assets_writeback_summary = {
                "status": "skipped",
                "reason": "flag_disabled",
                "batch_size": args.batch_size,
            }
        summary = backfill_structured_research_graph(
            repository,
            factory.neo4j_driver,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
        print(
            json.dumps(
                _build_backfill_report(
                    settings=settings,
                    init_report=init_report,
                    consistency_state=consistency_state,
                    schema_summary=schema_summary,
                    writeback_summary=writeback_summary,
                    philology_artifact_writeback_summary=philology_artifact_writeback_summary,
                    phase_graph_assets_writeback_summary=phase_graph_assets_writeback_summary,
                    graph_summary=summary,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        factory.close()


if __name__ == "__main__":
    raise SystemExit(main())