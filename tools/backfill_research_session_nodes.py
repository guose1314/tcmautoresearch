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
    return parser.parse_args()


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
        if factory.db_manager is None:
            raise RuntimeError("PostgreSQL backend is not initialized")
        if factory.neo4j_driver is None:
            raise RuntimeError("Neo4j backend is not initialized")

        repository = ResearchSessionRepository(factory.db_manager)
        writeback_summary = None
        philology_artifact_writeback_summary = None
        if not args.skip_pg_version_writeback:
            writeback_summary = repository.backfill_observe_document_version_metadata(batch_size=args.batch_size)
        if not args.skip_pg_philology_artifact_writeback:
            philology_artifact_writeback_summary = repository.backfill_observe_philology_artifacts(
                batch_size=args.batch_size,
                artifact_output=((runtime_config.get("philology_service") or {}).get("artifact_output") or {}),
            )
        summary = backfill_structured_research_graph(
            repository,
            factory.neo4j_driver,
            batch_size=args.batch_size,
        )
        print(
            json.dumps(
                {
                    "environment": settings.environment,
                    "loaded_files": list(settings.loaded_files),
                    "loaded_secret_files": list(settings.loaded_secret_files),
                    "storage": init_report,
                    "observe_version_metadata_writeback": writeback_summary,
                    "observe_philology_artifact_writeback": philology_artifact_writeback_summary,
                    "backfill": summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        factory.close()


if __name__ == "__main__":
    raise SystemExit(main())