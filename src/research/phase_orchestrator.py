"""Phase orchestrator for research pipeline phase scheduling and execution."""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.phase_tracker import PhaseTrackerMixin
from src.research.audit_history import publish_audit_event
from src.research.gap_analyzer import GapAnalyzer
from src.research.phase_result import get_phase_artifact_map, get_phase_value
from src.research.pipeline_events import publish_phase_lifecycle_event
from src.research.study_session_manager import (
    ResearchCycle,
    ResearchCycleStatus,
    ResearchPhase,
)

_GRAPH_IDENTIFIER_PATTERN = re.compile(r"[^0-9A-Za-z_]+")

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
        phase_name = getattr(phase, "value", phase)
        handler = self.pipeline.phase_handlers.get_handler(str(phase_name))
        if handler is None:
            return {"error": f"未知阶段: {phase_name}"}
        execute = getattr(handler, "execute", None)
        if execute is None:
            return {"error": f"未知阶段: {phase_name}"}
        return execute(cycle, context)

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
        phase_status: str="completed",
        error: Optional[str]=None,
    ) -> None:
        duration = time.perf_counter() - start_time
        normalized_status = str(phase_status or "completed").strip().lower() or "completed"
        completed_like = normalized_status not in {"failed", "skipped", "blocked", "pending", "running"}
        event_lifecycle_status = "completed" if normalized_status == "skipped" or completed_like else "failed"
        audit_action = "phase_completed" if normalized_status == "skipped" or completed_like else "phase_lifecycle_failed"
        phase_entry["status"] = normalized_status
        phase_entry["ended_at"] = datetime.now().isoformat()
        phase_entry["duration_seconds"] = round(duration, 6)
        if error:
            phase_entry["error"] = error
        metadata.setdefault("phase_timings", {})[phase_name] = round(duration, 6)
        if completed_like and phase_name not in metadata.setdefault("completed_phases", []):
            metadata["completed_phases"].append(phase_name)
        if completed_like:
            metadata["last_completed_phase"] = phase_name
        if normalized_status in {"failed", "blocked"}:
            metadata["failed_phase"] = phase_name
        metadata["final_status"] = normalized_status
        publish_phase_lifecycle_event(
            self.pipeline.event_bus,
            event_lifecycle_status,
            {
                "phase": phase_name,
                "status": normalized_status,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
                "error": error,
            },
        )
        publish_audit_event(
            self.pipeline.event_bus,
            audit_action,
            {
                "phase": phase_name,
                "status": normalized_status,
                "ended_at": phase_entry["ended_at"],
                "duration_seconds": phase_entry["duration_seconds"],
                "error": error,
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
            ResearchPhase.EXPERIMENT: ResearchPhase.EXPERIMENT_EXECUTION,
            ResearchPhase.EXPERIMENT_EXECUTION: ResearchPhase.ANALYZE,
            ResearchPhase.ANALYZE: ResearchPhase.PUBLISH,
            ResearchPhase.PUBLISH: ResearchPhase.REFLECT,
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
            "status": str(phase_result.get("status") or "completed").strip().lower() or "completed",
            "started_at": started_at,
            "completed_at": datetime.now().isoformat(),
            "duration": time.perf_counter() - start_time,
            "context": phase_context,
            "result": phase_result,
            "error": phase_result.get("error"),
        }

    def _sync_phase_history_entry(
        self,
        phase_entry: Dict[str, Any],
        phase_execution: Dict[str, Any],
        phase_result: Dict[str, Any],
    ) -> None:
        phase_entry["status"] = phase_execution.get("status") or phase_entry.get("status")
        phase_entry["completed_at"] = phase_execution["completed_at"]
        phase_entry["duration"] = phase_execution["duration"]
        if phase_execution.get("error"):
            phase_entry["error"] = phase_execution.get("error")
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
            research_cycle.deliverables = get_phase_value(phase_result, "deliverables", []) or []
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
        phase_name = getattr(phase, "value", phase)
        handler = self.pipeline.phase_handlers.get_handler(str(phase_name))
        if handler is None:
            return {"error": f"未知阶段: {phase_name}"}
        execute = getattr(handler, "execute", None)
        if execute is None:
            return {"error": f"未知阶段: {phase_name}"}
        return execute(cycle, context)

    def get_handler(self, phase_name: str) -> Any:
        handler = self.pipeline.phase_handlers.get_handler(phase_name)
        if handler is None:
            raise RuntimeError(f"阶段处理器不可用: {phase_name}")
        return handler

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

    def _should_use_structured_result_persistence(self) -> bool:
        database_config = self.pipeline.config.get("database")
        neo4j_config = self.pipeline.config.get("neo4j") or {}
        return bool(isinstance(database_config, dict) and database_config) or bool(neo4j_config.get("enabled"))

    def _normalize_repository_phase_status(self, phase_result: Dict[str, Any]) -> str:
        status = str(phase_result.get("status") or "").strip().lower()
        if phase_result.get("error"):
            return "failed"
        if status in {"failed", "skipped", "pending", "running"}:
            return status
        if status in {"blocked"}:
            return "failed"
        return "completed"

    def _normalize_graph_identifier(self, value: Any, default: str) -> str:
        text = _GRAPH_IDENTIFIER_PATTERN.sub("_", str(value or "").strip())
        text = text.strip("_")
        if not text:
            text = default
        if text[0].isdigit():
            text = f"{default}_{text}"
        return text

    def _normalize_graph_label(self, value: Any, default: str = "Entity") -> str:
        normalized = self._normalize_graph_identifier(value, default)
        parts = [part for part in normalized.split("_") if part]
        if not parts:
            return default
        return "".join(part[:1].upper() + part[1:] for part in parts)

    def _normalize_graph_relationship_type(self, value: Any, default: str = "RELATED_TO") -> str:
        return self._normalize_graph_identifier(value, default).upper()

    def _normalize_graph_properties(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in payload.items():
            if value in (None, "", [], {}):
                continue
            safe_key = self._normalize_graph_identifier(key, "prop")
            if isinstance(value, bool):
                normalized[safe_key] = value
                continue
            if isinstance(value, (int, float, str)):
                normalized[safe_key] = value
                continue
            if isinstance(value, list) and all(isinstance(item, (bool, int, float, str)) for item in value):
                normalized[safe_key] = value
                continue
            normalized[safe_key] = json.dumps(self._serialize_value(value), ensure_ascii=False)
        return normalized

    def _infer_artifact_type(self, phase_name: str, artifact_name: str, file_path: str) -> str:
        name = artifact_name.lower()
        path = file_path.lower()
        if any(token in name for token in ("bibtex", "gbt7714", "citation", "reference")):
            return "reference"
        if any(token in name for token in ("imrd", "report")):
            return "report"
        if phase_name == "publish" and path.endswith((".md", ".docx")):
            return "paper"
        if phase_name == "analyze":
            return "analysis"
        if phase_name == "experiment":
            return "protocol"
        return "other"

    def _infer_mime_type(self, file_path: str) -> Optional[str]:
        path = str(file_path or "").lower()
        if path.endswith(".md"):
            return "text/markdown"
        if path.endswith(".json"):
            return "application/json"
        if path.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if path.endswith(".txt"):
            return "text/plain"
        if path.endswith(".html"):
            return "text/html"
        return None

    def _resolve_artifact_size(self, file_path: str) -> int:
        path = str(file_path or "").strip()
        if not path or not os.path.exists(path):
            return 0
        try:
            return int(os.path.getsize(path))
        except OSError:
            return 0

    def _collect_phase_artifacts(self, phase_name: str, phase_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_artifacts = phase_result.get("artifacts") or []
        artifacts: List[Dict[str, Any]] = []
        if isinstance(raw_artifacts, list):
            artifacts.extend(item for item in raw_artifacts if isinstance(item, dict))

        if not artifacts:
            for name, path in get_phase_artifact_map(phase_result).items():
                artifacts.append({"name": name, "path": path, "type": "file"})

        deduplicated: Dict[tuple[str, str], Dict[str, Any]] = {}
        for artifact in artifacts:
            name = str(artifact.get("name") or artifact.get("type") or artifact.get("artifact_type") or f"{phase_name}_artifact").strip()
            raw_path = artifact.get("path") or artifact.get("file_path")
            if not raw_path and isinstance(artifact.get("value"), str):
                raw_path = artifact.get("value")
            path = str(raw_path or "").strip()
            key = (name, path)
            if key not in deduplicated:
                deduplicated[key] = artifact
        return list(deduplicated.values())

    def _estimate_artifact_size(self, payload: Any) -> int:
        try:
            return len(json.dumps(self._serialize_value(payload), ensure_ascii=False).encode("utf-8"))
        except Exception:
            return 0

    def _collect_observe_semantic_relationships(self, cycle: ResearchCycle) -> List[Dict[str, Any]]:
        observe_execution = cycle.phase_executions.get(ResearchPhase.OBSERVE, {})
        observe_result = observe_execution.get("result") if isinstance(observe_execution, dict) else {}
        if not isinstance(observe_result, dict):
            return []

        ingestion_pipeline = get_phase_value(observe_result, "ingestion_pipeline", {}) or {}
        aggregate = ingestion_pipeline.get("aggregate") if isinstance(ingestion_pipeline, dict) else {}
        aggregate_relationships = aggregate.get("semantic_relationships") if isinstance(aggregate, dict) else None
        if isinstance(aggregate_relationships, list) and aggregate_relationships:
            return [item for item in aggregate_relationships if isinstance(item, dict)]

        relationships: List[Dict[str, Any]] = []
        documents = ingestion_pipeline.get("documents") if isinstance(ingestion_pipeline, dict) else []
        if not isinstance(documents, list):
            return relationships
        for document in documents:
            if not isinstance(document, dict):
                continue
            document_relationships = document.get("semantic_relationships") or []
            if isinstance(document_relationships, list):
                relationships.extend(item for item in document_relationships if isinstance(item, dict))
        return relationships

    def _persist_cycle_phase_executions(
        self,
        repository: Any,
        cycle: ResearchCycle,
        session: Any = None,
    ) -> Dict[str, Dict[str, Any]]:
        phase_records: Dict[str, Dict[str, Any]] = {}
        for phase, execution in cycle.phase_executions.items():
            if not isinstance(execution, dict):
                continue
            phase_name = getattr(phase, "value", str(phase))
            phase_result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
            record = repository.add_phase_execution(
                cycle.cycle_id,
                {
                    "phase": phase_name,
                    "status": self._normalize_repository_phase_status(phase_result),
                    "started_at": execution.get("started_at") or cycle.started_at,
                    "completed_at": execution.get("completed_at") or cycle.completed_at,
                    "duration": execution.get("duration") or 0.0,
                    "input": self._serialize_value(execution.get("context") or {}),
                    "output": self._serialize_value(phase_result),
                    "error_detail": phase_result.get("error"),
                },
                session=session,
            )
            if isinstance(record, dict):
                phase_records[phase_name] = record
        return phase_records

    def _persist_cycle_artifacts(
        self,
        repository: Any,
        cycle: ResearchCycle,
        phase_records: Dict[str, Dict[str, Any]],
        session: Any = None,
    ) -> List[Dict[str, Any]]:
        artifact_records: List[Dict[str, Any]] = []
        for phase, execution in cycle.phase_executions.items():
            if not isinstance(execution, dict):
                continue
            phase_name = getattr(phase, "value", str(phase))
            phase_result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
            phase_record = phase_records.get(phase_name) or {}
            phase_execution_id = phase_record.get("id")

            for artifact in self._collect_phase_artifacts(phase_name, phase_result):
                artifact_name = str(artifact.get("name") or artifact.get("type") or artifact.get("artifact_type") or f"{phase_name}_artifact").strip()
                raw_file_path = artifact.get("path") or artifact.get("file_path")
                if not raw_file_path and isinstance(artifact.get("value"), str):
                    raw_file_path = artifact.get("value")
                file_path = str(raw_file_path or "").strip()
                content_payload = artifact.get("content") if "content" in artifact else artifact
                explicit_artifact_type = str(artifact.get("artifact_type") or "").strip().lower()
                explicit_mime_type = str(artifact.get("mime_type") or "").strip() or None
                explicit_size_bytes = artifact.get("size_bytes")
                artifact_metadata = {
                    "phase": phase_name,
                    "phase_status": phase_result.get("status"),
                }
                if isinstance(artifact.get("metadata"), dict):
                    artifact_metadata.update(self._serialize_value(artifact.get("metadata") or {}))

                size_bytes = 0
                if explicit_size_bytes not in (None, ""):
                    try:
                        size_bytes = int(explicit_size_bytes)
                    except (TypeError, ValueError):
                        size_bytes = 0
                if size_bytes <= 0 and file_path:
                    size_bytes = self._resolve_artifact_size(file_path)
                if size_bytes <= 0:
                    size_bytes = self._estimate_artifact_size(content_payload)

                saved = repository.add_artifact(
                    cycle.cycle_id,
                    {
                        "phase_execution_id": phase_execution_id,
                        "artifact_type": explicit_artifact_type or self._infer_artifact_type(phase_name, artifact_name, file_path),
                        "name": artifact_name,
                        "description": str(artifact.get("description") or artifact.get("label") or "").strip(),
                        "content": self._serialize_value(content_payload),
                        "file_path": file_path or None,
                        "mime_type": explicit_mime_type or self._infer_mime_type(file_path) or "application/json",
                        "size_bytes": size_bytes,
                        "metadata": artifact_metadata,
                    },
                    session=session,
                )
                if isinstance(saved, dict):
                    artifact_records.append(saved)
        return artifact_records

    def _persist_cycle_observe_documents(
        self,
        repository: Any,
        cycle: ResearchCycle,
        phase_records: Dict[str, Dict[str, Any]],
        session: Any = None,
    ) -> List[Dict[str, Any]]:
        observe_execution = cycle.phase_executions.get(ResearchPhase.OBSERVE)
        if not isinstance(observe_execution, dict):
            return []
        phase_result = observe_execution.get("result") if isinstance(observe_execution.get("result"), dict) else {}
        if not isinstance(phase_result, dict):
            return []
        ingestion_pipeline = get_phase_value(phase_result, "ingestion_pipeline", {}) or {}
        if not isinstance(ingestion_pipeline, dict):
            return []
        documents = [item for item in (ingestion_pipeline.get("documents") or []) if isinstance(item, dict)]
        if not documents:
            return []
        persisted = repository.replace_observe_document_graphs(
            cycle.cycle_id,
            str((phase_records.get("observe") or {}).get("id") or "").strip() or None,
            documents,
            session=session,
        )
        return persisted if isinstance(persisted, list) else []

    def _project_cycle_to_neo4j(
        self,
        neo4j_driver: Any,
        cycle: ResearchCycle,
        session_record: Dict[str, Any],
        phase_records: Dict[str, Dict[str, Any]],
        artifact_records: List[Dict[str, Any]],
        observe_documents: List[Dict[str, Any]],
        transaction: Any = None,
    ) -> Dict[str, Any]:
        if neo4j_driver is None:
            return {"status": "skipped", "enabled": False, "node_count": 0, "edge_count": 0}

        try:
            from src.research.research_session_graph_backfill import (
                build_observe_entity_graph_nodes,
                build_observe_graph_edges,
                build_observe_version_graph_edges,
                build_observe_version_graph_nodes,
                build_research_artifact_graph_properties,
                build_research_phase_execution_graph_properties,
                build_research_session_graph_properties,
            )
            from src.storage.neo4j_driver import Neo4jEdge, Neo4jNode

            node_map: Dict[tuple[str, str], Any] = {}
            edge_map: Dict[tuple[str, str, str, str, str], Any] = {}

            def _add_node(label: str, node_id: str, properties: Dict[str, Any]) -> None:
                key = (label, node_id)
                if key not in node_map:
                    node_map[key] = Neo4jNode(
                        id=node_id,
                        label=label,
                        properties=self._normalize_graph_properties(properties),
                    )

            def _add_edge(
                source_id: str,
                target_id: str,
                relationship_type: str,
                source_label: str,
                target_label: str,
                properties: Dict[str, Any],
            ) -> None:
                rel_type = self._normalize_graph_relationship_type(relationship_type)
                key = (source_label, source_id, rel_type, target_label, target_id)
                if key not in edge_map:
                    edge_map[key] = (
                        Neo4jEdge(
                            source_id=source_id,
                            target_id=target_id,
                            relationship_type=rel_type,
                            properties=self._normalize_graph_properties(properties),
                        ),
                        source_label,
                        target_label,
                    )

            _add_node(
                "ResearchSession",
                cycle.cycle_id,
                build_research_session_graph_properties(
                    {
                        "cycle_id": cycle.cycle_id,
                        "cycle_name": cycle.cycle_name,
                        "status": cycle.status.value,
                        "current_phase": session_record.get("current_phase"),
                        "research_objective": cycle.research_objective,
                        "research_scope": cycle.research_scope,
                        "created_at": session_record.get("created_at"),
                        "updated_at": session_record.get("updated_at"),
                        "started_at": cycle.started_at,
                        "completed_at": cycle.completed_at,
                        "duration": cycle.duration,
                    }
                ),
            )

            for phase_name, record in phase_records.items():
                phase_id = str(record.get("id") or f"{cycle.cycle_id}:{phase_name}")
                _add_node(
                    "ResearchPhaseExecution",
                    phase_id,
                    build_research_phase_execution_graph_properties(
                        {
                            **record,
                            "phase": phase_name,
                            "cycle_id": cycle.cycle_id,
                        }
                    ),
                )
                _add_edge(
                    cycle.cycle_id,
                    phase_id,
                    "HAS_PHASE",
                    "ResearchSession",
                    "ResearchPhaseExecution",
                    {"cycle_id": cycle.cycle_id, "phase": phase_name},
                )

            for artifact in artifact_records:
                artifact_id = str(artifact.get("id") or "")
                if not artifact_id:
                    continue
                _add_node(
                    "ResearchArtifact",
                    artifact_id,
                    build_research_artifact_graph_properties(
                        {
                            **artifact,
                            "cycle_id": cycle.cycle_id,
                        }
                    ),
                )
                phase_execution_id = str(artifact.get("phase_execution_id") or "").strip()
                if phase_execution_id:
                    _add_edge(
                        phase_execution_id,
                        artifact_id,
                        "GENERATED",
                        "ResearchPhaseExecution",
                        "ResearchArtifact",
                        {"cycle_id": cycle.cycle_id},
                    )
                else:
                    _add_edge(
                        cycle.cycle_id,
                        artifact_id,
                        "HAS_ARTIFACT",
                        "ResearchSession",
                        "ResearchArtifact",
                        {"cycle_id": cycle.cycle_id},
                    )

            observe_phase_id = str((phase_records.get("observe") or {}).get("id") or "").strip()
            observe_document_records = [item for item in observe_documents if isinstance(item, dict)] if isinstance(observe_documents, list) else []
            if observe_document_records:
                for node in build_observe_entity_graph_nodes(observe_document_records):
                    _add_node(node.label, node.id, node.properties)
                for node in build_observe_version_graph_nodes(observe_document_records):
                    _add_node(node.label, node.id, node.properties)
                for edge, source_label, target_label in build_observe_graph_edges(
                    cycle.cycle_id,
                    observe_phase_id,
                    observe_document_records,
                ):
                    _add_edge(
                        edge.source_id,
                        edge.target_id,
                        edge.relationship_type,
                        source_label,
                        target_label,
                        edge.properties,
                    )
                for edge, source_label, target_label in build_observe_version_graph_edges(
                    cycle.cycle_id,
                    observe_phase_id,
                    observe_document_records,
                ):
                    _add_edge(
                        edge.source_id,
                        edge.target_id,
                        edge.relationship_type,
                        source_label,
                        target_label,
                        edge.properties,
                    )
            else:
                for relation in self._collect_observe_semantic_relationships(cycle):
                    source_name = str(relation.get("source") or "").strip()
                    target_name = str(relation.get("target") or "").strip()
                    if not source_name or not target_name:
                        continue
                    source_type = self._normalize_graph_label(relation.get("source_type") or "Entity", "Entity")
                    target_type = self._normalize_graph_label(relation.get("target_type") or "Entity", "Entity")
                    source_id = f"entity::{source_name}"
                    target_id = f"entity::{target_name}"
                    _add_node(source_type, source_id, {"name": source_name, "entity_type": relation.get("source_type") or source_type})
                    _add_node(target_type, target_id, {"name": target_name, "entity_type": relation.get("target_type") or target_type})
                    _add_edge(
                        source_id,
                        target_id,
                        relation.get("type") or "RELATED_TO",
                        source_type,
                        target_type,
                        {
                            **(relation.get("metadata") if isinstance(relation.get("metadata"), dict) else {}),
                            "cycle_id": cycle.cycle_id,
                            "phase": "observe",
                        },
                    )
                    if observe_phase_id:
                        _add_edge(
                            observe_phase_id,
                            source_id,
                            "CAPTURED",
                            "ResearchPhaseExecution",
                            source_type,
                            {"cycle_id": cycle.cycle_id, "phase": "observe"},
                        )
                        _add_edge(
                            observe_phase_id,
                            target_id,
                            "CAPTURED",
                            "ResearchPhaseExecution",
                            target_type,
                            {"cycle_id": cycle.cycle_id, "phase": "observe"},
                        )

            nodes = list(node_map.values())
            edges = list(edge_map.values())
            _scope = "current_cycle"
            if transaction is not None:
                if nodes:
                    transaction.neo4j_batch_nodes(nodes)
                if edges:
                    transaction.neo4j_batch_edges(edges)
                return {
                    "status": "active",
                    "enabled": True,
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "graph_projection_scope": _scope,
                }
            node_status = neo4j_driver.batch_create_nodes(nodes)
            edge_status = neo4j_driver.batch_create_relationships(edges)
            if node_status is False or edge_status is False:
                return {
                    "status": "degraded",
                    "enabled": True,
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "graph_projection_scope": _scope,
                }
            return {
                "status": "active",
                "enabled": True,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "graph_projection_scope": _scope,
            }
        except Exception as exc:
            if transaction is not None:
                raise RuntimeError(f"Neo4j 研究资产投影失败: {exc}") from exc
            self.pipeline.logger.warning("Neo4j 研究资产投影失败，已降级为仅 PG 持久化: %s", exc)
            return {
                "status": "error",
                "enabled": True,
                "error": str(exc),
                "node_count": 0,
                "edge_count": 0,
            }

    def _persist_result_structured(self, cycle: ResearchCycle) -> bool:
        from src.infrastructure.research_session_repo import ResearchSessionRepository
        from src.storage import StorageBackendFactory

        factory = StorageBackendFactory(self.pipeline.config)
        try:
            persistence_report = factory.initialize()
            consistency_state = factory.get_consistency_state()
            repository = ResearchSessionRepository(factory.db_manager)
            session_record: Dict[str, Any] = {}
            phase_records: Dict[str, Dict[str, Any]] = {}
            observe_documents: List[Dict[str, Any]] = []
            artifact_records: List[Dict[str, Any]] = []
            graph_report: Dict[str, Any] = {
                "status": persistence_report.get("neo4j_status") if persistence_report.get("neo4j_status") != "active" else "skipped",
                "enabled": bool(factory.neo4j_driver),
                "node_count": 0,
                "edge_count": 0,
            }

            with factory.transaction() as txn:
                pg_session = txn.pg_session
                if repository.get_session(cycle.cycle_id, session=pg_session):
                    repository.delete_session(cycle.cycle_id, session=pg_session)
                session_record = repository.save_from_cycle(cycle, session=pg_session)
                phase_records = self._persist_cycle_phase_executions(repository, cycle, session=pg_session)
                observe_documents = self._persist_cycle_observe_documents(repository, cycle, phase_records, session=pg_session)
                artifact_records = self._persist_cycle_artifacts(repository, cycle, phase_records, session=pg_session)
                graph_report = self._project_cycle_to_neo4j(
                    factory.neo4j_driver,
                    cycle,
                    session_record if isinstance(session_record, dict) else {},
                    phase_records,
                    artifact_records,
                    observe_documents,
                    transaction=txn,
                )

                cycle.metadata["storage_persistence"] = {
                    "mode": consistency_state.mode,
                    "consistency_state": consistency_state.to_dict(),
                    "db_type": persistence_report.get("db_type"),
                    "pg_status": persistence_report.get("pg_status"),
                    "neo4j_status": graph_report.get("status") if graph_report.get("enabled") else persistence_report.get("neo4j_status"),
                    "phase_execution_count": len(phase_records),
                    "artifact_count": len(artifact_records),
                    "observe_document_count": len(observe_documents),
                    "observe_version_witness_count": sum(
                        1
                        for item in observe_documents
                        if isinstance(item, dict)
                        and (
                            str((item.get("version_metadata") or {}).get("witness_key") or "").strip()
                            or str(item.get("witness_key") or "").strip()
                        )
                    ),
                    "observe_version_lineage_count": len(
                        {
                            str(
                                ((item.get("version_metadata") or {}).get("version_lineage_key") or "").strip()
                                or ((item.get("version_metadata") or {}).get("work_fragment_key") or "").strip()
                                or str(item.get("version_lineage_key") or "").strip()
                            )
                            for item in observe_documents
                            if isinstance(item, dict)
                            and (
                                str(((item.get("version_metadata") or {}).get("version_lineage_key") or "").strip())
                                or str(((item.get("version_metadata") or {}).get("work_fragment_key") or "").strip())
                                or str(item.get("version_lineage_key") or "").strip()
                            )
                        }
                    ),
                    "observe_entity_count": sum(int(item.get("entity_count") or 0) for item in observe_documents if isinstance(item, dict)),
                    "observe_relationship_count": sum(int(item.get("relationship_count") or 0) for item in observe_documents if isinstance(item, dict)),
                    "graph_node_count": graph_report.get("node_count", 0),
                    "graph_edge_count": graph_report.get("edge_count", 0),
                    "eventual_consistency": self._classify_eventual_consistency(
                        consistency_state, graph_report,
                    ),
                }
                repository.update_session(cycle.cycle_id, {"metadata": cycle.metadata}, session=pg_session)

            self.pipeline.logger.info("研究结果已持久化到结构化存储: %s", cycle.cycle_id)
            return True
        finally:
            factory.close()

    @staticmethod
    def _classify_eventual_consistency(
        consistency_state: Any,
        graph_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """标注当前持久化是否存在 eventual consistency 边界。

        返回结构::
            {
                "graph_backfill_pending": bool,
                "reason": Optional[str],
            }
        """
        from src.storage.consistency import MODE_DUAL_WRITE

        graph_ok = (
            graph_report.get("enabled")
            and graph_report.get("status") == "active"
            and graph_report.get("node_count", 0) > 0
        )
        if consistency_state.mode == MODE_DUAL_WRITE and graph_ok:
            return {"graph_backfill_pending": False, "reason": None}

        if not graph_report.get("enabled"):
            reason = "Neo4j 未启用，图投影需后续 backfill"
        elif graph_report.get("status") != "active":
            reason = f"图投影状态 {graph_report.get('status')}，需后续 backfill"
        elif consistency_state.mode != MODE_DUAL_WRITE:
            reason = f"存储模式 {consistency_state.mode}，图数据需后续 backfill"
        else:
            reason = "图投影节点为零，需后续 backfill"
        return {"graph_backfill_pending": True, "reason": reason}

    def _persist_result_legacy_sqlite(self, cycle: ResearchCycle) -> bool:
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

    def _persist_result(self, cycle: ResearchCycle) -> bool:
        if self._should_use_structured_result_persistence():
            try:
                if self._persist_result_structured(cycle):
                    return True
            except Exception as exc:  # pragma: no cover
                self.pipeline.logger.warning("结构化研究结果持久化失败，回退 legacy sqlite: %s", exc)
        return self._persist_result_legacy_sqlite(cycle)
