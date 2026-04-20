from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

from src.research.evidence_contract import build_phase_evidence_protocol
from src.research.learning_strategy import (
    StrategyApplicationTracker,
    has_learning_strategy,
    resolve_learning_flag,
    resolve_learning_strategy,
    resolve_numeric_learning_parameter,
)

try:
    from src.research.theoretical_framework import (
        HypothesisStatus,
        ResearchDomain,
        ResearchHypothesis,
        TheoreticalFramework,
    )
except Exception:
    HypothesisStatus = None
    ResearchDomain = None
    ResearchHypothesis = None
    TheoreticalFramework = None

from src.research.phase_result import build_phase_result, get_phase_value

_PROTOCOL_DESIGN_DISPLAY_NAME = "实验方案阶段"
_PROTOCOL_DESIGN_BOUNDARY_NOTICE = "当前阶段仅生成研究协议与验证计划，不执行真实实验、临床试验或外部验证。"


class ExperimentPhaseMixin:
    """Mixin: experiment 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    当前阶段语义收口为 protocol design，而不是实验执行。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_experiment_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        self._experiment_tracker = StrategyApplicationTracker("experiment", context, self.pipeline.config)
        selected_hypothesis, selection_metadata = self._resolve_selected_hypothesis(cycle, context)
        if selected_hypothesis is None:
            blocked_metadata = {
                "phase_semantics": "protocol_design",
                "phase_display_name": _PROTOCOL_DESIGN_DISPLAY_NAME,
                "protocol_design_only": True,
                "execution_boundary": _PROTOCOL_DESIGN_BOUNDARY_NOTICE,
                "execution_status": "not_executed",
                "real_world_validation_status": "not_started",
                "validation_status": "blocked",
                "reason": "missing_hypothesis_selection",
                **selection_metadata,
            }
            return build_phase_result(
                "experiment",
                status="blocked",
                results={
                    "protocol_designs": [],
                    "experiments": [],
                    "protocol_design": {},
                    "study_protocol": {},
                    "selected_hypothesis": None,
                    "design_completion_rate": 0.0,
                    "execution_status": "not_executed",
                    "real_world_validation_status": "not_started",
                },
                metadata=blocked_metadata,
            )

        experiment_framework = self._create_theoretical_framework()
        experiment_context = self._build_experiment_context(cycle, context, selected_hypothesis)
        research_hypothesis = self._convert_to_research_hypothesis(selected_hypothesis, cycle)
        experiment = experiment_framework.design_experiment(research_hypothesis, experiment_context)

        experiment_payload = experiment.to_dict()
        study_protocol = experiment_payload.get("study_protocol") if isinstance(experiment_payload.get("study_protocol"), dict) else {}
        protocol_design_payload = {
            **experiment_payload,
            "phase_semantics": "protocol_design",
            "phase_display_name": _PROTOCOL_DESIGN_DISPLAY_NAME,
            "protocol_design_only": True,
            "execution_boundary": _PROTOCOL_DESIGN_BOUNDARY_NOTICE,
            "execution_status": "not_executed",
            "real_world_validation_status": "not_started",
            "human_execution_required": True,
        }
        experiment_results = {
            "protocol_designs": [protocol_design_payload],
            "experiments": [protocol_design_payload],
            "protocol_design": protocol_design_payload,
            "study_design": experiment.experimental_design,
            "sample_size": experiment.sample_size,
            "duration_days": experiment.duration,
            "methodology": experiment.methodology,
            "validation_metrics": {
                "quality_score": experiment.quality_score,
                "reproducibility_score": experiment.reproducibility_score,
                "scientific_validity": experiment.scientific_validity,
            },
            "data_sources": experiment.data_sources,
            "validation_plan": selected_hypothesis.get("validation_plan", ""),
            "expected_results": experiment.expected_results,
            "evidence_profile": experiment_context.get("evidence_profile", {}),
            "source_weights": experiment_context.get("source_weights", []),
            "gap_priority_summary": experiment_context.get("gap_priority_summary", {}),
            "study_protocol": study_protocol,
            "selected_hypothesis": selected_hypothesis,
            "design_completion_rate": 1.0,
            "phase_focus": "protocol_design",
            "execution_boundary": _PROTOCOL_DESIGN_BOUNDARY_NOTICE,
            "execution_status": "not_executed",
            "real_world_validation_status": "not_started",
        }
        metadata = {
            "study_type": experiment.experimental_design,
            "protocol_study_type": study_protocol.get("study_type", ""),
            "protocol_source": study_protocol.get("protocol_source", ""),
            "small_model_plan": (study_protocol.get("optimizer_metadata") or {}).get("small_model_plan"),
            "llm_cost_report": (study_protocol.get("optimizer_metadata") or {}).get("llm_cost_report"),
            "fallback_path": (study_protocol.get("optimizer_metadata") or {}).get("fallback_path"),
            "phase_semantics": "protocol_design",
            "phase_display_name": _PROTOCOL_DESIGN_DISPLAY_NAME,
            "protocol_design_only": True,
            "execution_boundary": _PROTOCOL_DESIGN_BOUNDARY_NOTICE,
            "execution_status": "not_executed",
            "real_world_validation_status": "not_started",
            "human_execution_required": True,
            "validation_status": "protocol_defined",
            "evidence_record_count": experiment_context.get("evidence_profile", {}).get("record_count", 0),
            "weighted_evidence_score": experiment_context.get("evidence_profile", {}).get("weighted_evidence_score", 0.0),
            "clinical_gap_available": experiment_context.get("evidence_profile", {}).get("clinical_gap_available", False),
            "highest_gap_priority": experiment_context.get("gap_priority_summary", {}).get("highest_priority", "低"),
            "learning_strategy_applied": has_learning_strategy(context, self.pipeline.config),
            "protocol_llm_generation_enabled": bool(experiment_context.get("use_llm_protocol_generation", False)),
            **selection_metadata,
        }
        if hasattr(self, "_experiment_tracker"):
            metadata["learning"] = self._experiment_tracker.to_metadata()
            self.pipeline.register_phase_learning_manifest(
                {"phase": "experiment", **self._experiment_tracker.to_metadata()}
            )
        evidence_protocol = build_phase_evidence_protocol(
            "experiment",
            evidence_records=experiment_context.get("evidence_records") or [],
            evidence_grade="protocol_design",
            evidence_summary={
                "study_design": experiment.experimental_design,
                "sample_size": experiment.sample_size,
                "methodology": experiment.methodology,
            },
        )
        experiment_results["evidence_protocol"] = evidence_protocol
        return build_phase_result(
            "experiment",
            status="completed",
            results=experiment_results,
            metadata=metadata,
        )

    def _create_theoretical_framework(self) -> Any:
        if TheoreticalFramework is None:
            raise RuntimeError("TheoreticalFramework 不可用，无法生成实验设计")
        return TheoreticalFramework(self.pipeline.config.get("theoretical_framework_config") or {})

    def _build_experiment_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> Dict[str, Any]:
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        literature_pipeline = get_phase_value(observe_result, "literature_pipeline", {}) or {}
        evidence_matrix = literature_pipeline.get("evidence_matrix") or {}
        clinical_gap_analysis = literature_pipeline.get("clinical_gap_analysis") or {}
        evidence_records = evidence_matrix.get("records") or []
        dimension_count = int(evidence_matrix.get("dimension_count") or 0)
        top_records = [dict(item) for item in evidence_records[:3] if isinstance(item, dict)]
        weighted_records = self._build_weighted_evidence_records(top_records, dimension_count)
        source_weights = self._build_source_weights(literature_pipeline, evidence_records)
        evidence_profile = self._build_evidence_profile(
            evidence_matrix,
            weighted_records,
            source_weights,
            literature_pipeline,
        )
        gap_priority_summary = self._extract_gap_priority_summary(clinical_gap_analysis)
        derived_data_sources = self._build_experiment_data_sources(source_weights, evidence_records)
        use_llm_protocol_generation = self._resolve_experiment_flag(
            context,
            "use_llm_protocol_generation",
            True,
        )
        return {
            "research_objective": cycle.research_objective or context.get("research_objective") or cycle.description,
            "research_scope": cycle.research_scope or context.get("research_scope") or "",
            "research_domain": selected_hypothesis.get("domain") or context.get("research_domain") or "integrative_research",
            "study_type": context.get("study_type"),
            "validation_plan": selected_hypothesis.get("validation_plan") or "",
            "supporting_signals": selected_hypothesis.get("supporting_signals") or [],
            "contradiction_signals": selected_hypothesis.get("contradiction_signals") or [],
            "evidence_matrix": evidence_matrix,
            "evidence_records": evidence_records,
            "weighted_evidence_records": weighted_records,
            "evidence_priority_titles": [item.get("title", "") for item in weighted_records if item.get("title")],
            "evidence_profile": evidence_profile,
            "source_weights": source_weights,
            "clinical_gap_analysis": clinical_gap_analysis,
            "gap_priority_summary": gap_priority_summary,
            "data_sources": context.get("data_sources") or derived_data_sources,
            "primary_outcome": context.get("primary_outcome") or context.get("outcome") or selected_hypothesis.get("expected_outcome") or cycle.research_objective,
            "llm_engine": context.get("llm_engine") or self.pipeline.config.get("llm_engine") or self.pipeline.config.get("llm_service"),
            "llm_service": context.get("llm_service") or self.pipeline.config.get("llm_service") or self.pipeline.config.get("llm_engine"),
            "use_llm_protocol_generation": use_llm_protocol_generation,
            "sample_size": self._resolve_experiment_sample_size(context, evidence_profile, selected_hypothesis, gap_priority_summary),
            "duration_days": self._resolve_experiment_duration_days(context, evidence_profile, selected_hypothesis),
            "methodology": self._resolve_experiment_methodology(context, evidence_profile, source_weights, gap_priority_summary),
            "learning_strategy": resolve_learning_strategy(context, self.pipeline.config),
        }

    def _resolve_experiment_flag(
        self,
        context: Dict[str, Any],
        flag_name: str,
        default: bool,
    ) -> bool:
        if flag_name in context:
            return bool(context.get(flag_name))

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        experiment_flag_name = f"experiment_{flag_name}"
        if experiment_flag_name in strategy:
            return bool(strategy.get(experiment_flag_name))

        return resolve_learning_flag(flag_name, default, context, self.pipeline.config)

    def _resolve_experiment_sample_size(
        self,
        context: Dict[str, Any],
        evidence_profile: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
        gap_priority_summary: Dict[str, Any],
    ) -> int:
        explicit_value = context.get("sample_size")
        if explicit_value is not None:
            try:
                return max(12, min(int(explicit_value), 400))
            except (TypeError, ValueError):
                pass

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        strategy_sample_size = strategy.get("experiment_sample_size")
        if strategy_sample_size is not None:
            try:
                return max(12, min(int(strategy_sample_size), 400))
            except (TypeError, ValueError):
                pass

        base_sample_size = self._derive_experiment_sample_size(
            evidence_profile,
            selected_hypothesis,
            gap_priority_summary,
        )
        if not has_learning_strategy(context, self.pipeline.config):
            return base_sample_size

        multiplier = strategy.get("experiment_sample_size_multiplier")
        if multiplier is not None:
            try:
                normalized_multiplier = max(0.5, min(float(multiplier), 2.0))
            except (TypeError, ValueError):
                normalized_multiplier = 1.0
        else:
            quality_threshold = resolve_numeric_learning_parameter(
                "quality_threshold",
                0.7,
                context,
                self.pipeline.config,
                min_value=0.3,
                max_value=0.95,
            )
            confidence_threshold = resolve_numeric_learning_parameter(
                "confidence_threshold",
                0.7,
                context,
                self.pipeline.config,
                min_value=0.3,
                max_value=0.95,
            )
            normalized_multiplier = 1.0
            if quality_threshold >= 0.82:
                normalized_multiplier = 1.2
            elif quality_threshold >= 0.74:
                normalized_multiplier = 1.1
            elif quality_threshold <= 0.55:
                normalized_multiplier = 0.9
            if confidence_threshold >= 0.82:
                normalized_multiplier = max(normalized_multiplier, 1.15)

        adjusted = max(12, min(int(round(base_sample_size * normalized_multiplier)), 400))
        if hasattr(self, "_experiment_tracker"):
            self._experiment_tracker.record(
                "sample_size", base_sample_size, adjusted,
                f"multiplier={normalized_multiplier}",
            )
        return adjusted

    def _resolve_experiment_duration_days(
        self,
        context: Dict[str, Any],
        evidence_profile: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> int:
        explicit_value = context.get("duration_days")
        if explicit_value is not None:
            try:
                return max(7, min(int(explicit_value), 120))
            except (TypeError, ValueError):
                pass

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        strategy_duration_days = strategy.get("experiment_duration_days")
        if strategy_duration_days is not None:
            try:
                return max(7, min(int(strategy_duration_days), 120))
            except (TypeError, ValueError):
                pass

        duration_days = self._derive_experiment_duration(evidence_profile, selected_hypothesis)
        if not has_learning_strategy(context, self.pipeline.config):
            return duration_days

        extra_days = strategy.get("experiment_duration_adjustment_days")
        if extra_days is not None:
            try:
                normalized_extra_days = int(extra_days)
            except (TypeError, ValueError):
                normalized_extra_days = 0
        else:
            quality_threshold = resolve_numeric_learning_parameter(
                "quality_threshold",
                0.7,
                context,
                self.pipeline.config,
                min_value=0.3,
                max_value=0.95,
            )
            if quality_threshold >= 0.82:
                normalized_extra_days = 7
            elif quality_threshold >= 0.74:
                normalized_extra_days = 4
            elif quality_threshold <= 0.55:
                normalized_extra_days = -2
            else:
                normalized_extra_days = 0

        adjusted = max(7, min(duration_days + normalized_extra_days, 120))
        if hasattr(self, "_experiment_tracker"):
            self._experiment_tracker.record(
                "duration_days", duration_days, adjusted,
                f"extra_days={normalized_extra_days}",
            )
        return adjusted

    def _resolve_experiment_methodology(
        self,
        context: Dict[str, Any],
        evidence_profile: Dict[str, Any],
        source_weights: List[Dict[str, Any]],
        gap_priority_summary: Dict[str, Any],
    ) -> str:
        explicit_methodology = context.get("methodology")
        if explicit_methodology:
            return str(explicit_methodology)

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        strategy_methodology = strategy.get("experiment_methodology")
        if strategy_methodology:
            return str(strategy_methodology)

        methodology = self._derive_experiment_methodology(
            evidence_profile,
            source_weights,
            gap_priority_summary,
        )
        if not has_learning_strategy(context, self.pipeline.config):
            return methodology

        quality_threshold = resolve_numeric_learning_parameter(
            "quality_threshold",
            0.7,
            context,
            self.pipeline.config,
            min_value=0.3,
            max_value=0.95,
        )
        if methodology == "data_analysis" and int(evidence_profile.get("record_count") or 0) > 0:
            adjusted = "evidence_weighted_analysis"
        elif methodology == "evidence_weighted_analysis" and len(source_weights) >= 2 and quality_threshold >= 0.74:
            adjusted = "multisource_weighted_comparative_analysis"
        elif methodology == "multisource_weighted_comparative_analysis" and quality_threshold <= 0.55:
            adjusted = "evidence_weighted_analysis"
        else:
            adjusted = methodology
        if hasattr(self, "_experiment_tracker") and adjusted != methodology:
            self._experiment_tracker.record(
                "methodology", methodology, adjusted,
                f"quality_threshold={quality_threshold}",
                parameter="quality_threshold", parameter_value=quality_threshold,
            )
        return adjusted

    def _extract_gap_priority_summary(self, clinical_gap_analysis: Dict[str, Any]) -> Dict[str, Any]:
        summary = clinical_gap_analysis.get("priority_summary") or {}
        counts = summary.get("counts") or {}
        return {
            "counts": {
                "高": int(counts.get("高", 0)),
                "中": int(counts.get("中", 0)),
                "低": int(counts.get("低", 0)),
            },
            "highest_priority": str(summary.get("highest_priority") or "低"),
            "total_gaps": int(summary.get("total_gaps") or len(clinical_gap_analysis.get("gaps") or [])),
        }

    def _build_weighted_evidence_records(
        self,
        records: List[Dict[str, Any]],
        dimension_count: int,
    ) -> List[Dict[str, Any]]:
        normalized_dimension_count = max(1, dimension_count)
        weighted_records: List[Dict[str, Any]] = []
        for item in records:
            coverage_score = float(item.get("coverage_score") or 0.0)
            weighted_records.append(
                {
                    **item,
                    "evidence_weight": round(min(1.0, coverage_score / normalized_dimension_count), 4),
                }
            )
        return weighted_records

    def _build_source_weights(
        self,
        literature_pipeline: Dict[str, Any],
        evidence_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        source_stats = literature_pipeline.get("source_stats") or {}
        if source_stats:
            total = sum(int((stats or {}).get("count", 0)) for stats in source_stats.values()) or 1
            weights = []
            for source, stats in source_stats.items():
                count = int((stats or {}).get("count", 0))
                weights.append(
                    {
                        "source": source,
                        "label": (stats or {}).get("source_name") or source,
                        "count": count,
                        "weight": round(count / total, 4),
                        "mode": (stats or {}).get("mode", ""),
                    }
                )
            return sorted(weights, key=lambda item: item.get("weight", 0.0), reverse=True)

        counts = Counter(str(item.get("source") or "unknown") for item in evidence_records if item.get("source"))
        total = sum(counts.values()) or 1
        return [
            {
                "source": source,
                "label": source,
                "count": count,
                "weight": round(count / total, 4),
                "mode": "derived",
            }
            for source, count in counts.most_common()
        ]

    def _build_evidence_profile(
        self,
        evidence_matrix: Dict[str, Any],
        weighted_records: List[Dict[str, Any]],
        source_weights: List[Dict[str, Any]],
        literature_pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:
        dimension_count = int(evidence_matrix.get("dimension_count") or 0)
        coverage_scores = [float(item.get("coverage_score") or 0.0) for item in weighted_records]
        average_coverage = round(sum(coverage_scores) / len(coverage_scores), 4) if coverage_scores else 0.0
        weighted_evidence_score = 0.0
        if dimension_count > 0:
            weighted_evidence_score = round(
                sum(float(item.get("evidence_weight") or 0.0) for item in weighted_records) / max(1, len(weighted_records)),
                4,
            )
        source_balance = 0.0
        if source_weights:
            source_balance = round(min(item.get("weight", 0.0) for item in source_weights) * len(source_weights), 4)
        clinical_gap = literature_pipeline.get("clinical_gap_analysis") or {}
        gap_priority_summary = self._extract_gap_priority_summary(clinical_gap)
        return {
            "record_count": int(evidence_matrix.get("record_count") or len(evidence_matrix.get("records") or [])),
            "dimension_count": dimension_count,
            "dimension_hit_counts": evidence_matrix.get("dimension_hit_counts") or {},
            "average_coverage": average_coverage,
            "weighted_evidence_score": weighted_evidence_score,
            "source_count": len(source_weights),
            "source_balance": source_balance,
            "clinical_gap_available": bool(clinical_gap.get("report")),
            "gap_total": int(gap_priority_summary.get("total_gaps", 0)),
            "gap_high_count": int((gap_priority_summary.get("counts") or {}).get("高", 0)),
            "gap_medium_count": int((gap_priority_summary.get("counts") or {}).get("中", 0)),
            "gap_low_count": int((gap_priority_summary.get("counts") or {}).get("低", 0)),
            "highest_gap_priority": str(gap_priority_summary.get("highest_priority") or "低"),
        }

    def _build_experiment_data_sources(
        self,
        source_weights: List[Dict[str, Any]],
        evidence_records: List[Dict[str, Any]],
    ) -> List[str]:
        sources = [str(item.get("label") or item.get("source") or "").strip() for item in source_weights]
        sources = [item for item in sources if item]
        if sources:
            return sources

        derived_sources = []
        for item in evidence_records[:3]:
            source = str(item.get("source") or "").strip()
            if source and source not in derived_sources:
                derived_sources.append(source)
        return derived_sources or ["古籍文本", "现代数据库", "专家知识"]

    def _derive_experiment_sample_size(
        self,
        evidence_profile: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
        gap_priority_summary: Dict[str, Any],
    ) -> int:
        record_count = int(evidence_profile.get("record_count") or 0)
        dimension_count = int(evidence_profile.get("dimension_count") or 0)
        weighted_score = float(evidence_profile.get("weighted_evidence_score") or 0.0)
        contradiction_count = len(selected_hypothesis.get("contradiction_signals") or [])
        gap_counts = gap_priority_summary.get("counts") or {}
        high_gap_count = int(gap_counts.get("高", 0))
        medium_gap_count = int(gap_counts.get("中", 0))
        highest_gap_priority = str(gap_priority_summary.get("highest_priority") or "低")
        sample_size = 36 + record_count * 8 + dimension_count * 6 + int(weighted_score * 40) + contradiction_count * 5
        sample_size += high_gap_count * 18 + medium_gap_count * 8
        if highest_gap_priority == "高":
            sample_size += 16
        return max(36, min(sample_size, 240))

    def _derive_experiment_duration(
        self,
        evidence_profile: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> int:
        duration = 14 + int(evidence_profile.get("dimension_count") or 0) * 3 + int(evidence_profile.get("record_count") or 0)
        if selected_hypothesis.get("contradiction_signals"):
            duration += 4
        if evidence_profile.get("clinical_gap_available"):
            duration += 5
        return max(14, min(duration, 90))

    def _derive_experiment_methodology(
        self,
        evidence_profile: Dict[str, Any],
        source_weights: List[Dict[str, Any]],
        gap_priority_summary: Dict[str, Any],
    ) -> str:
        highest_gap_priority = str(gap_priority_summary.get("highest_priority") or "低")
        if evidence_profile.get("clinical_gap_available") and highest_gap_priority == "高":
            return "high_priority_gap_escalated_validation"
        if evidence_profile.get("clinical_gap_available"):
            return "gap_informed_evidence_weighted_analysis"
        if len(source_weights) >= 2 and float(evidence_profile.get("weighted_evidence_score") or 0.0) >= 0.5:
            return "multisource_weighted_comparative_analysis"
        if int(evidence_profile.get("record_count") or 0) > 0:
            return "evidence_weighted_analysis"
        return "data_analysis"

    def _convert_to_research_hypothesis(
        self,
        hypothesis: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> Any:
        if ResearchHypothesis is None or ResearchDomain is None or HypothesisStatus is None:
            raise RuntimeError("ResearchHypothesis 不可用，无法构建实验输入")

        domain_value = str(hypothesis.get("domain") or "integrative_research").strip() or "integrative_research"
        try:
            domain = ResearchDomain(domain_value)
        except Exception:
            domain = ResearchDomain.INTEGRATIVE_RESEARCH

        status_value = str(hypothesis.get("status") or "draft").strip().lower()
        try:
            status = HypothesisStatus(status_value)
        except Exception:
            status = HypothesisStatus.ACTIVE

        return ResearchHypothesis(
            hypothesis_id=str(hypothesis.get("hypothesis_id") or ""),
            title=str(hypothesis.get("title") or hypothesis.get("statement") or "研究假设"),
            description=str(hypothesis.get("statement") or hypothesis.get("description") or ""),
            research_domain=domain,
            status=status,
            confidence=float(hypothesis.get("confidence") or hypothesis.get("final_score") or 0.0),
            complexity=int(float(hypothesis.get("final_score") or 0.0) * 100),
            testability=float((hypothesis.get("scores") or {}).get("testability", 0.0)),
            research_objective=cycle.research_objective,
            expected_outcome=str(hypothesis.get("rationale") or ""),
            validation_method=str(hypothesis.get("validation_plan") or ""),
            relevance_to_tcm=float((hypothesis.get("scores") or {}).get("relevance", 0.0)),
            novelty_score=float((hypothesis.get("scores") or {}).get("novelty", 0.0)),
            practical_value=float((hypothesis.get("scores") or {}).get("feasibility", 0.0)),
            supporting_evidence=[{"signal": item} for item in (hypothesis.get("supporting_signals") or [])],
            contradicting_evidence=[{"signal": item} for item in (hypothesis.get("contradiction_signals") or [])],
            tags=[str(hypothesis.get("domain") or domain.value)],
            keywords=[str(item) for item in (hypothesis.get("keywords") or []) if str(item).strip()],
        )
