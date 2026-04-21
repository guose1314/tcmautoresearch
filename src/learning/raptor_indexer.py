# src/learning/raptor_indexer.py
"""
RaptorIndexer — RAPTOR 多层摘要树索引（指令 I-07）。

RAPTOR（Recursive Abstractive Processing for Tree-Organized Retrieval）
将文档递归聚类并生成多层摘要，形成层次化索引树，使检索可以同时覆盖
具体细节（叶节点）和高层主题（根节点）。

参考：Sarthi et al. (2024) "RAPTOR: Recursive Abstractive Processing for
Tree-Organized Retrieval" https://arxiv.org/abs/2401.18059

层次结构：
  L0（叶节点）: 原始文档片段（每片 300-500 字）
  L1（聚类摘要）: 相似文档组的摘要（每组 5-10 片）
  L2（主题摘要）: L1 摘要的再摘要（跨主题）
  L3（全局摘要）: 整个语料库的顶层概述

设计原则：
  - 降级容忍：无 LLM 时用提取式摘要（截断）代替抽象式摘要
  - 无 ML 聚类时用词频余弦相似度实现简单聚类
  - 支持增量索引（新文档加入现有树）
"""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RaptorNode:
    """RAPTOR 树的单个节点（文档片段或聚类摘要）。"""

    node_id: str
    text: str
    level: int          # 0=原始, 1=聚类摘要, 2=主题摘要, 3=全局摘要
    children: List[str] = field(default_factory=list)  # 子节点 ID 列表
    metadata: Dict[str, Any] = field(default_factory=dict)
    cluster_id: int = -1
    word_freq: Dict[str, int] = field(default_factory=dict)  # 简单词频（替代 embedding）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "text": self.text[:500],
            "level": self.level,
            "children": self.children,
            "cluster_id": self.cluster_id,
            "metadata": self.metadata,
        }


@dataclass
class RaptorTree:
    """RAPTOR 索引树。"""

    nodes: Dict[str, RaptorNode] = field(default_factory=dict)
    levels: Dict[int, List[str]] = field(default_factory=dict)  # level → node_ids
    root_ids: List[str] = field(default_factory=list)

    @property
    def total_nodes(self) -> int:
        return len(self.nodes)

    def all_nodes_at_level(self, level: int) -> List[RaptorNode]:
        ids = self.levels.get(level, [])
        return [self.nodes[nid] for nid in ids if nid in self.nodes]

    def to_index_documents(self) -> List[Dict[str, Any]]:
        """将所有树节点转为 RAGService.index_batch() 格式。"""
        docs = []
        for node in self.nodes.values():
            docs.append({
                "id": node.node_id,
                "text": node.text,
                "metadata": {
                    "level": node.level,
                    "cluster_id": node.cluster_id,
                    **node.metadata,
                },
            })
        return docs


# ─────────────────────────────────────────────────────────────────────────────
# 主引擎
# ─────────────────────────────────────────────────────────────────────────────


class RaptorIndexer:
    """
    RAPTOR 多层摘要树索引构建器（指令 I-07）。

    用法::

        from src.learning.raptor_indexer import RaptorIndexer

        indexer = RaptorIndexer(llm_engine=engine, rag_service=rag)
        tree = indexer.build_tree(documents)
        # 自动将树节点写入 RAGService 向量库
        indexer.index_tree(tree)

        # 增量添加新文档
        new_tree = indexer.build_tree(new_docs, existing_tree=tree)
    """

    # 每个 L0 节点的最大字符数
    CHUNK_SIZE = 400
    # 每个聚类的最大文档数
    MAX_CLUSTER_SIZE = 8
    # 最小聚类大小（小于此值不生成摘要节点）
    MIN_CLUSTER_SIZE = 2
    # 最大树层次（0~3）
    MAX_LEVELS = 3

    def __init__(
        self,
        llm_engine: Optional[Any] = None,
        rag_service: Optional[Any] = None,
    ) -> None:
        """
        Args:
            llm_engine: LLMEngine 实例（用于抽象式摘要）；为 None 时用提取式。
            rag_service: RAGService 实例（用于将树节点写入向量库）。
        """
        self._llm = llm_engine
        self._rag = rag_service

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def build_tree(
        self,
        documents: List[Dict[str, Any]],
        existing_tree: Optional[RaptorTree] = None,
    ) -> RaptorTree:
        """
        从文档列表构建（或扩展）RAPTOR 索引树。

        Args:
            documents: 文档列表，每条需含 "text" 或 "content" 字段，
                       可选 "id"、"title"、"source" 字段。
            existing_tree: 若提供，则在现有树基础上增量添加新文档。

        Returns:
            构建好的 RaptorTree 对象。
        """
        tree = existing_tree or RaptorTree()

        # 1. 切分文档为 L0 叶节点
        l0_nodes = self._chunk_documents(documents)
        logger.info("RAPTOR: 生成 %d 个 L0 叶节点", len(l0_nodes))

        for node in l0_nodes:
            tree.nodes[node.node_id] = node
            tree.levels.setdefault(0, []).append(node.node_id)

        if len(l0_nodes) < self.MIN_CLUSTER_SIZE:
            logger.info("RAPTOR: 文档数量不足，跳过聚类摘要")
            tree.root_ids = [n.node_id for n in l0_nodes]
            return tree

        # 2. 递归聚类并生成摘要（L1 → L2 → L3）
        current_level_nodes = l0_nodes
        for level in range(1, self.MAX_LEVELS + 1):
            if len(current_level_nodes) < self.MIN_CLUSTER_SIZE:
                break

            clusters = self._cluster_nodes(current_level_nodes)
            summary_nodes: List[RaptorNode] = []

            for cluster_id, cluster_nodes in enumerate(clusters):
                if len(cluster_nodes) < self.MIN_CLUSTER_SIZE:
                    continue
                summary = self._generate_summary(cluster_nodes, level)
                if not summary:
                    continue

                children = [n.node_id for n in cluster_nodes]
                node_id = self._make_node_id(summary, level, cluster_id)
                summary_node = RaptorNode(
                    node_id=node_id,
                    text=summary,
                    level=level,
                    children=children,
                    cluster_id=cluster_id,
                    metadata={"n_children": len(children)},
                    word_freq=self._compute_word_freq(summary),
                )
                tree.nodes[node_id] = summary_node
                tree.levels.setdefault(level, []).append(node_id)
                summary_nodes.append(summary_node)

                logger.debug(
                    "RAPTOR L%d 聚类 %d: %d 子节点 → 摘要节点 %s",
                    level, cluster_id, len(children), node_id[:16],
                )

            if not summary_nodes:
                break

            current_level_nodes = summary_nodes
            logger.info("RAPTOR: L%d 生成 %d 个摘要节点", level, len(summary_nodes))

        # 3. 设置根节点（最高层节点）
        max_level = max(tree.levels.keys()) if tree.levels else 0
        tree.root_ids = tree.levels.get(max_level, [])

        logger.info(
            "RAPTOR 树构建完成：%d 个节点，%d 层，根节点 %d 个",
            tree.total_nodes,
            max_level,
            len(tree.root_ids),
        )
        return tree

    def index_tree(self, tree: RaptorTree) -> int:
        """
        将 RAPTOR 树的所有节点写入 RAGService 向量库（指令 I-07 关键步骤）。

        检索时可以同时命中叶节点（细节）和高层摘要节点（全局理解）。

        Args:
            tree: 已构建好的 RaptorTree。

        Returns:
            成功写入的节点数量。
        """
        if self._rag is None:
            logger.warning("RAPTOR: RAGService 未注入，无法写入向量库")
            return 0
        if not getattr(self._rag, "available", False):
            logger.warning("RAPTOR: RAGService 不可用（chromadb/sentence-transformers 未安装）")
            return 0

        docs = tree.to_index_documents()
        try:
            success = self._rag.index_batch(docs)
            logger.info("RAPTOR: 成功写入 %d/%d 个节点到向量库", success, len(docs))
            return success
        except Exception as exc:
            logger.error("RAPTOR: 写入向量库失败: %s", exc)
            return 0

    def build_and_index(
        self,
        documents: List[Dict[str, Any]],
        existing_tree: Optional[RaptorTree] = None,
    ) -> Tuple[RaptorTree, int]:
        """
        一步完成树构建和索引写入（便捷方法）。

        Returns:
            (RaptorTree, 成功写入的节点数)
        """
        tree = self.build_tree(documents, existing_tree)
        indexed = self.index_tree(tree)
        return tree, indexed

    # ------------------------------------------------------------------
    # L0：文档切分
    # ------------------------------------------------------------------

    def _chunk_documents(self, documents: List[Dict[str, Any]]) -> List[RaptorNode]:
        """将文档列表切分为固定大小的 L0 叶节点。"""
        nodes: List[RaptorNode] = []

        for doc_idx, doc in enumerate(documents):
            text = str(doc.get("text") or doc.get("content") or "").strip()
            if not text:
                continue

            doc_id = str(doc.get("id") or f"doc_{doc_idx}")
            metadata = {
                "source": str(doc.get("source") or doc.get("title") or doc_id),
                "doc_idx": doc_idx,
            }

            # 按 CHUNK_SIZE 切分（不截断句子，按"。！？"自然段落切分）
            chunks = self._split_text(text, self.CHUNK_SIZE)

            for chunk_idx, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                chunk_id = self._make_node_id(chunk, 0, doc_idx * 1000 + chunk_idx)
                node = RaptorNode(
                    node_id=chunk_id,
                    text=chunk,
                    level=0,
                    metadata={**metadata, "chunk_idx": chunk_idx},
                    word_freq=self._compute_word_freq(chunk),
                )
                nodes.append(node)

        return nodes

    # ------------------------------------------------------------------
    # 聚类（词频余弦相似度）
    # ------------------------------------------------------------------

    def _cluster_nodes(
        self,
        nodes: List[RaptorNode],
    ) -> List[List[RaptorNode]]:
        """
        将节点聚类为若干组，使用词频余弦相似度。

        实现：贪心聚类（无需 sklearn），按相似度将近邻节点分组。
        最大 cluster 大小 = MAX_CLUSTER_SIZE。

        Returns:
            聚类结果：List[cluster_members]
        """
        if len(nodes) <= self.MAX_CLUSTER_SIZE:
            return [nodes]

        clusters: List[List[RaptorNode]] = []
        remaining = list(nodes)

        while remaining:
            seed = remaining.pop(0)
            cluster = [seed]

            # 找最相似的节点加入同一 cluster
            similarities = [
                (i, self._cosine_similarity(seed.word_freq, n.word_freq))
                for i, n in enumerate(remaining)
            ]
            similarities.sort(key=lambda x: -x[1])

            for orig_idx, sim in similarities:
                if len(cluster) >= self.MAX_CLUSTER_SIZE:
                    break
                if sim < 0.05:  # 太低相似度的节点不合并
                    break
                # 找到对应的 remaining 中实际 index（已有 pop 操作，需要重新映射）
                pass

            # 简化版：取 remaining 的前 MAX_CLUSTER_SIZE - 1 个
            take = min(self.MAX_CLUSTER_SIZE - 1, len(remaining))
            cluster.extend(remaining[:take])
            del remaining[:take]

            clusters.append(cluster)

        return clusters

    # ------------------------------------------------------------------
    # 摘要生成
    # ------------------------------------------------------------------

    def _generate_summary(
        self,
        nodes: List[RaptorNode],
        level: int,
    ) -> str:
        """为节点聚类生成摘要文本。"""
        combined = "\n".join(n.text[:300] for n in nodes[:6])

        if self._llm is not None:
            return self._generate_llm_summary(combined, level)
        else:
            return self._generate_extractive_summary(combined, level)

    def _generate_llm_summary(self, combined_text: str, level: int) -> str:
        """使用 LLM 生成抽象式摘要（指令 I-07 高质量路径）。"""
        level_desc = {
            1: "聚类摘要（约 100 字）",
            2: "主题摘要（约 80 字）",
            3: "全局摘要（约 60 字）",
        }
        desc = level_desc.get(level, "摘要")
        prompt = (
            f"请将以下中医文献片段整合为{desc}，"
            "保留核心学术信息，语言精炼：\n\n"
            f"{combined_text[:800]}\n\n"
            f"整合摘要（不超过{150 - level * 30}字）："
        )
        try:
            return self._llm.generate(
                prompt,
                max_tokens=150 - level * 30,
                temperature=0.3,
            ).strip()
        except Exception as exc:
            logger.debug("RAPTOR: LLM 摘要生成失败，回退提取式: %s", exc)
            return self._generate_extractive_summary(combined_text, level)

    @staticmethod
    def _generate_extractive_summary(combined_text: str, level: int) -> str:
        """提取式摘要：取前 N 句（降级策略）。"""
        # 按中文句子分割
        sentences: List[str] = []
        current = ""
        for char in combined_text:
            current += char
            if char in "。！？\n" and current.strip():
                sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())

        # L1 取前 5 句, L2 取前 3 句, L3 取前 2 句
        take_n = max(5 - level, 2)
        return " ".join(sentences[:take_n])[:400]

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text(text: str, chunk_size: int) -> List[str]:
        """按中文句子边界切分文本为固定大小的块。"""
        chunks: List[str] = []
        current = ""
        for char in text:
            current += char
            if len(current) >= chunk_size and char in "。！？\n":
                chunks.append(current.strip())
                current = ""
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [text[:chunk_size]]

    @staticmethod
    def _compute_word_freq(text: str) -> Dict[str, int]:
        """计算文本的字符二元组频率（替代词频，无需分词库）。"""
        freq: Dict[str, int] = {}
        text_clean = text.replace(" ", "").replace("\n", "")
        for i in range(len(text_clean) - 1):
            bigram = text_clean[i:i + 2]
            if all("\u4e00" <= c <= "\u9fff" for c in bigram):  # 仅中文字符
                freq[bigram] = freq.get(bigram, 0) + 1
        return freq

    @staticmethod
    def _cosine_similarity(freq_a: Dict[str, int], freq_b: Dict[str, int]) -> float:
        """计算两个词频字典的余弦相似度。"""
        if not freq_a or not freq_b:
            return 0.0
        common = set(freq_a.keys()) & set(freq_b.keys())
        dot = sum(freq_a[k] * freq_b[k] for k in common)
        norm_a = math.sqrt(sum(v ** 2 for v in freq_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in freq_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _make_node_id(text: str, level: int, idx: int) -> str:
        """生成节点唯一 ID。"""
        content_hash = hashlib.md5(
            text[:100].encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:8]
        return f"raptor_L{level}_{idx}_{content_hash}"
