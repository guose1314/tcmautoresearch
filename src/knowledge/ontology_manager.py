"""TCM 本体管理：节点类型与关系类型约束的统一入口。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Set, Tuple

from src.semantic_modeling.tcm_relationships import RelationshipType


@dataclass(frozen=True)
class RelationshipConstraint:
    relationship_type: str
    source_types: Set[str]
    target_types: Set[str]


class OntologyManager:
    """统一管理实体节点类型、节点 ID 规范与关系类型约束。"""

    NODE_TYPES: Set[str] = {
        "formula",
        "herb",
        "syndrome",
        "efficacy",
        "theory",
        "property",
        "taste",
        "meridian",
        "symptom",
        "acupoint",
        "generic",
    }

    NODE_TYPE_ALIASES: Dict[str, str] = {
        "formulas": "formula",
        "herbs": "herb",
        "syndromes": "syndrome",
        "effects": "efficacy",
        "efficacies": "efficacy",
        "common": "generic",
        "unknown": "generic",
    }

    EMBEDDING_ITEM_TYPES: Set[str] = {
        "formula",
        "syndrome",
        "herb",
        "generic",
    }

    def __init__(self) -> None:
        self.relationship_types: Set[str] = {rel.value for rel in RelationshipType}
        self.relationship_constraints: Dict[str, RelationshipConstraint] = {
            RelationshipType.SOVEREIGN.value: RelationshipConstraint(
                relationship_type=RelationshipType.SOVEREIGN.value,
                source_types={"formula"},
                target_types={"herb"},
            ),
            RelationshipType.MINISTER.value: RelationshipConstraint(
                relationship_type=RelationshipType.MINISTER.value,
                source_types={"formula"},
                target_types={"herb"},
            ),
            RelationshipType.ASSISTANT.value: RelationshipConstraint(
                relationship_type=RelationshipType.ASSISTANT.value,
                source_types={"formula"},
                target_types={"herb"},
            ),
            RelationshipType.ENVOY.value: RelationshipConstraint(
                relationship_type=RelationshipType.ENVOY.value,
                source_types={"formula"},
                target_types={"herb"},
            ),
            RelationshipType.EFFICACY.value: RelationshipConstraint(
                relationship_type=RelationshipType.EFFICACY.value,
                source_types={"herb", "formula"},
                target_types={"efficacy"},
            ),
            RelationshipType.TREATS.value: RelationshipConstraint(
                relationship_type=RelationshipType.TREATS.value,
                source_types={"herb", "formula"},
                target_types={"syndrome"},
            ),
            RelationshipType.ENTERS.value: RelationshipConstraint(
                relationship_type=RelationshipType.ENTERS.value,
                source_types={"herb", "formula"},
                target_types={"meridian", "theory"},
            ),
            RelationshipType.HAS_PROPERTY.value: RelationshipConstraint(
                relationship_type=RelationshipType.HAS_PROPERTY.value,
                source_types={"herb", "formula"},
                target_types={"property", "taste", "theory"},
            ),
        }

    def normalize_node_type(self, node_type: str, strict: bool = False) -> str:
        value = (node_type or "").strip().lower()
        if value in self.NODE_TYPES:
            return value
        if value in self.NODE_TYPE_ALIASES:
            return self.NODE_TYPE_ALIASES[value]
        if strict:
            raise ValueError(f"不支持的节点类型: {node_type}")
        return "generic"

    def is_valid_node_type(self, node_type: str) -> bool:
        value = (node_type or "").strip().lower()
        return value in self.NODE_TYPES or value in self.NODE_TYPE_ALIASES

    def validate_embedding_item_type(self, item_type: str) -> bool:
        normalized = self.normalize_node_type(item_type)
        return normalized in self.EMBEDDING_ITEM_TYPES

    def make_node_id(self, node_type: str, name: str) -> str:
        normalized_type = self.normalize_node_type(node_type)
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("节点名称不能为空")
        return f"{normalized_type}:{clean_name}"

    def parse_node_id(self, node_id: str) -> Tuple[str, str]:
        text = str(node_id or "")
        if ":" not in text:
            return "generic", text
        node_type, name = text.split(":", 1)
        return self.normalize_node_type(node_type), name

    def validate_relationship(
        self,
        relationship_type: str,
        source_node_type: str,
        target_node_type: str,
    ) -> bool:
        rel = (relationship_type or "").strip().lower()
        src = self.normalize_node_type(source_node_type)
        tgt = self.normalize_node_type(target_node_type)

        if rel not in self.relationship_types:
            return False
        constraint = self.relationship_constraints.get(rel)
        if constraint is None:
            return True
        return src in constraint.source_types and tgt in constraint.target_types

    def validate_edge(self, source_node_id: str, target_node_id: str, relationship_type: str) -> bool:
        src_type, _ = self.parse_node_id(source_node_id)
        tgt_type, _ = self.parse_node_id(target_node_id)
        return self.validate_relationship(relationship_type, src_type, tgt_type)

    def normalize_text_entity_type_mentions(self, text: str) -> str:
        """对配置/文本中的类型别名做规范化替换（可选工具函数）。"""
        output = text
        for alias, canonical in self.NODE_TYPE_ALIASES.items():
            output = re.sub(rf"\b{re.escape(alias)}\b", canonical, output, flags=re.IGNORECASE)
        return output


_DEFAULT_ONTOLOGY_MANAGER = OntologyManager()


def get_default_ontology_manager() -> OntologyManager:
    return _DEFAULT_ONTOLOGY_MANAGER