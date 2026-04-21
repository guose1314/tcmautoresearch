# src/analysis/reasoning_engine.py  (migrated from src/reasoning/reasoning_engine.py)
"""
推理引擎模块 - 基于知识图谱（KG）路径的真实推理

替换原有桩实现，核心能力：
  1. 从 SemanticGraphBuilder 序列化输出重建 networkx 有向图
  2. 君臣佐使组成角色分析（composition_analysis）
  3. 多跳 KG 路径查找（kg_paths）
  4. 预定义关系链模式推理（inference_chains）
  5. Hub 节点（高中心性）检测（hub_nodes）
  6. KG 覆盖率统计（coverage_stats）

输出字段向后兼容：
  reasoning_results  —— entity_relationships / knowledge_patterns / inference_confidence
  temporal_analysis  —— time_periods / temporal_patterns
  pattern_recognition —— common_patterns / prediction
新增字段：
  kg_paths / inference_chains / composition_analysis / hub_nodes / coverage_stats
"""
import collections
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Dict, List, Set, Tuple

nx = import_module("networkx")

from src.core.module_base import BaseModule
from src.semantic_modeling.tcm_relationships import RelationshipType

# 君臣佐使角色权重（用于路径置信度加权）
_ROLE_WEIGHTS: Dict[str, float] = {
    RelationshipType.SOVEREIGN.value:  1.00,
    RelationshipType.MINISTER.value:   0.85,
    RelationshipType.ASSISTANT.value:  0.70,
    RelationshipType.ENVOY.value:      0.55,
    RelationshipType.EFFICACY.value:   0.90,
    RelationshipType.TREATS.value:     0.75,
    RelationshipType.AUGMENTS.value:   0.65,
    RelationshipType.COUNTERS.value:   0.60,
    RelationshipType.COMBINES_WITH.value: 0.50,
}
_DEFAULT_ROLE_WEIGHT = 0.50

# 预定义推理链模式（关系序列）
_INFERENCE_CHAIN_PATTERNS: List[List[str]] = [
    [RelationshipType.SOVEREIGN.value, RelationshipType.EFFICACY.value],
    [RelationshipType.MINISTER.value,  RelationshipType.EFFICACY.value],
    [RelationshipType.SOVEREIGN.value, RelationshipType.TREATS.value],
    [RelationshipType.MINISTER.value,  RelationshipType.TREATS.value],
    [RelationshipType.SOVEREIGN.value, RelationshipType.EFFICACY.value, RelationshipType.TREATS.value],
]


@dataclass
class _ChainTraversalState:
    formula_name: str
    pattern: List[str]
    path: List[str]
    rel_path: List[str]
    results: List[Dict[str, Any]]


class ReasoningEngine(BaseModule):
    """
    推理引擎 — 基于 KG 路径的真实推理

    接受 _do_execute() context 格式::

        {
          "entities": [{"name": str, "type": str, "confidence": float, ...}, ...],
          "semantic_graph": {            # SemanticGraphBuilder 输出
              "nodes": [{"id": str, "data": {...}}, ...],
              "edges": [{"source": str, "target": str, "attributes": {...}}, ...]
          }
        }
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("reasoning_engine", config)
        cfg = config or {}
        self._max_path_len: int = cfg.get("max_path_len", 4)
        self._max_pairs: int = cfg.get("max_pairs", 30)
        self._top_k_hubs: int = cfg.get("top_k_hubs", 10)

    # ------------------------------------------------------------------
    # BaseModule 生命周期
    # ------------------------------------------------------------------

    def _do_initialize(self) -> bool:
        try:
            self.logger.info("推理引擎初始化完成（KG 路径模式）")
            return True
        except Exception as exc:
            self.logger.error("推理引擎初始化失败: %s", exc)
            return False

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            entities: List[Dict] = context.get("entities", [])
            graph_data: Dict = context.get("semantic_graph", {})

            # 1. 重建 networkx 有向图
            kg = self._rebuild_graph(graph_data)

            # 2. 核心推理
            composition = self._analyze_composition_roles(kg, entities)
            kg_paths    = self._find_kg_paths(kg, entities)
            inf_chains  = self._build_inference_chains(kg, entities)
            hub_nodes   = self._find_hub_nodes(kg)
            coverage    = self._coverage_stats(kg, entities)

            # 3. 向后兼容字段（用真实数据回填）
            reasoning_results = self._build_reasoning_results(kg, entities, composition)
            temporal          = self._temporal_analysis(entities, kg)
            pattern           = self._pattern_recognition(entities, kg, composition)

            return {
                # 原有字段（全部保留）
                "reasoning_results":   reasoning_results,
                "temporal_analysis":   temporal,
                "pattern_recognition": pattern,
                # 新增扩展字段
                "kg_paths":             kg_paths,
                "inference_chains":     inf_chains,
                "composition_analysis": composition,
                "hub_nodes":            hub_nodes,
                "coverage_stats":       coverage,
            }

        except Exception as exc:
            self.logger.error("推理执行失败: %s", exc)
            raise

    def _do_cleanup(self) -> bool:
        try:
            self.logger.info("推理引擎资源清理完成")
            return True
        except Exception as exc:
            self.logger.error("推理引擎资源清理失败: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 图重建
    # ------------------------------------------------------------------

    def _rebuild_graph(self, graph_data: Dict) -> nx.DiGraph:
        """
        将 SemanticGraphBuilder 序列化输出重建为 nx.DiGraph。

        graph_data 结构::

            {
              "nodes": [{"id": str, "data": {...}}, ...],
              "edges": [{"source": str, "target": str, "attributes": {...}}, ...]
            }

        当同一有向对存在多条边时保留置信度最高的那条。
        """
        g = nx.DiGraph()
        for node_item in graph_data.get("nodes", []):
            nid = node_item.get("id", "")
            if nid:
                g.add_node(nid, **node_item.get("data", {}))
        for edge_item in graph_data.get("edges", []):
            src   = edge_item.get("source", "")
            tgt   = edge_item.get("target", "")
            attrs = edge_item.get("attributes", {})
            if not src or not tgt:
                continue
            if g.has_edge(src, tgt):
                if attrs.get("confidence", 0) <= g[src][tgt].get("confidence", 0):
                    continue
            g.add_edge(src, tgt, **attrs)
        return g

    # ------------------------------------------------------------------
    # 组成角色分析（君臣佐使）
    # ------------------------------------------------------------------

    def _analyze_composition_roles(
        self,
        kg: nx.DiGraph,
        entities: List[Dict],
    ) -> Dict[str, Any]:
        """遍历 KG 出边，按方剂归纳君臣佐使角色分布。"""
        composition_roles = [
            RelationshipType.SOVEREIGN.value,
            RelationshipType.MINISTER.value,
            RelationshipType.ASSISTANT.value,
            RelationshipType.ENVOY.value,
        ]
        formula_names = [e["name"] for e in entities if e.get("type") == "formula"]
        result: Dict[str, Dict] = {}

        for formula in formula_names:
            formula_node = f"formula:{formula}"
            if formula_node not in kg:
                continue
            roles: Dict[str, List[str]] = {r: [] for r in composition_roles}
            for _, tgt, data in kg.out_edges(formula_node, data=True):
                rel = data.get("relationship_type", "")
                if rel in roles:
                    herb_name = tgt.split(":", 1)[-1] if ":" in tgt else tgt
                    roles[rel].append(herb_name)
            result[formula] = {
                "roles":           roles,
                "total_herbs":     sum(len(v) for v in roles.values()),
                "sovereign_count": len(roles[RelationshipType.SOVEREIGN.value]),
                "minister_count":  len(roles[RelationshipType.MINISTER.value]),
                "assistant_count": len(roles[RelationshipType.ASSISTANT.value]),
                "envoy_count":     len(roles[RelationshipType.ENVOY.value]),
            }

        return {
            "formula_compositions":    result,
            "total_formulas_analyzed": len(result),
        }

    # ------------------------------------------------------------------
    # KG 路径查找
    # ------------------------------------------------------------------

    def _find_kg_paths(
        self,
        kg: nx.DiGraph,
        entities: List[Dict],
    ) -> List[Dict[str, Any]]:
        """
        查找方剂节点到证候/功效节点之间的多跳路径（≤ max_path_len 跳）。
        每对最多保留 3 条路径，全局上限 50 条，按置信度降序排列。
        """
        formula_nodes = self._collect_formula_nodes(entities)
        target_nodes = self._collect_target_nodes(kg, entities)

        paths_found: List[Dict[str, Any]] = []
        for src, tgt in self._iter_valid_pairs(kg, formula_nodes, target_nodes):
            for path in self._safe_simple_paths(kg, src, tgt):
                edge_labels = self._path_edge_labels(kg, path)
                confidence = self._path_confidence(kg, path)
                paths_found.append({
                    "path": path,
                    "length": len(path) - 1,
                    "relationship_sequence": edge_labels,
                    "confidence": round(confidence, 4),
                })

        paths_found.sort(key=lambda p: p["confidence"], reverse=True)
        return paths_found[:50]

    def _collect_formula_nodes(self, entities: List[Dict[str, Any]]) -> List[str]:
        """收集方剂节点 ID。"""
        return [f"formula:{e['name']}" for e in entities if e.get("type") == "formula" and e.get("name")]

    def _collect_target_nodes(self, kg: nx.DiGraph, entities: List[Dict[str, Any]]) -> List[str]:
        """收集证候/功效目标节点，包含实体输入和 KG 现有节点。"""
        target_nodes: List[str] = (
            [f"syndrome:{e['name']}" for e in entities if e.get("type") == "syndrome" and e.get("name")]
            + [f"efficacy:{e['name']}" for e in entities if e.get("type") == "efficacy" and e.get("name")]
        )
        for node in kg.nodes():
            if node.startswith(("syndrome:", "efficacy:")) and node not in target_nodes:
                target_nodes.append(node)
        return target_nodes

    def _iter_valid_pairs(
        self,
        kg: nx.DiGraph,
        formula_nodes: List[str],
        target_nodes: List[str],
    ) -> List[Tuple[str, str]]:
        """生成有效 source-target 对，受 max_pairs 限制。"""
        pairs: List[Tuple[str, str]] = []
        visited_pairs: Set[Tuple[str, str]] = set()
        for src in formula_nodes:
            if src not in kg:
                continue
            for tgt in target_nodes:
                if tgt not in kg or src == tgt:
                    continue
                pair = (src, tgt)
                if pair in visited_pairs:
                    continue
                visited_pairs.add(pair)
                pairs.append(pair)
                if len(pairs) >= self._max_pairs:
                    return pairs
        return pairs

    def _safe_simple_paths(self, kg: nx.DiGraph, src: str, tgt: str) -> List[List[str]]:
        """安全获取简单路径，异常时返回空列表。"""
        try:
            return list(nx.all_simple_paths(kg, source=src, target=tgt, cutoff=self._max_path_len))[:3]
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            return []

    def _path_edge_labels(self, kg: nx.DiGraph, path: List[str]) -> List[str]:
        return [
            (kg.get_edge_data(path[i], path[i + 1]) or {}).get("relationship_type", "unknown")
            for i in range(len(path) - 1)
        ]

    def _path_confidence(self, kg: nx.DiGraph, path: List[str]) -> float:
        """路径置信度 = 各边（edge_confidence × role_weight）的几何均值。"""
        n = len(path) - 1
        if n <= 0:
            return 0.0
        product = 1.0
        for i in range(n):
            data      = kg.get_edge_data(path[i], path[i + 1]) or {}
            edge_conf = data.get("confidence", 0.5)
            rel       = data.get("relationship_type", "")
            product  *= edge_conf * _ROLE_WEIGHTS.get(rel, _DEFAULT_ROLE_WEIGHT)
        return product ** (1.0 / n)

    # ------------------------------------------------------------------
    # 推理链构建
    # ------------------------------------------------------------------

    def _build_inference_chains(
        self,
        kg: nx.DiGraph,
        entities: List[Dict],
    ) -> List[Dict[str, Any]]:
        """
        沿预定义关系序列模式提取推理链，例如：
          方剂 -君药→ 药物 -功效→ 功效节点
        """
        chains: List[Dict[str, Any]] = []
        formula_nodes = [
            (f"formula:{e['name']}", e["name"])
            for e in entities if e.get("type") == "formula"
        ]
        for formula_node, formula_name in formula_nodes:
            if formula_node not in kg:
                continue
            for pattern in _INFERENCE_CHAIN_PATTERNS:
                state = _ChainTraversalState(
                    formula_name=formula_name,
                    pattern=pattern,
                    path=[formula_node],
                    rel_path=[],
                    results=chains,
                )
                self._dfs_chain(kg, formula_node, 0, state)

        # 去重 + 排序
        seen: Set[str] = set()
        unique: List[Dict[str, Any]] = []
        for c in chains:
            key = "→".join(c["path"])
            if key not in seen:
                seen.add(key)
                unique.append(c)
        unique.sort(key=lambda c: c["confidence"], reverse=True)
        return unique[:40]

    def _dfs_chain(
        self,
        kg: nx.DiGraph,
        current: str,
        depth: int,
        state: _ChainTraversalState,
    ) -> None:
        """按 pattern[depth] 扩展一跳，递归直到 pattern 消耗完。"""
        if depth == len(state.pattern):
            confidence = self._path_confidence_from_rel_path(kg, state.path, state.rel_path)
            state.results.append({
                "formula":               state.formula_name,
                "path":                  list(state.path),
                "relationship_sequence": list(state.rel_path),
                "pattern":               list(state.pattern),
                "confidence":            round(confidence, 4),
                "terminal_node":         state.path[-1],
                "terminal_label": (
                    state.path[-1].split(":", 1)[-1] if ":" in state.path[-1] else state.path[-1]
                ),
            })
            return
        target_rel = state.pattern[depth]
        for _, tgt, data in kg.out_edges(current, data=True):
            if data.get("relationship_type") != target_rel or tgt in state.path:
                continue
            state.path.append(tgt)
            state.rel_path.append(target_rel)
            self._dfs_chain(kg, tgt, depth + 1, state)
            state.path.pop()
            state.rel_path.pop()

    def _path_confidence_from_rel_path(
        self,
        kg: nx.DiGraph,
        path: List[str],
        rel_path: List[str],
    ) -> float:
        n = len(rel_path)
        if n == 0:
            return 0.0
        product = 1.0
        for i, rel in enumerate(rel_path):
            data      = kg.get_edge_data(path[i], path[i + 1]) or {}
            edge_conf = data.get("confidence", 0.5)
            product  *= edge_conf * _ROLE_WEIGHTS.get(rel, _DEFAULT_ROLE_WEIGHT)
        return product ** (1.0 / n)

    # ------------------------------------------------------------------
    # Hub 节点分析
    # ------------------------------------------------------------------

    def _find_hub_nodes(self, kg: nx.DiGraph) -> List[Dict[str, Any]]:
        """基于度中心性返回 top-k 节点。"""
        if kg.number_of_nodes() == 0:
            return []
        centrality  = nx.degree_centrality(kg)
        out_degrees = dict(kg.out_degree())
        in_degrees  = dict(kg.in_degree())
        scored = []
        for node_id, cent in centrality.items():
            node_data   = kg.nodes[node_id]
            entity_type, _, entity_name = node_id.partition(":")
            scored.append({
                "node_id":           node_id,
                "name":              entity_name or node_id,
                "entity_type":       entity_type,
                "degree_centrality": round(cent, 4),
                "out_degree":        out_degrees.get(node_id, 0),
                "in_degree":         in_degrees.get(node_id, 0),
                "confidence":        node_data.get("confidence", 0.5),
            })
        scored.sort(key=lambda x: (x["degree_centrality"], x["out_degree"]), reverse=True)
        return scored[: self._top_k_hubs]

    # ------------------------------------------------------------------
    # 覆盖率统计
    # ------------------------------------------------------------------

    def _coverage_stats(
        self,
        kg: nx.DiGraph,
        entities: List[Dict],
    ) -> Dict[str, Any]:
        """统计各类型实体在 KG 中的覆盖比例。"""
        type_counter: collections.Counter = collections.Counter()
        in_kg_counter: collections.Counter = collections.Counter()
        kg_nodes = set(kg.nodes())
        for entity in entities:
            etype = entity.get("type", "unknown")
            ename = entity.get("name", "")
            type_counter[etype] += 1
            if f"{etype}:{ename}" in kg_nodes:
                in_kg_counter[etype] += 1
        coverage_by_type: Dict[str, Dict] = {}
        for etype, total in type_counter.items():
            in_kg = in_kg_counter.get(etype, 0)
            coverage_by_type[etype] = {
                "total":         total,
                "in_kg":         in_kg,
                "coverage_rate": round(in_kg / total, 4) if total else 0.0,
            }
        total_entities = sum(type_counter.values())
        total_in_kg    = sum(in_kg_counter.values())
        return {
            "total_entities":        total_entities,
            "entities_in_kg":        total_in_kg,
            "overall_coverage_rate": round(total_in_kg / total_entities, 4) if total_entities else 0.0,
            "kg_nodes":              kg.number_of_nodes(),
            "kg_edges":              kg.number_of_edges(),
            "coverage_by_type":      coverage_by_type,
        }

    # ------------------------------------------------------------------
    # 向后兼容字段（用 KG 真实数据填充原桩输出）
    # ------------------------------------------------------------------

    def _build_reasoning_results(
        self,
        kg: nx.DiGraph,
        entities: List[Dict],
        composition: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        填充原 reasoning_results 字段。
        原桩为 O(n²) 笛卡尔积；现改用 KG 真实边列表。
        原字段名（entity_relationships / knowledge_patterns / inference_confidence）全部保留。
        """
        edge_list = [
            {
                "source":     src.split(":", 1)[-1] if ":" in src else src,
                "target":     tgt.split(":", 1)[-1] if ":" in tgt else tgt,
                "type":       data.get("relationship_type", "unknown"),
                "confidence": data.get("confidence", 0.5),
            }
            for src, tgt, data in kg.edges(data=True)
        ]
        inf_conf = (
            round(sum(e["confidence"] for e in edge_list) / len(edge_list), 4)
            if edge_list else 0.0
        )
        return {
            "entity_relationships": edge_list,
            "knowledge_patterns":   self._identify_patterns_from_kg(kg, entities),
            "inference_confidence": inf_conf,
        }

    def _identify_patterns_from_kg(
        self,
        kg: nx.DiGraph,
        entities: List[Dict],
    ) -> Dict[str, Any]:
        """基于真实 KG 的模式识别（替换原硬编码）。原字段名全部保留。"""
        groups: Dict[str, List[str]] = collections.defaultdict(list)
        for entity in entities:
            groups[entity.get("type", "unknown")].append(entity.get("name", ""))

        # 被多个来源指向的功效节点（共享功效）
        efficacy_in_degrees: Dict[str, int] = {
            node.split(":", 1)[-1]: kg.in_degree(node)
            for node in kg.nodes()
            if node.startswith("efficacy:")
        }
        common_efficacies = sorted(
            efficacy_in_degrees.keys(),
            key=lambda k: efficacy_in_degrees[k],
            reverse=True,
        )[:5]

        return {
            "common_entities":        common_efficacies,
            "entity_groups":          dict(groups),
            "most_shared_efficacies": common_efficacies,
        }

    def _temporal_analysis(
        self,
        entities: List[Dict],
        kg: nx.DiGraph,
    ) -> Dict[str, Any]:
        """
        基于 KG 关系多样性重构时间维度分析。
        原字段名（time_periods / temporal_patterns）全部保留。
        """
        dynasty_set: Set[str] = set()
        for entity in entities:
            dynasty = (
                (entity.get("metadata") or {}).get("dynasty")
                or entity.get("dynasty")
            )
            if dynasty:
                dynasty_set.add(dynasty)

        evolution_notes: List[str] = []
        if kg.number_of_edges() > 0:
            roles_found = {data.get("relationship_type", "") for _, _, data in kg.edges(data=True)}
            if RelationshipType.SOVEREIGN.value in roles_found:
                evolution_notes.append("君臣佐使配伍理论已系统化")
            if RelationshipType.EFFICACY.value in roles_found:
                evolution_notes.append("药物功效归纳体系完整")
            if RelationshipType.TREATS.value in roles_found:
                evolution_notes.append("方证对应关系有文献支撑")

        return {
            "time_periods":            sorted(dynasty_set) if dynasty_set else ["东汉", "宋代", "明代"],
            "temporal_patterns":       evolution_notes or ["方剂发展轨迹", "药材使用演变"],
            "kg_based_temporal_notes": evolution_notes,
            "dynasty_coverage":        len(dynasty_set),
        }

    def _pattern_recognition(
        self,
        entities: List[Dict],
        kg: nx.DiGraph,
        composition: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        基于 KG 结构的真实模式识别。
        原字段名（common_patterns / prediction）全部保留。
        """
        role_rel = {
            RelationshipType.SOVEREIGN.value,
            RelationshipType.MINISTER.value,
            RelationshipType.ASSISTANT.value,
            RelationshipType.ENVOY.value,
        }
        formula_herb_map: Dict[str, Set[str]] = collections.defaultdict(set)
        for src, tgt, data in kg.edges(data=True):
            if (
                src.startswith("formula:")
                and tgt.startswith("herb:")
                and data.get("relationship_type") in role_rel
            ):
                formula_herb_map[src].add(tgt.split(":", 1)[-1])

        co_herb_pairs: List[Tuple[str, str, int]] = []
        flist = list(formula_herb_map.keys())
        for i in range(len(flist)):
            for j in range(i + 1, len(flist)):
                common = formula_herb_map[flist[i]] & formula_herb_map[flist[j]]
                if common:
                    fi = flist[i].split(":", 1)[-1]
                    fj = flist[j].split(":", 1)[-1]
                    co_herb_pairs.append((fi, fj, len(common)))
        co_herb_pairs.sort(key=lambda x: x[2], reverse=True)
        pattern_notes = [
            f"{fi} 与 {fj} 共享 {cnt} 味药材"
            for fi, fj, cnt in co_herb_pairs[:5]
        ] or ["方剂配伍规律", "剂量变化趋势"]

        out_deg = dict(kg.out_degree())
        top_herbs = sorted(
            [n for n in kg.nodes() if n.startswith("herb:")],
            key=lambda n: out_deg.get(n, 0),
            reverse=True,
        )[:3]
        top_herb_names = [n.split(":", 1)[-1] for n in top_herbs]
        prediction = (
            f"核心药物（{'，'.join(top_herb_names)}）可能是新方剂候选成分"
            if top_herb_names
            else "未来可能的方剂组合"
        )

        return {
            "common_patterns":      pattern_notes,
            "prediction":           prediction,
            "formula_herb_overlap": [
                {"formula_a": fi, "formula_b": fj, "shared_herb_count": cnt}
                for fi, fj, cnt in co_herb_pairs[:10]
            ],
            "potential_key_herbs":  top_herb_names,
        }
