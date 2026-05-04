from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import or_

from src.infrastructure.persistence import (
    DatabaseManager,
    LearningInsight,
    OutboxDLQORM,
    OutboxEventORM,
    OutboxStatusEnum,
    PhaseExecution,
    ProductionMonitoringDLQORM,
    ProductionMonitoringOutboxORM,
    ProductionQualitySnapshotORM,
    ResearchArtifact,
)
from src.learning.learning_insight_repo import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_SUPERSEDED,
    normalize_status,
)
from src.learning.weak_edge_candidate_repo import COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES

logger = logging.getLogger(__name__)

PRODUCTION_QUALITY_CONTRACT_VERSION = "production-quality-monitor-v1"
DEFAULT_BATCH_LOG_PATH = Path("logs") / "batch_distill_progress.jsonl"
DEFAULT_MAX_LOG_RECORDS = 5000
DEFAULT_DB_SCAN_LIMIT = 200

_CLAIM_COLLECTION_KEYS = {
    "claim",
    "claims",
    "conclusion",
    "conclusions",
    "finding",
    "findings",
    "hypothesis",
    "hypotheses",
    "key_findings",
}
_EVIDENCE_KEYS = {
    "evidence",
    "evidence_id",
    "evidence_ids",
    "evidence_refs",
    "evidence_records",
    "citations",
    "citation",
    "source_ref",
    "source_refs",
    "supporting_evidence",
    "references",
}


class ProductionQualityMonitor:
    """Aggregate production batch quality metrics and keep a replayable DLQ."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager],
        *,
        batch_log_path: Optional[Path | str] = None,
        max_log_records: int = DEFAULT_MAX_LOG_RECORDS,
        db_scan_limit: int = DEFAULT_DB_SCAN_LIMIT,
    ) -> None:
        self._db = db_manager
        self._batch_log_path = Path(batch_log_path or DEFAULT_BATCH_LOG_PATH)
        self._max_log_records = max(1, int(max_log_records or DEFAULT_MAX_LOG_RECORDS))
        self._db_scan_limit = max(1, int(db_scan_limit or DEFAULT_DB_SCAN_LIMIT))

    def collect_dashboard_payload(
        self, *, recent_failure_limit: int = 12
    ) -> Dict[str, Any]:
        payload = self.collect_snapshot(persist=True)
        payload["recent_failures"] = self.list_dlq(limit=recent_failure_limit)
        return payload

    def collect_snapshot(self, *, persist: bool = True) -> Dict[str, Any]:
        read_result = _read_recent_batch_log(
            self._batch_log_path, self._max_log_records
        )
        records = [record for _, record in read_result["records"]]
        generated_at = _now_iso()
        log_metrics = _aggregate_batch_log(records)
        db_metrics = self._collect_db_metrics(read_result["records"])
        metrics = _merge_metric_groups(log_metrics, db_metrics)
        source = {
            "batch_log_path": str(self._batch_log_path),
            "batch_log_exists": self._batch_log_path.exists(),
            "log_record_count_total": read_result["total_lines"],
            "log_record_count_window": len(records),
            "invalid_log_line_count": read_result["invalid_lines"],
            "max_log_records": self._max_log_records,
        }
        payload = {
            "contract_version": PRODUCTION_QUALITY_CONTRACT_VERSION,
            "generated_at": generated_at,
            "metrics": metrics,
            "source": source,
        }
        if persist and self._db is not None:
            self._persist_snapshot(metrics, source)
        return payload

    def list_dlq(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        safe_limit = max(1, min(int(limit or 20), 200))
        items: List[Dict[str, Any]] = []
        with self._db.session_scope() as session:
            rows = (
                session.query(ProductionMonitoringDLQORM)
                .order_by(ProductionMonitoringDLQORM.last_seen_at.desc())
                .limit(safe_limit)
                .all()
            )
            for row in rows:
                items.append(_production_dlq_to_dict(row))
            if len(items) < safe_limit:
                graph_rows = (
                    session.query(OutboxDLQORM)
                    .order_by(OutboxDLQORM.moved_at.desc())
                    .limit(safe_limit - len(items))
                    .all()
                )
                items.extend(_graph_dlq_to_dict(row) for row in graph_rows)
        return items

    def replay_dlq_event(self, event_id: str) -> Dict[str, Any]:
        if self._db is None:
            raise RuntimeError("database unavailable")
        normalized_id = str(event_id or "").strip()
        if not normalized_id:
            raise ValueError("event_id is required")
        with self._db.session_scope() as session:
            row = _load_production_dlq_row(session, normalized_id)
            if row is None:
                raise LookupError("DLQ event not found")
            next_replay_count = int(row.replay_count or 0) + 1
            replay_key = f"replay:{row.event_key}:{next_replay_count}"
            outbox = ProductionMonitoringOutboxORM(
                id=uuid.uuid4(),
                event_key=replay_key,
                event_type=row.event_type,
                source=row.source,
                aggregate_id=row.aggregate_id,
                payload={
                    "replay_of": row.event_key,
                    "dlq_event_id": str(row.id),
                    "payload": dict(row.payload or {}),
                },
                status=OutboxStatusEnum.PENDING.value,
            )
            session.add(outbox)
            row.replay_count = next_replay_count
            row.replay_status = "queued"
            row.last_replayed_at = _now()
            session.flush()
            return {
                "status": "queued",
                "dlq_event_id": str(row.id),
                "outbox_event_id": str(outbox.id),
                "event_key": replay_key,
                "replay_count": next_replay_count,
            }

    def _collect_db_metrics(
        self, line_records: Sequence[Tuple[int, Mapping[str, Any]]]
    ) -> Dict[str, Any]:
        if self._db is None:
            return _empty_db_metrics()
        with self._db.session_scope() as session:
            self._ingest_failed_batch_events(session, line_records)
            session.flush()
            candidate = _candidate_edge_metrics(session)
            no_evidence = _no_evidence_metrics(session, limit=self._db_scan_limit)
            outbox = _outbox_metrics(session)
            dlq = _dlq_metrics(session)
            neo4j = _neo4j_projection_metrics(session)
        return {
            "candidate_edges": candidate,
            "evidence": no_evidence,
            "outbox": outbox,
            "dlq": dlq,
            "neo4j": neo4j,
        }

    def _ingest_failed_batch_events(
        self, session: Any, line_records: Sequence[Tuple[int, Mapping[str, Any]]]
    ) -> None:
        now = _now()
        for line_no, record in line_records:
            if _is_success_record(record):
                continue
            category = _failure_category(record)
            event_key = _batch_failure_event_key(record)
            aggregate_id = str(
                record.get("file_path_key")
                or record.get("source_file")
                or record.get("file")
                or "batch"
            )[:255]
            payload = {
                "line_no": line_no,
                "file": record.get("file"),
                "file_path_key": record.get("file_path_key"),
                "status": record.get("status"),
                "error": record.get("error"),
                "elapsed_s": record.get("elapsed_s"),
                "record": _compact_record(record),
            }
            outbox = (
                session.query(ProductionMonitoringOutboxORM)
                .filter(ProductionMonitoringOutboxORM.event_key == event_key)
                .one_or_none()
            )
            if outbox is None:
                outbox = ProductionMonitoringOutboxORM(
                    id=uuid.uuid4(),
                    event_key=event_key,
                    event_type="batch.file.failed",
                    source="batch_distill_progress",
                    aggregate_id=aggregate_id,
                    payload=payload,
                    status=OutboxStatusEnum.FAILED.value,
                    last_error=str(record.get("error") or "batch file failed")[:8192],
                )
                session.add(outbox)
                session.flush()
            else:
                outbox.payload = payload
                outbox.status = OutboxStatusEnum.FAILED.value
                outbox.last_error = str(record.get("error") or outbox.last_error or "")[
                    :8192
                ]
                outbox.updated_at = now
            dlq = (
                session.query(ProductionMonitoringDLQORM)
                .filter(ProductionMonitoringDLQORM.event_key == event_key)
                .one_or_none()
            )
            if dlq is None:
                session.add(
                    ProductionMonitoringDLQORM(
                        id=uuid.uuid4(),
                        event_key=event_key,
                        original_event_id=outbox.id,
                        event_type="batch.file.failed",
                        category=category,
                        source="batch_distill_progress",
                        aggregate_id=aggregate_id,
                        payload=payload,
                        retry_count=1,
                        last_error=str(record.get("error") or "batch file failed")[
                            :8192
                        ],
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                dlq.payload = payload
                dlq.category = category
                dlq.last_error = str(record.get("error") or dlq.last_error or "")[:8192]
                dlq.retry_count = max(int(dlq.retry_count or 0), 1)
                dlq.last_seen_at = now

    def _persist_snapshot(
        self, metrics: Mapping[str, Any], source: Mapping[str, Any]
    ) -> None:
        try:
            with self._db.session_scope() as session:  # type: ignore[union-attr]
                session.add(
                    ProductionQualitySnapshotORM(
                        id=uuid.uuid4(),
                        source="batch_distill",
                        window_label=f"last-{self._max_log_records}",
                        metrics_json=dict(metrics),
                        event_counts_json=dict(source),
                    )
                )
        except Exception:
            logger.warning("production quality snapshot persist failed", exc_info=True)


def start_production_quality_aggregation_task(
    app_state: Any,
    *,
    interval_s: Optional[float] = None,
    batch_log_path: Optional[Path | str] = None,
) -> Optional[asyncio.Task[Any]]:
    if os.environ.get("TCM_DISABLE_PRODUCTION_QUALITY_AGGREGATOR") == "1":
        return None
    db = getattr(app_state, "db_manager", None)
    if db is None:
        return None
    interval = max(
        5.0,
        float(interval_s or os.environ.get("TCM_PRODUCTION_QUALITY_INTERVAL_S", 15)),
    )

    async def _loop() -> None:
        while True:
            try:
                monitor = ProductionQualityMonitor(db, batch_log_path=batch_log_path)
                await asyncio.to_thread(monitor.collect_snapshot, persist=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("production quality aggregation failed", exc_info=True)
            await asyncio.sleep(interval)

    return asyncio.create_task(_loop(), name="production-quality-aggregator")


async def stop_production_quality_aggregation_task(
    task: Optional[asyncio.Task[Any]],
) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return


def _read_recent_batch_log(path: Path, max_records: int) -> Dict[str, Any]:
    records: Deque[Tuple[int, Dict[str, Any]]] = deque(maxlen=max_records)
    total_lines = 0
    invalid_lines = 0
    if not path.exists():
        return {"records": [], "total_lines": 0, "invalid_lines": 0}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            total_lines += 1
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            if isinstance(value, dict):
                records.append((total_lines, value))
    return {
        "records": list(records),
        "total_lines": total_lines,
        "invalid_lines": invalid_lines,
    }


def _aggregate_batch_log(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(records)
    success = sum(1 for record in records if _is_success_record(record))
    failed = total - success
    llm_timeout_count = sum(1 for record in records if _looks_like_timeout(record))
    llm_call_count, json_repair_counts = _collect_json_repair_counts(records)
    json_repair_count = _count_repaired_json(json_repair_counts)
    edge_tiers = _collect_edge_tiers(records)
    weak_edges = edge_tiers.get("weak_rule", 0) + edge_tiers.get("candidate_rule", 0)
    tier_total = sum(edge_tiers.values())
    log_neo4j_failures = sum(
        1 for record in records if _looks_like_neo4j_projection_failure(record)
    )
    return {
        "batch": {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": _ratio(success, total),
        },
        "llm": {
            "timeout_count": llm_timeout_count,
            "call_count": llm_call_count,
            "json_repair_count": json_repair_count,
            "json_repair_rate": _ratio(json_repair_count, llm_call_count),
            "json_repair_status_counts": dict(json_repair_counts),
        },
        "graph_quality": {
            "weak_edge_count": weak_edges,
            "edge_tier_total": tier_total,
            "weak_edge_ratio": _ratio(weak_edges, tier_total),
            "edge_tiers": dict(edge_tiers),
            "weak_edge_ratio_source": "batch_rule_quality_tiers"
            if tier_total
            else "unavailable",
        },
        "neo4j": {"projection_failure_count_from_log": log_neo4j_failures},
    }


def _merge_metric_groups(
    log_metrics: Mapping[str, Any], db_metrics: Mapping[str, Any]
) -> Dict[str, Any]:
    graph_quality = dict(log_metrics.get("graph_quality") or {})
    candidate = dict(db_metrics.get("candidate_edges") or {})
    if not graph_quality.get("edge_tier_total") and candidate.get("total"):
        total_relations = max(int(candidate.get("total") or 0), 1)
        graph_quality.update(
            {
                "weak_edge_count": int(candidate.get("total") or 0),
                "edge_tier_total": total_relations,
                "weak_edge_ratio": _ratio(candidate.get("total"), total_relations),
                "weak_edge_ratio_source": "learning_insights_candidate_edges",
            }
        )
    graph_quality["candidate_edge_acceptance_rate"] = candidate.get(
        "acceptance_rate", 0.0
    )
    graph_quality["candidate_edge_counts"] = candidate

    neo4j = dict(log_metrics.get("neo4j") or {})
    db_neo4j = dict(db_metrics.get("neo4j") or {})
    neo4j["projection_failure_count"] = int(
        neo4j.get("projection_failure_count_from_log") or 0
    ) + int(db_neo4j.get("projection_failure_count_from_dlq") or 0)
    neo4j.update(db_neo4j)

    return {
        "batch": dict(log_metrics.get("batch") or {}),
        "llm": dict(log_metrics.get("llm") or {}),
        "graph_quality": graph_quality,
        "evidence": dict(db_metrics.get("evidence") or {}),
        "neo4j": neo4j,
        "outbox": dict(db_metrics.get("outbox") or {}),
        "dlq": dict(db_metrics.get("dlq") or {}),
    }


def _candidate_edge_metrics(session: Any) -> Dict[str, Any]:
    rows = (
        session.query(LearningInsight.status)
        .filter(
            LearningInsight.insight_type.in_(list(COMPATIBLE_WEAK_EDGE_INSIGHT_TYPES))
        )
        .all()
    )
    statuses = Counter(normalize_status(row[0]) for row in rows)
    accepted = int(statuses.get(STATUS_ACCEPTED, 0))
    terminal = (
        accepted
        + int(statuses.get(STATUS_REJECTED, 0))
        + int(statuses.get(STATUS_SUPERSEDED, 0))
    )
    return {
        "total": len(rows),
        "accepted": accepted,
        "rejected": int(statuses.get(STATUS_REJECTED, 0)),
        "superseded": int(statuses.get(STATUS_SUPERSEDED, 0)),
        "pending": int(statuses.get("needs_review", 0))
        + int(statuses.get("active", 0)),
        "terminal_review_count": terminal,
        "acceptance_rate": _ratio(accepted, terminal),
        "status_counts": dict(statuses),
    }


def _no_evidence_metrics(session: Any, *, limit: int) -> Dict[str, Any]:
    items: List[Any] = []
    phase_rows = (
        session.query(PhaseExecution.output_json)
        .order_by(PhaseExecution.created_at.desc())
        .limit(limit)
        .all()
    )
    for (raw_output,) in phase_rows:
        _collect_claim_like_items(_json_loads(raw_output, {}), items)
    artifact_rows = (
        session.query(ResearchArtifact.content_json)
        .order_by(ResearchArtifact.created_at.desc())
        .limit(limit)
        .all()
    )
    for (raw_content,) in artifact_rows:
        _collect_claim_like_items(_json_loads(raw_content, {}), items)
    claim_items = [item for item in items if isinstance(item, Mapping)]
    no_evidence = sum(1 for item in claim_items if not _has_evidence(item))
    return {
        "conclusion_count": len(claim_items),
        "no_evidence_conclusion_count": no_evidence,
        "no_evidence_conclusion_rate": _ratio(no_evidence, len(claim_items)),
        "source": "phase_outputs_and_artifacts" if claim_items else "unavailable",
    }


def _outbox_metrics(session: Any) -> Dict[str, Any]:
    production_pending = (
        session.query(ProductionMonitoringOutboxORM)
        .filter(ProductionMonitoringOutboxORM.status == OutboxStatusEnum.PENDING.value)
        .count()
    )
    production_failed = (
        session.query(ProductionMonitoringOutboxORM)
        .filter(ProductionMonitoringOutboxORM.status == OutboxStatusEnum.FAILED.value)
        .count()
    )
    graph_pending = (
        session.query(OutboxEventORM)
        .filter(OutboxEventORM.status == OutboxStatusEnum.PENDING.value)
        .count()
    )
    return {
        "production_pending": int(production_pending),
        "production_failed": int(production_failed),
        "graph_pending": int(graph_pending),
    }


def _dlq_metrics(session: Any) -> Dict[str, Any]:
    category_rows = session.query(ProductionMonitoringDLQORM.category).all()
    categories = Counter(str(row[0] or "unknown") for row in category_rows)
    graph_dlq_count = int(session.query(OutboxDLQORM).count())
    return {
        "production_dlq_count": sum(categories.values()),
        "graph_dlq_count": graph_dlq_count,
        "total": sum(categories.values()) + graph_dlq_count,
        "category_counts": dict(categories),
    }


def _neo4j_projection_metrics(session: Any) -> Dict[str, Any]:
    graph_dlq_count = (
        session.query(OutboxDLQORM)
        .filter(
            or_(
                OutboxDLQORM.aggregate_type == "graph_projection",
                OutboxDLQORM.event_type.like("%neo4j%"),
            )
        )
        .count()
    )
    production_neo4j_count = (
        session.query(ProductionMonitoringDLQORM)
        .filter(ProductionMonitoringDLQORM.category == "neo4j_projection_failed")
        .count()
    )
    return {
        "projection_failure_count_from_dlq": int(graph_dlq_count)
        + int(production_neo4j_count),
        "graph_outbox_dlq_count": int(graph_dlq_count),
        "production_neo4j_dlq_count": int(production_neo4j_count),
    }


def _empty_db_metrics() -> Dict[str, Any]:
    return {
        "candidate_edges": {"total": 0, "acceptance_rate": 0.0, "status_counts": {}},
        "evidence": {
            "conclusion_count": 0,
            "no_evidence_conclusion_count": 0,
            "no_evidence_conclusion_rate": 0.0,
            "source": "database_unavailable",
        },
        "outbox": {"production_pending": 0, "production_failed": 0, "graph_pending": 0},
        "dlq": {
            "production_dlq_count": 0,
            "graph_dlq_count": 0,
            "total": 0,
            "category_counts": {},
        },
        "neo4j": {"projection_failure_count_from_dlq": 0},
    }


def _is_success_record(record: Mapping[str, Any]) -> bool:
    return bool(record.get("ok")) and int(record.get("status") or 0) < 400


def _looks_like_timeout(record: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(record.get(key) or "") for key in ("error", "message", "detail")
    ).lower()
    if "timeout" in text or "timed out" in text:
        return True
    for gateway in _iter_gateway_payloads(record):
        for call in _gateway_calls(gateway):
            warnings = " ".join(
                str(item) for item in call.get("warnings") or []
            ).lower()
            if "timeout" in warnings or "timed out" in warnings:
                return True
    return False


def _looks_like_neo4j_projection_failure(record: Mapping[str, Any]) -> bool:
    text = json.dumps(record, ensure_ascii=False, default=str).lower()
    if "neo4j" not in text:
        return False
    return (
        "projection_failed" in text
        or 'graph_projection_status": "failed' in text
        or "neo4j failed" in text
    )


def _collect_json_repair_counts(
    records: Sequence[Mapping[str, Any]],
) -> Tuple[int, Counter[str]]:
    counts: Counter[str] = Counter()
    call_count = 0
    for record in records:
        for gateway in _iter_gateway_payloads(record):
            summary = gateway.get("summary") if isinstance(gateway, Mapping) else None
            if isinstance(summary, Mapping):
                raw_counts = summary.get("json_repair_status_counts")
                if isinstance(raw_counts, Mapping):
                    for key, value in raw_counts.items():
                        counts[str(key or "unknown")] += _safe_int(value)
                call_count += _safe_int(summary.get("call_count"))
            for call in _gateway_calls(gateway):
                status = str(call.get("json_repair_status") or "unknown")
                counts[status] += 1
                call_count += 1
    if call_count == 0:
        call_count = sum(counts.values())
    return call_count, counts


def _iter_gateway_payloads(record: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    payloads: List[Mapping[str, Any]] = []
    direct = record.get("llm_gateway")
    if isinstance(direct, Mapping):
        payloads.append(direct)
    llm = record.get("llm")
    if isinstance(llm, Mapping) and isinstance(llm.get("llm_gateway"), Mapping):
        payloads.append(llm["llm_gateway"])
    return payloads


def _gateway_calls(gateway: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    calls = gateway.get("calls") if isinstance(gateway, Mapping) else None
    return [item for item in calls or [] if isinstance(item, Mapping)]


def _count_repaired_json(counts: Counter[str]) -> int:
    total = 0
    for status, count in counts.items():
        normalized = str(status or "").lower()
        if (
            "repair" in normalized
            and "not_requested" not in normalized
            and "failed" not in normalized
        ):
            total += int(count)
    return total


def _collect_edge_tiers(records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    tiers: Counter[str] = Counter()
    for record in records:
        for section_key in ("rule", "merged"):
            section = record.get(section_key)
            if not isinstance(section, Mapping):
                continue
            raw_tiers = section.get("quality_tiers") or section.get("edge_tiers")
            if not isinstance(raw_tiers, Mapping):
                continue
            for key, value in raw_tiers.items():
                tiers[str(key or "unknown")] += _safe_int(value)
    return tiers


def _failure_category(record: Mapping[str, Any]) -> str:
    text = json.dumps(record, ensure_ascii=False, default=str).lower()
    if "timeout" in text or "timed out" in text:
        return "llm_timeout"
    if "json" in text and ("decode" in text or "repair" in text or "parse" in text):
        return "json_parse_or_repair_failed"
    if "neo4j" in text or "projection" in text:
        return "neo4j_projection_failed"
    return "batch_file_failed"


def _batch_failure_event_key(record: Mapping[str, Any]) -> str:
    basis = "|".join(
        str(record.get(key) or "")
        for key in ("file_path_key", "file", "source_file", "status", "error")
    )
    digest = hashlib.sha1(basis.encode("utf-8", errors="ignore")).hexdigest()[:32]
    return f"batch-failure:{digest}"


def _compact_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    keep = {
        "file",
        "file_path_key",
        "status",
        "error",
        "elapsed_s",
        "read_timeout_s",
        "llm_gateway",
        "llm",
        "rule",
        "merged",
        "kg",
        "research",
    }
    return {key: record.get(key) for key in keep if key in record}


def _collect_claim_like_items(value: Any, out: List[Any]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key in _CLAIM_COLLECTION_KEYS:
                if isinstance(child, list):
                    out.extend(item for item in child if isinstance(item, Mapping))
                elif isinstance(child, Mapping):
                    out.append(child)
                continue
            if isinstance(child, (Mapping, list)):
                _collect_claim_like_items(child, out)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (Mapping, list)):
                _collect_claim_like_items(item, out)


def _has_evidence(item: Mapping[str, Any]) -> bool:
    for key, value in item.items():
        normalized_key = str(key or "").strip().lower()
        if normalized_key in _EVIDENCE_KEYS and value not in (None, "", [], {}):
            return True
        if isinstance(value, Mapping) and _has_evidence(value):
            return True
        if isinstance(value, list):
            for child in value:
                if isinstance(child, Mapping) and _has_evidence(child):
                    return True
                if child not in (None, "", [], {}) and normalized_key in _EVIDENCE_KEYS:
                    return True
    return False


def _production_dlq_to_dict(row: ProductionMonitoringDLQORM) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "event_key": row.event_key,
        "event_type": row.event_type,
        "category": row.category,
        "source": row.source,
        "aggregate_id": row.aggregate_id,
        "retry_count": int(row.retry_count or 0),
        "replay_count": int(row.replay_count or 0),
        "replay_status": row.replay_status,
        "last_error": row.last_error,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "payload": dict(row.payload or {}),
    }


def _graph_dlq_to_dict(row: OutboxDLQORM) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "event_key": str(row.original_event_id),
        "event_type": row.event_type,
        "category": "graph_outbox_dlq",
        "source": "graph_projection_outbox",
        "aggregate_id": row.aggregate_id,
        "retry_count": int(row.retry_count or 0),
        "replay_count": 0,
        "replay_status": "manual_graph_outbox_dlq",
        "last_error": row.last_error,
        "last_seen_at": row.moved_at.isoformat() if row.moved_at else None,
        "payload": dict(row.payload or {}),
    }


def _load_production_dlq_row(
    session: Any, event_id: str
) -> Optional[ProductionMonitoringDLQORM]:
    parsed_uuid: Any = event_id
    try:
        parsed_uuid = uuid.UUID(event_id)
    except Exception:
        pass
    row = session.get(ProductionMonitoringDLQORM, parsed_uuid)
    if row is not None:
        return row
    return (
        session.query(ProductionMonitoringDLQORM)
        .filter(ProductionMonitoringDLQORM.event_key == event_id)
        .one_or_none()
    )


def _json_loads(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: Any, denominator: Any) -> float:
    den = _safe_int(denominator)
    if den <= 0:
        return 0.0
    return round(_safe_int(numerator) / den, 4)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


__all__ = [
    "PRODUCTION_QUALITY_CONTRACT_VERSION",
    "ProductionQualityMonitor",
    "start_production_quality_aggregation_task",
    "stop_production_quality_aggregation_task",
]
