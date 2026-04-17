"""跨存储后端事务协调器。

保证 PostgreSQL + Neo4j 跨引擎原子性：
- PG flush（验证约束）→ Neo4j 执行 → PG commit
- Neo4j 失败时 PG 从未 commit，可安全 rollback
- PG commit 失败时补偿已执行的 Neo4j 操作

用法::

    with TransactionCoordinator(pg_session, neo4j_driver) as txn:
        txn.pg_add(entity)
        txn.neo4j_write("CREATE (n:Herb {name: $name})", name="黄芪")
        # 退出 with 块时自动 commit；异常时自动 rollback + 补偿
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

from .neo4j_driver import _safe_cypher_label

logger = logging.getLogger(__name__)


@dataclass
class _Neo4jPendingOp:
    """待提交的 Neo4j 写操作。"""
    cypher: str
    params: Dict[str, Any]
    compensate_cypher: Optional[str] = None
    compensate_params: Optional[Dict[str, Any]] = None


@dataclass
class TransactionResult:
    """事务执行结果。"""
    success: bool
    pg_committed: bool = False
    neo4j_committed: bool = False
    storage_mode: str = ""
    error: Optional[str] = None
    compensations_applied: int = 0
    neo4j_error: Optional[str] = None
    compensation_details: List[str] = field(default_factory=list)
    needs_backfill: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class TransactionCoordinator:
    """跨 PostgreSQL + Neo4j 的事务协调器。

    策略：prepare-both → commit-both
    1. 在 PostgreSQL session 中累积所有变更（flush 验证约束，但不 commit）
    2. 收集所有 Neo4j 写操作到待执行队列
    3. commit 阶段：先执行 Neo4j 操作（PG 尚未 commit，可安全回滚）
    4. Neo4j 全部成功后再 PG commit
    5. 如果 Neo4j 失败：补偿已执行的 Neo4j 操作 + PG rollback（从未 commit）
    6. 如果 PG commit 失败：补偿已执行的 Neo4j 操作

    Parameters
    ----------
    pg_session :
        SQLAlchemy Session（调用方负责创建；coordinator 负责 commit/rollback）。
    neo4j_driver :
        Neo4jDriver 实例；传 None 时只使用 PG（降级模式）。
    """

    def __init__(
        self,
        pg_session: Any,
        neo4j_driver: Any = None,
        *,
        auto_commit: bool = True,
    ):
        self._pg = pg_session
        self._neo4j = neo4j_driver
        self._auto_commit = auto_commit
        self._neo4j_pending: List[_Neo4jPendingOp] = []
        self._neo4j_executed: List[_Neo4jPendingOp] = []
        self._committed = False
        self._rolledback = False

    # ── Context Manager ──────────────────────────────────────────────────

    def __enter__(self) -> "TransactionCoordinator":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.rollback()
            return False
        if self._auto_commit and not self._committed and not self._rolledback:
            result = self.commit()
            if not result.success:
                raise RuntimeError(f"事务提交失败: {result.error}")
        return False

    @property
    def pg_session(self) -> Any:
        """暴露当前 PG session，供同一事务边界内的仓储层复用。"""
        return self._pg

    # ── PostgreSQL 操作 ──────────────────────────────────────────────────

    def pg_add(self, instance: Any) -> None:
        """向 PG session 添加对象（与后续 commit 一起提交）。"""
        self._pg.add(instance)

    def pg_add_all(self, instances: Sequence[Any]) -> None:
        self._pg.add_all(instances)

    def pg_flush(self) -> None:
        """刷新 PG session 以获取生成的 ID，但不提交。"""
        self._pg.flush()

    def pg_query(self, *args: Any, **kwargs: Any) -> Any:
        """透传 session.query()。"""
        return self._pg.query(*args, **kwargs)

    def pg_execute(self, *args: Any, **kwargs: Any) -> Any:
        """透传 session.execute()。"""
        return self._pg.execute(*args, **kwargs)

    # ── Neo4j 操作（延迟执行）─────────────────────────────────────────

    def neo4j_write(
        self,
        cypher: str,
        compensate_cypher: Optional[str] = None,
        **params: Any,
    ) -> None:
        """注册一个 Neo4j 写操作（commit 时才真正执行）。

        Parameters
        ----------
        cypher :
            Cypher 写语句。
        compensate_cypher :
            可选的补偿语句，在 Neo4j 部分失败时用于回滚已执行的操作。
        **params :
            Cypher 参数。
        """
        self._neo4j_pending.append(_Neo4jPendingOp(
            cypher=cypher,
            params=dict(params),
            compensate_cypher=compensate_cypher,
            compensate_params=dict(params) if compensate_cypher else None,
        ))

    def neo4j_batch_nodes(
        self,
        nodes: Sequence[Any],
        compensate: bool = True,
    ) -> None:
        """批量注册 Neo4j 节点创建。"""
        for node in nodes:
            props = dict(node.properties or {})
            props["id"] = node.id
            safe_label = _safe_cypher_label(node.label)
            cypher = (
                f"MERGE (n:{safe_label} {{id: $id}}) "
                f"SET n += $props"
            )
            comp = f"MATCH (n:{safe_label} {{id: $id}}) DETACH DELETE n" if compensate else None
            self._neo4j_pending.append(_Neo4jPendingOp(
                cypher=cypher,
                params={"id": node.id, "props": props},
                compensate_cypher=comp,
                compensate_params={"id": node.id} if comp else None,
            ))

    def neo4j_batch_edges(
        self,
        edges: Sequence[Any],
        compensate: bool = True,
    ) -> None:
        """批量注册 Neo4j 关系创建。edges 为 (Neo4jEdge, src_label, tgt_label) 三元组。"""
        for edge, src_label, tgt_label in edges:
            safe_src = _safe_cypher_label(src_label)
            safe_tgt = _safe_cypher_label(tgt_label)
            safe_rel = _safe_cypher_label(edge.relationship_type)
            cypher = (
                f"MATCH (a:{safe_src} {{id: $src_id}}) "
                f"MATCH (b:{safe_tgt} {{id: $tgt_id}}) "
                f"MERGE (a)-[r:{safe_rel}]->(b) "
                f"SET r += $props"
            )
            comp = (
                f"MATCH (a:{safe_src} {{id: $src_id}})-[r:{safe_rel}]->"
                f"(b:{safe_tgt} {{id: $tgt_id}}) DELETE r"
            ) if compensate else None
            self._neo4j_pending.append(_Neo4jPendingOp(
                cypher=cypher,
                params={
                    "src_id": edge.source_id,
                    "tgt_id": edge.target_id,
                    "props": dict(edge.properties or {}),
                },
                compensate_cypher=comp,
                compensate_params={
                    "src_id": edge.source_id,
                    "tgt_id": edge.target_id,
                } if comp else None,
            ))

    # ── Commit / Rollback ────────────────────────────────────────────────

    def commit(self) -> TransactionResult:
        """执行两阶段提交：flush PG → Neo4j execute → PG commit。

        保证原子性：PG 在 Neo4j 全部成功前不 commit，
        任一端失败都可完整回滚。
        """
        if self._committed or self._rolledback:
            return TransactionResult(success=self._committed, pg_committed=self._committed)

        has_neo4j = self._neo4j is not None and self._neo4j_pending
        result = TransactionResult(
            success=False,
            storage_mode="dual_write" if has_neo4j else "pg_only",
        )

        # Phase 1: PG flush（验证约束，生成 ID，但不 commit）
        try:
            self._pg.flush()
        except Exception as exc:
            self._pg.rollback()
            result.error = f"PostgreSQL flush 失败: {exc}"
            self._rolledback = True
            logger.error(result.error)
            return result

        # Phase 2: Neo4j execute（PG 尚未 commit，可安全回滚）
        if self._neo4j is not None and self._neo4j_pending:
            neo4j_error = self._execute_neo4j_ops()
            if neo4j_error is not None:
                # Neo4j 部分失败 → 补偿已执行的 Neo4j 操作 + 回滚 PG
                compensations, comp_details = self._compensate_neo4j_detailed()
                self._pg.rollback()
                result.compensations_applied = compensations
                result.compensation_details = comp_details
                result.neo4j_error = neo4j_error
                result.needs_backfill = True
                result.error = (
                    f"Neo4j 执行失败，已回滚 PG 并补偿 {compensations} 个 Neo4j 操作: "
                    f"{neo4j_error}"
                )
                result.success = False
                result.pg_committed = False
                result.neo4j_committed = False
                self._rolledback = True
                logger.error(result.error)
                return result
            result.neo4j_committed = True
        else:
            result.neo4j_committed = True  # 无 Neo4j 操作也视为成功

        # Phase 3: PG commit（Neo4j 已全部成功）
        try:
            self._pg.commit()
            result.pg_committed = True
        except Exception as exc:
            # PG commit 失败 → 补偿已执行的 Neo4j 操作
            compensations, comp_details = self._compensate_neo4j_detailed()
            result.compensations_applied = compensations
            result.compensation_details = comp_details
            result.needs_backfill = True
            result.error = (
                f"PostgreSQL commit 失败，已补偿 {compensations} 个 Neo4j 操作: {exc}"
            )
            result.success = False
            result.pg_committed = False
            result.neo4j_committed = False
            self._rolledback = True
            logger.error(result.error)
            return result

        result.success = True
        self._committed = True
        logger.debug("事务成功提交: PG=%s, Neo4j ops=%d",
                      result.pg_committed, len(self._neo4j_executed))
        return result

    def rollback(self) -> None:
        """回滚所有变更。"""
        if self._rolledback:
            return
        try:
            self._pg.rollback()
        except Exception as exc:
            logger.warning("PG rollback 异常: %s", exc)
        if self._neo4j_executed:
            self._compensate_neo4j()
        self._neo4j_pending.clear()
        self._rolledback = True

    # ── 内部方法 ──────────────────────────────────────────────────────────

    def _execute_neo4j_ops(self) -> Optional[str]:
        """逐一执行 Neo4j 操作，返回 None 表示全成功，否则返回错误信息。"""
        driver = self._neo4j
        if not hasattr(driver, 'driver') or driver.driver is None:
            return "Neo4j driver 未连接"

        for op in self._neo4j_pending:
            try:
                with driver.driver.session(database=driver.database) as session:
                    session.execute_write(
                        lambda tx, c=op.cypher, p=op.params: tx.run(c, **p)
                    )
                self._neo4j_executed.append(op)
            except Exception as exc:
                return f"Cypher 执行失败: {exc}"
        return None

    def _compensate_neo4j(self) -> int:
        """对已执行的 Neo4j 操作执行补偿，返回成功补偿数。"""
        count, _ = self._compensate_neo4j_detailed()
        return count

    def _compensate_neo4j_detailed(self) -> tuple:
        """对已执行的 Neo4j 操作执行补偿，返回 (成功补偿数, 详情列表)。"""
        driver = self._neo4j
        if driver is None or not hasattr(driver, 'driver') or driver.driver is None:
            return 0, []

        compensated = 0
        details: List[str] = []
        for op in reversed(self._neo4j_executed):
            if op.compensate_cypher is None:
                continue
            try:
                with driver.driver.session(database=driver.database) as session:
                    session.execute_write(
                        lambda tx, c=op.compensate_cypher, p=op.compensate_params or {}: tx.run(c, **p)
                    )
                compensated += 1
                details.append(f"compensated: {op.compensate_cypher[:80]}")
            except Exception as exc:
                logger.warning("Neo4j 补偿失败（需人工介入）: %s — %s", op.compensate_cypher, exc)
                details.append(f"failed: {op.compensate_cypher[:80]} — {exc}")
        self._neo4j_executed.clear()
        return compensated, details


@contextmanager
def transaction_scope(
    pg_session_factory: Callable[[], Any],
    neo4j_driver: Any = None,
):
    """便捷上下文管理器：自动创建 session + coordinator。

    用法::

        with transaction_scope(db_manager.get_session, neo4j_drv) as txn:
            txn.pg_add(doc)
            txn.neo4j_write("CREATE (n:Herb {name: $name})", name="黄芪")
    """
    session = pg_session_factory()
    try:
        with TransactionCoordinator(session, neo4j_driver) as txn:
            yield txn
    finally:
        session.close()
