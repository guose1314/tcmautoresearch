from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

import yaml

from src.storage.ontology.models import (
    OntologyNodeDefinition,
    OntologyRegistryDocument,
    OntologyRelationshipDefinition,
    is_legal_node_label,
    is_legal_relationship_type,
)

DEFAULT_ONTOLOGY_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "ontology"
    / "tcm_literature_graph.yml"
)


class OntologyRegistry:
    def __init__(self, document: OntologyRegistryDocument):
        self.document = document

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OntologyRegistry":
        return cls(OntologyRegistryDocument.model_validate(dict(payload)))

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "OntologyRegistry":
        registry_path = (
            Path(path) if path is not None else DEFAULT_ONTOLOGY_REGISTRY_PATH
        )
        payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, Mapping):
            raise ValueError(
                f"ontology registry YAML must be a mapping: {registry_path}"
            )
        return cls.from_mapping(payload)

    @property
    def contract_version(self) -> str:
        return self.document.contract_version

    @property
    def ontology_id(self) -> str:
        return self.document.ontology_id

    @property
    def schema_version(self) -> str:
        return self.document.schema_version

    def node_labels(self) -> tuple[str, ...]:
        return tuple(self.document.nodes.keys())

    def relationship_types(self) -> tuple[str, ...]:
        return tuple(self.document.relationships.keys())

    def traceability_fields(self) -> tuple[str, ...]:
        return tuple(self.document.traceability.keys())

    def get_node(self, label: str) -> OntologyNodeDefinition:
        return self.document.nodes[str(label)]

    def get_relationship(self, rel_type: str) -> OntologyRelationshipDefinition:
        return self.document.relationships[str(rel_type)]

    def has_node(self, label: str) -> bool:
        return str(label) in self.document.nodes

    def has_relationship(self, rel_type: str) -> bool:
        return str(rel_type) in self.document.relationships

    def validate_node_label(self, label: str) -> bool:
        value = str(label or "").strip()
        return is_legal_node_label(value) and self.has_node(value)

    def validate_relationship_type(self, rel_type: str) -> bool:
        value = str(rel_type or "").strip()
        return is_legal_relationship_type(value) and self.has_relationship(value)

    def required_node_properties(self, label: str) -> tuple[str, ...]:
        return tuple(self.get_node(label).required_properties)

    def required_relationship_properties(self, rel_type: str) -> tuple[str, ...]:
        return tuple(self.get_relationship(rel_type).required_properties)

    def node_unique_key(self, label: str) -> str:
        return self.get_node(label).unique_key

    def unique_constraint_specs(self) -> tuple[Dict[str, str], ...]:
        specs: list[Dict[str, str]] = []
        for label, node in self.document.nodes.items():
            unique_key = str(node.unique_key or "").strip()
            if not unique_key:
                continue
            specs.append(
                {
                    "name": _schema_identifier("ontology", label, unique_key, "unique"),
                    "label": label,
                    "property": unique_key,
                }
            )
        return tuple(specs)

    def fulltext_index_specs(self) -> tuple[Dict[str, Any], ...]:
        specs: list[Dict[str, Any]] = []
        for label, node in self.document.nodes.items():
            fields = _dedupe_strings(node.fulltext_fields)
            if not fields:
                continue
            specs.append(
                {
                    "name": _schema_identifier("ontology", label, "fulltext"),
                    "label": label,
                    "properties": fields,
                }
            )
        return tuple(specs)

    def to_dict(self) -> Dict[str, Any]:
        return self.document.model_dump(mode="json")


def load_ontology_registry(path: str | Path | None = None) -> OntologyRegistry:
    return OntologyRegistry.from_file(path)


def _schema_identifier(*parts: str) -> str:
    tokens = [
        str(part or "").strip().lower() for part in parts if str(part or "").strip()
    ]
    identifier = "_".join(tokens)
    return identifier or "ontology_schema_item"


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


__all__ = [
    "DEFAULT_ONTOLOGY_REGISTRY_PATH",
    "OntologyRegistry",
    "load_ontology_registry",
]
