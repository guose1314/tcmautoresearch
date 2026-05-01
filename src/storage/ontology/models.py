from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ONTOLOGY_CONTRACT_VERSION = "ontology-registry-v1"

REQUIRED_NODE_LABELS: tuple[str, ...] = (
    "Literature",
    "VersionWitness",
    "VersionLineage",
    "Formula",
    "Herb",
    "Symptom",
    "Syndrome",
    "Pathogenesis",
    "EvidenceClaim",
    "Citation",
    "ResearchTopic",
)

REQUIRED_RELATIONSHIP_TYPES: tuple[str, ...] = (
    "APPEARS_IN",
    "CONTAINS",
    "TREATS",
    "BELONGS_TO_LINEAGE",
    "EVIDENCE_FOR",
    "CITES",
    "BELONGS_TO_TOPIC",
)

_GRAPH_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RELATIONSHIP_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SUPPORTED_PROPERTY_TYPES = {
    "string",
    "integer",
    "float",
    "number",
    "boolean",
    "datetime",
    "date",
    "list",
    "dict",
    "json",
}


class OntologyValidationKind(str, Enum):
    NODE = "node"
    RELATIONSHIP = "relationship"
    TRACEABILITY = "traceability"


class OntologyProperty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., description="Portable property type name.")
    description: str = ""
    required: bool = False
    unique: bool = False
    indexed: bool = False
    fulltext: bool = False
    item_type: str = ""

    @field_validator("type")
    @classmethod
    def validate_property_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in _SUPPORTED_PROPERTY_TYPES:
            raise ValueError(
                f"unsupported property type '{value}', expected one of {sorted(_SUPPORTED_PROPERTY_TYPES)}"
            )
        return normalized


class OntologyNodeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    description: str = ""
    properties: Dict[str, OntologyProperty] = Field(default_factory=dict)
    required_properties: List[str] = Field(default_factory=lambda: ["id"])
    unique_key: str = "id"
    indexes: List[str] = Field(default_factory=list)
    fulltext_fields: List[str] = Field(default_factory=list)
    traceability_fields: List[str] = Field(default_factory=list)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        label = str(value or "").strip()
        if not _GRAPH_NAME_PATTERN.match(label):
            raise ValueError(f"illegal node label '{value}'")
        return label

    @model_validator(mode="after")
    def validate_property_contract(self) -> "OntologyNodeDefinition":
        _validate_property_names(
            self.properties, OntologyValidationKind.NODE, self.label
        )
        _validate_declared_fields(
            self.required_properties,
            self.properties,
            kind="required_properties",
            owner=f"node '{self.label}'",
        )
        if self.unique_key:
            _validate_declared_fields(
                [self.unique_key],
                self.properties,
                kind="unique_key",
                owner=f"node '{self.label}'",
            )
        _validate_declared_fields(
            self.indexes,
            self.properties,
            kind="indexes",
            owner=f"node '{self.label}'",
        )
        _validate_declared_fields(
            self.fulltext_fields,
            self.properties,
            kind="fulltext_fields",
            owner=f"node '{self.label}'",
        )
        return self


class OntologyRelationshipDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    description: str = ""
    source_labels: List[str] = Field(default_factory=list)
    target_labels: List[str] = Field(default_factory=list)
    properties: Dict[str, OntologyProperty] = Field(default_factory=dict)
    required_properties: List[str] = Field(default_factory=list)
    traceability_fields: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_source_target_aliases(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        if "source" in payload and "source_labels" not in payload:
            payload["source_labels"] = _coerce_list(payload.pop("source"))
        if "target" in payload and "target_labels" not in payload:
            payload["target_labels"] = _coerce_list(payload.pop("target"))
        payload["source_labels"] = _coerce_list(payload.get("source_labels"))
        payload["target_labels"] = _coerce_list(payload.get("target_labels"))
        return payload

    @field_validator("type")
    @classmethod
    def validate_relationship_type(cls, value: str) -> str:
        rel_type = str(value or "").strip()
        if not _RELATIONSHIP_TYPE_PATTERN.match(rel_type):
            raise ValueError(f"illegal relationship type '{value}'")
        return rel_type

    @field_validator("source_labels", "target_labels")
    @classmethod
    def validate_endpoint_labels(cls, value: List[str]) -> List[str]:
        labels = [str(item or "").strip() for item in value if str(item or "").strip()]
        if not labels:
            raise ValueError("relationship endpoint labels must not be empty")
        for label in labels:
            if not _GRAPH_NAME_PATTERN.match(label):
                raise ValueError(f"illegal relationship endpoint label '{label}'")
        return labels

    @model_validator(mode="after")
    def validate_property_contract(self) -> "OntologyRelationshipDefinition":
        _validate_property_names(
            self.properties, OntologyValidationKind.RELATIONSHIP, self.type
        )
        _validate_declared_fields(
            self.required_properties,
            self.properties,
            kind="required_properties",
            owner=f"relationship '{self.type}'",
        )
        return self


class OntologyRegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = ONTOLOGY_CONTRACT_VERSION
    ontology_id: str
    schema_version: str
    description: str = ""
    traceability: Dict[str, OntologyProperty] = Field(default_factory=dict)
    nodes: Dict[str, OntologyNodeDefinition] = Field(default_factory=dict)
    relationships: Dict[str, OntologyRelationshipDefinition] = Field(
        default_factory=dict
    )

    @model_validator(mode="before")
    @classmethod
    def inject_mapping_keys(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        payload["nodes"] = _inject_definition_keys(
            payload.get("nodes"), key_field="label"
        )
        payload["relationships"] = _inject_definition_keys(
            payload.get("relationships"), key_field="type"
        )
        return payload

    @field_validator("contract_version")
    @classmethod
    def validate_contract_version(cls, value: str) -> str:
        if value != ONTOLOGY_CONTRACT_VERSION:
            raise ValueError(
                f"contract_version must be '{ONTOLOGY_CONTRACT_VERSION}', got '{value}'"
            )
        return value

    @model_validator(mode="after")
    def validate_registry_contract(self) -> "OntologyRegistryDocument":
        _validate_property_names(
            self.traceability, OntologyValidationKind.TRACEABILITY, "traceability"
        )
        missing_nodes = sorted(set(REQUIRED_NODE_LABELS) - set(self.nodes))
        if missing_nodes:
            raise ValueError(f"missing required node labels: {missing_nodes}")
        missing_relationships = sorted(
            set(REQUIRED_RELATIONSHIP_TYPES) - set(self.relationships)
        )
        if missing_relationships:
            raise ValueError(
                f"missing required relationship types: {missing_relationships}"
            )
        for key, node in self.nodes.items():
            if key != node.label:
                raise ValueError(
                    f"node mapping key '{key}' does not match label '{node.label}'"
                )
            self._validate_traceability_fields(
                node.traceability_fields, owner=f"node '{node.label}'"
            )
        node_labels = set(self.nodes)
        for key, relationship in self.relationships.items():
            if key != relationship.type:
                raise ValueError(
                    f"relationship mapping key '{key}' does not match type '{relationship.type}'"
                )
            unknown_sources = sorted(set(relationship.source_labels) - node_labels)
            unknown_targets = sorted(set(relationship.target_labels) - node_labels)
            if unknown_sources or unknown_targets:
                raise ValueError(
                    f"relationship '{relationship.type}' references unknown endpoints: "
                    f"sources={unknown_sources}, targets={unknown_targets}"
                )
            self._validate_traceability_fields(
                relationship.traceability_fields,
                owner=f"relationship '{relationship.type}'",
            )
        return self

    def _validate_traceability_fields(self, fields: List[str], *, owner: str) -> None:
        missing = sorted(set(fields) - set(self.traceability))
        if missing:
            raise ValueError(
                f"{owner} declares traceability fields absent from registry: {missing}"
            )


def is_legal_node_label(label: str) -> bool:
    return bool(_GRAPH_NAME_PATTERN.match(str(label or "").strip()))


def is_legal_relationship_type(rel_type: str) -> bool:
    return bool(_RELATIONSHIP_TYPE_PATTERN.match(str(rel_type or "").strip()))


def _inject_definition_keys(value: Any, *, key_field: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    normalized: Dict[str, Any] = {}
    for key, raw_definition in value.items():
        definition = dict(raw_definition) if isinstance(raw_definition, Mapping) else {}
        definition.setdefault(key_field, str(key))
        normalized[str(key)] = definition
    return normalized


def _validate_property_names(
    properties: Mapping[str, OntologyProperty],
    kind: OntologyValidationKind,
    owner: str,
) -> None:
    for property_name in properties:
        if not _GRAPH_NAME_PATTERN.match(str(property_name)):
            raise ValueError(
                f"illegal {kind.value} property name '{property_name}' in {owner}"
            )


def _validate_declared_fields(
    field_names: List[str],
    properties: Mapping[str, OntologyProperty],
    *,
    kind: str,
    owner: str,
) -> None:
    missing = sorted(set(field_names) - set(properties))
    if missing:
        raise ValueError(
            f"{owner} {kind} references undefined property field(s): {missing}"
        )


def _coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


__all__ = [
    "ONTOLOGY_CONTRACT_VERSION",
    "REQUIRED_NODE_LABELS",
    "REQUIRED_RELATIONSHIP_TYPES",
    "OntologyProperty",
    "OntologyNodeDefinition",
    "OntologyRelationshipDefinition",
    "OntologyRegistryDocument",
    "is_legal_node_label",
    "is_legal_relationship_type",
]
