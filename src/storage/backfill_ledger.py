"""Backfill 台账 — 跟踪因事务失败产生的待补偿条目。

当 ``TransactionResult.needs_backfill == True`` 时，BackfillLedger 负责：
- 持久记录哪个 cycle_id / phase 需要 backfill
- 跟踪 backfill 状态（pending / completed / failed）
- 提供查询入口供 backfill 工具消费
- 提供指标聚合供 dashboard 展示

用法::

    ledger = BackfillLedger()
    ledger.record_pending(cycle_id="abc", phase="observe", reason="Neo4j 写失败")
    pending = ledger.get_pending()
    ledger.mark_completed("abc", phase="observe")
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_MAX_LEDGER_SIZE = 2000


@dataclass
class BackfillEntry:
    """一条待 backfill 记录。"""
    entry_id: str
    cycle_id: str
    phase: str
    reason: str
    status: str = "pending"  # pending | completed | failed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    error: Optional[str] = None
    transaction_error: Optional[str] = None
    compensation_details: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "entry_id": self.entry_id,
            "cycle_id": self.cycle_id,
            "phase": self.phase,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
        }
        if self.completed_at:
            result["completed_at"] = self.completed_at
        if self.error:
            result["error"] = self.error
        if self.transaction_error:
            result["transaction_error"] = self.transaction_error
        if self.compensation_details:
            result["compensation_details"] = self.compensation_details
        return result


class BackfillLedger:
    """内存 backfill 台账 — 跟踪待补偿的事务失败条目。

    线程安全：内部使用 Lock 保护状态。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Deque[BackfillEntry] = deque(maxlen=_MAX_LEDGER_SIZE)
        self._entry_counter = 0

    def record_pending(
        self,
        *,
        cycle_id: str,
        phase: str = "",
        reason: str = "",
        transaction_error: Optional[str] = None,
        compensation_details: Optional[List[str]] = None,
    ) -> str:
        """记录一条待 backfill 条目。

        Returns
        -------
        str
            生成的 entry_id。
        """
        with self._lock:
            self._entry_counter += 1
            entry_id = f"bf-{self._entry_counter:06d}"
            entry = BackfillEntry(
                entry_id=entry_id,
                cycle_id=cycle_id,
                phase=phase,
                reason=reason,
                transaction_error=transaction_error,
                compensation_details=compensation_details,
            )
            self._entries.append(entry)

        logger.info(
            "Backfill 台账新增: %s (cycle=%s, phase=%s, reason=%s)",
            entry_id, cycle_id, phase, reason,
        )
        return entry_id

    def record_from_transaction_result(
        self,
        result: Any,
        *,
        cycle_id: str = "",
        phase: str = "",
    ) -> Optional[str]:
        """从 TransactionResult 自动记录 backfill 条目。

        仅在 ``result.needs_backfill == True`` 时记录。

        Returns
        -------
        Optional[str]
            若记录了条目则返回 entry_id，否则 None。
        """
        if not getattr(result, "needs_backfill", False):
            return None

        return self.record_pending(
            cycle_id=cycle_id,
            phase=phase,
            reason=getattr(result, "error", "") or "transaction needs backfill",
            transaction_error=getattr(result, "neo4j_error", None) or getattr(result, "error", None),
            compensation_details=getattr(result, "compensation_details", None),
        )

    def mark_completed(self, cycle_id: str, *, phase: str = "") -> int:
        """标记指定 cycle_id（+ phase）的条目为已完成。

        Returns
        -------
        int
            标记为 completed 的条目数。
        """
        count = 0
        with self._lock:
            for entry in self._entries:
                if entry.cycle_id != cycle_id:
                    continue
                if phase and entry.phase != phase:
                    continue
                if entry.status == "pending":
                    entry.status = "completed"
                    entry.completed_at = datetime.now().isoformat()
                    count += 1
        if count:
            logger.info("Backfill 台账已完成: cycle=%s, phase=%s, count=%d", cycle_id, phase, count)
        return count

    def mark_failed(self, cycle_id: str, *, phase: str = "", error: str = "") -> int:
        """标记指定条目为 backfill 失败。"""
        count = 0
        with self._lock:
            for entry in self._entries:
                if entry.cycle_id != cycle_id:
                    continue
                if phase and entry.phase != phase:
                    continue
                if entry.status == "pending":
                    entry.status = "failed"
                    entry.completed_at = datetime.now().isoformat()
                    entry.error = error
                    count += 1
        return count

    # ── 查询 ──────────────────────────────────────────────────────────────

    def get_pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有 pending 状态的 backfill 条目。"""
        with self._lock:
            pending = [e for e in self._entries if e.status == "pending"]
        return [e.to_dict() for e in pending[:limit]]

    def get_all(self, limit: int = 200) -> List[Dict[str, Any]]:
        """获取所有 backfill 条目。"""
        with self._lock:
            items = list(self._entries)[-limit:]
        return [e.to_dict() for e in items]

    def get_summary(self) -> Dict[str, Any]:
        """获取 backfill 台账摘要。"""
        with self._lock:
            total = len(self._entries)
            pending = sum(1 for e in self._entries if e.status == "pending")
            completed = sum(1 for e in self._entries if e.status == "completed")
            failed = sum(1 for e in self._entries if e.status == "failed")

            pending_cycles = sorted(set(
                e.cycle_id for e in self._entries if e.status == "pending"
            ))

        return {
            "total_entries": total,
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "pending_cycle_ids": pending_cycles[:20],
            "has_pending": pending > 0,
        }
