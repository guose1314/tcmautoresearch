"""独立关系抽取模块：从实体列表中抽取语义关系。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from src.extraction.rule_relation_quality import tier_rule_edges
from src.knowledge.ontology_manager import OntologyManager
from src.semantic_modeling.tcm_relationships import (
    RelationshipType,
    TCMRelationshipDefinitions,
)


class RelationExtractor:
    """将关系抽取从 SemanticGraphBuilder 中解耦。"""

    def __init__(self) -> None:
        self.relationship_counts: Dict[str, int] = {}
        self.relationship_tier_counts: Dict[str, int] = {
            "strong_rule": 0,
            "weak_rule": 0,
            "candidate_rule": 0,
            "rejected_rule": 0,
        }
        self.ontology = OntologyManager()

    def extract(
        self, entities: List[Dict[str, Any]], raw_text: str = ""
    ) -> List[Dict[str, Any]]:
        self.relationship_counts.clear()
        edges: List[Dict[str, Any]] = []

        normalized_entities = [item for item in entities if isinstance(item, dict)]
        formulas = self._filter_entities_by_type(normalized_entities, "formula")
        herbs = self._filter_entities_by_type(normalized_entities, "herb")
        syndromes = self._filter_entities_by_type(normalized_entities, "syndrome")

        herb_name_to_node = self._build_name_to_node_map(herbs, "herb")

        edges.extend(self._extract_formula_herb_edges(formulas, herb_name_to_node))
        edges.extend(self._extract_herb_efficacy_edges(herbs))
        edges.extend(self._extract_treats_edges(formulas, herbs, syndromes))

        scored_edges, self.relationship_tier_counts = tier_rule_edges(
            edges, normalized_entities, raw_text
        )
        return scored_edges

    def _filter_entities_by_type(
        self,
        entities: Iterable[Dict[str, Any]],
        expected_type: str,
    ) -> List[Dict[str, Any]]:
        """按标准化节点类型筛选实体。"""
        return [
            entity
            for entity in entities
            if self.ontology.normalize_node_type(str(entity.get("type") or ""))
            == expected_type
            and entity.get("name")
        ]

    def _build_name_to_node_map(
        self,
        entities: Iterable[Dict[str, Any]],
        node_type: str,
    ) -> Dict[str, str]:
        """构建实体名到节点 ID 的映射。"""
        return {
            str(entity["name"]): self.ontology.make_node_id(
                node_type, str(entity["name"])
            )
            for entity in entities
        }

    def _extract_formula_herb_edges(
        self,
        formulas: Iterable[Dict[str, Any]],
        herb_name_to_node: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """抽取方剂到药物的君臣佐使关系。"""
        edges: List[Dict[str, Any]] = []
        for formula in formulas:
            formula_name = str(formula["name"])
            formula_node = self.ontology.make_node_id("formula", formula_name)
            composition = TCMRelationshipDefinitions.get_formula_composition(
                formula_name
            )
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
                        edges.append(self._edge(formula_node, herb_node, role, 0.95))
        return edges

    def _extract_herb_efficacy_edges(
        self, herbs: Iterable[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """抽取药物到功效关系。"""
        edges: List[Dict[str, Any]] = []
        for herb in herbs:
            herb_name = str(herb["name"])
            herb_node = self.ontology.make_node_id("herb", herb_name)
            efficacies = TCMRelationshipDefinitions.get_herb_efficacy(herb_name)
            for efficacy in efficacies:
                efficacy_node = self.ontology.make_node_id("efficacy", str(efficacy))
                if self.ontology.validate_edge(
                    herb_node, efficacy_node, RelationshipType.EFFICACY.value
                ):
                    edges.append(
                        self._edge(
                            herb_node, efficacy_node, RelationshipType.EFFICACY, 0.90
                        )
                    )
        return edges

    def _extract_treats_edges(
        self,
        formulas: Iterable[Dict[str, Any]],
        herbs: Iterable[Dict[str, Any]],
        syndromes: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """抽取方剂/药物到证候治疗关系。"""
        edges: List[Dict[str, Any]] = []
        for syndrome in syndromes:
            syndrome_node = self.ontology.make_node_id(
                "syndrome", str(syndrome["name"])
            )

            for formula in formulas:
                formula_node = self.ontology.make_node_id(
                    "formula", str(formula["name"])
                )
                if self.ontology.validate_edge(
                    formula_node, syndrome_node, RelationshipType.TREATS.value
                ):
                    edges.append(
                        self._edge(
                            formula_node, syndrome_node, RelationshipType.TREATS, 0.75
                        )
                    )

            for herb in herbs:
                herb_node = self.ontology.make_node_id("herb", str(herb["name"]))
                if self.ontology.validate_edge(
                    herb_node, syndrome_node, RelationshipType.TREATS.value
                ):
                    edges.append(
                        self._edge(
                            herb_node, syndrome_node, RelationshipType.TREATS, 0.60
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
                "description": TCMRelationshipDefinitions.get_relationship_description(
                    enum_value
                ),
            }
        stats["quality_tiers"] = dict(self.relationship_tier_counts)
        return stats

    def _edge(
        self,
        source: str,
        target: str,
        rel_type: RelationshipType,
        confidence: float,
    ) -> Dict[str, Any]:
        rel_type_value = rel_type.value
        self.relationship_counts[rel_type_value] = (
            self.relationship_counts.get(rel_type_value, 0) + 1
        )
        source_type, source_name = self._node_parts(source)
        target_type, target_name = self._node_parts(target)
        return {
            "source": source,
            "target": target,
            "relation": rel_type_value,
            "source_type": source_type,
            "target_type": target_type,
            "attributes": {
                "relationship_type": rel_type_value,
                "relationship_name": rel_type.name,
                "description": TCMRelationshipDefinitions.get_relationship_description(
                    rel_type
                ),
                "confidence": confidence,
                "source_name": source_name,
                "target_name": target_name,
                "source_type": source_type,
                "target_type": target_type,
            },
        }

    def _node_parts(self, node_id: str) -> tuple[str, str]:
        text = str(node_id or "")
        if ":" in text:
            node_type, name = text.split(":", 1)
            return node_type, name
        return "generic", text
