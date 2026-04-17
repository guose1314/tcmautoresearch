from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from src.research.audit_history import publish_audit_event
from src.research.phase_result import normalize_phase_result
from src.research.study_session_manager import ResearchCycle, ResearchPhase

if TYPE_CHECKING:
    from src.research.pipeline_phase_handlers import ResearchPhaseHandlers
    from src.research.research_pipeline import ResearchPipeline


class ResearchPipelineOrchestrator:
    """编排器：负责研究循环生命周期与阶段调度。"""

    def __init__(self, pipeline: "ResearchPipeline", phase_handlers: "ResearchPhaseHandlers"):
        self.pipeline = pipeline
        self.phase_handlers = phase_handlers

    def create_research_cycle(
        self,
        cycle_name: str,
        description: str,
        objective: str,
        scope: str,
        researchers: Optional[list[str]] = None,
        **cycle_options: Any,
    ):
        payload = {
            "cycle_name": cycle_name,
            "description": description,
            "objective": objective,
            "scope": scope,
            "researchers": researchers,
            "cycle_options": cycle_options,
        }
        event_result = self.pipeline.event_bus.request("cycle.create.requested", payload)
        if event_result is not None:
            return event_result
        return self._create_research_cycle_local(
            cycle_name=cycle_name,
            description=description,
            objective=objective,
            scope=scope,
            researchers=researchers,
            **cycle_options,
        )

    def _create_research_cycle_local(
        self,
        cycle_name: str,
        description: str,
        objective: str,
        scope: str,
        researchers: Optional[list[str]] = None,
        **cycle_options: Any,
    ):
        phase_entry = self.pipeline._start_phase(
            self.pipeline._metadata,
            "create_research_cycle",
            {"cycle_name": cycle_name, "scope": scope},
        )
        start_time = time.perf_counter()
        try:
            advisors = cycle_options.get("advisors") or []
            resources = cycle_options.get("resources") or {}
            requested_cycle_id = str(cycle_options.get("cycle_id") or "").strip()
            cycle_id = requested_cycle_id or f"cycle_{int(time.time())}_{hashlib.md5(cycle_name.encode()).hexdigest()[:8]}"

            research_cycle = ResearchCycle(
                cycle_id=cycle_id,
                cycle_name=cycle_name,
                description=description,
                research_objective=objective,
                research_scope=scope,
                researchers=researchers or [],
                advisors=advisors,
                resources=resources,
                tags=["created", "automated", "tcmautoresearch"],
            )
            self.pipeline._initialize_cycle_tracking(research_cycle)
            research_cycle.metadata["analysis_summary"] = self.pipeline._build_cycle_analysis_summary(research_cycle)
            self.pipeline.research_cycles[cycle_id] = research_cycle
            publish_audit_event(
                self.pipeline.event_bus,
                "cycle_created",
                {
                    "cycle_id": cycle_id,
                    "cycle_name": cycle_name,
                },
            )
            self.pipeline._complete_phase(self.pipeline._metadata, "create_research_cycle", phase_entry, start_time)
            self.pipeline.logger.info(f"研究循环创建完成: {cycle_name}")
            return research_cycle
        except Exception as exc:
            self.pipeline._fail_phase(
                self.pipeline._metadata,
                self.pipeline._failed_operations,
                "create_research_cycle",
                phase_entry,
                start_time,
                str(exc),
            )
            self.pipeline.logger.error(f"研究循环创建失败: {exc}")
            raise

    def start_research_cycle(self, cycle_id: str) -> bool:
        event_result = self.pipeline.event_bus.request("cycle.start.requested", {"cycle_id": cycle_id})
        if event_result is not None:
            return bool(event_result)
        return self._start_research_cycle_local(cycle_id)

    def _start_research_cycle_local(self, cycle_id: str) -> bool:
        phase_entry = self.pipeline._start_phase(self.pipeline._metadata, "start_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.pipeline.research_cycles:
                self.pipeline.logger.warning(f"研究循环 {cycle_id} 不存在")
                self.pipeline._fail_phase(
                    self.pipeline._metadata,
                    self.pipeline._failed_operations,
                    "start_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False

            research_cycle = self.pipeline.research_cycles[cycle_id]
            research_cycle.status = self.pipeline.ResearchCycleStatus.ACTIVE
            research_cycle.started_at = datetime.now().isoformat()
            research_cycle.current_phase = self.pipeline.ResearchPhase.OBSERVE
            research_cycle.metadata["final_status"] = research_cycle.status.value
            self.pipeline.active_cycles[cycle_id] = research_cycle
            self.pipeline.freeze_learning_strategy_snapshot()
            publish_audit_event(
                self.pipeline.event_bus,
                "cycle_started",
                {
                    "cycle_id": cycle_id,
                    "phase": research_cycle.current_phase.value,
                },
            )
            self.pipeline._complete_phase(self.pipeline._metadata, "start_research_cycle", phase_entry, start_time)
            self.pipeline.logger.info(f"研究循环启动: {research_cycle.cycle_name}")
            return True
        except Exception as exc:
            self.pipeline._fail_phase(
                self.pipeline._metadata,
                self.pipeline._failed_operations,
                "start_research_cycle",
                phase_entry,
                start_time,
                str(exc),
            )
            self.pipeline.logger.error(f"研究循环启动失败: {exc}")
            return False

    def execute_research_phase(
        self,
        cycle_id: str,
        phase,
        phase_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "cycle_id": cycle_id,
            "phase": phase,
            "phase_context": phase_context,
        }
        phase_name = getattr(phase, "value", str(phase))
        event_result = self.pipeline.event_bus.request("cycle.phase.execute.requested", payload)
        if isinstance(event_result, dict):
            return normalize_phase_result(phase_name, event_result)
        if event_result is not None:
            return normalize_phase_result(phase_name, {"results": {"value": event_result}})
        return self._execute_research_phase_local(cycle_id, phase, phase_context)

    def _execute_research_phase_local(
        self,
        cycle_id: str,
        phase,
        phase_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        phase_context_payload = phase_context or {}
        start_time = time.perf_counter()
        phase_name = getattr(phase, "value", str(phase))

        validation_error = self.pipeline._validate_research_phase_request(cycle_id)
        if validation_error:
            return normalize_phase_result(
                phase_name,
                {
                    "status": "failed",
                    "error": validation_error.get("error", "研究阶段执行请求无效"),
                    "metadata": {"validation_error": True},
                    "results": {},
                },
            )

        research_cycle = self.pipeline.research_cycles[cycle_id]
        phase_entry = self.pipeline._start_phase(research_cycle.metadata, phase.value, phase_context_payload)

        try:
            phase_result = normalize_phase_result(
                phase_name,
                self.pipeline._execute_phase_internal(phase, research_cycle, phase_context_payload),
            )
            raw_phase_status = str(phase_result.get("status") or "completed").strip().lower() or "completed"
            control_status = self._resolve_phase_control_status(phase_result)
            if control_status != "failed":
                self.pipeline._advance_research_cycle_phase(research_cycle, phase)
            phase_execution = self.pipeline._build_phase_execution(
                phase=phase,
                started_at=phase_entry["started_at"],
                start_time=start_time,
                phase_context=phase_context_payload,
                phase_result=phase_result,
            )
            research_cycle.phase_executions[phase] = phase_execution
            self.pipeline._complete_phase(
                research_cycle.metadata,
                phase.value,
                phase_entry,
                start_time,
                phase_status=raw_phase_status,
                error=phase_result.get("error"),
            )
            self.pipeline._sync_phase_history_entry(phase_entry, phase_execution, phase_result)
            self.pipeline._apply_phase_result(research_cycle, phase, phase_result)
            research_cycle.metadata["analysis_summary"] = self.pipeline._build_cycle_analysis_summary(research_cycle)
            if raw_phase_status not in {"failed", "skipped", "blocked", "pending", "running"}:
                self.pipeline._record_phase_success(cycle_id, phase, start_time)

            if control_status != "failed" and phase == ResearchPhase.ANALYZE:
                findings_count = (phase_result.get("metadata") or {}).get("record_count", 0)
                if findings_count == 0:
                    phase_entry["status"] = "degraded"
                    research_cycle.metadata["final_status"] = "degraded"
                    phase_result["status"] = "degraded"
                    phase_result.setdefault("metadata", {})["status"] = "degraded"
                    self.pipeline.logger.warning(
                        "analyze 阶段 findings=0，标记 status=degraded"
                    )

            self.pipeline.logger.info(f"研究阶段执行完成: {phase.value}")
            return phase_result
        except Exception as exc:
            return self.pipeline._handle_phase_execution_failure(cycle_id, phase, start_time, exc)

    @staticmethod
    def _resolve_phase_control_status(phase_result: Dict[str, Any]) -> str:
        status = str(phase_result.get("status") or "completed").strip().lower() or "completed"
        if phase_result.get("error"):
            return "failed"
        if status == "skipped":
            return "skipped"
        if status in {"failed", "blocked", "pending", "running"}:
            return "failed"
        return "completed"

    def complete_research_cycle(self, cycle_id: str) -> bool:
        event_result = self.pipeline.event_bus.request("cycle.complete.requested", {"cycle_id": cycle_id})
        if event_result is not None:
            return bool(event_result)
        return self._complete_research_cycle_local(cycle_id)

    def _complete_research_cycle_local(self, cycle_id: str) -> bool:
        phase_entry = self.pipeline._start_phase(self.pipeline._metadata, "complete_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.pipeline.research_cycles:
                self.pipeline.logger.warning(f"研究循环 {cycle_id} 不存在")
                self.pipeline._fail_phase(
                    self.pipeline._metadata,
                    self.pipeline._failed_operations,
                    "complete_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False

            research_cycle = self.pipeline.research_cycles[cycle_id]
            if research_cycle.status != self.pipeline.ResearchCycleStatus.ACTIVE or not research_cycle.started_at:
                self.pipeline.logger.warning(f"研究循环 {cycle_id} 尚未启动，无法完成")
                self.pipeline._fail_phase(
                    self.pipeline._metadata,
                    self.pipeline._failed_operations,
                    "complete_research_cycle",
                    phase_entry,
                    start_time,
                    "循环未启动",
                )
                return False

            research_cycle.status = self.pipeline.ResearchCycleStatus.COMPLETED
            research_cycle.completed_at = datetime.now().isoformat()
            if research_cycle.started_at:
                research_cycle.duration = (
                    datetime.fromisoformat(research_cycle.completed_at)
                    - datetime.fromisoformat(research_cycle.started_at)
                ).total_seconds()
            else:
                research_cycle.duration = 0.0
            if cycle_id in self.pipeline.active_cycles:
                del self.pipeline.active_cycles[cycle_id]
            research_cycle.metadata["final_status"] = research_cycle.status.value
            research_cycle.metadata["analysis_summary"] = self.pipeline._build_cycle_analysis_summary(research_cycle)
            publish_audit_event(
                self.pipeline.event_bus,
                "cycle_completed",
                {
                    "cycle_id": cycle_id,
                    "duration": research_cycle.duration,
                },
            )
            self.pipeline._complete_phase(self.pipeline._metadata, "complete_research_cycle", phase_entry, start_time)
            self.pipeline._persist_result(research_cycle)
            self.pipeline.logger.info(f"研究循环完成: {research_cycle.cycle_name}")
            return True
        except Exception as exc:
            self.pipeline._fail_phase(
                self.pipeline._metadata,
                self.pipeline._failed_operations,
                "complete_research_cycle",
                phase_entry,
                start_time,
                str(exc),
            )
            self.pipeline.logger.error(f"研究循环完成失败: {exc}")
            return False

    def suspend_research_cycle(self, cycle_id: str) -> bool:
        event_result = self.pipeline.event_bus.request("cycle.suspend.requested", {"cycle_id": cycle_id})
        if event_result is not None:
            return bool(event_result)
        return self._suspend_research_cycle_local(cycle_id)

    def _suspend_research_cycle_local(self, cycle_id: str) -> bool:
        phase_entry = self.pipeline._start_phase(self.pipeline._metadata, "suspend_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.pipeline.research_cycles:
                self.pipeline.logger.warning(f"研究循环 {cycle_id} 不存在")
                self.pipeline._fail_phase(
                    self.pipeline._metadata,
                    self.pipeline._failed_operations,
                    "suspend_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False

            research_cycle = self.pipeline.research_cycles[cycle_id]
            research_cycle.status = self.pipeline.ResearchCycleStatus.SUSPENDED
            if cycle_id in self.pipeline.active_cycles:
                del self.pipeline.active_cycles[cycle_id]
            research_cycle.metadata["final_status"] = research_cycle.status.value
            research_cycle.metadata["analysis_summary"] = self.pipeline._build_cycle_analysis_summary(research_cycle)
            publish_audit_event(
                self.pipeline.event_bus,
                "cycle_suspended",
                {"cycle_id": cycle_id},
            )
            self.pipeline._complete_phase(self.pipeline._metadata, "suspend_research_cycle", phase_entry, start_time)
            self.pipeline.logger.info(f"研究循环暂停: {research_cycle.cycle_name}")
            return True
        except Exception as exc:
            self.pipeline._fail_phase(
                self.pipeline._metadata,
                self.pipeline._failed_operations,
                "suspend_research_cycle",
                phase_entry,
                start_time,
                str(exc),
            )
            self.pipeline.logger.error(f"研究循环暂停失败: {exc}")
            return False

    def resume_research_cycle(self, cycle_id: str) -> bool:
        event_result = self.pipeline.event_bus.request("cycle.resume.requested", {"cycle_id": cycle_id})
        if event_result is not None:
            return bool(event_result)
        return self._resume_research_cycle_local(cycle_id)

    def _resume_research_cycle_local(self, cycle_id: str) -> bool:
        phase_entry = self.pipeline._start_phase(self.pipeline._metadata, "resume_research_cycle", {"cycle_id": cycle_id})
        start_time = time.perf_counter()
        try:
            if cycle_id not in self.pipeline.research_cycles:
                self.pipeline.logger.warning(f"研究循环 {cycle_id} 不存在")
                self.pipeline._fail_phase(
                    self.pipeline._metadata,
                    self.pipeline._failed_operations,
                    "resume_research_cycle",
                    phase_entry,
                    start_time,
                    "循环不存在",
                )
                return False

            research_cycle = self.pipeline.research_cycles[cycle_id]
            research_cycle.status = self.pipeline.ResearchCycleStatus.ACTIVE
            self.pipeline.active_cycles[cycle_id] = research_cycle
            research_cycle.metadata["final_status"] = research_cycle.status.value
            research_cycle.metadata["analysis_summary"] = self.pipeline._build_cycle_analysis_summary(research_cycle)
            publish_audit_event(
                self.pipeline.event_bus,
                "cycle_resumed",
                {"cycle_id": cycle_id},
            )
            self.pipeline._complete_phase(self.pipeline._metadata, "resume_research_cycle", phase_entry, start_time)
            self.pipeline.logger.info(f"研究循环恢复: {research_cycle.cycle_name}")
            return True
        except Exception as exc:
            self.pipeline._fail_phase(
                self.pipeline._metadata,
                self.pipeline._failed_operations,
                "resume_research_cycle",
                phase_entry,
                start_time,
                str(exc),
            )
            self.pipeline.logger.error(f"研究循环恢复失败: {exc}")
            return False
