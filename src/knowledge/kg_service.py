# src/knowledge/kg_service.py
"""
KnowledgeGraphService — 统一知识图谱服务

架构位置
--------
领域层的知识图谱统一入口。合并原有的:
- ``src/knowledge/tcm_knowledge_graph.py`` (NetworkX + SQLite)
- ``src/storage/neo4j_driver.py`` (Neo4j)

以 Neo4j 为主存储，NetworkX 作为可选内存缓存层。
当 Neo4j 不可用时，优雅降级到内存图。

设计目标
--------
* 统一实体和关系的增删查接口
* 支持 Cypher 查询和自然语言查询（通过 LLM 转换）
* 知识缺口发现（find_gaps）
* 子图提取（get_subgraph）

用法
----
::

    from src.knowledge.kg_service import KnowledgeGraphService

    kg = KnowledgeGraphService()
    kg.add_entities([{"name": "柴胡", "type": "herb", "properties": {...}}])
    kg.add_relations([{"source": "柴胡", "target": "疏肝", "type": "HAS_EFFICACY"}])
    result = kg.query_natural_language("柴胡归哪些经？")
    gaps = kg.find_gaps("小柴胡汤")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------

@dataclass
class EntityDTO:
    """知识图谱实体。"""
    name: str
    entity_type: str  # formula, herb, syndrome, target, pathway, efficacy
    properties: Dict[str, Any] = field(default_factory=dict)
    entity_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.entity_type,
            "properties": self.properties,
            "id": self.entity_id,
        }


@dataclass
class RelationDTO:
    """知识图谱关系。"""
    source: str
    target: str
    relation_type: str  # CONTAINS, TREATS, HAS_EFFICACY, ASSOCIATED_TARGET, ...
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.relation_type,
            "properties": self.properties,
        }


@dataclass
class KnowledgeGap:
    """知识缺口记录。"""
    gap_type: str       # orphan_entity | missing_downstream | incomplete_composition
    entity: str
    entity_type: str
    description: str
    severity: str       # high | medium | low


@dataclass
class KGQueryResult:
    """知识图谱查询结果。"""
    query: str
    cypher: str = ""
    records: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        return not self.error


@dataclass
class SubGraphDTO:
    """子图数据。"""
    center_entity: str
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    depth: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class KnowledgeGraphService:
    """统一知识图谱服务。

    Parameters
    ----------
    neo4j_uri : str | None
        Neo4j 连接 URI。为 ``None`` 时使用纯内存图。
    neo4j_auth : tuple[str, str] | None
        Neo4j 认证 (用户名, 密码)。
    neo4j_database : str
        Neo4j 数据库名。
    llm_gateway : object | None
        LLM 网关，用于自然语言→Cypher 转换。需具备 ``generate()`` 方法。
    config : dict | None
        从 config.yml 读取的 ``database.neo4j`` 配置节。
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_auth: Optional[tuple] = None,
        neo4j_database: str = "neo4j",
        llm_gateway: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._config = config or {}
        self._llm = llm_gateway
        self._neo4j_driver: Optional[Any] = None
        self._networkx_graph: Optional[Any] = None

        # Neo4j 配置
        self._neo4j_uri = neo4j_uri or self._config.get("uri")
        self._neo4j_auth = neo4j_auth or (
            self._config.get("username", "neo4j"),
            self._config.get("password", "neo4j"),
        )
        self._neo4j_database = neo4j_database or self._config.get("database", "neo4j")
        self._neo4j_enabled = self._config.get("enabled", False) and self._neo4j_uri

        # 初始化
        self._init_backends()

    def _init_backends(self) -> None:
        """初始化存储后端。"""
        # 尝试连接 Neo4j
        if self._neo4j_enabled:
            try:
                from src.storage.neo4j_driver import Neo4jDriver
                self._neo4j_driver = Neo4jDriver(
                    uri=self._neo4j_uri,
                    auth=self._neo4j_auth,
                    database=self._neo4j_database,
                )
                self._neo4j_driver.connect()
                logger.info("KnowledgeGraphService: Neo4j 已连接 (%s)", self._neo4j_uri)
            except Exception as exc:
                logger.warning("KnowledgeGraphService: Neo4j 连接失败，降级为内存图: %s", exc)
                self._neo4j_driver = None

        # 内存图（始终初始化，作为缓存或降级后端）
        try:
            import networkx as nx
            self._networkx_graph = nx.MultiDiGraph()
            logger.info("KnowledgeGraphService: NetworkX 内存图已初始化")
        except ImportError:
            logger.warning("networkx 未安装，内存图不可用")

    def close(self) -> None:
        """关闭所有连接。"""
        if self._neo4j_driver is not None:
            try:
                self._neo4j_driver.close()
            except Exception:
                pass
        self._networkx_graph = None

    @property
    def neo4j_available(self) -> bool:
        """Neo4j 是否可用。"""
        return self._neo4j_driver is not None

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    def add_entities(self, entities: Sequence[EntityDTO | Dict[str, Any]]) -> List[str]:
        """添加实体到知识图谱。

        Parameters
        ----------
        entities : list[EntityDTO | dict]
            实体列表。字典格式: ``{"name": str, "type": str, "properties": dict}``

        Returns
        -------
        list[str]
            添加的实体名称列表。
        """
        added: List[str] = []
        for ent in entities:
            if isinstance(ent, dict):
                ent = EntityDTO(
                    name=ent.get("name", ""),
                    entity_type=ent.get("type", "other"),
                    properties=ent.get("properties", {}),
                )

            # NetworkX 内存图
            if self._networkx_graph is not None:
                self._networkx_graph.add_node(
                    ent.name,
                    entity_type=ent.entity_type,
                    **ent.properties,
                )

            # Neo4j
            if self._neo4j_driver is not None:
                try:
                    from src.storage.neo4j_driver import Neo4jNode
                    node = Neo4jNode(
                        id=ent.entity_id or ent.name,
                        label=ent.entity_type.capitalize(),
                        properties={"name": ent.name, **ent.properties},
                    )
                    self._neo4j_driver.create_node(node)
                except Exception as exc:
                    logger.warning("Neo4j 添加实体失败 (%s): %s", ent.name, exc)

            added.append(ent.name)

        logger.info("已添加 %d 个实体到知识图谱", len(added))
        return added

    def add_relations(self, relations: Sequence[RelationDTO | Dict[str, Any]]) -> List[str]:
        """添加关系到知识图谱。

        Returns
        -------
        list[str]
            添加的关系描述列表。
        """
        added: List[str] = []
        for rel in relations:
            if isinstance(rel, dict):
                rel = RelationDTO(
                    source=rel.get("source", ""),
                    target=rel.get("target", ""),
                    relation_type=rel.get("type", "RELATES_TO"),
                    properties=rel.get("properties", {}),
                )

            desc = f"{rel.source}-[{rel.relation_type}]->{rel.target}"

            # NetworkX
            if self._networkx_graph is not None:
                self._networkx_graph.add_edge(
                    rel.source, rel.target,
                    key=rel.relation_type,
                    relation_type=rel.relation_type,
                    **rel.properties,
                )

            # Neo4j
            if self._neo4j_driver is not None:
                try:
                    from src.storage.neo4j_driver import Neo4jEdge
                    edge = Neo4jEdge(
                        source_id=rel.source,
                        target_id=rel.target,
                        relationship_type=rel.relation_type,
                        properties=rel.properties,
                    )
                    # 默认 label 为 "Entity"；调用方可通过 rel.properties 携带具体标签
                    src_label = str(rel.properties.get("source_label", "Entity"))
                    tgt_label = str(rel.properties.get("target_label", "Entity"))
                    self._neo4j_driver.create_relationship(edge, src_label, tgt_label)
                except Exception as exc:
                    logger.warning("Neo4j 添加关系失败 (%s): %s", desc, exc)

            added.append(desc)

        logger.info("已添加 %d 个关系到知识图谱", len(added))
        return added

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def query_cypher(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """执行 Cypher 查询。

        Parameters
        ----------
        cypher : str
            Cypher 查询语句。
        parameters : dict | None
            查询参数。

        Returns
        -------
        list[dict]
            查询结果记录列表。
        """
        if self._neo4j_driver is None:
            logger.warning("Neo4j 不可用，无法执行 Cypher 查询")
            return []

        try:
            driver = self._neo4j_driver.driver
            with driver.session(database=self._neo4j_database) as session:
                result = session.run(cypher, parameters or {})
                return [dict(record) for record in result]
        except Exception as exc:
            logger.error("Cypher 查询失败: %s\n查询: %s", exc, cypher[:200])
            return []

    def query_natural_language(self, question: str) -> KGQueryResult:
        """自然语言查询知识图谱。

        使用 LLM 将自然语言问题转换为 Cypher 查询，执行后返回结果。

        Parameters
        ----------
        question : str
            自然语言问题，如 "柴胡归哪些经？"

        Returns
        -------
        KGQueryResult
            查询结果。
        """
        if self._llm is None:
            return KGQueryResult(
                query=question,
                error="LLM 网关未配置，无法执行自然语言查询",
            )

        # 构建 Cypher 生成提示词
        system_prompt = (
            "你是一个中医知识图谱查询助手。将用户的自然语言问题转换为 Neo4j Cypher 查询。\n"
            "图谱中的节点类型: Formula(方剂), Herb(中药), Syndrome(证候), "
            "Target(靶点), Pathway(通路), Efficacy(功效)\n"
            "关系类型: CONTAINS(包含), TREATS(治疗), HAS_EFFICACY(有功效), "
            "ASSOCIATED_TARGET(关联靶点), PARTICIPATES_IN(参与通路)\n"
            "所有节点都有 name 属性。\n"
            "只输出 Cypher 查询语句，不要添加其他文字。"
        )

        try:
            cypher = self._llm.generate(question, system_prompt=system_prompt).strip()
            # 清理：移除可能的代码块标记
            cypher = cypher.strip("`").strip()
            if cypher.lower().startswith("cypher"):
                cypher = cypher[6:].strip()

            records = self.query_cypher(cypher)
            return KGQueryResult(
                query=question,
                cypher=cypher,
                records=records,
            )
        except Exception as exc:
            return KGQueryResult(
                query=question,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def find_gaps(self, entity: Optional[str] = None) -> List[KnowledgeGap]:
        """发现知识缺口。

        Parameters
        ----------
        entity : str | None
            焦点实体名称。为 ``None`` 时扫描整个图。

        Returns
        -------
        list[KnowledgeGap]
            知识缺口列表。
        """
        gaps: List[KnowledgeGap] = []

        if self._networkx_graph is None:
            return gaps

        g = self._networkx_graph

        # 查找孤立节点
        for node in g.nodes:
            if entity and node != entity:
                continue
            if g.degree(node) == 0:
                node_type = g.nodes[node].get("entity_type", "unknown")
                gaps.append(KnowledgeGap(
                    gap_type="orphan_entity",
                    entity=node,
                    entity_type=node_type,
                    description=f"实体 '{node}' 无任何关联关系",
                    severity="medium",
                ))

        # 查找缺少下游连接的方剂（应有 TREATS 关系）
        for node, data in g.nodes(data=True):
            if entity and node != entity:
                continue
            ntype = data.get("entity_type", "")
            if ntype == "formula":
                has_treats = any(
                    edata.get("relation_type") == "TREATS"
                    for _, _, edata in g.out_edges(node, data=True)
                )
                if not has_treats:
                    gaps.append(KnowledgeGap(
                        gap_type="missing_downstream",
                        entity=node,
                        entity_type="formula",
                        description=f"方剂 '{node}' 缺少治疗关系 (TREATS)",
                        severity="high",
                    ))

                # 检查是否有组成药材
                has_contains = any(
                    edata.get("relation_type") == "CONTAINS"
                    for _, _, edata in g.out_edges(node, data=True)
                )
                if not has_contains:
                    gaps.append(KnowledgeGap(
                        gap_type="incomplete_composition",
                        entity=node,
                        entity_type="formula",
                        description=f"方剂 '{node}' 缺少组成药材 (CONTAINS)",
                        severity="high",
                    ))

        logger.info("发现 %d 个知识缺口", len(gaps))
        return gaps

    def get_subgraph(self, entity: str, depth: int = 2) -> SubGraphDTO:
        """提取以指定实体为中心的子图。

        Parameters
        ----------
        entity : str
            中心实体名称。
        depth : int
            子图深度（跳数）。

        Returns
        -------
        SubGraphDTO
            子图数据。
        """
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        # 优先从 Neo4j 获取
        if self._neo4j_driver is not None:
            try:
                cypher = (
                    f"MATCH path = (start {{name: $name}})-[*1..{depth}]-(end) "
                    f"RETURN path LIMIT 100"
                )
                records = self.query_cypher(cypher, {"name": entity})
                # 将 Neo4j 路径转换为节点和边
                seen_nodes = set()
                for rec in records:
                    path = rec.get("path")
                    if path and hasattr(path, "nodes"):
                        for n in path.nodes:
                            nid = str(dict(n).get("name", n.id))
                            if nid not in seen_nodes:
                                seen_nodes.add(nid)
                                nodes.append(dict(n))
                        for r in path.relationships:
                            edges.append({
                                "source": str(dict(r.start_node).get("name", r.start_node.id)),
                                "target": str(dict(r.end_node).get("name", r.end_node.id)),
                                "type": r.type,
                            })
                return SubGraphDTO(center_entity=entity, nodes=nodes, edges=edges, depth=depth)
            except Exception as exc:
                logger.warning("Neo4j 子图提取失败，降级到 NetworkX: %s", exc)

        # 降级到 NetworkX
        if self._networkx_graph is not None and entity in self._networkx_graph:
            try:
                # BFS 获取子图
                bfs_nodes = set()
                bfs_nodes.add(entity)
                frontier = {entity}
                for _ in range(depth):
                    next_frontier = set()
                    for node in frontier:
                        for neighbor in self._networkx_graph.neighbors(node):
                            if neighbor not in bfs_nodes:
                                next_frontier.add(neighbor)
                                bfs_nodes.add(neighbor)
                        # 无向邻居
                        for pred in self._networkx_graph.predecessors(node):
                            if pred not in bfs_nodes:
                                next_frontier.add(pred)
                                bfs_nodes.add(pred)
                    frontier = next_frontier

                for node in bfs_nodes:
                    ndata = dict(self._networkx_graph.nodes[node])
                    ndata["name"] = node
                    nodes.append(ndata)

                for u, v, edata in self._networkx_graph.edges(data=True):
                    if u in bfs_nodes and v in bfs_nodes:
                        edges.append({
                            "source": u,
                            "target": v,
                            "type": edata.get("relation_type", "RELATES_TO"),
                        })
            except Exception as exc:
                logger.warning("NetworkX 子图提取失败: %s", exc)

        return SubGraphDTO(center_entity=entity, nodes=nodes, edges=edges, depth=depth)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_formula_composition(self, formula_name: str) -> Dict[str, List[str]]:
        """查询方剂组成。

        Returns
        -------
        dict
            ``{"sovereign": [...], "minister": [...], "assistant": [...], "envoy": [...]}``
        """
        if self._neo4j_driver is not None:
            try:
                return self._neo4j_driver.find_formula_composition(formula_name)
            except Exception as exc:
                logger.warning("Neo4j 方剂查询失败: %s", exc)

        # 降级到 NetworkX
        result: Dict[str, List[str]] = {}
        if self._networkx_graph is not None and formula_name in self._networkx_graph:
            for _, target, edata in self._networkx_graph.out_edges(formula_name, data=True):
                rel_type = edata.get("relation_type", "CONTAINS")
                role = edata.get("role", rel_type.lower())
                result.setdefault(role, []).append(target)
        return result

    def get_statistics(self) -> Dict[str, Any]:
        """获取知识图谱统计信息。"""
        stats: Dict[str, Any] = {}

        if self._networkx_graph is not None:
            stats["memory_graph"] = {
                "nodes": self._networkx_graph.number_of_nodes(),
                "edges": self._networkx_graph.number_of_edges(),
            }

        if self._neo4j_driver is not None:
            try:
                stats["neo4j"] = self._neo4j_driver.get_graph_statistics()
            except Exception:
                stats["neo4j"] = {"status": "error"}

        return stats
