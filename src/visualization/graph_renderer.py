# -*- coding: utf-8 -*-
"""知识图谱渲染器 — 将 NetworkX 图转换为前端可视化 JSON 格式。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 默认样式配置
# ---------------------------------------------------------------------------

_CATEGORY_COLORS: Dict[str, str] = {
    "herb": "#67C23A",        # 中药 — 绿
    "formula": "#E6A23C",     # 方剂 — 橙
    "symptom": "#F56C6C",     # 症状 — 红
    "disease": "#909399",     # 疾病 — 灰
    "meridian": "#409EFF",    # 经络 — 蓝
    "property": "#8B5CF6",    # 药性 — 紫
    "default": "#409EFF",
}

_DEFAULT_NODE_SIZE = 30
_HIGHLIGHT_COLOR = "#FF4500"
_HIGHLIGHT_WIDTH = 4


class KnowledgeGraphRenderer:
    """将 NetworkX 知识图谱转换为前端可视化 JSON。

    支持两种输出格式：
    - ECharts force-layout（百度 ECharts）
    - Cytoscape.js（Cytoscape 生态）
    """

    def __init__(
        self,
        category_colors: Optional[Dict[str, str]] = None,
        default_node_size: int = _DEFAULT_NODE_SIZE,
    ) -> None:
        self.category_colors = {**_CATEGORY_COLORS, **(category_colors or {})}
        self.default_node_size = default_node_size

    # ------------------------------------------------------------------
    # ECharts
    # ------------------------------------------------------------------

    def render_to_echarts_json(self, graph: nx.Graph) -> Dict[str, Any]:
        """将 NetworkX 图转换为 ECharts force-layout JSON。

        返回结构::

            {
                "nodes": [{"id", "name", "category", "symbolSize", "itemStyle", "value", ...}],
                "edges": [{"source", "target", "label", "lineStyle", ...}],
                "categories": [{"name", "itemStyle"}],
            }
        """
        if graph is None or graph.number_of_nodes() == 0:
            return {"nodes": [], "edges": [], "categories": []}

        # 收集所有分类
        categories_set: Set[str] = set()
        for _, data in graph.nodes(data=True):
            categories_set.add(self._node_category(data))
        categories_list = sorted(categories_set)
        cat_index = {c: i for i, c in enumerate(categories_list)}

        # 节点
        nodes: List[Dict[str, Any]] = []
        for node_id, data in graph.nodes(data=True):
            cat = self._node_category(data)
            degree = graph.degree(node_id)
            size = self.default_node_size + min(degree * 3, 40)
            nodes.append({
                "id": str(node_id),
                "name": data.get("label", data.get("name", str(node_id))),
                "category": cat_index[cat],
                "symbolSize": size,
                "value": degree,
                "itemStyle": {"color": self.category_colors.get(cat, self.category_colors["default"])},
                **({"extra": {k: v for k, v in data.items() if k not in ("label", "name", "type", "category")}} if data else {}),
            })

        # 边
        edges: List[Dict[str, Any]] = []
        for u, v, data in graph.edges(data=True):
            edge: Dict[str, Any] = {
                "source": str(u),
                "target": str(v),
            }
            label = data.get("label", data.get("relation", data.get("type", "")))
            if label:
                edge["label"] = {"show": True, "formatter": str(label)}
            weight = data.get("weight")
            if weight is not None:
                edge["lineStyle"] = {"width": max(1, min(float(weight) * 2, 8))}
            edges.append(edge)

        # 分类
        categories = [
            {"name": c, "itemStyle": {"color": self.category_colors.get(c, self.category_colors["default"])}}
            for c in categories_list
        ]

        return {"nodes": nodes, "edges": edges, "categories": categories}

    # ------------------------------------------------------------------
    # Cytoscape.js
    # ------------------------------------------------------------------

    def render_to_cytoscape_json(self, graph: nx.Graph) -> Dict[str, Any]:
        """将 NetworkX 图转换为 Cytoscape.js 兼容 JSON。

        返回结构::

            {
                "elements": {
                    "nodes": [{"data": {"id", "label", "category", "degree", ...}}],
                    "edges": [{"data": {"id", "source", "target", "label", "weight", ...}}],
                },
                "style": [...],
            }
        """
        if graph is None or graph.number_of_nodes() == 0:
            return {"elements": {"nodes": [], "edges": []}, "style": []}

        # 节点
        cy_nodes: List[Dict[str, Any]] = []
        for node_id, data in graph.nodes(data=True):
            cat = self._node_category(data)
            cy_nodes.append({
                "data": {
                    "id": str(node_id),
                    "label": data.get("label", data.get("name", str(node_id))),
                    "category": cat,
                    "degree": graph.degree(node_id),
                    "color": self.category_colors.get(cat, self.category_colors["default"]),
                },
            })

        # 边
        cy_edges: List[Dict[str, Any]] = []
        for idx, (u, v, data) in enumerate(graph.edges(data=True)):
            edge_data: Dict[str, Any] = {
                "id": f"e{idx}",
                "source": str(u),
                "target": str(v),
            }
            label = data.get("label", data.get("relation", data.get("type", "")))
            if label:
                edge_data["label"] = str(label)
            weight = data.get("weight")
            if weight is not None:
                edge_data["weight"] = float(weight)
            cy_edges.append({"data": edge_data})

        # 默认样式
        style = self._cytoscape_default_style()

        return {"elements": {"nodes": cy_nodes, "edges": cy_edges}, "style": style}

    # ------------------------------------------------------------------
    # 路径高亮
    # ------------------------------------------------------------------

    def highlight_path(
        self,
        graph: nx.Graph,
        source: str,
        target: str,
        format: str = "echarts",
    ) -> Dict[str, Any]:
        """高亮 source → target 的最短路径，返回完整图 JSON 并标记路径节点/边。

        Parameters
        ----------
        graph : nx.Graph
        source, target : str
            起点和终点节点 ID。
        format : str
            ``"echarts"`` 或 ``"cytoscape"``。

        Returns
        -------
        dict
            带有 ``path`` 字段的渲染 JSON；路径上的节点/边已添加高亮样式。
        """
        path_nodes: List[str] = []
        path_edges: List[Tuple[str, str]] = []

        try:
            raw_path: List = nx.shortest_path(graph, source=source, target=target)
            path_nodes = [str(n) for n in raw_path]
            path_edges = [(str(raw_path[i]), str(raw_path[i + 1])) for i in range(len(raw_path) - 1)]
        except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
            logger.warning("无法找到路径 %s → %s: %s", source, target, exc)

        path_set = set(path_nodes)
        edge_set = {(u, v) for u, v in path_edges} | {(v, u) for u, v in path_edges}

        if format == "cytoscape":
            result = self.render_to_cytoscape_json(graph)
            for node in result["elements"]["nodes"]:
                if node["data"]["id"] in path_set:
                    node["data"]["highlighted"] = True
                    node["data"]["color"] = _HIGHLIGHT_COLOR
            for edge in result["elements"]["edges"]:
                key = (edge["data"]["source"], edge["data"]["target"])
                if key in edge_set:
                    edge["data"]["highlighted"] = True
                    edge["data"]["color"] = _HIGHLIGHT_COLOR
        else:
            result = self.render_to_echarts_json(graph)
            for node in result["nodes"]:
                if node["id"] in path_set:
                    node["itemStyle"] = {"color": _HIGHLIGHT_COLOR, "borderWidth": 3, "borderColor": "#FFD700"}
                    node["symbolSize"] = node.get("symbolSize", self.default_node_size) + 10
            for edge in result["edges"]:
                key = (edge["source"], edge["target"])
                if key in edge_set:
                    edge["lineStyle"] = {"color": _HIGHLIGHT_COLOR, "width": _HIGHLIGHT_WIDTH}

        result["path"] = {"nodes": path_nodes, "edges": path_edges, "found": len(path_nodes) > 0}
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _node_category(data: Dict[str, Any]) -> str:
        """从节点属性中提取分类名称。"""
        for key in ("category", "type", "node_type"):
            val = data.get(key)
            if val:
                return str(val).lower()
        return "default"

    @staticmethod
    def _cytoscape_default_style() -> List[Dict[str, Any]]:
        """返回 Cytoscape.js 默认样式数组。"""
        return [
            {
                "selector": "node",
                "style": {
                    "background-color": "data(color)",
                    "label": "data(label)",
                    "font-size": "12px",
                    "text-valign": "bottom",
                    "text-halign": "center",
                },
            },
            {
                "selector": "edge",
                "style": {
                    "width": 2,
                    "line-color": "#ccc",
                    "target-arrow-color": "#ccc",
                    "target-arrow-shape": "triangle",
                    "curve-style": "bezier",
                    "label": "data(label)",
                    "font-size": "10px",
                },
            },
            {
                "selector": "[?highlighted]",
                "style": {
                    "background-color": _HIGHLIGHT_COLOR,
                    "line-color": _HIGHLIGHT_COLOR,
                    "target-arrow-color": _HIGHLIGHT_COLOR,
                    "width": _HIGHLIGHT_WIDTH,
                },
            },
        ]
