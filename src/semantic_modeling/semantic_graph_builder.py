# src/semantic_modeling/semantic_graph_builder.py
"""
语义图构建模块 - 集成君臣佐使关系识别 + 高级研究方法
支持方剂结构、性味归经、类方比较、现代药理学分析
基于T/C IATCM 098-2023标准
"""
import json
from typing import Any, Dict, List, Optional

import networkx as nx

from src.core.module_base import BaseModule
from src.semantic_modeling.research_methods import (
    ClassicalLiteratureArchaeologyAnalyzer,
    ComplexityNonlinearDynamicsAnalyzer,
    FormulaComparator,
    FormulaStructureAnalyzer,
    HerbPropertyDatabase,
    IntegratedResearchAnalyzer,
    ModernPharmacologyDatabase,
    NetworkPharmacologySystemBiologyAnalyzer,
    ResearchScoringPanel,
    SummaryAnalysisEngine,
    SupramolecularPhysicochemicalAnalyzer,
)
from src.semantic_modeling.tcm_relationships import (
    RelationshipType,
    TCMRelationshipDefinitions,
)


class SemanticGraphBuilder(BaseModule):
    """
    语义图构建器 - 支持君臣佐使等TCM语义关系
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("semantic_graph_builder", config)
        self.graph = nx.MultiDiGraph()
        self.entity_types = {}
        self.entity_map = {}  # 实体名称到节点ID的映射，支持关系识别
        self.relationships_used = {}  # 记录已使用的关系类型
        
    def _do_initialize(self) -> bool:
        """初始化语义图构建器"""
        try:
            self.logger.info("语义图构建器初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"语义图构建器初始化失败: {e}")
            return False
    
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行语义图构建 - 集成高级研究方法"""
        try:
            # 获取实体数据
            entities = context.get("entities", [])
            
            # 构建语义图
            graph = self._build_semantic_graph(entities)
            
            # 统计关系分布
            relationship_stats = self._calculate_relationship_statistics()
            
            # 【新增】提取关键方剂和药物
            formulas = [e for e in entities if e.get("type") == "formula"]
            herbs = [e for e in entities if e.get("type") == "herb"]
            herb_names = [h.get("name") for h in herbs if h.get("name")]
            
            # 【新增】生成高级研究视角
            research_perspectives = self._generate_research_perspectives(formulas)
            
            # 【新增】生成药物属性分析
            herb_analysis = self._analyze_herb_properties(herbs)
            
            # 【新增】类方比较分析
            formula_comparison = self._analyze_formula_similarities(formulas)
            
            # 【新增】现代药理学集成
            pharmacology_data = self._collect_pharmacology_data(herbs)

            # 优先复用 integrated 结果，避免首轮重复高级分析
            network_systems = self._extract_from_integrated(
                formulas,
                research_perspectives,
                integrated_key="network_pharmacology",
                fallback=lambda items: self._analyze_network_systems(items, herb_names),
            )
            supramolecular_physicochemistry = self._extract_from_integrated(
                formulas,
                research_perspectives,
                integrated_key="supramolecular_physicochemical",
                fallback=lambda items: self._analyze_supramolecular_physicochemistry(items, herb_names),
            )
            knowledge_archaeology = self._extract_from_integrated(
                formulas,
                research_perspectives,
                integrated_key="knowledge_archaeology",
                fallback=lambda items: self._analyze_knowledge_archaeology(items, herb_names),
            )
            complexity_dynamics = self._extract_from_integrated(
                formulas,
                research_perspectives,
                integrated_key="complexity_dynamics",
                fallback=lambda items: self._analyze_complexity_dynamics(items, herb_names),
            )

            # 【新增】统一评分面板（8维 0-1 标准化 + 总分 + 95%CI）
            scoring_panel = self._build_research_scoring_panel(research_perspectives, formula_comparison)

            # 【新增】总结分析（统计/挖掘/建模）
            summary_analysis = SummaryAnalysisEngine.analyze(context)
            
            # 构造输出
            output_data = {
                "semantic_graph": {
                    "nodes": [
                        {
                            "id": node,
                            "data": data
                        } for node, data in graph.nodes(data=True)
                    ],
                    "edges": [
                        {
                            "source": edge[0],
                            "target": edge[1],
                            "attributes": edge[2]
                        } for edge in graph.edges(data=True)
                    ]
                },
                "graph_statistics": {
                    "nodes_count": graph.number_of_nodes(),
                    "edges_count": graph.number_of_edges(),
                    "density": nx.density(graph) if graph.number_of_nodes() > 0 else 0,
                    "connected_components": nx.number_connected_components(graph.to_undirected()) if graph.number_of_nodes() > 0 else 0,
                    "relationships_by_type": relationship_stats,
                },
                "research_perspectives": research_perspectives,
                "herb_properties": herb_analysis,
                "formula_comparisons": formula_comparison,
                "pharmacology_integration": pharmacology_data,
                "network_pharmacology_systems_biology": network_systems,
                "supramolecular_physicochemistry": supramolecular_physicochemistry,
                "knowledge_archaeology": knowledge_archaeology,
                "complexity_nonlinear_dynamics": complexity_dynamics,
                "research_scoring_panel": scoring_panel,
                "summary_analysis": summary_analysis,
            }
            
            return output_data
            
        except Exception as e:
            self.logger.error(f"语义图构建执行失败: {e}")
            raise
    
    def _build_semantic_graph(self, entities: List[Dict]) -> nx.MultiDiGraph:
        """
        构建语义图 - 支持君臣佐使等TCM关系
        """
        # 清理图和映射
        self.graph.clear()
        self.entity_map.clear()
        self.relationships_used.clear()
        
        # 添加节点
        for entity in entities:
            self._add_node(entity)
        
        # 添加边（关系）
        self._add_relationships(entities)
        
        return self.graph
    
    def _add_node(self, entity: Dict):
        """
        添加节点到图中
        """
        # 使用实体名称作为节点ID（更易读）
        node_id = f"{entity['type']}:{entity['name']}"
        
        node_data = {
            "type": entity["type"],
            "name": entity["name"],
            "confidence": entity.get("confidence", 0.5),
            "position": entity.get("position", 0),
            "length": entity.get("length", len(entity['name']))
        }
        
        self.graph.add_node(node_id, **node_data)
        self.entity_types[node_id] = entity["type"]
        
        # 建立实体名称到节点ID的映射（支持多类型实体同名）
        if entity['name'] not in self.entity_map:
            self.entity_map[entity['name']] = []
        self.entity_map[entity['name']].append(node_id)
    
    def _add_relationships(self, entities: List[Dict]):
        """
        添加语义关系边（核心逻辑）
        """
        # 提取方剂实体，用于君臣佐使推断
        formulas = [e for e in entities if e.get("type") == "formula"]
        herbs = [e for e in entities if e.get("type") == "herb"]
        herb_name_to_node = {
            h["name"]: f"herb:{h['name']}"
            for h in herbs
            if h.get("name")
        }
        
        # 【策略1】方剂 → 药物 的君臣佐使关系
        for formula in formulas:
            formula_name = formula['name']
            formula_node = f"formula:{formula_name}"
            
            composition = TCMRelationshipDefinitions.get_formula_composition(formula_name)
            if composition:
                role_groups = {
                    RelationshipType.SOVEREIGN: composition.get("sovereign", []),
                    RelationshipType.MINISTER: composition.get("minister", []),
                    RelationshipType.ASSISTANT: composition.get("assistant", []),
                    RelationshipType.ENVOY: composition.get("envoy", []),
                }

                for role, herb_names in role_groups.items():
                    for herb_name in herb_names:
                        herb_node = herb_name_to_node.get(herb_name)
                        if not herb_node:
                            continue
                        self.graph.add_edge(
                            formula_node, herb_node,
                            relationship_type=role.value,
                            relationship_name=role.name,
                            description=TCMRelationshipDefinitions.get_relationship_description(role),
                            confidence=0.95
                        )
                        self._record_relationship(role.value)
        
        # 【策略2】药物 → 功效 的关系
        for herb in herbs:
            herb_name = herb['name']
            herb_node = f"herb:{herb_name}"
            
            efficacies = TCMRelationshipDefinitions.get_herb_efficacy(herb_name)
            for efficacy in efficacies:
                efficacy_node = f"efficacy:{efficacy}"
                
                self.graph.add_edge(
                    herb_node, efficacy_node,
                    relationship_type=RelationshipType.EFFICACY.value,
                    relationship_name=RelationshipType.EFFICACY.name,
                    description=TCMRelationshipDefinitions.get_relationship_description(
                        RelationshipType.EFFICACY
                    ),
                    confidence=0.90
                )
                self._record_relationship(RelationshipType.EFFICACY.value)
        
        # 【策略3】药物/方剂 → 证候 的治疗关系
        syndromes = [e for e in entities if e.get("type") == "syndrome"]
        for syndrome in syndromes:
            syndrome_node = f"syndrome:{syndrome['name']}"
            
            # 方剂治疗证候
            for formula in formulas:
                formula_node = f"formula:{formula['name']}"
                self.graph.add_edge(
                    formula_node, syndrome_node,
                    relationship_type=RelationshipType.TREATS.value,
                    relationship_name=RelationshipType.TREATS.name,
                    description=TCMRelationshipDefinitions.get_relationship_description(
                        RelationshipType.TREATS
                    ),
                    confidence=0.75
                )
                self._record_relationship(RelationshipType.TREATS.value)
            
            # 部分药物治疗证候
            for herb in herbs:
                herb_node = f"herb:{herb['name']}"
                self.graph.add_edge(
                    herb_node, syndrome_node,
                    relationship_type=RelationshipType.TREATS.value,
                    relationship_name=RelationshipType.TREATS.name,
                    description=TCMRelationshipDefinitions.get_relationship_description(
                        RelationshipType.TREATS
                    ),
                    confidence=0.60
                )
                self._record_relationship(RelationshipType.TREATS.value)
    
    def _record_relationship(self, rel_type_value: str):
        """记录已使用的关系类型及其计数"""
        if rel_type_value not in self.relationships_used:
            self.relationships_used[rel_type_value] = 0
        self.relationships_used[rel_type_value] += 1
    
    def _calculate_relationship_statistics(self) -> Dict[str, Any]:
        """
        计算关系类型统计信息
        """
        stats = {}
        for rel_type, count in self.relationships_used.items():
            stats[rel_type] = {
                "count": count,
                "description": TCMRelationshipDefinitions.get_relationship_description(
                    RelationshipType[rel_type.upper()] if rel_type.upper() in [r.name for r in RelationshipType]
                    else RelationshipType.COMBINES_WITH
                )
            }
        return stats
    
    def _generate_research_perspectives(self, formulas: List[Dict]) -> Dict:
        """生成方剂结构分析 - Formula Structure Analysis"""
        perspectives = {}
        for formula in formulas:
            formula_name = formula.get("name")
            structure = FormulaStructureAnalyzer.analyze_formula_structure(formula_name)
            if structure:
                perspectives[formula_name] = {
                    "structure": structure,
                    "integrated": IntegratedResearchAnalyzer.generate_research_perspective(formula_name)
                }
        return perspectives
    
    def _analyze_herb_properties(self, herbs: List[Dict]) -> Dict:
        """分析药物性味与归经 - Herb Properties & Meridian Entry"""
        properties = {}
        for herb in herbs:
            herb_name = herb.get("name")
            prop = HerbPropertyDatabase.get_herb_property(herb_name)
            if prop:
                properties[herb_name] = prop
        return properties
    
    def _analyze_formula_similarities(self, formulas: List[Dict]) -> List[Dict]:
        """类方比较分析 - Similar Formula Comparison"""
        comparisons = []
        formula_names = [f.get("name") for f in formulas if f.get("name")]
        
        # 对比所有方剂对
        for i, f1 in enumerate(formula_names):
            for f2 in formula_names[i+1:]:
                comparison = FormulaComparator.compare_formulas(f1, f2)
                if comparison:
                    comparisons.append(comparison)
        
        return comparisons
    
    def _collect_pharmacology_data(self, herbs: List[Dict]) -> Dict:
        """现代药理学与临床研究数据 - Modern Pharmacology & Clinical Research"""
        pharmacology = {}
        for herb in herbs:
            herb_name = herb.get("name")
            pharm_data = ModernPharmacologyDatabase.get_pharmacological_data(herb_name)
            if pharm_data:
                pharmacology[herb_name] = {
                    "components": pharm_data.get("active_components", {}),
                    "actions": pharm_data.get("pharmacological_actions", []),
                    "clinical": pharm_data.get("clinical_research", {}),
                    "safety": ModernPharmacologyDatabase.get_safety_info(herb_name)
                }
        return pharmacology

    def _extract_from_integrated(
        self,
        formulas: List[Dict],
        research_perspectives: Dict[str, Dict[str, Any]],
        integrated_key: str,
        fallback,
    ) -> Dict[str, Any]:
        """从 integrated 结果提取目标分析，缺失时回退到独立分析器。"""
        output: Dict[str, Any] = {}
        missing_formulas: List[Dict[str, Any]] = []

        for formula in formulas:
            formula_name = formula.get("name")
            if not formula_name:
                continue
            integrated = (research_perspectives.get(formula_name) or {}).get("integrated", {})
            value = integrated.get(integrated_key)
            if value:
                output[formula_name] = value
            else:
                missing_formulas.append(formula)

        if missing_formulas:
            output.update(fallback(missing_formulas))

        return output

    def _analyze_network_systems(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """网络药理学与系统性生物学分析"""
        output: Dict[str, Any] = {}
        for formula in formulas:
            formula_name = formula.get("name")
            if formula_name:
                output[formula_name] = NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network(
                    formula_name,
                    herb_names,
                )
        return output

    def _analyze_supramolecular_physicochemistry(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """超分子化学和物理化学分析"""
        output: Dict[str, Any] = {}
        for formula in formulas:
            formula_name = formula.get("name")
            if formula_name:
                output[formula_name] = SupramolecularPhysicochemicalAnalyzer.analyze_formula_physicochemical(
                    formula_name,
                    herb_names,
                )
        return output

    def _analyze_knowledge_archaeology(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """古典文献数字化与知识考古分析"""
        output: Dict[str, Any] = {}
        for formula in formulas:
            formula_name = formula.get("name")
            if formula_name:
                output[formula_name] = ClassicalLiteratureArchaeologyAnalyzer.analyze_formula_knowledge_archaeology(
                    formula_name,
                    herb_names,
                )
        return output

    def _analyze_complexity_dynamics(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """复杂性科学与非线性动力学分析"""
        output: Dict[str, Any] = {}
        for formula in formulas:
            formula_name = formula.get("name")
            if formula_name:
                output[formula_name] = ComplexityNonlinearDynamicsAnalyzer.analyze_formula_complexity_dynamics(
                    formula_name,
                    herb_names,
                )
        return output

    def _build_research_scoring_panel(
        self,
        research_perspectives: Dict[str, Dict[str, Any]],
        formula_comparisons: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """构建统一评分面板"""
        result: Dict[str, Any] = {}
        for formula_name, perspective_data in research_perspectives.items():
            integrated = perspective_data.get("integrated", {})
            if not integrated:
                continue
            result[formula_name] = ResearchScoringPanel.score_research_perspective(
                integrated,
                formula_comparisons,
            )
        return result
    
    def _do_cleanup(self) -> bool:
        """清理资源"""
        try:
            self.graph.clear()
            self.entity_types.clear()
            self.entity_map.clear()
            self.relationships_used.clear()
            self.logger.info("语义图构建器资源清理完成")
            return True
        except Exception as e:
            self.logger.error(f"语义图构建器资源清理失败: {e}")
            return False
