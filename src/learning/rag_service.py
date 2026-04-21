# src/learning/rag_service.py
"""
RAG（检索增强生成）服务（RAGService）。

基于 ChromaDB 向量数据库实现文档索引与检索，
配合本地 Qwen1.5-7B 模型实现真正的自我学习闭环。

参考：
  - Self-RAG (Asai et al., 2023): https://arxiv.org/abs/2310.11511
  - LongRAG (Jiang et al., 2024): https://arxiv.org/abs/2406.15319
  - RAG Survey (Gao et al., 2023): https://arxiv.org/abs/2312.10997

当 chromadb 或 sentence-transformers 未安装时，
RAGService 自动降级为空检索（不抛异常），确保主流程不中断。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.llm.llm_engine import LLMEngine

logger = logging.getLogger(__name__)


class RAGService:
    """
    基于 ChromaDB 的检索增强生成服务。

    功能：
    1. ``index_document()``   — 将文档 embedding 并写入向量库
    2. ``retrieve()``         — 按语义检索最相关的 K 条文档
    3. ``generate_with_rag()``— RAG 增强生成：检索上下文 + LLM 生成

    若 ChromaDB 不可用，所有方法以空结果返回，不影响主流程。

    用法::

        rag = RAGService(persist_dir="./data/chroma_db")
        rag.index_document("doc_001", "五苓散由茯苓、猪苓、泽泻、白术、桂枝组成")
        results = rag.retrieve("水肿方剂", k=5)
    """

    _SYSTEM_PROMPT_TEMPLATE = (
        "你是中医科研助手，精通中医理论、中医古籍与现代中医科研方法。\n"
        "以下是与问题相关的参考资料：\n"
        "---\n"
        "{context}\n"
        "---\n"
        "请基于上述参考资料，结合中医理论，给出准确、严谨的回答。不得编造文献。"
    )

    def __init__(
        self,
        persist_dir: str = "./data/chroma_db",
        collection_name: str = "tcm_research",
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        """
        Args:
            persist_dir: ChromaDB 本地持久化目录。
            collection_name: 向量集合名称。
            embedding_model: sentence-transformers 模型名称（支持中文的多语言模型）。
        """
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._client: Any = None
        self._collection: Any = None
        self._embedder: Any = None
        self._available = False

        self._init_chromadb()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _init_chromadb(self) -> None:
        """初始化 ChromaDB 客户端与 embedding 模型（失败时降级）。"""
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB 初始化成功: %s", self.persist_dir)
        except ImportError:
            logger.warning("chromadb 未安装，RAGService 将以降级模式运行（空检索）。"
                           "安装方法: pip install chromadb")
            return
        except Exception as exc:
            logger.warning("ChromaDB 初始化失败，RAGService 降级: %s", exc)
            return

        try:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(self.embedding_model)
            logger.info("Embedding 模型加载成功: %s", self.embedding_model)
            self._available = True
        except ImportError:
            logger.warning("sentence-transformers 未安装，RAGService 降级（空检索）。"
                           "安装方法: pip install sentence-transformers")
        except Exception as exc:
            logger.warning("Embedding 模型加载失败，RAGService 降级: %s", exc)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """RAGService 是否完全可用（ChromaDB + embedding 模型均已就绪）。"""
        return self._available

    def index_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        将文档 embedding 并写入向量库。

        Args:
            doc_id: 文档唯一 ID。
            text: 文档文本内容。
            metadata: 可选元数据（如 ``{"cycle_id": "...", "phase": "analyze"}``）。

        Returns:
            True 表示写入成功，False 表示跳过（RAGService 不可用或写入失败）。
        """
        if not self._available or not text:
            return False

        try:
            embedding = self._embedder.encode(text, normalize_embeddings=True).tolist()
            meta = {
                "indexed_at": datetime.now().isoformat(),
                **(metadata or {}),
            }
            # ChromaDB upsert 语义保证幂等
            self._collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text[:2000]],  # 截断超长文本
                metadatas=[meta],
            )
            logger.debug("RAG 索引文档: %s (len=%d)", doc_id, len(text))
            return True
        except Exception as exc:
            logger.warning("RAG 索引失败 (doc_id=%s): %s", doc_id, exc)
            return False

    def retrieve(
        self,
        query: str,
        k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        按语义检索最相关的 K 条文档。

        Args:
            query: 检索查询文本。
            k: 返回的最大文档数量。
            where: ChromaDB 元数据过滤条件（可选）。

        Returns:
            文档列表，每条格式为 ``{"id": ..., "text": ..., "metadata": ..., "score": ...}``。
            若不可用，返回空列表。
        """
        if not self._available or not query:
            return []

        try:
            q_embedding = self._embedder.encode(query, normalize_embeddings=True).tolist()
            query_kwargs: Dict[str, Any] = {
                "query_embeddings": [q_embedding],
                "n_results": min(k, max(1, self._collection.count())),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                query_kwargs["where"] = where

            response = self._collection.query(**query_kwargs)
            results: List[Dict[str, Any]] = []
            ids = (response.get("ids") or [[]])[0]
            docs = (response.get("documents") or [[]])[0]
            metas = (response.get("metadatas") or [[]])[0]
            distances = (response.get("distances") or [[]])[0]

            for doc_id, text, meta, dist in zip(ids, docs, metas, distances):
                results.append({
                    "id": doc_id,
                    "text": text,
                    "metadata": meta or {},
                    "score": round(1.0 - float(dist), 4),  # cosine 距离转相似度
                })
            return results
        except Exception as exc:
            logger.warning("RAG 检索失败 (query=%s): %s", query[:50], exc)
            return []

    def generate_with_rag(
        self,
        query: str,
        llm: "LLMEngine",
        k: int = 5,
        system_extra: str = "",
    ) -> str:
        """
        RAG 增强生成：先检索相关上下文，再调用 LLM 生成回答。

        Args:
            query: 用户问题或研究任务描述。
            llm: 本地 LLMEngine 实例（Qwen1.5-7B）。
            k: 检索文档数量。
            system_extra: 追加到 system prompt 末尾的额外指令。

        Returns:
            LLM 生成的回答文本；若 LLM 不可用，返回空字符串。
        """
        docs = self.retrieve(query, k=k)
        if docs:
            context = "\n---\n".join(
                f"[参考{i + 1}] {d['text']}" for i, d in enumerate(docs)
            )
        else:
            context = "（暂无相关参考资料，请基于中医理论直接回答）"

        system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(context=context)
        if system_extra:
            system_prompt = f"{system_prompt}\n{system_extra}"

        try:
            return llm.generate(query, system=system_prompt)
        except Exception as exc:
            logger.error("RAG 增强生成失败: %s", exc)
            return ""

    def index_batch(
        self,
        documents: List[Dict[str, Any]],
    ) -> int:
        """
        批量索引文档。

        Args:
            documents: 文档列表，每条须含 ``id`` 和 ``text`` 字段，可选 ``metadata``。

        Returns:
            成功索引的文档数量。
        """
        success_count = 0
        for doc in documents:
            doc_id = doc.get("id") or hashlib.md5(
                doc.get("text", "").encode(), usedforsecurity=False
            ).hexdigest()
            if self.index_document(doc_id, doc.get("text", ""), doc.get("metadata")):
                success_count += 1
        return success_count

    def count(self) -> int:
        """返回向量库中已索引的文档数量。"""
        if not self._available or self._collection is None:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0
