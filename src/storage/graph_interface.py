"""
知识图谱统一接口与数据结构。

将 IKnowledgeGraph / KnowledgeGap 从 knowledge 层提取到 storage 层，
作为 Neo4j 后端与 NetworkX 后端的共同契约，避免循环引用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ENTITY_TYPES: Set[str] = {
    "formula",    # 方剂
    "herb",       # 中药
    "syndrome",   # 证候
    "target",     # 靶点
    "pathway",    # 通路
    "efficacy",   # 功效
}

FOUR_LEVELS: Tuple[str, ...] = ("formula", "syndrome", "target", "pathway")

LEVEL_RELATION_TYPES: Dict[Tuple[str, str], str] = {
    ("formula", "syndrome"): "treats",
    ("syndrome", "target"): "associated_target",
    ("target", "pathway"): "participates_in",
}

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeGap:
    """一条知识缺口记录。"""

    gap_type: str       # orphan_entity | missing_downstream | incomplete_composition
    entity: str
    entity_type: str
    description: str
    severity: str       # high | medium | low


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


class IKnowledgeGraph(ABC):
    """知识图谱统一接口。

    所有后端（Neo4j / NetworkX）均需实现此接口。
    ``get_subgraph`` 返回 ``networkx.DiGraph`` 以兼容现有可视化 / 分析代码。
    """

    @abstractmethod
    def add_entity(self, entity: Dict[str, Any]) -> None: ...

    @abstractmethod
    def add_relation(
        self,
        src: str,
        rel_type: str,
        dst: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    @abstractmethod
    def query_path(self, src: str, dst: str) -> List[List[str]]: ...

    @abstractmethod
    def find_gaps(self) -> List[KnowledgeGap]: ...

    @abstractmethod
    def get_subgraph(self, entity: str, depth: int = 2) -> Any:
        """返回以 *entity* 为中心的子图。

        返回值类型为 ``networkx.DiGraph``（若可用）或等效结构。
        """
        ...
