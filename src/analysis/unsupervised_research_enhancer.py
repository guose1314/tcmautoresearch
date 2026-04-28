from __future__ import annotations

"""无监督科研增强器。

面向古籍文本分析主链提供一组轻量、可解释、零标注的科研增强信号：

- 图社区发现: 将实体关系图划分为潜在研究主题
- 桥接实体识别: 找出跨主题连接的关键概念
- 新颖性候选挖掘: 标记跨社区且中心性较高的关系
- 文档签名: 生成可持久化的科研画像摘要

实现优先考虑当前仓库的在线批处理约束，因此仅依赖 networkx 和标准库，
避免引入额外训练步骤或重量级模型。
"""

import hashlib
import math
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Tuple

import networkx as nx

_LITERATURE_ALIGNMENT: List[Dict[str, Any]] = [
    {
        "title": "Contrastive learning enhanced graph relation representation for document-level relation extraction",
        "year": 2024,
        "method": "图关系表示 + 对比式关系增强",
        "adaptation": "使用社区边界与桥接实体作为零标注关系显著性先验。",
    },
    {
        "title": "Document Aware Contrastive Learning Approach for Generative Retrieval",
        "year": 2024,
        "method": "文档级表示对齐",
        "adaptation": "将文档主题签名与实体社区原型写入科研资产，提升检索与科研追踪。",
    },
    {
        "title": "Exploration of scientific documents through unsupervised learning-based segmentation techniques",
        "year": 2024,
        "method": "无监督文档分段与主题细粒度表示",
        "adaptation": "利用实体图社区近似文档主题段，补充古籍段落级科研结构。",
    },
    {
        "title": "Developing a Machine Learning Model Using Transformer to Assess the Novelty of Scientific Articles",
        "year": 2024,
        "method": "基于文档表示的无监督新颖性检测",
        "adaptation": "将跨社区高桥接关系标记为古籍知识新颖性候选。",
    },
    {
        "title": "Conceptual Design Considerations of a Knowledge Graph-Driven Framework for Scientific Knowledge Exploration",
        "year": 2025,
        "method": "无监督盲抽取 + 科学知识图谱探索",
        "adaptation": "将无监督主题、桥接实体和关系候选同步写入 PG/Neo4j 形成科研资产。",
    },
]


def build_unsupervised_research_view(
    raw_text: str,
    entities: Iterable[Mapping[str, Any]],
    graph_data: Mapping[str, Any],
    *,
    source_file: str | None = None,
) -> Dict[str, Any]:
    """从实体与关系图中构造可持久化的无监督科研画像。"""

    normalized_entities = _normalize_entities(entities)
    graph = _build_entity_graph(normalized_entities, graph_data)

    if graph.number_of_nodes() == 0:
        return {
            "document_signature": _build_empty_signature(raw_text, source_file),
            "community_topics": [],
            "bridge_entities": [],
            "salient_relations": [],
            "novelty_candidates": [],
            "entity_annotations": {},
            "neo4j_projection": {"nodes": [], "edges": []},
            "literature_alignment": list(_LITERATURE_ALIGNMENT),
        }

    pagerank = _safe_pagerank(graph)
    degree_centrality = (
        nx.degree_centrality(graph)
        if graph.number_of_nodes() > 1
        else {n: 1.0 for n in graph.nodes}
    )
    betweenness = (
        nx.betweenness_centrality(graph, weight=None, normalized=True)
        if graph.number_of_nodes() > 2
        else {n: 0.0 for n in graph.nodes}
    )

    community_sets = _detect_communities(graph)
    community_assignments = _build_community_assignments(community_sets)
    community_topics = _build_community_topics(
        graph,
        community_sets,
        pagerank,
        degree_centrality,
        source_file=source_file,
    )
    topic_lookup = {topic["community_id"]: topic for topic in community_topics}
    topic_entropy = _distribution_entropy([len(group) for group in community_sets])
    bridge_entities = _build_bridge_entities(
        graph,
        community_assignments,
        pagerank,
        degree_centrality,
        betweenness,
        topic_lookup,
    )
    salient_relations, novelty_candidates = _score_relations(
        graph,
        community_assignments,
        pagerank,
        betweenness,
    )
    entity_annotations = _build_entity_annotations(
        graph,
        pagerank,
        degree_centrality,
        betweenness,
        bridge_entities,
        topic_lookup,
        community_assignments,
    )

    document_signature = _build_document_signature(
        raw_text,
        graph,
        normalized_entities,
        community_topics,
        bridge_entities,
        topic_entropy,
        source_file=source_file,
    )

    return {
        "document_signature": document_signature,
        "community_topics": community_topics,
        "bridge_entities": bridge_entities,
        "salient_relations": salient_relations,
        "novelty_candidates": novelty_candidates,
        "entity_annotations": entity_annotations,
        "neo4j_projection": _build_neo4j_projection(
            document_signature,
            community_topics,
            bridge_entities,
            entity_annotations,
            community_assignments,
        ),
        "literature_alignment": list(_LITERATURE_ALIGNMENT),
    }


def apply_unsupervised_annotations(
    entities: Iterable[Mapping[str, Any]],
    graph_data: Mapping[str, Any],
    unsupervised_view: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """把无监督信号回填到实体与关系元数据，便于双库存储。"""

    annotations = {
        str(name): dict(payload)
        for name, payload in dict(
            unsupervised_view.get("entity_annotations") or {}
        ).items()
    }
    salient_lookup = {
        (
            str(item.get("source") or ""),
            str(item.get("target") or ""),
            str(item.get("relation") or ""),
        ): dict(item)
        for item in list(unsupervised_view.get("salient_relations") or [])
    }
    novelty_lookup = {
        (
            str(item.get("source") or ""),
            str(item.get("target") or ""),
            str(item.get("relation") or ""),
        ): dict(item)
        for item in list(unsupervised_view.get("novelty_candidates") or [])
    }

    enriched_entities: List[Dict[str, Any]] = []
    for entity in entities:
        item = dict(entity)
        name = str(
            item.get("name") or item.get("text") or item.get("value") or ""
        ).strip()
        if name and name in annotations:
            meta = dict(item.get("metadata") or {})
            meta["unsupervised_learning"] = annotations[name]
            item["metadata"] = meta
            item["unsupervised_learning"] = annotations[name]
        enriched_entities.append(item)

    enriched_graph = {**graph_data}
    enriched_edges: List[Dict[str, Any]] = []
    for edge in list(graph_data.get("edges") or []):
        item = dict(edge)
        source = str(item.get("source") or item.get("from") or "").strip()
        target = str(item.get("target") or item.get("to") or "").strip()
        relation = str(
            item.get("relation")
            or item.get("rel_type")
            or item.get("label")
            or "related"
        ).strip()
        key = (source, target, relation)
        relation_meta = dict(item.get("attributes") or {})
        if key in salient_lookup:
            relation_meta["salience"] = {
                "association_score": salient_lookup[key].get("association_score"),
                "cross_community": salient_lookup[key].get("cross_community"),
            }
        if key in novelty_lookup:
            relation_meta["novelty"] = {
                "novelty_score": novelty_lookup[key].get("novelty_score"),
                "reason": novelty_lookup[key].get("reason"),
            }
        if relation_meta:
            item["attributes"] = relation_meta
            item["unsupervised_learning"] = relation_meta
        enriched_edges.append(item)
    enriched_graph["edges"] = enriched_edges
    return enriched_entities, enriched_graph


def _normalize_entities(entities: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for entity in entities:
        name = str(
            entity.get("name") or entity.get("text") or entity.get("value") or ""
        ).strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "type": str(
                    entity.get("type") or entity.get("entity_type") or "generic"
                )
                .strip()
                .lower()
                or "generic",
                "confidence": float(entity.get("confidence", 0.5) or 0.5),
            }
        )
    return normalized


def _build_entity_graph(
    entities: List[Dict[str, Any]],
    graph_data: Mapping[str, Any],
) -> nx.Graph:
    graph = nx.Graph()
    for entity in entities:
        graph.add_node(
            entity["name"],
            name=entity["name"],
            type=entity["type"],
            confidence=entity["confidence"],
        )

    edge_weights: Counter[Tuple[str, str]] = Counter()
    edge_relations: Dict[Tuple[str, str], set[str]] = defaultdict(set)
    for edge in list(graph_data.get("edges") or []):
        source = str(edge.get("source") or edge.get("from") or "").strip()
        target = str(edge.get("target") or edge.get("to") or "").strip()
        relation = (
            str(
                edge.get("relation")
                or edge.get("rel_type")
                or edge.get("label")
                or "related"
            ).strip()
            or "related"
        )
        if not source or not target or source == target:
            continue
        graph.add_node(
            source, name=source, type=str(edge.get("source_type") or "generic")
        )
        graph.add_node(
            target, name=target, type=str(edge.get("target_type") or "generic")
        )
        pair = tuple(sorted((source, target)))
        edge_weights[pair] += 1
        edge_relations[pair].add(relation)

    for pair, weight in edge_weights.items():
        source, target = pair
        graph.add_edge(
            source,
            target,
            weight=float(weight),
            relation_types=sorted(edge_relations[pair]),
            relation_type=sorted(edge_relations[pair])[0]
            if edge_relations[pair]
            else "related",
        )
    return graph


def _safe_pagerank(graph: nx.Graph) -> Dict[str, float]:
    if graph.number_of_nodes() == 1:
        only = next(iter(graph.nodes))
        return {only: 1.0}
    if graph.number_of_edges() == 0:
        uniform = 1.0 / max(1, graph.number_of_nodes())
        return {node: uniform for node in graph.nodes}
    return nx.pagerank(graph, weight="weight")


def _detect_communities(graph: nx.Graph) -> List[set[str]]:
    if graph.number_of_nodes() == 0:
        return []
    if graph.number_of_edges() == 0:
        return [{node} for node in graph.nodes]
    communities = list(
        nx.algorithms.community.greedy_modularity_communities(graph, weight="weight")
    )
    if not communities:
        return [{node} for node in graph.nodes]
    return [set(group) for group in communities]


def _build_community_assignments(communities: Iterable[set[str]]) -> Dict[str, str]:
    assignments: Dict[str, str] = {}
    for index, group in enumerate(communities, start=1):
        cid = f"topic_{index:02d}"
        for node in group:
            assignments[node] = cid
    return assignments


def _build_community_topics(
    graph: nx.Graph,
    communities: List[set[str]],
    pagerank: Mapping[str, float],
    degree_centrality: Mapping[str, float],
    *,
    source_file: str | None,
) -> List[Dict[str, Any]]:
    topics: List[Dict[str, Any]] = []
    total_nodes = max(1, graph.number_of_nodes())
    for index, group in enumerate(communities, start=1):
        cid = f"topic_{index:02d}"
        subgraph = graph.subgraph(group)
        ordered_nodes = sorted(
            group,
            key=lambda node: (
                pagerank.get(node, 0.0),
                degree_centrality.get(node, 0.0),
                node,
            ),
            reverse=True,
        )
        dominant_types = Counter(
            str(graph.nodes[node].get("type") or "generic") for node in group
        )
        label = " / ".join(ordered_nodes[:2]) if ordered_nodes else cid
        possible_edges = len(group) * (len(group) - 1) / 2
        cohesion = (
            round(subgraph.number_of_edges() / possible_edges, 4)
            if possible_edges > 0
            else 0.0
        )
        topics.append(
            {
                "topic_id": _stable_id(source_file or "document", cid, label),
                "community_id": cid,
                "label": label,
                "size": len(group),
                "coverage": round(len(group) / total_nodes, 4),
                "cohesion": cohesion,
                "member_names": ordered_nodes,
                "hub_entities": ordered_nodes[:3],
                "dominant_types": dominant_types.most_common(3),
            }
        )
    return topics


def _build_bridge_entities(
    graph: nx.Graph,
    community_assignments: Mapping[str, str],
    pagerank: Mapping[str, float],
    degree_centrality: Mapping[str, float],
    betweenness: Mapping[str, float],
    topic_lookup: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    bridges: List[Dict[str, Any]] = []
    for node in graph.nodes:
        neighbour_communities = {
            community_assignments.get(neighbour)
            for neighbour in graph.neighbors(node)
            if community_assignments.get(neighbour)
        }
        community_span = len(neighbour_communities)
        bridge_score = round(
            min(
                1.0,
                betweenness.get(node, 0.0) * 0.6
                + degree_centrality.get(node, 0.0) * 0.25
                + max(0, community_span - 1) * 0.15,
            ),
            4,
        )
        if bridge_score < 0.08 and community_span < 2:
            continue
        current_topic = topic_lookup.get(community_assignments.get(node, ""), {})
        bridges.append(
            {
                "name": node,
                "type": str(graph.nodes[node].get("type") or "generic"),
                "community_id": community_assignments.get(node),
                "topic_label": current_topic.get("label"),
                "pagerank": round(pagerank.get(node, 0.0), 4),
                "degree_centrality": round(degree_centrality.get(node, 0.0), 4),
                "betweenness": round(betweenness.get(node, 0.0), 4),
                "community_span": community_span,
                "bridge_score": bridge_score,
            }
        )
    bridges.sort(
        key=lambda item: (item["bridge_score"], item["betweenness"], item["pagerank"]),
        reverse=True,
    )
    return bridges[:10]


def _score_relations(
    graph: nx.Graph,
    community_assignments: Mapping[str, str],
    pagerank: Mapping[str, float],
    betweenness: Mapping[str, float],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    salient_relations: List[Dict[str, Any]] = []
    novelty_candidates: List[Dict[str, Any]] = []
    max_weight = max(
        (float(data.get("weight", 1.0)) for _, _, data in graph.edges(data=True)),
        default=1.0,
    )
    for source, target, data in graph.edges(data=True):
        relation = str(data.get("relation_type") or "related")
        weight = float(data.get("weight", 1.0))
        cross_community = community_assignments.get(
            source
        ) != community_assignments.get(target)
        association_score = round(
            min(
                1.0,
                ((pagerank.get(source, 0.0) + pagerank.get(target, 0.0)) / 2) * 0.45
                + (weight / max_weight) * 0.35
                + (0.2 if cross_community else 0.05),
            ),
            4,
        )
        salient_relations.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "association_score": association_score,
                "cross_community": cross_community,
                "weight": weight,
            }
        )
        novelty_score = round(
            min(
                1.0,
                (0.55 if cross_community else 0.1)
                + ((betweenness.get(source, 0.0) + betweenness.get(target, 0.0)) / 2)
                * 0.45,
            ),
            4,
        )
        if novelty_score >= 0.35:
            novelty_candidates.append(
                {
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "novelty_score": novelty_score,
                    "reason": "cross_community_bridge"
                    if cross_community
                    else "high_bridge_centrality",
                }
            )
    salient_relations.sort(key=lambda item: item["association_score"], reverse=True)
    novelty_candidates.sort(key=lambda item: item["novelty_score"], reverse=True)
    return salient_relations[:15], novelty_candidates[:10]


def _build_entity_annotations(
    graph: nx.Graph,
    pagerank: Mapping[str, float],
    degree_centrality: Mapping[str, float],
    betweenness: Mapping[str, float],
    bridge_entities: Iterable[Mapping[str, Any]],
    topic_lookup: Mapping[str, Mapping[str, Any]],
    community_assignments: Mapping[str, str],
) -> Dict[str, Dict[str, Any]]:
    bridge_lookup = {str(item.get("name")): item for item in bridge_entities}
    annotations: Dict[str, Dict[str, Any]] = {}
    for node in graph.nodes:
        community_id = community_assignments.get(node)
        topic = topic_lookup.get(community_id or "", {})
        bridge = bridge_lookup.get(node)
        annotations[node] = {
            "community_id": community_id,
            "topic_label": topic.get("label"),
            "topic_size": topic.get("size"),
            "pagerank": round(pagerank.get(node, 0.0), 4),
            "degree_centrality": round(degree_centrality.get(node, 0.0), 4),
            "betweenness": round(betweenness.get(node, 0.0), 4),
            "bridge_score": round(
                float(bridge.get("bridge_score", 0.0)) if bridge else 0.0, 4
            ),
        }
    return annotations


def _build_document_signature(
    raw_text: str,
    graph: nx.Graph,
    entities: List[Dict[str, Any]],
    community_topics: List[Dict[str, Any]],
    bridge_entities: List[Dict[str, Any]],
    topic_entropy: float,
    *,
    source_file: str | None,
) -> Dict[str, Any]:
    entity_type_counts = Counter(item["type"] for item in entities)
    return {
        "document_key": _stable_id(
            source_file or "document", str(len(raw_text)), str(graph.number_of_nodes())
        ),
        "source_file": source_file,
        "raw_text_length": len(raw_text or ""),
        "entity_count": graph.number_of_nodes(),
        "relation_count": graph.number_of_edges(),
        "entity_type_distribution": dict(entity_type_counts),
        "entity_type_entropy": _distribution_entropy(entity_type_counts.values()),
        "topic_count": len(community_topics),
        "topic_entropy": topic_entropy,
        "bridge_entity_count": len(bridge_entities),
        "graph_density": round(nx.density(graph), 6)
        if graph.number_of_nodes() > 1
        else 0.0,
        "connected_components": nx.number_connected_components(graph)
        if graph.number_of_nodes()
        else 0,
        "top_topics": [topic["label"] for topic in community_topics[:3]],
    }


def _build_neo4j_projection(
    document_signature: Mapping[str, Any],
    community_topics: Iterable[Mapping[str, Any]],
    bridge_entities: Iterable[Mapping[str, Any]],
    entity_annotations: Mapping[str, Mapping[str, Any]],
    community_assignments: Mapping[str, str],
) -> Dict[str, Any]:
    # T3.2: ResearchTopic / HAS_LATENT_TOPIC / HAS_TOPIC_MEMBER 已迁移到
    # CatalogContext (Topic / BELONGS_TO_TOPIC)。本函数保留旧投影仅为过渡兼容，
    # 下个版本（T3.x 收尾）将整体删除。
    import warnings as _warnings

    _warnings.warn(
        "_build_neo4j_projection emits legacy ResearchTopic/HAS_LATENT_TOPIC/HAS_TOPIC_MEMBER; "
        "use CatalogContext.upsert_topic_membership instead (will be removed in next minor).",
        DeprecationWarning,
        stacklevel=2,
    )
    doc_id = str(
        document_signature.get("document_key") or _stable_id("document", "unknown")
    )
    doc_name = str(document_signature.get("source_file") or doc_id)
    nodes: List[Dict[str, Any]] = [
        {
            "id": doc_id,
            "name": doc_name,
            "type": "research_document",
            "props": {
                "topic_count": int(document_signature.get("topic_count", 0)),
                "bridge_entity_count": int(
                    document_signature.get("bridge_entity_count", 0)
                ),
                "graph_density": float(document_signature.get("graph_density", 0.0)),
                "topic_entropy": float(document_signature.get("topic_entropy", 0.0)),
            },
        }
    ]
    edges: List[Dict[str, Any]] = []

    for topic in community_topics:
        topic_id = str(topic.get("topic_id"))
        nodes.append(
            {
                "id": topic_id,
                "name": str(topic.get("label") or topic_id),
                "type": "research_topic",
                "props": {
                    "community_id": topic.get("community_id"),
                    "size": int(topic.get("size", 0)),
                    "cohesion": float(topic.get("cohesion", 0.0)),
                    "coverage": float(topic.get("coverage", 0.0)),
                },
            }
        )
        edges.append(
            {
                "src_id": doc_id,
                "dst_id": topic_id,
                "rel_type": "HAS_LATENT_TOPIC",
                "props": {
                    "size": int(topic.get("size", 0)),
                    "cohesion": float(topic.get("cohesion", 0.0)),
                },
            }
        )
        for member_name in list(topic.get("member_names") or [])[:8]:
            annotation = entity_annotations.get(str(member_name), {})
            edges.append(
                {
                    "src_id": topic_id,
                    "dst_id": str(member_name),
                    "rel_type": "HAS_TOPIC_MEMBER",
                    "props": {
                        "community_id": topic.get("community_id"),
                        "pagerank": float(annotation.get("pagerank", 0.0)),
                    },
                }
            )

    for bridge in list(bridge_entities)[:8]:
        entity_name = str(bridge.get("name") or "")
        if not entity_name:
            continue
        community_id = community_assignments.get(entity_name)
        if not community_id:
            continue
        topic = next(
            (
                item
                for item in community_topics
                if item.get("community_id") == community_id
            ),
            None,
        )
        if not topic:
            continue
        edges.append(
            {
                "src_id": str(topic.get("topic_id")),
                "dst_id": entity_name,
                "rel_type": "HIGHLIGHTS_BRIDGE",
                "props": {
                    "bridge_score": float(bridge.get("bridge_score", 0.0)),
                    "community_span": int(bridge.get("community_span", 0)),
                },
            }
        )

    return {"nodes": nodes, "edges": edges}


def _build_empty_signature(raw_text: str, source_file: str | None) -> Dict[str, Any]:
    return {
        "document_key": _stable_id(source_file or "document", str(len(raw_text or ""))),
        "source_file": source_file,
        "raw_text_length": len(raw_text or ""),
        "entity_count": 0,
        "relation_count": 0,
        "entity_type_distribution": {},
        "entity_type_entropy": 0.0,
        "topic_count": 0,
        "topic_entropy": 0.0,
        "bridge_entity_count": 0,
        "graph_density": 0.0,
        "connected_components": 0,
        "top_topics": [],
    }


def _distribution_entropy(values: Iterable[int]) -> float:
    counts = [int(value) for value in values if int(value) > 0]
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        p = count / total
        entropy -= p * math.log(p, 2)
    return round(entropy, 4)


def _stable_id(*parts: str) -> str:
    digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]
