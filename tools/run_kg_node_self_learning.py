from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.persistence import DatabaseManager  # noqa: E402
from src.learning.kg_node_self_learning import (  # noqa: E402
    KGNodeSelfLearningEnhancer,
    export_review_queue_jsonl,
    load_review_jsonl,
)
from src.learning.learning_insight_repo import LearningInsightRepo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mine reviewable KG candidate edges from persisted PostgreSQL entities."
    )
    parser.add_argument("--cycle-id", default="kg-node-self-learning")
    parser.add_argument("--database-url", default=os.getenv("TCM_DATABASE_URL", ""))
    parser.add_argument(
        "--production-local",
        action="store_true",
        help="Require TCM__DATABASE__* environment variables.",
    )
    parser.add_argument("--max-entities", type=int, default=4000)
    parser.add_argument("--max-candidates", type=int, default=200)
    parser.add_argument("--min-confidence", type=float, default=0.58)
    parser.add_argument("--persist-insights", action="store_true")
    parser.add_argument("--export-review-jsonl", default="")
    parser.add_argument("--apply-reviewed-jsonl", default="")
    parser.add_argument("--reviewer", default="expert_review")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    database_url = _resolve_database_url(args)
    db = DatabaseManager(database_url)
    repo = LearningInsightRepo(db)
    enhancer = KGNodeSelfLearningEnhancer(
        db,
        learning_insight_repo=repo,
        max_entities=args.max_entities,
        max_candidates=args.max_candidates,
        min_confidence=args.min_confidence,
    )
    try:
        if args.apply_reviewed_jsonl:
            reviewed_items = load_review_jsonl(args.apply_reviewed_jsonl)
            result = enhancer.apply_reviewed_edges(
                reviewed_items,
                reviewer=args.reviewer,
                dry_run=args.dry_run,
            )
            _print_json(result)
            return 0

        if args.persist_insights and not args.dry_run:
            insights = enhancer.persist_candidate_insights(cycle_id=args.cycle_id)
        else:
            candidates = enhancer.mine_candidate_edges(cycle_id=args.cycle_id)
            insights = enhancer.candidates_to_learning_insights(
                candidates, cycle_id=args.cycle_id
            )

        review_queue = enhancer.build_expert_review_queue(insights)
        if args.export_review_jsonl:
            output_path = export_review_queue_jsonl(
                review_queue, args.export_review_jsonl
            )
        else:
            output_path = None

        _print_json(
            {
                "cycle_id": args.cycle_id,
                "candidate_count": review_queue["total_count"],
                "pending_count": review_queue["pending_count"],
                "persisted_insight_count": (
                    len(insights) if args.persist_insights and not args.dry_run else 0
                ),
                "dry_run": bool(args.dry_run),
                "review_jsonl": str(output_path) if output_path else None,
                "top_candidates": review_queue["items"][:10],
            }
        )
        return 0
    finally:
        db.close()


def _resolve_database_url(args: argparse.Namespace) -> str:
    if args.database_url:
        return args.database_url
    env_url = _database_url_from_env()
    if args.production_local:
        if not env_url:
            raise RuntimeError(
                "--production-local requires TCM__DATABASE__HOST/NAME/USER/PASSWORD "
                "or POSTGRES_HOST/DB/USER/PASSWORD in the current process environment"
            )
        return env_url
    if env_url:
        return env_url
    return "sqlite:///tcm_autoresearch.db"


def _database_url_from_env() -> str:
    host = os.getenv("TCM__DATABASE__HOST") or os.getenv("POSTGRES_HOST")
    db_name = os.getenv("TCM__DATABASE__NAME") or os.getenv("POSTGRES_DB")
    user = os.getenv("TCM__DATABASE__USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("TCM__DATABASE__PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    port = os.getenv("TCM__DATABASE__PORT") or os.getenv("POSTGRES_PORT") or "5432"
    if not all([host, db_name, user, password]):
        return ""
    return (
        f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{db_name}"
    )


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
