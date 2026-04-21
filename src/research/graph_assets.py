from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.research.graph_asset_contract import (
    FORMULA_COMPONENT_NODE_TYPE,
    HERB_EFFICACY_NODE_TYPE,
    PATHOGENESIS_PROPERTY_TYPE,
    SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION,
    EfficacyNodeContract,
    FormulaComponentNodeContract,
    FormulaProvenanceEdgeContract,
    HerbProvenanceEdgeContract,
    PathogenesisNodeContract,
    SymptomNodeContract,
    resolve_manifestation_source,
)
from src.semantic_modeling.tcm_relationships import TCMRelationshipDefinitions
from src.storage.graph_schema import (
    NodeLabel,
    RelType,
    resolve_node_label,
)

_FORMULA_ROLE_TO_RELTYPE = {
    "sovereign": RelType.SOVEREIGN.value,
    "minister": RelType.MINISTER.value,
    "assistant": RelType.ASSISTANT.value,
    "envoy": RelType.ENVOY.value,
}

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


def build_philology_subgraph(
    cycle_id: str,
    observe_philology: Mapping[str, Any],
    *,
    phase: str = "observe",
) -> Dict[str, Any]:
    catalog_summary = dict((observe_philology or {}).get("catalog_summary") or {})
    documents = [item for item in (catalog_summary.get("documents") or []) if isinstance(item, Mapping)]
    version_lineages = [item for item in (catalog_summary.get("version_lineages") or []) if isinstance(item, Mapping)]
    terminology_rows = [item for item in ((observe_philology or {}).get("terminology_standard_table") or []) if isinstance(item, Mapping)]
    evidence_chains = [item for item in ((observe_philology or {}).get("evidence_chains") or []) if isinstance(item, Mapping)]
    conflict_claims = [item for item in ((observe_philology or {}).get("conflict_claims") or []) if isinstance(item, Mapping)]
    fragment_candidates = [item for item in ((observe_philology or {}).get("fragment_candidates") or []) if isinstance(item, Mapping)]
    lost_text_candidates = [item for item in ((observe_philology or {}).get("lost_text_candidates") or []) if isinstance(item, Mapping)]
    citation_source_candidates = [item for item in ((observe_philology or {}).get("citation_source_candidates") or []) if isinstance(item, Mapping)]

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_keys: set[Tuple[str, str]] = set()
    edge_keys: set[Tuple[str, str, str, str, str]] = set()
    catalog_node_ids: Dict[str, str] = {}
    lineage_node_ids: Dict[str, str] = {}
    witness_node_ids: Dict[str, str] = {}
    catalog_by_title: Dict[str, str] = {}
    witness_by_title: Dict[str, str] = {}
    document_witness_lookup: Dict[Tuple[str, str], str] = {}
    fragment_node_ids: Dict[str, str] = {}

    def build_review_fields(payload: Mapping[str, Any], *, default_review_status: str = "pending", default_manual_review: bool = False) -> Dict[str, Any]:
        return {
            "review_status": str(payload.get("review_status") or default_review_status),
            "needs_manual_review": bool(payload.get("needs_manual_review", default_manual_review)),
            "reviewer": str(payload.get("reviewer") or ""),
            "reviewed_at": str(payload.get("reviewed_at") or ""),
            "decision_basis": str(payload.get("decision_basis") or payload.get("basis_summary") or ""),
        }

    terminology_review_lookup: Dict[Tuple[str, str, str, str], Mapping[str, Any]] = {}
    for row in terminology_rows:
        review_key = (
            str(row.get("document_urn") or "").strip(),
            str(row.get("document_title") or row.get("work_title") or "").strip(),
            str(row.get("canonical") or "").strip(),
            str(row.get("semantic_scope") or row.get("label") or "common").strip(),
        )
        if any(review_key):
            terminology_review_lookup[review_key] = row

    # Derive per-document exegesis entries from terminology_standard_table rows.
    # Historical observe phases often store terminology data only in the top-level
    # terminology_standard_table without embedding exegesis_entries inside each
    # catalog document, so we build a secondary lookup keyed by document_urn and
    # document_title to supplement add_exegesis_nodes() below.
    document_derived_exegesis: Dict[str, List[Mapping[str, Any]]] = {}
    for _row in terminology_rows:
        _canonical = str(_row.get("canonical") or "").strip()
        if not _canonical:
            continue
        for _doc_key in filter(None, [
            str(_row.get("document_urn") or "").strip(),
            str(_row.get("document_title") or _row.get("work_title") or "").strip(),
        ]):
            document_derived_exegesis.setdefault(_doc_key, []).append(_row)

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

    for document in documents:
        catalog_id = str(document.get("catalog_id") or "").strip() or f"catalog::{_slugify(document.get('document_urn') or document.get('document_title') or document.get('work_title'))}"
        title = str(document.get("document_title") or document.get("work_title") or catalog_id)
        source = str(document.get("source_type") or document.get("source") or document.get("document_urn") or "")
        classification = str(document.get("fragment_title") or document.get("work_title") or "")
        catalog_node_ids[catalog_id] = catalog_id
        catalog_by_title.setdefault(title, catalog_id)
        add_node(
            NodeLabel.CATALOG.value,
            catalog_id,
            {
                "catalog_id": catalog_id,
                "title": title,
                "source": source,
                "classification": classification,
                **build_review_fields(document, default_review_status="accepted", default_manual_review=False),
            },
        )

        witness_key = str(document.get("witness_key") or document.get("document_urn") or catalog_id).strip()
        witness_node_id = f"witness::{witness_key}"
        witness_node_ids[witness_key] = witness_node_id
        witness_by_title.setdefault(title, witness_node_id)
        document_key = (str(document.get("document_urn") or "").strip(), title)
        if any(document_key):
            document_witness_lookup[document_key] = witness_node_id
        add_node(
            NodeLabel.VERSION_WITNESS.value,
            witness_node_id,
            {
                "cycle_id": cycle_id,
                "witness_key": witness_key,
                "version_lineage_key": str(document.get("version_lineage_key") or ""),
                "work_fragment_key": str(document.get("work_fragment_key") or ""),
                "catalog_id": catalog_id,
                "work_title": str(document.get("work_title") or ""),
                "fragment_title": str(document.get("fragment_title") or ""),
                "dynasty": str(document.get("dynasty") or ""),
                "author": str(document.get("author") or ""),
                "edition": str(document.get("edition") or ""),
                "source_type": str(document.get("source_type") or ""),
                "source_ref": str(document.get("document_urn") or document.get("catalog_id") or ""),
                "document_id": str(document.get("document_id") or ""),
                "document_urn": str(document.get("document_urn") or ""),
                "document_title": title,
                "phase_execution_id": str(document.get("phase_execution_id") or ""),
                **build_review_fields(document, default_review_status="accepted", default_manual_review=False),
            },
        )
        add_edge(
            witness_node_id,
            catalog_id,
            RelType.CATALOGED_IN.value,
            NodeLabel.VERSION_WITNESS.value,
            NodeLabel.CATALOG.value,
            {"cycle_id": cycle_id, "phase": phase},
        )

    for lineage in version_lineages:
        lineage_key = str(lineage.get("version_lineage_key") or "").strip()
        if not lineage_key:
            continue
        lineage_node_id = f"lineage::{lineage_key}"
        lineage_node_ids[lineage_key] = lineage_node_id
        add_node(
            NodeLabel.VERSION_LINEAGE.value,
            lineage_node_id,
            {
                "version_lineage_key": lineage_key,
                "work_fragment_key": str(lineage.get("work_fragment_key") or ""),
                "work_title": str(lineage.get("work_title") or ""),
                "fragment_title": str(lineage.get("fragment_title") or ""),
                "dynasty": str(lineage.get("dynasty") or ""),
                "author": str(lineage.get("author") or ""),
                "edition": str(lineage.get("edition") or ""),
                "lineage_id_source": str(lineage.get("lineage_id_source") or "catalog_summary"),
                **build_review_fields(lineage, default_review_status="accepted", default_manual_review=False),
            },
        )
        for witness in [item for item in (lineage.get("witnesses") or []) if isinstance(item, Mapping)]:
            witness_key = str(witness.get("witness_key") or witness.get("urn") or witness.get("title") or "").strip()
            if not witness_key:
                continue
            witness_node_id = witness_node_ids.get(witness_key) or f"witness::{witness_key}"
            witness_node_ids[witness_key] = witness_node_id
            witness_title = str(witness.get("title") or witness.get("document_title") or witness_key)
            witness_by_title.setdefault(witness_title, witness_node_id)
            document_key = (str(witness.get("urn") or "").strip(), witness_title)
            if any(document_key):
                document_witness_lookup[document_key] = witness_node_id
            add_node(
                NodeLabel.VERSION_WITNESS.value,
                witness_node_id,
                {
                    "cycle_id": cycle_id,
                    "witness_key": witness_key,
                    "version_lineage_key": lineage_key,
                    "work_fragment_key": str(lineage.get("work_fragment_key") or ""),
                    "catalog_id": str(witness.get("catalog_id") or ""),
                    "work_title": str(lineage.get("work_title") or ""),
                    "fragment_title": str(lineage.get("fragment_title") or ""),
                    "dynasty": str(lineage.get("dynasty") or ""),
                    "author": str(lineage.get("author") or ""),
                    "edition": str(lineage.get("edition") or ""),
                    "source_type": str(witness.get("source_type") or ""),
                    "source_ref": str(witness.get("urn") or witness.get("catalog_id") or ""),
                    "document_id": str(witness.get("document_id") or ""),
                    "document_urn": str(witness.get("urn") or ""),
                    "document_title": witness_title,
                    **build_review_fields(witness, default_review_status="accepted", default_manual_review=False),
                },
            )
            add_edge(
                lineage_node_id,
                witness_node_id,
                RelType.WITNESSED_BY.value,
                NodeLabel.VERSION_LINEAGE.value,
                NodeLabel.VERSION_WITNESS.value,
                {"cycle_id": cycle_id, "phase": phase},
            )
            add_edge(
                witness_node_id,
                lineage_node_id,
                RelType.BELONGS_TO_LINEAGE.value,
                NodeLabel.VERSION_WITNESS.value,
                NodeLabel.VERSION_LINEAGE.value,
                {"cycle_id": cycle_id, "phase": phase},
            )
            catalog_id = str(witness.get("catalog_id") or "").strip()
            if catalog_id and catalog_id in catalog_node_ids:
                add_edge(
                    witness_node_id,
                    catalog_id,
                    RelType.CATALOGED_IN.value,
                    NodeLabel.VERSION_WITNESS.value,
                    NodeLabel.CATALOG.value,
                    {"cycle_id": cycle_id, "phase": phase},
                )
                add_edge(
                    catalog_id,
                    lineage_node_id,
                    RelType.HAS_VERSION.value,
                    NodeLabel.CATALOG.value,
                    NodeLabel.VERSION_LINEAGE.value,
                    {"cycle_id": cycle_id, "phase": phase},
                )

    def add_exegesis_nodes() -> None:
        for document in documents:
            document_title = str(document.get("document_title") or document.get("work_title") or "").strip()
            document_urn = str(document.get("document_urn") or "").strip()
            work_title = str(document.get("work_title") or "").strip()
            version_lineage_key = str(document.get("version_lineage_key") or "").strip()
            witness_key = str(document.get("witness_key") or "").strip()
            catalog_id = str(document.get("catalog_id") or "").strip()
            lineage_node_id = lineage_node_ids.get(version_lineage_key)
            witness_node_id = witness_node_ids.get(witness_key) or document_witness_lookup.get((document_urn, document_title))
            catalog_node_id = catalog_node_ids.get(catalog_id) or catalog_by_title.get(document_title)
            _existing_exegesis = [item for item in (document.get("exegesis_entries") or []) if isinstance(item, Mapping)]
            _seen_exegesis_keys: set[tuple[str, str]] = {
                (
                    str(e.get("canonical") or "").strip(),
                    str(e.get("semantic_scope") or e.get("label") or "common").strip(),
                )
                for e in _existing_exegesis
                if str(e.get("canonical") or "").strip()
            }
            _derived_exegesis: List[Mapping[str, Any]] = []
            for _doc_key in filter(None, [document_urn, document_title]):
                for _row in (document_derived_exegesis.get(_doc_key) or []):
                    _c = str(_row.get("canonical") or "").strip()
                    _s = str(_row.get("semantic_scope") or _row.get("label") or "common").strip()
                    if _c and (_c, _s) not in _seen_exegesis_keys:
                        _seen_exegesis_keys.add((_c, _s))
                        _derived_exegesis.append(_row)
            for entry in [*_existing_exegesis, *_derived_exegesis]:
                canonical = str(entry.get("canonical") or "").strip()
                semantic_scope = str(entry.get("semantic_scope") or entry.get("label") or "common").strip()
                if not canonical:
                    continue
                merged_entry = dict(entry)
                review_key = (document_urn, document_title, canonical, semantic_scope)
                review_row = terminology_review_lookup.get(review_key)
                if review_row:
                    merged_entry.update({
                        key: review_row.get(key)
                        for key in ("review_status", "needs_manual_review", "reviewer", "reviewed_at", "decision_basis")
                        if key in review_row
                    })
                exegesis_id = _build_exegesis_id(document_urn, document_title, canonical, semantic_scope)
                exegesis_node_id = f"exegesis::{cycle_id}::{exegesis_id}"
                exegesis_term_node_id = f"exegesis_term::{cycle_id}::{exegesis_id}"
                add_node(
                    NodeLabel.EXEGESIS_ENTRY.value,
                    exegesis_node_id,
                    {
                        "cycle_id": cycle_id,
                        "phase": phase,
                        "exegesis_id": exegesis_id,
                        "canonical": canonical,
                        "label": str(entry.get("label") or semantic_scope),
                        "definition": str(entry.get("definition") or ""),
                        "definition_source": str(merged_entry.get("definition_source") or ""),
                        "semantic_scope": semantic_scope,
                        "observed_forms": _normalize_string_list(merged_entry.get("observed_forms")),
                        "configured_variants": _normalize_string_list(merged_entry.get("configured_variants")),
                        "sources": _normalize_string_list(merged_entry.get("sources")),
                        "source_refs": _normalize_string_list(merged_entry.get("source_refs")),
                        "notes": _normalize_string_list(merged_entry.get("notes")),
                        "dynasty_usage": _normalize_string_list(merged_entry.get("dynasty_usage")),
                        "disambiguation_basis": _normalize_string_list(merged_entry.get("disambiguation_basis")),
                        **build_review_fields(merged_entry, default_review_status="pending", default_manual_review=True),
                        "exegesis_notes": str(merged_entry.get("exegesis_notes") or ""),
                        "document_urn": document_urn,
                        "document_title": document_title,
                        "work_title": work_title,
                        "version_lineage_key": version_lineage_key,
                        "witness_key": witness_key,
                    },
                )
                add_node(
                    NodeLabel.EXEGESIS_TERM.value,
                    exegesis_term_node_id,
                    {
                        "cycle_id": cycle_id,
                        "phase": phase,
                        "exegesis_id": exegesis_id,
                        "canonical": canonical,
                        "label": str(merged_entry.get("label") or semantic_scope),
                        "definition": str(merged_entry.get("definition") or ""),
                        "definition_source": str(merged_entry.get("definition_source") or ""),
                        "semantic_scope": semantic_scope,
                        "observed_forms": _normalize_string_list(merged_entry.get("observed_forms")),
                        "configured_variants": _normalize_string_list(merged_entry.get("configured_variants")),
                        "sources": _normalize_string_list(merged_entry.get("sources")),
                        "source_refs": _normalize_string_list(merged_entry.get("source_refs")),
                        "notes": _normalize_string_list(merged_entry.get("notes")),
                        "dynasty_usage": _normalize_string_list(merged_entry.get("dynasty_usage")),
                        "disambiguation_basis": _normalize_string_list(merged_entry.get("disambiguation_basis")),
                        **build_review_fields(merged_entry, default_review_status="pending", default_manual_review=True),
                        "exegesis_notes": str(merged_entry.get("exegesis_notes") or ""),
                        "document_urn": document_urn,
                        "document_title": document_title,
                        "work_title": work_title,
                        "version_lineage_key": version_lineage_key,
                        "witness_key": witness_key,
                    },
                )
                term_label = _resolve_exegesis_term_label(entry)
                term_node_id = f"term::{term_label.lower()}::{_slugify(canonical)}"
                add_node(
                    term_label,
                    term_node_id,
                    {
                        "name": canonical,
                        "type": semantic_scope,
                        "description": str(entry.get("definition") or ""),
                        "confidence": 1.0,
                    },
                )
                add_edge(
                    exegesis_node_id,
                    term_node_id,
                    _resolve_exegesis_relation_type(term_label),
                    NodeLabel.EXEGESIS_ENTRY.value,
                    term_label,
                    {
                        "cycle_id": cycle_id,
                        "phase": phase,
                        **(
                            HerbProvenanceEdgeContract.build_properties(
                                herb_canonical=canonical,
                                source_exegesis_id=exegesis_id,
                                semantic_scope=semantic_scope,
                            )
                            if term_label == NodeLabel.HERB.value
                            else FormulaProvenanceEdgeContract.build_properties(
                                formula_canonical=canonical,
                                source_exegesis_id=exegesis_id,
                                semantic_scope=semantic_scope,
                            )
                            if term_label == NodeLabel.FORMULA.value
                            else {"semantic_scope": semantic_scope}
                        ),
                    },
                )
                add_edge(
                    exegesis_term_node_id,
                    term_node_id,
                    RelType.INTERPRETS.value,
                    NodeLabel.EXEGESIS_TERM.value,
                    term_label,
                    {"cycle_id": cycle_id, "phase": phase, "semantic_scope": semantic_scope},
                )
                _add_exegesis_domain_semantics(
                    add_node=add_node,
                    add_edge=add_edge,
                    cycle_id=cycle_id,
                    phase=phase,
                    exegesis_id=exegesis_id,
                    exegesis_node_id=exegesis_node_id,
                    term_node_id=term_node_id,
                    term_label=term_label,
                    canonical=canonical,
                    semantic_scope=semantic_scope,
                    entry=merged_entry,
                )
                if catalog_node_id:
                    add_edge(
                        catalog_node_id,
                        exegesis_node_id,
                        RelType.HAS_EXEGESIS.value,
                        NodeLabel.CATALOG.value,
                        NodeLabel.EXEGESIS_ENTRY.value,
                        {"cycle_id": cycle_id, "phase": phase},
                    )
                if lineage_node_id:
                    add_edge(
                        lineage_node_id,
                        exegesis_node_id,
                        RelType.HAS_EXEGESIS.value,
                        NodeLabel.VERSION_LINEAGE.value,
                        NodeLabel.EXEGESIS_ENTRY.value,
                        {"cycle_id": cycle_id, "phase": phase},
                    )
                if witness_node_id:
                    add_edge(
                        witness_node_id,
                        exegesis_node_id,
                        RelType.HAS_EXEGESIS.value,
                        NodeLabel.VERSION_WITNESS.value,
                        NodeLabel.EXEGESIS_ENTRY.value,
                        {"cycle_id": cycle_id, "phase": phase},
                    )
                    add_edge(
                        witness_node_id,
                        exegesis_term_node_id,
                        RelType.ATTESTS_TO.value,
                        NodeLabel.VERSION_WITNESS.value,
                        NodeLabel.EXEGESIS_TERM.value,
                        {"cycle_id": cycle_id, "phase": phase},
                    )

    def add_fragment_candidate_nodes(items: Sequence[Mapping[str, Any]], candidate_kind: str) -> None:
        for entry in items:
            candidate_id = str(entry.get("fragment_candidate_id") or entry.get("candidate_id") or entry.get("id") or "").strip()
            if not candidate_id:
                continue
            fragment_title = str(entry.get("fragment_title") or entry.get("document_title") or candidate_id).strip()
            document_title = str(entry.get("document_title") or "").strip()
            document_urn = str(entry.get("document_urn") or "").strip()
            version_lineage_key = str(entry.get("version_lineage_key") or "").strip()
            witness_key = str(entry.get("witness_key") or "").strip()
            witness_title = str(entry.get("witness_title") or "").strip()
            fragment_node_id = f"fragment::{cycle_id}::{candidate_kind}::{candidate_id}"
            fragment_node_ids[candidate_id] = fragment_node_id
            add_node(
                NodeLabel.FRAGMENT_CANDIDATE.value,
                fragment_node_id,
                {
                    "cycle_id": cycle_id,
                    "phase": phase,
                    "candidate_id": candidate_id,
                    "candidate_kind": candidate_kind,
                    "fragment_title": fragment_title,
                    "document_title": document_title,
                    "document_urn": document_urn,
                    "source_type": str(entry.get("source_type") or ""),
                    "witness_title": witness_title,
                    "witness_urn": str(entry.get("witness_urn") or ""),
                    "work_title": str(entry.get("work_title") or ""),
                    "version_lineage_key": version_lineage_key,
                    "witness_key": witness_key,
                    "match_score": _as_float(entry.get("match_score"), 0.0),
                    "confidence": _as_float(entry.get("confidence"), _as_float(entry.get("match_score"), 0.0)),
                    "review_status": str(entry.get("review_status") or "pending"),
                    "needs_manual_review": bool(entry.get("needs_manual_review", True)),
                    "reviewer": str(entry.get("reviewer") or ""),
                    "reviewed_at": str(entry.get("reviewed_at") or ""),
                    "decision_basis": str(entry.get("decision_basis") or ""),
                    "reconstruction_basis": str(entry.get("reconstruction_basis") or ""),
                    "source_refs": _normalize_string_list(entry.get("source_refs")),
                    "asset_key": str(entry.get("asset_key") or ""),
                    "text_preview": str(entry.get("witness_text") or entry.get("text_preview") or "")[:200],
                },
            )
            lineage_node_id = lineage_node_ids.get(version_lineage_key)
            witness_node_id = witness_node_ids.get(witness_key)
            if not witness_node_id:
                witness_node_id = document_witness_lookup.get((document_urn, document_title)) or witness_by_title.get(witness_title or document_title)
            catalog_node_id = catalog_by_title.get(document_title)
            if witness_node_id:
                add_edge(
                    witness_node_id,
                    fragment_node_id,
                    RelType.HAS_FRAGMENT_CANDIDATE.value,
                    NodeLabel.VERSION_WITNESS.value,
                    NodeLabel.FRAGMENT_CANDIDATE.value,
                    {"cycle_id": cycle_id, "phase": phase, "candidate_kind": candidate_kind},
                )
                add_edge(
                    fragment_node_id,
                    witness_node_id,
                    RelType.DERIVED_FROM.value,
                    NodeLabel.FRAGMENT_CANDIDATE.value,
                    NodeLabel.VERSION_WITNESS.value,
                    {"cycle_id": cycle_id, "phase": phase, "candidate_kind": candidate_kind},
                )
                add_edge(
                    fragment_node_id,
                    witness_node_id,
                    RelType.RECONSTRUCTS.value,
                    NodeLabel.FRAGMENT_CANDIDATE.value,
                    NodeLabel.VERSION_WITNESS.value,
                    {"cycle_id": cycle_id, "phase": phase, "candidate_kind": candidate_kind},
                )
            if lineage_node_id:
                add_edge(
                    lineage_node_id,
                    fragment_node_id,
                    RelType.HAS_FRAGMENT_CANDIDATE.value,
                    NodeLabel.VERSION_LINEAGE.value,
                    NodeLabel.FRAGMENT_CANDIDATE.value,
                    {"cycle_id": cycle_id, "phase": phase, "candidate_kind": candidate_kind},
                )
            if catalog_node_id:
                add_edge(
                    catalog_node_id,
                    fragment_node_id,
                    RelType.HAS_FRAGMENT_CANDIDATE.value,
                    NodeLabel.CATALOG.value,
                    NodeLabel.FRAGMENT_CANDIDATE.value,
                    {"cycle_id": cycle_id, "phase": phase, "candidate_kind": candidate_kind},
                )

    def add_claim_node(claim: Mapping[str, Any], claim_bucket: str) -> None:
        claim_id = str(
            claim.get("evidence_chain_id")
            or claim.get("claim_id")
            or f"{claim_bucket}::{_slugify(claim.get('claim_statement') or claim.get('basis_summary') or len(nodes))}"
        ).strip()
        if not claim_id:
            return
        claim_node_id = f"philology_claim::{cycle_id}::{claim_id}"
        textual_chain_node_id = f"textual_chain::{cycle_id}::{claim_id}"
        add_node(
            NodeLabel.EVIDENCE_CLAIM.value,
            claim_node_id,
            {
                "cycle_id": cycle_id,
                "phase": phase,
                "claim_id": claim_id,
                "claim_text": str(claim.get("claim_statement") or claim.get("claim_text") or claim_id),
                "confidence": _as_float(claim.get("confidence"), 0.0),
                "relation_type": str(claim.get("claim_type") or claim_bucket),
                "support_count": len(_normalize_string_list(claim.get("source_refs"))),
                "review_status": str(claim.get("review_status") or "pending"),
                "needs_manual_review": bool(claim.get("needs_manual_review", False)),
                "reviewer": str(claim.get("reviewer") or ""),
                "reviewed_at": str(claim.get("reviewed_at") or ""),
                "decision_basis": str(claim.get("basis_summary") or claim.get("decision_basis") or ""),
                "work_title": str(claim.get("work_title") or ""),
                "document_title": str(claim.get("document_title") or claim.get("base_title") or ""),
                "version_lineage_key": str(claim.get("version_lineage_key") or ""),
                "witness_key": str(claim.get("witness_key") or ""),
            },
        )
        add_node(
            NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value,
            textual_chain_node_id,
            {
                "cycle_id": cycle_id,
                "phase": phase,
                "claim_id": claim_id,
                "claim_text": str(claim.get("claim_statement") or claim.get("claim_text") or claim_id),
                "claim_type": str(claim.get("claim_type") or claim_bucket),
                "confidence": _as_float(claim.get("confidence"), 0.0),
                "relation_type": str(claim.get("claim_type") or claim_bucket),
                "support_count": len(_normalize_string_list(claim.get("source_refs"))),
                **build_review_fields(claim, default_review_status="pending", default_manual_review=False),
                "work_title": str(claim.get("work_title") or ""),
                "document_title": str(claim.get("document_title") or claim.get("base_title") or ""),
                "version_lineage_key": str(claim.get("version_lineage_key") or ""),
                "witness_key": str(claim.get("witness_key") or ""),
            },
        )

        lineage_key = str(claim.get("version_lineage_key") or "").strip()
        if lineage_key and lineage_key in lineage_node_ids:
            add_edge(
                claim_node_id,
                lineage_node_ids[lineage_key],
                RelType.DERIVED_FROM.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                NodeLabel.VERSION_LINEAGE.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )
            add_edge(
                textual_chain_node_id,
                lineage_node_ids[lineage_key],
                RelType.DERIVED_FROM.value,
                NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value,
                NodeLabel.VERSION_LINEAGE.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )

        witness_key = str(claim.get("witness_key") or "").strip()
        if witness_key and witness_key in witness_node_ids:
            add_edge(
                claim_node_id,
                witness_node_ids[witness_key],
                RelType.EVIDENCED_BY.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                NodeLabel.VERSION_WITNESS.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )
            add_edge(
                textual_chain_node_id,
                witness_node_ids[witness_key],
                RelType.EVIDENCED_BY.value,
                NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value,
                NodeLabel.VERSION_WITNESS.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )

        witness_title = str(claim.get("witness_title") or "").strip()
        witness_node_id = witness_by_title.get(witness_title)
        if witness_node_id:
            add_edge(
                claim_node_id,
                witness_node_id,
                RelType.EVIDENCED_BY.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                NodeLabel.VERSION_WITNESS.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )
            add_edge(
                textual_chain_node_id,
                witness_node_id,
                RelType.EVIDENCED_BY.value,
                NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value,
                NodeLabel.VERSION_WITNESS.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )

        document_title = str(claim.get("document_title") or claim.get("work_title") or "").strip()
        catalog_node_id = catalog_by_title.get(document_title)
        if catalog_node_id:
            add_edge(
                claim_node_id,
                catalog_node_id,
                RelType.EVIDENCED_BY.value,
                NodeLabel.EVIDENCE_CLAIM.value,
                NodeLabel.CATALOG.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )
            add_edge(
                textual_chain_node_id,
                catalog_node_id,
                RelType.EVIDENCED_BY.value,
                NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value,
                NodeLabel.CATALOG.value,
                {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
            )

        claim_source_refs = set(_normalize_string_list(claim.get("source_refs")))
        if claim_source_refs:
            for entry in [*fragment_candidates, *lost_text_candidates, *citation_source_candidates]:
                candidate_id = str(entry.get("fragment_candidate_id") or entry.get("candidate_id") or entry.get("id") or "").strip()
                fragment_node_id = fragment_node_ids.get(candidate_id)
                if not fragment_node_id:
                    continue
                fragment_refs = set(_normalize_string_list(entry.get("source_refs")))
                if claim_source_refs.intersection(fragment_refs):
                    add_edge(
                        textual_chain_node_id,
                        fragment_node_id,
                        RelType.CITES_FRAGMENT.value,
                        NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value,
                        NodeLabel.FRAGMENT_CANDIDATE.value,
                        {"cycle_id": cycle_id, "phase": phase, "claim_bucket": claim_bucket},
                    )

    add_exegesis_nodes()
    add_fragment_candidate_nodes(fragment_candidates, "fragment_candidates")
    add_fragment_candidate_nodes(lost_text_candidates, "lost_text_candidates")
    add_fragment_candidate_nodes(citation_source_candidates, "citation_source_candidates")

    for claim in evidence_chains:
        add_claim_node(claim, "evidence_chain")
    for claim in conflict_claims:
        add_claim_node(claim, "conflict_claim")

    return _build_subgraph_payload(
        graph_type="philology_subgraph",
        asset_family="philology",
        nodes=nodes,
        edges=edges,
        summary={
            "catalog_count": len(documents),
            "version_lineage_count": len(version_lineages),
            "witness_count": len(witness_node_ids),
            "exegesis_entry_count": sum(1 for node in nodes if node.get("label") == NodeLabel.EXEGESIS_ENTRY.value),
            "exegesis_term_count": sum(1 for node in nodes if node.get("label") == NodeLabel.EXEGESIS_TERM.value),
            "fragment_candidate_count": sum(1 for node in nodes if node.get("label") == NodeLabel.FRAGMENT_CANDIDATE.value),
            "evidence_chain_count": len(evidence_chains),
            "conflict_claim_count": len(conflict_claims),
            "textual_evidence_chain_count": sum(1 for node in nodes if node.get("label") == NodeLabel.TEXTUAL_EVIDENCE_CHAIN.value),
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


def _build_exegesis_id(document_urn: str, document_title: str, canonical: str, semantic_scope: str) -> str:
    return _slugify("::".join(part for part in (document_urn or document_title, canonical, semantic_scope) if part))


def _resolve_exegesis_term_label(entry: Mapping[str, Any]) -> str:
    semantic_scope = str(entry.get("semantic_scope") or entry.get("label") or "").strip().lower()
    definition_source = str(entry.get("definition_source") or "").strip().lower()
    category = str(entry.get("category") or "").strip().lower()
    candidate_types = [category, semantic_scope, definition_source]
    for candidate in candidate_types:
        if "formula" in candidate or "方剂" in candidate:
            return NodeLabel.FORMULA.value
        if "herb" in candidate or "本草" in candidate or "药名" in candidate:
            return NodeLabel.HERB.value
        if "syndrome" in candidate or "证候" in candidate:
            return NodeLabel.SYNDROME.value
        if "efficacy" in candidate or "功效" in candidate:
            return NodeLabel.EFFICACY.value
    return NodeLabel.ENTITY.value


def _resolve_exegesis_relation_type(term_label: str) -> str:
    if term_label == NodeLabel.HERB.value:
        return RelType.EXPLAINS_HERB.value
    if term_label == NodeLabel.FORMULA.value:
        return RelType.EXPLAINS_FORMULA.value
    if term_label == NodeLabel.SYNDROME.value:
        return RelType.EXPLAINS_SYNDROME.value
    return RelType.RELATED_TO.value


def _add_exegesis_domain_semantics(
    *,
    add_node: Any,
    add_edge: Any,
    cycle_id: str,
    phase: str,
    exegesis_id: str,
    exegesis_node_id: str,
    term_node_id: str,
    term_label: str,
    canonical: str,
    semantic_scope: str,
    entry: Mapping[str, Any],
) -> None:
    if term_label == NodeLabel.HERB.value:
        _add_herb_exegesis_semantics(
            add_node=add_node,
            add_edge=add_edge,
            cycle_id=cycle_id,
            phase=phase,
            exegesis_id=exegesis_id,
            exegesis_node_id=exegesis_node_id,
            herb_node_id=term_node_id,
            canonical=canonical,
            semantic_scope=semantic_scope,
        )
        return
    if term_label == NodeLabel.FORMULA.value:
        _add_formula_exegesis_semantics(
            add_node=add_node,
            add_edge=add_edge,
            cycle_id=cycle_id,
            phase=phase,
            exegesis_id=exegesis_id,
            exegesis_node_id=exegesis_node_id,
            formula_node_id=term_node_id,
            canonical=canonical,
            semantic_scope=semantic_scope,
        )
        return
    if term_label == NodeLabel.SYNDROME.value:
        _add_syndrome_exegesis_semantics(
            add_node=add_node,
            add_edge=add_edge,
            cycle_id=cycle_id,
            phase=phase,
            exegesis_id=exegesis_id,
            exegesis_node_id=exegesis_node_id,
            syndrome_node_id=term_node_id,
            canonical=canonical,
            semantic_scope=semantic_scope,
            entry=entry,
        )


def _add_herb_exegesis_semantics(
    *,
    add_node: Any,
    add_edge: Any,
    cycle_id: str,
    phase: str,
    exegesis_id: str,
    exegesis_node_id: str,
    herb_node_id: str,
    canonical: str,
    semantic_scope: str,
) -> None:
    efficacies = list(dict.fromkeys(TCMRelationshipDefinitions.get_herb_efficacy(canonical)))
    for efficacy_name in efficacies:
        efficacy_node_id = f"efficacy::{exegesis_id}::{_slugify(efficacy_name)}"
        add_node(
            NodeLabel.EFFICACY.value,
            efficacy_node_id,
            {
                "name": efficacy_name,
                "type": HERB_EFFICACY_NODE_TYPE,
                "description": f"{canonical}相关功效",
                **EfficacyNodeContract.build_properties(
                    herb_canonical=canonical,
                    source_exegesis_id=exegesis_id,
                ),
                "confidence": 1.0,
            },
        )
        add_edge(
            herb_node_id,
            efficacy_node_id,
            RelType.HAS_EFFICACY.value,
            NodeLabel.HERB.value,
            NodeLabel.EFFICACY.value,
            {"cycle_id": cycle_id, "phase": phase},
        )
        add_edge(
            exegesis_node_id,
            efficacy_node_id,
            RelType.EXPLAINS_EFFICACY.value,
            NodeLabel.EXEGESIS_ENTRY.value,
            NodeLabel.EFFICACY.value,
            {"cycle_id": cycle_id, "phase": phase, "semantic_scope": semantic_scope},
        )


def _add_formula_exegesis_semantics(
    *,
    add_node: Any,
    add_edge: Any,
    cycle_id: str,
    phase: str,
    exegesis_id: str,
    exegesis_node_id: str,
    formula_node_id: str,
    canonical: str,
    semantic_scope: str,
) -> None:
    composition = TCMRelationshipDefinitions.get_formula_composition(canonical)
    for role_name, rel_type in _FORMULA_ROLE_TO_RELTYPE.items():
        members = list(dict.fromkeys(composition.get(role_name) or []))
        for herb_name in members:
            herb_node_id = f"formula_component::{exegesis_id}::{_slugify(role_name)}::{_slugify(herb_name)}"
            add_node(
                NodeLabel.HERB.value,
                herb_node_id,
                {
                    "name": herb_name,
                    "type": FORMULA_COMPONENT_NODE_TYPE,
                    "description": f"{canonical}组成药物",
                    **FormulaComponentNodeContract.build_properties(
                        formula_canonical=canonical,
                        source_exegesis_id=exegesis_id,
                        formula_role=role_name,
                    ),
                    "confidence": 1.0,
                },
            )
            add_edge(
                formula_node_id,
                herb_node_id,
                rel_type,
                NodeLabel.FORMULA.value,
                NodeLabel.HERB.value,
                {"cycle_id": cycle_id, "phase": phase, "formula_role": role_name},
            )
            add_edge(
                exegesis_node_id,
                herb_node_id,
                RelType.EXPLAINS_FORMULA_COMPONENT.value,
                NodeLabel.EXEGESIS_ENTRY.value,
                NodeLabel.HERB.value,
                {"cycle_id": cycle_id, "phase": phase, "semantic_scope": semantic_scope, "formula_role": role_name},
            )


def _add_syndrome_exegesis_semantics(
    *,
    add_node: Any,
    add_edge: Any,
    cycle_id: str,
    phase: str,
    exegesis_id: str,
    exegesis_node_id: str,
    syndrome_node_id: str,
    canonical: str,
    semantic_scope: str,
    entry: Mapping[str, Any],
) -> None:
    syndrome_info = TCMRelationshipDefinitions.get_syndrome_definition(canonical)
    symptoms = list(dict.fromkeys(syndrome_info.get("symptoms") or []))
    pathogenesis = str(syndrome_info.get("pathogenesis") or "").strip()
    manifestation_source = resolve_manifestation_source(entry)
    for symptom_name in symptoms:
        symptom_node_id = f"term::symptom::{_slugify(symptom_name)}"
        add_node(
            NodeLabel.SYMPTOM.value,
            symptom_node_id,
            {
                "name": symptom_name,
                "type": "syndrome_symptom",
                "description": f"{canonical}典型表现",
                **SymptomNodeContract.build_properties(
                    syndrome_canonical=canonical,
                    source_exegesis_id=exegesis_id,
                    manifestation_source=manifestation_source,
                    symptom_category=SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION,
                ),
                "confidence": 1.0,
            },
        )
        add_edge(
            symptom_node_id,
            syndrome_node_id,
            RelType.SYMPTOM_OF.value,
            NodeLabel.SYMPTOM.value,
            NodeLabel.SYNDROME.value,
            {"cycle_id": cycle_id, "phase": phase},
        )
        add_edge(
            exegesis_node_id,
            symptom_node_id,
            RelType.EXPLAINS_SYMPTOM.value,
            NodeLabel.EXEGESIS_ENTRY.value,
            NodeLabel.SYMPTOM.value,
            {"cycle_id": cycle_id, "phase": phase, "semantic_scope": semantic_scope},
        )
    if pathogenesis:
        pathogenesis_node_id = f"term::property::pathogenesis::{_slugify(canonical)}"
        add_node(
            NodeLabel.PROPERTY.value,
            pathogenesis_node_id,
            {
                "name": f"{canonical}病机",
                "type": PATHOGENESIS_PROPERTY_TYPE,
                "description": pathogenesis,
                **PathogenesisNodeContract.build_properties(
                    syndrome_canonical=canonical,
                    source_exegesis_id=exegesis_id,
                ),
                "confidence": 1.0,
            },
        )
        add_edge(
            syndrome_node_id,
            pathogenesis_node_id,
            RelType.RELATED_TO.value,
            NodeLabel.SYNDROME.value,
            NodeLabel.PROPERTY.value,
            {"cycle_id": cycle_id, "phase": phase, "property_kind": "pathogenesis"},
        )
        add_edge(
            exegesis_node_id,
            pathogenesis_node_id,
            RelType.EXPLAINS_PATHOGENESIS.value,
            NodeLabel.EXEGESIS_ENTRY.value,
            NodeLabel.PROPERTY.value,
            {"cycle_id": cycle_id, "phase": phase, "semantic_scope": semantic_scope},
        )


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
