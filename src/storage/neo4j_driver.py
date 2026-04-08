from __future__ import annotations

"""
Neo4j 图数据库驱动
中医古籍全自动研究系统 - 知识图谱存储

提供:
- Neo4jDriver: 底层 Cypher CRUD
- Neo4jKnowledgeGraph(IKnowledgeGraph): 统一图谱接口的 Neo4j 实现
- create_knowledge_graph(): 工厂函数，按配置返回 Neo4j 或 NetworkX 后端
"""

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from .graph_interface import (
    ENTITY_TYPES,
    FOUR_LEVELS,
    LEVEL_RELATION_TYPES,
    IKnowledgeGraph,
    KnowledgeGap,
)

if TYPE_CHECKING:
    from src.infrastructure.persistence import Entity, EntityRelationship

logger = logging.getLogger(__name__)

_CYPHER_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_cypher_label(value: str) -> str:
    """校验 Cypher 标签/关系类型标识符，防止注入。

    Cypher 不支持对 label 和 relationship-type 使用 ``$param`` 参数化，
    因此必须在拼接前确保值仅含合法标识符字符。
    """
    if not isinstance(value, str) or not _CYPHER_IDENTIFIER_RE.match(value):
        raise ValueError(
            f"非法 Cypher 标识符: {value!r}，仅允许字母、数字和下划线"
        )
    return value


def _get_neo4j_graph_database() -> Any:
    """按需加载 Neo4j GraphDatabase，避免模块导入阶段硬依赖。"""
    try:
        return import_module("neo4j").GraphDatabase
    except Exception as exc:  # pragma: no cover - 缺依赖时在运行期反馈
        raise RuntimeError("neo4j 未安装或不可用，无法执行图数据库操作") from exc


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
    
    def __init__(
        self,
        uri: str,
        auth: Tuple[str, str],
        database: str = "neo4j",
        *,
        max_connection_pool_size: int = 50,
        connection_acquisition_timeout: float = 60.0,
        max_connection_lifetime: int = 3600,
    ):
        """
        初始化Neo4j驱动
        
        Args:
            uri: 连接URI，例如 neo4j://localhost:7687
            auth: (用户名, 密码) 元组
            database: 数据库名称
            max_connection_pool_size: 连接池最大连接数
            connection_acquisition_timeout: 从池中获取连接的超时秒数
            max_connection_lifetime: 连接最大存活秒数
        """
        self.uri = uri
        self.auth = auth
        self.database = database
        self._pool_config = {
            "max_connection_pool_size": max_connection_pool_size,
            "connection_acquisition_timeout": connection_acquisition_timeout,
            "max_connection_lifetime": max_connection_lifetime,
        }
        self.driver = None
    
    def connect(self):
        """建立连接（启用连接池）"""
        try:
            GraphDatabase = _get_neo4j_graph_database()
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=self.auth,
                max_connection_pool_size=self._pool_config["max_connection_pool_size"],
                connection_acquisition_timeout=self._pool_config["connection_acquisition_timeout"],
                max_connection_lifetime=self._pool_config["max_connection_lifetime"],
            )
            # 验证连接
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1")
                result.consume()
            logger.info(
                "Neo4j 连接成功: %s (pool_size=%d)",
                self.uri, self._pool_config["max_connection_pool_size"],
            )
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
            query = f"""
            MERGE (n:{_safe_cypher_label(node.label)} {{id: $id}})
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
                    MERGE (n:{_safe_cypher_label(label)} {{id: row.id}})
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
            query = f"MATCH (n:{_safe_cypher_label(label)} {{id: $id}}) RETURN n"
            
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
            query = f"MATCH (n:{_safe_cypher_label(label)} {{id: $id}}) DETACH DELETE n"
            
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
            query = f"""
            MATCH (source:{_safe_cypher_label(source_label)} {{id: $source_id}})
            MATCH (target:{_safe_cypher_label(target_label)} {{id: $target_id}})
            MERGE (source)-[r:{_safe_cypher_label(edge.relationship_type)}]->(target)
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
                    MATCH (source:{_safe_cypher_label(source_label)} {{id: row.source_id}})
                    MATCH (target:{_safe_cypher_label(target_label)} {{id: row.target_id}})
                    MERGE (source)-[r:{_safe_cypher_label(rel_type)}]->(target)
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
            if rel_type:
                query = f"""
                MATCH (source:{_safe_cypher_label(source_label)} {{id: $source_id}})-[r:{_safe_cypher_label(rel_type)}]->(target)
                RETURN r, target
                """
            else:
                query = f"""
                MATCH (source:{_safe_cypher_label(source_label)} {{id: $source_id}})-[r]->(target)
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
            query = f"""
            MATCH (source:{_safe_cypher_label(source_label)} {{id: $source_id}})-[r:{_safe_cypher_label(rel_type)}]->(target:{_safe_cypher_label(target_label)} {{id: $target_id}})
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

    def collect_formula_similarity_evidence(self, formula_name: str, similar_formula_name: str) -> Dict[str, Any]:
        """汇总两个方剂在图数据库中的相似性证据。"""
        try:
            shared_herb_query = """
            MATCH (f1:Formula {name: $formula_name})-[r1]->(h:Herb)<-[r2]-(f2:Formula {name: $similar_formula_name})
            WHERE type(r1) IN ['SOVEREIGN', 'MINISTER', 'ASSISTANT', 'ENVOY']
              AND type(r2) IN ['SOVEREIGN', 'MINISTER', 'ASSISTANT', 'ENVOY']
            RETURN h.name AS herb_name, type(r1) AS formula_role, type(r2) AS similar_formula_role
            ORDER BY herb_name
            """
            shared_syndrome_query = """
            MATCH (f1:Formula {name: $formula_name})-[:TREATS]->(s:Syndrome)<-[:TREATS]-(f2:Formula {name: $similar_formula_name})
            RETURN collect(DISTINCT s.name) AS syndromes
            """
            direct_relationship_query = """
            MATCH (f1:Formula {name: $formula_name})-[r]-(f2:Formula {name: $similar_formula_name})
            RETURN type(r) AS relationship_type, properties(r) AS properties
            """

            with self.driver.session(database=self.database) as session:
                shared_herbs = session.execute_read(
                    lambda tx: [
                        {
                            "herb": record["herb_name"],
                            "formula_role": str(record["formula_role"]).lower(),
                            "similar_formula_role": str(record["similar_formula_role"]).lower(),
                        }
                        for record in tx.run(
                            shared_herb_query,
                            formula_name=formula_name,
                            similar_formula_name=similar_formula_name,
                        )
                    ]
                )
                syndrome_record = session.execute_read(
                    lambda tx: tx.run(
                        shared_syndrome_query,
                        formula_name=formula_name,
                        similar_formula_name=similar_formula_name,
                    ).single()
                )
                direct_relationships = session.execute_read(
                    lambda tx: [
                        {
                            "relationship_type": record["relationship_type"],
                            "properties": dict(record["properties"] or {}),
                        }
                        for record in tx.run(
                            direct_relationship_query,
                            formula_name=formula_name,
                            similar_formula_name=similar_formula_name,
                        )
                    ]
                )

            shared_syndromes = []
            if syndrome_record:
                shared_syndromes = [item for item in (syndrome_record.get("syndromes") or []) if item]

            evidence_score = min(
                1.0,
                round(
                    len(shared_herbs) * 0.18
                    + len(shared_syndromes) * 0.22
                    + len(direct_relationships) * 0.12,
                    3,
                ),
            )
            return {
                "source": "neo4j",
                "shared_herbs": shared_herbs,
                "shared_syndromes": shared_syndromes,
                "direct_relationships": direct_relationships,
                "evidence_score": evidence_score,
            }
        except Exception as e:
            logger.error(f"查询方剂图谱证据失败: {e}")
            return {}
    
    def get_graph_statistics(self) -> Dict[str, Any]:
        """
        获取图数据库统计信息
        
        Returns:
            统计数据
        """
        try:
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

def entity_to_neo4j_node(entity: Entity, node_id: str | None = None) -> Neo4jNode:
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


def relationship_to_neo4j_edge(rel: EntityRelationship, rel_type_name: str) -> Neo4jEdge:
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


# ==================== 统一接口实现 ====================

# 实体 type → Neo4j 标签映射
_TYPE_TO_LABEL: Dict[str, str] = {
    "formula": "Formula",
    "herb": "Herb",
    "syndrome": "Syndrome",
    "target": "Target",
    "pathway": "Pathway",
    "efficacy": "Efficacy",
    "property": "Property",
    "taste": "Taste",
    "meridian": "Meridian",
    "generic": "Entity",
}

_COMPOSITION_ROLES: Set[str] = {"sovereign", "minister", "assistant", "envoy"}


class Neo4jKnowledgeGraph(IKnowledgeGraph):
    """基于 Neo4j 的 IKnowledgeGraph 实现。

    作为全系统知识图谱的首选后端。
    当 Neo4j 不可用时可通过工厂退化为 NetworkX。

    Parameters
    ----------
    driver : Neo4jDriver
        已初始化（已 connect）的 Neo4j 驱动实例。
    preload_formulas : bool
        是否预加载 TCMRelationshipDefinitions 静态数据。
    """

    def __init__(self, driver: Neo4jDriver, *, preload_formulas: bool = True) -> None:
        self._driver = driver
        if preload_formulas:
            self._preload_formula_compositions()

    # ------------------------------------------------------------------ #
    # IKnowledgeGraph 接口
    # ------------------------------------------------------------------ #

    def add_entity(self, entity: Dict[str, Any]) -> None:
        name = entity["name"]
        etype = entity.get("type", "generic")
        label = _TYPE_TO_LABEL.get(etype, "Entity")
        props = {k: v for k, v in entity.items() if k not in ("name", "type")}
        props["name"] = name
        props["entity_type"] = etype
        self._driver.create_node(Neo4jNode(id=name, label=label, properties=props))

    def add_relation(
        self,
        src: str,
        rel_type: str,
        dst: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        metadata = metadata or {}
        # 自动补端点（Neo4j MERGE 天然幂等）
        self._ensure_node(src)
        self._ensure_node(dst)
        rel_upper = rel_type.upper()
        src_label = self._resolve_label(src)
        dst_label = self._resolve_label(dst)
        edge = Neo4jEdge(
            source_id=src,
            target_id=dst,
            relationship_type=rel_upper,
            properties=metadata,
        )
        self._driver.create_relationship(edge, src_label, dst_label)

    def query_path(self, src: str, dst: str) -> List[List[str]]:
        """查询两节点间所有简单路径（最大深度 8）。"""
        query = """
        MATCH p = allShortestPaths((a {id: $src})-[*..8]-(b {id: $dst}))
        RETURN [n IN nodes(p) | n.id] AS path
        LIMIT 50
        """
        try:
            with self._driver.driver.session(database=self._driver.database) as session:
                records = session.execute_read(
                    lambda tx: list(tx.run(query, src=src, dst=dst))
                )
            return [list(r["path"]) for r in records if r["path"]]
        except Exception as exc:
            logger.warning("Neo4j query_path 失败: %s", exc)
            return []

    def find_gaps(self) -> List[KnowledgeGap]:
        gaps: List[KnowledgeGap] = []
        self._find_orphan_gaps_cypher(gaps)
        self._find_missing_downstream_gaps_cypher(gaps)
        self._find_incomplete_composition_gaps_cypher(gaps)
        return gaps

    def get_subgraph(self, entity: str, depth: int = 2) -> Any:
        """以 entity 为中心 BFS 提取子图，返回 networkx.DiGraph。"""
        safe_depth = max(1, min(int(depth), 20))
        query = f"""  # nosec: cypher — safe_depth is a bounded int(1-20)
        MATCH (start {{id: $entity_id}})
        CALL {{
            WITH start
            MATCH path = (start)-[*1..{safe_depth}]-(neighbor)
            RETURN nodes(path) AS ns, relationships(path) AS rs
        }}
        WITH ns, rs
        UNWIND ns AS n
        WITH collect(DISTINCT n) AS all_nodes,
             collect(rs) AS all_paths
        UNWIND all_paths AS rels_in_path
        UNWIND rels_in_path AS r
        WITH all_nodes,
             collect(DISTINCT r) AS all_rels
        RETURN
            [n IN all_nodes | {{id: n.id, labels: labels(n), props: properties(n)}}] AS nodes,
            [r IN all_rels  | {{src: startNode(r).id, dst: endNode(r).id,
                               type: type(r), props: properties(r)}}] AS edges
        """
        try:
            nx = import_module("networkx")
            with self._driver.driver.session(database=self._driver.database) as session:
                record = session.execute_read(
                    lambda tx: tx.run(query, entity_id=entity).single()
                )
            g = nx.DiGraph()
            if record:
                for n in record["nodes"]:
                    g.add_node(n["id"], **(n["props"] or {}))
                for e in record["edges"]:
                    g.add_edge(e["src"], e["dst"], rel_type=e["type"], **(e["props"] or {}))
            return g
        except Exception as exc:
            logger.warning("Neo4j get_subgraph 失败: %s", exc)
            nx = import_module("networkx")
            return nx.DiGraph()

    # ------------------------------------------------------------------ #
    # 便捷查询（与 TCMKnowledgeGraph 对齐）
    # ------------------------------------------------------------------ #

    @property
    def entity_count(self) -> int:
        stats = self._driver.get_graph_statistics()
        return stats.get("total_nodes", 0)

    @property
    def relation_count(self) -> int:
        stats = self._driver.get_graph_statistics()
        return stats.get("total_relationships", 0)

    def entities_by_type(self, entity_type: str) -> List[str]:
        label = _TYPE_TO_LABEL.get(entity_type, "Entity")
        query = f"MATCH (n:{_safe_cypher_label(label)}) RETURN n.id AS id"
        try:
            with self._driver.driver.session(database=self._driver.database) as session:
                records = session.execute_read(lambda tx: list(tx.run(query)))
            return [r["id"] for r in records if r["id"]]
        except Exception:
            return []

    def neighbors(self, entity: str, rel_type: Optional[str] = None) -> List[str]:
        if rel_type:
            query = """
            MATCH (n {id: $eid})-[r]->(m)
            WHERE type(r) = $rtype
            RETURN m.id AS id
            """
            params: Dict[str, Any] = {"eid": entity, "rtype": rel_type.upper()}
        else:
            query = "MATCH (n {id: $eid})-[]->(m) RETURN m.id AS id"
            params = {"eid": entity}
        try:
            with self._driver.driver.session(database=self._driver.database) as session:
                records = session.execute_read(lambda tx: list(tx.run(query, **params)))
            return [r["id"] for r in records if r["id"]]
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    # 批量导入
    # ------------------------------------------------------------------ #

    def bulk_add_entities(self, entities: List[Dict[str, Any]]) -> int:
        nodes = []
        for ent in entities:
            name = ent["name"]
            etype = ent.get("type", "generic")
            label = _TYPE_TO_LABEL.get(etype, "Entity")
            props = {k: v for k, v in ent.items() if k not in ("name", "type")}
            props["name"] = name
            props["entity_type"] = etype
            nodes.append(Neo4jNode(id=name, label=label, properties=props))
        if nodes:
            self._driver.batch_create_nodes(nodes)
        return len(nodes)

    def bulk_add_relations(
        self, relations: List[Tuple[str, str, str, Optional[Dict[str, Any]]]]
    ) -> int:
        edges: List[Tuple[Neo4jEdge, str, str]] = []
        for src, rel_type, dst, meta in relations:
            meta = meta or {}
            self._ensure_node(src)
            self._ensure_node(dst)
            src_label = self._resolve_label(src)
            dst_label = self._resolve_label(dst)
            edge = Neo4jEdge(
                source_id=src,
                target_id=dst,
                relationship_type=rel_type.upper(),
                properties=meta,
            )
            edges.append((edge, src_label, dst_label))
        if edges:
            self._driver.batch_create_relationships(edges)
        return len(edges)

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #

    def save(self) -> None:
        """Neo4j 写操作立即落盘，此处为兼容性空操作。"""

    def close(self) -> None:
        self._driver.close()

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _ensure_node(self, name: str) -> None:
        """MERGE 节点，确保存在。"""
        self._driver.create_node(Neo4jNode(id=name, label="Entity", properties={"name": name}))

    def _resolve_label(self, node_id: str) -> str:
        """尝试获取已有节点的标签，默认 Entity。"""
        for label in _TYPE_TO_LABEL.values():
            node = self._driver.get_node(node_id, label)
            if node is not None:
                return label
        return "Entity"

    def _preload_formula_compositions(self) -> None:
        """从 TCMRelationshipDefinitions 预加载方剂组成到 Neo4j。"""
        try:
            from src.semantic_modeling.tcm_relationships import (
                TCMRelationshipDefinitions,
            )
        except ImportError:
            logger.debug("TCMRelationshipDefinitions 不可用，跳过预加载")
            return

        nodes: List[Neo4jNode] = []
        edge_tuples: List[Tuple[Neo4jEdge, str, str]] = []

        compositions = TCMRelationshipDefinitions.FORMULA_COMPOSITIONS
        for formula_name, roles in compositions.items():
            nodes.append(Neo4jNode(id=formula_name, label="Formula",
                                    properties={"name": formula_name, "entity_type": "formula"}))
            for role, herbs in roles.items():
                for herb in herbs:
                    nodes.append(Neo4jNode(id=herb, label="Herb",
                                            properties={"name": herb, "entity_type": "herb"}))
                    edge_tuples.append((
                        Neo4jEdge(source_id=formula_name, target_id=herb,
                                  relationship_type=role.upper(), properties={}),
                        "Formula", "Herb",
                    ))

        for herb, effs in TCMRelationshipDefinitions.HERB_EFFICACY_MAP.items():
            nodes.append(Neo4jNode(id=herb, label="Herb",
                                    properties={"name": herb, "entity_type": "herb"}))
            for eff in effs:
                nodes.append(Neo4jNode(id=eff, label="Efficacy",
                                        properties={"name": eff, "entity_type": "efficacy"}))
                edge_tuples.append((
                    Neo4jEdge(source_id=herb, target_id=eff,
                              relationship_type="EFFICACY", properties={}),
                    "Herb", "Efficacy",
                ))

        if nodes:
            self._driver.batch_create_nodes(nodes)
        if edge_tuples:
            self._driver.batch_create_relationships(edge_tuples)

    # -- Cypher gap detection --

    def _find_orphan_gaps_cypher(self, gaps: List[KnowledgeGap]) -> None:
        query = """
        MATCH (n)
        WHERE NOT (n)--()
        RETURN n.id AS id, labels(n)[0] AS label
        """
        try:
            with self._driver.driver.session(database=self._driver.database) as session:
                records = session.execute_read(lambda tx: list(tx.run(query)))
            for r in records:
                ntype = r["label"].lower() if r["label"] else "generic"
                gaps.append(KnowledgeGap(
                    gap_type="orphan_entity",
                    entity=r["id"],
                    entity_type=ntype,
                    description=f"实体 '{r['id']}' 没有任何关系连接",
                    severity="medium",
                ))
        except Exception as exc:
            logger.warning("orphan gap 查询失败: %s", exc)

    def _find_missing_downstream_gaps_cypher(self, gaps: List[KnowledgeGap]) -> None:
        level_pairs = [
            ("Formula", "Syndrome", "TREATS"),
            ("Syndrome", "Target", "ASSOCIATED_TARGET"),
            ("Target", "Pathway", "PARTICIPATES_IN"),
        ]
        for src_label, dst_label, expected_rel in level_pairs:
            query = f"""
            MATCH (n:{_safe_cypher_label(src_label)})
            WHERE NOT (n)-[:{_safe_cypher_label(expected_rel)}]->(:{_safe_cypher_label(dst_label)})
            RETURN n.id AS id
            """
            try:
                with self._driver.driver.session(database=self._driver.database) as session:
                    records = session.execute_read(lambda tx: list(tx.run(query)))
                for r in records:
                    gaps.append(KnowledgeGap(
                        gap_type="missing_downstream",
                        entity=r["id"],
                        entity_type=src_label.lower(),
                        description=(
                            f"{src_label.lower()} '{r['id']}' 缺少到 {dst_label.lower()}"
                            f" 层级的 '{expected_rel.lower()}' 关系"
                        ),
                        severity="high",
                    ))
            except Exception as exc:
                logger.warning("downstream gap 查询失败 (%s): %s", src_label, exc)

    def _find_incomplete_composition_gaps_cypher(self, gaps: List[KnowledgeGap]) -> None:
        query = """
        MATCH (f:Formula)
        OPTIONAL MATCH (f)-[r]->(h:Herb)
        WHERE type(r) IN ['SOVEREIGN','MINISTER','ASSISTANT','ENVOY']
        WITH f, collect(DISTINCT type(r)) AS present_roles
        WHERE size(present_roles) < 4
        RETURN f.id AS id, present_roles
        """
        try:
            with self._driver.driver.session(database=self._driver.database) as session:
                records = session.execute_read(lambda tx: list(tx.run(query)))
            for r in records:
                present = {str(role).lower() for role in (r["present_roles"] or [])}
                missing = _COMPOSITION_ROLES - present
                if missing:
                    gaps.append(KnowledgeGap(
                        gap_type="incomplete_composition",
                        entity=r["id"],
                        entity_type="formula",
                        description=f"方剂 '{r['id']}' 缺少角色: {', '.join(sorted(missing))}",
                        severity="low" if len(missing) == 1 else "medium",
                    ))
        except Exception as exc:
            logger.warning("composition gap 查询失败: %s", exc)


# ==================== 工厂函数 ====================


def create_knowledge_graph(
    config: Optional[Dict[str, Any]] = None,
    *,
    preload_formulas: bool = True,
) -> IKnowledgeGraph:
    """按配置返回知识图谱后端。

    优先使用 Neo4j；不可用时退化为 NetworkX (TCMKnowledgeGraph)。

    Parameters
    ----------
    config : dict | None
        应用配置字典，需包含 ``neo4j`` 段。
    preload_formulas : bool
        是否预加载方剂数据。

    Returns
    -------
    IKnowledgeGraph
        Neo4jKnowledgeGraph 或 TCMKnowledgeGraph 实例。
    """
    import os

    config = config or {}
    neo4j_cfg = config.get("neo4j") or {}

    if neo4j_cfg.get("enabled"):
        uri = neo4j_cfg.get("uri", "neo4j://localhost:7687")
        user = neo4j_cfg.get("user", "neo4j")
        password_env = neo4j_cfg.get("password_env", "TCM_NEO4J_PASSWORD")
        password = os.environ.get(password_env, "")
        database = neo4j_cfg.get("database", "neo4j")
        try:
            driver = Neo4jDriver(
                uri=uri, auth=(user, password), database=database,
                max_connection_pool_size=int(neo4j_cfg.get("max_connection_pool_size", 50)),
                connection_acquisition_timeout=float(neo4j_cfg.get("connection_acquisition_timeout", 60)),
                max_connection_lifetime=int(neo4j_cfg.get("max_connection_lifetime", 3600)),
            )
            driver.connect()
            logger.info("知识图谱后端: Neo4j (%s)", uri)
            return Neo4jKnowledgeGraph(driver, preload_formulas=preload_formulas)
        except Exception as exc:
            logger.warning("Neo4j 不可用，退化为 NetworkX: %s", exc)

    # Fallback: NetworkX
    from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph

    logger.info("知识图谱后端: NetworkX (TCMKnowledgeGraph)")
    return TCMKnowledgeGraph(preload_formulas=preload_formulas)
