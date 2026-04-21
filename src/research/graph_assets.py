from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.storage.graph_schema import (
    ENTITY_TYPE_TO_LABEL,
    NodeLabel,
    RelType,
    resolve_node_label,
)


def build_hypothesis_subgraph(cycle_id: str, hypotheses: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_keys: set[Tuple[str, str]] = set()
    edge_keys: set[Tuple[str, str, str, str, str]] = set()

    def add_node(label: str, node_id: str, properties: Optional[Dict[str, Any]] = None) -> None:
        key = (label, node_id)
        if key in node_keys:
            return
        node_keys.add(key)
        nodes.append({
            "id": node_id,
            "label": resolve_node_label(label),
            "properties": dict(properties or {}),
        })

    def add_edge(
        source_id: str,
        target_id: str,
        relationship_type: str,
        source_label: str,
        target_label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = (source_label, source_id, relationship_type, target_label, target_id)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "source_label": source_label,
            "target_label": target_label,
            "properties": dict(properties or {}),
        })

    for index, hypothesis in enumerate(hypotheses, start=1):
        if not isinstance(hypothesis, Mapping):
            continue
        hypothesis_id = str(hypothesis.get("hypothesis_id") or f"generated-{index}").strip()
        if not hypothesis_id:
            continue
        node_id = f"hypothesis::{cycle_id}::{hypothesis_id}"
        source_entities = _normalize_string_list(hypothesis.get("source_entities") or hypothesis.get("keywords"))
        supporting_signals = _normalize_string_list(hypothesis.get("supporting_signals"))
        contradiction_signals = _normalize_string_list(hypothesis.get("contradiction_signals"))
        add_node(
            NodeLabel.HYPOTHESIS.value,
            node_id,
            {
                "cycle_id": cycle_id,
                "phase": "hypothesis",
                "hypothesis_id": hypothesis_id,
                "title": str(hypothesis.get("title") or hypothesis.get("statement") or hypothesis_id),
                "description": str(
                    hypothesis.get("statement")
                    or hypothesis.get("description")
                    or hypothesis.get("rationale")
                    or ""
                ),
                "domain": str(hypothesis.get("domain") or "integrative_research"),
                "confidence": _as_float(hypothesis.get("confidence"), 0.0),
                "status": str(hypothesis.get("status") or "draft"),
                "validation_plan": str(hypothesis.get("validation_plan") or ""),
                "supporting_signal_count": len(supporting_signals),
                "contradiction_signal_count": len(contradiction_signals),
            },
        )
        for role, entity_names in (
            ("source_entity", source_entities),
            ("supporting_signal", supporting_signals),
            ("contradiction_signal", contradiction_signals),
        ):
            for entity_name in entity_names:
                entity_node_id = f"entity::{_slugify(entity_name)}"
                add_node(
                    NodeLabel.ENTITY.value,
                    entity_node_id,
                    {
                        "name": entity_name,
                        "entity_type": "hypothesis_context",
                        "cycle_id": cycle_id,
                    },
                )
                add_edge(
                    node_id,
                    entity_node_id,
                    RelType.RELATED_TO.value,
                    NodeLabel.HYPOTHESIS.value,
                    NodeLabel.ENTITY.value,
                    {
                        "cycle_id": cycle_id,
                        "phase": "hypothesis",
                        "role": role,
                    },
                )

    return _build_subgraph_payload(
        graph_type="hypothesis_subgraph",
        asset_family="hypothesis",
        nodes=nodes,
        edges=edges,
        summary={
            "hypothesis_count": sum(1 for n in nodes if n.get("label") == NodeLabel.HYPOTHESIS.value),
        },
    )


def build_evidence_subgraph(
    cycle_id: str,
    evidence_protocol: Mapping[str, Any],
    *,
    phase: str = "analyze",
) -> Dict[str, Any]:
    protocol = dict(evidence_protocol or {})
    raw_records = [item for item in (protocol.get("evidence_records") or []) if isinstance(item, Mapping)]
    raw_claims = [item for item in (protocol.get("claims") or []) if isinstance(item, Mapping)]

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_keys: set[Tuple[str, str]] = set()
    edge_keys: set[Tuple[str, str, str, str, str]] = set()
    evidence_node_ids: Dict[str, str] = {}

    def add_node(label: str, node_id: str, properties: Optional[Dict[str, Any]] = None) -> None:
        key = (label, node_id)
        if key in node_keys:
            return
        node_keys.add(key)
        nodes.append({
            "id": node_id,
            "label": resolve_node_label(label),
            "properties": dict(properties or {}),
        })

    def add_edge(
        source_id: str,
        target_id: str,
        relationship_type: str,
        source_label: str,
        target_label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        key = (source_label, source_id, relationship_type, target_label, target_id)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "source_label": source_label,
            "target_label": target_label,
            "properties": dict(properties or {}),
        })

    for record in raw_records:
        evidence_id = str(record.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        node_id = f"evidence::{cycle_id}::{evidence_id}"
        evidence_node_ids[evidence_id] = node_id
        add_node(
            NodeLabel.EVIDENCE.value,
            node_id,
            {
                "cycle_id": cycle_id,
                "phase": phase,
                "evidence_id": evidence_id,
                "title": str(record.get("title") or record.get("document_title") or evidence_id),
                "source": str(record.get("source_type") or record.get("source_ref") or "evidence_protocol"),
                "evidence_grade": str(record.get("evidence_grade") or ""),
                "confidence": _as_float(record.get("confidence"), 0.0),
                "provenance_type": str(record.get("source_type") or ""),
                "document_id": str(record.get("source_ref") or ""),
                "source_type": str(record.get("source_type") or ""),
                "source_ref": str(record.get("source_ref") or ""),
                "relation_type": str(record.get("relation_type") or "related"),
                "source_entity": str(record.get("source_entity") or ""),
                "target_entity": str(record.get("target_entity") or ""),
                "excerpt": str(record.get("excerpt") or ""),
                "document_title": str(record.get("document_title") or ""),
                "work_title": str(record.get("work_title") or ""),
                "version_lineage_key": str(record.get("version_lineage_key") or ""),
                "witness_key": str(record.get("witness_key") or ""),
            },
        )

    for claim in raw_claims:
        claim_id = str(claim.get("claim_id") or "").strip()
        if not claim_id:
            continue
        evidence_ids = _resolve_claim_evidence_ids(claim, raw_records)
        claim_node_id = f"claim::{cycle_id}::{claim_id}"
        claim_text = _build_claim_text(claim)
        add_node(
            NodeLabel.EVIDENCE_CLAIM.value,
            claim_node_id,
            {
                "cycle_id": cycle_id,
                "phase": phase,
                "claim_id": claim_id,
                "claim_text": claim_text,
                "confidence": _as_float(claim.get("confidence"), 0.0),
                "evidence_grade": str(((protocol.get("evidence_grade_summary") or {}).get("overall_grade") or "")),
                "evidence_ids": list(evidence_ids),
                "source_entity": str(claim.get("source_entity") or ""),
                "target_entity": str(claim.get("target_entity") or ""),
                "relation_type": str(claim.get("relation_type") or "related"),
                "support_count": int(claim.get("support_count") or len(evidence_ids) or 0),
                "review_status": str(claim.get("review_status") or ""),
                "needs_manual_review": bool(claim.get("needs_manual_review", False)),
                "reviewer": str(claim.get("reviewer") or ""),
                "reviewed_at": str(claim.get("reviewed_at") or ""),
                "decision_basis": str(claim.get("decision_basis") or ""),
                "document_title": str(claim.get("document_title") or ""),
                "work_title": str(claim.get("work_title") or ""),
                "version_lineage_key": str(claim.get("version_lineage_key") or ""),
                "witness_key": str(claim.get("witness_key") or ""),
            },
        )

        for endpoint_role, field_name in (("source", "source_entity"), ("target", "target_entity")):
            entity_name = str(claim.get(field_name) or "").strip()
            if not entity_name:
                continue
            entity_node_id = f"entity::{_slugify(entity_name)}"
            add_node(
                NodeLabel.ENTITY.value,
                entity_node_id,
                {
                    "name": entity_name,
                    "entity_type": "claim_endpoint",
                    "cycle_id": cycle_id,
                },
            )
            add_edge(
                claim_node_id,
                entity_node_id,
                RelType.CLAIMS.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                NodeLabel.ENTITY.value,
                {
                    "cycle_id": cycle_id,
                    "phase": phase,
                    "endpoint_role": endpoint_role,
                },
            )

        for evidence_id in evidence_ids:
            evidence_node_id = evidence_node_ids.get(evidence_id)
            if not evidence_node_id:
                continue
            record = next((item for item in raw_records if str(item.get("evidence_id") or "") == evidence_id), {})
            edge_props = {
                "cycle_id": cycle_id,
                "phase": phase,
                "claim_id": claim_id,
                "evidence_id": evidence_id,
                "source_type": str(record.get("source_type") or ""),
                "source_ref": str(record.get("source_ref") or ""),
                "document_title": str(record.get("document_title") or ""),
                "work_title": str(record.get("work_title") or ""),
                "version_lineage_key": str(record.get("version_lineage_key") or ""),
                "witness_key": str(record.get("witness_key") or ""),
            }
            add_edge(
                evidence_node_id,
                claim_node_id,
                RelType.EVIDENCE_FOR.value,
                NodeLabel.EVIDENCE.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                edge_props,
            )
            add_edge(
                claim_node_id,
                evidence_node_id,
                RelType.SUPPORTED_BY.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                NodeLabel.EVIDENCE.value,
                edge_props,
            )

    return _build_subgraph_payload(
        graph_type="evidence_subgraph",
        asset_family="evidence",
        nodes=nodes,
        edges=edges,
        summary={
            "evidence_record_count": len(raw_records),
            "claim_count": len(raw_claims),
            "linked_claim_count": sum(1 for item in raw_claims if _resolve_claim_evidence_ids(item, raw_records)),
        },
    )


def build_graph_assets_payload(**subgraphs: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    summary: Dict[str, Dict[str, int]] = {}
    for key, subgraph in subgraphs.items():
        if not isinstance(subgraph, Mapping):
            continue
        payload[key] = dict(subgraph)
        summary[key] = {
            "node_count": int(subgraph.get("node_count") or 0),
            "edge_count": int(subgraph.get("edge_count") or 0),
        }
    if payload:
        payload["summary"] = summary
    return payload


def get_phase_graph_assets(result: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    results = result.get("results")
    if not isinstance(results, Mapping):
        return {}
    graph_assets = results.get("graph_assets")
    return dict(graph_assets) if isinstance(graph_assets, Mapping) else {}


def _build_subgraph_payload(
    *,
    graph_type: str,
    asset_family: str,
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "graph_type": graph_type,
        "asset_family": asset_family,
        "nodes": [dict(node) for node in nodes],
        "edges": [dict(edge) for edge in edges],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "summary": dict(summary or {}),
    }


def _resolve_claim_evidence_ids(
    claim: Mapping[str, Any],
    records: Iterable[Mapping[str, Any]],
) -> List[str]:
    explicit = [str(item).strip() for item in (claim.get("evidence_ids") or []) if str(item).strip()]
    if explicit:
        return explicit
    source_entity = str(claim.get("source_entity") or "").strip()
    target_entity = str(claim.get("target_entity") or "").strip()
    relation_type = str(claim.get("relation_type") or "related").strip() or "related"
    matched: List[str] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        if source_entity and str(record.get("source_entity") or "").strip() != source_entity:
            continue
        if target_entity and str(record.get("target_entity") or "").strip() != target_entity:
            continue
        if relation_type and str(record.get("relation_type") or "related").strip() != relation_type:
            continue
        evidence_id = str(record.get("evidence_id") or "").strip()
        if evidence_id:
            matched.append(evidence_id)
    return matched


def _build_claim_text(claim: Mapping[str, Any]) -> str:
    source_entity = str(claim.get("source_entity") or "").strip()
    target_entity = str(claim.get("target_entity") or "").strip()
    relation_type = str(claim.get("relation_type") or "related").strip() or "related"
    if source_entity or target_entity:
        return f"{source_entity} {relation_type} {target_entity}".strip()
    return str(claim.get("claim_id") or "claim")


def _normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, (list, tuple)):
        return []
    normalized: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _slugify(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    allowed = []
    for char in text:
        if char.isalnum() or char in {"_", "-", ":"}:
            allowed.append(char)
    return "".join(allowed)[:64] or "item"


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
