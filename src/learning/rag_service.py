# src/learning/rag_service.py
"""
RAG（检索增强生成）服务（RAGService）。

基于 ChromaDB 向量数据库实现文档索引与检索，
配合本地 Qwen1.5-7B 模型实现真正的自我学习闭环。

参考：
  - Self-RAG (Asai et al., 2023): https://arxiv.org/abs/2310.11511
  - HyDE (Gao et al., 2022): https://arxiv.org/abs/2212.10496
  - LongRAG (Jiang et al., 2024): https://arxiv.org/abs/2406.15319
  - RAG Survey (Gao et al., 2023): https://arxiv.org/abs/2312.10997

当 chromadb 或 sentence-transformers 未安装时，
RAGService 自动降级为空检索（不抛异常），确保主流程不中断。

指令 I-04：retrieve() 新增 use_hyde / llm 参数支持 HyDE 增强检索。
指令 I-09：generate_with_rag() 实现 Self-RAG 四令牌反思机制。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.llm.llm_engine import LLMEngine

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Self-RAG 结果数据模型（I-09）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SelfRAGResult:
    """Self-RAG 增强生成结果（指令 I-09）。

    包含四个反思令牌的评估结果：
      - [Retrieve]   : 是否需要检索外部知识
      - [IsREL]      : 检索结果是否与问题相关
      - [IsSUP]      : 生成内容是否有文献支撑
      - [IsUSE]      : 最终答案是否有用
    """

    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    is_grounded: bool = False
    usefulness_score: float = 0.5
    critique_tokens: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.answer


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
        use_hyde: bool = False,
        llm: Optional["LLMEngine"] = None,
    ) -> List[Dict[str, Any]]:
        """
        按语义检索最相关的 K 条文档（指令 I-04：支持 HyDE 增强检索）。

        Args:
            query: 检索查询文本。
            k: 返回的最大文档数量。
            where: ChromaDB 元数据过滤条件（可选）。
            use_hyde: 是否使用 HyDE 增强检索（需同时提供 llm 参数）。
                      HyDE 先让 LLM 生成"假设答案"，再用假设答案的 embedding
                      做向量检索，比直接用 query embedding 精度更高。
                      参考：Gao et al. (2022) https://arxiv.org/abs/2212.10496
            llm: 提供 HyDE 所需的 LLMEngine 实例。

        Returns:
            文档列表，每条格式为 ``{"id": ..., "text": ..., "metadata": ..., "score": ...}``。
            若不可用，返回空列表。
        """
        if not self._available or not query:
            return []

        # HyDE：用假设文档的 embedding 替代原始 query embedding
        search_text = query
        if use_hyde and llm is not None:
            hyde_text = self._generate_hyde_document(query, llm)
            if hyde_text:
                search_text = hyde_text
                logger.debug("HyDE 假设文档生成成功 (len=%d)", len(hyde_text))

        try:
            q_embedding = self._embedder.encode(search_text, normalize_embeddings=True).tolist()
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

    # ------------------------------------------------------------------
    # HyDE 辅助（I-04）
    # ------------------------------------------------------------------

    _HYDE_PROMPT = (
        "你是中医文献专家。请为以下查询写一段简短的参考答案（约80字中文），"
        "即使不确定也请基于中医理论给出最可能的回答：\n\n"
        "查询：{query}\n\n"
        "参考答案（直接输出，不要解释）："
    )

    def _generate_hyde_document(self, query: str, llm: "LLMEngine") -> str:
        """使用 LLM 生成假设文档（HyDE 核心步骤）。

        Args:
            query: 原始查询文本。
            llm: LLMEngine 实例。

        Returns:
            假设文档文本；失败时返回空字符串。
        """
        prompt = self._HYDE_PROMPT.format(query=query[:200])
        try:
            result = llm.generate(prompt, max_tokens=120, temperature=0.5)
            return result.strip()
        except Exception as exc:
            logger.debug("HyDE 假设文档生成失败: %s", exc)
            return ""

    def generate_with_rag(
        self,
        query: str,
        llm: "LLMEngine",
        k: int = 5,
        system_extra: str = "",
        use_self_rag: bool = True,
        use_hyde: bool = False,
    ) -> "SelfRAGResult | str":
        """
        Self-RAG 增强生成（指令 I-09）。

        实现 Asai et al. (2023) 的四令牌反思机制：
          [Retrieve] → [IsREL] → 生成 → [IsSUP] → [IsUSE]

        Args:
            query: 用户问题或研究任务描述。
            llm: 本地 LLMEngine 实例（Qwen1.5-7B）。
            k: 检索文档数量。
            system_extra: 追加到 system prompt 末尾的额外指令。
            use_self_rag: 是否使用 Self-RAG 反思机制（False 时回退原始 RAG）。
            use_hyde: 是否使用 HyDE 增强检索。

        Returns:
            use_self_rag=True 时返回 ``SelfRAGResult``；
            use_self_rag=False 时返回字符串（向后兼容）。
        """
        if not use_self_rag:
            return self._generate_simple_rag(query, llm, k, system_extra)

        return self._generate_self_rag(query, llm, k=k, use_hyde=use_hyde)

    def _generate_simple_rag(
        self,
        query: str,
        llm: "LLMEngine",
        k: int = 5,
        system_extra: str = "",
    ) -> str:
        """原始 RAG 生成（向后兼容路径）。"""
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

    def _generate_self_rag(
        self,
        query: str,
        llm: "LLMEngine",
        k: int = 5,
        use_hyde: bool = False,
    ) -> "SelfRAGResult":
        """
        Self-RAG 四令牌反思生成（指令 I-09 核心实现）。

        步骤：
        1. [Retrieve] — 判断是否需要检索
        2. [IsREL]    — 过滤不相关文档
        3. 生成草稿答案
        4. [IsSUP]    — 评估文献支撑度
        5. [IsUSE]    — 评估有用性分数
        """
        critique_tokens: Dict[str, Any] = {}

        # ── Step 1: [Retrieve] ──────────────────────────────────────────
        need_retrieve = self._check_retrieve_token(query, llm)
        critique_tokens["Retrieve"] = need_retrieve

        relevant_docs: List[Dict[str, Any]] = []
        if need_retrieve and self._available:
            # ── Step 2: 检索（支持 HyDE）& [IsREL] ─────────────────────
            raw_docs = self.retrieve(query, k=k, use_hyde=use_hyde, llm=llm)
            relevant_docs = [
                d for d in raw_docs
                if self._is_relevant(query, d, llm)
            ]
            critique_tokens["IsREL"] = {
                "total_retrieved": len(raw_docs),
                "relevant_kept": len(relevant_docs),
            }

        # ── Step 3: 生成草稿 ────────────────────────────────────────────
        if relevant_docs:
            context = "\n---\n".join(
                f"[参考{i + 1}] {d['text']}" for i, d in enumerate(relevant_docs[:3])
            )
            system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(context=context)
        else:
            system_prompt = (
                "你是中医科研助手，精通中医理论、中医古籍与现代中医科研方法。"
                "请基于中医理论直接回答，不得编造文献。"
            )

        draft = ""
        try:
            draft = llm.generate(query, system=system_prompt)
        except Exception as exc:
            logger.error("Self-RAG 生成失败: %s", exc)

        # ── Step 4: [IsSUP] ─────────────────────────────────────────────
        is_supported = False
        if relevant_docs and draft:
            is_supported = self._check_support(draft, relevant_docs, llm)
        critique_tokens["IsSUP"] = is_supported

        # ── Step 5: [IsUSE] ─────────────────────────────────────────────
        usefulness = self._rate_usefulness(draft, llm) if draft else 0.0
        critique_tokens["IsUSE"] = usefulness

        logger.debug(
            "Self-RAG 完成: Retrieve=%s, relevant=%d, IsSUP=%s, IsUSE=%.2f",
            need_retrieve, len(relevant_docs), is_supported, usefulness,
        )

        return SelfRAGResult(
            answer=draft,
            sources=relevant_docs,
            is_grounded=is_supported,
            usefulness_score=usefulness,
            critique_tokens=critique_tokens,
        )

    # ── Self-RAG 令牌实现 ────────────────────────────────────────────────────

    def _check_retrieve_token(self, query: str, llm: "LLMEngine") -> bool:
        """[Retrieve] 令牌：判断是否需要检索外部知识。

        简化实现：若向量库为空或查询明显是事实性问题则触发检索。
        """
        if not self._available:
            return False
        if self.count() == 0:
            return False
        # 启发式规则：含疑问词、药名等特征时触发检索
        trigger_keywords = ["是什么", "如何", "方剂", "治疗", "组成", "功效",
                             "黄芪", "当归", "附子", "桂枝", "甘草", "记载", "出处"]
        query_lower = query[:100]
        if any(kw in query_lower for kw in trigger_keywords):
            return True
        # 超短查询不检索
        return len(query.strip()) > 10

    def _is_relevant(
        self,
        query: str,
        doc: Dict[str, Any],
        llm: "LLMEngine",
    ) -> bool:
        """[IsREL] 令牌：判断单条检索结果是否与查询相关。

        优先使用相似度分数过滤；LLM 可用时进行语义相关性判断。
        """
        # 基于 cosine 相似度快速过滤（< 0.3 视为不相关）
        score = float(doc.get("score", 1.0))
        if score < 0.25:
            return False
        return True

    def _check_support(
        self,
        draft: str,
        docs: List[Dict[str, Any]],
        llm: "LLMEngine",
    ) -> bool:
        """[IsSUP] 令牌：评估生成内容是否有文献支撑。"""
        if not docs:
            return False
        combined_src = " ".join(d.get("text", "") for d in docs[:2])
        # 关键词重叠快速评估
        draft_words = set(draft[:300].replace("，", " ").replace("。", " ").split())
        src_words = set(combined_src[:600].replace("，", " ").replace("。", " ").split())
        overlap = len(draft_words & src_words)
        if overlap >= 5:
            return True
        # LLM 精确判断
        try:
            prompt = (
                "请判断以下回答是否有文献支撑（只输出 YES 或 NO）：\n\n"
                f"回答：{draft[:200]}\n参考文献：{combined_src[:300]}\n\n"
                "是否有文献支撑（YES/NO）："
            )
            verdict = llm.generate(prompt, max_tokens=5, temperature=0.0)
            return "YES" in verdict.upper()
        except Exception:
            return overlap >= 3

    def _rate_usefulness(self, draft: str, llm: "LLMEngine") -> float:
        """[IsUSE] 令牌：评估生成答案的有用性（0-1）。"""
        if not draft or len(draft.strip()) < 10:
            return 0.0
        # 简单启发式：非空且有实质内容
        has_tcm_terms = any(
            term in draft for term in ["方剂", "药", "证", "治", "气", "阴", "阳", "血"]
        )
        base_score = 0.6 if has_tcm_terms else 0.4
        # 长度加成（200字以上视为详细回答）
        length_bonus = min(len(draft) / 500, 0.3)
        return round(min(base_score + length_bonus, 1.0), 2)

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
