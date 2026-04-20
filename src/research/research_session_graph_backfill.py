"""Backfill structured research graph nodes and edges from structured records."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from src.storage.graph_schema import NodeLabel, RelType, resolve_node_label
from src.storage.neo4j_driver import Neo4jEdge, Neo4jNode

_GRAPH_IDENTIFIER_PATTERN = re.compile(r"[^0-9A-Za-z_]+")


def _compact_graph_properties(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }


def _normalize_graph_identifier(value: Any, default: str) -> str:
    text = _GRAPH_IDENTIFIER_PATTERN.sub("_", str(value or "").strip())
    text = text.strip("_")
    if not text:
        text = default
    if text[0].isdigit():
        text = f"{default}_{text}"
    return text


def _normalize_graph_label(value: Any, default: str = NodeLabel.ENTITY.value) -> str:
    normalized = _normalize_graph_identifier(value, default)
    parts = [part for part in normalized.split("_") if part]
    if not parts:
        return default
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _normalize_graph_relationship_type(value: Any, default: str = RelType.RELATED_TO.value) -> str:
    return _normalize_graph_identifier(value, default).upper()


def _observe_entity_raw_type(entity_record: Mapping[str, Any]) -> str:
    metadata = entity_record.get("entity_metadata") if isinstance(entity_record.get("entity_metadata"), dict) else {}
    return str(metadata.get("raw_type") or entity_record.get("type") or "other").strip() or "other"


def build_research_session_graph_properties(session_record: Mapping[str, Any]) -> Dict[str, Any]:
    payload = {
        "cycle_id": str(session_record.get("cycle_id") or "").strip(),
        "cycle_name": str(session_record.get("cycle_name") or "").strip(),
        "status": str(session_record.get("status") or "").strip(),
        "current_phase": str(session_record.get("current_phase") or "").strip(),
        "research_objective": str(session_record.get("research_objective") or "").strip(),
        "research_scope": str(session_record.get("research_scope") or "").strip(),
        "started_at": session_record.get("started_at"),
        "completed_at": session_record.get("completed_at"),
        "duration": session_record.get("duration"),
        "created_at": session_record.get("created_at"),
        "updated_at": session_record.get("updated_at"),
    }
    return _compact_graph_properties(payload)


def build_research_phase_execution_graph_properties(phase_record: Mapping[str, Any]) -> Dict[str, Any]:
    payload = {
        "phase": str(phase_record.get("phase") or "").strip(),
        "status": str(phase_record.get("status") or "").strip(),
        "started_at": phase_record.get("started_at"),
        "completed_at": phase_record.get("completed_at"),
        "duration": phase_record.get("duration"),
        "cycle_id": str(phase_record.get("cycle_id") or "").strip(),
        "created_at": phase_record.get("created_at"),
        "error_detail": str(phase_record.get("error_detail") or "").strip(),
    }
    return _compact_graph_properties(payload)


def build_research_artifact_graph_properties(artifact_record: Mapping[str, Any]) -> Dict[str, Any]:
    payload = {
        "name": str(artifact_record.get("name") or "").strip(),
        "artifact_type": str(artifact_record.get("artifact_type") or "").strip(),
        "description": str(artifact_record.get("description") or "").strip(),
        "file_path": str(artifact_record.get("file_path") or "").strip(),
        "mime_type": str(artifact_record.get("mime_type") or "").strip(),
        "size_bytes": artifact_record.get("size_bytes"),
        "cycle_id": str(artifact_record.get("cycle_id") or "").strip(),
        "phase_execution_id": str(artifact_record.get("phase_execution_id") or "").strip(),
        "created_at": artifact_record.get("created_at"),
        "updated_at": artifact_record.get("updated_at"),
    }
    return _compact_graph_properties(payload)


def build_observe_entity_graph_properties(entity_record: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = entity_record.get("entity_metadata") if isinstance(entity_record.get("entity_metadata"), dict) else {}
    payload = {
        "entity_id": str(entity_record.get("id") or "").strip(),
        "name": str(entity_record.get("name") or "").strip(),
        "entity_type": _observe_entity_raw_type(entity_record),
        "confidence": entity_record.get("confidence"),
        "position": entity_record.get("position"),
        "length": entity_record.get("length"),
        "alternative_names": list(entity_record.get("alternative_names") or []),
        "description": str(entity_record.get("description") or "").strip(),
        "cycle_id": str(metadata.get("cycle_id") or "").strip(),
        "phase_execution_id": str(metadata.get("phase_execution_id") or "").strip(),
        "document_id": str(entity_record.get("document_id") or "").strip(),
        "document_urn": str(metadata.get("document_urn") or "").strip(),
        "document_title": str(metadata.get("document_title") or "").strip(),
        "created_at": entity_record.get("created_at"),
        "updated_at": entity_record.get("updated_at"),
    }
    return _compact_graph_properties(payload)


def _observe_document_version_metadata(document_record: Mapping[str, Any]) -> Dict[str, Any]:
    version_metadata = document_record.get("version_metadata") if isinstance(document_record.get("version_metadata"), dict) else {}
    if version_metadata:
        return dict(version_metadata)
    metadata = document_record.get("metadata") if isinstance(document_record.get("metadata"), dict) else {}
    nested_version_metadata = metadata.get("version_metadata") if isinstance(metadata.get("version_metadata"), dict) else {}
    return dict(nested_version_metadata)


def _observe_version_lineage_node_id(document_record: Mapping[str, Any]) -> str:
    version_metadata = _observe_document_version_metadata(document_record)
    lineage_key = str(version_metadata.get("version_lineage_key") or version_metadata.get("work_fragment_key") or "").strip()
    if not lineage_key:
        return ""
    return f"version_lineage::{lineage_key}"


def _observe_version_witness_node_id(document_record: Mapping[str, Any]) -> str:
    version_metadata = _observe_document_version_metadata(document_record)
    witness_key = str(version_metadata.get("witness_key") or document_record.get("id") or document_record.get("urn") or "").strip()
    if not witness_key:
        return ""
    return f"version_witness::{witness_key}"


def build_observe_version_lineage_graph_properties(document_record: Mapping[str, Any]) -> Dict[str, Any]:
    version_metadata = _observe_document_version_metadata(document_record)
    payload = {
        "version_lineage_key": str(version_metadata.get("version_lineage_key") or "").strip(),
        "work_fragment_key": str(version_metadata.get("work_fragment_key") or "").strip(),
        "work_title": str(version_metadata.get("work_title") or document_record.get("work_title") or "").strip(),
        "fragment_title": str(version_metadata.get("fragment_title") or document_record.get("fragment_title") or "").strip(),
        "dynasty": str(version_metadata.get("dynasty") or document_record.get("dynasty") or "").strip(),
        "author": str(version_metadata.get("author") or document_record.get("author") or "").strip(),
        "edition": str(version_metadata.get("edition") or document_record.get("edition") or "").strip(),
        "lineage_id_source": "version_lineage_key" if version_metadata.get("version_lineage_key") else "work_fragment_key",
    }
    return _compact_graph_properties(payload)


def build_observe_version_witness_graph_properties(document_record: Mapping[str, Any]) -> Dict[str, Any]:
    version_metadata = _observe_document_version_metadata(document_record)
    payload = {
        "witness_key": str(version_metadata.get("witness_key") or document_record.get("id") or document_record.get("urn") or "").strip(),
        "version_lineage_key": str(version_metadata.get("version_lineage_key") or document_record.get("version_lineage_key") or "").strip(),
        "work_fragment_key": str(version_metadata.get("work_fragment_key") or document_record.get("work_fragment_key") or "").strip(),
        "catalog_id": str(version_metadata.get("catalog_id") or document_record.get("catalog_id") or "").strip(),
        "work_title": str(version_metadata.get("work_title") or document_record.get("work_title") or "").strip(),
        "fragment_title": str(version_metadata.get("fragment_title") or document_record.get("fragment_title") or "").strip(),
        "dynasty": str(version_metadata.get("dynasty") or document_record.get("dynasty") or "").strip(),
        "author": str(version_metadata.get("author") or document_record.get("author") or "").strip(),
        "edition": str(version_metadata.get("edition") or document_record.get("edition") or "").strip(),
        "source_type": str(version_metadata.get("source_type") or document_record.get("source_type") or "").strip(),
        "source_ref": str(version_metadata.get("source_ref") or document_record.get("urn") or "").strip(),
        "document_id": str(document_record.get("id") or "").strip(),
        "document_urn": str(document_record.get("urn") or "").strip(),
        "document_title": str(document_record.get("title") or "").strip(),
        "cycle_id": str(document_record.get("cycle_id") or "").strip(),
        "phase_execution_id": str(document_record.get("phase_execution_id") or "").strip(),
    }
    return _compact_graph_properties(payload)


def build_research_session_graph_nodes(session_records: Sequence[Mapping[str, Any]]) -> List[Neo4jNode]:
    nodes: List[Neo4jNode] = []
    for session_record in session_records:
        cycle_id = str(session_record.get("cycle_id") or "").strip()
        if not cycle_id:
            continue
        nodes.append(
            Neo4jNode(
                id=cycle_id,
                label=NodeLabel.RESEARCH_SESSION.value,
                properties=build_research_session_graph_properties(session_record),
            )
        )
    return nodes


def build_research_phase_execution_graph_nodes(
    cycle_id: str,
    phase_records: Sequence[Mapping[str, Any]],
) -> List[Neo4jNode]:
    normalized_cycle_id = str(cycle_id or "").strip()
    nodes: List[Neo4jNode] = []
    for phase_record in phase_records:
        phase_id = str(phase_record.get("id") or "").strip()
        if not phase_id:
            continue
        properties = build_research_phase_execution_graph_properties(
            {
                **dict(phase_record),
                "cycle_id": normalized_cycle_id or str(phase_record.get("cycle_id") or "").strip(),
            }
        )
        nodes.append(
            Neo4jNode(
                id=phase_id,
                label=NodeLabel.RESEARCH_PHASE_EXECUTION.value,
                properties=properties,
            )
        )
    return nodes


def build_research_artifact_graph_nodes(
    cycle_id: str,
    artifact_records: Sequence[Mapping[str, Any]],
) -> List[Neo4jNode]:
    normalized_cycle_id = str(cycle_id or "").strip()
    nodes: List[Neo4jNode] = []
    for artifact_record in artifact_records:
        artifact_id = str(artifact_record.get("id") or "").strip()
        if not artifact_id:
            continue
        properties = build_research_artifact_graph_properties(
            {
                **dict(artifact_record),
                "cycle_id": normalized_cycle_id or str(artifact_record.get("cycle_id") or "").strip(),
            }
        )
        nodes.append(
            Neo4jNode(
                id=artifact_id,
                label=NodeLabel.RESEARCH_ARTIFACT.value,
                properties=properties,
            )
        )
    return nodes


def build_observe_entity_graph_nodes(
    observe_documents: Sequence[Mapping[str, Any]],
) -> List[Neo4jNode]:
    nodes: List[Neo4jNode] = []
    seen: set[tuple[str, str]] = set()
    for document_record in observe_documents:
        entities = document_record.get("entities") if isinstance(document_record.get("entities"), list) else []
        for entity_record in entities:
            if not isinstance(entity_record, Mapping):
                continue
            entity_name = str(entity_record.get("name") or "").strip()
            if not entity_name:
                continue
            label = _normalize_graph_label(_observe_entity_raw_type(entity_record), NodeLabel.ENTITY.value)
            node_id = f"entity::{entity_name}"
            key = (label, node_id)
            if key in seen:
                continue
            seen.add(key)
            nodes.append(
                Neo4jNode(
                    id=node_id,
                    label=label,
                    properties=build_observe_entity_graph_properties(entity_record),
                )
            )
    return nodes


def build_observe_version_graph_nodes(
    observe_documents: Sequence[Mapping[str, Any]],
) -> List[Neo4jNode]:
    nodes: List[Neo4jNode] = []
    seen: set[tuple[str, str]] = set()
    for document_record in observe_documents:
        version_metadata = _observe_document_version_metadata(document_record)
        if not version_metadata:
            continue

        lineage_node_id = _observe_version_lineage_node_id(document_record)
        if lineage_node_id:
            lineage_key = ("VersionLineage", lineage_node_id)
            if lineage_key not in seen:
                seen.add(lineage_key)
                nodes.append(
                    Neo4jNode(
                        id=lineage_node_id,
                        label=NodeLabel.VERSION_LINEAGE.value,
                        properties=build_observe_version_lineage_graph_properties(document_record),
                    )
                )

        witness_node_id = _observe_version_witness_node_id(document_record)
        if witness_node_id:
            witness_key = ("VersionWitness", witness_node_id)
            if witness_key not in seen:
                seen.add(witness_key)
                nodes.append(
                    Neo4jNode(
                        id=witness_node_id,
                        label=NodeLabel.VERSION_WITNESS.value,
                        properties=build_observe_version_witness_graph_properties(document_record),
                    )
                )
    return nodes


def build_research_graph_edges(
    cycle_id: str,
    phase_records: Sequence[Mapping[str, Any]],
    artifact_records: Sequence[Mapping[str, Any]],
) -> List[Tuple[Neo4jEdge, str, str]]:
    normalized_cycle_id = str(cycle_id or "").strip()
    edges: List[Tuple[Neo4jEdge, str, str]] = []

    for phase_record in phase_records:
        phase_id = str(phase_record.get("id") or "").strip()
        if not normalized_cycle_id or not phase_id:
            continue
        edges.append(
            (
                Neo4jEdge(
                    source_id=normalized_cycle_id,
                    target_id=phase_id,
                    relationship_type=RelType.HAS_PHASE.value,
                    properties=_compact_graph_properties(
                        {
                            "cycle_id": normalized_cycle_id,
                            "phase": str(phase_record.get("phase") or "").strip(),
                        }
                    ),
                ),
                NodeLabel.RESEARCH_SESSION.value,
                NodeLabel.RESEARCH_PHASE_EXECUTION.value,
            )
        )

    for artifact_record in artifact_records:
        artifact_id = str(artifact_record.get("id") or "").strip()
        if not artifact_id:
            continue
        phase_execution_id = str(artifact_record.get("phase_execution_id") or "").strip()
        edge_properties = _compact_graph_properties(
            {
                "cycle_id": normalized_cycle_id,
                "artifact_type": str(artifact_record.get("artifact_type") or "").strip(),
            }
        )
        if phase_execution_id:
            edges.append(
                (
                    Neo4jEdge(
                        source_id=phase_execution_id,
                        target_id=artifact_id,
                        relationship_type=RelType.GENERATED.value,
                        properties=edge_properties,
                    ),
                    NodeLabel.RESEARCH_PHASE_EXECUTION.value,
                    NodeLabel.RESEARCH_ARTIFACT.value,
                )
            )
            continue
        if not normalized_cycle_id:
            continue
        edges.append(
            (
                Neo4jEdge(
                    source_id=normalized_cycle_id,
                    target_id=artifact_id,
                    relationship_type=RelType.HAS_ARTIFACT.value,
                    properties=edge_properties,
                ),
                NodeLabel.RESEARCH_SESSION.value,
                NodeLabel.RESEARCH_ARTIFACT.value,
            )
        )

    return edges


def build_observe_graph_edges(
    cycle_id: str,
    observe_phase_id: str,
    observe_documents: Sequence[Mapping[str, Any]],
) -> List[Tuple[Neo4jEdge, str, str]]:
    normalized_cycle_id = str(cycle_id or "").strip()
    normalized_phase_id = str(observe_phase_id or "").strip()
    edges: List[Tuple[Neo4jEdge, str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def _append_edge(edge: Neo4jEdge, source_label: str, target_label: str) -> None:
        key = (source_label, edge.source_id, edge.relationship_type, target_label, edge.target_id)
        if key in seen:
            return
        seen.add(key)
        edges.append((edge, source_label, target_label))

    for document_record in observe_documents:
        document_id = str(document_record.get("id") or "").strip()
        document_urn = str(document_record.get("urn") or "").strip()
        document_title = str(document_record.get("title") or "").strip()
        for entity_record in document_record.get("entities") if isinstance(document_record.get("entities"), list) else []:
            if not isinstance(entity_record, Mapping):
                continue
            entity_name = str(entity_record.get("name") or "").strip()
            if not entity_name or not normalized_phase_id:
                continue
            raw_type = _observe_entity_raw_type(entity_record)
            entity_label = _normalize_graph_label(raw_type, NodeLabel.ENTITY.value)
            _append_edge(
                Neo4jEdge(
                    source_id=normalized_phase_id,
                    target_id=f"entity::{entity_name}",
                    relationship_type=RelType.CAPTURED.value,
                    properties=_compact_graph_properties(
                        {
                            "cycle_id": normalized_cycle_id,
                            "phase": "observe",
                            "phase_execution_id": normalized_phase_id,
                            "document_id": document_id,
                            "document_urn": document_urn,
                            "document_title": document_title,
                        }
                    ),
                ),
                NodeLabel.RESEARCH_PHASE_EXECUTION.value,
                entity_label,
            )

        relationships = document_record.get("semantic_relationships") if isinstance(document_record.get("semantic_relationships"), list) else []
        for relationship_record in relationships:
            if not isinstance(relationship_record, Mapping):
                continue
            source_name = str(relationship_record.get("source_entity_name") or "").strip()
            target_name = str(relationship_record.get("target_entity_name") or "").strip()
            if not source_name or not target_name:
                continue
            source_type = str(relationship_record.get("source_entity_type") or "entity").strip() or "entity"
            target_type = str(relationship_record.get("target_entity_type") or "entity").strip() or "entity"
            relationship_metadata = relationship_record.get("relationship_metadata") if isinstance(relationship_record.get("relationship_metadata"), dict) else {}
            _append_edge(
                Neo4jEdge(
                    source_id=f"entity::{source_name}",
                    target_id=f"entity::{target_name}",
                    relationship_type=_normalize_graph_relationship_type(
                        relationship_record.get("relationship_type")
                        or relationship_record.get("relationship_name")
                        or "RELATED_TO"
                    ),
                    properties=_compact_graph_properties(
                        {
                            "cycle_id": normalized_cycle_id or str(relationship_metadata.get("cycle_id") or "").strip(),
                            "phase": "observe",
                            "phase_execution_id": str(
                                relationship_metadata.get("phase_execution_id")
                                or document_record.get("phase_execution_id")
                                or normalized_phase_id
                            ).strip(),
                            "document_id": document_id or str(relationship_metadata.get("document_id") or "").strip(),
                            "document_urn": document_urn or str(relationship_metadata.get("document_urn") or "").strip(),
                            "document_title": document_title or str(relationship_metadata.get("document_title") or "").strip(),
                            "confidence": relationship_record.get("confidence"),
                            "evidence": relationship_record.get("evidence"),
                            "relationship_name": relationship_record.get("relationship_name"),
                            "created_by_module": relationship_record.get("created_by_module"),
                            "created_at": relationship_record.get("created_at"),
                        }
                    ),
                ),
                _normalize_graph_label(source_type, NodeLabel.ENTITY.value),
                _normalize_graph_label(target_type, NodeLabel.ENTITY.value),
            )

    return edges


def build_observe_version_graph_edges(
    cycle_id: str,
    observe_phase_id: str,
    observe_documents: Sequence[Mapping[str, Any]],
) -> List[Tuple[Neo4jEdge, str, str]]:
    normalized_cycle_id = str(cycle_id or "").strip()
    normalized_phase_id = str(observe_phase_id or "").strip()
    edges: List[Tuple[Neo4jEdge, str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def _append_edge(edge: Neo4jEdge, source_label: str, target_label: str) -> None:
        key = (source_label, edge.source_id, edge.relationship_type, target_label, edge.target_id)
        if key in seen:
            return
        seen.add(key)
        edges.append((edge, source_label, target_label))

    for document_record in observe_documents:
        version_metadata = _observe_document_version_metadata(document_record)
        if not version_metadata:
            continue

        witness_node_id = _observe_version_witness_node_id(document_record)
        lineage_node_id = _observe_version_lineage_node_id(document_record)
        document_id = str(document_record.get("id") or "").strip()
        document_urn = str(document_record.get("urn") or "").strip()
        document_title = str(document_record.get("title") or "").strip()

        if normalized_phase_id and witness_node_id:
            _append_edge(
                Neo4jEdge(
                    source_id=normalized_phase_id,
                    target_id=witness_node_id,
                    relationship_type=RelType.OBSERVED_WITNESS.value,
                    properties=_compact_graph_properties(
                        {
                            "cycle_id": normalized_cycle_id,
                            "phase": "observe",
                            "phase_execution_id": normalized_phase_id,
                            "document_id": document_id,
                            "document_urn": document_urn,
                            "document_title": document_title,
                            "version_lineage_key": str(version_metadata.get("version_lineage_key") or "").strip(),
                            "witness_key": str(version_metadata.get("witness_key") or "").strip(),
                        }
                    ),
                ),
                NodeLabel.RESEARCH_PHASE_EXECUTION.value,
                NodeLabel.VERSION_WITNESS.value,
            )

        if witness_node_id and lineage_node_id:
            _append_edge(
                Neo4jEdge(
                    source_id=witness_node_id,
                    target_id=lineage_node_id,
                    relationship_type=RelType.BELONGS_TO_LINEAGE.value,
                    properties=_compact_graph_properties(
                        {
                            "cycle_id": normalized_cycle_id or str(document_record.get("cycle_id") or "").strip(),
                            "work_fragment_key": str(version_metadata.get("work_fragment_key") or "").strip(),
                            "version_lineage_key": str(version_metadata.get("version_lineage_key") or "").strip(),
                            "catalog_id": str(version_metadata.get("catalog_id") or document_record.get("catalog_id") or "").strip(),
                        }
                    ),
                ),
                NodeLabel.VERSION_WITNESS.value,
                NodeLabel.VERSION_LINEAGE.value,
            )

    return edges


def _iter_session_batches(repository: Any, batch_size: int) -> Iterable[List[Dict[str, Any]]]:
    effective_batch_size = max(int(batch_size or 0), 1)
    offset = 0
    while True:
        page = repository.list_sessions(limit=effective_batch_size, offset=offset)
        items = [item for item in (page.get("items") or []) if isinstance(item, dict)]
        if not items:
            break
        yield items
        offset += len(items)
        total = int(page.get("total") or 0)
        if offset >= total:
            break


def _iter_session_snapshot_batches(repository: Any, batch_size: int) -> Iterable[List[Dict[str, Any]]]:
    for session_batch in _iter_session_batches(repository, batch_size):
        snapshots: List[Dict[str, Any]] = []
        for session_record in session_batch:
            cycle_id = str(session_record.get("cycle_id") or "").strip()
            if not cycle_id:
                continue
            snapshot = repository.get_full_snapshot(cycle_id)
            if not isinstance(snapshot, dict):
                snapshot = dict(session_record)
                snapshot["phase_executions"] = repository.list_phase_executions(cycle_id)
                snapshot["artifacts"] = repository.list_artifacts(cycle_id)
            snapshots.append(snapshot)
        if snapshots:
            yield snapshots


def backfill_research_session_nodes(
    repository: Any,
    neo4j_driver: Any,
    *,
    batch_size: int = 200,
) -> Dict[str, Any]:
    if neo4j_driver is None:
        return {
            "status": "skipped",
            "batch_count": 0,
            "node_count": 0,
        }

    total_nodes = 0
    batch_count = 0
    for session_batch in _iter_session_batches(repository, batch_size):
        nodes = build_research_session_graph_nodes(session_batch)
        if not nodes:
            continue
        if neo4j_driver.batch_create_nodes(nodes) is False:
            raise RuntimeError("Neo4j batch_create_nodes returned False while backfilling ResearchSession nodes")
        batch_count += 1
        total_nodes += len(nodes)

    return {
        "status": "active",
        "batch_count": batch_count,
        "node_count": total_nodes,
    }


def backfill_structured_research_graph(
    repository: Any,
    neo4j_driver: Any,
    *,
    batch_size: int = 200,
) -> Dict[str, Any]:
    if neo4j_driver is None:
        return {
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
        }

    batch_count = 0
    session_node_count = 0
    phase_node_count = 0
    artifact_node_count = 0
    observe_entity_node_count = 0
    version_lineage_node_count = 0
    version_witness_node_count = 0
    has_phase_edge_count = 0
    generated_edge_count = 0
    has_artifact_edge_count = 0
    semantic_edge_count = 0
    captured_edge_count = 0
    observed_witness_edge_count = 0
    belongs_to_lineage_edge_count = 0

    for snapshot_batch in _iter_session_snapshot_batches(repository, batch_size):
        nodes: List[Neo4jNode] = []
        edges: List[Tuple[Neo4jEdge, str, str]] = []

        for snapshot in snapshot_batch:
            cycle_id = str(snapshot.get("cycle_id") or "").strip()
            if not cycle_id:
                continue

            session_nodes = build_research_session_graph_nodes([snapshot])
            phase_records = [item for item in (snapshot.get("phase_executions") or []) if isinstance(item, dict)]
            artifact_records = [item for item in (snapshot.get("artifacts") or []) if isinstance(item, dict)]
            observe_documents = [item for item in (snapshot.get("observe_documents") or []) if isinstance(item, dict)]
            phase_nodes = build_research_phase_execution_graph_nodes(cycle_id, phase_records)
            artifact_nodes = build_research_artifact_graph_nodes(cycle_id, artifact_records)
            observe_entity_nodes = build_observe_entity_graph_nodes(observe_documents)
            observe_version_nodes = build_observe_version_graph_nodes(observe_documents)
            batch_edges = build_research_graph_edges(cycle_id, phase_records, artifact_records)
            observe_phase_id = str((next((record for record in phase_records if str(record.get("phase") or "").strip() == "observe"), {}) or {}).get("id") or "").strip()
            observe_edges = build_observe_graph_edges(cycle_id, observe_phase_id, observe_documents)
            observe_version_edges = build_observe_version_graph_edges(cycle_id, observe_phase_id, observe_documents)

            nodes.extend(session_nodes)
            nodes.extend(phase_nodes)
            nodes.extend(artifact_nodes)
            nodes.extend(observe_entity_nodes)
            nodes.extend(observe_version_nodes)
            edges.extend(batch_edges)
            edges.extend(observe_edges)
            edges.extend(observe_version_edges)

            session_node_count += len(session_nodes)
            phase_node_count += len(phase_nodes)
            artifact_node_count += len(artifact_nodes)
            observe_entity_node_count += len(observe_entity_nodes)
            version_lineage_node_count += sum(1 for node in observe_version_nodes if node.label == "VersionLineage")
            version_witness_node_count += sum(1 for node in observe_version_nodes if node.label == "VersionWitness")
            has_phase_edge_count += sum(1 for edge, _, _ in batch_edges if edge.relationship_type == "HAS_PHASE")
            generated_edge_count += sum(1 for edge, _, _ in batch_edges if edge.relationship_type == "GENERATED")
            has_artifact_edge_count += sum(1 for edge, _, _ in batch_edges if edge.relationship_type == "HAS_ARTIFACT")
            semantic_edge_count += sum(1 for edge, _, _ in observe_edges if edge.relationship_type != "CAPTURED")
            captured_edge_count += sum(1 for edge, _, _ in observe_edges if edge.relationship_type == "CAPTURED")
            observed_witness_edge_count += sum(1 for edge, _, _ in observe_version_edges if edge.relationship_type == "OBSERVED_WITNESS")
            belongs_to_lineage_edge_count += sum(1 for edge, _, _ in observe_version_edges if edge.relationship_type == "BELONGS_TO_LINEAGE")

        if not nodes:
            continue
        if neo4j_driver.batch_create_nodes(nodes) is False:
            raise RuntimeError("Neo4j batch_create_nodes returned False while backfilling structured research graph nodes")
        if edges and neo4j_driver.batch_create_relationships(edges) is False:
            raise RuntimeError("Neo4j batch_create_relationships returned False while backfilling structured research graph edges")
        batch_count += 1

    edge_count = (
        has_phase_edge_count
        + generated_edge_count
        + has_artifact_edge_count
        + semantic_edge_count
        + captured_edge_count
        + observed_witness_edge_count
        + belongs_to_lineage_edge_count
    )
    return {
        "status": "active",
        "batch_count": batch_count,
        "node_count": (
            session_node_count
            + phase_node_count
            + artifact_node_count
            + observe_entity_node_count
            + version_lineage_node_count
            + version_witness_node_count
        ),
        "edge_count": edge_count,
        "session_node_count": session_node_count,
        "phase_node_count": phase_node_count,
        "artifact_node_count": artifact_node_count,
        "observe_entity_node_count": observe_entity_node_count,
        "version_lineage_node_count": version_lineage_node_count,
        "version_witness_node_count": version_witness_node_count,
        "has_phase_edge_count": has_phase_edge_count,
        "generated_edge_count": generated_edge_count,
        "has_artifact_edge_count": has_artifact_edge_count,
        "semantic_edge_count": semantic_edge_count,
        "captured_edge_count": captured_edge_count,
        "observed_witness_edge_count": observed_witness_edge_count,
        "belongs_to_lineage_edge_count": belongs_to_lineage_edge_count,
    }