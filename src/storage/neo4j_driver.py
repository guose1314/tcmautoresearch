"""
Neo4j 图数据库驱动
中医古籍全自动研究系统 - 知识图谱存储
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Neo4jNode:
    """Neo4j节点"""
    id: str
    label: str  # 节点类型：Formula, Herb, Syndrome, Efficacy
    properties: Dict[str, Any]


@dataclass
class Neo4jEdge:
    """Neo4j边"""
    source_id: str
    target_id: str
    relationship_type: str  # SOVEREIGN, MINISTER, TREATS, etc.
    properties: Dict[str, Any]


class Neo4jDriver:
    """Neo4j 驱动封装 - 支持图数据CRUD"""
    
    def __init__(self, uri: str, auth: Tuple[str, str], database: str = "neo4j"):
        """
        初始化Neo4j驱动
        
        Args:
            uri: 连接URI，例如 neo4j://localhost:7687
            auth: (用户名, 密码) 元组
            database: 数据库名称
        """
        self.uri = uri
        self.auth = auth
        self.database = database
        self.driver = None
    
    def connect(self):
        """建立连接"""
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(self.uri, auth=self.auth)
            # 验证连接
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1")
                result.consume()
            logger.info(f"Neo4j 连接成功: {self.uri}")
        except Exception as e:
            logger.error(f"Neo4j 连接失败: {e}")
            raise
    
    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j 连接已关闭")
    
    def clear_database(self):
        """清空数据库（谨慎使用）"""
        try:
            from neo4j import GraphDatabase
            with self.driver.session(database=self.database) as session:
                session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))
            logger.info("Neo4j 数据库已清空")
        except Exception as e:
            logger.error(f"清空数据库失败: {e}")
            raise
    
    # ==================== 节点操作 ====================
    
    def create_node(self, node: Neo4jNode) -> bool:
        """
        创建或更新节点
        
        Args:
            node: 节点对象
        
        Returns:
            是否成功
        """
        try:
            from neo4j import GraphDatabase
            query = f"""
            MERGE (n:{node.label} {{id: $id}})
            SET n += $properties
            RETURN n
            """
            
            with self.driver.session(database=self.database) as session:
                session.execute_write(
                    lambda tx: tx.run(
                        query,
                        id=node.id,
                        properties=node.properties
                    )
                )
            return True
        except Exception as e:
            logger.error(f"创建节点失败: {e}")
            return False
    
    def batch_create_nodes(self, nodes: List[Neo4jNode]) -> bool:
        """批量创建节点"""
        try:
            if not nodes:
                return True

            grouped_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for node in nodes:
                grouped_rows[node.label].append(
                    {
                        "id": node.id,
                        "properties": node.properties,
                    }
                )

            with self.driver.session(database=self.database) as session:
                for label, rows in grouped_rows.items():
                    query = f"""
                    UNWIND $rows AS row
                    MERGE (n:{label} {{id: row.id}})
                    SET n += row.properties
                    """
                    session.execute_write(lambda tx: tx.run(query, rows=rows))

            logger.info(f"批量创建节点成功: {len(nodes)} 个节点")
            return True
        except Exception as e:
            logger.error(f"批量创建节点失败: {e}")
            return False
    
    def get_node(self, node_id: str, label: str) -> Optional[Dict]:
        """
        获取节点
        
        Args:
            node_id: 节点ID
            label: 节点标签
        
        Returns:
            节点数据或None
        """
        try:
            from neo4j import GraphDatabase
            query = f"MATCH (n:{label} {{id: $id}}) RETURN n"
            
            with self.driver.session(database=self.database) as session:
                result = session.execute_read(
                    lambda tx: tx.run(query, id=node_id).single()
                )
            
            if result:
                return dict(result['n'])
            return None
        except Exception as e:
            logger.error(f"获取节点失败: {e}")
            return None
    
    def delete_node(self, node_id: str, label: str) -> bool:
        """删除节点及其关系"""
        try:
            from neo4j import GraphDatabase
            query = f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n"
            
            with self.driver.session(database=self.database) as session:
                session.execute_write(lambda tx: tx.run(query, id=node_id))
            return True
        except Exception as e:
            logger.error(f"删除节点失败: {e}")
            return False
    
    # ==================== 关系操作 ====================
    
    def create_relationship(self, edge: Neo4jEdge, source_label: str, target_label: str) -> bool:
        """
        创建关系
        
        Args:
            edge: 边对象
            source_label: 源节点标签
            target_label: 目标节点标签
        
        Returns:
            是否成功
        """
        try:
            from neo4j import GraphDatabase
            query = f"""
            MATCH (source:{source_label} {{id: $source_id}})
            MATCH (target:{target_label} {{id: $target_id}})
            MERGE (source)-[r:{edge.relationship_type}]->(target)
            SET r += $properties
            RETURN r
            """
            
            with self.driver.session(database=self.database) as session:
                session.execute_write(
                    lambda tx: tx.run(
                        query,
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                        properties=edge.properties
                    )
                )
            return True
        except Exception as e:
            logger.error(f"创建关系失败: {e}")
            return False
    
    def batch_create_relationships(self, edges: List[Tuple[Neo4jEdge, str, str]]) -> bool:
        """
        批量创建关系
        
        Args:
            edges: [(edge, source_label, target_label), ...] 列表
        
        Returns:
            是否成功
        """
        try:
            if not edges:
                return True

            grouped_rows: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
            for edge, source_label, target_label in edges:
                grouped_rows[(source_label, target_label, edge.relationship_type)].append(
                    {
                        "source_id": edge.source_id,
                        "target_id": edge.target_id,
                        "properties": edge.properties,
                    }
                )

            with self.driver.session(database=self.database) as session:
                for (source_label, target_label, rel_type), rows in grouped_rows.items():
                    query = f"""
                    UNWIND $rows AS row
                    MATCH (source:{source_label} {{id: row.source_id}})
                    MATCH (target:{target_label} {{id: row.target_id}})
                    MERGE (source)-[r:{rel_type}]->(target)
                    SET r += row.properties
                    """
                    session.execute_write(lambda tx: tx.run(query, rows=rows))

            logger.info(f"批量创建关系成功: {len(edges)} 个关系")
            return True
        except Exception as e:
            logger.error(f"批量创建关系失败: {e}")
            return False
    
    def get_relationships(self, source_id: str, source_label: str, 
                         rel_type: Optional[str] = None) -> List[Dict]:
        """
        获取节点的出边关系
        
        Args:
            source_id: 源节点ID
            source_label: 源节点标签
            rel_type: 关系类型过滤（可选）
        
        Returns:
            关系列表
        """
        try:
            from neo4j import GraphDatabase
            if rel_type:
                query = f"""
                MATCH (source:{source_label} {{id: $source_id}})-[r:{rel_type}]->(target)
                RETURN r, target
                """
            else:
                query = f"""
                MATCH (source:{source_label} {{id: $source_id}})-[r]->(target)
                RETURN r, target
                """
            
            with self.driver.session(database=self.database) as session:
                results = session.execute_read(
                    lambda tx: list(tx.run(query, source_id=source_id))
                )
            
            return [
                {
                    'relationship': dict(result['r']),
                    'target': dict(result['target'])
                }
                for result in results
            ]
        except Exception as e:
            logger.error(f"获取关系失败: {e}")
            return []
    
    def delete_relationship(self, source_id: str, target_id: str, 
                          rel_type: str, source_label: str, target_label: str) -> bool:
        """删除关系"""
        try:
            from neo4j import GraphDatabase
            query = f"""
            MATCH (source:{source_label} {{id: $source_id}})-[r:{rel_type}]->(target:{target_label} {{id: $target_id}})
            DELETE r
            """
            
            with self.driver.session(database=self.database) as session:
                session.execute_write(
                    lambda tx: tx.run(
                        query,
                        source_id=source_id,
                        target_id=target_id
                    )
                )
            return True
        except Exception as e:
            logger.error(f"删除关系失败: {e}")
            return False
    
    # ==================== 查询操作 ====================
    
    def find_formula_composition(self, formula_name: str) -> Dict[str, List[str]]:
        """
        查找方剂的组成（君臣佐使）
        
        Args:
            formula_name: 方剂名称
        
        Returns:
            {
                'sovereign': [药物列表],
                'minister': [药物列表],
                'assistant': [药物列表],
                'envoy': [药物列表]
            }
        """
        try:
            from neo4j import GraphDatabase
            query = """
            MATCH (f:Formula {name: $formula_name})
            OPTIONAL MATCH (f)-[:SOVEREIGN]->(sovereign:Herb)
            OPTIONAL MATCH (f)-[:MINISTER]->(minister:Herb)
            OPTIONAL MATCH (f)-[:ASSISTANT]->(assistant:Herb)
            OPTIONAL MATCH (f)-[:ENVOY]->(envoy:Herb)
            RETURN 
                collect(sovereign.name) as sovereign,
                collect(minister.name) as minister,
                collect(assistant.name) as assistant,
                collect(envoy.name) as envoy
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.execute_read(
                    lambda tx: tx.run(query, formula_name=formula_name).single()
                )
            
            if result:
                return {
                    'sovereign': [h for h in result['sovereign'] if h],
                    'minister': [h for h in result['minister'] if h],
                    'assistant': [h for h in result['assistant'] if h],
                    'envoy': [h for h in result['envoy'] if h],
                }
            return {}
        except Exception as e:
            logger.error(f"查询方剂组成失败: {e}")
            return {}
    
    def find_formulas_treating_syndrome(self, syndrome_name: str) -> List[Dict]:
        """
        查找治疗某症候的所有方剂
        
        Args:
            syndrome_name: 症候名称
        
        Returns:
            方剂列表
        """
        try:
            from neo4j import GraphDatabase
            query = """
            MATCH (f:Formula)-[:TREATS]->(s:Syndrome {name: $syndrome_name})
            RETURN f.name as name, f as properties
            """
            
            with self.driver.session(database=self.database) as session:
                results = session.execute_read(
                    lambda tx: list(tx.run(query, syndrome_name=syndrome_name))
                )
            
            return [{'name': result['name'], 'properties': dict(result['properties'])} for result in results]
        except Exception as e:
            logger.error(f"查询治疗方剂失败: {e}")
            return []
    
    def find_herb_efficacies(self, herb_name: str) -> List[str]:
        """
        查找中药的所有功效
        
        Args:
            herb_name: 中药名称
        
        Returns:
            功效列表
        """
        try:
            from neo4j import GraphDatabase
            query = """
            MATCH (h:Herb {name: $herb_name})-[:HAS_EFFICACY]->(e:Efficacy)
            RETURN e.name as efficacy
            """
            
            with self.driver.session(database=self.database) as session:
                results = session.execute_read(
                    lambda tx: list(tx.run(query, herb_name=herb_name))
                )
            
            return [result['efficacy'] for result in results]
        except Exception as e:
            logger.error(f"查询功效失败: {e}")
            return []
    
    def find_similar_formulas(self, formula_name: str, limit: int = 10) -> List[Dict]:
        """
        查找类似方剂
        
        Args:
            formula_name: 方剂名称
            limit: 返回数量限制
        
        Returns:
            类似方剂列表
        """
        try:
            from neo4j import GraphDatabase
            query = """
            MATCH (f1:Formula {name: $formula_name})-[:SIMILAR_TO]-(f2:Formula)
            RETURN f2.name as name, f2 as properties
            LIMIT $limit
            """
            
            with self.driver.session(database=self.database) as session:
                results = session.execute_read(
                    lambda tx: list(tx.run(query, formula_name=formula_name, limit=limit))
                )
            
            return [{'name': result['name'], 'properties': dict(result['properties'])} for result in results]
        except Exception as e:
            logger.error(f"查询类似方剂失败: {e}")
            return []
    
    def get_graph_statistics(self) -> Dict[str, Any]:
        """
        获取图数据库统计信息
        
        Returns:
            统计数据
        """
        try:
            from neo4j import GraphDatabase
            node_query = "MATCH (n) RETURN labels(n)[0] as label, count(*) as count"
            rel_query = "MATCH ()-[r]->() RETURN type(r) as type, count(*) as count"
            
            with self.driver.session(database=self.database) as session:
                nodes = session.execute_read(lambda tx: list(tx.run(node_query)))
                rels = session.execute_read(lambda tx: list(tx.run(rel_query)))
            
            return {
                'nodes_by_type': {result['label']: result['count'] for result in nodes},
                'relationships_by_type': {result['type']: result['count'] for result in rels},
                'total_nodes': sum(result['count'] for result in nodes),
                'total_relationships': sum(result['count'] for result in rels),
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}


# ==================== 工具函数 ====================

def _to_json_text(value: Any) -> str:
    """将复杂对象转换为 Neo4j 可接受的 JSON 文本。"""
    if value is None:
        return "{}"
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return "{}"

def entity_to_neo4j_node(entity: 'Entity', node_id: str = None) -> Neo4jNode:
    """
    将PostgreSQL实体转换为Neo4j节点
    
    Args:
        entity: SQLAlchemy Entity 对象
        node_id: 自定义节点ID
    
    Returns:
        Neo4j节点
    """
    label_map = {
        'formula': 'Formula',
        'herb': 'Herb',
        'syndrome': 'Syndrome',
        'efficacy': 'Efficacy',
        'property': 'Property',
        'taste': 'Taste',
        'meridian': 'Meridian',
    }
    
    node_id = node_id or str(entity.id)
    label = label_map.get(entity.type.value, 'Entity')
    
    return Neo4jNode(
        id=node_id,
        label=label,
        properties={
            'name': entity.name,
            'type': entity.type.value,
            'confidence': entity.confidence,
            'alternative_names': entity.alternative_names or [],
            'description': entity.description or '',
            'entity_metadata_json': _to_json_text(entity.entity_metadata),
        }
    )


def relationship_to_neo4j_edge(rel: 'EntityRelationship', rel_type_name: str) -> Neo4jEdge:
    """
    将PostgreSQL关系转换为Neo4j边
    
    Args:
        rel: SQLAlchemy EntityRelationship 对象
        rel_type_name: 关系类型英文名
    
    Returns:
        Neo4j边
    """
    return Neo4jEdge(
        source_id=str(rel.source_entity_id),
        target_id=str(rel.target_entity_id),
        relationship_type=rel_type_name,
        properties={
            'confidence': rel.confidence,
            'created_by_module': rel.created_by_module or 'unknown',
            'evidence': rel.evidence or '',
            'relationship_metadata_json': _to_json_text(rel.relationship_metadata),
        }
    )
