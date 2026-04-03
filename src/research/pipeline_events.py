"""Shared pipeline event constants and publishing helpers."""

from typing import Any, Dict, Optional

PHASE_LIFECYCLE_EVENT_NAMES: Dict[str, str] = {
    "started": "phase.lifecycle.started",
    "completed": "phase.lifecycle.completed",
    "failed": "phase.lifecycle.failed",
}

AUDIT_EVENT_NAMES: Dict[str, str] = {
    "cycle_created": "audit.lifecycle.cycle.created",
    "cycle_started": "audit.lifecycle.cycle.started",
    "cycle_completed": "audit.lifecycle.cycle.completed",
    "cycle_suspended": "audit.lifecycle.cycle.suspended",
    "cycle_resumed": "audit.lifecycle.cycle.resumed",
    "phase_started": "audit.lifecycle.phase.started",
    "phase_completed": "audit.lifecycle.phase.completed",
    "phase_lifecycle_failed": "audit.lifecycle.phase.failed",
    "phase_executed": "audit.lifecycle.phase.executed",
    "phase_failed": "audit.lifecycle.phase.execution_failed",
}

AUDIT_EVENT_LEGACY_NAMES: Dict[str, str] = {
    "cycle_created": "cycle.lifecycle.created",
    "cycle_started": "cycle.lifecycle.started",
    "cycle_completed": "cycle.lifecycle.completed",
    "cycle_suspended": "cycle.lifecycle.suspended",
    "cycle_resumed": "cycle.lifecycle.resumed",
    "phase_executed": "phase.execution.succeeded",
    "phase_failed": "phase.execution.failed",
}


def publish_named_event(event_bus: Any, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
    event_bus.publish(event_name, payload or {})


def publish_phase_lifecycle_event(
    event_bus: Any,
    phase_state: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    event_name = PHASE_LIFECYCLE_EVENT_NAMES.get(phase_state)
    if event_name is None:
        raise KeyError(f"Unknown phase lifecycle state: {phase_state}")
    publish_named_event(event_bus, event_name, payload)


def publish_audit_event(
    event_bus: Any,
    action: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    event_name = AUDIT_EVENT_NAMES.get(action)
    if event_name is None:
        raise KeyError(f"Unknown audit action: {action}")
    publish_named_event(event_bus, event_name, payload)


__all__ = [
    "AUDIT_EVENT_LEGACY_NAMES",
    "AUDIT_EVENT_NAMES",
    "PHASE_LIFECYCLE_EVENT_NAMES",
    "publish_audit_event",
    "publish_named_event",
    "publish_phase_lifecycle_event",
]