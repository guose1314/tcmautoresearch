#!/usr/bin/env python3
"""Storage stress benchmark for PostgreSQL + Neo4j dual write."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Sequence
from uuid import uuid4

from src.storage import UnifiedStorageDriver


@dataclass
class PhaseResult:
    name: str
    duration_ms: float
    count: int = 0

    @property
    def throughput_per_sec(self) -> float:
        if self.duration_ms <= 0 or self.count <= 0:
            return 0.0
        return self.count / (self.duration_ms / 1000.0)


@dataclass
class RoundResult:
    entity_count: int
    relationship_count: int
    total_ms: float
    phases: List[PhaseResult]

    @property
    def entity_throughput(self) -> float:
        if self.total_ms <= 0:
            return 0.0
        return self.entity_count / (self.total_ms / 1000.0)

    @property
    def relationship_throughput(self) -> float:
        if self.total_ms <= 0:
            return 0.0
        return self.relationship_count / (self.total_ms / 1000.0)


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def build_entities(n: int) -> List[Dict]:
    types = ["formula", "herb", "syndrome", "efficacy", "property", "taste", "meridian"]
    entities: List[Dict] = []
    for i in range(n):
        t = types[i % len(types)]
        entities.append(
            {
                "name": f"bench_{t}_{i}",
                "type": t,
                "confidence": 0.80 + ((i % 20) / 100.0),
                "position": i * 2,
                "length": len(f"bench_{t}_{i}"),
                "alternative_names": [f"alias_{i}"],
                "description": f"benchmark entity {i}",
                "metadata": {"source": "stress", "index": i, "kind": t},
            }
        )
    return entities


def build_relationships(entity_ids: Sequence[Any]) -> List[Dict]:
    rel_types = ["CONTAINS", "HAS_EFFICACY", "TREATS", "SIMILAR_TO", "ASSISTANT", "MINISTER", "SOVEREIGN"]
    rels: List[Dict] = []

    # chain relationships
    for i in range(len(entity_ids) - 1):
        rels.append(
            {
                "source_entity_id": entity_ids[i],
                "target_entity_id": entity_ids[i + 1],
                "relationship_type": rel_types[i % len(rel_types)],
                "confidence": 0.75 + ((i % 15) / 100.0),
                "created_by_module": "stress_benchmark",
                "evidence": f"chain_{i}",
                "metadata": {"link": "chain", "i": i},
            }
        )

    # skip-one relationships
    for i in range(len(entity_ids) - 2):
        rels.append(
            {
                "source_entity_id": entity_ids[i],
                "target_entity_id": entity_ids[i + 2],
                "relationship_type": rel_types[(i + 2) % len(rel_types)],
                "confidence": 0.70 + ((i % 20) / 100.0),
                "created_by_module": "stress_benchmark",
                "evidence": f"skip_{i}",
                "metadata": {"link": "skip", "i": i},
            }
        )

    return rels


def run_round(storage: UnifiedStorageDriver, n_entities: int) -> RoundResult:
    phases: List[PhaseResult] = []

    round_start = now_ms()

    t0 = now_ms()
    doc_id = storage.save_document(
        source_file=f"stress_doc_{n_entities}_{uuid4().hex[:8]}",
        objective="stress_benchmark",
        raw_text_size=n_entities * 40,
    )
    if doc_id is None:
        raise RuntimeError("save_document returned None")
    t1 = now_ms()
    phases.append(PhaseResult(name="save_document", duration_ms=t1 - t0, count=1))

    entities = build_entities(n_entities)
    t2 = now_ms()
    entity_ids = storage.save_entities(doc_id, entities)
    t3 = now_ms()
    phases.append(PhaseResult(name="save_entities", duration_ms=t3 - t2, count=len(entity_ids)))

    rels = build_relationships(entity_ids)
    t4 = now_ms()
    rel_ids = storage.save_relationships(doc_id, rels)
    t5 = now_ms()
    phases.append(PhaseResult(name="save_relationships", duration_ms=t5 - t4, count=len(rel_ids)))

    stats = {
        "formulas_count": n_entities // 7,
        "herbs_count": n_entities // 7,
        "syndromes_count": n_entities // 7,
        "efficacies_count": n_entities // 7,
        "relationships_count": len(rel_ids),
        "graph_nodes_count": len(entity_ids),
        "graph_edges_count": len(rel_ids),
        "graph_density": 0.0,
        "connected_components": 1,
        "source_modules": ["stress_benchmark"],
        "processing_time_ms": int(now_ms() - round_start),
    }
    t6 = now_ms()
    storage.save_statistics(doc_id, stats)
    t7 = now_ms()
    phases.append(PhaseResult(name="save_statistics", duration_ms=t7 - t6, count=1))

    total = now_ms() - round_start
    return RoundResult(
        entity_count=len(entity_ids),
        relationship_count=len(rel_ids),
        total_ms=total,
        phases=phases,
    )


def main() -> int:
    db_password = os.getenv("DB_PASSWORD", "")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not db_password or not neo4j_password:
        print("ERROR: DB_PASSWORD and NEO4J_PASSWORD are required.")
        return 2

    pg_url = f"postgresql://tcm_user:{db_password}@localhost:5432/tcm_autoresearch"
    neo4j_uri = "neo4j://localhost:7687"
    neo4j_auth = ("neo4j", neo4j_password)

    storage = UnifiedStorageDriver(pg_url, neo4j_uri, neo4j_auth)

    rounds = [100, 300, 500]
    results: Dict[str, Dict] = {}

    try:
        storage.initialize()

        for n in rounds:
            rr = run_round(storage, n)
            results[str(n)] = {
                "entity_count": rr.entity_count,
                "relationship_count": rr.relationship_count,
                "total_ms": round(rr.total_ms, 2),
                "entity_throughput_per_sec": round(rr.entity_throughput, 2),
                "relationship_throughput_per_sec": round(rr.relationship_throughput, 2),
                "phases": [
                    {
                        "name": p.name,
                        "duration_ms": round(p.duration_ms, 2),
                        "count": p.count,
                        "throughput_per_sec": round(p.throughput_per_sec, 2),
                    }
                    for p in rr.phases
                ],
            }

        summary = {
            "timestamp": datetime.now().isoformat(),
            "rounds": results,
        }
        out_file = "storage_stress_results.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\nRESULT_FILE={out_file}")
        return 0

    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
