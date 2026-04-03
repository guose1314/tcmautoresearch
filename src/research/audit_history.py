"""Audit history helpers for reusable execution logging."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.research.pipeline_events import (
    AUDIT_EVENT_LEGACY_NAMES,
    AUDIT_EVENT_NAMES,
)
from src.research.pipeline_events import (
    publish_audit_event as _publish_audit_event,
)

publish_audit_event = _publish_audit_event


@dataclass(frozen=True)
class AuditEntry:
    """Normalized audit log entry returned by query operations."""

    timestamp: str
    action: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            **self.metadata,
        }


class AuditHistory:
    """Shared audit log store for pipeline and cycle lifecycle events."""

    def __init__(self, entries: Optional[List[Dict[str, Any]]] = None):
        self.entries = entries if entries is not None else []
        self._event_bus: Any = None
        self._subscriptions: List[tuple[str, Callable[[Dict[str, Any]], None]]] = []

    def record(self, action: str, metadata: Optional[Dict[str, Any]] = None) -> AuditEntry:
        payload = dict(metadata or {})
        payload.pop("timestamp", None)
        payload.pop("action", None)
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            metadata=payload,
        )
        self.entries.append(entry.to_dict())
        return entry

    def query(self, filters: Optional[Dict[str, Any]] = None) -> List[AuditEntry]:
        normalized_filters = dict(filters or {})
        action_prefix = normalized_filters.pop("action_prefix", None)
        timestamp_from = self._parse_timestamp(normalized_filters.pop("timestamp_from", None))
        timestamp_to = self._parse_timestamp(normalized_filters.pop("timestamp_to", None))
        return [
            self._to_audit_entry(entry)
            for entry in self.entries
            if self._matches_filters(entry, normalized_filters, action_prefix, timestamp_from, timestamp_to)
        ]

    def clear(self) -> None:
        self.entries.clear()

    def attach_to_event_bus(self, event_bus: Any) -> None:
        if event_bus is self._event_bus:
            return
        if self._event_bus is not None:
            self.detach_from_event_bus()

        subscriptions = [
            (AUDIT_EVENT_NAMES["cycle_created"], self._on_cycle_created),
            (AUDIT_EVENT_NAMES["cycle_started"], self._on_cycle_started),
            (AUDIT_EVENT_NAMES["cycle_completed"], self._on_cycle_completed),
            (AUDIT_EVENT_NAMES["cycle_suspended"], self._on_cycle_suspended),
            (AUDIT_EVENT_NAMES["cycle_resumed"], self._on_cycle_resumed),
            (AUDIT_EVENT_NAMES["phase_executed"], self._on_phase_execution_succeeded),
            (AUDIT_EVENT_NAMES["phase_failed"], self._on_phase_execution_failed),
            (AUDIT_EVENT_LEGACY_NAMES["cycle_created"], self._on_cycle_created),
            (AUDIT_EVENT_LEGACY_NAMES["cycle_started"], self._on_cycle_started),
            (AUDIT_EVENT_LEGACY_NAMES["cycle_completed"], self._on_cycle_completed),
            (AUDIT_EVENT_LEGACY_NAMES["cycle_suspended"], self._on_cycle_suspended),
            (AUDIT_EVENT_LEGACY_NAMES["cycle_resumed"], self._on_cycle_resumed),
            (AUDIT_EVENT_LEGACY_NAMES["phase_executed"], self._on_phase_execution_succeeded),
            (AUDIT_EVENT_LEGACY_NAMES["phase_failed"], self._on_phase_execution_failed),
        ]
        for event_name, handler in subscriptions:
            event_bus.subscribe(event_name, handler)

        self._event_bus = event_bus
        self._subscriptions = subscriptions

    def detach_from_event_bus(self) -> None:
        if self._event_bus is None:
            return

        for event_name, handler in self._subscriptions:
            self._event_bus.unsubscribe(event_name, handler)

        self._event_bus = None
        self._subscriptions = []

    def _matches_filters(
        self,
        entry: Dict[str, Any],
        filters: Dict[str, Any],
        action_prefix: Optional[str] = None,
        timestamp_from: Optional[datetime] = None,
        timestamp_to: Optional[datetime] = None,
    ) -> bool:
        if action_prefix is not None and not str(entry.get("action", "")).startswith(action_prefix):
            return False

        if timestamp_from is not None or timestamp_to is not None:
            entry_timestamp = self._parse_timestamp(entry.get("timestamp"))
            if entry_timestamp is None:
                return False
            if timestamp_from is not None and entry_timestamp < timestamp_from:
                return False
            if timestamp_to is not None and entry_timestamp > timestamp_to:
                return False

        for key, value in filters.items():
            if entry.get(key) != value:
                return False
        return True

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _to_audit_entry(self, entry: Dict[str, Any]) -> AuditEntry:
        metadata = {
            key: value
            for key, value in entry.items()
            if key not in {"timestamp", "action"}
        }
        return AuditEntry(
            timestamp=str(entry.get("timestamp", "")),
            action=str(entry.get("action", "")),
            metadata=metadata,
        )

    def _record_from_event(self, action: str, payload: Dict[str, Any]) -> None:
        self.record(action, payload)

    def _on_cycle_created(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("cycle_created", payload)

    def _on_cycle_started(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("cycle_started", payload)

    def _on_cycle_completed(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("cycle_completed", payload)

    def _on_cycle_suspended(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("cycle_suspended", payload)

    def _on_cycle_resumed(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("cycle_resumed", payload)

    def _on_phase_execution_succeeded(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("phase_executed", payload)

    def _on_phase_execution_failed(self, payload: Dict[str, Any]) -> None:
        self._record_from_event("phase_failed", payload)


__all__ = [
    "AUDIT_EVENT_LEGACY_NAMES",
    "AUDIT_EVENT_NAMES",
    "AuditHistory",
    "AuditEntry",
    "publish_audit_event",
]