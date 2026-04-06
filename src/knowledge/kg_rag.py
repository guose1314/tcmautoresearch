# -*- coding: utf-8 -*-
"""KG-RAG 服务：对话前自动从知识图谱检索相关子图，注入提示上下文。

流程：
1. 从用户查询中提取 TCM 实体（方剂 / 中药 / 证候）
2. 对每个识别实体，查询知识图谱子图 + 专项关系
3. 可选：通过向量检索补充语义相似项
4. 将检索到的知识格式化为结构化上下文字符串
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from src.storage.graph_interface import IKnowledgeGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 实体名称静态词典（从 TCMRelationshipDefinitions 懒加载）
# ---------------------------------------------------------------------------

_KNOWN_FORMULAS: Optional[Set[str]] = None
_KNOWN_HERBS: Optional[Set[str]] = None
_KNOWN_EFFICACIES: Optional[Set[str]] = None


def _load_known_entities() -> None:
    """从 TCMRelationshipDefinitions 一次性加载已知实体名称。"""
    global _KNOWN_FORMULAS, _KNOWN_HERBS, _KNOWN_EFFICACIES
    if _KNOWN_FORMULAS is not None:
        return
    try:
        from src.semantic_modeling.tcm_relationships import (
            TCMRelationshipDefinitions as Defs,
        )
        _KNOWN_FORMULAS = set(Defs.FORMULA_COMPOSITIONS.keys())
        _KNOWN_HERBS = set(Defs.HERB_EFFICACY_MAP.keys())

        effs: Set[str] = set()
        for eff_list in Defs.HERB_EFFICACY_MAP.values():
            effs.update(eff_list)
        _KNOWN_EFFICACIES = effs
    except ImportError:
        _KNOWN_FORMULAS = set()
        _KNOWN_HERBS = set()
        _KNOWN_EFFICACIES = set()
        logger.debug("TCMRelationshipDefinitions 不可用，实体词典为空")


# ---------------------------------------------------------------------------
# 核心服务
# ---------------------------------------------------------------------------


class KGRAGContext:
    """封装一次检索产出的知识上下文。"""

    __slots__ = ("entities_found", "graph_facts", "similar_items")

    def __init__(self) -> None:
        self.entities_found: List[Dict[str, str]] = []   # [{name, type}]
        self.graph_facts: List[str] = []                  # 自然语言事实
        self.similar_items: List[Dict[str, Any]] = []     # 向量近邻

    @property
    def empty(self) -> bool:
        return not self.graph_facts and not self.similar_items

    def format(self) -> str:
        """将上下文格式化为可直接注入 prompt 的文本块。"""
        if self.empty:
            return ""
        parts: List[str] = []

        if self.entities_found:
            names = ", ".join(f"{e['name']}({e['type']})" for e in self.entities_found)
            parts.append(f"识别到的实体：{names}")

        if self.graph_facts:
            parts.append("知识图谱事实：")
            for fact in self.graph_facts:
                parts.append(f"  - {fact}")

        if self.similar_items:
            parts.append("语义相似项：")
            for item in self.similar_items[:5]:
                score = item.get("score", "")
                score_str = f" (相似度 {score:.2f})" if isinstance(score, (int, float)) else ""
                parts.append(f"  - {item.get('text', item.get('name', ''))}{score_str}")

        return "\n".join(parts)


class KGRAGService:
    """知识图谱增强检索（KG-RAG）服务。

    Parameters
    ----------
    knowledge_graph : IKnowledgeGraph | None
        知识图谱后端（Neo4j 或 NetworkX）。
    embedding_service : object | None
        ``EmbeddingService`` 实例，可选；用于语义相似项检索。
    subgraph_depth : int
        get_subgraph 的 BFS 深度，默认 2。
    max_facts : int
        单次检索返回的最大事实条数。
    embedding_top_k : int
        向量检索返回前 k 个结果。
    embedding_min_score : float
        向量检索最低分数阈值。
    """

    def __init__(
        self,
        knowledge_graph: Optional[IKnowledgeGraph] = None,
        embedding_service: Optional[Any] = None,
        *,
        subgraph_depth: int = 2,
        max_facts: int = 20,
        embedding_top_k: int = 5,
        embedding_min_score: float = 0.3,
    ) -> None:
        self._kg = knowledge_graph
        self._emb = embedding_service
        self._depth = subgraph_depth
        self._max_facts = max_facts
        self._emb_top_k = embedding_top_k
        self._emb_min_score = embedding_min_score

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def retrieve(self, query: str) -> KGRAGContext:
        """根据用户查询检索知识上下文。

        Parameters
        ----------
        query : str
            用户输入的自然语言查询。

        Returns
        -------
        KGRAGContext
            包含图谱事实与语义相似项的上下文对象。
        """
        ctx = KGRAGContext()
        if not query or not query.strip():
            return ctx

        # 1. 实体抽取
        entities = self.extract_entities(query)
        ctx.entities_found = entities

        # 2. 图谱检索
        if self._kg is not None and entities:
            self._retrieve_graph_facts(entities, ctx)

        # 3. 向量语义检索（补充）
        if self._emb is not None:
            self._retrieve_similar_items(query, ctx)

        return ctx

    # ------------------------------------------------------------------
    # 实体抽取
    # ------------------------------------------------------------------

    def extract_entities(self, query: str) -> List[Dict[str, str]]:
        """从查询文本中抽取 TCM 实体（基于词典匹配）。

        Returns
        -------
        list[dict]
            ``[{"name": "四君子汤", "type": "formula"}, ...]``
        """
        _load_known_entities()
        assert _KNOWN_FORMULAS is not None
        assert _KNOWN_HERBS is not None
        assert _KNOWN_EFFICACIES is not None

        found: List[Dict[str, str]] = []
        seen: Set[str] = set()

        for name in _KNOWN_FORMULAS:
            if name in query and name not in seen:
                found.append({"name": name, "type": "formula"})
                seen.add(name)

        for name in _KNOWN_HERBS:
            if name in query and name not in seen:
                found.append({"name": name, "type": "herb"})
                seen.add(name)

        for name in _KNOWN_EFFICACIES:
            if name in query and name not in seen:
                found.append({"name": name, "type": "efficacy"})
                seen.add(name)

        return found

    # ------------------------------------------------------------------
    # 图谱检索内部方法
    # ------------------------------------------------------------------

    def _retrieve_graph_facts(
        self, entities: List[Dict[str, str]], ctx: KGRAGContext
    ) -> None:
        """从知识图谱检索与实体相关的事实。"""
        assert self._kg is not None
        facts: List[str] = []

        for ent in entities:
            name = ent["name"]
            etype = ent["type"]

            # 子图邻居
            try:
                subgraph = self._kg.get_subgraph(name, depth=self._depth)
                if subgraph is not None:
                    self._extract_subgraph_facts(name, etype, subgraph, facts)
            except Exception as exc:
                logger.debug("get_subgraph(%s) 失败: %s", name, exc)

            # 方剂专用：组成与主治
            if etype == "formula":
                self._retrieve_formula_details(name, facts)

            # 中药专用：功效
            if etype == "herb":
                self._retrieve_herb_efficacies(name, facts)

            if len(facts) >= self._max_facts:
                break

        ctx.graph_facts = facts[: self._max_facts]

    def _extract_subgraph_facts(
        self, entity: str, etype: str, subgraph: Any, facts: List[str]
    ) -> None:
        """从 networkx.DiGraph 子图提取自然语言事实。"""
        try:
            for src, dst, data in subgraph.edges(data=True):
                rel = data.get("rel_type", data.get("relationship_type", "相关"))
                facts.append(f"{src} —[{rel}]→ {dst}")
                if len(facts) >= self._max_facts:
                    return
        except Exception:
            pass

    def _retrieve_formula_details(self, formula_name: str, facts: List[str]) -> None:
        """补充方剂的君臣佐使组成。"""
        try:
            from src.semantic_modeling.tcm_relationships import (
                TCMRelationshipDefinitions as Defs,
            )
            comp = Defs.get_formula_composition(formula_name)
            if comp:
                role_names = {"sovereign": "君", "minister": "臣", "assistant": "佐", "envoy": "使"}
                parts = []
                for role, herbs in comp.items():
                    if herbs:
                        label = role_names.get(role, role)
                        parts.append(f"{label}药: {', '.join(herbs)}")
                if parts:
                    facts.append(f"{formula_name} 组成 — {'; '.join(parts)}")
        except ImportError:
            pass

        # 尝试通过 KG 接口查询邻居中的 Syndrome
        try:
            neighbors = self._kg.neighbors(formula_name, rel_type="TREATS")  # type: ignore[union-attr]
            if neighbors:
                facts.append(f"{formula_name} 治疗: {', '.join(neighbors[:5])}")
        except Exception:
            pass

    def _retrieve_herb_efficacies(self, herb_name: str, facts: List[str]) -> None:
        """补充中药功效。"""
        try:
            from src.semantic_modeling.tcm_relationships import (
                TCMRelationshipDefinitions as Defs,
            )
            effs = Defs.get_herb_efficacy(herb_name)
            if effs:
                facts.append(f"{herb_name} 功效: {', '.join(effs)}")
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # 向量检索内部方法
    # ------------------------------------------------------------------

    def _retrieve_similar_items(self, query: str, ctx: KGRAGContext) -> None:
        """通过 EmbeddingService 语义检索补充相似项。"""
        try:
            results = self._emb.search(
                query=query,
                top_k=self._emb_top_k,
                min_score=self._emb_min_score,
            )
            for r in results:
                ctx.similar_items.append({
                    "name": r.item_id,
                    "text": r.text,
                    "type": r.item_type,
                    "score": r.score,
                })
        except Exception as exc:
            logger.debug("向量检索失败: %s", exc)
