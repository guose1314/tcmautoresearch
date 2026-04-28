from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg2
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "logs" / "batch_distill_progress.jsonl"

PG_CONFIG = {
    "dbname": "tcmautoresearch",
    "user": "postgres",
    "password": "Hgk1989225",
    "host": "localhost",
    "port": 5432,
}

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "Hgk1989225")
NEO4J_DB = "neo4j"


@dataclass(frozen=True)
class DocRow:
    id: str
    source_file: str
    created_at: Any
    processing_timestamp: Any
    entity_count: int


def load_successful_files(log_path: Path) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            file_name = rec.get("file")
            if rec.get("ok") is True and file_name and file_name not in seen:
                seen.add(file_name)
                files.append(file_name)
    return files


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def build_plan() -> dict[str, Any]:
    successful_files = load_successful_files(LOG_PATH)
    pg = psycopg2.connect(**PG_CONFIG)
    cur = pg.cursor()

    cur.execute(
        """
        SELECT d.id::text,
               d.source_file,
               d.created_at,
               d.processing_timestamp,
               COUNT(e.id)::int AS entity_count
        FROM documents d
        LEFT JOIN entities e ON e.document_id = d.id
        GROUP BY d.id, d.source_file, d.created_at, d.processing_timestamp
        """
    )
    docs = [DocRow(*row) for row in cur.fetchall()]

    groups: list[dict[str, Any]] = []
    delete_doc_ids: list[str] = []
    keep_doc_ids: list[str] = []

    for base in successful_files:
        matches = [doc for doc in docs if doc.source_file.startswith(base)]
        matches.sort(key=lambda doc: (doc.created_at, doc.processing_timestamp, doc.id))
        if not matches:
            groups.append({
                "base": base,
                "count": 0,
                "keep": None,
                "delete": [],
                "docs": [],
            })
            continue

        keep = matches[0]
        delete = matches[1:]
        keep_doc_ids.append(keep.id)
        delete_doc_ids.extend(doc.id for doc in delete)
        groups.append({
            "base": base,
            "count": len(matches),
            "keep": keep.id,
            "delete": [doc.id for doc in delete],
            "docs": [
                {
                    "id": doc.id,
                    "source_file": doc.source_file,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "processing_timestamp": (
                        doc.processing_timestamp.isoformat()
                        if doc.processing_timestamp else None
                    ),
                    "entity_count": doc.entity_count,
                }
                for doc in matches
            ],
        })

    delete_doc_param = delete_doc_ids or ["00000000-0000-0000-0000-000000000000"]
    cur.execute(
        'SELECT id::text, document_id::text FROM entities WHERE document_id = ANY(%s::uuid[])',
        (delete_doc_param,),
    )
    entity_rows = cur.fetchall()
    delete_entity_ids = [row[0] for row in entity_rows]
    delete_entity_param = delete_entity_ids or ["00000000-0000-0000-0000-000000000000"]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM entity_relationships
        WHERE source_entity_id = ANY(%s::uuid[])
           OR target_entity_id = ANY(%s::uuid[])
        """,
        (delete_entity_param, delete_entity_param),
    )
    rel_count = cur.fetchone()[0]

    child_tables = {}
    for table in (
        "processing_statistics",
        "quality_metrics",
        "research_analyses",
        "processing_logs",
    ):
        cur.execute(
            f'SELECT COUNT(*) FROM {table} WHERE document_id = ANY(%s::uuid[])',
            (delete_doc_param,),
        )
        child_tables[table] = cur.fetchone()[0]

    cur.close()
    pg.close()

    neo_node_count = 0
    neo_edge_count = 0
    if delete_entity_ids:
        neo = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with neo.session(database=NEO4J_DB) as session:
            neo_node_count = session.run(
                'MATCH (n) WHERE n.id IN $ids RETURN count(n) AS c',
                ids=delete_entity_ids,
            ).single()["c"]
            neo_edge_count = session.run(
                'MATCH (n)-[r]-() WHERE n.id IN $ids RETURN count(r) AS c',
                ids=delete_entity_ids,
            ).single()["c"]
        neo.close()

    return {
        "successful_files": len(successful_files),
        "duplicate_groups": sum(1 for group in groups if group["count"] > 1),
        "groups": groups,
        "keep_doc_ids": keep_doc_ids,
        "delete_doc_ids": delete_doc_ids,
        "delete_entity_ids": delete_entity_ids,
        "delete_documents": len(delete_doc_ids),
        "delete_entities": len(delete_entity_ids),
        "delete_relationships": rel_count,
        "child_tables": child_tables,
        "neo4j_nodes": neo_node_count,
        "neo4j_edges": neo_edge_count,
    }


def delete_from_neo4j(entity_ids: list[str]) -> int:
    if not entity_ids:
        return 0
    deleted = 0
    neo = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with neo.session(database=NEO4J_DB) as session:
        for batch in chunked(entity_ids, 500):
            result = session.run(
                """
                MATCH (n)
                WHERE n.id IN $ids
                WITH collect(n) AS nodes
                FOREACH (node IN nodes | DETACH DELETE node)
                RETURN size(nodes) AS deleted
                """,
                ids=batch,
            )
            deleted += result.single()["deleted"]
    neo.close()
    return deleted


def delete_from_postgres(doc_ids: list[str]) -> int:
    if not doc_ids:
        return 0
    pg = psycopg2.connect(**PG_CONFIG)
    pg.autocommit = False
    cur = pg.cursor()
    cur.execute(
        'DELETE FROM documents WHERE id = ANY(%s::uuid[])',
        (doc_ids,),
    )
    deleted = cur.rowcount
    pg.commit()
    cur.close()
    pg.close()
    return deleted


def summarize(plan: dict[str, Any]) -> dict[str, Any]:
    distribution: dict[str, int] = {}
    for group in plan["groups"]:
        key = str(group["count"])
        distribution[key] = distribution.get(key, 0) + 1
    return {
        "successful_files": plan["successful_files"],
        "duplicate_groups": plan["duplicate_groups"],
        "group_count_distribution": distribution,
        "delete_documents": plan["delete_documents"],
        "delete_entities": plan["delete_entities"],
        "delete_relationships": plan["delete_relationships"],
        "delete_processing_statistics": plan["child_tables"]["processing_statistics"],
        "delete_quality_metrics": plan["child_tables"]["quality_metrics"],
        "delete_research_analyses": plan["child_tables"]["research_analyses"],
        "delete_processing_logs": plan["child_tables"]["processing_logs"],
        "neo4j_nodes": plan["neo4j_nodes"],
        "neo4j_edges": plan["neo4j_edges"],
        "delete_bases": [group["base"] for group in plan["groups"] if group["delete"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="execute deletion")
    args = parser.parse_args()

    plan = build_plan()
    print(json.dumps({"dry_run": not args.apply, **summarize(plan)}, ensure_ascii=False, indent=2))

    if not args.apply:
        return 0

    deleted_nodes = delete_from_neo4j(plan["delete_entity_ids"])
    deleted_docs = delete_from_postgres(plan["delete_doc_ids"])
    after = build_plan()
    print(
        json.dumps(
            {
                "applied": True,
                "deleted_neo4j_nodes": deleted_nodes,
                "deleted_pg_documents": deleted_docs,
                "remaining_duplicate_documents": after["delete_documents"],
                "remaining_duplicate_entities": after["delete_entities"],
                "remaining_duplicate_relationships": after["delete_relationships"],
                "remaining_duplicate_neo4j_nodes": after["neo4j_nodes"],
                "remaining_duplicate_neo4j_edges": after["neo4j_edges"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())