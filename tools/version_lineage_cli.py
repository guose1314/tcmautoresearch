"""Minimal CLI for edition lineage and variant reading import/view."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.persistence import (
    Document,
    EditionLineage,
    PersistenceService,
    VariantReading,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import or view document edition lineage and variant readings."
    )
    parser.add_argument(
        "--database-url",
        default=f"sqlite:///{(REPO_ROOT / 'data' / 'tcmautoresearch.db').as_posix()}",
        help="SQLAlchemy database URL.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="Import JSON payloads.")
    import_parser.add_argument("--json", required=True, dest="json_path")

    list_parser = subparsers.add_parser(
        "list", help="List edition lineage and variants."
    )
    list_parser.add_argument("--document-id")
    list_parser.add_argument("--source-file")
    list_parser.add_argument("--canonical-document-key")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    service = PersistenceService({"connection_string": args.database_url})
    if not service.initialize():
        raise RuntimeError("PersistenceService initialization failed")
    try:
        if args.command == "import":
            payloads = _load_payloads(Path(args.json_path))
            results = [service.persist_document_graph(payload) for payload in payloads]
            _print_json({"imported": len(results), "results": results})
            return 0
        if args.command == "list":
            snapshot = _load_snapshot(
                service,
                document_id=args.document_id,
                source_file=args.source_file,
                canonical_document_key=args.canonical_document_key,
            )
            _print_json(snapshot)
            return 0
    finally:
        service.cleanup()
    return 1


def _load_payloads(path: Path) -> List[Mapping[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, Mapping) and isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, Mapping)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        return [data]
    raise ValueError(f"Unsupported JSON payload shape: {path}")


def _load_snapshot(
    service: PersistenceService,
    *,
    document_id: Optional[str],
    source_file: Optional[str],
    canonical_document_key: Optional[str],
) -> Dict[str, Any]:
    if not any((document_id, source_file, canonical_document_key)):
        return _list_recent_version_records(service)
    if canonical_document_key:
        manager = service._require_manager()
        with manager.session_scope() as session:
            document = (
                session.query(Document)
                .filter_by(
                    canonical_document_key=canonical_document_key.strip().lower()
                )
                .one_or_none()
            )
            if document is None:
                return {
                    "found": False,
                    "canonical_document_key": canonical_document_key,
                }
            document_id = str(document.id)
    return service.get_document_snapshot(
        document_id=document_id,
        source_file=source_file,
    )


def _list_recent_version_records(
    service: PersistenceService, limit: int = 200
) -> Dict[str, Any]:
    manager = service._require_manager()
    with manager.session_scope() as session:
        editions = (
            session.query(EditionLineage)
            .order_by(EditionLineage.created_at.desc())
            .limit(limit)
            .all()
        )
        variants = (
            session.query(VariantReading)
            .order_by(VariantReading.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "found": True,
            "edition_lineage_count": session.query(EditionLineage).count(),
            "variant_reading_count": session.query(VariantReading).count(),
            "edition_lineages": [item.to_dict() for item in editions],
            "variant_readings": [item.to_dict() for item in variants],
        }


def _print_json(payload: Mapping[str, Any] | Iterable[Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
