"""存储后端工厂 — 根据配置激活 SQLite / PostgreSQL / Neo4j。

解决 PostgreSQL/Neo4j 代码已存在但从未被激活的问题。
提供统一的工厂方法，根据 config.yml 中的配置自动选择后端。

用法::

    factory = StorageBackendFactory(config)
    factory.initialize()
    # 获取事务协调器
    with factory.transaction() as txn:
        txn.pg_add(entity)
        txn.neo4j_write("CREATE ...")
    factory.close()

配置示例 (config.yml)::

    database:
      type: "postgresql"  # sqlite | postgresql
      path: "./data/tcmautoresearch.db"  # SQLite 路径
      # PostgreSQL 连接
      host: "localhost"
      port: 5432
      name: "tcmautoresearch"
      user: "tcm"
      password_env: "TCM_DB_PASSWORD"  # 从环境变量读取密码

    neo4j:
      enabled: true
      uri: "neo4j://localhost:7687"
      user: "neo4j"
      password_env: "TCM_NEO4J_PASSWORD"
      database: "neo4j"
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from src.infrastructure.persistence import (
    Base,
    DatabaseManager,
)
from src.infrastructure.secret_resolution import resolve_config_password
from src.storage.backfill_ledger import BackfillLedger
from src.storage.degradation_governor import DegradationGovernor
from src.storage.observability import StorageObservability

logger = logging.getLogger(__name__)


def _build_pg_connection_string(db_config: Dict[str, Any]) -> str:
    """从配置构建 PostgreSQL 连接字符串。"""
    host = db_config.get("host", "localhost")
    port = int(db_config.get("port", 5432))
    name = db_config.get("name", "tcmautoresearch")
    user = db_config.get("user", "tcm")
    password = resolve_config_password(db_config, default_env_name="TCM_DB_PASSWORD")
    ssl_mode = db_config.get("ssl_mode", "prefer")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={ssl_mode}"


def _build_sqlite_connection_string(db_config: Dict[str, Any]) -> str:
    """从配置构建 SQLite 连接字符串。"""
    path = db_config.get("path", os.path.join("data", "tcmautoresearch.db"))
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    return f"sqlite:///{abs_path}"


class StorageBackendFactory:
    """根据配置激活存储后端并提供事务协调器。

    Parameters
    ----------
    config :
        项目配置字典（从 config.yml 加载）。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._db_config = self._config.get("database") or {}
        self._neo4j_config = self._config.get("neo4j") or {}

        self._db_manager: Optional[DatabaseManager] = None
        self._neo4j_driver: Any = None
        self._db_type: str = str(self._db_config.get("type", "sqlite")).strip().lower()
        self._initialized = False

        # ── 治理与可观测性组件 ─────────────────────────────────────────
        self._degradation_governor = DegradationGovernor()
        self._backfill_ledger = BackfillLedger()
        self._observability = StorageObservability()

    @property
    def db_type(self) -> str:
        return self._db_type

    @property
    def neo4j_enabled(self) -> bool:
        return bool(self._neo4j_config.get("enabled", False))

    @property
    def db_manager(self) -> Optional[DatabaseManager]:
        return self._db_manager

    @property
    def neo4j_driver(self) -> Any:
        return self._neo4j_driver

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def degradation_governor(self) -> DegradationGovernor:
        return self._degradation_governor

    @property
    def backfill_ledger(self) -> BackfillLedger:
        return self._backfill_ledger

    @property
    def observability(self) -> StorageObservability:
        return self._observability

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def initialize(self) -> Dict[str, Any]:
        """初始化所有配置的后端，返回状态报告。"""
        report: Dict[str, Any] = {
            "db_type": self._db_type,
            "neo4j_enabled": self.neo4j_enabled,
            "pg_status": "skipped",
            "neo4j_status": "skipped",
        }

        # 初始化关系型数据库
        try:
            if self._db_type == "postgresql":
                conn_str = _build_pg_connection_string(self._db_config)
                report["pg_status"] = "connecting"
            else:
                conn_str = _build_sqlite_connection_string(self._db_config)
                report["pg_status"] = "sqlite_fallback"

            self._db_manager = DatabaseManager(
                conn_str,
                echo=bool(self._db_config.get("echo", False)),
                connection_timeout=self._db_config.get("connection_timeout"),
                pool_size=self._db_config.get("connection_pool_size"),
                max_overflow=self._db_config.get("max_overflow"),
            )
            self._db_manager.init_db()

            # 创建默认关系类型
            with self._db_manager.session_scope() as session:
                DatabaseManager.create_default_relationships(session)

            report["pg_status"] = "active"
            report["schema_completeness"] = self._db_manager.get_schema_completeness_report()
            logger.info("关系型数据库初始化完成: %s (%s)", self._db_type, conn_str.split("@")[-1] if "@" in conn_str else "local")
        except Exception as exc:
            report["pg_status"] = f"error: {exc}"
            logger.error("数据库初始化失败: %s", exc)
            raise

        # 初始化 Neo4j（可选）
        if self.neo4j_enabled:
            try:
                from src.storage.neo4j_driver import Neo4jDriver

                uri = self._neo4j_config.get("uri", "neo4j://localhost:7687")
                user = self._neo4j_config.get("user", "neo4j")
                password = resolve_config_password(self._neo4j_config, default_env_name="TCM_NEO4J_PASSWORD")
                database = self._neo4j_config.get("database", "neo4j")

                self._neo4j_driver = Neo4jDriver(
                    uri, (user, password), database=database,
                    max_connection_pool_size=int(self._neo4j_config.get("max_connection_pool_size", 50)),
                    connection_acquisition_timeout=float(self._neo4j_config.get("connection_acquisition_timeout", 60)),
                    max_connection_lifetime=int(self._neo4j_config.get("max_connection_lifetime", 3600)),
                )
                self._neo4j_driver.connect()
                report["neo4j_status"] = "active"
                logger.info("Neo4j 初始化完成: %s", uri)
            except Exception as exc:
                report["neo4j_status"] = f"error: {exc}"
                logger.warning("Neo4j 初始化失败（降级为仅 PG 模式）: %s", exc)
                self._neo4j_driver = None

        self._initialized = True
        self._degradation_governor.set_initial_mode(
            self.get_consistency_state().mode
        )
        return report

    def close(self) -> None:
        """关闭所有后端连接。"""
        if self._db_manager:
            try:
                self._db_manager.close()
            except Exception as exc:
                logger.warning("关闭数据库连接失败: %s", exc)
            self._db_manager = None

        if self._neo4j_driver:
            try:
                self._neo4j_driver.close()
            except Exception as exc:
                logger.warning("关闭 Neo4j 连接失败: %s", exc)
            self._neo4j_driver = None

        self._initialized = False

    # ── 事务 ──────────────────────────────────────────────────────────────

    @contextmanager
    def transaction(self, *, observer: Any = None) -> Iterator[Any]:
        """创建跨后端事务协调器。

        Parameters
        ----------
        observer :
            可选的 ``TransactionObserver``，接收 commit/rollback 结构化结果。

        Yields
        ------
        TransactionCoordinator
            事务协调器实例。提交后可通过 ``txn.last_result`` 访问
            ``TransactionResult``（含阶段耗时与补偿详情）。
        """
        if not self._initialized or self._db_manager is None:
            raise RuntimeError("StorageBackendFactory 尚未初始化")

        from src.storage.transaction import TransactionCoordinator

        session = self._db_manager.get_session()
        txn = None
        try:
            txn = TransactionCoordinator(session, self._neo4j_driver, observer=observer)
            with txn:
                yield txn
            # commit 完成后记录观测（__exit__ 已执行 auto_commit）
            if txn.last_result is not None:
                self._observability.record(txn.last_result)
                self._degradation_governor.record_transaction_result(txn.last_result)
        finally:
            try:
                session.close()
            except Exception as e:
                logger.error(f"关闭 session 失败: {e}", exc_info=True)

    @contextmanager
    def session_scope(self) -> Iterator[Any]:
        """仅 PG 的 session scope（向后兼容）。"""
        if not self._initialized or self._db_manager is None:
            raise RuntimeError("StorageBackendFactory 尚未初始化")
        with self._db_manager.session_scope() as session:
            yield session

    # ── 查询 ──────────────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """检查所有后端健康状态。"""
        result: Dict[str, Any] = {
            "initialized": self._initialized,
            "db_type": self._db_type,
        }
        if self._db_manager:
            result["db_healthy"] = self._db_manager.health_check()
            result["schema_completeness"] = self._db_manager.get_schema_completeness_report()
        else:
            result["db_healthy"] = False

        if self._neo4j_driver and hasattr(self._neo4j_driver, "driver") and self._neo4j_driver.driver:
            try:
                with self._neo4j_driver.driver.session(database=self._neo4j_driver.database) as s:
                    s.run("RETURN 1").consume()
                result["neo4j_healthy"] = True
            except Exception:
                result["neo4j_healthy"] = False
        else:
            result["neo4j_healthy"] = None  # 未启用

        return result

    def _detect_schema_drift(self) -> bool:
        """返回当前后端是否检测到 schema drift。"""
        if not self._initialized or self._db_type != "postgresql" or self._db_manager is None:
            return False

        inspect_schema_drift = getattr(self._db_manager, "inspect_schema_drift", None)
        if not callable(inspect_schema_drift):
            return False

        try:
            report = inspect_schema_drift() or {}
        except Exception as exc:
            logger.debug("schema drift 检测失败，consistency_state 按未检测处理: %s", exc)
            return False

        status = str(report.get("status") or "").strip().lower()
        legacy_enum_count = int(report.get("legacy_enum_count", 0) or 0)
        incompatible_drift_count = int(report.get("incompatible_drift_count", 0) or 0)
        compatibility_variant_count = int(report.get("compatibility_variant_count", 0) or 0)
        return bool(
            legacy_enum_count
            or incompatible_drift_count
            or compatibility_variant_count
            or status in {"degraded", "error"}
        )

    def get_consistency_state(self) -> "StorageConsistencyState":
        """返回当前存储一致性状态合同。

        这是判断存储运行模式（dual_write / pg_only / sqlite_fallback）
        的唯一推荐入口。运行时 metadata、dashboard、运维检查都应
        通过此方法获取一致结论。
        """
        from src.storage.consistency import build_consistency_state

        neo4j_driver_connected = bool(
            self._neo4j_driver
            and hasattr(self._neo4j_driver, "driver")
            and self._neo4j_driver.driver
        )
        neo4j_status: str
        if not self._initialized:
            neo4j_status = "uninitialized"
        elif not self.neo4j_enabled:
            neo4j_status = "skipped"
        elif neo4j_driver_connected:
            neo4j_status = "active"
        else:
            neo4j_status = "error: driver not connected"

        pg_status: str
        if not self._initialized:
            pg_status = "uninitialized"
        elif self._db_manager is not None:
            pg_status = "active"
        else:
            pg_status = "error: db_manager not available"

        return build_consistency_state(
            initialized=self._initialized,
            db_type=self._db_type,
            pg_status=pg_status,
            neo4j_enabled=self.neo4j_enabled,
            neo4j_status=neo4j_status,
            neo4j_driver_connected=neo4j_driver_connected,
            schema_drift_detected=self._detect_schema_drift(),
        )

    def get_storage_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息。"""
        stats: Dict[str, Any] = {"db_type": self._db_type}
        if self._db_manager:
            try:
                from src.infrastructure.persistence import (
                    Document,
                    Entity,
                    EntityRelationship,
                    RelationshipType,
                    ResearchRecord,
                )
                with self._db_manager.session_scope() as session:
                    stats["documents"] = session.query(Document).count()
                    stats["entities"] = session.query(Entity).count()
                    stats["relationships"] = session.query(EntityRelationship).count()
                    stats["relationship_types"] = session.query(RelationshipType).count()
                    stats["research_records"] = session.query(ResearchRecord).count()
            except Exception as exc:
                stats["error"] = str(exc)

        if self._neo4j_driver and hasattr(self._neo4j_driver, "get_graph_statistics"):
            try:
                stats["neo4j"] = self._neo4j_driver.get_graph_statistics()
            except Exception as exc:
                stats["neo4j_error"] = str(exc)

        return stats

    def get_governance_report(self) -> Dict[str, Any]:
        """获取完整的存储治理与可观测性报告。

        聚合降级治理、backfill 台账和事务观测指标。
        """
        return {
            "consistency_state": self.get_consistency_state().to_dict(),
            "degradation": self._degradation_governor.to_governance_report(),
            "backfill": self._backfill_ledger.get_summary(),
            "observability": self._observability.get_health_report(),
        }
