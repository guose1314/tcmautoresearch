#!/usr/bin/env python3
"""Backfill legacy self-learning pickle data into research_learning_feedback."""

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
from src.research.legacy_learning_feedback_backfill import (
    backfill_legacy_learning_feedback,
)
from src.storage import StorageBackendFactory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill legacy learning_data.pkl into canonical research_learning_feedback records"
    )
    parser.add_argument("--environment", default="production", help="Target configuration environment")
    parser.add_argument("--config", dest="config_path", default=None, help="Optional config file path")
    parser.add_argument("--file-path", default=None, help="Path to legacy learning_data.pkl")
    parser.add_argument("--cycle-id", default=None, help="Target cycle_id for imported legacy feedback")
    parser.add_argument("--cycle-name", default=None, help="Optional target cycle name")
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Overwrite existing learning feedback rows for the target cycle_id",
    )
    return parser.parse_args()


def _build_report(*, settings, init_report, consistency_state, summary):
    return {
        "environment": settings.environment,
        "loaded_files": list(settings.loaded_files),
        "loaded_secret_files": list(settings.loaded_secret_files),
        "storage": {
            **dict(init_report),
            "consistency_state": dict(consistency_state),
        },
        "backfill": {
            **{key: value for key, value in summary.items() if key != "library"},
            "library_summary": dict((summary.get("library") or {}).get("summary") or {}),
        },
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

        repository = ResearchSessionRepository(factory.db_manager)
        summary = backfill_legacy_learning_feedback(
            repository,
            file_path=args.file_path,
            cycle_id=args.cycle_id,
            cycle_name=args.cycle_name,
            overwrite_existing=bool(args.overwrite_existing),
        )
        print(
            json.dumps(
                _build_report(
                    settings=settings,
                    init_report=init_report,
                    consistency_state=consistency_state,
                    summary=summary,
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