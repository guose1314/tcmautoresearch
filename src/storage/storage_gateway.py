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

指令 I-03：新增 PostgreSQL 持久化支持（学习记录、研究结果）。
"""

from __future__ import annotations

import json
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
        self._pg_engine: Any = None  # SQLAlchemy engine (I-03)

        self._init_neo4j()
        self._init_postgres()
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
                auth=(
                    self._neo4j_config.get("username", "neo4j"),
                    self._neo4j_config.get("password", "neo4j"),
                ),
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

    def _init_postgres(self) -> None:
        """初始化 PostgreSQL 连接（若 enabled=True，使用 SQLAlchemy）。

        指令 I-03：提供学习记录和研究结果的结构化持久化。
        降级策略：若 psycopg2/SQLAlchemy 不可用或连接失败，跳过而不崩溃。
        """
        if not self._postgres_config:
            return
        url = self._postgres_config.get("url", "")
        if not url:
            return
        # 解析环境变量占位符（如 ${TCM_POSTGRES_URL:-...}）
        if url.startswith("${"):
            import os
            import re
            m = re.match(r"\$\{(\w+):-(.+)\}", url)
            if m:
                url = os.environ.get(m.group(1), m.group(2))
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(
                url,
                pool_size=self._postgres_config.get("pool_size", 5),
                max_overflow=self._postgres_config.get("max_overflow", 10),
                pool_timeout=self._postgres_config.get("pool_timeout", 30),
                echo=self._postgres_config.get("echo", False),
                pool_pre_ping=True,
            )
            # 测试连通性
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._pg_engine = engine
            self._ensure_pg_schema()
            logger.info("StorageGateway: PostgreSQL 连接成功 (%s)", url.split("@")[-1])
        except ImportError:
            logger.warning("StorageGateway: sqlalchemy 未安装，PostgreSQL 跳过")
        except Exception as exc:
            logger.warning("StorageGateway: PostgreSQL 初始化失败，结构化数据将跳过: %s", exc)

    def _ensure_pg_schema(self) -> None:
        """确保学习记录表和研究结果表存在（幂等 DDL）。"""
        from sqlalchemy import text
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS learning_records (
                id SERIAL PRIMARY KEY,
                task_id VARCHAR(64) UNIQUE NOT NULL,
                phase VARCHAR(32),
                performance FLOAT,
                feedback FLOAT,
                input_summary TEXT,
                output_summary TEXT,
                ewma_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_lr_phase ON learning_records(phase)",
            "CREATE INDEX IF NOT EXISTS idx_lr_performance ON learning_records(performance)",
            "CREATE INDEX IF NOT EXISTS idx_lr_created ON learning_records(created_at DESC)",
            """
            CREATE TABLE IF NOT EXISTS research_results (
                id SERIAL PRIMARY KEY,
                cycle_id VARCHAR(64) NOT NULL,
                phase VARCHAR(32),
                result_json TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_rr_cycle ON research_results(cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_rr_phase ON research_results(phase)",
        ]
        try:
            with self._pg_engine.begin() as conn:
                for stmt in ddl_statements:
                    conn.execute(text(stmt))
            logger.info("StorageGateway: PostgreSQL schema 已就绪")
        except Exception as exc:
            logger.warning("StorageGateway: PostgreSQL schema 创建失败: %s", exc)

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

        同时向 Neo4j（实体/关系）、PostgreSQL（结构化存档）
        和 ChromaDB（可检索文本）写入。

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

        # 2. 写入 PostgreSQL 结构化存档（I-03）
        self.save_research_result_pg(cycle_id, result)

        # 3. 写入 ChromaDB 向量库
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

    def save_learning_record(self, record: Dict[str, Any]) -> bool:
        """将学习记录持久化到 PostgreSQL（指令 I-03）。

        Args:
            record: LearningRecord.to_dict() 格式的字典，必须含 task_id。

        Returns:
            True 表示写入成功，False 表示跳过（PG 不可用）。
        """
        if self._pg_engine is None:
            return False
        task_id = record.get("task_id")
        if not task_id:
            return False
        try:
            from sqlalchemy import text
            input_data = record.get("input_data", {})
            output_data = record.get("output_data", {})
            stmt = text(
                """
                INSERT INTO learning_records
                    (task_id, phase, performance, feedback, input_summary, output_summary, ewma_score)
                VALUES
                    (:task_id, :phase, :performance, :feedback,
                     :input_summary, :output_summary, :ewma_score)
                ON CONFLICT (task_id) DO UPDATE SET
                    performance   = EXCLUDED.performance,
                    feedback      = EXCLUDED.feedback,
                    output_summary= EXCLUDED.output_summary,
                    ewma_score    = EXCLUDED.ewma_score
                """
            )
            with self._pg_engine.begin() as conn:
                conn.execute(stmt, {
                    "task_id": task_id,
                    "phase": str(input_data.get("metadata", {}).get("phase", "unknown"))[:32],
                    "performance": float(record.get("performance", 0.0)),
                    "feedback": float(record.get("feedback") or 0.0),
                    "input_summary": str(input_data.get("text", ""))[:500],
                    "output_summary": json.dumps(output_data, ensure_ascii=False)[:1000],
                    "ewma_score": float(record.get("ewma_score") or 0.0),
                })
            return True
        except Exception as exc:
            logger.warning("StorageGateway: 学习记录写入 PostgreSQL 失败: %s", exc)
            return False

    def load_learning_records(self, limit: int = 200) -> List[Dict[str, Any]]:
        """从 PostgreSQL 加载历史学习记录（指令 I-03）。

        Args:
            limit: 最大返回条数（按创建时间倒序）。

        Returns:
            学习记录列表，每条为 dict（兼容 LearningRecord.from_dict()）。
        """
        if self._pg_engine is None:
            return []
        try:
            from sqlalchemy import text
            stmt = text(
                "SELECT task_id, phase, performance, feedback, input_summary, "
                "output_summary, ewma_score, created_at "
                "FROM learning_records "
                "ORDER BY created_at DESC LIMIT :limit"
            )
            with self._pg_engine.connect() as conn:
                rows = conn.execute(stmt, {"limit": limit}).fetchall()
            records = []
            for row in rows:
                records.append({
                    "task_id": row[0],
                    "input_data": {"text": row[4] or "", "metadata": {"phase": row[1]}},
                    "output_data": self._safe_json_loads(row[5]),
                    "performance": float(row[2] or 0.0),
                    "feedback": float(row[3] or 0.0) if row[3] is not None else None,
                    "ewma_score": float(row[6] or 0.0),
                    "timestamp": row[7].isoformat() if row[7] else datetime.now().isoformat(),
                })
            logger.info("StorageGateway: 从 PostgreSQL 加载了 %d 条学习记录", len(records))
            return records
        except Exception as exc:
            logger.warning("StorageGateway: 从 PostgreSQL 加载学习记录失败: %s", exc)
            return []

    def save_research_result_pg(self, cycle_id: str, result: Dict[str, Any]) -> bool:
        """将研究结果持久化到 PostgreSQL（指令 I-03）。"""
        if self._pg_engine is None:
            return False
        try:
            from sqlalchemy import text
            stmt = text(
                """
                INSERT INTO research_results (cycle_id, phase, result_json, summary)
                VALUES (:cycle_id, :phase, :result_json, :summary)
                """
            )
            with self._pg_engine.begin() as conn:
                conn.execute(stmt, {
                    "cycle_id": str(cycle_id)[:64],
                    "phase": str(result.get("phase", "unknown"))[:32],
                    "result_json": json.dumps(result, ensure_ascii=False, default=str)[:8000],
                    "summary": str(result.get("summary", ""))[:1000],
                })
            return True
        except Exception as exc:
            logger.warning("StorageGateway: 研究结果写入 PostgreSQL 失败: %s", exc)
            return False

    @property
    def postgres_available(self) -> bool:
        """PostgreSQL 是否已连接就绪。"""
        return self._pg_engine is not None

    @staticmethod
    def _safe_json_loads(text_val: Any) -> Dict[str, Any]:
        """安全解析 JSON 字符串，失败返回空字典。"""
        if not text_val:
            return {}
        try:
            return json.loads(text_val)
        except Exception:
            return {}

    def close(self) -> None:
        """关闭所有底层连接。"""
        if self._neo4j_driver is not None:
            try:
                self._neo4j_driver.close()
            except Exception:
                pass
        self._neo4j_driver = None
        self._neo4j_writer = None
        if self._pg_engine is not None:
            try:
                self._pg_engine.dispose()
            except Exception:
                pass
        self._pg_engine = None

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
