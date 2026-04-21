# src/storage/storage_gateway.py
"""
StorageGateway — 统一存储门面（Facade）。

将 Neo4j（图谱）、PostgreSQL（结构化数据）、SQLite（轻量级备选）
及 ChromaDB（向量检索）统一封装为单一接口，
消除上层业务（ResearchPipeline / SelfLearningEngine 等）
直接依赖底层驱动的耦合问题。

设计原则：
  - 故障容忍：任一后端不可用时降级而不崩溃
  - 最小配置：从 config.yml 读取所有连接参数
  - 幂等写入：底层均使用 UPSERT / MERGE 语义
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StorageGateway:
    """
    统一存储门面。

    提供以下方法：
      - ``save_research_result()``  — 持久化研究阶段结果
      - ``load_research_results()`` — 加载历史研究结果
      - ``save_entities()``         — 批量写入实体到图谱
      - ``save_relations()``        — 批量写入关系到图谱
      - ``index_for_rag()``         — 将文本写入 ChromaDB 向量库

    用法::

        gw = StorageGateway.from_config(config)
        gw.save_research_result("cycle_001", result)
    """

    def __init__(
        self,
        neo4j_config: Optional[Dict[str, Any]] = None,
        postgres_config: Optional[Dict[str, Any]] = None,
        rag_persist_dir: str = "./data/chroma_db",
    ) -> None:
        self._neo4j_config = neo4j_config or {}
        self._postgres_config = postgres_config or {}
        self._rag_persist_dir = rag_persist_dir

        self._neo4j_driver: Any = None
        self._neo4j_writer: Any = None
        self._rag_service: Any = None

        self._init_neo4j()
        self._init_rag()

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "StorageGateway":
        """
        从应用配置字典创建 StorageGateway 实例。

        Args:
            config: 应用根配置字典（对应 config.yml）。

        Returns:
            StorageGateway 实例（若配置缺失则以空配置创建）。
        """
        db_config = config.get("database") or {}
        neo4j_cfg = db_config.get("neo4j") or {}
        pg_cfg = db_config.get("postgresql") or {}
        rag_dir = (config.get("rag") or {}).get("persist_dir", "./data/chroma_db")

        return cls(
            neo4j_config=neo4j_cfg if neo4j_cfg.get("enabled") else None,
            postgres_config=pg_cfg if pg_cfg.get("enabled") else None,
            rag_persist_dir=rag_dir,
        )

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _init_neo4j(self) -> None:
        """初始化 Neo4j 连接（若 enabled=True）。"""
        if not self._neo4j_config:
            return
        try:
            from src.storage.neo4j_driver import Neo4jDriver
            from src.storage.neo4j_writer import TCMGraphWriter

            driver = Neo4jDriver(
                uri=self._neo4j_config.get("uri", "bolt://localhost:7687"),
                username=self._neo4j_config.get("username", "neo4j"),
                password=self._neo4j_config.get("password", "neo4j"),
                database=self._neo4j_config.get("database", "neo4j"),
            )
            driver.connect()
            self._neo4j_driver = driver
            self._neo4j_writer = TCMGraphWriter(driver)
            logger.info("StorageGateway: Neo4j 连接成功")
        except Exception as exc:
            logger.warning("StorageGateway: Neo4j 初始化失败，图谱写入将跳过: %s", exc)

    def _init_rag(self) -> None:
        """初始化 RAGService（ChromaDB）。"""
        try:
            from src.learning.rag_service import RAGService

            svc = RAGService(persist_dir=self._rag_persist_dir)
            if svc.available:
                self._rag_service = svc
                logger.info("StorageGateway: RAGService 初始化成功")
            else:
                logger.info("StorageGateway: RAGService 不可用（chromadb/sentence-transformers 未安装），向量检索跳过")
        except Exception as exc:
            logger.debug("StorageGateway: RAGService 初始化失败: %s", exc)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def save_research_result(
        self,
        cycle_id: str,
        result: Dict[str, Any],
    ) -> None:
        """
        持久化研究阶段结果。

        同时向 Neo4j（实体/关系）和 ChromaDB（可检索文本）写入。

        Args:
            cycle_id: 当前研究周期 ID。
            result: 研究阶段输出字典。
        """
        # 1. 写入 Neo4j 图谱
        if self._neo4j_writer is not None:
            try:
                self._neo4j_writer.write_analysis_result(result, cycle_id=cycle_id)
            except Exception as exc:
                logger.warning("StorageGateway: Neo4j 写入失败: %s", exc)

        # 2. 写入 ChromaDB 向量库
        if self._rag_service is not None:
            self._index_result_to_rag(cycle_id, result)

    def save_entities(
        self,
        entities: List[Dict[str, Any]],
        cycle_id: str = "",
    ) -> None:
        """批量写入实体到 Neo4j 图谱。"""
        if self._neo4j_writer is None:
            return
        try:
            from src.storage.neo4j_driver import Neo4jNode

            nodes = []
            for entity in entities:
                if not isinstance(entity, dict) or not entity.get("name"):
                    continue
                node_id = entity.get("id") or str(entity.get("name"))
                nodes.append(
                    Neo4jNode(
                        id=node_id,
                        label=entity.get("type", "Entity"),
                        properties={**entity, "id": node_id, "_cycle_id": cycle_id},
                    )
                )
            if nodes:
                self._neo4j_driver.batch_create_nodes(nodes)
        except Exception as exc:
            logger.warning("StorageGateway: 批量写入实体失败: %s", exc)

    def save_relations(
        self,
        relations: List[Dict[str, Any]],
        cycle_id: str = "",
    ) -> None:
        """批量写入关系到 Neo4j 图谱。"""
        if self._neo4j_writer is None:
            return
        try:
            from src.storage.neo4j_driver import Neo4jEdge

            edges = []
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                source = str(rel.get("source") or "").strip()
                target = str(rel.get("target") or "").strip()
                rel_type = str(rel.get("type") or "RELATED_TO").strip()
                if not source or not target:
                    continue
                edges.append(
                    Neo4jEdge(
                        source_id=source,
                        target_id=target,
                        relationship_type=rel_type.upper(),
                        properties={"_cycle_id": cycle_id},
                    )
                )
            if edges:
                self._neo4j_driver.batch_create_relationships(edges)
        except Exception as exc:
            logger.warning("StorageGateway: 批量写入关系失败: %s", exc)

    def index_for_rag(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """将文本写入 ChromaDB 向量库，供后续 RAG 检索。"""
        if self._rag_service is None:
            return False
        try:
            return self._rag_service.index_document(doc_id, text, metadata)
        except Exception as exc:
            logger.warning("StorageGateway: RAG 索引失败: %s", exc)
            return False

    def retrieve_similar(
        self,
        query: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """从 ChromaDB 检索与查询语义相近的文档。"""
        if self._rag_service is None:
            return []
        try:
            return self._rag_service.retrieve(query, k=k)
        except Exception as exc:
            logger.warning("StorageGateway: RAG 检索失败: %s", exc)
            return []

    def close(self) -> None:
        """关闭所有底层连接。"""
        if self._neo4j_driver is not None:
            try:
                self._neo4j_driver.close()
            except Exception:
                pass
        self._neo4j_driver = None
        self._neo4j_writer = None

    # ------------------------------------------------------------------
    # 私有辅助
    # ------------------------------------------------------------------

    def _index_result_to_rag(
        self,
        cycle_id: str,
        result: Dict[str, Any],
    ) -> None:
        """提取研究结果中的关键文本并写入 RAG 向量库。"""
        import hashlib

        phase = result.get("phase", "unknown")
        parts: List[str] = []

        for key in ("summary", "interpretation", "hypothesis", "reflections"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip()[:500])
            elif isinstance(val, list):
                for item in val[:2]:
                    if isinstance(item, dict):
                        text = str(item.get("reflection") or item.get("title") or "")
                    else:
                        text = str(item)
                    if text.strip():
                        parts.append(text.strip()[:200])

        if not parts:
            return

        combined = "\n".join(parts)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        doc_id = f"gw_{cycle_id}_{phase}_{ts}_{hashlib.md5(combined.encode(), usedforsecurity=False).hexdigest()[:8]}"
        self._rag_service.index_document(
            doc_id=doc_id,
            text=combined,
            metadata={"cycle_id": cycle_id, "phase": phase, "indexed_at": ts},
        )
