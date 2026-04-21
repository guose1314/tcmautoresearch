from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

GRAPH_TRACE_FIELD_SYMPTOM_CATEGORY = "symptom_category"
GRAPH_TRACE_FIELD_MANIFESTATION_SOURCE = "manifestation_source"
GRAPH_TRACE_FIELD_SYNDROME_CANONICAL = "syndrome_canonical"
GRAPH_TRACE_FIELD_SOURCE_SYNDROME = "source_syndrome"
GRAPH_TRACE_FIELD_HERB_CANONICAL = "herb_canonical"
GRAPH_TRACE_FIELD_SOURCE_HERB = "source_herb"
GRAPH_TRACE_FIELD_FORMULA_CANONICAL = "formula_canonical"
GRAPH_TRACE_FIELD_SOURCE_FORMULA = "source_formula"
GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID = "source_exegesis_id"
GRAPH_TRACE_FIELD_FORMULA_ROLE = "formula_role"
GRAPH_TRACE_FIELD_SEMANTIC_SCOPE = "semantic_scope"
GRAPH_TRACE_FIELD_PROVENANCE_KIND = "provenance_kind"

GRAPH_TRACEABILITY_FIELDS = frozenset({
    GRAPH_TRACE_FIELD_SYMPTOM_CATEGORY,
    GRAPH_TRACE_FIELD_MANIFESTATION_SOURCE,
    GRAPH_TRACE_FIELD_SYNDROME_CANONICAL,
    GRAPH_TRACE_FIELD_SOURCE_SYNDROME,
    GRAPH_TRACE_FIELD_HERB_CANONICAL,
    GRAPH_TRACE_FIELD_SOURCE_HERB,
    GRAPH_TRACE_FIELD_FORMULA_CANONICAL,
    GRAPH_TRACE_FIELD_SOURCE_FORMULA,
    GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
    GRAPH_TRACE_FIELD_FORMULA_ROLE,
    GRAPH_TRACE_FIELD_SEMANTIC_SCOPE,
    GRAPH_TRACE_FIELD_PROVENANCE_KIND,
})

SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION = "typical_manifestation"
HERB_EFFICACY_NODE_TYPE = "herb_efficacy"
FORMULA_COMPONENT_NODE_TYPE = "formula_component"
PATHOGENESIS_PROPERTY_TYPE = "pathogenesis"

TRACEABILITY_KIND_SYMPTOM = "symptom"
TRACEABILITY_KIND_PATHOGENESIS = "pathogenesis"
TRACEABILITY_KIND_EFFICACY = "efficacy"
TRACEABILITY_KIND_FORMULA_COMPONENT = "formula_component"
TRACEABILITY_KIND_HERB_PROVENANCE_EDGE = "herb_provenance_edge"
TRACEABILITY_KIND_FORMULA_PROVENANCE_EDGE = "formula_provenance_edge"

PROVENANCE_KIND_HERB_EXEGESIS = "herb_exegesis"
PROVENANCE_KIND_FORMULA_EXEGESIS = "formula_exegesis"

MANIFESTATION_SOURCE_STRUCTURED = "structured_tcm_knowledge"
MANIFESTATION_SOURCE_DICTIONARY = "dictionary_exegesis"
MANIFESTATION_SOURCE_MANUAL = "manual_review"

MANIFESTATION_SOURCES = frozenset({
    MANIFESTATION_SOURCE_STRUCTURED,
    MANIFESTATION_SOURCE_DICTIONARY,
    MANIFESTATION_SOURCE_MANUAL,
})


def build_syndrome_traceability_properties(
    *,
    syndrome_canonical: str,
    source_exegesis_id: str,
) -> Dict[str, str]:
    return {
        GRAPH_TRACE_FIELD_SYNDROME_CANONICAL: syndrome_canonical,
        GRAPH_TRACE_FIELD_SOURCE_SYNDROME: syndrome_canonical,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID: source_exegesis_id,
    }


def build_herb_traceability_properties(
    *,
    herb_canonical: str,
    source_exegesis_id: str,
) -> Dict[str, str]:
    return {
        GRAPH_TRACE_FIELD_HERB_CANONICAL: herb_canonical,
        GRAPH_TRACE_FIELD_SOURCE_HERB: herb_canonical,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID: source_exegesis_id,
    }


def build_formula_traceability_properties(
    *,
    formula_canonical: str,
    source_exegesis_id: str,
    formula_role: Optional[str] = None,
) -> Dict[str, str]:
    properties = {
        GRAPH_TRACE_FIELD_FORMULA_CANONICAL: formula_canonical,
        GRAPH_TRACE_FIELD_SOURCE_FORMULA: formula_canonical,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID: source_exegesis_id,
    }
    if formula_role:
        properties[GRAPH_TRACE_FIELD_FORMULA_ROLE] = formula_role
    return properties


def build_herb_provenance_edge_properties(
    *,
    herb_canonical: str,
    source_exegesis_id: str,
    semantic_scope: str,
) -> Dict[str, str]:
    return {
        **build_herb_traceability_properties(
            herb_canonical=herb_canonical,
            source_exegesis_id=source_exegesis_id,
        ),
        GRAPH_TRACE_FIELD_SEMANTIC_SCOPE: semantic_scope,
        GRAPH_TRACE_FIELD_PROVENANCE_KIND: PROVENANCE_KIND_HERB_EXEGESIS,
    }


def build_formula_provenance_edge_properties(
    *,
    formula_canonical: str,
    source_exegesis_id: str,
    semantic_scope: str,
) -> Dict[str, str]:
    return {
        **build_formula_traceability_properties(
            formula_canonical=formula_canonical,
            source_exegesis_id=source_exegesis_id,
        ),
        GRAPH_TRACE_FIELD_SEMANTIC_SCOPE: semantic_scope,
        GRAPH_TRACE_FIELD_PROVENANCE_KIND: PROVENANCE_KIND_FORMULA_EXEGESIS,
    }


def build_symptom_traceability_properties(
    *,
    syndrome_canonical: str,
    source_exegesis_id: str,
    manifestation_source: str,
    symptom_category: str = SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION,
) -> Dict[str, str]:
    return {
        GRAPH_TRACE_FIELD_SYMPTOM_CATEGORY: symptom_category,
        GRAPH_TRACE_FIELD_MANIFESTATION_SOURCE: manifestation_source,
        **build_syndrome_traceability_properties(
            syndrome_canonical=syndrome_canonical,
            source_exegesis_id=source_exegesis_id,
        ),
    }


class SymptomNodeContract:
    label = "Symptom"
    traceability_kind = TRACEABILITY_KIND_SYMPTOM
    required_fields = frozenset({
        GRAPH_TRACE_FIELD_SYMPTOM_CATEGORY,
        GRAPH_TRACE_FIELD_MANIFESTATION_SOURCE,
        GRAPH_TRACE_FIELD_SYNDROME_CANONICAL,
        GRAPH_TRACE_FIELD_SOURCE_SYNDROME,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
    })

    @staticmethod
    def build_properties(
        *,
        syndrome_canonical: str,
        source_exegesis_id: str,
        manifestation_source: str,
        symptom_category: str = SYMPTOM_CATEGORY_TYPICAL_MANIFESTATION,
    ) -> Dict[str, str]:
        return build_symptom_traceability_properties(
            syndrome_canonical=syndrome_canonical,
            source_exegesis_id=source_exegesis_id,
            manifestation_source=manifestation_source,
            symptom_category=symptom_category,
        )


class PathogenesisNodeContract:
    label = "Property"
    property_type = PATHOGENESIS_PROPERTY_TYPE
    traceability_kind = TRACEABILITY_KIND_PATHOGENESIS
    required_fields = frozenset({
        GRAPH_TRACE_FIELD_SYNDROME_CANONICAL,
        GRAPH_TRACE_FIELD_SOURCE_SYNDROME,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
    })

    @staticmethod
    def build_properties(
        *,
        syndrome_canonical: str,
        source_exegesis_id: str,
    ) -> Dict[str, str]:
        return build_syndrome_traceability_properties(
            syndrome_canonical=syndrome_canonical,
            source_exegesis_id=source_exegesis_id,
        )


class EfficacyNodeContract:
    label = "Efficacy"
    node_type = HERB_EFFICACY_NODE_TYPE
    traceability_kind = TRACEABILITY_KIND_EFFICACY
    required_fields = frozenset({
        GRAPH_TRACE_FIELD_HERB_CANONICAL,
        GRAPH_TRACE_FIELD_SOURCE_HERB,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
    })

    @staticmethod
    def build_properties(
        *,
        herb_canonical: str,
        source_exegesis_id: str,
    ) -> Dict[str, str]:
        return build_herb_traceability_properties(
            herb_canonical=herb_canonical,
            source_exegesis_id=source_exegesis_id,
        )


class FormulaComponentNodeContract:
    label = "Herb"
    node_type = FORMULA_COMPONENT_NODE_TYPE
    traceability_kind = TRACEABILITY_KIND_FORMULA_COMPONENT
    required_fields = frozenset({
        GRAPH_TRACE_FIELD_FORMULA_CANONICAL,
        GRAPH_TRACE_FIELD_SOURCE_FORMULA,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
        GRAPH_TRACE_FIELD_FORMULA_ROLE,
    })

    @staticmethod
    def build_properties(
        *,
        formula_canonical: str,
        source_exegesis_id: str,
        formula_role: str,
    ) -> Dict[str, str]:
        return build_formula_traceability_properties(
            formula_canonical=formula_canonical,
            source_exegesis_id=source_exegesis_id,
            formula_role=formula_role,
        )


class HerbProvenanceEdgeContract:
    source_label = "ExegesisEntry"
    target_label = "Herb"
    relationship_type = "EXPLAINS_HERB"
    traceability_kind = TRACEABILITY_KIND_HERB_PROVENANCE_EDGE
    required_fields = frozenset({
        GRAPH_TRACE_FIELD_HERB_CANONICAL,
        GRAPH_TRACE_FIELD_SOURCE_HERB,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
        GRAPH_TRACE_FIELD_SEMANTIC_SCOPE,
        GRAPH_TRACE_FIELD_PROVENANCE_KIND,
    })

    @staticmethod
    def build_properties(
        *,
        herb_canonical: str,
        source_exegesis_id: str,
        semantic_scope: str,
    ) -> Dict[str, str]:
        return build_herb_provenance_edge_properties(
            herb_canonical=herb_canonical,
            source_exegesis_id=source_exegesis_id,
            semantic_scope=semantic_scope,
        )


class FormulaProvenanceEdgeContract:
    source_label = "ExegesisEntry"
    target_label = "Formula"
    relationship_type = "EXPLAINS_FORMULA"
    traceability_kind = TRACEABILITY_KIND_FORMULA_PROVENANCE_EDGE
    required_fields = frozenset({
        GRAPH_TRACE_FIELD_FORMULA_CANONICAL,
        GRAPH_TRACE_FIELD_SOURCE_FORMULA,
        GRAPH_TRACE_FIELD_SOURCE_EXEGESIS_ID,
        GRAPH_TRACE_FIELD_SEMANTIC_SCOPE,
        GRAPH_TRACE_FIELD_PROVENANCE_KIND,
    })

    @staticmethod
    def build_properties(
        *,
        formula_canonical: str,
        source_exegesis_id: str,
        semantic_scope: str,
    ) -> Dict[str, str]:
        return build_formula_provenance_edge_properties(
            formula_canonical=formula_canonical,
            source_exegesis_id=source_exegesis_id,
            semantic_scope=semantic_scope,
        )


def get_traceability_contract(
    label: str,
    properties: Mapping[str, Any],
) -> Optional[type[Any]]:
    if label == SymptomNodeContract.label:
        return SymptomNodeContract
    if (
        label == EfficacyNodeContract.label
        and str(properties.get("type") or "").strip() == EfficacyNodeContract.node_type
    ):
        return EfficacyNodeContract
    if (
        label == FormulaComponentNodeContract.label
        and str(properties.get("type") or "").strip() == FormulaComponentNodeContract.node_type
    ):
        return FormulaComponentNodeContract
    if (
        label == PathogenesisNodeContract.label
        and str(properties.get("type") or "").strip() == PathogenesisNodeContract.property_type
    ):
        return PathogenesisNodeContract
    return None


def get_graph_traceability_kind(label: str, properties: Mapping[str, Any]) -> str:
    contract = get_traceability_contract(label, properties)
    if contract is None:
        return ""
    return str(getattr(contract, "traceability_kind", "") or "")


def get_edge_traceability_contract(
    source_label: str,
    target_label: str,
    relationship_type: str,
    properties: Mapping[str, Any],
) -> Optional[type[Any]]:
    if (
        source_label == HerbProvenanceEdgeContract.source_label
        and target_label == HerbProvenanceEdgeContract.target_label
        and relationship_type == HerbProvenanceEdgeContract.relationship_type
        and str(properties.get(GRAPH_TRACE_FIELD_PROVENANCE_KIND) or "").strip() == PROVENANCE_KIND_HERB_EXEGESIS
    ):
        return HerbProvenanceEdgeContract
    if (
        source_label == FormulaProvenanceEdgeContract.source_label
        and target_label == FormulaProvenanceEdgeContract.target_label
        and relationship_type == FormulaProvenanceEdgeContract.relationship_type
        and str(properties.get(GRAPH_TRACE_FIELD_PROVENANCE_KIND) or "").strip() == PROVENANCE_KIND_FORMULA_EXEGESIS
    ):
        return FormulaProvenanceEdgeContract
    return None


def get_graph_edge_traceability_kind(
    source_label: str,
    target_label: str,
    relationship_type: str,
    properties: Mapping[str, Any],
) -> str:
    contract = get_edge_traceability_contract(source_label, target_label, relationship_type, properties)
    if contract is None:
        return ""
    return str(getattr(contract, "traceability_kind", "") or "")


def has_complete_graph_edge_traceability(
    source_label: str,
    target_label: str,
    relationship_type: str,
    properties: Mapping[str, Any],
) -> bool:
    contract = get_edge_traceability_contract(source_label, target_label, relationship_type, properties)
    if contract is None:
        return False
    for field_name in getattr(contract, "required_fields", frozenset()):
        value = properties.get(field_name)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def has_complete_graph_traceability(label: str, properties: Mapping[str, Any]) -> bool:
    contract = get_traceability_contract(label, properties)
    if contract is None:
        return False
    for field_name in getattr(contract, "required_fields", frozenset()):
        value = properties.get(field_name)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def resolve_manifestation_source(entry: Mapping[str, Any]) -> str:
    review_status = str(entry.get("review_status") or "").strip().lower()
    reviewer = str(entry.get("reviewer") or "").strip()
    if reviewer or review_status in {"accepted", "rejected"}:
        return MANIFESTATION_SOURCE_MANUAL

    definition_source = str(entry.get("definition_source") or "").strip().lower()
    if definition_source == MANIFESTATION_SOURCE_STRUCTURED:
        return MANIFESTATION_SOURCE_STRUCTURED
    if definition_source in {"config_terminology_standard", "terminology_note", "external_dictionary"}:
        return MANIFESTATION_SOURCE_DICTIONARY
    return MANIFESTATION_SOURCE_STRUCTURED