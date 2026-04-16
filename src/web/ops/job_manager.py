"""Web 控制台研究任务管理与 SSE 事件流。"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from src.infrastructure.config_loader import AppSettings
from src.infrastructure.runtime_config_assembler import (
    RuntimeAssembly,
    build_runtime_assembly,
)
from src.web.ops.job_store import PersistentJobStore
from src.web.ops.research_job_runner import StreamingResearchRunner

TerminalStatus = {"completed", "partial", "failed"}
DEFAULT_JOB_STORAGE_DIR = Path(__file__).resolve().parent.parent / "output" / "web_console_jobs"


def _utc_now() -> str:
    return datetime.now().isoformat()


@dataclass
class ResearchJob:
    job_id: str
    topic: str
    status: str = "queued"
    progress: float = 0.0
    current_phase: str = ""
    created_at: str = field(default_factory=_utc_now)
    started_at: str = ""
    completed_at: str = ""
    result: Optional[Dict[str, Any]] = None
    error: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    condition: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "topic": self.topic,
            "status": self.status,
            "progress": round(self.progress, 3),
            "current_phase": self.current_phase,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result": self.result,
            "event_count": len(self.events),
        }

    def list_snapshot(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "topic": self.topic,
            "status": self.status,
            "progress": round(self.progress, 3),
            "current_phase": self.current_phase,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }

    def append_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self.condition:
            event = {
                "sequence": len(self.events) + 1,
                "event": event_type,
                "job_id": self.job_id,
                "timestamp": _utc_now(),
                "data": data,
            }
            self.events.append(event)
            self.condition.notify_all()
            return event

    def is_terminal(self) -> bool:
        return self.status in TerminalStatus

    def persistence_payload(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "job": self.snapshot(),
            "events": list(self.events),
        }
class ResearchJobManager:
    """支持持久化恢复的研究任务管理器。"""

    def __init__(
        self,
        runner_factory: Optional[Callable[[Dict[str, Any]], StreamingResearchRunner]] = None,
        storage_dir: str | Path | None = None,
        default_orchestrator_config: Optional[Dict[str, Any]] = None,
        runtime_assembly: Optional[RuntimeAssembly] = None,
        settings: Optional[AppSettings] = None,
        config_path: str | Path | None = None,
        environment: Optional[str] = None,
    ):
        resolved_runtime_assembly = runtime_assembly
        if resolved_runtime_assembly is None and default_orchestrator_config is None:
            if settings is not None or config_path is not None or environment is not None:
                resolved_runtime_assembly = build_runtime_assembly(
                    settings=settings,
                    config_path=config_path,
                    environment=environment,
                    entrypoint="web",
                )

        resolved_storage_dir = storage_dir
        if resolved_storage_dir is None and resolved_runtime_assembly is not None:
            resolved_storage_dir = resolved_runtime_assembly.settings.job_storage_dir
        if default_orchestrator_config is None and resolved_runtime_assembly is not None:
            default_orchestrator_config = resolved_runtime_assembly.orchestrator_config

        self._runner_factory = runner_factory or (lambda config: StreamingResearchRunner(config))
        self._default_orchestrator_config = deepcopy(default_orchestrator_config or {})
        self._store = PersistentJobStore(resolved_storage_dir or DEFAULT_JOB_STORAGE_DIR)
        self._jobs: Dict[str, ResearchJob] = self._load_persisted_jobs()
        self._lock = threading.Lock()
        self._workers: List[threading.Thread] = []

    def run_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        runner = self._runner_factory(self._resolve_orchestrator_config(payload))
        result = runner.run(payload)
        return result.to_dict()

    def create_job(self, payload: Dict[str, Any]) -> ResearchJob:
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise ValueError("topic 不能为空")

        job = ResearchJob(job_id=uuid4().hex, topic=topic)
        with self._lock:
            self._jobs[job.job_id] = job

        job.append_event("job_queued", {"status": job.status, "progress": job.progress, "topic": job.topic})
        self._persist_job(job)
        worker = threading.Thread(target=self._run_job, args=(job, dict(payload)), daemon=True)
        with self._lock:
            self._workers.append(worker)
        worker.start()
        return job

    def get_job(self, job_id: str) -> Optional[ResearchJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 50))
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(
            key=lambda job: (
                job.created_at or "",
                job.started_at or "",
                job.completed_at or "",
                job.job_id,
            ),
            reverse=True,
        )
        return [job.list_snapshot() for job in jobs[:safe_limit]]

    def delete_job(self, job_id: str) -> Dict[str, Any]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            raise ValueError("job_id 不能为空")

        with self._lock:
            job = self._jobs.get(normalized_job_id)
            if job is None:
                raise KeyError(normalized_job_id)
            if not job.is_terminal():
                raise RuntimeError("仅支持删除已完成、部分完成或失败的任务")
            snapshot = job.list_snapshot()
            del self._jobs[normalized_job_id]

        deleted = self._store.delete_job(normalized_job_id)
        return {
            "job_id": normalized_job_id,
            "deleted": deleted,
            "job": snapshot,
        }

    def get_runtime_metrics(self) -> Dict[str, Any]:
        with self._lock:
            jobs = list(self._jobs.values())
            workers = list(self._workers)

        status_counts: Dict[str, int] = {}
        total_events = 0
        total_progress = 0.0
        for job in jobs:
            status_counts[job.status] = status_counts.get(job.status, 0) + 1
            total_events += len(job.events)
            total_progress += float(job.progress)

        return {
            "total_jobs": len(jobs),
            "status_counts": status_counts,
            "active_workers": sum(1 for worker in workers if worker.is_alive()),
            "terminal_jobs": sum(1 for job in jobs if job.is_terminal()),
            "running_jobs": status_counts.get("running", 0),
            "queued_jobs": status_counts.get("queued", 0),
            "failed_jobs": status_counts.get("failed", 0),
            "completed_jobs": status_counts.get("completed", 0),
            "partial_jobs": status_counts.get("partial", 0),
            "total_events": total_events,
            "average_progress": (total_progress / len(jobs)) if jobs else 0.0,
        }

    def get_storage_summary(self) -> Dict[str, Any]:
        return self._store.get_storage_summary()

    def list_persisted_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        payloads = self._store.list_job_payloads(limit=limit)
        records: List[Dict[str, Any]] = []
        for payload in payloads:
            snapshot = payload.get("job") if isinstance(payload.get("job"), dict) else {}
            events = payload.get("events") if isinstance(payload.get("events"), list) else []
            records.append(
                {
                    "job_id": str(snapshot.get("job_id") or ""),
                    "job": snapshot,
                    "event_count": len(events),
                    "has_result": isinstance(snapshot.get("result"), dict),
                }
            )
        return records

    def get_persisted_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        payload = self._store.get_job_payload(job_id)
        if not isinstance(payload, dict):
            return None
        return payload

    def sync_job_observe_philology(self, job_id: str, observe_philology: Dict[str, Any]) -> bool:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            return False

        observe_payload = deepcopy(observe_philology if isinstance(observe_philology, dict) else {})
        updated = False
        with self._lock:
            job = self._jobs.get(normalized_job_id)
            if job is not None:
                if not isinstance(job.result, dict):
                    job.result = {}
                job.result["observe_philology"] = observe_payload
                self._persist_job(job)
                updated = True

        persisted_payload = self._store.get_job_payload(normalized_job_id)
        if not isinstance(persisted_payload, dict):
            return updated

        snapshot = persisted_payload.get("job") if isinstance(persisted_payload.get("job"), dict) else None
        if snapshot is None:
            return updated

        result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
        result["observe_philology"] = deepcopy(observe_payload)
        snapshot["result"] = result
        persisted_payload["job"] = snapshot
        self._store.save_job(persisted_payload)
        return True

    def _load_persisted_jobs(self) -> Dict[str, ResearchJob]:
        restored: Dict[str, ResearchJob] = {}
        needs_save = False
        for job_id, payload in self._store.load_jobs().items():
            job = self._job_from_payload(job_id, payload)
            if job is None:
                continue
            if not job.is_terminal():
                job.status = "failed"
                job.progress = 100.0
                job.completed_at = job.completed_at or _utc_now()
                job.error = job.error or "服务重启或异常退出，任务执行中断"
                job.append_event(
                    "job_failed",
                    {
                        "status": job.status,
                        "progress": job.progress,
                        "error": job.error,
                        "recovered": True,
                    },
                )
                if isinstance(job.result, dict):
                    job.result["status"] = "failed"
                    if not job.result.get("completed_at"):
                        job.result["completed_at"] = job.completed_at
                needs_save = True
            restored[job_id] = job
        if needs_save:
            for job in restored.values():
                self._persist_job(job)
        return restored

    def _job_from_payload(self, job_id: str, payload: Dict[str, Any]) -> Optional[ResearchJob]:
        if not isinstance(payload, dict):
            return None
        snapshot = payload.get("job") or {}
        if not isinstance(snapshot, dict):
            return None
        normalized_job_id = str(snapshot.get("job_id") or job_id).strip()
        topic = str(snapshot.get("topic") or "").strip()
        if not normalized_job_id or not topic:
            return None
        events = payload.get("events") or []
        normalized_events = [dict(item) for item in events if isinstance(item, dict)]
        return ResearchJob(
            job_id=normalized_job_id,
            topic=topic,
            status=str(snapshot.get("status") or "queued"),
            progress=float(snapshot.get("progress") or 0.0),
            current_phase=str(snapshot.get("current_phase") or ""),
            created_at=str(snapshot.get("created_at") or _utc_now()),
            started_at=str(snapshot.get("started_at") or ""),
            completed_at=str(snapshot.get("completed_at") or ""),
            result=snapshot.get("result") if isinstance(snapshot.get("result"), dict) else snapshot.get("result"),
            error=str(snapshot.get("error") or ""),
            events=normalized_events,
        )

    def _persist_job(self, job: ResearchJob) -> None:
        self._store.save_job(job.persistence_payload())

    def close(self, timeout: float = 5.0) -> None:
        with self._lock:
            workers = list(self._workers)
        for worker in workers:
            if worker.is_alive():
                worker.join(timeout=timeout)

    def _resolve_orchestrator_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload_config = payload.get("orchestrator_config") if isinstance(payload.get("orchestrator_config"), dict) else {}
        return {
            **deepcopy(self._default_orchestrator_config),
            **deepcopy(payload_config),
        }

    def _run_job(self, job: ResearchJob, payload: Dict[str, Any]) -> None:
        runner = self._runner_factory(self._resolve_orchestrator_config(payload))
        job.status = "running"
        job.started_at = _utc_now()
        job.append_event("job_started", {"status": job.status, "progress": job.progress})
        self._persist_job(job)

        def emit(event_type: str, data: Dict[str, Any]) -> None:
            if event_type == "phase_started":
                job.current_phase = str(data.get("phase") or "")
                job.progress = float(data.get("progress", job.progress))
            elif event_type == "phase_completed":
                job.current_phase = str(data.get("phase") or job.current_phase)
                job.progress = float(data.get("progress", job.progress))
                if str(data.get("status")) == "failed":
                    job.error = str(data.get("error") or "")
            elif event_type == "phase_skipped":
                job.progress = float(data.get("progress", job.progress))
            elif event_type == "job_completed":
                job.result = data.get("result")
                job.status = str(data.get("status") or job.status)
                job.progress = 100.0
                job.completed_at = _utc_now()
                if isinstance(job.result, dict) and job.result.get("status") == "failed" and not job.error:
                    phases = job.result.get("phases") or []
                    for phase in phases:
                        if phase.get("error"):
                            job.error = str(phase.get("error"))
                            break
            job.append_event(event_type, data)
            self._persist_job(job)

        try:
            result = runner.run(payload, emit=emit)
            if job.result is None:
                job.result = result.to_dict()
            if job.status not in TerminalStatus:
                job.status = result.status
                job.progress = 100.0
                job.completed_at = _utc_now()
            self._persist_job(job)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.progress = 100.0
            job.completed_at = _utc_now()
            job.append_event(
                "job_failed",
                {
                    "status": job.status,
                    "progress": job.progress,
                    "error": job.error,
                },
            )
            self._persist_job(job)
        finally:
            current = threading.current_thread()
            with self._lock:
                self._workers = [worker for worker in self._workers if worker is not current and worker.is_alive()]


def format_sse(event: Dict[str, Any]) -> str:
    payload = json.dumps(event["data"], ensure_ascii=False)
    return "\n".join(
        [
            f"id: {event['sequence']}",
            f"event: {event['event']}",
            f"data: {payload}",
            "",
        ]
    )