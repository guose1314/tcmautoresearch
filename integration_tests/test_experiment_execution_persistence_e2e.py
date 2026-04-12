from __future__ import annotations

import os
import socket
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from src.infrastructure.research_session_repo import ResearchSessionRepository
from src.infrastructure.runtime_config_assembler import build_runtime_assembly
from src.orchestration.research_runtime_service import ResearchRuntimeService
from src.storage.backend_factory import StorageBackendFactory

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENABLE_ENV = "TCM_RUN_DEV_PERSISTENCE_E2E"
_CONFIG_PATH_ENV = "TCM_DEV_PERSISTENCE_E2E_CONFIG"
_ENVIRONMENT_ENV = "TCM_DEV_PERSISTENCE_E2E_ENV"


def _port_open(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(2)
        try:
            sock.connect((host, int(port)))
        except OSError:
            return False
    return True


@unittest.skipUnless(
    os.environ.get(_ENABLE_ENV) == "1",
    "设置 TCM_RUN_DEV_PERSISTENCE_E2E=1 后运行真实 PostgreSQL + Neo4j experiment_execution 持久化回归",
)
class ExperimentExecutionPersistenceE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        environment = str(os.environ.get(_ENVIRONMENT_ENV, "development") or "development").strip() or "development"
        config_path = str(os.environ.get(_CONFIG_PATH_ENV) or "").strip() or None
        assembly = build_runtime_assembly(
            root_path=_REPO_ROOT,
            config_path=config_path,
            environment=environment,
        )
        runtime_config = deepcopy(assembly.runtime_config)
        database_config = runtime_config.get("database") or {}
        neo4j_config = runtime_config.get("neo4j") or {}

        if str(database_config.get("type") or "").strip().lower() != "postgresql":
            raise RuntimeError("真实持久化回归要求 database.type=postgresql")
        if not bool(neo4j_config.get("enabled")):
            raise RuntimeError("真实持久化回归要求 neo4j.enabled=true")

        pg_host = str(database_config.get("host") or "127.0.0.1")
        pg_port = int(database_config.get("port") or 5432)
        neo4j_uri = str(neo4j_config.get("uri") or "neo4j://127.0.0.1:7687")
        parsed_neo4j = urlparse(neo4j_uri)
        neo4j_host = parsed_neo4j.hostname or "127.0.0.1"
        neo4j_port = parsed_neo4j.port or 7687

        if not _port_open(pg_host, pg_port):
            raise RuntimeError(f"PostgreSQL 不可达: {pg_host}:{pg_port}")
        if not _port_open(neo4j_host, neo4j_port):
            raise RuntimeError(f"Neo4j 不可达: {neo4j_host}:{neo4j_port}")

        factory = StorageBackendFactory(runtime_config)
        init_report = factory.initialize()
        if init_report.get("pg_status") != "active":
            raise RuntimeError(f"PostgreSQL 初始化失败: {init_report.get('pg_status')}")
        if init_report.get("neo4j_status") != "active":
            raise RuntimeError(f"Neo4j 初始化失败: {init_report.get('neo4j_status')}")

        cls._environment = environment
        cls._output_root = (_REPO_ROOT / "output" / environment / "integration_persistence").resolve()
        cls._output_root.mkdir(parents=True, exist_ok=True)
        cls._orchestrator_config = deepcopy(assembly.orchestrator_config)
        cls._factory = factory
        cls._repository = ResearchSessionRepository(factory.db_manager)

    @classmethod
    def tearDownClass(cls):
        factory = getattr(cls, "_factory", None)
        if factory is not None:
            factory.close()
        super().tearDownClass()

    def setUp(self):
        self._cycle_ids: list[str] = []
        self._tempdirs: list[tempfile.TemporaryDirectory[str]] = []

    def tearDown(self):
        for cycle_id in reversed(self._cycle_ids):
            self._cleanup_cycle(cycle_id)
        for tempdir in reversed(self._tempdirs):
            tempdir.cleanup()
        super().tearDown()

    def test_persists_skipped_when_execution_inputs_absent(self):
        _, runtime_result, snapshot, graph_projection = self._run_cycle(imported_inputs=False)

        self.assertEqual(runtime_result.orchestration_result.status, "completed")
        self.assertEqual(runtime_result.phase_results["experiment_execution"]["status"], "skipped")
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["current_phase"], "reflect")
        self.assertEqual(len(snapshot["phase_executions"]), 7)

        phase_map = {item["phase"]: item for item in snapshot["phase_executions"]}
        self.assertEqual(phase_map["experiment_execution"]["status"], "skipped")

        completed_phases = self._completed_phases(snapshot)
        self.assertNotIn("experiment_execution", completed_phases)
        self.assertEqual(self._completed_phase_count(snapshot), 6)

        self.assertEqual(graph_projection["session_status"], "completed")
        self.assertEqual(graph_projection["current_phase"], "reflect")
        self.assertEqual(graph_projection["has_phase_count"], 7)
        self.assertEqual(graph_projection["phase_status"], "skipped")

    def test_persists_completed_when_execution_inputs_present(self):
        _, runtime_result, snapshot, graph_projection = self._run_cycle(imported_inputs=True)

        self.assertEqual(runtime_result.orchestration_result.status, "completed")
        self.assertEqual(runtime_result.phase_results["experiment_execution"]["status"], "completed")
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["current_phase"], "reflect")
        self.assertEqual(len(snapshot["phase_executions"]), 7)

        phase_map = {item["phase"]: item for item in snapshot["phase_executions"]}
        self.assertEqual(phase_map["experiment_execution"]["status"], "completed")

        completed_phases = self._completed_phases(snapshot)
        self.assertIn("experiment_execution", completed_phases)
        self.assertEqual(self._completed_phase_count(snapshot), 7)

        self.assertEqual(graph_projection["session_status"], "completed")
        self.assertEqual(graph_projection["current_phase"], "reflect")
        self.assertEqual(graph_projection["has_phase_count"], 7)
        self.assertEqual(graph_projection["phase_status"], "completed")

    def _run_cycle(self, *, imported_inputs: bool):
        tempdir = tempfile.TemporaryDirectory(dir=str(self._output_root))
        self._tempdirs.append(tempdir)
        output_dir = Path(tempdir.name)
        cycle_id = (
            f"e2e_experiment_execution_completed_{uuid4().hex}"
            if imported_inputs
            else f"e2e_experiment_execution_skipped_{uuid4().hex}"
        )
        self._cycle_ids.append(cycle_id)

        runtime_service = ResearchRuntimeService(deepcopy(self._orchestrator_config))
        runtime_result = runtime_service.run(
            "四君子汤治疗脾气虚证的配伍与机制研究",
            cycle_id=cycle_id,
            cycle_name="experiment-execution-persistence-e2e",
            description="真实 experiment_execution 持久化回归",
            scope="中医古籍方剂研究",
            phase_contexts=self._build_phase_contexts(output_dir, imported_inputs=imported_inputs),
        )

        snapshot = self._repository.get_full_snapshot(cycle_id)
        if snapshot is None:
            self.fail(f"未在 PostgreSQL 中找到会话快照: {cycle_id}")

        graph_projection = self._read_graph_projection(cycle_id)
        if graph_projection is None:
            self.fail(f"未在 Neo4j 中找到 experiment_execution 投影: {cycle_id}")

        return cycle_id, runtime_result, snapshot, graph_projection

    def _build_phase_contexts(self, output_dir: Path, *, imported_inputs: bool) -> dict[str, dict[str, object]]:
        contexts: dict[str, dict[str, object]] = {
            "observe": {
                "use_ctext_whitelist": False,
                "use_local_corpus": False,
                "run_literature_retrieval": False,
                "run_preprocess_and_extract": False,
                "use_llm_generation": False,
                "data_source": "manual",
            },
            "hypothesis": {
                "use_llm_generation": False,
                "entities": [
                    {"name": "四君子汤", "type": "formula", "confidence": 0.95},
                    {"name": "脾气虚证", "type": "syndrome", "confidence": 0.9},
                    {"name": "补气", "type": "efficacy", "confidence": 0.85},
                ],
                "contradictions": ["部分古籍剂量记载不完全一致"],
            },
            "experiment": {
                "use_llm_protocol_generation": False,
            },
            "publish": {
                "paper_output_formats": ["markdown"],
                "report_output_formats": ["markdown"],
                "paper_output_dir": str(output_dir),
                "report_output_dir": str(output_dir),
                "output_dir": str(output_dir),
            },
        }

        if not imported_inputs:
            return contexts

        execution_file = output_dir / "experiment_execution_import.csv"
        execution_file.write_text(
            "formula,syndrome,herbs\n四君子汤,脾气虚证,党参|白术|茯苓|甘草\n",
            encoding="utf-8",
        )
        contexts["experiment_execution"] = {
            "analysis_records": [
                {
                    "formula": "四君子汤",
                    "syndrome": "脾气虚证",
                    "herbs": ["党参", "白术", "茯苓", "甘草"],
                    "source": "integration_e2e",
                }
            ],
            "analysis_relationships": [
                {
                    "source": "四君子汤",
                    "target": "党参",
                    "type": "contains",
                    "source_type": "formula",
                    "target_type": "herb",
                    "metadata": {"confidence": 0.92, "source": "integration_e2e"},
                }
            ],
            "sampling_events": [{"batch": "e2e-batch-1", "size": 24}],
            "execution_summary": {
                "execution_status": "results_imported",
                "real_world_validation_status": "results_imported",
            },
            "output_files": {"csv": str(execution_file)},
        }
        return contexts

    def _read_graph_projection(self, cycle_id: str):
        neo4j_driver = self._factory.neo4j_driver
        with neo4j_driver.driver.session(database=neo4j_driver.database) as session:
            session_record = session.execute_read(
                lambda tx: tx.run(
                    """
                    MATCH (s:ResearchSession {cycle_id: $cycle_id})
                    OPTIONAL MATCH (s)-[:HAS_PHASE]->(phase:ResearchPhaseExecution)
                    RETURN s.status AS session_status,
                           s.current_phase AS current_phase,
                           count(phase) AS has_phase_count
                    """,
                    cycle_id=cycle_id,
                ).single()
            )
            phase_record = session.execute_read(
                lambda tx: tx.run(
                    """
                    MATCH (phase:ResearchPhaseExecution {cycle_id: $cycle_id, phase: 'experiment_execution'})
                    RETURN phase.status AS phase_status
                    """,
                    cycle_id=cycle_id,
                ).single()
            )

        if session_record is None or phase_record is None:
            return None
        return {
            "session_status": session_record["session_status"],
            "current_phase": session_record["current_phase"],
            "has_phase_count": int(session_record["has_phase_count"] or 0),
            "phase_status": phase_record["phase_status"],
        }

    def _cleanup_cycle(self, cycle_id: str) -> None:
        try:
            self._repository.delete_session(cycle_id)
        except Exception:
            pass

        neo4j_driver = getattr(self._factory, "neo4j_driver", None)
        if neo4j_driver is None:
            return
        try:
            with neo4j_driver.driver.session(database=neo4j_driver.database) as session:
                session.execute_write(
                    lambda tx: tx.run(
                        """
                        MATCH (n)
                        WHERE n.cycle_id = $cycle_id
                           OR (n:ResearchSession AND n.id = $cycle_id)
                        DETACH DELETE n
                        """,
                        cycle_id=cycle_id,
                    )
                )
        except Exception:
            pass

    @staticmethod
    def _completed_phases(snapshot: dict[str, object]) -> list[str]:
        metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        completed_phases = metadata.get("completed_phases") if isinstance(metadata, dict) else []
        if isinstance(completed_phases, list):
            return [str(item) for item in completed_phases]
        analysis_summary = metadata.get("analysis_summary") if isinstance(metadata, dict) else {}
        if isinstance(analysis_summary, dict) and isinstance(analysis_summary.get("completed_phases"), list):
            return [str(item) for item in analysis_summary.get("completed_phases")]
        return []

    @staticmethod
    def _completed_phase_count(snapshot: dict[str, object]) -> int:
        metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        analysis_summary = metadata.get("analysis_summary") if isinstance(metadata, dict) else {}
        if isinstance(analysis_summary, dict) and analysis_summary.get("completed_phase_count") is not None:
            return int(analysis_summary.get("completed_phase_count") or 0)
        return len(ExperimentExecutionPersistenceE2ETest._completed_phases(snapshot))


if __name__ == "__main__":
    unittest.main()