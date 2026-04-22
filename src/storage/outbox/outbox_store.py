"""Phase L-2 — Outbox 内存存储与重放器。

提供 :class:`InMemoryOutboxStore` —— 一个线程安全的内存版 outbox，作为
后续 PG/JSONB-backed outbox 的最小可运行替身；同时提供
:func:`replay_pending_events` 实现 ``at-least-once`` 语义的重放器。

设计要点：
- 所有操作以 ``event_id`` 为幂等键
- 重放器接受任意 ``Callable[[OutboxEvent], None]`` 处理器，方便适配 Neo4j 写入
- 处理器抛错时事件自动 ``mark_failed`` 并保留以便后续重放
- 重放完成后返回 :class:`OutboxReplaySummary` 便于监控与审计
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .event_contract import (
    OUTBOX_STATUS_FAILED,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PROCESSED,
    OutboxEvent,
)

__all__ = [
    "InMemoryOutboxStore",
    "OutboxReplaySummary",
    "replay_pending_events",
]


@dataclass
class OutboxReplaySummary:
    """一次重放的统计摘要。"""

    attempted: int = 0
    processed: int = 0
    failed: int = 0
    failed_event_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "attempted": self.attempted,
            "processed": self.processed,
            "failed": self.failed,
            "failed_event_ids": list(self.failed_event_ids),
        }


class InMemoryOutboxStore:
    """线程安全的内存 outbox。

    适用于：
    - 单元测试与最小可运行示例
    - 临时工作站环境（重启后 outbox 数据将丢失）

    生产环境应当替换为基于 PG 的实现，但 API 保持一致。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: Dict[str, OutboxEvent] = {}

    # ── 写入 ──────────────────────────────────────────────────────────

    def append(self, event: OutboxEvent) -> OutboxEvent:
        """追加事件；若 ``event_id`` 已存在则直接抛错，避免静默覆盖。"""
        if not isinstance(event, OutboxEvent):
            raise TypeError("append() 仅接受 OutboxEvent 实例")
        with self._lock:
            if event.event_id in self._events:
                raise ValueError(f"事件 {event.event_id!r} 已存在于 outbox")
            self._events[event.event_id] = event
        return event

    def upsert(self, event: OutboxEvent) -> OutboxEvent:
        """以 ``event_id`` 为键覆盖写入，用于幂等重放场景。"""
        if not isinstance(event, OutboxEvent):
            raise TypeError("upsert() 仅接受 OutboxEvent 实例")
        with self._lock:
            self._events[event.event_id] = event
        return event

    # ── 查询 ──────────────────────────────────────────────────────────

    def get(self, event_id: str) -> Optional[OutboxEvent]:
        with self._lock:
            return self._events.get(event_id)

    def list_pending(self) -> List[OutboxEvent]:
        with self._lock:
            return [e for e in self._events.values() if e.status == OUTBOX_STATUS_PENDING]

    def list_failed(self) -> List[OutboxEvent]:
        with self._lock:
            return [e for e in self._events.values() if e.status == OUTBOX_STATUS_FAILED]

    def list_all(self) -> List[OutboxEvent]:
        with self._lock:
            return list(self._events.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)

    # ── 状态变迁 ───────────────────────────────────────────────────────

    def mark_processed(self, event_id: str) -> Optional[OutboxEvent]:
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                return None
            event.mark_processed()
            return event

    def mark_failed(self, event_id: str, error: str) -> Optional[OutboxEvent]:
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                return None
            event.mark_failed(error)
            return event

    def reset_failed_for_retry(self) -> int:
        """将所有 ``failed`` 事件重置为 ``pending``，返回重置条数。"""
        count = 0
        with self._lock:
            for event in self._events.values():
                if event.status == OUTBOX_STATUS_FAILED:
                    event.reset_for_retry()
                    count += 1
        return count

    # ── 维护 ──────────────────────────────────────────────────────────

    def purge_processed(self) -> int:
        """删除所有已 ``processed`` 事件，返回删除条数。"""
        with self._lock:
            processed_ids = [
                eid for eid, e in self._events.items() if e.status == OUTBOX_STATUS_PROCESSED
            ]
            for eid in processed_ids:
                del self._events[eid]
            return len(processed_ids)


def replay_pending_events(
    store: InMemoryOutboxStore,
    handler: Callable[[OutboxEvent], None],
    *,
    max_events: Optional[int] = None,
) -> OutboxReplaySummary:
    """对 ``store`` 中所有 pending 事件依次调用 ``handler`` 重放。

    ``at-least-once`` 语义：
    - 处理器返回时事件被标记为 ``processed``
    - 处理器抛出异常时事件被标记为 ``failed`` 并记录错误，**不向上抛错**
    - 调用方可通过 :class:`OutboxReplaySummary` 获取每次重放的成败统计

    Parameters
    ----------
    max_events :
        本次重放上限；``None`` 表示不限制。
    """
    summary = OutboxReplaySummary()
    pending = store.list_pending()
    if max_events is not None:
        pending = pending[: max(0, int(max_events))]

    for event in pending:
        summary.attempted += 1
        try:
            handler(event)
        except Exception as exc:  # noqa: BLE001 — outbox 必须吞掉处理器异常
            store.mark_failed(event.event_id, str(exc))
            summary.failed += 1
            summary.failed_event_ids.append(event.event_id)
            continue
        store.mark_processed(event.event_id)
        summary.processed += 1
    return summary
