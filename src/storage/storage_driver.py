"""
统一存储驱动 - PostgreSQL + Neo4j 集成
中医古籍全自动研究系统
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from src.storage.db_models import (
    DatabaseManager,
    Document,
    Entity,
    EntityRelationship,
    EntityTypeEnum,
    LogStatusEnum,
    ProcessingLog,
    ProcessingStatistics,
    ProcessStatusEnum,
    QualityMetrics,
    RelationshipType,
    ResearchAnalysis,
)
from src.storage.neo4j_driver import (
    Neo4jDriver,
    Neo4jEdge,
    entity_to_neo4j_node,
)

logger = logging.getLogger(__name__)


def _chunk_list(items: List[Dict[str, Any]], chunk_size: int) -> List[List[Dict[str, Any]]]:
    """将列表按固定大小分块。"""
    if chunk_size <= 0:
        chunk_size = 300
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


class UnifiedStorageDriver:
    """
    统一存储驱动 - 同时管理PostgreSQL和Neo4j
    
    职责：
    1. 实体存储和查询
    2. 关系存储和查询
    3. 统计信息存储
    4. 分析结果存储
    5. 日志记录
    """
    
    def __init__(self, pg_connection_string: str, neo4j_uri: str, 
                 neo4j_auth: Tuple[str, str]):
        """
        初始化存储驱动
        
        Args:
            pg_connection_string: PostgreSQL连接字符串
            neo4j_uri: Neo4j连接URI
            neo4j_auth: Neo4j认证(用户名, 密码)
        """
        self.pg_manager = DatabaseManager(pg_connection_string)
        self.neo4j = Neo4jDriver(neo4j_uri, neo4j_auth)
        self.session = None
    
    def initialize(self):
        """初始化存储系统"""
        try:
            # 初始化PostgreSQL
            logger.info("初始化PostgreSQL...")
            self.pg_manager.init_db()
            self.session = self.pg_manager.get_session()
            
            # 创建默认关系类型
            DatabaseManager.create_default_relationships(self.session)
            self.session.commit()
            logger.info("PostgreSQL 初始化完成")
            
            # 初始化Neo4j
            logger.info("初始化Neo4j...")
            self.neo4j.connect()
            logger.info("Neo4j 初始化完成")
            
            logger.info("统一存储驱动初始化成功")
        except Exception as e:
            logger.error("存储驱动初始化失败: %s", e)
            raise
    
    def close(self):
        """关闭所有数据库连接"""
        try:
            if self.session:
                self.session.close()
            self.pg_manager.close()
            self.neo4j.close()
            logger.info("所有数据库连接已关闭")
        except Exception as e:
            logger.error("关闭连接失败: %s", e)
    
    # ==================== 文档管理 ====================
    
    def save_document(self, source_file: str, objective: str = None, 
                     raw_text_size: int = 0) -> Optional[UUID]:
        """
        保存文档元信息
        
        Args:
            source_file: 源文件路径
            objective: 处理目标
            raw_text_size: 原始文本大小
        
        Returns:
            文档ID
        """
        try:
            doc = Document(
                source_file=source_file,
                objective=objective or "automatic_analysis",
                raw_text_size=raw_text_size,
                process_status=ProcessStatusEnum.PENDING
            )
            self.session.add(doc)
            self.session.commit()
            
            logger.info(f"文档已保存: {source_file} (ID: {doc.id})")
            return doc.id
        except Exception as e:
            self.session.rollback()
            logger.error("保存文档失败: %s", e)
            return None
    
    def update_document_status(self, document_id: UUID, status: str):
        """更新文档处理状态"""
        try:
            doc = self.session.query(Document).filter_by(id=document_id).first()
            if doc:
                doc.process_status = ProcessStatusEnum(status)
                self.session.commit()
                logger.info("文档状态已更新: %s -> %s", document_id, status)
        except Exception as e:
            self.session.rollback()
            logger.error("更新文档状态失败: %s", e)
    
    # ==================== 实体管理 ====================
    
    def save_entities(self, document_id: UUID, entities: List[Dict[str, Any]]) -> List[UUID]:
        """
        保存实体到PostgreSQL和Neo4j
        
        Args:
            document_id: 文档ID
            entities: 实体列表，每个实体包含 name, type, confidence, position, length 等
        
        Returns:
            实体ID列表
        """
        entity_ids = []
        neo4j_nodes = []
        
        try:
            for entity_data in entities:
                # 保存到PostgreSQL
                entity = Entity(
                    document_id=document_id,
                    name=entity_data.get('name', ''),
                    type=EntityTypeEnum[entity_data.get('type', 'OTHER').upper()],
                    confidence=entity_data.get('confidence', 0.5),
                    position=entity_data.get('position', 0),
                    length=entity_data.get('length', 0),
                    alternative_names=entity_data.get('alternative_names', []),
                    description=entity_data.get('description', ''),
                    entity_metadata=entity_data.get('metadata', {})
                )
                self.session.add(entity)
                self.session.flush()  # 获取ID
                
                entity_ids.append(entity.id)
                
                # 准备Neo4j节点
                neo4j_nodes.append(entity_to_neo4j_node(entity))
            
            # 提交PostgreSQL事务
            self.session.commit()
            logger.info("已保存 %s 个实体到PostgreSQL", len(entity_ids))
            
            # 批量创建Neo4j节点
            if neo4j_nodes:
                self.neo4j.batch_create_nodes(neo4j_nodes)
                logger.info("已保存 %s 个节点到Neo4j", len(neo4j_nodes))
            
            return entity_ids
        
        except Exception as e:
            self.session.rollback()
            logger.error("保存实体失败: %s", e)
            return []
    
    def get_entities(self, document_id: UUID) -> List[Dict[str, Any]]:
        """获取文档的所有实体"""
        try:
            entities = self.session.query(Entity).filter_by(document_id=document_id).all()
            return [entity.to_dict() for entity in entities]
        except Exception as e:
            logger.error("获取实体失败: %s", e)
            return []
    
    # ==================== 关系管理 ====================
    
    def save_relationships(self, document_id: UUID, 
                          relationships: List[Dict[str, Any]]) -> List[UUID]:
        """
        保存实体关系到PostgreSQL和Neo4j
        
        Args:
            document_id: 文档ID
            relationships: 关系列表，包含 source_entity_id, target_entity_id, 
                          relationship_type, confidence 等
        
        Returns:
            关系ID列表
        """
        rel_ids = []
        batch_size = 500
        
        try:
            if not relationships:
                return rel_ids

            # 获取所有关系类型的映射
            rel_types = self.session.query(RelationshipType).all()
            rel_type_map = {rt.relationship_type: rt.id for rt in rel_types}
            
            # 获取所有实体类型映射
            entities = self.session.query(Entity).filter_by(document_id=document_id).all()
            entity_type_map = {str(e.id): (e.name, EntityTypeEnum(e.type.value).name.lower()) for e in entities}

            for rel_batch in _chunk_list(relationships, batch_size):
                neo4j_edges = []

                for rel_data in rel_batch:
                    source_id = rel_data.get('source_entity_id')
                    target_id = rel_data.get('target_entity_id')
                    rel_type = rel_data.get('relationship_type')

                    rel_type_id = rel_type_map.get(rel_type)
                    if not rel_type_id:
                        logger.warning("未找到关系类型: %s", rel_type)
                        continue

                    relationship = EntityRelationship(
                        source_entity_id=source_id,
                        target_entity_id=target_id,
                        relationship_type_id=rel_type_id,
                        confidence=rel_data.get('confidence', 0.5),
                        created_by_module=rel_data.get('created_by_module', 'semantic_graph_builder'),
                        evidence=rel_data.get('evidence', ''),
                        relationship_metadata=rel_data.get('metadata', {})
                    )
                    self.session.add(relationship)
                    self.session.flush()
                    rel_ids.append(relationship.id)

                    if str(source_id) in entity_type_map and str(target_id) in entity_type_map:
                        source_label = entity_type_map[str(source_id)][1].capitalize()
                        target_label = entity_type_map[str(target_id)][1].capitalize()

                        neo4j_edges.append((
                            Neo4jEdge(
                                source_id=str(source_id),
                                target_id=str(target_id),
                                relationship_type=rel_type,
                                properties={
                                    'confidence': rel_data.get('confidence', 0.5),
                                    'created_by_module': rel_data.get('created_by_module', ''),
                                    'evidence': rel_data.get('evidence', ''),
                                }
                            ),
                            source_label,
                            target_label
                        ))

                self.session.commit()

                if neo4j_edges:
                    self.neo4j.batch_create_relationships(neo4j_edges)

            logger.info("已保存 %s 个关系到PostgreSQL", len(rel_ids))
            logger.info("已保存 %s 个关系到Neo4j", len(rel_ids))
            
            return rel_ids
        
        except Exception as e:
            self.session.rollback()
            logger.error("保存关系失败: %s", e)
            return []
    
    def get_relationships(self, document_id: UUID) -> List[Dict[str, Any]]:
        """获取文档的所有关系"""
        try:
            relationships = (
                self.session.query(EntityRelationship)
                .join(Entity, Entity.id == EntityRelationship.source_entity_id)
                .filter(Entity.document_id == document_id)
                .all()
            )
            return [rel.to_dict() for rel in relationships]
        except Exception as e:
            logger.error("获取关系失败: %s", e)
            return []
    
    # ==================== 统计管理 ====================
    
    def save_statistics(self, document_id: UUID, 
                       stats_data: Dict[str, Any]) -> bool:
        """
        保存处理统计信息
        
        Args:
            document_id: 文档ID
            stats_data: 统计数据
        
        Returns:
            是否成功
        """
        try:
            stats = ProcessingStatistics(
                document_id=document_id,
                formulas_count=stats_data.get('formulas_count', 0),
                herbs_count=stats_data.get('herbs_count', 0),
                syndromes_count=stats_data.get('syndromes_count', 0),
                efficacies_count=stats_data.get('efficacies_count', 0),
                relationships_count=stats_data.get('relationships_count', 0),
                graph_nodes_count=stats_data.get('graph_nodes_count', 0),
                graph_edges_count=stats_data.get('graph_edges_count', 0),
                graph_density=stats_data.get('graph_density', 0.0),
                connected_components=stats_data.get('connected_components', 0),
                source_modules=stats_data.get('source_modules', []),
                processing_time_ms=stats_data.get('processing_time_ms', 0)
            )
            self.session.add(stats)
            self.session.commit()
            logger.info("统计信息已保存: %s", document_id)
            return True
        except Exception as e:
            self.session.rollback()
            logger.error("保存统计信息失败: %s", e)
            return False
    
    # ==================== 质量指标管理 ====================
    
    def save_quality_metrics(self, document_id: UUID, 
                            metrics_data: Dict[str, Any]) -> bool:
        """保存质量指标"""
        try:
            metrics = QualityMetrics(
                document_id=document_id,
                confidence_score=metrics_data.get('confidence_score', 0.0),
                completeness=metrics_data.get('completeness', 0.0),
                entity_precision=metrics_data.get('entity_precision', 0.0),
                relationship_precision=metrics_data.get('relationship_precision', 0.0),
                graph_quality_score=metrics_data.get('graph_quality_score', 0.0),
                evaluator=metrics_data.get('evaluator', 'system'),
                assessment_notes=metrics_data.get('assessment_notes', '')
            )
            self.session.add(metrics)
            self.session.commit()
            logger.info("质量指标已保存: %s", document_id)
            return True
        except Exception as e:
            self.session.rollback()
            logger.error("保存质量指标失败: %s", e)
            return False
    
    # ==================== 研究分析管理 ====================
    
    def save_research_analysis(self, document_id: UUID, 
                              analysis_data: Dict[str, Any]) -> bool:
        """保存研究分析结果"""
        try:
            analysis = ResearchAnalysis(
                document_id=document_id,
                research_perspectives=analysis_data.get('research_perspectives', {}),
                formula_comparisons=analysis_data.get('formula_comparisons', {}),
                herb_properties_analysis=analysis_data.get('herb_properties_analysis', {}),
                pharmacology_integration=analysis_data.get('pharmacology_integration', {}),
                network_pharmacology=analysis_data.get('network_pharmacology', {}),
                supramolecular_physicochemistry=analysis_data.get('supramolecular_physicochemistry', {}),
                knowledge_archaeology=analysis_data.get('knowledge_archaeology', {}),
                complexity_dynamics=analysis_data.get('complexity_dynamics', {}),
                research_scoring_panel=analysis_data.get('research_scoring_panel', {}),
                summary_analysis=analysis_data.get('summary_analysis', {})
            )
            self.session.add(analysis)
            self.session.commit()
            logger.info("研究分析已保存: %s", document_id)
            return True
        except Exception as e:
            self.session.rollback()
            logger.error("保存研究分析失败: %s", e)
            return False
    
    # ==================== 日志管理 ====================
    
    def log_module_execution(self, document_id: UUID, module_name: str,
                            status: str, message: str = None,
                            error_details: str = None,
                            execution_time_ms: int = 0) -> bool:
        """
        记录模块执行日志
        
        Args:
            document_id: 文档ID
            module_name: 模块名称
            status: 执行状态 (start|success|failure|warning)
            message: 执行消息
            error_details: 错误详情
            execution_time_ms: 执行时间（毫秒）
        
        Returns:
            是否成功
        """
        try:
            log = ProcessingLog(
                document_id=document_id,
                module_name=module_name,
                status=LogStatusEnum(status),
                message=message,
                error_details=error_details,
                execution_time_ms=execution_time_ms
            )
            self.session.add(log)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            logger.error("记录日志失败: %s", e)
            return False
    
    # ==================== 查询服务 ====================
    
    def query_formula_composition(self, formula_name: str) -> Dict[str, List[str]]:
        """
        查询方剂组成（从Neo4j）
        
        Args:
            formula_name: 方剂名称
        
        Returns:
            {sovereign: [...], minister: [...], ...}
        """
        return self.neo4j.find_formula_composition(formula_name)
    
    def query_treating_formulas(self, syndrome_name: str) -> List[Dict]:
        """
        查询治疗某症候的方剂（从Neo4j）
        
        Args:
            syndrome_name: 症候名称
        
        Returns:
            方剂列表
        """
        return self.neo4j.find_formulas_treating_syndrome(syndrome_name)
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """获取存储系统统计信息"""
        try:
            # PostgreSQL统计
            doc_count = self.session.query(Document).count()
            entity_count = self.session.query(Entity).count()
            rel_count = self.session.query(EntityRelationship).count()
            
            # Neo4j统计
            neo4j_stats = self.neo4j.get_graph_statistics()
            
            return {
                'postgresql': {
                    'documents': doc_count,
                    'entities': entity_count,
                    'relationships': rel_count,
                },
                'neo4j': neo4j_stats,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error("获取统计信息失败: %s", e)
            return {}
