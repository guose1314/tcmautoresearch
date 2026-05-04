from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import or_, text

from src.infrastructure.persistence import (
    DatabaseManager,
    Entity,
    EntityRelationship,
)
from src.learning.weak_edge_candidate_repo import (
    WeakEdgeCandidateRepository,
    extract_weak_edge_candidate_payload,
)

KG_NODE_SELF_LEARNING_CONTRACT_VERSION = "kg-node-self-learning-v1"
KG_NODE_SELF_LEARNING_SOURCE = "kg_node_self_learning"
KG_NODE_SELF_LEARNING_MODULE = "kg_node_self_learning"

REVIEW_STATUS_ACCEPTED = "accepted"
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_NEEDS_SOURCE = "needs_source"

_COMPOSITION_RELATIONS = {"CONTAINS", "SOVEREIGN", "MINISTER", "ASSISTANT", "ENVOY"}
_THERAPEUTIC_RELATIONS = {"TREATS", "INDICATES", "SYMPTOM_OF", "CAUSE_OF"}


@dataclass(frozen=True)
class EntityNode:
    id: str
    name: str
    entity_type: str
    document_id: str
    confidence: float
    position: int
    length: int
    alternative_names: Tuple[str, ...] = ()


@dataclass
class EdgeCandidate:
    source_entity_id: str
    target_entity_id: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str
    relationship_type: str
    confidence: float
    signals: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_edge_id(self) -> str:
        seed = "|".join(
            (
                self.source_entity_id,
                self.target_entity_id,
                self.relationship_type,
                self.source_name,
                self.target_name,
            )
        )
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"kg-edge:{digest}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": KG_NODE_SELF_LEARNING_CONTRACT_VERSION,
            "candidate_edge_id": self.candidate_edge_id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "source_name": self.source_name,
            "target_name": self.target_name,
            "source_type": self.source_type,
            "target_type": self.target_type,
            "relationship_type": self.relationship_type,
            "confidence": round(float(self.confidence), 4),
            "signals": list(dict.fromkeys(self.signals)),
            "evidence": dict(self.evidence or {}),
            "review_status": REVIEW_STATUS_PENDING,
            "needs_expert_review": True,
            "review_priority": _review_priority(self.confidence, self.signals),
            "source": KG_NODE_SELF_LEARNING_SOURCE,
        }


class KGNodeSelfLearningEnhancer:
    """Mine reviewable candidate edges from persisted PG knowledge graph nodes.

    The implementation intentionally follows a human-in-the-loop design: it
    creates candidate edges as LearningInsight rows and only writes real graph
    edges when a reviewed payload is explicitly marked as accepted.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        *,
        learning_insight_repo: Any = None,
        max_entities: int = 4000,
        max_candidates: int = 200,
        min_confidence: float = 0.58,
        document_neighbor_window: int = 18,
        max_position_gap: int = 2200,
        include_two_hop: bool = True,
        neo4j_driver: Any = None,
    ) -> None:
        if db_manager is None:
            raise ValueError("db_manager is required")
        self._db = db_manager
        self._repo = learning_insight_repo
        self._max_entities = max(1, int(max_entities or 1))
        self._max_candidates = max(1, int(max_candidates or 1))
        self._min_confidence = _clamp_confidence(min_confidence)
        self._document_neighbor_window = max(1, int(document_neighbor_window or 1))
        self._max_position_gap = max(0, int(max_position_gap or 0))
        self._include_two_hop = bool(include_two_hop)
        self._neo4j_driver = neo4j_driver

    def mine_pg_assets(
        self, cycle_id: str = "kg-node-self-learning"
    ) -> List[Dict[str, Any]]:
        """ResearchLearningService-compatible miner method."""
        candidates = self.mine_candidate_edges(cycle_id=cycle_id)
        return self.candidates_to_learning_insights(candidates, cycle_id=cycle_id)

    def mine_candidate_edges(
        self, *, cycle_id: str = "kg-node-self-learning"
    ) -> List[Dict[str, Any]]:
        snapshot = self._load_graph_snapshot()
        entities: List[EntityNode] = snapshot["entities"]
        existing_edges: set[tuple[str, str]] = snapshot["existing_edges"]
        existing_typed_edges: set[tuple[str, str, str]] = snapshot[
            "existing_typed_edges"
        ]
        relationships: List[Dict[str, Any]] = snapshot["relationships"]

        merged: Dict[tuple[str, str, str], EdgeCandidate] = {}
        for candidate in self._iter_document_candidates(entities, existing_edges):
            self._merge_candidate(merged, candidate)
        for candidate in self._iter_alias_candidates(entities, existing_edges):
            self._merge_candidate(merged, candidate)
        if self._include_two_hop:
            for candidate in self._iter_two_hop_candidates(
                entities,
                relationships,
                existing_edges,
                existing_typed_edges,
            ):
                self._merge_candidate(merged, candidate)

        candidates = [
            item for item in merged.values() if item.confidence >= self._min_confidence
        ]
        candidates.sort(
            key=lambda item: (
                -float(item.confidence),
                item.relationship_type,
                item.source_name,
                item.target_name,
            )
        )
        return [
            {
                **candidate.to_dict(),
                "cycle_id": str(cycle_id or "kg-node-self-learning"),
                "created_at": _now_iso(),
            }
            for candidate in candidates[: self._max_candidates]
        ]

    def candidates_to_learning_insights(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        cycle_id: str = "kg-node-self-learning",
    ) -> List[Dict[str, Any]]:
        insights: List[Dict[str, Any]] = []
        normalized_cycle_id = str(cycle_id or "kg-node-self-learning").strip()
        weak_edge_repo = WeakEdgeCandidateRepository(self._db)
        for candidate in candidates or []:
            if not isinstance(candidate, Mapping):
                continue
            insight = weak_edge_repo.prepare_upsert_mapping(
                candidate,
                target_phase="analyze",
                source_algorithm=KG_NODE_SELF_LEARNING_SOURCE,
                discovered_at=candidate.get("created_at") or _now_iso(),
                legacy_insight_types=["candidate_edge"],
            )
            insight["cycle_id"] = normalized_cycle_id
            insights.append(insight)
        return insights

    def persist_candidate_insights(
        self, *, cycle_id: str = "kg-node-self-learning"
    ) -> List[Dict[str, Any]]:
        if self._repo is None:
            raise ValueError("learning_insight_repo is required to persist insights")
        persisted: List[Dict[str, Any]] = []
        for insight in self.mine_pg_assets(cycle_id=cycle_id):
            persisted.append(dict(self._repo.upsert(insight)))
        return persisted

    def build_expert_review_queue(
        self,
        candidates_or_insights: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for item in candidates_or_insights or []:
            candidate = _extract_candidate_edge_payload(item)
            if not candidate:
                continue
            items.append(
                {
                    "asset_type": "candidate_edge",
                    "asset_key": candidate["candidate_edge_id"],
                    "review_status": str(
                        candidate.get("review_status") or REVIEW_STATUS_PENDING
                    ),
                    "priority_bucket": str(
                        candidate.get("review_priority") or "medium"
                    ),
                    "source_entity_id": candidate.get("source_entity_id"),
                    "target_entity_id": candidate.get("target_entity_id"),
                    "source_name": candidate.get("source_name"),
                    "target_name": candidate.get("target_name"),
                    "relationship_type": candidate.get("relationship_type"),
                    "confidence": candidate.get("confidence"),
                    "signals": list(candidate.get("signals") or []),
                    "decision_basis": "",
                    "needs_manual_review": True,
                    "candidate_edge": dict(candidate),
                }
            )
        items.sort(
            key=lambda item: (-float(item.get("confidence") or 0.0), item["asset_key"])
        )
        return {
            "contract_version": KG_NODE_SELF_LEARNING_CONTRACT_VERSION,
            "asset_type": "candidate_edge",
            "total_count": len(items),
            "pending_count": sum(
                1
                for item in items
                if item.get("review_status") == REVIEW_STATUS_PENDING
            ),
            "items": items,
        }

    def apply_reviewed_edges(
        self,
        reviewed_items: Sequence[Mapping[str, Any]],
        *,
        reviewer: str = "expert_review",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        accepted = [
            _extract_candidate_edge_payload(item)
            for item in reviewed_items or []
            if _review_status(item) == REVIEW_STATUS_ACCEPTED
        ]
        accepted = [item for item in accepted if item]
        if not accepted:
            return {"applied": 0, "skipped": 0, "dry_run": bool(dry_run), "items": []}

        traces: List[Dict[str, Any]] = []
        applied = 0
        skipped = 0
        with self._db.session_scope() as session:
            type_cache = _relationship_type_cache(session)
            for candidate in accepted:
                rel_type = (
                    str(candidate.get("relationship_type") or "RELATED_TO")
                    .strip()
                    .upper()
                )
                source_id = str(candidate.get("source_entity_id") or "").strip()
                target_id = str(candidate.get("target_entity_id") or "").strip()
                if not source_id or not target_id or source_id == target_id:
                    skipped += 1
                    traces.append(
                        {
                            "candidate_edge_id": candidate.get("candidate_edge_id"),
                            "skipped": "invalid_endpoint",
                        }
                    )
                    continue
                if _edge_exists(session, source_id, target_id, rel_type):
                    skipped += 1
                    traces.append(
                        {
                            "candidate_edge_id": candidate.get("candidate_edge_id"),
                            "skipped": "edge_exists",
                        }
                    )
                    continue
                if dry_run:
                    traces.append(
                        {
                            "candidate_edge_id": candidate.get("candidate_edge_id"),
                            "dry_run": True,
                        }
                    )
                    continue
                rel_type_id = _resolve_relationship_type_id(
                    session, type_cache, rel_type
                )
                relationship = EntityRelationship(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relationship_type_id=rel_type_id,
                    confidence=_clamp_confidence(candidate.get("confidence")),
                    created_by_module=KG_NODE_SELF_LEARNING_MODULE,
                    evidence=json.dumps(
                        {
                            "candidate_edge_id": candidate.get("candidate_edge_id"),
                            "reviewer": reviewer,
                            "signals": list(candidate.get("signals") or []),
                        },
                        ensure_ascii=False,
                    ),
                    relationship_metadata={
                        "source": KG_NODE_SELF_LEARNING_SOURCE,
                        "review_status": REVIEW_STATUS_ACCEPTED,
                        "reviewer": reviewer,
                        "candidate_edge": dict(candidate),
                        "applied_at": _now_iso(),
                    },
                )
                session.add(relationship)
                session.flush()
                neo4j_trace = self._project_accepted_edge_to_neo4j(
                    session,
                    relationship,
                    rel_type=rel_type,
                    candidate=candidate,
                )
                applied += 1
                traces.append(
                    {
                        "candidate_edge_id": candidate.get("candidate_edge_id"),
                        "relationship_id": str(relationship.id),
                        "source_entity_id": source_id,
                        "target_entity_id": target_id,
                        "relationship_type": rel_type,
                        "applied": True,
                        **neo4j_trace,
                    }
                )
        return {
            "applied": applied,
            "skipped": skipped,
            "dry_run": bool(dry_run),
            "items": traces,
        }

    def _project_accepted_edge_to_neo4j(
        self,
        session: Any,
        relationship: EntityRelationship,
        *,
        rel_type: str,
        candidate: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if self._neo4j_driver is None:
            return {"neo4j_written": False, "neo4j_status": "driver_missing"}
        try:
            from src.storage.neo4j_driver import (
                Neo4jEdge,
                entity_to_neo4j_node,
                relationship_to_neo4j_edge,
            )

            source = session.get(Entity, relationship.source_entity_id)
            target = session.get(Entity, relationship.target_entity_id)
            if source is None or target is None:
                return {"neo4j_written": False, "neo4j_status": "endpoint_missing"}

            source_node = entity_to_neo4j_node(source)
            target_node = entity_to_neo4j_node(target)
            edge = relationship_to_neo4j_edge(relationship, rel_type)
            edge = Neo4jEdge(
                source_id=edge.source_id,
                target_id=edge.target_id,
                relationship_type=edge.relationship_type,
                properties={
                    **dict(edge.properties or {}),
                    "relationship_id": str(relationship.id),
                    "candidate_edge_id": str(candidate.get("candidate_edge_id") or ""),
                    "expert_reviewed": True,
                    "review_status": REVIEW_STATUS_ACCEPTED,
                    "source": KG_NODE_SELF_LEARNING_SOURCE,
                },
            )
            self._neo4j_driver.create_node(source_node)
            self._neo4j_driver.create_node(target_node)
            written = bool(
                self._neo4j_driver.create_relationship(
                    edge, source_node.label, target_node.label
                )
            )
            return {
                "neo4j_written": written,
                "neo4j_status": "projected" if written else "projection_failed",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "neo4j_written": False,
                "neo4j_status": "projection_error",
                "neo4j_error": str(exc),
            }

    def _load_graph_snapshot(self) -> Dict[str, Any]:
        with self._db.session_scope() as session:
            entity_rows = (
                session.query(Entity)
                .order_by(Entity.confidence.desc(), Entity.created_at.desc())
                .limit(self._max_entities)
                .all()
            )
            entities = [_entity_to_node(row) for row in entity_rows]
            entity_ids = [node.id for node in entities]
            rel_type_by_id = _relationship_type_cache(session)
            relationships: List[Dict[str, Any]] = []
            if entity_ids:
                relationship_rows = (
                    session.query(EntityRelationship)
                    .filter(
                        or_(
                            EntityRelationship.source_entity_id.in_(entity_ids),
                            EntityRelationship.target_entity_id.in_(entity_ids),
                        )
                    )
                    .all()
                )
                for rel in relationship_rows:
                    rel_type = (
                        rel_type_by_id.get(str(rel.relationship_type_id), {}).get(
                            "relationship_type"
                        )
                        or "RELATED"
                    )
                    relationships.append(
                        {
                            "source_entity_id": str(rel.source_entity_id),
                            "target_entity_id": str(rel.target_entity_id),
                            "relationship_type": str(rel_type).upper(),
                            "confidence": float(rel.confidence or 0.0),
                        }
                    )
            existing_edges = {
                (item["source_entity_id"], item["target_entity_id"])
                for item in relationships
            }
            existing_edges.update(
                (target, source) for source, target in list(existing_edges)
            )
            existing_typed_edges = {
                (
                    item["source_entity_id"],
                    item["target_entity_id"],
                    item["relationship_type"],
                )
                for item in relationships
            }
            return {
                "entities": entities,
                "relationships": relationships,
                "existing_edges": existing_edges,
                "existing_typed_edges": existing_typed_edges,
            }

    def _iter_document_candidates(
        self,
        entities: Sequence[EntityNode],
        existing_edges: set[tuple[str, str]],
    ) -> Iterable[EdgeCandidate]:
        by_document: Dict[str, List[EntityNode]] = defaultdict(list)
        for node in entities:
            by_document[node.document_id].append(node)
        for document_id, nodes in by_document.items():
            ordered = sorted(nodes, key=lambda item: (item.position, item.name))
            for index, left in enumerate(ordered):
                window = ordered[index + 1 : index + 1 + self._document_neighbor_window]
                for right in window:
                    distance = abs(int(right.position) - int(left.position))
                    if self._max_position_gap and distance > self._max_position_gap:
                        continue
                    relation = _resolve_schema_relation(left, right)
                    if relation is None:
                        continue
                    source, target, rel_type, type_prior = relation
                    if (source.id, target.id) in existing_edges:
                        continue
                    proximity = _proximity_score(distance, self._max_position_gap)
                    confidence = _combine_scores(
                        type_prior, proximity, source.confidence, target.confidence
                    )
                    yield EdgeCandidate(
                        source_entity_id=source.id,
                        target_entity_id=target.id,
                        source_name=source.name,
                        target_name=target.name,
                        source_type=source.entity_type,
                        target_type=target.entity_type,
                        relationship_type=rel_type,
                        confidence=confidence,
                        signals=["schema_prior", "document_proximity"],
                        evidence={
                            "document_id": document_id,
                            "position_distance": distance,
                        },
                    )

    def _iter_alias_candidates(
        self,
        entities: Sequence[EntityNode],
        existing_edges: set[tuple[str, str]],
    ) -> Iterable[EdgeCandidate]:
        buckets: Dict[tuple[str, str], List[EntityNode]] = defaultdict(list)
        for node in entities:
            key = (_normalized_name(node.name)[:1], node.entity_type)
            if key[0]:
                buckets[key].append(node)
        for nodes in buckets.values():
            if len(nodes) < 2:
                continue
            for index, left in enumerate(nodes):
                for right in nodes[index + 1 :]:
                    if (left.id, right.id) in existing_edges:
                        continue
                    similarity = _name_similarity(left, right)
                    if similarity < 0.64:
                        continue
                    confidence = round(
                        0.45
                        + similarity * 0.45
                        + min(left.confidence, right.confidence) * 0.1,
                        4,
                    )
                    yield EdgeCandidate(
                        source_entity_id=left.id,
                        target_entity_id=right.id,
                        source_name=left.name,
                        target_name=right.name,
                        source_type=left.entity_type,
                        target_type=right.entity_type,
                        relationship_type="VARIANT_OF",
                        confidence=min(confidence, 0.96),
                        signals=["lexical_alias_similarity", "same_type"],
                        evidence={"name_similarity": round(similarity, 4)},
                    )

    def _iter_two_hop_candidates(
        self,
        entities: Sequence[EntityNode],
        relationships: Sequence[Mapping[str, Any]],
        existing_edges: set[tuple[str, str]],
        existing_typed_edges: set[tuple[str, str, str]],
    ) -> Iterable[EdgeCandidate]:
        entity_by_id = {node.id: node for node in entities}
        outgoing: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
        for rel in relationships:
            outgoing[str(rel.get("source_entity_id") or "")].append(rel)
        seen: set[tuple[str, str, str]] = set()
        for source_id, first_hop_edges in outgoing.items():
            source = entity_by_id.get(source_id)
            if source is None:
                continue
            for first in first_hop_edges:
                middle_id = str(first.get("target_entity_id") or "")
                first_type = str(first.get("relationship_type") or "").upper()
                for second in outgoing.get(middle_id, []):
                    target_id = str(second.get("target_entity_id") or "")
                    if not target_id or target_id == source_id:
                        continue
                    target = entity_by_id.get(target_id)
                    if target is None:
                        continue
                    rel_type = _resolve_two_hop_relation(
                        first_type, str(second.get("relationship_type") or "").upper()
                    )
                    key = (source_id, target_id, rel_type)
                    if (
                        key in seen
                        or key in existing_typed_edges
                        or (source_id, target_id) in existing_edges
                    ):
                        continue
                    seen.add(key)
                    first_conf = float(first.get("confidence") or 0.5)
                    second_conf = float(second.get("confidence") or 0.5)
                    confidence = round(
                        0.48
                        + min(first_conf, second_conf) * 0.28
                        + source.confidence * 0.08
                        + target.confidence * 0.08,
                        4,
                    )
                    yield EdgeCandidate(
                        source_entity_id=source.id,
                        target_entity_id=target.id,
                        source_name=source.name,
                        target_name=target.name,
                        source_type=source.entity_type,
                        target_type=target.entity_type,
                        relationship_type=rel_type,
                        confidence=min(confidence, 0.9),
                        signals=["two_hop_path_closure", "graph_link_prediction"],
                        evidence={
                            "middle_entity_id": middle_id,
                            "first_relationship_type": first_type,
                            "second_relationship_type": str(
                                second.get("relationship_type") or ""
                            ).upper(),
                        },
                    )

    @staticmethod
    def _merge_candidate(
        merged: Dict[tuple[str, str, str], EdgeCandidate],
        candidate: EdgeCandidate,
    ) -> None:
        key = (
            candidate.source_entity_id,
            candidate.target_entity_id,
            candidate.relationship_type,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = candidate
            return
        existing.confidence = min(
            0.99, max(existing.confidence, candidate.confidence) + 0.04
        )
        existing.signals = list(dict.fromkeys([*existing.signals, *candidate.signals]))
        existing.evidence.setdefault("merged_evidence", [])
        existing.evidence["merged_evidence"].append(candidate.evidence)


def export_review_queue_jsonl(
    review_queue: Mapping[str, Any], output_path: str | Path
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in review_queue.get("items") or []:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def load_review_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text_line = line.strip()
        if not text_line:
            continue
        payload = json.loads(text_line)
        if isinstance(payload, Mapping):
            items.append(dict(payload))
    return items


def _entity_to_node(row: Entity) -> EntityNode:
    entity_type = getattr(row.type, "value", row.type)
    return EntityNode(
        id=str(row.id),
        name=str(row.name or "").strip(),
        entity_type=str(entity_type or "other").strip().lower(),
        document_id=str(row.document_id),
        confidence=_clamp_confidence(row.confidence),
        position=int(row.position or 0),
        length=int(row.length or 0),
        alternative_names=tuple(
            str(item).strip()
            for item in row.alternative_names or []
            if str(item).strip()
        ),
    )


def _relationship_type_cache(session: Any) -> Dict[str, Dict[str, Any]]:
    rows = session.execute(
        text("SELECT id, relationship_name, relationship_type FROM relationship_types")
    ).all()
    cache: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        entry = {
            "id": row[0],
            "relationship_name": str(row[1] or "").strip(),
            "relationship_type": str(row[2] or "").strip().upper(),
        }
        for key in (
            str(entry["id"]),
            entry["relationship_name"],
            entry["relationship_type"],
        ):
            if key:
                cache[str(key).upper()] = entry
                cache[str(key)] = entry
    return cache


def _resolve_relationship_type_id(
    session: Any, cache: Dict[str, Dict[str, Any]], raw_type: str
) -> Any:
    normalized = str(raw_type or "RELATED_TO").strip().upper().replace(" ", "_")
    cached = cache.get(normalized)
    if cached is not None:
        return cached["id"]
    rel_id = str(uuid.uuid4())
    session.execute(
        text(
            """
            INSERT INTO relationship_types
                (id, relationship_name, relationship_type, description, category, confidence_baseline, created_at)
            VALUES
                (:id, :relationship_name, :relationship_type, :description, NULL, :confidence_baseline, :created_at)
            """
        ),
        {
            "id": rel_id,
            "relationship_name": normalized.lower(),
            "relationship_type": normalized,
            "description": f"Self-learned candidate relationship: {normalized}",
            "confidence_baseline": 0.5,
            "created_at": datetime.now(timezone.utc),
        },
    )
    entry = {
        "id": rel_id,
        "relationship_name": normalized.lower(),
        "relationship_type": normalized,
    }
    cache[normalized] = entry
    cache[rel_id] = entry
    return rel_id


def _edge_exists(session: Any, source_id: str, target_id: str, rel_type: str) -> bool:
    rows = session.execute(
        text(
            """
            SELECT 1
            FROM entity_relationships er
            JOIN relationship_types rt ON rt.id = er.relationship_type_id
            WHERE er.source_entity_id = :source_id
              AND er.target_entity_id = :target_id
              AND upper(rt.relationship_type) = :relationship_type
            LIMIT 1
            """
        ),
        {
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": str(rel_type or "RELATED_TO").upper(),
        },
    ).first()
    return rows is not None


def _resolve_schema_relation(
    left: EntityNode, right: EntityNode
) -> Optional[tuple[EntityNode, EntityNode, str, float]]:
    pair = (left.entity_type, right.entity_type)
    if pair == ("formula", "herb"):
        return left, right, "CONTAINS", 0.82
    if pair == ("herb", "formula"):
        return right, left, "CONTAINS", 0.82
    if pair == ("formula", "syndrome"):
        return left, right, "TREATS", 0.78
    if pair == ("syndrome", "formula"):
        return right, left, "TREATS", 0.78
    if pair == ("herb", "syndrome"):
        return left, right, "TREATS", 0.67
    if pair == ("syndrome", "herb"):
        return right, left, "TREATS", 0.67
    if pair in {("herb", "efficacy"), ("formula", "efficacy")}:
        return left, right, "EFFICACY", 0.7
    if pair in {("efficacy", "herb"), ("efficacy", "formula")}:
        return right, left, "EFFICACY", 0.7
    return None


def _resolve_two_hop_relation(first_type: str, second_type: str) -> str:
    first = str(first_type or "").upper()
    second = str(second_type or "").upper()
    if first in _COMPOSITION_RELATIONS and second in _THERAPEUTIC_RELATIONS:
        return "TREATS"
    if second == "EFFICACY":
        return "EFFICACY"
    if first == second and first:
        return first
    return "RELATED_TO"


def _combine_scores(*scores: float) -> float:
    values = [_clamp_confidence(score) for score in scores if score is not None]
    if not values:
        return 0.0
    # Harmonic-ish conservative blend: all signals must carry some weight.
    weighted = values[0] * 0.42
    tail = values[1:]
    if tail:
        weighted += sum(tail) / len(tail) * 0.58
    return round(max(0.0, min(0.98, weighted)), 4)


def _proximity_score(distance: int, max_gap: int) -> float:
    if max_gap <= 0:
        return 0.7
    bounded = max(0.0, min(1.0, 1.0 - float(distance) / float(max_gap)))
    return round(0.45 + bounded * 0.45, 4)


def _name_similarity(left: EntityNode, right: EntityNode) -> float:
    left_names = [left.name, *left.alternative_names]
    right_names = [right.name, *right.alternative_names]
    return max(
        (_dice_name_similarity(a, b) for a in left_names for b in right_names),
        default=0.0,
    )


def _dice_name_similarity(left: str, right: str) -> float:
    a = _normalized_name(left)
    b = _normalized_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
        return 0.82
    a_grams = _char_ngrams(a)
    b_grams = _char_ngrams(b)
    if not a_grams or not b_grams:
        return 0.0
    overlap = len(a_grams & b_grams)
    return (2.0 * overlap) / (len(a_grams) + len(b_grams))


def _char_ngrams(value: str) -> set[str]:
    if len(value) <= 1:
        return {value}
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _normalized_name(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())


def _review_priority(confidence: float, signals: Sequence[str]) -> str:
    score = _clamp_confidence(confidence)
    if score >= 0.82 and len(set(signals)) >= 2:
        return "high"
    if score >= 0.68:
        return "medium"
    return "low"


def _review_status(item: Mapping[str, Any]) -> str:
    status = (
        str(item.get("review_status") or item.get("expert_review_status") or "")
        .strip()
        .lower()
    )
    if status:
        return status
    candidate = (
        item.get("candidate_edge")
        if isinstance(item.get("candidate_edge"), Mapping)
        else {}
    )
    return str(candidate.get("review_status") or "").strip().lower()


def _extract_candidate_edge_payload(item: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(item, Mapping):
        return {}
    weak_edge_payload = extract_weak_edge_candidate_payload(item)
    if weak_edge_payload:
        candidate = dict(weak_edge_payload.get("candidate_edge") or {})
    elif isinstance(item.get("candidate_edge"), Mapping):
        candidate = dict(item["candidate_edge"])
    elif str(item.get("insight_type") or "") == "candidate_edge":
        refs = item.get("evidence_refs_json") or item.get("evidence_refs") or []
        candidate = {}
        if isinstance(refs, list) and refs and isinstance(refs[0], Mapping):
            first = dict(refs[0])
            nested = first.get("candidate_edge")
            candidate = dict(nested) if isinstance(nested, Mapping) else first
    else:
        candidate = dict(item)
    if not str(candidate.get("candidate_edge_id") or "").strip():
        return {}
    review_status = _review_status(item) or str(
        candidate.get("review_status") or REVIEW_STATUS_PENDING
    )
    candidate["review_status"] = review_status
    return candidate


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "KG_NODE_SELF_LEARNING_CONTRACT_VERSION",
    "KG_NODE_SELF_LEARNING_SOURCE",
    "KGNodeSelfLearningEnhancer",
    "export_review_queue_jsonl",
    "load_review_jsonl",
]
