"""Phase L-1 — `PhaseOrchestrator` 拆分外观层单元测试。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.research.phase_orchestrator_facade import (
    CONTRACT_VERSION,
    PHASE_FACADE_CONTRACT_VERSION,
    PhaseGraphExporter,
    PhaseOrchestratorFacades,
    PhasePersistence,
    PhaseRunner,
    build_phase_orchestrator_facades,
)


def _make_orchestrator() -> MagicMock:
    """构造一个 ``PhaseOrchestrator`` 替身，仅模拟 facade 用到的方法。"""
    orch = MagicMock(name="PhaseOrchestrator")
    orch.get_handler.return_value = SimpleNamespace(name="handler")
    orch._execute_phase_internal.return_value = {"status": "completed", "phase": "observe"}
    orch._persist_cycle_phase_executions.return_value = {"observe": {"id": "p1"}}
    orch._persist_cycle_artifacts.return_value = [{"id": "a1"}]
    orch._persist_cycle_learning_feedback.return_value = {"id": "f1"}
    orch._persist_cycle_observe_documents.return_value = [{"id": "d1"}]
    orch._project_cycle_to_neo4j.return_value = {"status": "ok"}
    orch.export_pipeline_data.return_value = True
    orch.get_pipeline_summary.return_value = {"pipeline_summary": {"total_cycles": 0}}
    return orch


class TestContractVersion(unittest.TestCase):
    def test_contract_version_is_v1(self) -> None:
        self.assertEqual(CONTRACT_VERSION, "phase-orchestrator-facade-v1")
        self.assertEqual(PHASE_FACADE_CONTRACT_VERSION, CONTRACT_VERSION)


class TestPhaseRunner(unittest.TestCase):
    def test_get_handler_delegates(self) -> None:
        orch = _make_orchestrator()
        runner = PhaseRunner(orchestrator=orch)
        handler = runner.get_handler("observe")
        orch.get_handler.assert_called_once_with("observe")
        self.assertIs(handler, orch.get_handler.return_value)

    def test_execute_delegates_with_context(self) -> None:
        orch = _make_orchestrator()
        runner = PhaseRunner(orchestrator=orch)
        result = runner.execute(phase="observe", cycle="cycle-1", context={"k": 1})
        orch._execute_phase_internal.assert_called_once_with("observe", "cycle-1", {"k": 1})
        self.assertEqual(result["status"], "completed")

    def test_execute_default_context_is_empty_dict(self) -> None:
        orch = _make_orchestrator()
        runner = PhaseRunner(orchestrator=orch)
        runner.execute(phase="observe", cycle="cycle-1")
        args, _ = orch._execute_phase_internal.call_args
        self.assertEqual(args[2], {})


class TestPhasePersistence(unittest.TestCase):
    def test_persist_phase_executions_delegates(self) -> None:
        orch = _make_orchestrator()
        persistence = PhasePersistence(orchestrator=orch)
        result = persistence.persist_phase_executions(repository="repo", cycle="c", session="s")
        orch._persist_cycle_phase_executions.assert_called_once_with("repo", "c", session="s")
        self.assertIn("observe", result)

    def test_persist_artifacts_delegates(self) -> None:
        orch = _make_orchestrator()
        persistence = PhasePersistence(orchestrator=orch)
        records = persistence.persist_artifacts(
            repository="repo", cycle="c", phase_records={"observe": {"id": "p1"}}
        )
        orch._persist_cycle_artifacts.assert_called_once()
        self.assertEqual(records, [{"id": "a1"}])

    def test_persist_learning_feedback_delegates(self) -> None:
        orch = _make_orchestrator()
        persistence = PhasePersistence(orchestrator=orch)
        feedback = persistence.persist_learning_feedback(
            repository="repo", cycle="c", phase_records={}
        )
        orch._persist_cycle_learning_feedback.assert_called_once()
        self.assertEqual(feedback, {"id": "f1"})

    def test_persist_observe_documents_delegates(self) -> None:
        orch = _make_orchestrator()
        persistence = PhasePersistence(orchestrator=orch)
        docs = persistence.persist_observe_documents(
            repository="repo", cycle="c", phase_records={}
        )
        orch._persist_cycle_observe_documents.assert_called_once()
        self.assertEqual(docs, [{"id": "d1"}])


class TestPhaseGraphExporter(unittest.TestCase):
    def test_project_cycle_to_neo4j_delegates(self) -> None:
        orch = _make_orchestrator()
        exporter = PhaseGraphExporter(orchestrator=orch)
        result = exporter.project_cycle_to_neo4j(
            neo4j_driver="drv",
            cycle="c",
            session_record={"id": "s"},
            phase_records={},
            artifact_records=[],
            observe_documents=[],
        )
        orch._project_cycle_to_neo4j.assert_called_once()
        self.assertEqual(result, {"status": "ok"})

    def test_export_pipeline_data_delegates(self) -> None:
        orch = _make_orchestrator()
        exporter = PhaseGraphExporter(orchestrator=orch)
        self.assertTrue(exporter.export_pipeline_data("/tmp/out.json"))
        orch.export_pipeline_data.assert_called_once_with("/tmp/out.json")

    def test_get_pipeline_summary_delegates(self) -> None:
        orch = _make_orchestrator()
        exporter = PhaseGraphExporter(orchestrator=orch)
        summary = exporter.get_pipeline_summary()
        self.assertIn("pipeline_summary", summary)


class TestBuildFacades(unittest.TestCase):
    def test_build_returns_three_facades(self) -> None:
        orch = _make_orchestrator()
        facades = build_phase_orchestrator_facades(orch)
        self.assertIsInstance(facades, PhaseOrchestratorFacades)
        self.assertIsInstance(facades.runner, PhaseRunner)
        self.assertIsInstance(facades.persistence, PhasePersistence)
        self.assertIsInstance(facades.exporter, PhaseGraphExporter)
        self.assertEqual(facades.contract_version, CONTRACT_VERSION)

    def test_facades_share_same_orchestrator(self) -> None:
        orch = _make_orchestrator()
        facades = build_phase_orchestrator_facades(orch)
        self.assertIs(facades.runner.orchestrator, orch)
        self.assertIs(facades.persistence.orchestrator, orch)
        self.assertIs(facades.exporter.orchestrator, orch)


if __name__ == "__main__":
    unittest.main()
