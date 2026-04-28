"""
TCM 四级知识图谱：方剂 → 证候 → 靶点 → 通路

基于 NetworkX MultiDiGraph 内存图 + SQLite 持久化。
IKnowledgeGraph / KnowledgeGap 从 src.storage.graph_interface 导入，
保持向后兼容的本地名称。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import networkx as nx

from src.semantic_modeling.tcm_relationships import TCMRelationshipDefinitions
from src.storage.graph_interface import (
    ENTITY_TYPES,
    FOUR_LEVELS,
    LEVEL_RELATION_TYPES,
    IKnowledgeGraph,
    KnowledgeGap,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLite 持久化层
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    name     TEXT PRIMARY KEY,
    type     TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS relations (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    src      TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    dst      TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(src, rel_type, dst)
);
CREATE INDEX IF NOT EXISTS idx_rel_src ON relations(src);
CREATE INDEX IF NOT EXISTS idx_rel_dst ON relations(dst);
"""


class _SQLiteBackend:
    """薄封装：SQLite 读写。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        try:
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    # -- 写 --

    def upsert_entity(self, name: str, entity_type: str,
                      metadata: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO entities(name, type, metadata) VALUES(?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET type=excluded.type, metadata=excluded.metadata",
            (name, entity_type, json.dumps(metadata, ensure_ascii=False)),
        )
        conn.commit()

    def upsert_relation(self, src: str, rel_type: str, dst: str,
                        metadata: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO relations(src, rel_type, dst, metadata) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(src, rel_type, dst) DO UPDATE SET metadata=excluded.metadata",
            (src, rel_type, dst, json.dumps(metadata, ensure_ascii=False)),
        )
        conn.commit()

    # -- 批量写 --

    def bulk_upsert_entities(self, rows: Sequence[Tuple[str, str, Dict]]) -> None:
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO entities(name, type, metadata) VALUES(?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET type=excluded.type, metadata=excluded.metadata",
            [(n, t, json.dumps(m, ensure_ascii=False)) for n, t, m in rows],
        )
        conn.commit()

    def bulk_upsert_relations(self, rows: Sequence[Tuple[str, str, str, Dict]]) -> None:
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO relations(src, rel_type, dst, metadata) VALUES(?, ?, ?, ?)"
            " ON CONFLICT(src, rel_type, dst) DO UPDATE SET metadata=excluded.metadata",
            [(s, r, d, json.dumps(m, ensure_ascii=False)) for s, r, d, m in rows],
        )
        conn.commit()

    # -- 读 --

    def load_all_entities(self) -> List[Tuple[str, str, Dict]]:
        cur = self._get_conn().execute("SELECT name, type, metadata FROM entities")
        return [(r[0], r[1], json.loads(r[2])) for r in cur.fetchall()]

    def load_all_relations(self) -> List[Tuple[str, str, str, Dict]]:
        cur = self._get_conn().execute("SELECT src, rel_type, dst, metadata FROM relations")
        return [(r[0], r[1], r[2], json.loads(r[3])) for r in cur.fetchall()]

    def entity_count(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM entities").fetchone()[0]

    def relation_count(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM relations").fetchone()[0]

    # -- 生命周期 --

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            return
        try:
            conn.close()
        finally:
            self._local.conn = None


# ---------------------------------------------------------------------------
# 核心实现
# ---------------------------------------------------------------------------

class TCMKnowledgeGraph(IKnowledgeGraph):
    """
    基于 NetworkX + SQLite 的 TCM 四级知识图谱。

    四级层次: 方剂(formula) → 证候(syndrome) → 靶点(target) → 通路(pathway)

    Parameters
    ----------
    db_path : str | Path | None
        SQLite 文件路径。None 表示纯内存模式（不做持久化）。
    preload_formulas : bool
        初始化时是否预加载 TCMRelationshipDefinitions.FORMULA_COMPOSITIONS。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        preload_formulas: bool = True,
    ) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._db: Optional[_SQLiteBackend] = None
        if db_path is not None:
            self._db = _SQLiteBackend(db_path)
            self._load_from_db()

        if preload_formulas:
            self._preload_formula_compositions()

    # ------------------------------------------------------------------
    # IKnowledgeGraph 接口实现
    # ------------------------------------------------------------------

    def add_entity(self, entity: Dict[str, Any]) -> None:
        """添加实体节点。

        entity 至少包含 ``name`` 和 ``type`` 两个键。
        """
        name = entity["name"]
        etype = entity.get("type", "generic")
        metadata = {k: v for k, v in entity.items() if k not in ("name", "type")}
        self._graph.add_node(name, type=etype, **metadata)
        if self._db:
            self._db.upsert_entity(name, etype, metadata)

    def add_relation(
        self,
        src: str,
        rel_type: str,
        dst: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加关系边。如果端点不存在则自动创建。"""
        metadata = metadata or {}
        # 自动补节点
        if src not in self._graph:
            self._graph.add_node(src, type="generic")
            if self._db:
                self._db.upsert_entity(src, "generic", {})
        if dst not in self._graph:
            self._graph.add_node(dst, type="generic")
            if self._db:
                self._db.upsert_entity(dst, "generic", {})
        self._graph.add_edge(src, dst, rel_type=rel_type, **metadata)
        if self._db:
            self._db.upsert_relation(src, rel_type, dst, metadata)

    def query_path(self, src: str, dst: str) -> List[List[str]]:
        """查询两节点间所有简单路径（默认最大深度 8）。"""
        if src not in self._graph or dst not in self._graph:
            return []
        try:
            return list(nx.all_simple_paths(self._graph, src, dst, cutoff=8))
        except nx.NetworkXError:
            return []

    def find_gaps(self) -> List[KnowledgeGap]:
        """识别知识缺口。

        三大类:
        1. orphan_entity — 孤立节点（无入边也无出边）
        2. missing_downstream — 四级节点缺少下游连接
        3. incomplete_composition — 方剂缺少君/臣/佐/使角色
        """
        gaps: List[KnowledgeGap] = []
        self._find_orphan_gaps(gaps)
        self._find_missing_downstream_gaps(gaps)
        self._find_incomplete_composition_gaps(gaps)
        return gaps

    def get_subgraph(self, entity: str, depth: int = 2) -> nx.DiGraph:
        """以 *entity* 为中心提取 BFS 子图。"""
        if entity not in self._graph:
            return nx.DiGraph()
        visited: Set[str] = set()
        frontier: Set[str] = {entity}
        for _ in range(depth):
            next_frontier: Set[str] = set()
            for n in frontier:
                if n in visited:
                    continue
                visited.add(n)
                next_frontier.update(self._graph.successors(n))
                next_frontier.update(self._graph.predecessors(n))
            frontier = next_frontier - visited
        visited.update(frontier)
        return nx.DiGraph(self._graph.subgraph(visited))

    # ------------------------------------------------------------------
    # 便捷查询
    # ------------------------------------------------------------------

    @property
    def entity_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def relation_count(self) -> int:
        return self._graph.number_of_edges()

    def entities_by_type(self, entity_type: str) -> List[str]:
        return [n for n, d in self._graph.nodes(data=True) if d.get("type") == entity_type]

    def neighbors(self, entity: str, rel_type: Optional[str] = None) -> List[str]:
        if entity not in self._graph:
            return []
        result = []
        for _, dst, data in self._graph.out_edges(entity, data=True):
            if rel_type is None or data.get("rel_type") == rel_type:
                result.append(dst)
        return result

    # ------------------------------------------------------------------
    # 批量导入
    # ------------------------------------------------------------------

    def bulk_add_entities(self, entities: Sequence[Dict[str, Any]]) -> int:
        rows = []
        for ent in entities:
            name = ent["name"]
            etype = ent.get("type", "generic")
            meta = {k: v for k, v in ent.items() if k not in ("name", "type")}
            self._graph.add_node(name, type=etype, **meta)
            rows.append((name, etype, meta))
        if self._db and rows:
            self._db.bulk_upsert_entities(rows)
        return len(rows)

    def bulk_add_relations(
        self, relations: Sequence[Tuple[str, str, str, Optional[Dict[str, Any]]]]
    ) -> int:
        """批量添加关系。每条: (src, rel_type, dst, metadata|None)。"""
        db_rows = []
        for src, rel_type, dst, meta in relations:
            meta = meta or {}
            if src not in self._graph:
                self._graph.add_node(src, type="generic")
            if dst not in self._graph:
                self._graph.add_node(dst, type="generic")
            self._graph.add_edge(src, dst, rel_type=rel_type, **meta)
            db_rows.append((src, rel_type, dst, meta))
        if self._db and db_rows:
            self._db.bulk_upsert_relations(db_rows)
        return len(db_rows)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self) -> None:
        """将内存图完整写入 SQLite（覆盖式同步）。"""
        if self._db is None:
            return
        entity_rows = []
        for n, d in self._graph.nodes(data=True):
            etype = d.get("type", "generic")
            meta = {k: v for k, v in d.items() if k != "type"}
            entity_rows.append((n, etype, meta))
        self._db.bulk_upsert_entities(entity_rows)

        rel_rows = []
        for u, v, d in self._graph.edges(data=True):
            rt = d.get("rel_type", "unknown")
            meta = {k: v_ for k, v_ in d.items() if k != "rel_type"}
            rel_rows.append((u, rt, v, meta))
        self._db.bulk_upsert_relations(rel_rows)

    def close(self) -> None:
        if self._db:
            self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _load_from_db(self) -> None:
        assert self._db is not None
        for name, etype, meta in self._db.load_all_entities():
            self._graph.add_node(name, type=etype, **meta)
        for src, rel_type, dst, meta in self._db.load_all_relations():
            self._graph.add_edge(src, dst, rel_type=rel_type, **meta)

    def _preload_formula_compositions(self) -> None:
        """从 TCMRelationshipDefinitions 预加载方剂组成。"""
        compositions = TCMRelationshipDefinitions.FORMULA_COMPOSITIONS
        for formula_name, roles in compositions.items():
            self._graph.add_node(formula_name, type="formula")
            for role, herbs in roles.items():
                for herb in herbs:
                    self._graph.add_node(herb, type="herb")
                    self._graph.add_edge(
                        formula_name, herb, rel_type=role,
                    )
        # 同时加载功效关系
        for herb, effs in TCMRelationshipDefinitions.HERB_EFFICACY_MAP.items():
            if herb not in self._graph:
                self._graph.add_node(herb, type="herb")
            for eff in effs:
                if eff not in self._graph:
                    self._graph.add_node(eff, type="efficacy")
                self._graph.add_edge(herb, eff, rel_type="efficacy")

    # -- gap finders --

    def _find_orphan_gaps(self, gaps: List[KnowledgeGap]) -> None:
        for node in self._graph.nodes():
            if self._graph.degree(node) == 0:
                ntype = self._graph.nodes[node].get("type", "generic")
                gaps.append(KnowledgeGap(
                    gap_type="orphan_entity",
                    entity=node,
                    entity_type=ntype,
                    description=f"实体 '{node}' 没有任何关系连接",
                    severity="medium",
                ))

    def _find_missing_downstream_gaps(self, gaps: List[KnowledgeGap]) -> None:
        """四级中某级节点缺少到下一级的连接。"""
        level_pairs = [
            ("formula", "syndrome", "treats"),
            ("syndrome", "target", "associated_target"),
            ("target", "pathway", "participates_in"),
        ]
        for src_type, dst_type, expected_rel in level_pairs:
            for node, data in self._graph.nodes(data=True):
                if data.get("type") != src_type:
                    continue
                has_downstream = any(
                    self._graph.nodes.get(dst, {}).get("type") == dst_type
                    for dst in self._graph.successors(node)
                )
                if not has_downstream:
                    gaps.append(KnowledgeGap(
                        gap_type="missing_downstream",
                        entity=node,
                        entity_type=src_type,
                        description=(
                            f"{src_type} '{node}' 缺少到 {dst_type} 层级的 "
                            f"'{expected_rel}' 关系"
                        ),
                        severity="high",
                    ))

    def _find_incomplete_composition_gaps(self, gaps: List[KnowledgeGap]) -> None:
        """方剂缺少某种君臣佐使角色。"""
        required_roles = {"sovereign", "minister", "assistant", "envoy"}
        for node, data in self._graph.nodes(data=True):
            if data.get("type") != "formula":
                continue
            present_roles: Set[str] = set()
            for _, _, edata in self._graph.out_edges(node, data=True):
                rt = edata.get("rel_type", "")
                if rt in required_roles:
                    present_roles.add(rt)
            missing = required_roles - present_roles
            if missing:
                gaps.append(KnowledgeGap(
                    gap_type="incomplete_composition",
                    entity=node,
                    entity_type="formula",
                    description=(
                        f"方剂 '{node}' 缺少角色: {', '.join(sorted(missing))}"
                    ),
                    severity="low" if len(missing) == 1 else "medium",
                ))
