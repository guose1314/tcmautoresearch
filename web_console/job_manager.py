"""Web 控制台研究任务管理与 SSE 事件流。"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from src.orchestration.research_orchestrator import (
    OrchestrationResult,
    PhaseOutcome,
    ResearchOrchestrator,
    _slug_topic,
)
from src.research.research_pipeline import ResearchPipeline

TerminalStatus = {"completed", "partial", "failed"}


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


class StreamingResearchRunner:
    """按阶段驱动 ResearchPipeline，并对外发射进度事件。"""

    def __init__(self, orchestrator_config: Optional[Dict[str, Any]] = None):
        self.orchestrator = ResearchOrchestrator(orchestrator_config or {})

    def run(
        self,
        payload: Dict[str, Any],
        emit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> OrchestrationResult:
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise ValueError("topic 不能为空")

        phase_contexts = payload.get("phase_contexts") or {}
        cycle_name = payload.get("cycle_name") or _slug_topic(topic)
        description = payload.get("description") or topic
        scope = payload.get("scope") or self.orchestrator._infer_scope(topic)

        started_at = _utc_now()
        started_perf = time.perf_counter()

        pipeline = ResearchPipeline(self.orchestrator.pipeline_config)
        cycle = pipeline.create_research_cycle(
            cycle_name=cycle_name,
            description=description,
            objective=topic,
            scope=scope,
            researchers=self.orchestrator.researchers,
        )
        cycle_id = cycle.cycle_id

        self._emit(
            emit,
            "cycle_created",
            {
                "topic": topic,
                "cycle_id": cycle_id,
                "cycle_name": cycle_name,
                "scope": scope,
            },
        )

        if not pipeline.start_research_cycle(cycle_id):
            result = OrchestrationResult(
                topic=topic,
                cycle_id=cycle_id,
                status="failed",
                started_at=started_at,
                completed_at=_utc_now(),
                total_duration_sec=time.perf_counter() - started_perf,
                phases=[],
                pipeline_metadata={"error": "研究周期启动失败"},
            )
            self._emit(emit, "job_completed", {"status": result.status, "result": result.to_dict()})
            return result

        total_phases = len(self.orchestrator._phases)
        phase_outcomes: List[PhaseOutcome] = []
        overall_status = "completed"

        try:
            for index, phase in enumerate(self.orchestrator._phases, start=1):
                progress_before = ((index - 1) / total_phases) * 100.0
                ctx = self.orchestrator._build_phase_context(topic, phase, phase_contexts)
                self._emit(
                    emit,
                    "phase_started",
                    {
                        "phase": phase.value,
                        "index": index,
                        "total": total_phases,
                        "progress": round(progress_before, 3),
                    },
                )
                outcome = self.orchestrator._run_single_phase(pipeline, cycle_id, phase, ctx)
                phase_outcomes.append(outcome)
                progress_after = (index / total_phases) * 100.0
                self._emit(
                    emit,
                    "phase_completed",
                    {
                        "phase": outcome.phase,
                        "status": outcome.status,
                        "duration_sec": round(outcome.duration_sec, 3),
                        "error": outcome.error,
                        "summary": outcome.summary,
                        "index": index,
                        "total": total_phases,
                        "progress": round(progress_after, 3),
                    },
                )

                if outcome.status == "failed":
                    if self.orchestrator.stop_on_failure:
                        overall_status = "partial"
                        remaining = self.orchestrator._phases[index:]
                        for remaining_phase in remaining:
                            skipped = PhaseOutcome(
                                phase=remaining_phase.value,
                                status="skipped",
                                duration_sec=0.0,
                                summary={"reason": f"前置阶段 {phase.value} 失败"},
                            )
                            phase_outcomes.append(skipped)
                            self._emit(
                                emit,
                                "phase_skipped",
                                {
                                    "phase": skipped.phase,
                                    "status": skipped.status,
                                    "summary": skipped.summary,
                                    "progress": round(progress_after, 3),
                                },
                            )
                        break
                    overall_status = "partial"
        finally:
            pipeline.cleanup()

        non_skipped = [item for item in phase_outcomes if item.status != "skipped"]
        if non_skipped and overall_status != "partial" and all(item.status == "failed" for item in non_skipped):
            overall_status = "failed"

        result = OrchestrationResult(
            topic=topic,
            cycle_id=cycle_id,
            status=overall_status,
            started_at=started_at,
            completed_at=_utc_now(),
            total_duration_sec=time.perf_counter() - started_perf,
            phases=phase_outcomes,
            pipeline_metadata={
                "cycle_name": cycle_name,
                "description": description,
                "scope": scope,
                "phases_requested": [phase.value for phase in self.orchestrator._phases],
            },
        )
        self._emit(emit, "job_completed", {"status": result.status, "result": result.to_dict()})
        return result

    @staticmethod
    def _emit(
        emit: Optional[Callable[[str, Dict[str, Any]], None]],
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        if emit is not None:
            emit(event_type, payload)


class ResearchJobManager:
    """内存态研究任务管理器。"""

    def __init__(
        self,
        runner_factory: Optional[Callable[[Dict[str, Any]], StreamingResearchRunner]] = None,
    ):
        self._runner_factory = runner_factory or (lambda config: StreamingResearchRunner(config))
        self._jobs: Dict[str, ResearchJob] = {}
        self._lock = threading.Lock()

    def run_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        runner = self._runner_factory(payload.get("orchestrator_config") or {})
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
        worker = threading.Thread(target=self._run_job, args=(job, dict(payload)), daemon=True)
        worker.start()
        return job

    def get_job(self, job_id: str) -> Optional[ResearchJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def _run_job(self, job: ResearchJob, payload: Dict[str, Any]) -> None:
        runner = self._runner_factory(payload.get("orchestrator_config") or {})
        job.status = "running"
        job.started_at = _utc_now()
        job.append_event("job_started", {"status": job.status, "progress": job.progress})

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

        try:
            result = runner.run(payload, emit=emit)
            if job.result is None:
                job.result = result.to_dict()
            if job.status not in TerminalStatus:
                job.status = result.status
                job.progress = 100.0
                job.completed_at = _utc_now()
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