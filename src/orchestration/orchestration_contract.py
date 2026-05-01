"""Shared orchestration contracts used by runtime and legacy orchestrator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.research.phase_result import get_phase_artifact_map, get_phase_value


@dataclass
class PhaseOutcome:
    """Summary for a single research phase execution."""

    phase: str
    status: str
    duration_sec: float
    error: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "duration_sec": round(self.duration_sec, 3),
            "error": self.error,
            "summary": self.summary,
        }


@dataclass
class OrchestrationResult:
    """Final orchestration output."""

    topic: str
    cycle_id: str
    status: str
    started_at: str
    completed_at: str
    total_duration_sec: float
    phases: List[PhaseOutcome]
    pipeline_metadata: Dict[str, Any]
    analysis_results: Dict[str, Any] = field(default_factory=dict)
    research_artifact: Dict[str, Any] = field(default_factory=dict)
    observe_philology: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "topic": self.topic,
            "cycle_id": self.cycle_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_sec": round(self.total_duration_sec, 3),
            "phases": [p.to_dict() for p in self.phases],
            "pipeline_metadata": self.pipeline_metadata,
        }
        if self.analysis_results:
            payload["analysis_results"] = self.analysis_results
        if self.research_artifact:
            payload["research_artifact"] = self.research_artifact
        if self.observe_philology:
            payload["observe_philology"] = self.observe_philology
        return payload

    @property
    def succeeded_phases(self) -> List[str]:
        return [p.phase for p in self.phases if p.status == "completed"]

    @property
    def failed_phases(self) -> List[str]:
        return [p.phase for p in self.phases if p.status == "failed"]


def topic_to_phase_context(
    topic: str,
    phase: Any,
    *,
    study_type: Optional[str] = None,
    primary_outcome: Optional[str] = None,
    intervention: Optional[str] = None,
    comparison: Optional[str] = None,
) -> Dict[str, Any]:
    """Build conservative default phase context from a research topic."""
    phase_name = str(getattr(phase, "value", phase)).lower()
    resolved_study_type = study_type or _infer_study_type(topic)
    resolved_primary_outcome = primary_outcome or _infer_primary_outcome(topic)
    resolved_intervention = intervention or _infer_intervention(topic)
    resolved_comparison = comparison or _infer_comparison(topic)

    base: Dict[str, Any] = {"research_topic": topic}

    if phase_name == "observe":
        return {
            **base,
            "run_literature_retrieval": False,
            "run_preprocess_and_extract": False,
            "use_ctext_whitelist": False,
            "data_source": "manual",
            "literature_query": topic,
        }
    if phase_name == "hypothesis":
        return {
            **base,
            "research_objective": topic,
            "study_type": resolved_study_type,
            "primary_outcome": resolved_primary_outcome,
            "intervention": resolved_intervention,
            "comparison": resolved_comparison,
        }
    if phase_name == "experiment":
        return {
            **base,
            "study_type": resolved_study_type,
            "primary_outcome": resolved_primary_outcome,
            "outcome": resolved_primary_outcome,
            "intervention": resolved_intervention,
            "comparison": resolved_comparison,
        }
    if phase_name == "experiment_execution":
        return {
            **base,
            "execution_mode": "external_import",
            "external_execution_required": True,
        }
    if phase_name == "analyze":
        return {**base}
    if phase_name == "publish":
        return {**base}
    if phase_name == "reflect":
        return {**base}
    return base


def summarize_phase_result(phase: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract stable summary fields from raw phase results."""
    phase_name = str(getattr(phase, "value", phase)).lower()

    if phase_name == "observe":
        return {
            "observation_count": len(get_phase_value(result, "observations", [])),
            "finding_count": len(get_phase_value(result, "findings", [])),
            "data_source": (result.get("metadata") or {}).get("data_source", "unknown"),
            "corpus_schema": (result.get("metadata") or {}).get("corpus_schema"),
            "literature_records": (
                get_phase_value(result, "literature_pipeline", {}) or {}
            ).get("record_count", 0),
        }
    if phase_name == "hypothesis":
        hyps = get_phase_value(result, "hypotheses", []) or []
        return {
            "hypothesis_count": len(hyps),
            "validated_count": sum(1 for h in hyps if h.get("status") == "validated"),
            "domain": get_phase_value(result, "domain", ""),
        }
    if phase_name == "experiment":
        experiment_results = result.get("results") or {}
        metadata = result.get("metadata") or {}
        protocol_designs = (
            get_phase_value(result, "protocol_designs", [])
            or get_phase_value(result, "experiments", [])
            or []
        )
        first_protocol_design = protocol_designs[0] if protocol_designs else {}
        design_completion_rate = get_phase_value(result, "design_completion_rate", None)
        if design_completion_rate is None:
            design_completion_rate = get_phase_value(result, "success_rate", 0.0)
        return {
            "protocol_design_count": len(protocol_designs),
            "design_completion_rate": design_completion_rate,
            "selected_hypothesis_id": metadata.get("selected_hypothesis_id", ""),
            "evidence_record_count": metadata.get("evidence_record_count", 0),
            "weighted_evidence_score": metadata.get("weighted_evidence_score", 0.0),
            "methodology": experiment_results.get("methodology")
            or first_protocol_design.get("methodology", ""),
            "sample_size": experiment_results.get("sample_size")
            or first_protocol_design.get("sample_size", 0),
            "highest_gap_priority": metadata.get("highest_gap_priority", "低"),
            "execution_status": experiment_results.get("execution_status")
            or metadata.get("execution_status", "not_executed"),
            "real_world_validation_status": experiment_results.get(
                "real_world_validation_status"
            )
            or metadata.get("real_world_validation_status", "not_started"),
        }
    if phase_name == "experiment_execution":
        execution_results = result.get("results") or {}
        metadata = result.get("metadata") or {}
        return {
            "imported_record_count": metadata.get(
                "imported_record_count",
                len(get_phase_value(result, "analysis_records", []) or []),
            ),
            "imported_relationship_count": metadata.get(
                "imported_relationship_count",
                len(get_phase_value(result, "analysis_relationships", []) or []),
            ),
            "sampling_event_count": metadata.get(
                "sampling_event_count",
                len(get_phase_value(result, "sampling_events", []) or []),
            ),
            "imported_artifact_count": metadata.get(
                "imported_artifact_count", len(get_phase_artifact_map(result))
            ),
            "execution_status": execution_results.get("execution_status")
            or metadata.get("execution_status", "not_executed"),
            "real_world_validation_status": execution_results.get(
                "real_world_validation_status"
            )
            or metadata.get("real_world_validation_status", "not_started"),
        }
    if phase_name == "analyze":
        return {
            "analysis_methods": result.get("methods_used", []),
            "key_findings": result.get("key_findings", [])[:3],
        }
    if phase_name == "publish":
        summary = {
            "deliverable_count": len(get_phase_value(result, "deliverables", [])),
            "abstract_word_count": len(str(result.get("abstract", "")).split()),
        }
        output_files = get_phase_artifact_map(result)
        if output_files:
            summary["output_files"] = output_files
        return summary
    if phase_name == "reflect":
        return {
            "improvement_suggestions": get_phase_value(result, "improvements", [])[:3],
            "next_cycle_focus": result.get("next_cycle_focus", ""),
        }
    return {}


def resolve_phase_outcome_status(result: Dict[str, Any]) -> str:
    """Normalize raw phase status into PhaseOutcome status."""
    status = (
        str((result or {}).get("status") or "completed").strip().lower() or "completed"
    )
    if (result or {}).get("error"):
        return "failed"
    if status == "skipped":
        return "skipped"
    if status in {"failed", "blocked", "pending", "running"}:
        return "failed"
    return "completed"


def extract_publish_result_highlights(
    pipeline: Any,
    cycle_id: str,
) -> Dict[str, Dict[str, Any]]:
    """Extract publish phase highlights from a pipeline cycle."""
    cycle = pipeline.research_cycles.get(cycle_id)
    if cycle is None:
        return {}
    publish_execution = cycle.phase_executions.get(pipeline.ResearchPhase.PUBLISH) or {}
    publish_result = publish_execution.get("result") or {}
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


def infer_scope(topic: str) -> str:
    keywords = ["古籍", "方剂", "本草", "临床", "药理", "证候", "针灸", "经络"]
    hits = [kw for kw in keywords if kw in topic]
    if hits:
        return "+".join(hits[:3])
    return "中医古籍与现代研究"


_infer_scope = infer_scope


def _infer_study_type(topic: str) -> str:
    normalized = topic.lower()
    if any(
        keyword in normalized for keyword in ("meta", "荟萃", "合并分析", "合并效应")
    ):
        return "meta_analysis"
    if any(
        keyword in normalized
        for keyword in ("系统综述", "systematic", "prisma", "文献综述")
    ):
        return "systematic_review"
    if any(
        keyword in normalized
        for keyword in ("病例对照", "case-control", "odds ratio", "危险因素")
    ):
        return "case_control"
    if any(keyword in normalized for keyword in ("队列", "cohort", "随访", "预后")):
        return "cohort"
    if any(
        keyword in normalized
        for keyword in ("网络药理", "靶点", "通路", "分子对接", "kegg", "ppi")
    ):
        return "network_pharmacology"
    return "rct"


def _infer_primary_outcome(topic: str) -> str:
    normalized = topic.lower()
    if any(keyword in normalized for keyword in ("血压", "高血压")):
        return "收缩压/舒张压变化"
    if any(keyword in normalized for keyword in ("血糖", "糖尿病", "hba1c")):
        return "HbA1c 或空腹血糖变化"
    if any(keyword in normalized for keyword in ("生存", "死亡", "复发", "事件")):
        return "事件发生率或复发率"
    if any(keyword in normalized for keyword in ("疼痛", "症状", "评分", "量表")):
        return "症状量表评分变化"
    if any(keyword in normalized for keyword in ("机制", "靶点", "通路", "网络药理")):
        return "核心靶点与通路富集特征"
    return "主要临床疗效结局"


def _infer_intervention(topic: str) -> str:
    matches = re.findall(
        r"[\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:汤|散|丸|方|颗粒|胶囊|针灸|艾灸)", topic
    )
    if matches:
        return f"{matches[0]} 干预"
    if "中药" in topic or "方剂" in topic:
        return "目标中药/方剂干预"
    return "目标中医干预方案"


def _infer_comparison(topic: str) -> str:
    normalized = topic.lower()
    if "安慰剂" in topic:
        return "安慰剂对照"
    if any(
        keyword in normalized
        for keyword in ("队列", "cohort", "病例对照", "case-control")
    ):
        return "非暴露组或匹配对照组"
    return "常规治疗或安慰剂"


def _slug_topic(topic: str, max_len: int = 40) -> str:
    """Convert topic into a legal, bounded cycle name."""
    clean = "".join(c for c in topic if c.isalnum() or c in "-_ ，。·")
    clean = clean.strip().replace(" ", "_")[:max_len] or "research_cycle"
    return clean


__all__ = [
    "OrchestrationResult",
    "PhaseOutcome",
    "_infer_scope",
    "_slug_topic",
    "extract_publish_result_highlights",
    "infer_scope",
    "resolve_phase_outcome_status",
    "summarize_phase_result",
    "topic_to_phase_context",
]
