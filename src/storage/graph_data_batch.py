from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.storage.neo4j_driver import Neo4jEdge, Neo4jNode


@dataclass
class GraphDataBatch:
    """统一图数据批处理对象
    用于在 SemanticModeler 等分析阶段结束后收集整理所有的实体和关联提取结果，
    以便统一传送给 TransactionCoordinator 执行事务级双写。
    """
    
    # 将要入 PG / Neo4j 的实体节点列表
    nodes: List[Neo4jNode] = field(default_factory=list)
    
    # 将要入 PG / Neo4j 的边列表。元组形式: (edge_obj, source_label, target_label)
    edges: List[tuple[Neo4jEdge, str, str]] = field(default_factory=list)

    # 附带将要存入 PG 的 SQLAlchemy ORM 对象（可选）
    pg_entities: List[Any] = field(default_factory=list)

    def add_node(self, node: Neo4jNode) -> None:
        """追加图节点"""
        self.nodes.append(node)

    def add_edge(self, edge: Neo4jEdge, source_label: str, target_label: str) -> None:
        """追加图边及其两端节点的 Label (以便组装 MERGE 语句)"""
        self.edges.append((edge, source_label, target_label))

    def add_pg_entity(self, pg_entity: Any) -> None:
        """追加 PG 关系型记录"""
        self.pg_entities.append(pg_entity)

    def is_empty(self) -> bool:
        """判断批次是否为空"""
        return not self.nodes and not self.edges and not self.pg_entities

    def clear(self) -> None:
        """清空批次数据"""
        self.nodes.clear()
        self.edges.clear()
        self.pg_entities.clear()
