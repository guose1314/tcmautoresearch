from __future__ import annotations

import unittest
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List

from src.contexts.catalog.cypher import LINK_DOCUMENT_TO_TOPIC
from src.contexts.catalog.service import CatalogContext
from src.generation.report_generator import ReportFormat, ReportGenerator
from src.infrastructure.persistence import DatabaseManager, OutboxEventORM
from src.orchestration.research_runtime_service import ResearchRuntimeService
from src.research.hypothesis_engine import Hypothesis, infer_methodology_tag
from src.storage.outbox import OutboxWorker, PgOutboxStore


class _RecordingNeo4jTx:
    def __init__(self, owner):
        self._owner = owner

    def run(self, query, **params):
        self._owner.executed_queries.append((query, params))
        return {"query": query, "params": params}


class _RecordingNeo4jSession:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        return _RecordingNeo4jTx(self._owner).run(query, **params)

    def execute_write(self, callback):
        return callback(_RecordingNeo4jTx(self._owner))


class _RecordingNeo4jBackend:
    def __init__(self, owner):
        self._owner = owner

    def session(self, database=None):
        self._owner.session_databases.append(database)
        return _RecordingNeo4jSession(self._owner)


class _RecordingNeo4jDriver:
    def __init__(self):
        self.database = "neo4j"
        self.executed_queries: List = []
        self.session_databases: List = []
        self.driver = _RecordingNeo4jBackend(self)


class _FakeCycle:
    def __init__(self):
        self.cycle_id = "cycle-seven-phase"
        self.cycle_name = "seven-phase-e2e"
        self.phase_executions = {}


class _SevenPhaseRuntimePipeline:
    ACTIVE_HARNESS: Dict[str, object] = {}

    def __init__(self, config=None, *, storage_factory=None):
        self.config = config or {}
        self.storage_factory = storage_factory
        self.cycle = _FakeCycle()
        self.completed = False
        self.cleaned = False
        self.harness = self.ACTIVE_HARNESS

    def create_research_cycle(self, **kwargs):
        cycle_id = kwargs.get("cycle_id")
        cycle_name = kwargs.get("cycle_name")
        if cycle_id:
            self.cycle.cycle_id = cycle_id
        if cycle_name:
            self.cycle.cycle_name = cycle_name
        return self.cycle

    def start_research_cycle(self, _cycle_id):
        return True

    def execute_research_phase(self, cycle_id, phase, phase_context=None):
        phase_name = phase.value if hasattr(phase, "value") else str(phase)
        phase_context = dict(phase_context or {})
        topic = str(
            phase_context.get("question")
            or phase_context.get("research_question")
            or self.harness.get("topic")
            or ""
        ).strip()
        result = deepcopy(self.harness["phase_results"][phase_name])
        result.setdefault("metadata", {})
        result["metadata"].update(
            {
                "received_question": topic,
                "received_phase_context": dict(phase_context),
            }
        )

        if phase_name == "analyze" and not self.harness.get("event_id"):
            event_id = self.harness["store"].enqueue(
                aggregate_type="document",
                aggregate_id=self.harness["document_id"],
                event_type="catalog.topic_membership.upserted",
                payload={
                    "document_id": self.harness["document_id"],
                    "topics": [
                        {
                            "key": self.harness["topic_key"],
                            "label": topic,
                            "description": f"来自 {self.harness['fixture_name']} 的主题归类",
                            "weight": 0.9,
                        }
                    ],
                },
            )
            self.harness["event_id"] = event_id

        if phase_name == "publish" and not self.harness.get("report_output_path"):
            session_result = {
                "session_id": cycle_id,
                "research_question": topic,
                "phase_results": self.harness["phase_results"],
                "metadata": {
                    "title": f"{topic} 七阶段科研报告",
                    "fixture_name": self.harness["fixture_name"],
                },
            }
            report = self.harness["report_generator"].generate_report(
                session_result,
                ReportFormat.MARKDOWN,
            )
            result["results"]["output_files"]["markdown"] = report.output_path
            result["artifacts"] = [
                {"name": "markdown", "path": report.output_path, "type": "file"}
            ]
            result["metadata"].update({"report_count": 1, "report_error_count": 0})
            self.harness["report_output_path"] = report.output_path

        self.cycle.phase_executions[phase] = {"result": deepcopy(result)}
        return result

    def complete_research_cycle(self, _cycle_id):
        self.completed = True
        return True

    def cleanup(self):
        self.cleaned = True
        return True

    def get_learning_strategy(self):
        return {}

    def get_previous_iteration_feedback(self):
        return {}

    def _serialize_cycle(self, cycle):
        return {
            "cycle_id": cycle.cycle_id,
            "cycle_name": cycle.cycle_name,
            "phase_executions": {
                phase.value: payload
                for phase, payload in cycle.phase_executions.items()
            },
        }


class SevenPhasePipelineE2ETest(unittest.TestCase):
    FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
    FIXTURE_FILES = [
        "118-增订医方歌诀-清-王泰林.txt",
        "121-医方歌括-清-王泰林.txt",
        "196-产后十八论-清-佚名.txt",
        "287-脉诀考证-明-李时珍.txt",
        "503-脉诀-宋-崔嘉彦.txt",
    ]
    PHASES = [
        "observe",
        "hypothesis",
        "experiment",
        "experiment_execution",
        "analyze",
        "publish",
        "reflect",
    ]

    def test_five_selected_classics_walkthrough_with_pg_neo4j_imrd_and_outbox(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "seven_phase.sqlite3"
            db_manager = DatabaseManager(f"sqlite:///{db_path}")
            db_manager.init_db()
            store = PgOutboxStore(db_manager)
            neo4j_driver = _RecordingNeo4jDriver()
            catalog = CatalogContext(neo4j_driver)
            output_dir = Path(tmp_dir) / "reports"
            report_generator = ReportGenerator({"output_dir": str(output_dir)})
            report_generator.initialize()
            try:
                processed_event_ids: List[str] = []
                research_pipeline_module = import_module(
                    "src.research.research_pipeline"
                )
                original_pipeline = research_pipeline_module.ResearchPipeline

                def _handle_event(event: Dict) -> None:
                    payload = dict(event.get("payload") or {})
                    processed_event_ids.append(str(event.get("id")))
                    catalog.upsert_topic_membership(
                        payload["document_id"],
                        payload.get("topics") or [],
                    )

                worker = OutboxWorker(
                    store,
                    handler=_handle_event,
                    poll_interval=0.01,
                    batch_size=16,
                )
                research_pipeline_module.ResearchPipeline = _SevenPhaseRuntimePipeline
                try:
                    for index, fixture_name in enumerate(self.FIXTURE_FILES, start=1):
                        fixture_path = self.FIXTURE_DIR / fixture_name
                        self.assertTrue(
                            fixture_path.exists(), f"fixture missing: {fixture_name}"
                        )
                        raw_text = fixture_path.read_text(encoding="utf-8")
                        self.assertLessEqual(fixture_path.stat().st_size, 50 * 1024)
                        self.assertTrue(raw_text.strip())

                        topic = fixture_path.stem
                        hypothesis = Hypothesis(
                            hypothesis_id=f"hyp-{index}",
                            title=f"{topic} 的知识假设",
                            statement=f"围绕 {topic} 构建 7 阶段科研验证链路。",
                            rationale=f"基于 {topic} 文本抽取的证据线索生成。",
                            novelty=0.78,
                            feasibility=0.83,
                            evidence_support=0.81,
                            confidence=0.8,
                            source_gap_type="classification_gap"
                            if index % 2
                            else "philology_gap",
                            source_entities=[topic],
                            methodology_tag=infer_methodology_tag(
                                "classification_gap" if index % 2 else "philology_gap"
                            ),
                            evidence_grade="B" if index % 2 else "A",
                        )

                        document_id = f"doc-{index}"
                        phase_results = self._build_phase_results(raw_text, hypothesis)
                        harness = {
                            "document_id": document_id,
                            "event_id": None,
                            "fixture_name": fixture_name,
                            "phase_results": phase_results,
                            "report_generator": report_generator,
                            "report_output_path": None,
                            "store": store,
                            "topic": topic,
                            "topic_key": f"topic-{index}",
                        }
                        _SevenPhaseRuntimePipeline.ACTIVE_HARNESS = harness
                        runtime = ResearchRuntimeService(
                            {
                                "pipeline_config": {},
                                "phases": self.PHASES,
                            }
                        )
                        try:
                            result = runtime.run(
                                topic,
                                cycle_id=f"session-{index}",
                                phase_contexts={
                                    phase_name: {
                                        "document_id": document_id,
                                        "fixture_name": fixture_name,
                                        "raw_text": raw_text,
                                    }
                                    for phase_name in self.PHASES
                                },
                            )
                        finally:
                            runtime.close()

                        self.assertEqual(
                            result.orchestration_result.status, "completed"
                        )
                        self.assertEqual(len(result.orchestration_result.phases), 7)
                        self.assertTrue(
                            all(
                                phase.status == "completed"
                                for phase in result.orchestration_result.phases
                            )
                        )
                        self.assertEqual(
                            hypothesis.methodology_tag,
                            result.phase_results["hypothesis"]["results"]["hypotheses"][
                                0
                            ]["methodology_tag"],
                        )
                        self.assertEqual(
                            hypothesis.evidence_grade,
                            result.phase_results["hypothesis"]["results"]["hypotheses"][
                                0
                            ]["evidence_grade"],
                        )
                        self.assertIn(
                            "statistical_analysis",
                            result.orchestration_result.analysis_results,
                        )
                        self.assertIn(
                            "evidence", result.orchestration_result.research_artifact
                        )

                        report_path = Path(
                            result.phase_results["publish"]["results"]["output_files"][
                                "markdown"
                            ]
                        )
                        self.assertTrue(report_path.exists(), "IMRD markdown 未落盘")

                        batch_stats = self._run_worker_once(worker)
                        self.assertGreaterEqual(batch_stats["processed"], 1)
                        self.assertIn(harness["event_id"], processed_event_ids)
                finally:
                    research_pipeline_module.ResearchPipeline = original_pipeline

                with db_manager.session_scope() as session:
                    processed_rows = (
                        session.query(OutboxEventORM)
                        .order_by(OutboxEventORM.created_at.asc())
                        .all()
                    )
                    self.assertEqual(len(processed_rows), 5)
                    self.assertTrue(
                        all(row.status == "processed" for row in processed_rows),
                        "outbox_events.status 必须全部为 processed",
                    )

                belongs_to_topic_writes = [
                    (query, params)
                    for query, params in neo4j_driver.executed_queries
                    if "BELONGS_TO_TOPIC" in str(query)
                ]
                self.assertGreaterEqual(len(belongs_to_topic_writes), 5)
                self.assertTrue(
                    all(
                        str(query).strip() == LINK_DOCUMENT_TO_TOPIC
                        for query, _ in belongs_to_topic_writes
                    ),
                    "应通过 catalog cypher 写入 BELONGS_TO_TOPIC",
                )

                report_files = list(output_dir.glob("*.md"))
                self.assertEqual(len(report_files), 5)
            finally:
                report_generator.cleanup()
                db_manager.close()

    @staticmethod
    def _build_phase_results(raw_text: str, hypothesis: Hypothesis) -> Dict[str, Dict]:
        snippet = "".join(raw_text.splitlines())[:180]
        findings = [snippet[:60] or hypothesis.title]
        return {
            "observe": {
                "phase": "observe",
                "status": "completed",
                "results": {
                    "observations": [snippet[:80]],
                    "findings": findings,
                    "literature_pipeline": {
                        "record_count": 1,
                        "summaries": [snippet[:100]],
                        "evidence_points": [f"证据线索: {hypothesis.title}"],
                    },
                },
                "metadata": {},
                "error": None,
            },
            "hypothesis": {
                "phase": "hypothesis",
                "status": "completed",
                "results": {
                    "hypotheses": [hypothesis.to_dict()],
                },
                "metadata": {},
                "error": None,
            },
            "experiment": {
                "phase": "experiment",
                "status": "completed",
                "results": {
                    "study_design": "comparative textual analysis",
                    "methodology_tag": hypothesis.methodology_tag,
                },
                "metadata": {},
                "error": None,
            },
            "experiment_execution": {
                "phase": "experiment_execution",
                "status": "completed",
                "results": {
                    "execution_status": "completed",
                    "captured_documents": 1,
                },
                "metadata": {},
                "error": None,
            },
            "analyze": {
                "phase": "analyze",
                "status": "completed",
                "results": {
                    "analysis_summary": f"方法学标签={hypothesis.methodology_tag}",
                    "evidence_grade": hypothesis.evidence_grade,
                },
                "metadata": {},
                "error": None,
            },
            "publish": {
                "phase": "publish",
                "status": "completed",
                "results": {
                    "deliverables": ["imrd_markdown"],
                    "abstract": f"{hypothesis.title} 的结构化研究摘要",
                    "analysis_results": {"statistical_analysis": {"p_value": 0.03}},
                    "research_artifact": {
                        "evidence": [{"id": hypothesis.hypothesis_id}]
                    },
                    "output_files": {},
                },
                "metadata": {},
                "error": None,
            },
            "reflect": {
                "phase": "reflect",
                "status": "completed",
                "results": {
                    "next_actions": ["补充专家复核"],
                },
                "metadata": {},
                "error": None,
            },
        }

    @staticmethod
    def _run_worker_once(worker: OutboxWorker) -> Dict[str, int]:
        import asyncio

        return asyncio.run(worker.run_once())


if __name__ == "__main__":
    unittest.main()
