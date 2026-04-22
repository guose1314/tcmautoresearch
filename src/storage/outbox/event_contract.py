"""Phase L-2 — Outbox 事件契约。

定义 :class:`OutboxEvent` 与状态常量，作为 PG 事务后写图谱失败时的
**事务性 outbox** 事件载体。

契约版本：``outbox-event-v1``。

设计要点：
- ``event_id`` 由调用方提供（建议使用 ULID/UUID4），不会自动生成
- ``payload`` 保持纯字典，便于 JSON 序列化与跨进程重放
- ``status`` 仅允许 ``pending`` / ``processed`` / ``failed`` 三态
- ``attempts`` / ``last_error`` 由 store 负责更新
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

CONTRACT_VERSION = "outbox-event-v1"
OUTBOX_CONTRACT_VERSION = CONTRACT_VERSION

OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_PROCESSED = "processed"
OUTBOX_STATUS_FAILED = "failed"

OUTBOX_VALID_STATUSES = frozenset(
    {OUTBOX_STATUS_PENDING, OUTBOX_STATUS_PROCESSED, OUTBOX_STATUS_FAILED}
)

__all__ = [
    "CONTRACT_VERSION",
    "OUTBOX_CONTRACT_VERSION",
    "OUTBOX_STATUS_PENDING",
    "OUTBOX_STATUS_PROCESSED",
    "OUTBOX_STATUS_FAILED",
    "OUTBOX_VALID_STATUSES",
    "OutboxEvent",
]


def _utcnow_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class OutboxEvent:
    """单条 outbox 事件。

    Parameters
    ----------
    event_id :
        全局唯一事件标识（建议 UUID/ULID）。
    event_type :
        事件类型，例如 ``neo4j.cycle_projection`` / ``neo4j.subgraph_write``。
    payload :
        待重放的载荷（必须可 JSON 序列化）。
    status :
        当前状态（``pending`` / ``processed`` / ``failed``）。
    attempts :
        已重放次数。
    last_error :
        最近一次失败的错误信息（成功后保留以便审计）。
    created_at / updated_at :
        ISO 时间戳。
    """

    event_id: str
    event_type: str
    payload: Dict[str, Any]
    status: str = OUTBOX_STATUS_PENDING
    attempts: int = 0
    last_error: Optional[str] = None
    created_at: str = field(default_factory=_utcnow_iso)
    updated_at: str = field(default_factory=_utcnow_iso)

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("OutboxEvent.event_id 不能为空字符串")
        if not isinstance(self.event_type, str) or not self.event_type.strip():
            raise ValueError("OutboxEvent.event_type 不能为空字符串")
        if not isinstance(self.payload, dict):
            raise TypeError("OutboxEvent.payload 必须是 dict")
        if self.status not in OUTBOX_VALID_STATUSES:
            raise ValueError(
                f"OutboxEvent.status 非法: {self.status!r}, 必须为 {sorted(OUTBOX_VALID_STATUSES)}"
            )
        if not isinstance(self.attempts, int) or self.attempts < 0:
            raise ValueError("OutboxEvent.attempts 必须是非负整数")

    # ── 序列化 ────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutboxEvent":
        return cls(
            event_id=str(data["event_id"]),
            event_type=str(data["event_type"]),
            payload=dict(data.get("payload") or {}),
            status=str(data.get("status") or OUTBOX_STATUS_PENDING),
            attempts=int(data.get("attempts") or 0),
            last_error=data.get("last_error"),
            created_at=str(data.get("created_at") or _utcnow_iso()),
            updated_at=str(data.get("updated_at") or _utcnow_iso()),
        )

    # ── 状态变迁 ───────────────────────────────────────────────────────

    def mark_processed(self) -> None:
        self.status = OUTBOX_STATUS_PROCESSED
        self.attempts += 1
        self.last_error = None
        self.updated_at = _utcnow_iso()

    def mark_failed(self, error: str) -> None:
        self.status = OUTBOX_STATUS_FAILED
        self.attempts += 1
        self.last_error = str(error)
        self.updated_at = _utcnow_iso()

    def reset_for_retry(self) -> None:
        """将事件状态从 ``failed`` 重置为 ``pending`` 以便重新入队。"""
        self.status = OUTBOX_STATUS_PENDING
        self.last_error = None
        self.updated_at = _utcnow_iso()
