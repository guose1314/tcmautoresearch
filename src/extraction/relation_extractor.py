"""独立关系抽取模块：从实体列表中抽取语义关系。"""

from __future__ import annotations

from typing import Any, Dict, List

from src.knowledge.ontology_manager import OntologyManager
from src.semantic_modeling.tcm_relationships import (
    RelationshipType,
    TCMRelationshipDefinitions,
)


class RelationExtractor:
    """将关系抽取从 SemanticGraphBuilder 中解耦。"""

    def __init__(self) -> None:
        self.relationship_counts: Dict[str, int] = {}
        self.ontology = OntologyManager()

    def extract(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self.relationship_counts.clear()
        edges: List[Dict[str, Any]] = []

        formulas = [e for e in entities if self.ontology.normalize_node_type(str(e.get("type") or "")) == "formula" and e.get("name")]
        herbs = [e for e in entities if self.ontology.normalize_node_type(str(e.get("type") or "")) == "herb" and e.get("name")]
        syndromes = [e for e in entities if self.ontology.normalize_node_type(str(e.get("type") or "")) == "syndrome" and e.get("name")]

        herb_name_to_node = {
            str(herb["name"]): self.ontology.make_node_id("herb", str(herb["name"]))
            for herb in herbs
        }

        # 策略1：方剂 -> 药物（君臣佐使）
        for formula in formulas:
            formula_name = str(formula["name"])
            formula_node = self.ontology.make_node_id("formula", formula_name)
            composition = TCMRelationshipDefinitions.get_formula_composition(formula_name)
            if not composition:
                continue

            role_groups = {
                RelationshipType.SOVEREIGN: composition.get("sovereign", []),
                RelationshipType.MINISTER: composition.get("minister", []),
                RelationshipType.ASSISTANT: composition.get("assistant", []),
                RelationshipType.ENVOY: composition.get("envoy", []),
            }

            for role, herb_names in role_groups.items():
                for herb_name in herb_names:
                    herb_node = herb_name_to_node.get(str(herb_name))
                    if not herb_node:
                        continue
                    if self.ontology.validate_edge(formula_node, herb_node, role.value):
                        edges.append(
                            self._edge(
                                source=formula_node,
                                target=herb_node,
                                rel_type=role,
                                confidence=0.95,
                            )
                        )

        # 策略2：药物 -> 功效
        for herb in herbs:
            herb_name = str(herb["name"])
            herb_node = self.ontology.make_node_id("herb", herb_name)
            efficacies = TCMRelationshipDefinitions.get_herb_efficacy(herb_name)
            for efficacy in efficacies:
                efficacy_node = self.ontology.make_node_id("efficacy", str(efficacy))
                if self.ontology.validate_edge(herb_node, efficacy_node, RelationshipType.EFFICACY.value):
                    edges.append(
                        self._edge(
                            source=herb_node,
                            target=efficacy_node,
                            rel_type=RelationshipType.EFFICACY,
                            confidence=0.90,
                        )
                    )

        # 策略3：方剂/药物 -> 证候（治疗）
        for syndrome in syndromes:
            syndrome_node = self.ontology.make_node_id("syndrome", str(syndrome["name"]))
            for formula in formulas:
                formula_node = self.ontology.make_node_id("formula", str(formula["name"]))
                if self.ontology.validate_edge(formula_node, syndrome_node, RelationshipType.TREATS.value):
                    edges.append(
                        self._edge(
                            source=formula_node,
                            target=syndrome_node,
                            rel_type=RelationshipType.TREATS,
                            confidence=0.75,
                        )
                    )

            for herb in herbs:
                herb_node = self.ontology.make_node_id("herb", str(herb["name"]))
                if self.ontology.validate_edge(herb_node, syndrome_node, RelationshipType.TREATS.value):
                    edges.append(
                        self._edge(
                            source=herb_node,
                            target=syndrome_node,
                            rel_type=RelationshipType.TREATS,
                            confidence=0.60,
                        )
                    )

        return edges

    def relationship_statistics(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        valid_names = {rel.name for rel in RelationshipType}
        for rel_type, count in self.relationship_counts.items():
            enum_name = rel_type.upper()
            enum_value = (
                RelationshipType[enum_name]
                if enum_name in valid_names
                else RelationshipType.COMBINES_WITH
            )
            stats[rel_type] = {
                "count": count,
                "description": TCMRelationshipDefinitions.get_relationship_description(enum_value),
            }
        return stats

    def _edge(
        self,
        source: str,
        target: str,
        rel_type: RelationshipType,
        confidence: float,
    ) -> Dict[str, Any]:
        rel_type_value = rel_type.value
        self.relationship_counts[rel_type_value] = self.relationship_counts.get(rel_type_value, 0) + 1
        return {
            "source": source,
            "target": target,
            "attributes": {
                "relationship_type": rel_type_value,
                "relationship_name": rel_type.name,
                "description": TCMRelationshipDefinitions.get_relationship_description(rel_type),
                "confidence": confidence,
            },
        }