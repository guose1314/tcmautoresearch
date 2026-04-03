import unittest
from unittest.mock import MagicMock, patch

from src.core.event_bus import EventBus
from src.research.audit_history import (
    AUDIT_EVENT_NAMES,
    AuditEntry,
    AuditHistory,
    publish_audit_event,
)
from src.research.pipeline_events import (
    PHASE_LIFECYCLE_EVENT_NAMES,
    publish_phase_lifecycle_event,
)


class TestAuditHistory(unittest.TestCase):
    def test_record_appends_flattened_entry_and_returns_dataclass(self):
        history = AuditHistory()

        entry = history.record("cycle_created", {"cycle_id": "c1", "phase": "observe"})

        self.assertIsInstance(entry, AuditEntry)
        self.assertEqual(entry.action, "cycle_created")
        self.assertEqual(entry.metadata["cycle_id"], "c1")
        self.assertEqual(history.entries[0]["action"], "cycle_created")
        self.assertEqual(history.entries[0]["cycle_id"], "c1")
        self.assertIn("timestamp", history.entries[0])

    def test_record_ignores_conflicting_action_and_timestamp_in_metadata(self):
        history = AuditHistory()

        entry = history.record("phase_executed", {"action": "wrong", "timestamp": "old", "cycle_id": "c1"})

        self.assertEqual(entry.action, "phase_executed")
        self.assertEqual(entry.metadata, {"cycle_id": "c1"})
        self.assertEqual(history.entries[0]["action"], "phase_executed")
        self.assertNotEqual(history.entries[0]["timestamp"], "old")

    def test_query_returns_all_entries_without_filters(self):
        history = AuditHistory()
        history.record("cycle_created", {"cycle_id": "c1"})
        history.record("cycle_started", {"cycle_id": "c2"})

        result = history.query()

        self.assertEqual([entry.action for entry in result], ["cycle_created", "cycle_started"])
        self.assertEqual(result[0].metadata["cycle_id"], "c1")

    def test_query_filters_by_action_and_metadata(self):
        history = AuditHistory()
        history.record("phase_executed", {"cycle_id": "c1", "phase": "observe"})
        history.record("phase_executed", {"cycle_id": "c2", "phase": "observe"})
        history.record("phase_failed", {"cycle_id": "c1", "phase": "analyze"})

        result = history.query({"action": "phase_executed", "cycle_id": "c1"})

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].action, "phase_executed")
        self.assertEqual(result[0].metadata["phase"], "observe")

    def test_query_returns_empty_list_for_non_matching_filters(self):
        history = AuditHistory()
        history.record("cycle_completed", {"cycle_id": "c1"})

        self.assertEqual(history.query({"cycle_id": "missing"}), [])

    def test_query_filters_by_action_prefix(self):
        history = AuditHistory(
            [
                {"timestamp": "2026-04-02T10:00:00", "action": "cycle_created", "cycle_id": "c1"},
                {"timestamp": "2026-04-02T10:30:00", "action": "cycle_started", "cycle_id": "c1"},
                {"timestamp": "2026-04-02T11:00:00", "action": "phase_executed", "cycle_id": "c1"},
            ]
        )

        result = history.query({"action_prefix": "cycle_"})

        self.assertEqual([entry.action for entry in result], ["cycle_created", "cycle_started"])

    def test_query_filters_by_timestamp_range(self):
        history = AuditHistory(
            [
                {"timestamp": "2026-04-02T10:00:00", "action": "cycle_created", "cycle_id": "c1"},
                {"timestamp": "2026-04-02T10:30:00", "action": "cycle_started", "cycle_id": "c1"},
                {"timestamp": "2026-04-02T11:00:00", "action": "phase_executed", "cycle_id": "c1"},
            ]
        )

        result = history.query(
            {
                "timestamp_from": "2026-04-02T10:15:00",
                "timestamp_to": "2026-04-02T10:45:00",
            }
        )

        self.assertEqual([entry.action for entry in result], ["cycle_started"])

    def test_shared_entries_reference_stays_in_sync(self):
        shared_entries = []
        history = AuditHistory(shared_entries)

        history.record("cycle_resumed", {"cycle_id": "c9"})

        self.assertIs(history.entries, shared_entries)
        self.assertEqual(shared_entries[0]["cycle_id"], "c9")

    def test_attach_to_event_bus_records_cycle_lifecycle_events(self):
        history = AuditHistory()
        bus = EventBus()
        history.attach_to_event_bus(bus)

        bus.publish(AUDIT_EVENT_NAMES["cycle_created"], {"cycle_id": "c1", "cycle_name": "demo"})
        bus.publish(AUDIT_EVENT_NAMES["cycle_started"], {"cycle_id": "c1", "phase": "observe"})

        self.assertEqual([entry["action"] for entry in history.entries], ["cycle_created", "cycle_started"])
        self.assertEqual(history.entries[0]["cycle_name"], "demo")

    def test_attach_to_event_bus_records_phase_execution_events(self):
        history = AuditHistory()
        bus = EventBus()
        history.attach_to_event_bus(bus)

        bus.publish(AUDIT_EVENT_NAMES["phase_executed"], {"cycle_id": "c1", "phase": "observe", "duration": 0.3})
        bus.publish(AUDIT_EVENT_NAMES["phase_failed"], {"cycle_id": "c1", "phase": "analyze", "error": "boom"})

        self.assertEqual([entry["action"] for entry in history.entries], ["phase_executed", "phase_failed"])
        self.assertEqual(history.entries[1]["error"], "boom")

    def test_attach_to_same_event_bus_is_idempotent(self):
        history = AuditHistory()
        bus = EventBus()
        history.attach_to_event_bus(bus)
        history.attach_to_event_bus(bus)

        bus.publish(AUDIT_EVENT_NAMES["cycle_resumed"], {"cycle_id": "c2"})

        self.assertEqual(len(history.entries), 1)

    def test_detach_from_event_bus_stops_recording(self):
        history = AuditHistory()
        bus = EventBus()
        history.attach_to_event_bus(bus)
        history.detach_from_event_bus()

        bus.publish(AUDIT_EVENT_NAMES["cycle_completed"], {"cycle_id": "c1"})

        self.assertEqual(history.entries, [])

    def test_publish_audit_event_uses_canonical_names(self):
        history = AuditHistory()
        bus = EventBus()
        history.attach_to_event_bus(bus)

        publish_audit_event(bus, "cycle_created", {"cycle_id": "c3"})

        self.assertEqual(history.entries[0]["action"], "cycle_created")

    def test_legacy_event_names_remain_supported(self):
        history = AuditHistory()
        bus = EventBus()
        history.attach_to_event_bus(bus)

        bus.publish("cycle.lifecycle.created", {"cycle_id": "legacy"})

        self.assertEqual(history.entries[0]["cycle_id"], "legacy")

    def test_publish_phase_lifecycle_event_uses_shared_constants(self):
        captured = []
        bus = EventBus()
        bus.subscribe(PHASE_LIFECYCLE_EVENT_NAMES["started"], lambda payload: captured.append(payload))

        publish_phase_lifecycle_event(bus, "started", {"phase": "observe"})

        self.assertEqual(captured[0]["phase"], "observe")


class TestAuditHistoryPipelineIntegration(unittest.TestCase):
    def test_pipeline_execution_history_alias_updates_via_events(self):
        module_factory = MagicMock()
        module_factory.has.return_value = False

        with patch("src.research.research_pipeline.HypothesisEngine") as hypothesis_engine, \
             patch("src.research.research_pipeline.ResearchPhaseHandlers"), \
             patch("src.research.research_pipeline.ResearchPipelineOrchestrator"), \
             patch("src.research.research_pipeline.ModuleFactory") as module_factory_cls:
            hypothesis_engine.return_value.initialize.return_value = None
            module_factory_cls.from_config.return_value = module_factory

            from src.research.research_pipeline import ResearchPipeline

            pipeline = ResearchPipeline({})

        self.assertIs(pipeline.execution_history, pipeline.audit_history.entries)

        pipeline.event_bus.publish("cycle.lifecycle.created", {"cycle_id": "c1", "cycle_name": "demo"})

        self.assertEqual(len(pipeline.execution_history), 1)
        self.assertEqual(pipeline.execution_history[0]["action"], "cycle_created")
        self.assertEqual(pipeline.get_cycle_history("c1"), pipeline.execution_history)


if __name__ == "__main__":
    unittest.main()