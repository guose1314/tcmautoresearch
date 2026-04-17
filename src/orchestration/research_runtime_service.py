"""Shared runtime service for CLI and Web research entrypoints."""

from __future__ import annotations

import logging
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.orchestration.research_orchestrator import (
    OrchestrationResult,
    PhaseOutcome,
    ResearchOrchestrator,
    _slug_topic,
    topic_to_phase_context,
)
from src.research.observe_philology import resolve_observe_philology_assets
from src.research.phase_result import (
    extract_research_phase_results,
    get_phase_artifact_map,
    get_phase_value,
)

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

# ── 阶段 context 规范默认值（各入口共享） ───────────────────────────────────
# 所有通过 ResearchRuntimeService 发起的研究均继承此基线，调用方可通过
# phase_contexts 参数覆盖任意键。API / Web 等入口若有环境相关补充（如
# local_data_dir），应在调用层追加而非重新定义整套默认值。

CANONICAL_OBSERVE_DEFAULTS: Dict[str, Any] = {
    "data_source": "local",
    "use_local_corpus": True,
    "collect_local_corpus": True,
    "use_ctext_whitelist": False,
    "run_preprocess_and_extract": True,
    "run_literature_retrieval": False,
}

CANONICAL_PUBLISH_DEFAULTS: Dict[str, Any] = {
    "allow_pipeline_citation_fallback": False,
}

_SHARED_RUNTIME_PROFILES: Dict[str, Dict[str, Any]] = {
    "demo_research": {
        "phases": ["observe"],
        "stop_on_failure": True,
        "default_cycle_name_mode": "timestamp",
        "default_cycle_name_prefix": "research",
        "default_scope": "中医药",
        "default_observe_context": dict(CANONICAL_OBSERVE_DEFAULTS),
        "default_publish_context": dict(CANONICAL_PUBLISH_DEFAULTS),
    },
    "web_research": {
        "phases": list(_DEFAULT_PHASES),
        "stop_on_failure": True,
        "default_cycle_name_mode": "slug",
        "default_observe_context": dict(CANONICAL_OBSERVE_DEFAULTS),
        "default_publish_context": dict(CANONICAL_PUBLISH_DEFAULTS),
    }
}


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

    @staticmethod
    def _resolve_publish_result(
        phase_results: Dict[str, Any],
        cycle_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        publish_result = phase_results.get("publish") if isinstance(phase_results.get("publish"), dict) else {}
        if publish_result:
            return publish_result
        snapshot_phase_results = extract_research_phase_results(cycle_snapshot)
        candidate = snapshot_phase_results.get("publish") if isinstance(snapshot_phase_results.get("publish"), dict) else {}
        return candidate if isinstance(candidate, dict) else {}

    @staticmethod
    def _extract_publish_output_files(publish_result: Dict[str, Any]) -> Dict[str, str]:
        if not isinstance(publish_result, dict):
            return {}

        output_files = get_phase_value(publish_result, "output_files", {})
        if isinstance(output_files, dict) and output_files:
            return {
                str(name): str(path)
                for name, path in output_files.items()
                if path not in (None, "", [], {})
            }

        artifact_map = get_phase_artifact_map(publish_result)
        return {
            str(name): str(path)
            for name, path in artifact_map.items()
            if path not in (None, "", [], {})
        }

    @staticmethod
    def _extract_publish_deliverables(
        publish_result: Dict[str, Any],
        cycle_snapshot: Dict[str, Any],
    ) -> List[Any]:
        snapshot_deliverables = cycle_snapshot.get("deliverables")
        if isinstance(snapshot_deliverables, list) and snapshot_deliverables:
            return deepcopy(snapshot_deliverables)

        deliverables = get_phase_value(publish_result, "deliverables", [])
        if isinstance(deliverables, list) and deliverables:
            return deepcopy(deliverables)
        return []

    @staticmethod
    def _build_report_summary(
        publish_result: Dict[str, Any],
        publish_output_files: Dict[str, str],
        publish_deliverables: List[Any],
    ) -> Dict[str, Any]:
        if not isinstance(publish_result, dict):
            return {}

        metadata = publish_result.get("metadata") if isinstance(publish_result.get("metadata"), dict) else {}
        report_error_count = int(metadata.get("report_error_count", 0) or 0)
        report_count = int(metadata.get("report_count", 0) or 0)
        if report_count <= 0 and publish_output_files:
            report_count = len(publish_output_files)

        if report_error_count > 0:
            status = "degraded"
        elif publish_output_files:
            status = "completed"
        else:
            status = "pending"

        if not publish_output_files and report_count <= 0 and not publish_deliverables:
            return {}

        summary: Dict[str, Any] = {
            "status": status,
            "report_count": report_count,
            "report_error_count": report_error_count,
            "output_files": deepcopy(publish_output_files),
        }
        if publish_deliverables:
            summary["deliverables"] = deepcopy(publish_deliverables)
        return summary

    @property
    def session_result(self) -> Dict[str, Any]:
        normalized_question = str(self.orchestration_result.topic or "").strip()
        phase_results = deepcopy(self.phase_results or {})
        cycle_snapshot = deepcopy(self.cycle_snapshot or {})
        publish_result = self._resolve_publish_result(phase_results, cycle_snapshot)
        publish_output_files = self._extract_publish_output_files(publish_result)
        publish_deliverables = self._extract_publish_deliverables(publish_result, cycle_snapshot)
        publish_reports = self._build_report_summary(publish_result, publish_output_files, publish_deliverables)
        snapshot_metadata = cycle_snapshot.get("metadata") if isinstance(cycle_snapshot.get("metadata"), dict) else {}
        metadata = deepcopy(snapshot_metadata)
        metadata["research_question"] = normalized_question
        metadata["cycle_name"] = (
            self.orchestration_result.pipeline_metadata.get("cycle_name")
            or metadata.get("cycle_name")
        )

        session_result = {
            "status": self.orchestration_result.status,
            "session_id": self.orchestration_result.cycle_id,
            "cycle_id": self.orchestration_result.cycle_id,
            "title": f"中医科研 IMRD 报告：{normalized_question}",
            "question": normalized_question,
            "research_question": normalized_question,
            "executed_phases": list(phase_results.keys()),
            "phase_results": phase_results,
            "metadata": metadata,
            "cycle_snapshot": cycle_snapshot,
        }

        if isinstance(metadata.get("analysis_summary"), dict) and metadata.get("analysis_summary"):
            session_result["analysis_summary"] = deepcopy(metadata.get("analysis_summary") or {})

        if publish_deliverables:
            session_result["deliverables"] = deepcopy(publish_deliverables)

        analysis_results = self.orchestration_result.analysis_results
        if not isinstance(analysis_results, dict) or not analysis_results:
            analysis_results = get_phase_value(publish_result, "analysis_results", {})
        if isinstance(analysis_results, dict) and analysis_results:
            session_result["analysis_results"] = deepcopy(analysis_results)

        research_artifact = self.orchestration_result.research_artifact
        if not isinstance(research_artifact, dict) or not research_artifact:
            research_artifact = get_phase_value(publish_result, "research_artifact", {})
        if isinstance(research_artifact, dict) and research_artifact:
            session_result["research_artifact"] = deepcopy(research_artifact)

        observe_philology = (
            dict(self.orchestration_result.observe_philology)
            if isinstance(self.orchestration_result.observe_philology, dict)
            else {}
        )
        if observe_philology:
            session_result["observe_philology"] = observe_philology
        if publish_output_files:
            session_result["report_outputs"] = deepcopy(publish_output_files)
        if publish_reports:
            session_result["reports"] = publish_reports
        return session_result

    def to_session_result(self) -> Dict[str, Any]:
        return self.session_result


class ResearchRuntimeService:
    """Execute a research session through one shared control path."""

    def __init__(self, orchestrator_config: Optional[Dict[str, Any]] = None):
        raw_config: Dict[str, Any] = deepcopy(orchestrator_config or {})
        profile_defaults = self._resolve_runtime_profile_config(raw_config.get("runtime_profile"))
        self.config: Dict[str, Any] = {**profile_defaults, **raw_config}
        self.pipeline_config: Dict[str, Any] = deepcopy(self.config.get("pipeline_config") or {})
        self.stop_on_failure: bool = bool(self.config.get("stop_on_failure", True))
        self.researchers: List[str] = list(self.config.get("researchers") or ["orchestrator"])

        configured_phases = self.config.get("phases") or list(_DEFAULT_PHASES)
        normalized_phases = [str(item).strip().lower() for item in configured_phases if str(item).strip()]
        self.phase_names = normalized_phases or list(_DEFAULT_PHASES)

    @staticmethod
    def _resolve_runtime_profile_config(runtime_profile: Optional[str]) -> Dict[str, Any]:
        normalized_profile = str(runtime_profile or "").strip().lower()
        if not normalized_profile:
            return {}

        profile_defaults = _SHARED_RUNTIME_PROFILES.get(normalized_profile)
        if profile_defaults is None:
            logger.warning("忽略未知 runtime_profile: %s", runtime_profile)
            return {}

        return deepcopy(profile_defaults)

    def run(
        self,
        topic: str,
        *,
        cycle_id: Optional[str] = None,
        phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
        report_output_formats: Optional[List[str]] = None,
        report_output_dir: Optional[str] = None,
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
        normalized_phase_contexts = self._apply_publish_report_policy(
            normalized_phase_contexts,
            report_output_formats=report_output_formats,
            report_output_dir=report_output_dir,
        )
        resolved_cycle_id = str(cycle_id or "").strip() or None

        resolved_cycle_name = self._resolve_cycle_name(normalized_topic, cycle_name)
        resolved_description = description or normalized_topic
        default_scope = str(self.config.get("default_scope") or "").strip()
        resolved_scope = scope or default_scope or ResearchOrchestrator._infer_scope(normalized_topic)
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
        observe_philology: Dict[str, Any] = {}

        pipeline = ResearchPipeline(self.pipeline_config)
        learning_strategy = self._extract_learning_strategy(pipeline)
        previous_iteration_feedback = self._extract_previous_iteration_feedback(pipeline)
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
                    learning_strategy=learning_strategy,
                    previous_iteration_feedback=previous_iteration_feedback,
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
            observe_philology = resolve_observe_philology_assets(
                observe_phase_result=phase_results.get("observe"),
                observe_documents=cycle_snapshot.get("observe_documents") if isinstance(cycle_snapshot.get("observe_documents"), list) else [],
            )
            if not observe_philology.get("available"):
                observe_philology = {}
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
                "learning_strategy_active": bool(learning_strategy),
                "learned_parameter_count": len(
                    learning_strategy.get("tuned_parameters", {})
                    if isinstance(learning_strategy.get("tuned_parameters"), dict)
                    else {}
                ),
            },
            analysis_results=publish_highlights.get("analysis_results") or {},
            research_artifact=publish_highlights.get("research_artifact") or {},
            observe_philology=observe_philology,
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

    def _resolve_cycle_name(self, topic: str, explicit_cycle_name: Optional[str]) -> str:
        normalized_explicit_cycle_name = str(explicit_cycle_name or "").strip()
        if normalized_explicit_cycle_name:
            return normalized_explicit_cycle_name

        default_cycle_name_mode = str(self.config.get("default_cycle_name_mode") or "slug").strip().lower()
        if default_cycle_name_mode == "timestamp":
            cycle_name_prefix = str(self.config.get("default_cycle_name_prefix") or "research").strip() or "research"
            return f"{cycle_name_prefix}_{int(time.time())}"

        return _slug_topic(topic)

    def _build_phase_context(
        self,
        topic: str,
        phase: Any,
        phase_contexts: Dict[str, Dict[str, Any]],
        *,
        learning_strategy: Optional[Dict[str, Any]],
        previous_iteration_feedback: Optional[Dict[str, Any]],
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
        merged = {**base, **dict(config_override), **dict(call_override)}
        if isinstance(learning_strategy, dict) and learning_strategy and "learning_strategy" not in merged:
            merged["learning_strategy"] = deepcopy(learning_strategy)
        if (
            isinstance(previous_iteration_feedback, dict)
            and previous_iteration_feedback
            and "previous_iteration_feedback" not in merged
        ):
            merged["previous_iteration_feedback"] = deepcopy(previous_iteration_feedback)
        return merged

    @staticmethod
    def _extract_learning_strategy(pipeline: Any) -> Dict[str, Any]:
        getter = getattr(pipeline, "get_learning_strategy", None)
        if callable(getter):
            try:
                strategy = getter()
            except Exception as exc:
                logger.warning("提取学习策略快照失败: %s", exc)
            else:
                if isinstance(strategy, dict):
                    return dict(strategy)

        pipeline_config = getattr(pipeline, "config", None)
        if isinstance(pipeline_config, dict) and isinstance(pipeline_config.get("learning_strategy"), dict):
            return dict(pipeline_config.get("learning_strategy") or {})
        return {}

    @staticmethod
    def _extract_previous_iteration_feedback(pipeline: Any) -> Dict[str, Any]:
        getter = getattr(pipeline, "get_previous_iteration_feedback", None)
        if callable(getter):
            try:
                previous_feedback = getter()
            except Exception as exc:
                logger.warning("提取上一轮学习反馈失败: %s", exc)
            else:
                if isinstance(previous_feedback, dict):
                    return dict(previous_feedback)

        pipeline_config = getattr(pipeline, "config", None)
        if isinstance(pipeline_config, dict) and isinstance(pipeline_config.get("previous_iteration_feedback"), dict):
            return dict(pipeline_config.get("previous_iteration_feedback") or {})
        return {}

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
    def _apply_publish_report_policy(
        phase_contexts: Dict[str, Dict[str, Any]],
        *,
        report_output_formats: Optional[List[str]],
        report_output_dir: Optional[str],
    ) -> Dict[str, Dict[str, Any]]:
        normalized_formats = [
            str(item).strip()
            for item in (report_output_formats or [])
            if str(item).strip()
        ]
        normalized_output_dir = str(report_output_dir or "").strip()
        if not normalized_formats and not normalized_output_dir:
            return phase_contexts

        merged = deepcopy(phase_contexts)
        publish_context = dict(merged.get("publish") or {})
        if normalized_formats:
            publish_context["report_output_formats"] = normalized_formats
        if normalized_output_dir:
            publish_context["report_output_dir"] = normalized_output_dir
        merged["publish"] = publish_context
        return merged

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