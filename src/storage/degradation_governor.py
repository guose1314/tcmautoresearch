"""降级治理器 — 跟踪存储模式变迁并提供结构化警告。

当系统处于 sqlite_fallback 或 pg_only（Neo4j 不可用）模式时，
DegradationGovernor 负责：
- 记录降级事件（含时间戳与原因）
- 在每次事务完成时累计降级指标
- 提供 ``is_production_ready`` 判定
- 提供 ``acknowledge_degradation()`` 使运维人员显式确认

用法::

    governor = DegradationGovernor()
    governor.record_mode_transition("dual_write", "pg_only", reason="Neo4j 连接超时")
    if not governor.is_production_ready:
        logger.warning(governor.summary)
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 最大历史记录条数 ──────────────────────────────────────────────────────
_MAX_TRANSITION_HISTORY = 100
_MAX_FAILED_TRANSACTIONS = 200


@dataclass
class ModeTransition:
    """一次模式变迁事件。"""
    from_mode: str
    to_mode: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DegradationMetrics:
    """降级指标聚合。"""
    total_transactions: int = 0
    failed_transactions: int = 0
    neo4j_failures: int = 0
    compensations_applied: int = 0
    backfill_pending_count: int = 0
    sqlite_fallback_transactions: int = 0
    pg_only_transactions: int = 0
    dual_write_transactions: int = 0
    last_failure_timestamp: Optional[str] = None
    last_success_timestamp: Optional[str] = None

    @property
    def failure_rate(self) -> float:
        if self.total_transactions == 0:
            return 0.0
        return self.failed_transactions / self.total_transactions

    @property
    def neo4j_failure_rate(self) -> float:
        if self.total_transactions == 0:
            return 0.0
        return self.neo4j_failures / self.total_transactions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_transactions": self.total_transactions,
            "failed_transactions": self.failed_transactions,
            "neo4j_failures": self.neo4j_failures,
            "compensations_applied": self.compensations_applied,
            "backfill_pending_count": self.backfill_pending_count,
            "sqlite_fallback_transactions": self.sqlite_fallback_transactions,
            "pg_only_transactions": self.pg_only_transactions,
            "dual_write_transactions": self.dual_write_transactions,
            "failure_rate": round(self.failure_rate, 4),
            "neo4j_failure_rate": round(self.neo4j_failure_rate, 4),
            "last_failure_timestamp": self.last_failure_timestamp,
            "last_success_timestamp": self.last_success_timestamp,
        }


class DegradationGovernor:
    """跟踪存储降级状态并提供治理决策。

    线程安全：内部使用 RLock 保护所有可变状态。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._current_mode: str = "uninitialized"
        self._transitions: Deque[ModeTransition] = deque(maxlen=_MAX_TRANSITION_HISTORY)
        self._metrics = DegradationMetrics()
        self._acknowledged = False
        self._acknowledged_mode: Optional[str] = None

    @property
    def current_mode(self) -> str:
        with self._lock:
            return self._current_mode

    @property
    def metrics(self) -> DegradationMetrics:
        with self._lock:
            return self._metrics

    @property
    def is_production_ready(self) -> bool:
        """判定当前存储状态是否适合生产负载。

        生产就绪条件：
        - 模式为 dual_write，或
        - 模式为 pg_only 且已被运维显式确认
        """
        with self._lock:
            if self._current_mode == "dual_write":
                return True
            if self._current_mode == "pg_only" and self._acknowledged and self._acknowledged_mode == "pg_only":
                return True
            return False

    @property
    def is_degraded(self) -> bool:
        with self._lock:
            return self._current_mode in ("pg_only", "sqlite_fallback")

    @property
    def summary(self) -> str:
        """人类可读的降级状态摘要。"""
        with self._lock:
            mode = self._current_mode
            m = self._metrics
            if mode == "dual_write":
                return f"存储正常 (dual_write): {m.total_transactions} 笔事务, 失败率 {m.failure_rate:.1%}"
            elif mode == "pg_only":
                ack = "（已确认）" if self._acknowledged else "（未确认 ⚠️）"
                return (
                    f"降级运行 (pg_only){ack}: Neo4j 不可用, "
                    f"Neo4j 失败 {m.neo4j_failures} 次, "
                    f"待 backfill {m.backfill_pending_count} 项"
                )
            elif mode == "sqlite_fallback":
                return (
                    f"SQLite 降级模式: 非生产环境, "
                    f"{m.sqlite_fallback_transactions} 笔事务"
                )
            return "存储未初始化"

    # ── 事件记录 ──────────────────────────────────────────────────────────

    def record_mode_transition(self, from_mode: str, to_mode: str, *, reason: str = "") -> None:
        """记录一次模式变迁事件。"""
        with self._lock:
            transition = ModeTransition(
                from_mode=from_mode,
                to_mode=to_mode,
                reason=reason,
            )
            self._transitions.append(transition)
            self._current_mode = to_mode

            if self._acknowledged and self._acknowledged_mode != to_mode:
                self._acknowledged = False
                self._acknowledged_mode = None

        if to_mode in ("pg_only", "sqlite_fallback"):
            logger.warning(
                "存储降级: %s → %s (原因: %s)",
                from_mode, to_mode, reason or "未指定",
            )
        elif from_mode in ("pg_only", "sqlite_fallback") and to_mode == "dual_write":
            logger.info("存储恢复: %s → %s", from_mode, to_mode)

    def record_transaction_result(self, result: Any) -> None:
        """从 TransactionResult 记录事务观测指标。

        Parameters
        ----------
        result :
            TransactionResult 实例（或具有相同属性的对象）。
        """
        with self._lock:
            self._metrics.total_transactions += 1
            mode = getattr(result, "storage_mode", "")

            if mode == "dual_write":
                self._metrics.dual_write_transactions += 1
            elif mode == "pg_only":
                self._metrics.pg_only_transactions += 1
            elif mode == "sqlite_fallback":
                self._metrics.sqlite_fallback_transactions += 1

            if not getattr(result, "success", True):
                self._metrics.failed_transactions += 1
                self._metrics.last_failure_timestamp = datetime.now().isoformat()

                if getattr(result, "neo4j_error", None):
                    self._metrics.neo4j_failures += 1

            else:
                self._metrics.last_success_timestamp = datetime.now().isoformat()

            self._metrics.compensations_applied += int(
                getattr(result, "compensations_applied", 0) or 0
            )
            if getattr(result, "needs_backfill", False):
                self._metrics.backfill_pending_count += 1

    def set_initial_mode(self, mode: str) -> None:
        """工厂初始化完成后设置初始模式。"""
        with self._lock:
            old = self._current_mode
            self._current_mode = mode
        if old != mode:
            self.record_mode_transition(old, mode, reason="factory 初始化")

    # ── 运维操作 ──────────────────────────────────────────────────────────

    def acknowledge_degradation(self, mode: Optional[str] = None) -> bool:
        """运维显式确认当前降级状态可接受。

        Parameters
        ----------
        mode :
            要确认的模式。若不匹配当前模式则拒绝。

        Returns
        -------
        bool
            是否确认成功。
        """
        with self._lock:
            target = mode or self._current_mode
            if target not in ("pg_only", "sqlite_fallback"):
                return False
            if target != self._current_mode:
                return False
            self._acknowledged = True
            self._acknowledged_mode = target
            return True

    def get_transitions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的模式变迁记录。"""
        with self._lock:
            items = list(self._transitions)[-limit:]
        return [
            {
                "from_mode": t.from_mode,
                "to_mode": t.to_mode,
                "reason": t.reason,
                "timestamp": t.timestamp,
            }
            for t in items
        ]

    def to_governance_report(self) -> Dict[str, Any]:
        """生成完整的治理报告。"""
        with self._lock:
            return {
                "current_mode": self._current_mode,
                "is_production_ready": self.is_production_ready,
                "is_degraded": self.is_degraded,
                "acknowledged": self._acknowledged,
                "acknowledged_mode": self._acknowledged_mode,
                "metrics": self._metrics.to_dict(),
                "recent_transitions": self.get_transitions(10),
                "summary": self.summary,
            }
