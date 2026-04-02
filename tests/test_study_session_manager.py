# tests/test_study_session_manager.py
"""
StudySessionManager 单元测试

覆盖：
  - ResearchPhase / ResearchCycleStatus / ResearchCycle 数据结构
  - initialize_cycle_tracking
  - mark_cycle_failed
  - build_cycle_analysis_summary
  - serialize_phase_executions / serialize_cycle
  - get_cycle_status / get_all_cycles / get_cycle_history
  - backward-compat: imports from src.research.research_pipeline
"""

import unittest
from datetime import datetime

from src.research.study_session_manager import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
    StudySessionManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager() -> StudySessionManager:
    gov = {
        "enable_phase_tracking": True,
        "persist_failed_operations": True,
        "minimum_stable_completion_rate": 0.8,
        "export_contract_version": "d44.v1",
    }
    return StudySessionManager(gov)


def _make_cycle(cycle_id: str = "c1") -> ResearchCycle:
    return ResearchCycle(
        cycle_id=cycle_id,
        cycle_name="Test Cycle",
        description="Test description",
        research_objective="Test objective",
    )


# ---------------------------------------------------------------------------
# 1. Enum / dataclass sanity
# ---------------------------------------------------------------------------

class TestEnumsAndDataclass(unittest.TestCase):
    def test_research_phase_values(self):
        phases = {p.value for p in ResearchPhase}
        self.assertSetEqual(
            phases,
            {"observe", "hypothesis", "experiment", "analyze", "publish", "reflect"},
        )

    def test_research_cycle_status_values(self):
        statuses = {s.value for s in ResearchCycleStatus}
        self.assertSetEqual(
            statuses,
            {"pending", "active", "completed", "failed", "suspended"},
        )

    def test_research_cycle_defaults(self):
        c = _make_cycle()
        self.assertEqual(c.status, ResearchCycleStatus.PENDING)
        self.assertEqual(c.current_phase, ResearchPhase.OBSERVE)
        self.assertIsNone(c.started_at)
        self.assertEqual(c.duration, 0.0)
        self.assertEqual(c.phase_executions, {})
        self.assertEqual(c.outcomes, [])

    def test_research_cycle_required_fields(self):
        with self.assertRaises(TypeError):
            ResearchCycle()  # missing required positional args


# ---------------------------------------------------------------------------
# 2. initialize_cycle_tracking
# ---------------------------------------------------------------------------

class TestInitializeCycleTracking(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()
        self.cycle = _make_cycle()

    def test_sets_phase_history_empty_list(self):
        self.mgr.initialize_cycle_tracking(self.cycle)
        self.assertEqual(self.cycle.metadata["phase_history"], [])

    def test_sets_completed_phases_empty_list(self):
        self.mgr.initialize_cycle_tracking(self.cycle)
        self.assertEqual(self.cycle.metadata["completed_phases"], [])

    def test_sets_failed_phase_none(self):
        self.mgr.initialize_cycle_tracking(self.cycle)
        self.assertIsNone(self.cycle.metadata["failed_phase"])

    def test_sets_final_status_from_cycle_status(self):
        self.cycle.status = ResearchCycleStatus.ACTIVE
        self.mgr.initialize_cycle_tracking(self.cycle)
        self.assertEqual(self.cycle.metadata["final_status"], "active")

    def test_sets_last_completed_phase_none(self):
        self.mgr.initialize_cycle_tracking(self.cycle)
        self.assertIsNone(self.cycle.metadata["last_completed_phase"])

    def test_sets_failed_operations_empty_list(self):
        self.mgr.initialize_cycle_tracking(self.cycle)
        self.assertEqual(self.cycle.metadata["failed_operations"], [])


# ---------------------------------------------------------------------------
# 3. mark_cycle_failed
# ---------------------------------------------------------------------------

class TestMarkCycleFailed(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()
        self.cycle = _make_cycle()
        self.cycle.started_at = datetime.now().isoformat()
        self.mgr.research_cycles["c1"] = self.cycle
        self.mgr.active_cycles["c1"] = self.cycle
        self.mgr.initialize_cycle_tracking(self.cycle)

    def test_sets_status_to_failed(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "error A")
        self.assertEqual(self.cycle.status, ResearchCycleStatus.FAILED)

    def test_sets_failed_phase_in_metadata(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "error A")
        self.assertEqual(self.cycle.metadata["failed_phase"], "observe")

    def test_sets_completed_at(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "err")
        self.assertIsNotNone(self.cycle.completed_at)

    def test_removes_from_active_cycles(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "err")
        self.assertNotIn("c1", self.mgr.active_cycles)

    def test_appends_to_failed_cycles(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "err")
        self.assertIn(self.cycle, self.mgr.failed_cycles)

    def test_idempotent_on_failed_cycles(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "err")
        self.mgr.mark_cycle_failed(self.cycle, "observe", "err")
        count = sum(1 for c in self.mgr.failed_cycles if c.cycle_id == "c1")
        self.assertEqual(count, 1)

    def test_records_failed_operation_in_cycle_metadata(self):
        self.mgr.mark_cycle_failed(self.cycle, "observe", "err")
        ops = self.cycle.metadata.get("failed_operations", [])
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["operation"], "observe")

    def test_persist_false_skips_operation_record(self):
        mgr = StudySessionManager({"persist_failed_operations": False})
        cycle = _make_cycle("c2")
        cycle.started_at = datetime.now().isoformat()
        mgr.initialize_cycle_tracking(cycle)
        mgr.mark_cycle_failed(cycle, "observe", "err")
        self.assertEqual(cycle.metadata.get("failed_operations", []), [])


# ---------------------------------------------------------------------------
# 4. build_cycle_analysis_summary
# ---------------------------------------------------------------------------

class TestBuildCycleAnalysisSummary(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()
        self.cycle = _make_cycle()
        self.mgr.initialize_cycle_tracking(self.cycle)

    def test_pending_status(self):
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["status"], "pending")

    def test_active_status(self):
        self.cycle.status = ResearchCycleStatus.ACTIVE
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["status"], "in_progress")

    def test_completed_status(self):
        self.cycle.status = ResearchCycleStatus.COMPLETED
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["status"], "stable")

    def test_failed_status(self):
        self.cycle.status = ResearchCycleStatus.FAILED
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["status"], "needs_followup")

    def test_suspended_status(self):
        self.cycle.status = ResearchCycleStatus.SUSPENDED
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["status"], "paused")

    def test_completed_phase_count(self):
        self.cycle.metadata["completed_phases"] = ["observe", "hypothesis"]
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["completed_phase_count"], 2)

    def test_outcome_count(self):
        self.cycle.outcomes = [{"data": 1}, {"data": 2}]
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["outcome_count"], 2)

    def test_deliverable_count(self):
        self.cycle.deliverables = [{"report": "A"}]
        summary = self.mgr.build_cycle_analysis_summary(self.cycle)
        self.assertEqual(summary["deliverable_count"], 1)


# ---------------------------------------------------------------------------
# 5. serialize_phase_executions / serialize_cycle
# ---------------------------------------------------------------------------

class TestSerializeMethods(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()
        self.cycle = _make_cycle()

    def test_serialize_phase_executions_empty(self):
        result = self.mgr.serialize_phase_executions(self.cycle)
        self.assertEqual(result, {})

    def test_serialize_phase_executions_with_entry(self):
        self.cycle.phase_executions[ResearchPhase.OBSERVE] = {"status": "done"}
        result = self.mgr.serialize_phase_executions(self.cycle)
        self.assertIn("observe", result)
        self.assertEqual(result["observe"]["status"], "done")

    def test_serialize_cycle_required_keys(self):
        result = self.mgr.serialize_cycle(self.cycle)
        for key in ("cycle_id", "cycle_name", "status", "current_phase",
                    "phase_executions", "metadata"):
            self.assertIn(key, result)

    def test_serialize_cycle_status_is_string(self):
        result = self.mgr.serialize_cycle(self.cycle)
        self.assertIsInstance(result["status"], str)
        self.assertEqual(result["status"], "pending")

    def test_serialize_cycle_handles_datetime_in_metadata(self):
        self.cycle.metadata["started"] = datetime(2024, 1, 1, 12, 0, 0)
        result = self.mgr.serialize_cycle(self.cycle)
        self.assertIsInstance(result["metadata"]["started"], str)


# ---------------------------------------------------------------------------
# 6. get_cycle_status
# ---------------------------------------------------------------------------

class TestGetCycleStatus(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()
        self.cycle = _make_cycle("cx1")
        self.mgr.research_cycles["cx1"] = self.cycle

    def test_returns_error_for_unknown_id(self):
        result = self.mgr.get_cycle_status("nonexistent")
        self.assertIn("error", result)

    def test_returns_cycle_id(self):
        result = self.mgr.get_cycle_status("cx1")
        self.assertEqual(result["cycle_id"], "cx1")

    def test_returns_status_string(self):
        result = self.mgr.get_cycle_status("cx1")
        self.assertEqual(result["status"], "pending")

    def test_returns_current_phase_string(self):
        result = self.mgr.get_cycle_status("cx1")
        self.assertEqual(result["current_phase"], "observe")


# ---------------------------------------------------------------------------
# 7. get_all_cycles
# ---------------------------------------------------------------------------

class TestGetAllCycles(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()

    def test_empty_returns_empty_list(self):
        self.assertEqual(self.mgr.get_all_cycles(), [])

    def test_returns_all_cycles(self):
        for i in range(3):
            c = _make_cycle(f"c{i}")
            self.mgr.research_cycles[c.cycle_id] = c
        result = self.mgr.get_all_cycles()
        self.assertEqual(len(result), 3)

    def test_cycle_entry_has_required_keys(self):
        c = _make_cycle("ca")
        self.mgr.research_cycles["ca"] = c
        entry = self.mgr.get_all_cycles()[0]
        for key in ("cycle_id", "cycle_name", "status", "current_phase"):
            self.assertIn(key, entry)


# ---------------------------------------------------------------------------
# 8. get_cycle_history
# ---------------------------------------------------------------------------

class TestGetCycleHistory(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_manager()
        self.mgr.execution_history = [
            {"cycle_id": "c1", "event": "start"},
            {"cycle_id": "c2", "event": "start"},
            {"cycle_id": "c1", "event": "phase_done"},
        ]

    def test_filters_by_cycle_id(self):
        result = self.mgr.get_cycle_history("c1")
        self.assertEqual(len(result), 2)

    def test_no_results_for_unknown_cycle(self):
        result = self.mgr.get_cycle_history("zz")
        self.assertEqual(result, [])

    def test_does_not_include_other_cycles(self):
        result = self.mgr.get_cycle_history("c2")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["event"], "start")


# ---------------------------------------------------------------------------
# 9. Shared-reference integration with dict aliases
# ---------------------------------------------------------------------------

class TestSharedDictReferences(unittest.TestCase):
    """Verify that dict aliases (as used in ResearchPipeline) share state."""

    def test_mutation_via_alias_reflects_in_manager(self):
        mgr = _make_manager()
        alias = mgr.research_cycles   # simulate pipeline.research_cycles = session_manager.research_cycles
        c = _make_cycle("sr1")
        alias["sr1"] = c
        self.assertIn("sr1", mgr.research_cycles)

    def test_manager_mutation_reflects_in_alias(self):
        mgr = _make_manager()
        alias = mgr.active_cycles
        c = _make_cycle("sr2")
        mgr.active_cycles["sr2"] = c
        self.assertIn("sr2", alias)


# ---------------------------------------------------------------------------
# 10. Backward-compat imports from research_pipeline
# ---------------------------------------------------------------------------

class TestBackwardCompatImports(unittest.TestCase):
    def test_import_research_phase_from_pipeline(self):
        from src.research.research_pipeline import ResearchPhase as RP
        self.assertIs(RP, ResearchPhase)

    def test_import_research_cycle_status_from_pipeline(self):
        from src.research.research_pipeline import ResearchCycleStatus as RCS
        self.assertIs(RCS, ResearchCycleStatus)

    def test_import_research_cycle_from_pipeline(self):
        from src.research.research_pipeline import ResearchCycle as RC
        self.assertIs(RC, ResearchCycle)

    def test_import_from_research_package(self):
        from src.research import StudySessionManager as SSM
        self.assertIs(SSM, StudySessionManager)

    def test_pipeline_class_attr_same_objects(self):
        from src.research.research_pipeline import ResearchPipeline
        self.assertIs(ResearchPipeline.ResearchPhase, ResearchPhase)
        self.assertIs(ResearchPipeline.ResearchCycle, ResearchCycle)


if __name__ == "__main__":
    unittest.main()
