"""Shared runtime service for CLI and Web research entrypoints."""

from __future__ import annotations

import logging
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.cycle.cycle_reporter import extract_research_phase_results
from src.orchestration.research_orchestrator import (
    OrchestrationResult,
    PhaseOutcome,
    ResearchOrchestrator,
    _slug_topic,
    topic_to_phase_context,
)
from src.research.phase_result import get_phase_value

logger = logging.getLogger(__name__)

RuntimeEmitFn = Callable[[str, Dict[str, Any]], None]

_DEFAULT_PHASES = [
    "observe",
    "hypothesis",
    "experiment",
    "experiment_execution",
    "analyze",
    "publish",
    "reflect",
]


def _load_pipeline_symbols() -> tuple[Any, Any]:
    from src.research.research_pipeline import ResearchPipeline
    from src.research.study_session_manager import ResearchPhase

    return ResearchPipeline, ResearchPhase


@dataclass
class ResearchRuntimeResult:
    """Shared runtime output with both orchestration summary and raw phase payloads."""

    orchestration_result: OrchestrationResult
    phase_results: Dict[str, Any]
    cycle_snapshot: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return self.orchestration_result.to_dict()


class ResearchRuntimeService:
    """Execute a research session through one shared control path."""

    def __init__(self, orchestrator_config: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = deepcopy(orchestrator_config or {})
        self.pipeline_config: Dict[str, Any] = deepcopy(self.config.get("pipeline_config") or {})
        self.stop_on_failure: bool = bool(self.config.get("stop_on_failure", True))
        self.researchers: List[str] = list(self.config.get("researchers") or ["orchestrator"])

        configured_phases = self.config.get("phases") or list(_DEFAULT_PHASES)
        normalized_phases = [str(item).strip().lower() for item in configured_phases if str(item).strip()]
        self.phase_names = normalized_phases or list(_DEFAULT_PHASES)

    def run(
        self,
        topic: str,
        *,
        cycle_id: Optional[str] = None,
        phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
        cycle_name: Optional[str] = None,
        description: Optional[str] = None,
        scope: Optional[str] = None,
        study_type: Optional[str] = None,
        primary_outcome: Optional[str] = None,
        intervention: Optional[str] = None,
        comparison: Optional[str] = None,
        emit: Optional[RuntimeEmitFn] = None,
    ) -> ResearchRuntimeResult:
        normalized_topic = str(topic or "").strip()
        if not normalized_topic:
            raise ValueError("topic 不能为空")

        ResearchPipeline, ResearchPhase = _load_pipeline_symbols()
        phases = self._resolve_phases(ResearchPhase)
        normalized_phase_contexts = self._normalize_phase_contexts(phase_contexts)
        resolved_cycle_id = str(cycle_id or "").strip() or None

        resolved_cycle_name = cycle_name or _slug_topic(normalized_topic)
        resolved_description = description or normalized_topic
        resolved_scope = scope or ResearchOrchestrator._infer_scope(normalized_topic)
        protocol_inputs = {
            "study_type": study_type,
            "primary_outcome": primary_outcome,
            "intervention": intervention,
            "comparison": comparison,
        }

        started_at = datetime.now().isoformat()
        started_perf = time.perf_counter()
        phase_results: Dict[str, Any] = {}
        cycle_snapshot: Dict[str, Any] = {}
        phase_outcomes: List[PhaseOutcome] = []
        overall_status = "completed"
        publish_highlights: Dict[str, Dict[str, Any]] = {}

        pipeline = ResearchPipeline(self.pipeline_config)
        cycle = pipeline.create_research_cycle(
            cycle_id=resolved_cycle_id,
            cycle_name=resolved_cycle_name,
            description=resolved_description,
            objective=normalized_topic,
            scope=resolved_scope,
            researchers=self.researchers,
        )
        cycle_id = cycle.cycle_id

        self._emit(
            emit,
            "cycle_created",
            {
                "topic": normalized_topic,
                "cycle_id": cycle_id,
                "cycle_name": resolved_cycle_name,
                "scope": resolved_scope,
            },
        )

        try:
            if not pipeline.start_research_cycle(cycle_id):
                orchestration_result = OrchestrationResult(
                    topic=normalized_topic,
                    cycle_id=cycle_id,
                    status="failed",
                    started_at=started_at,
                    completed_at=datetime.now().isoformat(),
                    total_duration_sec=time.perf_counter() - started_perf,
                    phases=[],
                    pipeline_metadata={"error": "研究周期启动失败"},
                )
                self._emit(
                    emit,
                    "job_completed",
                    {"status": orchestration_result.status, "result": orchestration_result.to_dict()},
                )
                return ResearchRuntimeResult(
                    orchestration_result=orchestration_result,
                    phase_results=phase_results,
                    cycle_snapshot=cycle_snapshot,
                )

            total_phases = len(phases) or 1
            for index, phase in enumerate(phases, start=1):
                progress_before = ((index - 1) / total_phases) * 100.0
                phase_context = self._build_phase_context(
                    normalized_topic,
                    phase,
                    normalized_phase_contexts,
                    study_type=study_type,
                    primary_outcome=primary_outcome,
                    intervention=intervention,
                    comparison=comparison,
                )
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
                raw_result, outcome = self._run_single_phase(pipeline, cycle_id, phase, phase_context)
                if raw_result is not None:
                    phase_results[phase.value] = raw_result
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

                if outcome.status != "failed":
                    continue

                overall_status = "partial"
                if not self.stop_on_failure:
                    continue

                for skipped in self._build_skipped_outcomes(phases, index, phase):
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

            try:
                pipeline.complete_research_cycle(cycle_id)
            except Exception as exc:
                logger.warning("complete_research_cycle 失败: %s", exc)

            cycle_snapshot = self._serialize_cycle(pipeline, cycle)
            snapshot_phase_results = extract_research_phase_results(cycle_snapshot)
            if snapshot_phase_results:
                phase_results.update(snapshot_phase_results)

            publish_highlights = self._extract_publish_result_highlights(
                pipeline,
                cycle_id,
                cycle_snapshot,
            )
        finally:
            try:
                pipeline.cleanup()
            except Exception as exc:
                logger.warning("pipeline cleanup 失败: %s", exc)

        non_skipped = [item for item in phase_outcomes if item.status != "skipped"]
        if non_skipped and overall_status != "partial" and all(item.status == "failed" for item in non_skipped):
            overall_status = "failed"

        orchestration_result = OrchestrationResult(
            topic=normalized_topic,
            cycle_id=cycle_id,
            status=overall_status,
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            total_duration_sec=time.perf_counter() - started_perf,
            phases=phase_outcomes,
            pipeline_metadata={
                "cycle_name": resolved_cycle_name,
                "description": resolved_description,
                "scope": resolved_scope,
                "phases_requested": [phase.value for phase in phases],
                "protocol_inputs": protocol_inputs,
            },
            analysis_results=publish_highlights.get("analysis_results") or {},
            research_artifact=publish_highlights.get("research_artifact") or {},
        )
        self._emit(
            emit,
            "job_completed",
            {"status": orchestration_result.status, "result": orchestration_result.to_dict()},
        )
        return ResearchRuntimeResult(
            orchestration_result=orchestration_result,
            phase_results=phase_results,
            cycle_snapshot=cycle_snapshot,
        )

    def _resolve_phases(self, research_phase_cls: Any) -> List[Any]:
        phase_map = {phase.value: phase for phase in research_phase_cls}
        resolved: List[Any] = []
        for phase_name in self.phase_names:
            phase = phase_map.get(phase_name)
            if phase is None:
                logger.warning("跳过未知阶段: %s (可选: %s)", phase_name, list(phase_map.keys()))
                continue
            resolved.append(phase)
        if resolved:
            return resolved
        observe = phase_map.get("observe")
        return [observe] if observe is not None else []

    def _build_phase_context(
        self,
        topic: str,
        phase: Any,
        phase_contexts: Dict[str, Dict[str, Any]],
        *,
        study_type: Optional[str],
        primary_outcome: Optional[str],
        intervention: Optional[str],
        comparison: Optional[str],
    ) -> Dict[str, Any]:
        base = topic_to_phase_context(
            topic,
            phase,
            study_type=study_type,
            primary_outcome=primary_outcome,
            intervention=intervention,
            comparison=comparison,
        )
        base.setdefault("question", topic)
        base.setdefault("research_question", topic)

        config_key = f"default_{phase.value}_context"
        config_override = self.config.get(config_key) if isinstance(self.config.get(config_key), dict) else {}
        call_override = phase_contexts.get(phase.value) if isinstance(phase_contexts.get(phase.value), dict) else {}
        return {**base, **dict(config_override), **dict(call_override)}

    @staticmethod
    def _normalize_phase_contexts(raw_phase_contexts: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        if not isinstance(raw_phase_contexts, dict):
            return {}
        normalized: Dict[str, Dict[str, Any]] = {}
        for key, value in raw_phase_contexts.items():
            phase_name = str(key or "").strip().lower()
            if not phase_name or not isinstance(value, dict):
                continue
            normalized[phase_name] = dict(value)
        return normalized

    @staticmethod
    def _normalize_phase_result(raw_result: Any) -> Dict[str, Any]:
        if isinstance(raw_result, dict):
            return raw_result
        return {"result": raw_result}

    @staticmethod
    def _run_single_phase(
        pipeline: Any,
        cycle_id: str,
        phase: Any,
        phase_context: Dict[str, Any],
    ) -> tuple[Dict[str, Any], PhaseOutcome]:
        phase_started_at = time.perf_counter()
        try:
            raw_result = pipeline.execute_research_phase(cycle_id, phase, phase_context)
        except Exception as exc:
            duration = time.perf_counter() - phase_started_at
            failure_result = {"error": str(exc)}
            return failure_result, PhaseOutcome(
                phase=phase.value,
                status="failed",
                duration_sec=duration,
                error=str(exc),
            )

        normalized_result = ResearchRuntimeService._normalize_phase_result(raw_result)
        duration = time.perf_counter() - phase_started_at
        if normalized_result.get("error"):
            return normalized_result, PhaseOutcome(
                phase=phase.value,
                status="failed",
                duration_sec=duration,
                error=str(normalized_result.get("error") or ""),
                summary=normalized_result,
            )

        summary = ResearchOrchestrator._summarize_phase_result(phase, normalized_result)
        outcome_status = ResearchOrchestrator._resolve_phase_outcome_status(normalized_result)
        return normalized_result, PhaseOutcome(
            phase=phase.value,
            status=outcome_status,
            duration_sec=duration,
            summary=summary,
            error=str(normalized_result.get("error") or "") if outcome_status == "failed" else "",
        )

    @staticmethod
    def _build_skipped_outcomes(phases: List[Any], failed_index: int, failed_phase: Any) -> List[PhaseOutcome]:
        skipped: List[PhaseOutcome] = []
        for phase in phases[failed_index:]:
            skipped.append(
                PhaseOutcome(
                    phase=phase.value,
                    status="skipped",
                    duration_sec=0.0,
                    summary={"reason": f"前置阶段 {failed_phase.value} 失败"},
                )
            )
        return skipped

    @staticmethod
    def _serialize_cycle(pipeline: Any, cycle: Any) -> Dict[str, Any]:
        serialize_cycle = getattr(pipeline, "_serialize_cycle", None)
        if not callable(serialize_cycle):
            return {}
        try:
            snapshot = serialize_cycle(cycle)
        except Exception as exc:
            logger.warning("cycle snapshot 序列化失败: %s", exc)
            return {}
        return snapshot if isinstance(snapshot, dict) else {}

    @staticmethod
    def _extract_publish_result_highlights(
        pipeline: Any,
        cycle_id: str,
        cycle_snapshot: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        if hasattr(pipeline, "research_cycles"):
            try:
                highlights = ResearchOrchestrator._extract_publish_result_highlights(pipeline, cycle_id)
            except Exception as exc:
                logger.warning("publish highlights 提取失败，回退到 snapshot: %s", exc)
            else:
                if highlights:
                    return highlights

        publish_result = extract_research_phase_results(cycle_snapshot).get("publish") or {}
        if not isinstance(publish_result, dict):
            return {}

        highlights: Dict[str, Dict[str, Any]] = {}
        analysis_results = get_phase_value(publish_result, "analysis_results")
        research_artifact = get_phase_value(publish_result, "research_artifact")
        if isinstance(analysis_results, dict) and analysis_results:
            highlights["analysis_results"] = analysis_results
        if isinstance(research_artifact, dict) and research_artifact:
            highlights["research_artifact"] = research_artifact
        return highlights

    @staticmethod
    def _emit(
        emit: Optional[RuntimeEmitFn],
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        if emit is not None:
            emit(event_type, payload)