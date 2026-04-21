# src/analysis/semantic_graph.py  (migrated from src/semantic_modeling/semantic_graph_builder.py)
"""
语义图构建模块 - 集成君臣佐使关系识别 + 高级研究方法
支持方剂结构、性味归经、类方比较、现代药理学分析
基于T/C IATCM 098-2023标准
"""
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

nx = import_module("networkx")

from src.core.module_base import BaseModule
from src.extraction.relation_extractor import RelationExtractor
from src.knowledge.embedding_service import EmbeddingService
from src.knowledge.ontology_manager import OntologyManager
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


class SemanticGraphBuilder(BaseModule):
    """
    语义图构建器 - 支持君臣佐使等TCM语义关系
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("semantic_graph_builder", config)
        cfg = config or {}
        self.graph = nx.MultiDiGraph()
        self.entity_types = {}
        self.entity_map = {}  # 实体名称到节点ID的映射，支持关系识别
        self.relationships_used = {}  # 记录已使用的关系类型
        self.relation_extractor = RelationExtractor()
        self.ontology = OntologyManager()
        self._formula_similarity_top_k = int(cfg.get("formula_similarity_top_k", 3) or 3)
        self._formula_similarity_min_score = float(cfg.get("formula_similarity_min_score", 0.35) or 0.35)
        self._embedding_model_name = str(
            cfg.get("embedding_model_name")
            or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        persist_dir = cfg.get("formula_index_persist_directory") or "cache/embedding_indexes"
        self._formula_index_persist_directory = str(Path(persist_dir).resolve())
        self._formula_index_corpus_version = str(cfg.get("formula_index_corpus_version") or "tcm_formula_catalog.v1")
        self._embedding_encoder = cfg.get("embedding_encoder")
        self._neo4j_driver = cfg.get("neo4j_driver")
        self._formula_embedding_service: Optional[EmbeddingService] = None
        self._formula_catalog_by_name: Dict[str, Dict[str, Any]] = {}
        
    def _do_initialize(self) -> bool:
        """初始化语义图构建器"""
        try:
            self.logger.info("语义图构建器初始化完成")
            return True
        except Exception as e:
            self.logger.error("语义图构建器初始化失败: %s", e)
            return False
    
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行语义图构建 - 集成高级研究方法"""
        try:
            entities = self._validate_entities(context)
            
            # 构建语义图
            graph = self._build_semantic_graph(entities)
            
            # 统计关系分布
            relationship_stats = self._calculate_relationship_statistics()
            
            formulas, herbs = self._partition_entities(entities)
            herb_names = self._extract_entity_names(herbs)
            
            # 【新增】生成高级研究视角
            research_perspectives = self._generate_research_perspectives(formulas)
            
            # 【新增】生成药物属性分析
            herb_analysis = self._analyze_herb_properties(herbs)
            
            # 【新增】类方比较分析
            formula_comparison = self._analyze_formula_similarities(formulas)
            
            # 【新增】现代药理学集成
            pharmacology_data = self._collect_pharmacology_data(herbs)

            # 优先复用 integrated 结果，避免首轮重复高级分析
            advanced_analyses = self._collect_advanced_formula_analyses(
                formulas,
                herb_names,
                research_perspectives,
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
                "network_pharmacology_systems_biology": advanced_analyses["network_pharmacology_systems_biology"],
                "supramolecular_physicochemistry": advanced_analyses["supramolecular_physicochemistry"],
                "knowledge_archaeology": advanced_analyses["knowledge_archaeology"],
                "complexity_nonlinear_dynamics": advanced_analyses["complexity_nonlinear_dynamics"],
                "research_scoring_panel": scoring_panel,
                "summary_analysis": summary_analysis,
            }
            
            return output_data
            
        except Exception as e:
            self.logger.error("语义图构建执行失败: %s", e)
            raise

    def _validate_entities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """验证实体输入并统一为列表结构。"""
        entities = context.get("entities", [])
        if entities is None:
            return []
        if not isinstance(entities, list):
            raise ValueError("entities 必须为列表")
        return [item for item in entities if isinstance(item, dict)]

    def _partition_entities(self, entities: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """拆分方剂与药物实体。"""
        formulas = [entity for entity in entities if entity.get("type") == "formula"]
        herbs = [entity for entity in entities if entity.get("type") == "herb"]
        return formulas, herbs

    def _extract_entity_names(self, entities: List[Dict[str, Any]]) -> List[str]:
        """提取实体名称列表（过滤空值）。"""
        return [str(entity.get("name")) for entity in entities if entity.get("name")]

    def _collect_advanced_formula_analyses(
        self,
        formulas: List[Dict[str, Any]],
        herb_names: List[str],
        research_perspectives: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """聚合高级方剂分析结果，优先复用 integrated 输出。"""
        analysis_specs: List[Tuple[str, str, Callable[[List[Dict[str, Any]], List[str]], Dict[str, Any]]]] = [
            ("network_pharmacology_systems_biology", "network_pharmacology", self._analyze_network_systems),
            ("supramolecular_physicochemistry", "supramolecular_physicochemical", self._analyze_supramolecular_physicochemistry),
            ("knowledge_archaeology", "knowledge_archaeology", self._analyze_knowledge_archaeology),
            ("complexity_nonlinear_dynamics", "complexity_dynamics", self._analyze_complexity_dynamics),
        ]

        results: Dict[str, Dict[str, Any]] = {}
        for output_key, integrated_key, fallback in analysis_specs:
            results[output_key] = self._extract_from_integrated(
                formulas,
                research_perspectives,
                integrated_key=integrated_key,
                fallback=lambda items, analyzer=fallback: analyzer(items, herb_names),
            )
        return results
    
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
        entity_type = self.ontology.normalize_node_type(str(entity.get("type") or ""))
        entity_name = str(entity.get("name") or "").strip()
        if not entity_name:
            return
        node_id = self.ontology.make_node_id(entity_type, entity_name)
        
        node_data = {
            "type": entity_type,
            "name": entity_name,
            "confidence": entity.get("confidence", 0.5),
            "position": entity.get("position", 0),
            "length": entity.get("length", len(entity_name))
        }
        
        self.graph.add_node(node_id, **node_data)
        self.entity_types[node_id] = entity_type
        
        # 建立实体名称到节点ID的映射（支持多类型实体同名）
        if entity_name not in self.entity_map:
            self.entity_map[entity_name] = []
        self.entity_map[entity_name].append(node_id)
    
    def _add_relationships(self, entities: List[Dict]):
        """
        添加语义关系边（委托给独立 RelationExtractor）
        """
        extracted_edges = self.relation_extractor.extract(entities)
        for edge in extracted_edges:
            self.graph.add_edge(
                edge["source"],
                edge["target"],
                **edge["attributes"],
            )
        self.relationships_used = dict(self.relation_extractor.relationship_counts)
    
    def _record_relationship(self, rel_type_value: str):
        """记录已使用的关系类型及其计数"""
        if rel_type_value not in self.relationships_used:
            self.relationships_used[rel_type_value] = 0
        self.relationships_used[rel_type_value] += 1
    
    def _calculate_relationship_statistics(self) -> Dict[str, Any]:
        """
        计算关系类型统计信息
        """
        return self.relation_extractor.relationship_statistics()
    
    def _generate_research_perspectives(self, formulas: List[Dict]) -> Dict:
        """生成方剂结构分析 - Formula Structure Analysis"""
        perspectives = {}
        for formula in formulas:
            formula_name = formula.get("name")
            structure = FormulaStructureAnalyzer.analyze_formula_structure(formula_name)
            if structure:
                integrated = IntegratedResearchAnalyzer.generate_research_perspective(formula_name)
                integrated["similar_formula_matches"] = self._build_similar_formula_matches(formula_name, integrated)
                perspectives[formula_name] = {
                    "structure": structure,
                    "integrated": integrated,
                }
        return perspectives

    def _build_similar_formula_matches(self, formula_name: str, integrated: Dict[str, Any]) -> List[Dict[str, Any]]:
        service = self._get_formula_embedding_service()
        results: List[Dict[str, Any]] = []
        seen_names = set()

        if service is not None:
            query_text = self._build_formula_query_text(formula_name)
            try:
                matches = service.search_similar_formulas(
                    query=query_text,
                    top_k=self._formula_similarity_top_k,
                    min_score=self._formula_similarity_min_score,
                    exclude_formula_id=formula_name,
                )
            except Exception as exc:
                self.logger.warning("相似方剂 embedding 检索失败: %s", exc)
                matches = []

            for match in matches:
                match_name = str(match.metadata.get("name") or match.item_id)
                if not match_name or match_name in seen_names:
                    continue
                seen_names.add(match_name)
                results.append(
                    {
                        "formula_id": match.item_id,
                        "formula_name": match_name,
                        "rank": len(results) + 1,
                        "similarity_score": match.score,
                        "retrieval_sources": ["embedding"],
                        "graph_evidence": self._resolve_formula_graph_evidence(formula_name, match_name),
                    }
                )

        for match_name in integrated.get("similar_formulas") or []:
            if not match_name or match_name in seen_names:
                continue
            seen_names.add(match_name)
            results.append(
                {
                    "formula_id": match_name,
                    "formula_name": match_name,
                    "rank": len(results) + 1,
                    "similarity_score": None,
                    "retrieval_sources": ["relationship_reasoning"],
                    "graph_evidence": self._resolve_formula_graph_evidence(formula_name, match_name),
                }
            )

        return results

    def _get_formula_embedding_service(self) -> Optional[EmbeddingService]:
        if self._formula_embedding_service is not None:
            return self._formula_embedding_service

        try:
            service = EmbeddingService(
                model_name=self._embedding_model_name,
                encoder=self._embedding_encoder,
                use_faiss=False,
                persist_directory=self._formula_index_persist_directory,
                index_name="formula_similarity_index",
                corpus_version=self._formula_index_corpus_version,
            )
            catalog = self._build_formula_embedding_catalog()
            if not catalog:
                return None
            self._formula_catalog_by_name = {str(item["name"]): item for item in catalog if item.get("name")}
            service.build_formula_index(catalog)
            self._formula_embedding_service = service
            return service
        except Exception as exc:
            self.logger.warning("构建方剂 embedding 索引失败，回退关系证据: %s", exc)
            return None

    def _build_formula_embedding_catalog(self) -> List[Dict[str, Any]]:
        catalog_names = set(FormulaStructureAnalyzer.FORMULA_STRUCTURES.keys())
        for family_formulas in FormulaComparator.FORMULA_FAMILIES.values():
            catalog_names.update(name for name in family_formulas if name)
        for formula_left, formula_right in FormulaComparator.FORMULA_RELATIONSHIPS.keys():
            catalog_names.add(formula_left)
            catalog_names.add(formula_right)

        catalog: List[Dict[str, Any]] = []
        for formula_name in sorted(catalog_names):
            composition = FormulaStructureAnalyzer.get_formula_composition(formula_name)
            structure = FormulaStructureAnalyzer.analyze_formula_structure(formula_name)
            herbs: List[str] = []
            for herb_names in composition.values():
                herbs.extend(str(herb) for herb in herb_names if herb)

            descriptions = [str(structure.get("characteristics") or "").strip()]
            for _, relation_data in FormulaComparator.find_similar_formulas(formula_name):
                difference = str(relation_data.get("difference") or "").strip()
                if difference:
                    descriptions.append(difference)

            catalog.append(
                {
                    "formula_id": formula_name,
                    "name": formula_name,
                    "herbs": herbs,
                    "indications": [],
                    "description": "；".join(part for part in descriptions if part),
                }
            )
        return catalog

    def _build_formula_query_text(self, formula_name: str) -> str:
        catalog_item = self._formula_catalog_by_name.get(formula_name) or {
            "name": formula_name,
            "herbs": [],
            "indications": [],
            "description": "",
        }
        return "；".join(
            part
            for part in [
                str(catalog_item.get("name") or formula_name),
                self._format_formula_field("药物:", catalog_item.get("herbs") or []),
                self._format_formula_field("证候:", catalog_item.get("indications") or []),
                str(catalog_item.get("description") or "").strip(),
            ]
            if part
        )

    def _format_formula_field(self, prefix: str, values: List[str]) -> str:
        if not values:
            return ""
        return prefix + " ".join(str(value) for value in values if value)

    def _resolve_formula_graph_evidence(self, formula_name: str, similar_formula_name: str) -> Dict[str, Any]:
        local_evidence = self._build_local_formula_graph_evidence(formula_name, similar_formula_name)
        neo4j_evidence = self._collect_neo4j_formula_graph_evidence(formula_name, similar_formula_name)
        if not neo4j_evidence:
            return local_evidence

        local_shared = {item.get("herb") for item in local_evidence.get("shared_herbs", []) if item.get("herb")}
        merged_shared = list(neo4j_evidence.get("shared_herbs", []))
        for item in local_evidence.get("shared_herbs", []):
            herb_name = item.get("herb")
            if herb_name and herb_name not in {entry.get("herb") for entry in merged_shared}:
                merged_shared.append(item)

        return {
            "source": "neo4j+relationship_reasoning",
            "shared_herbs": merged_shared,
            "shared_syndromes": neo4j_evidence.get("shared_syndromes", []),
            "direct_relationships": neo4j_evidence.get("direct_relationships", []),
            "role_overlaps": local_evidence.get("role_overlaps", []),
            "comparison_summary": local_evidence.get("comparison_summary", {}),
            "evidence_score": round(
                max(float(neo4j_evidence.get("evidence_score", 0.0) or 0.0), float(local_evidence.get("evidence_score", 0.0) or 0.0)),
                3,
            ),
            "shared_herb_count": len({item.get("herb") for item in merged_shared if item.get("herb")}),
            "local_shared_herb_count": len(local_shared),
        }

    def _collect_neo4j_formula_graph_evidence(self, formula_name: str, similar_formula_name: str) -> Dict[str, Any]:
        if self._neo4j_driver is None or not hasattr(self._neo4j_driver, "collect_formula_similarity_evidence"):
            return {}
        try:
            payload = self._neo4j_driver.collect_formula_similarity_evidence(formula_name, similar_formula_name)
        except Exception as exc:
            self.logger.warning("Neo4j 图谱证据查询失败: %s", exc)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _build_local_formula_graph_evidence(self, formula_name: str, similar_formula_name: str) -> Dict[str, Any]:
        composition_a = FormulaStructureAnalyzer.get_formula_composition(formula_name)
        composition_b = FormulaStructureAnalyzer.get_formula_composition(similar_formula_name)
        shared_herbs: List[Dict[str, str]] = []
        role_overlaps: List[Dict[str, Any]] = []

        for role_a, herbs_a in composition_a.items():
            herbs_a_set = {str(item) for item in herbs_a if item}
            if not herbs_a_set:
                continue
            for role_b, herbs_b in composition_b.items():
                common = sorted(herbs_a_set & {str(item) for item in herbs_b if item})
                if not common:
                    continue
                role_overlaps.append(
                    {
                        "formula_role": role_a,
                        "similar_formula_role": role_b,
                        "herbs": common,
                    }
                )
                shared_herbs.extend(
                    {
                        "herb": herb_name,
                        "formula_role": role_a,
                        "similar_formula_role": role_b,
                    }
                    for herb_name in common
                )

        comparison_summary = FormulaComparator.compare_formulas(formula_name, similar_formula_name)
        comparison_herbs = [str(item) for item in comparison_summary.get("common_herbs", []) if item]
        existing_shared = {item.get("herb") for item in shared_herbs if item.get("herb")}
        for herb_name in comparison_herbs:
            if herb_name not in existing_shared:
                shared_herbs.append(
                    {
                        "herb": herb_name,
                        "formula_role": "unknown",
                        "similar_formula_role": "unknown",
                    }
                )

        evidence_score = min(
            1.0,
            round(len(shared_herbs) * 0.14 + len(role_overlaps) * 0.08 + (0.2 if comparison_summary else 0.0), 3),
        )
        return {
            "source": "relationship_reasoning",
            "shared_herbs": shared_herbs,
            "shared_syndromes": [],
            "direct_relationships": [],
            "role_overlaps": role_overlaps,
            "comparison_summary": comparison_summary,
            "evidence_score": evidence_score,
            "shared_herb_count": len({item.get("herb") for item in shared_herbs if item.get("herb")}),
        }
    
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
        return self._analyze_formulas_with(
            formulas,
            herb_names,
            NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network,
        )

    def _analyze_supramolecular_physicochemistry(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """超分子化学和物理化学分析"""
        return self._analyze_formulas_with(
            formulas,
            herb_names,
            SupramolecularPhysicochemicalAnalyzer.analyze_formula_physicochemical,
        )

    def _analyze_knowledge_archaeology(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """古典文献数字化与知识考古分析"""
        return self._analyze_formulas_with(
            formulas,
            herb_names,
            ClassicalLiteratureArchaeologyAnalyzer.analyze_formula_knowledge_archaeology,
        )

    def _analyze_complexity_dynamics(self, formulas: List[Dict], herb_names: List[str]) -> Dict:
        """复杂性科学与非线性动力学分析"""
        return self._analyze_formulas_with(
            formulas,
            herb_names,
            ComplexityNonlinearDynamicsAnalyzer.analyze_formula_complexity_dynamics,
        )

    def _analyze_formulas_with(
        self,
        formulas: List[Dict],
        herb_names: List[str],
        analyzer: Callable[[str, List[str]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """用统一模式执行方剂级分析器。"""
        output: Dict[str, Any] = {}
        for formula in formulas:
            formula_name = formula.get("name")
            if formula_name:
                output[formula_name] = analyzer(formula_name, herb_names)
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
            self._formula_embedding_service = None
            self._formula_catalog_by_name.clear()
            self.logger.info("语义图构建器资源清理完成")
            return True
        except Exception as e:
            self.logger.error("语义图构建器资源清理失败: %s", e)
            return False
