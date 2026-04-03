from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.core.phase_tracker import PhaseTrackerMixin


class _Status(Enum):
    OK = "ok"


@dataclass
class _Payload:
    value: int


class _Tracker(PhaseTrackerMixin):
    def __init__(self):
        self.governance_config = {
            "enable_phase_tracking": True,
            "persist_failed_operations": True,
        }
        self.phase_history = []
        self.phase_timings = {}
        self.completed_phases = []
        self.failed_phase = None
        self.final_status = "initialized"
        self.last_completed_phase = None
        self.failed_operations = []


def test_serialize_value_handles_nested_supported_types():
    tracker = _Tracker()

    serialized = tracker._serialize_value(
        {
            "status": _Status.OK,
            "ts": datetime(2026, 3, 31, 12, 0, 0),
            "dd": defaultdict(int, {"a": 1}),
            "tuple": (1, 2),
            "data": _Payload(value=7),
            "fn": test_serialize_value_handles_nested_supported_types,
        }
    )

    assert serialized["status"] == "ok"
    assert isinstance(serialized["ts"], str)
    assert serialized["dd"] == {"a": 1}
    assert serialized["tuple"] == [1, 2]
    assert serialized["data"] == {"value": 7}
    assert serialized["fn"] == "test_serialize_value_handles_nested_supported_types"


def test_phase_tracking_lifecycle_still_works():
    tracker = _Tracker()

    started = tracker._start_phase("demo", {"x": 1})
    tracker._complete_phase("demo", started, {"y": 2}, final_status="completed")

    assert tracker.last_completed_phase == "demo"
    assert tracker.final_status == "completed"
    assert tracker.phase_timings["demo"] >= 0.0
    assert tracker.phase_history[-1]["status"] == "completed"
