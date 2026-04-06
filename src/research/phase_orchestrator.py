"""Phase orchestrator for research pipeline phase scheduling and execution."""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.collector.corpus_bundle import CorpusBundle
from src.core.phase_tracker import PhaseTrackerMixin
from src.research.audit_history import publish_audit_event
from src.research.gap_analyzer import GapAnalyzer
from src.research.pipeline_events import publish_phase_lifecycle_event
from src.research.study_session_manager import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
)

# Keep a module-local symbol for lazy loading, mirroring research_pipeline behavior.
try:
    from src.infra.llm_service import CachedLLMService as _ImportedCachedLLMService
except Exception:
    _ImportedCachedLLMService = None

CachedLLMService = _ImportedCachedLLMService


class PhaseOrchestrator(PhaseTrackerMixin):
    """Coordinates phase lifecycle, execution dispatch, and export/persistence logic."""

    def __init__(self, pipeline: Any):
        self.pipeline = pipeline
        self.logger = logging.getLogger(__name__)
        self._register_event_handlers()

    def _register_event_handlers(self) -> None:
        self.pipeline.event_bus.subscribe("phase.execute.requested", self._on_phase_execute_requested)
        self.pipeline.event_bus.subscribe("cycle.create.requested", self._on_cycle_create_requested)
        self.pipeline.event_bus.subscribe("cycle.start.requested", self._on_cycle_start_requested)
        self.pipeline.event_bus.subscribe("cycle.phase.execute.requested", self._on_cycle_phase_execute_requested)
        self.pipeline.event_bus.subscribe("cycle.complete.requested", self._on_cycle_complete_requested)
        self.pipeline.event_bus.subscribe("cycle.suspend.requested", self._on_cycle_suspend_requested)
        self.pipeline.event_bus.subscribe("cycle.resume.requested", self._on_cycle_resume_requested)

    def _on_phase_execute_requested(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        phase = payload.get("phase")
        cycle = payload.get("cycle")
        context = payload.get("context") or {}
        if phase is None or cycle is None:
            return None
        return self.pipeline.phase_handlers.execute_phase_internal(phase, cycle, context)

    def _on_cycle_create_requested(self, payload: Dict[str, Any]) -> Optional[Any]:
        if not hasattr(self.pipeline, "orchestrator"):
            return None
        cycle_name = payload.get("cycle_name")
        description = payload.get("description")
        objective = payload.get("objective")
        scope = payload.get("scope")
        researchers = payload.get("researchers")
        cycle_options = payload.get("cycle_options") or {}
        if not all(isinstance(value, str) and value for value in [cycle_name, description, objective, scope]):
            return None
        return self.pipeline.orchestrator._create_research_cycle_local(
            cycle_name=cycle_name,
            description=description,
            objective=objective,
            scope=scope,
            researchers=researchers,
            **cycle_options,
        )

    def _on_cycle_start_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self.pipeline, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.pipeline.orchestrator._start_research_cycle_local(cycle_id)

    def _on_cycle_phase_execute_requested(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not hasattr(self.pipeline, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        phase = payload.get("phase")
        if not isinstance(cycle_id, str) or not cycle_id or phase is None:
            return None
        return self.pipeline.orchestrator._execute_research_phase_local(
            cycle_id,
            phase,
            payload.get("phase_context"),
        )

    def _on_cycle_complete_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self.pipeline, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.pipeline.orchestrator._complete_research_cycle_local(cycle_id)

    def _on_cycle_suspend_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self.pipeline, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.pipeline.orchestrator._suspend_research_cycle_local(cycle_id)

    def _on_cycle_resume_requested(self, payload: Dict[str, Any]) -> Optional[bool]:
        if not hasattr(self.pipeline, "orchestrator"):
            return None
        cycle_id = payload.get("cycle_id")
        if not isinstance(cycle_id, str) or not cycle_id:
            return None
        return self.pipeline.orchestrator._resume_research_cycle_local(cycle_id)

    def _start_phase(# type: ignore[override]
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        context: Optional[Dict[str, Any]]=None,
    ) -> Dict[str, Any]:
        phase_entry = {
            "phase": phase_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "context": self._serialize_value(context or {}),
        }
        if self.pipeline._governance_config.get("enable_phase_tracking", True):
            metadata.setdefault("phase_history", []).append(phase_entry)
        publish_phase_lifecycle_event(
            self.pipeline.event_bus,
            "started",
            {
                "phase": phase_name,
                "started_at": phase_entry["started_at"],
                "context": phase_entry["context"],
            },
        )
        publish_audit_event(
            self.pipeline.event_bus,
            "phase_started",
            {
                "phase": phase_name,
                "started_at": phase_entry["started_at"],
                "context": phase_entry["context"],
            },
        )
        return phase_entry

    def _complete_phase(# type: ignore[override]
        self,
        metadata: Dict[str, Any],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "completed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        if phase_name not in metadata.setdefault("completed_phases", []):
            metadata["completed_phases"].append(phase_name)
        metadata["last_completed_phase"] = phase_name
        metadata["final_status"] = "completed"
        publish_phase_lifecycle_event(
            self.pipeline.event_bus,
            "completed",
            {
                "phase": phase_name,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
            },
        )
        publish_audit_event(
            self.pipeline.event_bus,
            "phase_completed",
            {
                "phase": phase_name,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
            },
        )

    def _fail_phase(# type: ignore[override]
        self,
        metadata: Dict[str, Any],
        failed_operations: List[Dict[str, Any]],
        phase_name: str,
        phase_entry: Dict[str, Any],
        start_time: float,
        error: str,
    ) -> None:
        duration = time.perf_counter() - start_time
        phase_entry["status"] = "failed"
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        phase_entry["error"] = error
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        metadata["failed_phase"] = phase_name
        metadata["final_status"] = "failed"
        publish_phase_lifecycle_event(
            self.pipeline.event_bus,
            "failed",
            {
                "phase": phase_name,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
                "error": error,
            },
        )
        publish_audit_event(
            self.pipeline.event_bus,
            "phase_lifecycle_failed",
            {
                "phase": phase_name,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
                "error": error,
            },
        )
        self._record_failed_operation(
            failed_operations,
            phase_name,
            error,
            duration,
            phase_entry.get("context", {}),
        )

    def _record_failed_operation(# type: ignore[override]
        self,
        failed_operations: List[Dict[str, Any]],
        operation: str,
        error: str,
        duration: float,
        details: Optional[Dict[str, Any]]=None,
    ) -> None:
        if not self.pipeline._governance_config.get("persist_failed_operations", True):
            return
        failed_operations.append(
            {
                "operation": operation,
                "error": error,
                "details": self._serialize_value(details or {}),
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration, 6),
            }
        )

    def _build_runtime_metadata(self) -> Dict[str, Any]:
        return self._build_runtime_metadata_from_dict(self.pipeline._metadata)

    def _validate_research_phase_request(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        if cycle_id not in self.pipeline.research_cycles:
            self.pipeline.logger.warning(f"研究循环 {cycle_id} 不存在")
            return {"error": "循环不存在"}

        research_cycle = self.pipeline.research_cycles[cycle_id]
        if research_cycle.status != ResearchCycleStatus.ACTIVE:
            self.pipeline.logger.warning(f"研究循环 {cycle_id} 不处于活跃状态")
            return {"error": "循环未激活"}
        return None

    def _advance_research_cycle_phase(self, research_cycle: ResearchCycle, phase: ResearchPhase) -> None:
        phase_transitions = {
            ResearchPhase.OBSERVE: ResearchPhase.HYPOTHESIS,
            ResearchPhase.HYPOTHESIS: ResearchPhase.EXPERIMENT,
            ResearchPhase.EXPERIMENT: ResearchPhase.ANALYZE,
            ResearchPhase.ANALYZE: ResearchPhase.PUBLISH,
            ResearchPhase.PUBLISH: ResearchPhase.REFLECT,
            ResearchPhase.REFLECT: ResearchPhase.OBSERVE,
        }
        research_cycle.current_phase = phase_transitions.get(phase, research_cycle.current_phase)

    def _build_phase_execution(
        self,
        phase: ResearchPhase,
        started_at: str,
        start_time: float,
        phase_context: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "phase": phase.value,
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "duration": time.perf_counter() - start_time,
            "context": phase_context,
            "result": phase_result,
        }

    def _sync_phase_history_entry(
        self,
        phase_entry: Dict[str, Any],
        phase_execution: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> None:
        phase_entry["completed_at"] = phase_execution["completed_at"]
        phase_entry["duration"] = phase_execution["duration"]
        phase_entry["result"] = self._serialize_value(phase_result)

    def _apply_phase_result(
        self,
        research_cycle: ResearchCycle,
        phase: ResearchPhase,
        phase_result: Dict[str, Any],
    ) -> None:
        research_cycle.metadata["final_status"] = research_cycle.status.value
        if not isinstance(phase_result, dict):
            return

        research_cycle.outcomes.append({"phase": phase.value, "result": phase_result})
        if phase == ResearchPhase.PUBLISH:
            research_cycle.deliverables = phase_result.get("deliverables", [])
        if phase == ResearchPhase.ANALYZE:
            research_cycle.quality_metrics = phase_result.get("results", {})

    def _record_phase_success(self, cycle_id: str, phase: ResearchPhase, start_time: float) -> None:
        publish_audit_event(
            self.pipeline.event_bus,
            "phase_executed",
            {
                "cycle_id": cycle_id,
                "phase": phase.value,
                "duration": time.perf_counter() - start_time,
            },
        )

    def _handle_phase_execution_failure(
        self,
        cycle_id: str,
        phase: ResearchPhase,
        start_time: float,
        exc: Exception,
    ) -> Dict[str, Any]:
        self.pipeline.logger.error(f"研究阶段执行失败: {exc}")
        if cycle_id not in self.pipeline.research_cycles:
            return {"error": str(exc)}

        research_cycle = self.pipeline.research_cycles[cycle_id]
        self._record_failed_phase_history(research_cycle, phase, start_time, str(exc))
        self.pipeline.session_manager.mark_cycle_failed(research_cycle, phase.value, str(exc))
        research_cycle.metadata["analysis_summary"] = self.pipeline.session_manager.build_cycle_analysis_summary(research_cycle)
        publish_audit_event(
            self.pipeline.event_bus,
            "phase_failed",
            {
                "cycle_id": cycle_id,
                "phase": phase.value,
                "error": str(exc),
            },
        )
        return {"error": str(exc)}

    def _record_failed_phase_history(
        self,
        research_cycle: ResearchCycle,
        phase: ResearchPhase,
        start_time: float,
        error: str,
    ) -> None:
        history = research_cycle.metadata.get("phase_history", [])
        if not history or history[-1].get("phase") != phase.value:
            return

        failure_details = {
            "cycle_id": research_cycle.cycle_id,
            "cycle_name": research_cycle.cycle_name,
            "status": research_cycle.status.value,
            "phase": phase.value,
        }
        history[-1]["context"] = self._serialize_value(
            {
                **(history[-1].get("context") or {}),
                **failure_details,
            }
        )
        self._fail_phase(
            research_cycle.metadata,
            research_cycle.metadata.setdefault("failed_operations", []),
            phase.value,
            history[-1],
            start_time,
            error,
        )
        history[-1]["completed_at"] = datetime.now().isoformat()
        history[-1]["duration"] = time.perf_counter() - start_time
        self._record_failed_operation(
            self.pipeline._failed_operations,
            phase.value,
            error,
            time.perf_counter() - start_time,
            failure_details,
        )

    def _execute_phase_internal(
        self,
        phase: ResearchPhase,
        cycle: ResearchCycle,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {
            "phase": phase,
            "cycle": cycle,
            "context": context,
        }
        result = self.pipeline.event_bus.request("phase.execute.requested", payload)
        if isinstance(result, dict):
            return result
        return self.pipeline.phase_handlers.execute_phase_internal(phase, cycle, context)

    def _get_phase_handler(self, phase_name: str) -> Any:
        handler = self.pipeline.phase_handlers.get_handler(phase_name)
        if handler is None:
            raise RuntimeError(f"阶段处理器不可用: {phase_name}")
        return handler

    def _observe_handler(self) -> Any:
        return self._get_phase_handler("observe")

    def _hypothesis_handler(self) -> Any:
        return self._get_phase_handler("hypothesis")

    def _experiment_handler(self) -> Any:
        return self._get_phase_handler("experiment")

    def _analyze_handler(self) -> Any:
        return self._get_phase_handler("analyze")

    def _publish_handler(self) -> Any:
        return self._get_phase_handler("publish")

    def _reflect_handler(self) -> Any:
        return self._get_phase_handler("reflect")

    def _execute_observe_phase(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._observe_handler().execute_observe_phase(cycle, context)

    def _build_observe_seed_lists(self) -> Tuple[List[str], List[str]]:
        return self._observe_handler()._build_observe_seed_lists()

    def _collect_observe_corpus_if_enabled(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._observe_handler()._collect_observe_corpus_if_enabled(context)

    def _register_observe_collection_result(
        self,
        source_result: Optional[Dict[str, Any]],
        source_type: str,
        bundles: List[CorpusBundle],
        fallback_error: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return self._observe_handler()._register_observe_collection_result(
            source_result,
            source_type,
            bundles,
            fallback_error,
        )

    def _to_observe_corpus_bundle(
        self,
        source_result: Dict[str, Any],
        source_type: str,
    ) -> Optional[CorpusBundle]:
        return self._observe_handler()._to_observe_corpus_bundle(source_result, source_type)

    def _run_observe_literature_if_enabled(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._observe_handler()._run_observe_literature_if_enabled(context)

    def _run_observe_ingestion_if_enabled(
        self,
        corpus_result: Optional[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._observe_handler()._run_observe_ingestion_if_enabled(corpus_result, context)

    def _append_corpus_observe_updates(
        self,
        corpus_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        self._observe_handler()._append_corpus_observe_updates(corpus_result, observations, findings)

    def _append_ingestion_observe_updates(
        self,
        ingestion_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        self._observe_handler()._append_ingestion_observe_updates(ingestion_result, observations, findings)

    def _append_literature_observe_updates(
        self,
        literature_result: Optional[Dict[str, Any]],
        observations: List[str],
        findings: List[str],
    ) -> None:
        self._observe_handler()._append_literature_observe_updates(literature_result, observations, findings)

    def _build_observe_metadata(
        self,
        context: Dict[str, Any],
        observations: List[str],
        findings: List[str],
        corpus_result: Optional[Dict[str, Any]],
        ingestion_result: Optional[Dict[str, Any]],
        literature_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return self._observe_handler()._build_observe_metadata(
            context,
            observations,
            findings,
            corpus_result,
            ingestion_result,
            literature_result,
        )

    def _is_ctext_corpus_collected(self, corpus_result: Optional[Dict[str, Any]]) -> bool:
        return self._observe_handler()._is_ctext_corpus_collected(corpus_result)

    def _build_observe_ingestion_flags(
        self,
        ingestion_result: Optional[Dict[str, Any]],
        ingestion_ok: bool,
    ) -> Tuple[bool, bool]:
        return self._observe_handler()._build_observe_ingestion_flags(ingestion_result, ingestion_ok)

    def _has_observe_evidence_matrix(
        self,
        literature_result: Optional[Dict[str, Any]],
        literature_ok: bool,
    ) -> bool:
        return self._observe_handler()._has_observe_evidence_matrix(literature_result, literature_ok)

    def _should_run_observe_ingestion(self, context: Dict[str, Any]) -> bool:
        return self._observe_handler()._should_run_observe_ingestion(context)

    def _should_run_observe_literature(self, context: Dict[str, Any]) -> bool:
        return self._observe_handler()._should_run_observe_literature(context)

    def _run_observe_literature_pipeline(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._observe_handler()._run_observe_literature_pipeline(context)

    def _should_run_clinical_gap_analysis(self, context: Dict[str, Any]) -> bool:
        if "run_clinical_gap_analysis" in context:
            return bool(context.get("run_clinical_gap_analysis"))

        gap_config = self.pipeline.config.get("clinical_gap_analysis", {})
        return bool(gap_config.get("enabled", False))

    def _run_clinical_gap_analysis(
        self,
        evidence_matrix: Dict[str, Any],
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        global CachedLLMService
        if CachedLLMService is None:
            from src.infra.llm_service import CachedLLMService as _CLS

            CachedLLMService = _CLS

        gap_config = self.pipeline.config.get("clinical_gap_analysis", {})
        llm_config = self.pipeline.config.get("models", {}).get("llm", {})

        engine = CachedLLMService.from_gap_config(gap_config, llm_config)
        analyzer = GapAnalyzer(gap_config, llm_service=engine)
        analysis_context = {
            "evidence_matrix": evidence_matrix,
            "literature_summaries": summaries,
            "llm_service": engine,
            "clinical_question": context.get("clinical_question"),
            "literature_query": context.get("literature_query"),
            "research_topic": context.get("research_topic"),
            "gap_output_language": context.get("gap_output_language"),
            "gap_output_mode": context.get("gap_output_mode"),
            "output_language": context.get("output_language"),
            "use_llm_refinement": context.get("use_llm_refinement"),
        }

        try:
            engine.load()
            analyzer.initialize()
            result = analyzer.execute(analysis_context)
            stats = engine.cache_stats()
            self.pipeline.logger.debug(
                "LLM 缓存统计: hits=%d misses=%d total_entries=%s",
                stats.get("session_hits", 0),
                stats.get("session_misses", 0),
                stats.get("total_entries", "n/a"),
            )
            result.setdefault("metadata", {})["cache_stats"] = stats
            return result
        except Exception as e:
            self.pipeline.logger.error(f"Qwen 临床 Gap Analysis 失败: {e}")
            return {
                "clinical_question": str(
                    context.get("clinical_question")
                    or context.get("literature_query")
                    or gap_config.get("default_clinical_question")
                    or "中医干预在目标人群中的临床有效性与安全性证据缺口是什么？"
                ),
                "output_language": str(
                    context.get("gap_output_language")
                    or context.get("output_language")
                    or gap_config.get("default_output_language")
                    or gap_config.get("output_language", "zh")
                ),
                "error": str(e),
            }
        finally:
            analyzer.cleanup()
            engine.unload()

    def _extract_literature_summaries(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for item in records:
            title = (item.get("title") or "").strip()
            abstract = (item.get("abstract") or "").strip()
            text = abstract or title
            if not text:
                continue

            summaries.append(
                {
                    "source": item.get("source", ""),
                    "title": title,
                    "year": item.get("year"),
                    "doi": item.get("doi", ""),
                    "url": item.get("url", ""),
                    "summary_text": text[:1200],
                    "has_abstract": bool(abstract),
                }
            )
        return summaries

    def _build_evidence_matrix(
        self,
        summaries: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        default_dimensions: Dict[str, List[str]] = {
            "condition_terms": ["covid", "diabetes", "cancer", "depression", "inflammation", "pain"],
            "intervention_terms": ["traditional chinese medicine", "tcm", "herb", "formula", "decoction", "acupuncture"],
            "outcome_terms": ["efficacy", "effectiveness", "safety", "survival", "risk", "response"],
            "method_terms": ["randomized", "meta-analysis", "cohort", "case-control", "network", "machine learning"],
        }

        dimension_keywords = context.get("evidence_dimensions") or default_dimensions
        records: List[Dict[str, Any]] = []
        dimension_hit_counts = {key: 0 for key in dimension_keywords.keys()}

        for item in summaries:
            text = f"{item.get('title', '')} {item.get('summary_text', '')}".lower()
            row_hits: Dict[str, List[str]] = {}

            for dimension, keywords in dimension_keywords.items():
                hits = [kw for kw in keywords if kw.lower() in text]
                row_hits[dimension] = hits
                if hits:
                    dimension_hit_counts[dimension] += 1

            coverage_score = sum(1 for hits in row_hits.values() if hits)
            records.append(
                {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "year": item.get("year"),
                    "coverage_score": coverage_score,
                    "dimension_hits": row_hits,
                }
            )

        records.sort(key=lambda r: r.get("coverage_score", 0), reverse=True)
        return {
            "dimension_count": len(dimension_keywords),
            "dimension_keywords": dimension_keywords,
            "dimension_hit_counts": dimension_hit_counts,
            "record_count": len(records),
            "records": records,
        }

    def _should_collect_ctext_corpus(self, context: Dict[str, Any]) -> bool:
        return self._observe_handler()._should_collect_ctext_corpus(context)

    def _should_collect_local_corpus(self, context: Dict[str, Any]) -> bool:
        return self._observe_handler()._should_collect_local_corpus(context)

    def _collect_local_observation_corpus(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._observe_handler()._collect_local_observation_corpus(context)

    def _resolve_observe_data_source(self, context: Dict[str, Any]) -> str:
        return self._observe_handler()._resolve_observe_data_source(context)

    def _resolve_whitelist_groups(self, context: Dict[str, Any]) -> List[str]:
        return self._observe_handler()._resolve_whitelist_groups(context)

    def _collect_ctext_observation_corpus(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._observe_handler()._collect_ctext_observation_corpus(context)

    def _run_observe_ingestion_pipeline(self, corpus_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        return self._observe_handler()._run_observe_ingestion_pipeline(corpus_result, context)

    def _extract_corpus_text_entries(self, corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
        return self._observe_handler()._extract_corpus_text_entries(corpus_result)

    def _execute_hypothesis_phase(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._hypothesis_handler().execute_hypothesis_phase(cycle, context)

    def _build_hypothesis_context(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._hypothesis_handler()._build_hypothesis_context(cycle, context)

    def _infer_hypothesis_domain(
        self,
        cycle: ResearchCycle,
        observations: List[str],
        findings: List[str],
    ) -> str:
        return self._hypothesis_handler()._infer_hypothesis_domain(cycle, observations, findings)

    def _execute_experiment_phase(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._experiment_handler().execute_experiment_phase(cycle, context)

    def _execute_analyze_phase(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._analyze_handler().execute_analyze_phase(cycle, context)

    def _execute_publish_phase(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._publish_handler().execute_publish_phase(cycle, context)

    def _collect_citation_records(
        self,
        cycle: ResearchCycle,
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._publish_handler().collect_citation_records(cycle, context, literature_pipeline)

    def _execute_reflect_phase(self, cycle: ResearchCycle, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._reflect_handler().execute_reflect_phase(cycle, context)

    def get_pipeline_summary(self) -> Dict[str, Any]:
        total_cycles = len(self.pipeline.research_cycles)
        active_cycles = len(self.pipeline.active_cycles)
        completed_cycles = sum(
            1 for c in self.pipeline.research_cycles.values() if c.status == ResearchCycleStatus.COMPLETED
        )
        failed_cycles = sum(
            1 for c in self.pipeline.research_cycles.values() if c.status == ResearchCycleStatus.FAILED
        )

        completion_rate = (completed_cycles / total_cycles) if total_cycles > 0 else 0.0

        return {
            "pipeline_summary": {
                "total_cycles": total_cycles,
                "active_cycles": active_cycles,
                "completed_cycles": completed_cycles,
                "failed_cycles": failed_cycles,
                "completion_rate": round(completion_rate, 4),
                "quality_metrics": self._serialize_value(self.pipeline.quality_metrics),
                "resource_usage": self._serialize_value(self.pipeline.resource_usage),
                "recent_activities": self._serialize_value(
                    self.pipeline.execution_history[-10:] if self.pipeline.execution_history else []
                ),
                "analysis_summary": self.pipeline._build_pipeline_analysis_summary(),
                "report_metadata": self.pipeline._build_report_metadata(),
                "failed_operations": self._serialize_value(self.pipeline._failed_operations),
                "metadata": self._build_runtime_metadata(),
            }
        }

    def export_pipeline_data(self, output_path: str) -> bool:
        phase_entry = self._start_phase(self.pipeline._metadata, "export_pipeline_data", {"output_path": output_path})
        start_time = time.perf_counter()
        try:
            pipeline_data = {
                "report_metadata": {
                    **self.pipeline._build_report_metadata(),
                    "output_path": output_path,
                    "exported_file": os.path.basename(output_path),
                },
                "pipeline_info": {
                    "version": "2.0.0",
                    "generated_at": datetime.now().isoformat(),
                    "pipeline_summary": self.get_pipeline_summary(),
                },
                "research_cycles": [self.pipeline._serialize_cycle(cycle) for cycle in self.pipeline.research_cycles.values()],
                "failed_cycles": [self.pipeline._serialize_cycle(cycle) for cycle in self.pipeline.failed_cycles],
                "execution_history": self._serialize_value(self.pipeline.execution_history),
                "quality_metrics": self._serialize_value(self.pipeline.quality_metrics),
                "resource_usage": self._serialize_value(self.pipeline.resource_usage),
                "failed_operations": self._serialize_value(self.pipeline._failed_operations),
                "metadata": self._build_runtime_metadata(),
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(pipeline_data, f, ensure_ascii=False, indent=2)
            self._complete_phase(self.pipeline._metadata, "export_pipeline_data", phase_entry, start_time)

            self.pipeline.logger.info(f"流程数据已导出到: {output_path}")
            return True

        except Exception as e:
            self._fail_phase(
                self.pipeline._metadata,
                self.pipeline._failed_operations,
                "export_pipeline_data",
                phase_entry,
                start_time,
                str(e),
            )
            self.pipeline.logger.error(f"流程数据导出失败: {e}")
            return False

    def _persist_result(self, cycle: ResearchCycle) -> bool:
        db_path = self.pipeline.config.get(
            "result_store_path",
            os.path.join("output", "research_results.db"),
        )
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        ddl = """
        CREATE TABLE IF NOT EXISTS research_results (
            cycle_id          TEXT PRIMARY KEY,
            cycle_name        TEXT NOT NULL,
            status            TEXT NOT NULL,
            started_at        TEXT,
            completed_at      TEXT,
            duration          REAL,
            research_objective TEXT,
            outcomes_json     TEXT,
            metadata_json     TEXT,
            persisted_at      TEXT NOT NULL
        )
        """
        row = (
            cycle.cycle_id,
            cycle.cycle_name,
            cycle.status.value,
            cycle.started_at,
            cycle.completed_at,
            cycle.duration,
            cycle.research_objective,
            json.dumps(self._serialize_value(cycle.outcomes), ensure_ascii=False),
            json.dumps(self._serialize_value(cycle.metadata), ensure_ascii=False),
            datetime.now().isoformat(),
        )
        upsert = """
        INSERT OR REPLACE INTO research_results
            (cycle_id, cycle_name, status, started_at, completed_at, duration,
             research_objective, outcomes_json, metadata_json, persisted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(ddl)
                conn.execute(upsert, row)
            finally:
                conn.close()
            self.pipeline.logger.info(f"研究结果已持久化: {cycle.cycle_id} → {db_path}")
            return True
        except Exception as exc:  # pragma: no cover
            self.pipeline.logger.warning(f"研究结果持久化失败，已跳过: {exc}")
            return False
