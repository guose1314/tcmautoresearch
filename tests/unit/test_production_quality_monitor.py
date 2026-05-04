from __future__ import annotations

import json
import uuid

from src.infrastructure.persistence import (
    DatabaseManager,
    LearningInsight,
    OutboxStatusEnum,
    PhaseExecution,
    PhaseStatusEnum,
    ProductionMonitoringOutboxORM,
    ResearchSession,
    SessionStatusEnum,
)
from src.monitoring.production_quality import ProductionQualityMonitor


def test_production_quality_monitor_aggregates_batch_log_and_db(tmp_path) -> None:
    log_path = tmp_path / "batch_distill_progress.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "file": "ok.txt",
                "ok": True,
                "status": 200,
                "llm_gateway": {
                    "summary": {
                        "call_count": 2,
                        "json_repair_status_counts": {
                            "not_requested": 1,
                            "repaired": 1,
                        },
                    }
                },
                "rule": {
                    "quality_tiers": {
                        "strong_rule": 3,
                        "weak_rule": 1,
                        "candidate_rule": 1,
                    }
                },
            },
            {
                "file": "timeout.txt",
                "file_path_key": "data/timeout.txt",
                "ok": False,
                "status": 0,
                "error": "read-timeout",
            },
        ],
    )
    db = _build_db_with_quality_sources()
    monitor = ProductionQualityMonitor(db, batch_log_path=log_path, max_log_records=50)

    payload = monitor.collect_dashboard_payload(recent_failure_limit=5)

    metrics = payload["metrics"]
    assert metrics["batch"]["total"] == 2
    assert metrics["batch"]["success_rate"] == 0.5
    assert metrics["llm"]["timeout_count"] == 1
    assert metrics["llm"]["json_repair_rate"] == 0.5
    assert metrics["graph_quality"]["weak_edge_ratio"] == 0.4
    assert metrics["graph_quality"]["candidate_edge_acceptance_rate"] == 0.5
    assert metrics["evidence"]["no_evidence_conclusion_rate"] == 0.5
    assert metrics["dlq"]["production_dlq_count"] == 1
    assert payload["recent_failures"][0]["category"] == "llm_timeout"


def test_production_quality_monitor_replays_dlq_to_outbox(tmp_path) -> None:
    log_path = tmp_path / "batch_distill_progress.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "file": "broken.txt",
                "file_path_key": "data/broken.txt",
                "ok": False,
                "status": 500,
                "error": "neo4j projection failed",
            }
        ],
    )
    db = _build_db_with_quality_sources()
    monitor = ProductionQualityMonitor(db, batch_log_path=log_path, max_log_records=10)
    monitor.collect_snapshot(persist=True)
    dlq_item = monitor.list_dlq(limit=1)[0]

    replay = monitor.replay_dlq_event(dlq_item["id"])

    assert replay["status"] == "queued"
    with db.session_scope() as session:
        row = session.get(
            ProductionMonitoringOutboxORM, uuid.UUID(replay["outbox_event_id"])
        )
        assert row is not None
        assert row.status == OutboxStatusEnum.PENDING.value
        assert row.payload["replay_of"] == dlq_item["event_key"]


def _build_db_with_quality_sources() -> DatabaseManager:
    db = DatabaseManager("sqlite:///:memory:")
    db.init_db()
    with db.session_scope() as session:
        research_session = ResearchSession(
            id=uuid.uuid4(),
            cycle_id="cycle-monitoring",
            cycle_name="Production Monitoring",
            status=SessionStatusEnum.ACTIVE,
        )
        session.add(research_session)
        session.flush()
        session.add(
            PhaseExecution(
                id=uuid.uuid4(),
                session_id=research_session.id,
                phase="publish",
                status=PhaseStatusEnum.COMPLETED,
                output_json=json.dumps(
                    {
                        "claims": [
                            {"claim": "缺少来源"},
                            {"claim": "具备来源", "evidence_ids": ["ev-1"]},
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
        )
        session.add(
            LearningInsight(
                insight_id="weak-edge-accepted",
                source="test",
                target_phase="analyze",
                insight_type="weak_edge_candidate",
                description="accepted weak edge",
                confidence=0.8,
                evidence_refs_json=[],
                status="accepted",
            )
        )
        session.add(
            LearningInsight(
                insight_id="weak-edge-rejected",
                source="test",
                target_phase="analyze",
                insight_type="weak_edge_candidate",
                description="rejected weak edge",
                confidence=0.4,
                evidence_refs_json=[],
                status="rejected",
            )
        )
    return db


def _write_jsonl(path, records) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
