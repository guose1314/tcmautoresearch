from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

import os
from datetime import datetime

try:
    from src.generation.citation_manager import CitationManager
except Exception:
    CitationManager = None

try:
    from src.generation.paper_writer import PaperWriter
except Exception:
    PaperWriter = None

try:
    from src.generation.llm_context_adapter import (
        DEFAULT_LLM_ANALYSIS_MODULE_ALIASES,
        wrap_paper_writer_with_llm_context,
    )
except Exception:
    DEFAULT_LLM_ANALYSIS_MODULE_ALIASES = {}
    wrap_paper_writer_with_llm_context = None

try:
    from src.generation.output_formatter import OutputGenerator
except Exception:
    OutputGenerator = None

try:
    from src.generation.report_generator import ReportGenerator
except Exception:
    ReportGenerator = None

try:
    from src.quality import EvidenceGrader
except Exception:
    EvidenceGrader = None

from src.research.evidence_contract import (
    build_citation_records_from_evidence_protocol,
    build_evidence_protocol,
)
from src.research.learning_strategy import (
    StrategyApplicationTracker,
    has_learning_strategy,
    resolve_learning_flag,
    resolve_learning_strategy,
    resolve_numeric_learning_parameter,
)
from src.research.phase_result import (
    build_phase_result,
    get_phase_results,
    get_phase_value,
    is_phase_result_payload,
)

_PUBLISH_LLM_ANALYSIS_MODULE_ALIASES: Dict[str, tuple[str, ...]] = (
    dict(DEFAULT_LLM_ANALYSIS_MODULE_ALIASES)
    if DEFAULT_LLM_ANALYSIS_MODULE_ALIASES
    else {
        "research_perspectives": ("research_perspectives",),
        "formula_comparisons": ("formula_comparisons",),
        "herb_properties_analysis": ("herb_properties_analysis", "herb_properties"),
        "pharmacology_integration": ("pharmacology_integration",),
        "network_pharmacology": ("network_pharmacology", "network_pharmacology_systems_biology"),
        "supramolecular_physicochemistry": ("supramolecular_physicochemistry",),
        "knowledge_archaeology": ("knowledge_archaeology",),
        "complexity_dynamics": ("complexity_dynamics", "complexity_nonlinear_dynamics"),
        "research_scoring_panel": ("research_scoring_panel",),
        "summary_analysis": ("summary_analysis",),
    }
)

_REMOVED_PUBLISH_ANALYSIS_ALIAS_FIELDS: tuple[str, ...] = (
    "primary_association",
    "data_mining_summary",
    "data_mining_methods",
)

_REMOVED_PUBLISH_DATA_MINING_ALIAS_FIELDS: tuple[str, ...] = (
    "frequent_itemsets",
    "association_rules",
    "clustering",
    "latent_topics",
    "frequency_chi_square",
    "predictive_modeling",
)


class PublishPhaseMixin:
    """Mixin: publish 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_publish_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        self._publish_tracker = StrategyApplicationTracker("publish", context, self.pipeline.config)
        observe_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {}).get("result", {})
        hypothesis_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.HYPOTHESIS, {}).get("result", {})
        experiment_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.EXPERIMENT, {}).get("result", {})
        experiment_execution_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.EXPERIMENT_EXECUTION, {}).get("result", {})
        analyze_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.ANALYZE, {}).get("result", {})
        literature_pipeline = get_phase_value(observe_result, "literature_pipeline", {}) or {}
        citation_records = self._collect_citation_records(cycle, context, literature_pipeline)
        generate_paper = self._resolve_publish_flag(context, "generate_paper", True)
        generate_reports = self._resolve_publish_flag(context, "generate_reports", True)

        citation_manager = self._create_citation_manager()
        citation_result = self._execute_citation_manager(citation_manager, citation_records)

        paper_context = self._build_publish_paper_context(
            cycle,
            context,
            observe_result,
            hypothesis_result,
            experiment_result,
            analyze_result,
            literature_pipeline,
            citation_records,
            citation_result,
        )
        if generate_paper:
            paper_writer = self._create_paper_writer()
            paper_result = self._execute_paper_writer(paper_writer, paper_context)
        else:
            paper_result = {}
        paper_output_files = paper_result.get("output_files") if isinstance(paper_result, dict) else {}
        citation_output_files = citation_result.get("output_files")
        merged_output_files = self._merge_publish_output_files(
            paper_output_files if isinstance(paper_output_files, dict) else {},
            citation_output_files if isinstance(citation_output_files, dict) else {},
        )
        report_session_payload = self._build_publish_report_session_payload(
            cycle,
            context,
            observe_result,
            hypothesis_result,
            experiment_result,
            experiment_execution_result,
            analyze_result,
            paper_context,
            paper_result if isinstance(paper_result, dict) else {},
            citation_result,
            merged_output_files,
        )
        if generate_reports:
            report_generation_result = self._generate_publish_reports(report_session_payload, context)
        else:
            report_generation_result = {"reports": {}, "output_files": {}, "errors": []}
        report_output_files = report_generation_result.get("output_files") if isinstance(report_generation_result, dict) else {}
        merged_output_files = self._merge_publish_output_files(
            merged_output_files,
            report_output_files if isinstance(report_output_files, dict) else {},
        )

        publications = (
            self._build_publications_from_paper_result(
                cycle,
                context,
                paper_context,
                paper_result if isinstance(paper_result, dict) else {},
            )
            if generate_paper
            else []
        )

        deliverables = [
            "研究报告",
            "数据集",
            "分析工具包",
            "可视化图表",
        ]
        if citation_result.get("bibtex"):
            deliverables.append("BibTeX 参考文献")
        if citation_result.get("gbt7714"):
            deliverables.append("GB/T 7714 参考文献")
        if merged_output_files.get("markdown"):
            deliverables.append("Markdown 论文初稿")
        if merged_output_files.get("docx"):
            deliverables.append("DOCX 论文初稿")
        if merged_output_files.get("imrd_markdown"):
            deliverables.append("Markdown IMRD 报告")
        if merged_output_files.get("imrd_docx"):
            deliverables.append("DOCX IMRD 报告")

        cycle.metadata.setdefault("phase_dossier_sources", {})["publish"] = {
            "paper_draft": copy.deepcopy(paper_result.get("paper_draft", {})) if isinstance(paper_result, dict) else {},
            "paper_review_summary": copy.deepcopy(paper_result.get("review_summary", {})) if isinstance(paper_result, dict) else {},
        }

        metadata = {
            "publication_count": len(publications),
            "deliverable_count": len(deliverables),
            "citation_count": citation_result.get("citation_count", 0),
            "paper_section_count": paper_result.get("section_count", 0) if isinstance(paper_result, dict) else 0,
            "paper_reference_count": paper_result.get("reference_count", 0) if isinstance(paper_result, dict) else 0,
            "paper_review_summary": copy.deepcopy(paper_result.get("review_summary", {})) if isinstance(paper_result, dict) and isinstance(paper_result.get("review_summary"), dict) else {},
            "report_count": len(report_generation_result.get("reports", {})) if isinstance(report_generation_result, dict) else 0,
            "report_error_count": len(report_generation_result.get("errors", [])) if isinstance(report_generation_result, dict) else 0,
            "learning_strategy_applied": has_learning_strategy(context, self.pipeline.config),
            "paper_generation_enabled": generate_paper,
            "report_generation_enabled": generate_reports,
        }
        if hasattr(self, "_publish_tracker"):
            metadata["learning"] = self._publish_tracker.to_metadata()
            self.pipeline.register_phase_learning_manifest(
                {"phase": "publish", **self._publish_tracker.to_metadata()}
            )
        report_errors = report_generation_result.get("errors", []) if isinstance(report_generation_result, dict) else []
        status = "degraded" if report_errors else "completed"
        return build_phase_result(
            "publish",
            status=status,
            results={
                "publications": publications,
                "deliverables": deliverables,
                "citations": citation_result.get("entries", []),
                "bibtex": citation_result.get("bibtex", ""),
                "gbt7714": citation_result.get("gbt7714", ""),
                "formatted_references": citation_result.get("formatted_references", ""),
                "output_files": merged_output_files,
                "analysis_results": paper_context.get("analysis_results", {}),
                "research_artifact": paper_context.get("research_artifact", {}),
            },
            artifacts=merged_output_files,
            metadata=metadata,
        )

    def collect_citation_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self._collect_citation_records(cycle, context, literature_pipeline)

    def _collect_citation_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        context_records = context.get("citation_records")
        if isinstance(context_records, list):
            return [dict(item) for item in context_records if isinstance(item, dict)]

        literature_records = literature_pipeline.get("records")
        if isinstance(literature_records, list) and literature_records:
            return [dict(item) for item in literature_records if isinstance(item, dict)]

        protocol_citations = self._collect_citation_records_from_evidence_protocol(cycle, context)
        if protocol_citations:
            return protocol_citations

        corpus_records = self._collect_citation_records_from_observe_corpus(cycle, context)
        if corpus_records:
            return corpus_records

        if not self._should_allow_pipeline_citation_fallback(context):
            return []

        return self._build_pipeline_outcome_citation_records(cycle)

    def _collect_citation_records_from_evidence_protocol(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        analyze_execution = cycle.phase_executions.get(self.pipeline.ResearchPhase.ANALYZE, {})
        analyze_result = analyze_execution.get("result") if isinstance(analyze_execution, dict) else {}
        analyze_results = get_phase_results(analyze_result) if isinstance(analyze_result, dict) else {}
        reasoning_results = self._resolve_publish_context_reasoning_results(context)
        if not reasoning_results and isinstance(analyze_results, dict):
            nested_reasoning = analyze_results.get("reasoning_results")
            if isinstance(nested_reasoning, dict):
                reasoning_results = nested_reasoning

        evidence_protocol = self._resolve_publish_evidence_protocol(
            context,
            analyze_result if isinstance(analyze_result, dict) else {},
            analyze_results if isinstance(analyze_results, dict) else {},
            reasoning_results if isinstance(reasoning_results, dict) else {},
        )
        return [
            dict(item)
            for item in build_citation_records_from_evidence_protocol(evidence_protocol)
            if isinstance(item, dict)
        ]

    def _collect_citation_records_from_observe_corpus(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        observe_execution = cycle.phase_executions.get(self.pipeline.ResearchPhase.OBSERVE, {})
        observe_result = observe_execution.get("result") if isinstance(observe_execution, dict) else {}
        if not isinstance(observe_result, dict):
            return []

        corpus_result = get_phase_value(observe_result, "corpus_collection")
        if not isinstance(corpus_result, dict) or corpus_result.get("error"):
            return []

        try:
            text_entries = self.pipeline._extract_corpus_text_entries(corpus_result)
        except Exception:
            return []

        if not isinstance(text_entries, list) or not text_entries:
            return []

        raw_max_records = self._resolve_publish_max_local_citation_records(context)
        try:
            max_records = max(1, min(int(raw_max_records), 200))
        except (TypeError, ValueError):
            max_records = 20

        authors = [
            str(author).strip()
            for author in (cycle.researchers or [])
            if str(author).strip()
        ] or ["中医古籍研究团队"]
        context_authors = context.get("citation_authors")
        if isinstance(context_authors, list):
            normalized_context_authors = [
                str(author).strip() for author in context_authors if str(author).strip()
            ]
            if normalized_context_authors:
                authors = normalized_context_authors

        citation_year = context.get("citation_year", datetime.now().year)
        local_journal = str(context.get("local_citation_journal") or "本地古籍语料库").strip()
        ctext_journal = str(context.get("ctext_citation_journal") or "ctext 标准语料库").strip()
        local_publisher = str(context.get("local_citation_publisher") or "中医古籍语料数据集").strip()

        citations: List[Dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        for entry in text_entries:
            if not isinstance(entry, dict):
                continue

            source_ref = str(entry.get("urn") or "").strip()
            source_type = str(entry.get("source_type") or "local").strip().lower()
            title = str(entry.get("title") or "").strip()
            if not title and source_ref:
                title = os.path.splitext(os.path.basename(source_ref))[0].strip()
            if not title:
                continue

            dedupe_key = (title, source_ref)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            journal = ctext_journal if source_type == "ctext" else local_journal
            note_segments = ["evidence_type=corpus_document"]
            if source_ref:
                note_segments.insert(0, f"source_ref={source_ref}")

            citations.append(
                {
                    "title": title,
                    "authors": authors,
                    "year": citation_year,
                    "journal": journal,
                    "publisher": local_publisher,
                    "entry_type": "book",
                    "source": f"{source_type}_corpus" if source_type else "corpus",
                    "source_type": source_type,
                    "source_ref": source_ref,
                    "note": "; ".join(note_segments),
                }
            )

            if len(citations) >= max_records:
                break

        return citations

    def _resolve_publish_flag(
        self,
        context: Dict[str, Any],
        flag_name: str,
        default: bool,
    ) -> bool:
        if flag_name in context:
            return bool(context.get(flag_name))

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        publish_flag_name = f"publish_{flag_name}"
        if publish_flag_name in strategy:
            return bool(strategy.get(publish_flag_name))

        return resolve_learning_flag(flag_name, default, context, self.pipeline.config)

    def _resolve_publish_max_local_citation_records(
        self,
        context: Dict[str, Any],
    ) -> int:
        explicit_max_records = context.get("max_local_citation_records")
        if explicit_max_records is not None:
            return explicit_max_records

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        strategy_max_records = strategy.get("publish_max_local_citation_records")
        if strategy_max_records is not None:
            return strategy_max_records

        if not has_learning_strategy(context, self.pipeline.config):
            return 20

        quality_threshold = resolve_numeric_learning_parameter(
            "quality_threshold",
            0.7,
            context,
            self.pipeline.config,
            min_value=0.3,
            max_value=0.95,
        )
        if quality_threshold >= 0.82:
            adjusted = 32
            reason = "quality_threshold >= 0.82"
        elif quality_threshold >= 0.74:
            adjusted = 24
            reason = "quality_threshold >= 0.74"
        elif quality_threshold <= 0.55:
            adjusted = 12
            reason = "quality_threshold <= 0.55"
        else:
            adjusted = 20
            reason = "no_adjustment"
        if hasattr(self, "_publish_tracker"):
            self._publish_tracker.record(
                "max_local_citation_records", 20, adjusted, reason,
                parameter="quality_threshold", parameter_value=quality_threshold,
            )
        return adjusted

    def _should_allow_pipeline_citation_fallback(self, context: Dict[str, Any]) -> bool:
        if "allow_pipeline_citation_fallback" in context:
            return bool(context.get("allow_pipeline_citation_fallback"))

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        if "publish_allow_pipeline_citation_fallback" in strategy:
            return bool(strategy.get("publish_allow_pipeline_citation_fallback"))
        if "allow_pipeline_citation_fallback" in strategy:
            return bool(strategy.get("allow_pipeline_citation_fallback"))

        publish_config = self.pipeline.config.get("publish", {})
        return bool(publish_config.get("allow_pipeline_citation_fallback", True))

    def _build_pipeline_outcome_citation_records(self, cycle: "ResearchCycle") -> List[Dict[str, Any]]:
        publications = [
            {
                "title": outcome.get("result", {}).get("title", "") or outcome.get("result", {}).get("phase", ""),
                "authors": cycle.researchers,
                "year": datetime.now().year,
                "journal": "中医古籍全自动研究系统",
                "source": "pipeline",
                "note": outcome.get("phase", ""),
            }
            for outcome in cycle.outcomes
            if isinstance(outcome, dict) and isinstance(outcome.get("result"), dict)
        ]
        return [item for item in publications if item.get("title")]

    def _create_citation_manager(self) -> Any:
        try:
            return self.pipeline.output_port.create_citation_manager(self.pipeline.config.get("citation_management") or {})
        except Exception:
            citation_manager_cls = CitationManager or self.pipeline.CitationManager
            if citation_manager_cls is None:
                raise RuntimeError("CitationManager 不可用")
            return citation_manager_cls(self.pipeline.config.get("citation_management") or {})

    def _execute_citation_manager(
        self,
        citation_manager: Any,
        citation_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        citation_manager.initialize()
        try:
            return citation_manager.execute({"records": citation_records})
        finally:
            citation_manager.cleanup()

    def _create_paper_writer(self) -> Any:
        paper_config = dict(self.pipeline.config.get("paper_writing") or {})
        try:
            paper_writer = self.pipeline.output_port.create_paper_writer(paper_config)
        except Exception:
            paper_writer_cls = PaperWriter or getattr(self.pipeline, "PaperWriter", None)
            if paper_writer_cls is None:
                raise RuntimeError("PaperWriter 不可用")
            paper_writer = paper_writer_cls(paper_config)

        if not callable(wrap_paper_writer_with_llm_context):
            return paper_writer
        return wrap_paper_writer_with_llm_context(
            paper_writer,
            module_aliases=_PUBLISH_LLM_ANALYSIS_MODULE_ALIASES,
        )

    def _create_output_generator(self) -> Any:
        output_config = dict(
            self.pipeline.config.get("structured_output")
            or self.pipeline.config.get("output_generation")
            or {}
        )
        try:
            return self.pipeline.output_port.create_output_generator(output_config)
        except Exception:
            output_generator_cls = OutputGenerator or getattr(self.pipeline, "OutputGenerator", None)
            if output_generator_cls is None:
                raise RuntimeError("OutputGenerator 不可用")
            return output_generator_cls(output_config)

    def _create_report_generator(self, context: Dict[str, Any] | None=None) -> Any:
        report_context = context or {}
        report_config = dict(self.pipeline.config.get("report_generation") or {})
        if report_context.get("report_output_dir"):
            report_config["output_dir"] = report_context.get("report_output_dir")
        if report_context.get("report_output_formats"):
            report_config["output_formats"] = report_context.get("report_output_formats")
        try:
            return self.pipeline.output_port.create_report_generator(report_config)
        except Exception:
            report_generator_cls = ReportGenerator or getattr(self.pipeline, "ReportGenerator", None)
            if report_generator_cls is None:
                raise RuntimeError("ReportGenerator 不可用")
            return report_generator_cls(report_config)

    def _create_evidence_grader(self) -> Any:
        grader_config = dict(self.pipeline.config.get("evidence_grading") or {})
        if EvidenceGrader is None:
            raise RuntimeError("EvidenceGrader 不可用")
        return EvidenceGrader(grader_config)

    def _build_publish_paper_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        observe_result: Dict[str, Any],
        hypothesis_result: Dict[str, Any],
        experiment_result: Dict[str, Any],
        analyze_result: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
        citation_records: List[Dict[str, Any]],
        citation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        hypothesis_candidates = get_phase_value(hypothesis_result, "hypotheses", []) or []
        selected_hypothesis = self._resolve_publish_selected_hypothesis(
            hypothesis_result,
            experiment_result,
            hypothesis_candidates,
        )

        ingestion_pipeline = get_phase_value(observe_result, "ingestion_pipeline", {}) or {}

        publish_hypotheses = self._build_publish_hypothesis_entries(
            hypothesis_result,
            ingestion_pipeline,
            context,
            selected_hypothesis,
        )
        if publish_hypotheses:
            selected_hypothesis_id = str(selected_hypothesis.get("hypothesis_id") or "").strip()
            matched_selected = next(
                (
                    item
                    for item in publish_hypotheses
                    if str(item.get("hypothesis_id") or "").strip() == selected_hypothesis_id
                ),
                None,
            )
            if matched_selected is not None:
                selected_hypothesis = matched_selected
            elif not selected_hypothesis:
                selected_hypothesis = publish_hypotheses[0]
        hypothesis_audit_summary = self._build_publish_hypothesis_audit_summary(
            publish_hypotheses,
            self._extract_hypothesis_reasoning_summary(ingestion_pipeline, context),
        )

        experiment_context = (
            self._build_experiment_context(cycle, context, selected_hypothesis)
            if selected_hypothesis
            else {}
        )
        analyze_results = get_phase_results(analyze_result)
        statistical_analysis = self._resolve_publish_statistical_analysis(context, analyze_result, analyze_results)
        observe_entities = self._extract_publish_entities(observe_result, context)
        reasoning_results = self._build_publish_reasoning_results(
            context,
            experiment_context,
            experiment_result,
            analyze_result,
            analyze_results,
        )
        data_mining_result = self._resolve_publish_data_mining_result(context, analyze_result, analyze_results)
        data_mining_aliases = self._build_publish_data_mining_aliases(data_mining_result)
        research_perspectives = self._resolve_publish_research_perspectives(context, analyze_result, analyze_results)
        publish_output_context = self._build_publish_output_context(
            cycle,
            context,
            observe_entities,
            {**hypothesis_result, "hypotheses": publish_hypotheses},
            selected_hypothesis,
            hypothesis_audit_summary,
            analyze_result,
            analyze_results,
            reasoning_results,
            data_mining_result,
            research_perspectives,
        )
        structured_output = (
            self._execute_publish_output_generator(publish_output_context)
            if self._resolve_publish_flag(context, "generate_structured_output", True)
            else {}
        )
        structured_payload_raw = structured_output.get("output_data") if isinstance(structured_output, dict) else {}
        structured_payload = structured_payload_raw if isinstance(structured_payload_raw, dict) else {}
        research_artifact = structured_payload.get("research_artifact") if isinstance(structured_payload, dict) else {}
        if not isinstance(research_artifact, dict):
            research_artifact = {}
        similar_formula_graph_evidence_summary = self._resolve_publish_similar_formula_graph_evidence_summary(
            context,
            analyze_result,
            analyze_results,
            research_artifact,
        )
        evidence_grade_summary = self._resolve_publish_evidence_grade_summary(
            context,
            analyze_result,
            analyze_results,
            research_artifact,
        )
        evidence_protocol = self._resolve_publish_evidence_protocol(
            context,
            analyze_result,
            analyze_results,
            reasoning_results,
        )
        if not research_artifact:
            research_artifact = {
                "hypothesis": publish_hypotheses or ([selected_hypothesis] if selected_hypothesis else []),
                "hypothesis_audit_summary": hypothesis_audit_summary,
                "evidence_grade_summary": evidence_grade_summary,
                "evidence": list(evidence_protocol.get("evidence_records") or reasoning_results.get("evidence_records") or []),
                "data_mining_result": data_mining_result,
                "similar_formula_graph_evidence_summary": similar_formula_graph_evidence_summary,
            }
        elif evidence_grade_summary:
            existing_evidence_grade_summary = research_artifact.get("evidence_grade_summary")
            if not isinstance(existing_evidence_grade_summary, dict) or not existing_evidence_grade_summary:
                research_artifact["evidence_grade_summary"] = evidence_grade_summary
        if evidence_protocol:
            existing_evidence = research_artifact.get("evidence")
            if not isinstance(existing_evidence, list) or not existing_evidence:
                research_artifact["evidence"] = list(evidence_protocol.get("evidence_records") or [])
        research_artifact = self._enrich_publish_research_artifact(
            research_artifact,
            statistical_analysis,
            data_mining_result,
            data_mining_aliases,
            similar_formula_graph_evidence_summary,
        )
        llm_analysis_context = self._build_publish_llm_analysis_context(
            context,
            analyze_result,
            analyze_results,
            structured_payload,
            research_artifact,
            research_perspectives,
        )
        analysis_results_payload = self._compose_publish_analysis_results(
            structured_payload,
            analyze_result,
            statistical_analysis,
            experiment_result,
            reasoning_results,
            data_mining_result,
            data_mining_aliases,
            research_perspectives,
            evidence_protocol,
            similar_formula_graph_evidence_summary,
            llm_analysis_context,
        )
        output_dir = context.get("paper_output_dir") or context.get("output_dir") or os.path.join("output", "papers", cycle.cycle_id)
        output_formats = context.get("paper_output_formats") or context.get("output_formats") or ["markdown", "docx"]
        title = str(
            context.get("paper_title")
            or context.get("title")
            or f"{cycle.research_objective or cycle.description}研究"
        ).strip()
        phase_dossiers = context.get("phase_dossiers") if isinstance(context.get("phase_dossiers"), dict) else {}
        observe_dossier = context.get("observe_dossier") if isinstance(context.get("observe_dossier"), dict) else phase_dossiers.get("observe", {})
        analyze_dossier = context.get("analyze_dossier") if isinstance(context.get("analyze_dossier"), dict) else phase_dossiers.get("analyze", {})
        phase_dossier_texts = context.get("phase_dossier_texts") if isinstance(context.get("phase_dossier_texts"), dict) else {}

        paper_context = {
            "title": title,
            "authors": context.get("authors") or cycle.researchers,
            "author": context.get("author") or ", ".join(cycle.researchers),
            "affiliation": context.get("affiliation") or "",
            "journal": context.get("journal") or "",
            "objective": cycle.research_objective or context.get("objective") or cycle.description,
            "research_domain": context.get("research_domain") or selected_hypothesis.get("domain") or "中医古籍研究",
            "keywords": context.get("keywords") or selected_hypothesis.get("keywords") or [],
            "entities": observe_entities,
            "hypotheses": publish_hypotheses or ([selected_hypothesis] if selected_hypothesis else []),
            "hypothesis": selected_hypothesis,
            "hypothesis_audit_summary": hypothesis_audit_summary,
            "evidence_grade_summary": evidence_grade_summary,
            "reasoning_results": reasoning_results,
            "data_mining_result": data_mining_result,
            "similar_formula_graph_evidence_summary": similar_formula_graph_evidence_summary,
            "literature_pipeline": literature_pipeline,
            "citation_records": citation_records,
            "formatted_references": citation_result.get("formatted_references") or citation_result.get("gbt7714") or "",
            "limitations": self._resolve_publish_limitations(context, analyze_results, analysis_results_payload),
            "gap_analysis": experiment_context.get("clinical_gap_analysis") or {},
            "analysis_results": analysis_results_payload,
            "research_artifact": research_artifact,
            "llm_analysis_context": llm_analysis_context,
            "phase_dossiers": phase_dossiers,
            "phase_dossier_texts": phase_dossier_texts,
            "observe_dossier": observe_dossier,
            "analyze_dossier": analyze_dossier,
            "observe_dossier_text": context.get("observe_dossier_text") or phase_dossier_texts.get("observe") or "",
            "analyze_dossier_text": context.get("analyze_dossier_text") or phase_dossier_texts.get("analyze") or "",
            "output_data": structured_payload,
            "quality_metrics": structured_payload.get("quality_metrics") if isinstance(structured_payload, dict) else {},
            "recommendations": structured_payload.get("recommendations") if isinstance(structured_payload, dict) else [],
            "research_perspectives": research_perspectives,
            "output_dir": output_dir,
            "output_formats": output_formats,
            "file_stem": context.get("paper_file_stem") or cycle.cycle_name or cycle.cycle_id,
        }
        paper_context.update(self._resolve_publish_paper_iteration_settings(context))
        if isinstance(context.get("figure_paths"), list):
            paper_context["figure_paths"] = context.get("figure_paths")
        return paper_context

    def _resolve_publish_selected_hypothesis(
        self,
        hypothesis_result: Dict[str, Any],
        experiment_result: Dict[str, Any],
        hypothesis_candidates: Any,
    ) -> Dict[str, Any]:
        experiment_results = get_phase_results(experiment_result)
        selected_hypothesis = experiment_results.get("selected_hypothesis")
        if isinstance(selected_hypothesis, dict) and selected_hypothesis:
            return selected_hypothesis

        selected_hypothesis_id = ""
        for source in (experiment_result, hypothesis_result):
            if not isinstance(source, dict):
                continue
            metadata = source.get("metadata")
            if not isinstance(metadata, dict):
                continue
            candidate_id = str(metadata.get("selected_hypothesis_id") or "").strip()
            if candidate_id:
                selected_hypothesis_id = candidate_id
                break

        if isinstance(hypothesis_candidates, list):
            if selected_hypothesis_id:
                matched_hypothesis = next(
                    (
                        item
                        for item in hypothesis_candidates
                        if isinstance(item, dict)
                        and str(item.get("hypothesis_id") or "").strip() == selected_hypothesis_id
                    ),
                    None,
                )
                if matched_hypothesis is not None:
                    return matched_hypothesis

            first_hypothesis = next((item for item in hypothesis_candidates if isinstance(item, dict)), None)
            if first_hypothesis is not None:
                return first_hypothesis

        return {}

    def _build_publish_report_session_payload(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        observe_result: Dict[str, Any],
        hypothesis_result: Dict[str, Any],
        experiment_result: Dict[str, Any],
        experiment_execution_result: Dict[str, Any],
        analyze_result: Dict[str, Any],
        paper_context: Dict[str, Any],
        paper_result: Dict[str, Any],
        citation_result: Dict[str, Any],
        merged_output_files: Dict[str, Any],
    ) -> Dict[str, Any]:
        reflect_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.REFLECT, {}).get("result", {})
        publish_payload = {
            "paper_draft": paper_result.get("paper_draft", {}),
            "paper_language": paper_result.get("language", ""),
            "formatted_references": citation_result.get("formatted_references", ""),
            "citations": citation_result.get("entries", []),
            "research_artifact": paper_context.get("research_artifact", {}),
            "analysis_results": paper_context.get("analysis_results", {}),
            "output_files": merged_output_files,
        }
        phase_results = {
            "observe": self._normalize_report_phase_result("observe", observe_result),
            "hypothesis": self._normalize_report_phase_result("hypothesis", hypothesis_result),
            "experiment": self._normalize_report_phase_result("experiment", experiment_result),
            "experiment_execution": self._normalize_report_phase_result("experiment_execution", experiment_execution_result),
            "analyze": self._normalize_report_phase_result("analyze", analyze_result),
            "publish": self._normalize_report_phase_result("publish", publish_payload),
        }
        if isinstance(reflect_result, dict) and reflect_result:
            phase_results["reflect"] = self._normalize_report_phase_result("reflect", reflect_result)

        return {
            "session_id": cycle.cycle_id,
            "title": str(paper_context.get("title") or cycle.research_objective or cycle.description or "中医科研 IMRD 报告").strip(),
            "question": cycle.research_objective or context.get("question") or cycle.description,
            "research_question": cycle.research_objective or context.get("question") or cycle.description,
            "metadata": {
                "title": str(paper_context.get("title") or cycle.research_objective or cycle.description or "中医科研 IMRD 报告").strip(),
                "research_question": cycle.research_objective or context.get("question") or cycle.description,
                "cycle_name": cycle.cycle_name,
                "research_scope": cycle.research_scope,
                "researchers": cycle.researchers,
                "generated_by": "publish_phase",
            },
            "phase_results": phase_results,
        }

    def _normalize_report_phase_result(self, phase_name: str, phase_result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(phase_result) if isinstance(phase_result, dict) else {}
        nested_results = normalized.get("results")
        if isinstance(nested_results, dict):
            for key, value in nested_results.items():
                normalized.setdefault(key, value)

        if phase_name == "experiment" and "study_protocol" not in normalized:
            experiments = normalized.get("experiments")
            if isinstance(experiments, list) and experiments and isinstance(experiments[0], dict):
                normalized["study_protocol"] = experiments[0]
            elif isinstance(nested_results, dict) and nested_results:
                normalized["study_protocol"] = nested_results
        return normalized

    def _generate_publish_reports(
        self,
        report_session_payload: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        report_formats = self._resolve_publish_report_formats(context)
        if not report_formats:
            return {"reports": {}, "output_files": {}, "errors": []}

        try:
            report_generator = self._create_report_generator(context)
        except Exception as exc:
            self.pipeline.logger.warning("Publish 阶段无法创建 ReportGenerator: %s", exc)
            return {"reports": {}, "output_files": {}, "errors": [str(exc)]}

        reports: Dict[str, Any] = {}
        output_files: Dict[str, Any] = {}
        errors: List[Dict[str, str]] = []
        initialized = False
        try:
            initialized = bool(report_generator.initialize())
            if not initialized:
                message = "ReportGenerator 初始化失败"
                self.pipeline.logger.warning(message)
                return {"reports": {}, "output_files": {}, "errors": [message]}

            for report_format in report_formats:
                try:
                    report = report_generator.generate_report(report_session_payload, report_format)
                    reports[str(report_format)] = report.to_dict()
                    if report.output_path:
                        output_files[f"imrd_{report.format}"] = report.output_path
                except Exception as exc:
                    self.pipeline.logger.warning("Publish 阶段生成 %s IMRD 报告失败: %s", report_format, exc)
                    errors.append({str(report_format): str(exc)})
        finally:
            if initialized:
                report_generator.cleanup()

        return {"reports": reports, "output_files": output_files, "errors": errors}

    def _resolve_publish_report_formats(self, context: Dict[str, Any]) -> List[str]:
        configured_formats = (
            context.get("report_output_formats")
            or context.get("report_formats")
            or (self.pipeline.config.get("report_generation") or {}).get("output_formats")
            or ["markdown", "docx"]
        )
        if isinstance(configured_formats, str):
            configured_formats = [configured_formats]
        if not isinstance(configured_formats, list):
            return ["markdown", "docx"]

        normalized: List[str] = []
        for item in configured_formats:
            value = str(item).strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        return normalized or ["markdown", "docx"]

    def _build_publish_output_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        observe_entities: List[Dict[str, Any]],
        hypothesis_result: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
        hypothesis_audit_summary: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        research_perspectives: Dict[str, Any],
    ) -> Dict[str, Any]:
        semantic_graph = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("semantic_graph",),
        )
        temporal_analysis = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("temporal_analysis",),
        )
        pattern_recognition = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("pattern_recognition",),
        )
        statistics = self._resolve_publish_dict_field(
            [context, analyze_result, analyze_results],
            ("statistics",),
        )
        raw_statistical_analysis = analyze_results.get("statistical_analysis")
        statistical_analysis = raw_statistical_analysis if isinstance(raw_statistical_analysis, dict) else {}
        return {
            "source_file": str(context.get("source_file") or cycle.cycle_name or cycle.cycle_id),
            "objective": cycle.research_objective or context.get("objective") or cycle.description,
            "entities": observe_entities,
            "statistics": statistics,
            "hypothesis": get_phase_value(hypothesis_result, "hypotheses", []) or ([selected_hypothesis] if selected_hypothesis else []),
            "hypothesis_result": hypothesis_result,
            "hypothesis_audit_summary": hypothesis_audit_summary,
            "reasoning_results": reasoning_results,
            "data_mining_result": data_mining_result,
            "research_perspectives": research_perspectives,
            "analysis_results": analyze_results,
            "semantic_graph": semantic_graph,
            "temporal_analysis": temporal_analysis,
            "pattern_recognition": pattern_recognition,
            "confidence_score": context.get("confidence_score") or statistical_analysis.get("confidence_level") or 0.5,
        }

    def _build_publish_hypothesis_entries(
        self,
        hypothesis_result: Dict[str, Any],
        ingestion_pipeline: Dict[str, Any],
        context: Dict[str, Any],
        selected_hypothesis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        raw_hypotheses = get_phase_value(hypothesis_result, "hypotheses", []) or ([selected_hypothesis] if selected_hypothesis else [])
        if not isinstance(raw_hypotheses, list):
            return []

        relationships = self._extract_hypothesis_relationships(ingestion_pipeline, context)
        reasoning_summary = self._extract_hypothesis_reasoning_summary(ingestion_pipeline, context)
        return [
            self._enrich_publish_hypothesis(item, relationships, reasoning_summary)
            for item in raw_hypotheses
            if isinstance(item, dict)
        ]

    def _enrich_publish_hypothesis(
        self,
        hypothesis: Dict[str, Any],
        relationships: List[Dict[str, Any]],
        reasoning_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        enriched = dict(hypothesis)
        scores = dict(enriched.get("scores") or {})
        mechanism_completeness = float(
            scores.get("mechanism_completeness")
            or enriched.get("mechanism_completeness")
            or 0.0
        )
        source_entities = [
            str(item).strip()
            for item in (enriched.get("source_entities") or [])
            if str(item).strip()
        ]
        relationship_evidence = self._match_hypothesis_relationships(source_entities, relationships)
        merged_sources: List[str] = []
        for relation in relationship_evidence:
            metadata = relation.get("metadata") or {}
            source_name = str(metadata.get("source") or "").strip()
            if source_name and source_name not in merged_sources:
                merged_sources.append(source_name)
            for merged_source in metadata.get("merged_sources") or []:
                merged_source_name = str(merged_source).strip()
                if merged_source_name and merged_source_name not in merged_sources:
                    merged_sources.append(merged_source_name)

        audit = dict(enriched.get("audit") or {})
        audit.update(
            {
                "mechanism_completeness": mechanism_completeness,
                "reasoning_inference_confidence": float(reasoning_summary.get("inference_confidence") or 0.0),
                "relationship_count": len(relationship_evidence),
                "merged_sources": merged_sources,
                "relationship_evidence": relationship_evidence[:5],
            }
        )
        enriched["scores"] = scores
        enriched["mechanism_completeness"] = mechanism_completeness
        enriched["audit"] = audit
        return enriched

    def _match_hypothesis_relationships(
        self,
        source_entities: List[str],
        relationships: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not source_entities:
            return []

        entity_set = {item for item in source_entities if item}
        matched: List[Dict[str, Any]] = []
        for relation in relationships:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source") or "").strip()
            target = str(relation.get("target") or "").strip()
            if source not in entity_set and target not in entity_set:
                continue
            matched.append(
                {
                    "source": source,
                    "target": target,
                    "type": str(relation.get("type") or relation.get("rel_type") or "related_to"),
                    "source_type": str(relation.get("source_type") or "generic"),
                    "target_type": str(relation.get("target_type") or "generic"),
                    "metadata": dict(relation.get("metadata") or {}),
                }
            )
        matched.sort(key=self._relationship_confidence, reverse=True)
        return matched

    def _build_publish_hypothesis_audit_summary(
        self,
        hypotheses: List[Dict[str, Any]],
        reasoning_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not hypotheses:
            return {}

        mechanism_scores: List[float] = []
        merged_sources: List[str] = []
        relationship_count = 0
        selected_hypothesis = hypotheses[0]
        for hypothesis in hypotheses:
            mechanism_value = float(
                hypothesis.get("mechanism_completeness")
                or (hypothesis.get("scores") or {}).get("mechanism_completeness")
                or 0.0
            )
            mechanism_scores.append(mechanism_value)
            audit = hypothesis.get("audit") or {}
            relationship_count += int(audit.get("relationship_count") or 0)
            for source_name in audit.get("merged_sources") or []:
                source_text = str(source_name).strip()
                if source_text and source_text not in merged_sources:
                    merged_sources.append(source_text)

        return {
            "selected_hypothesis_id": str(selected_hypothesis.get("hypothesis_id") or ""),
            "hypothesis_count": len(hypotheses),
            "selected_mechanism_completeness": float(
                selected_hypothesis.get("mechanism_completeness")
                or (selected_hypothesis.get("scores") or {}).get("mechanism_completeness")
                or 0.0
            ),
            "average_mechanism_completeness": round(sum(mechanism_scores) / len(mechanism_scores), 4),
            "relationship_count": relationship_count,
            "merged_sources": merged_sources,
            "reasoning_inference_confidence": float(reasoning_summary.get("inference_confidence") or 0.0),
        }

    def _execute_publish_output_generator(self, publish_output_context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            output_generator = self._create_output_generator()
        except Exception as exc:
            self.pipeline.logger.warning("Publish 阶段无法创建 OutputGenerator，将退回简化产物上下文: %s", exc)
            return {}

        output_generator.initialize()
        try:
            return output_generator.execute(publish_output_context)
        except Exception as exc:
            self.pipeline.logger.warning("Publish 阶段构建 research_artifact 失败，将退回简化产物上下文: %s", exc)
            return {}
        finally:
            output_generator.cleanup()

    def _compose_publish_analysis_results(
        self,
        structured_payload: Dict[str, Any],
        analyze_result: Dict[str, Any],
        statistical_analysis: Dict[str, Any],
        experiment_result: Dict[str, Any],
        reasoning_results: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        data_mining_aliases: Dict[str, Any],
        research_perspectives: Dict[str, Any],
        evidence_protocol: Dict[str, Any],
        similar_formula_graph_evidence_summary: Dict[str, Any],
        llm_analysis_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        composed: Dict[str, Any] = {}
        structured_analysis = structured_payload.get("analysis_results") if isinstance(structured_payload, dict) else {}
        if isinstance(structured_analysis, dict):
            composed.update(structured_analysis)

        if evidence_protocol and "evidence_protocol" not in composed:
            composed["evidence_protocol"] = copy.deepcopy(evidence_protocol)

        if reasoning_results:
            composed["reasoning_results"] = reasoning_results
        if data_mining_result:
            composed["data_mining_result"] = data_mining_result
        for alias_key, alias_value in data_mining_aliases.items():
            if alias_key not in composed:
                composed[alias_key] = copy.deepcopy(alias_value)
        if research_perspectives:
            composed["research_perspectives"] = research_perspectives
        if similar_formula_graph_evidence_summary:
            composed["similar_formula_graph_evidence_summary"] = similar_formula_graph_evidence_summary
        if statistical_analysis:
            composed["statistical_analysis"] = copy.deepcopy(statistical_analysis)
            for key in (
                "statistical_significance",
                "confidence_level",
                "effect_size",
                "p_value",
                "interpretation",
                "limitations",
                "evidence_grade",
                "evidence_grade_summary",
            ):
                if key in statistical_analysis and key not in composed:
                    composed[key] = copy.deepcopy(statistical_analysis.get(key))
        experiment_payload = experiment_result.get("results") if isinstance(experiment_result, dict) else None
        if isinstance(experiment_payload, dict) and experiment_payload:
            composed["experiment_results"] = experiment_payload
        analyze_metadata = analyze_result.get("metadata") if isinstance(analyze_result, dict) else None
        if isinstance(analyze_metadata, dict) and analyze_metadata:
            composed["metadata"] = analyze_metadata
        quality_metrics = structured_payload.get("quality_metrics") if isinstance(structured_payload, dict) else None
        if isinstance(quality_metrics, dict) and quality_metrics:
            composed["quality_metrics"] = quality_metrics
        recommendations = structured_payload.get("recommendations") if isinstance(structured_payload, dict) else None
        if isinstance(recommendations, list) and recommendations:
            composed["recommendations"] = recommendations
        if llm_analysis_context:
            composed["llm_analysis_context"] = llm_analysis_context
            analysis_modules = llm_analysis_context.get("analysis_modules")
            if isinstance(analysis_modules, dict):
                for module_name, module_value in analysis_modules.items():
                    if module_name not in composed:
                        composed[module_name] = module_value
        for alias_field in _REMOVED_PUBLISH_ANALYSIS_ALIAS_FIELDS:
            composed.pop(alias_field, None)
        self._strip_publish_data_mining_aliases(composed, data_mining_result)
        return composed

    def _build_publish_llm_analysis_context(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        structured_payload: Dict[str, Any],
        research_artifact: Dict[str, Any],
        research_perspectives: Dict[str, Any],
    ) -> Dict[str, Any]:
        structured_analysis = structured_payload.get("analysis_results") if isinstance(structured_payload, dict) else {}
        containers: List[Any] = [
            context,
            analyze_result,
            analyze_results,
            structured_payload,
            structured_analysis if isinstance(structured_analysis, dict) else {},
            research_artifact,
        ]

        modules: Dict[str, Any] = {}
        for module_name, aliases in _PUBLISH_LLM_ANALYSIS_MODULE_ALIASES.items():
            module_value = self._resolve_publish_field(containers, aliases)
            if module_name == "research_perspectives" and module_value is None and research_perspectives:
                module_value = copy.deepcopy(research_perspectives)
            modules[module_name] = module_value if module_value is not None else {}

        module_presence = {
            module_name: self._has_publish_payload(module_value)
            for module_name, module_value in modules.items()
        }
        phase_dossiers = context.get("phase_dossiers") if isinstance(context.get("phase_dossiers"), dict) else {}
        for phase_name in ("observe", "analyze", "publish"):
            dossier_payload = context.get(f"{phase_name}_dossier")
            if not isinstance(dossier_payload, dict):
                candidate = phase_dossiers.get(phase_name)
                dossier_payload = candidate if isinstance(candidate, dict) else {}
            if dossier_payload:
                modules[f"{phase_name}_dossier"] = copy.deepcopy(dossier_payload)
                module_presence[f"{phase_name}_dossier"] = True

        phase_dossier_texts = context.get("phase_dossier_texts") if isinstance(context.get("phase_dossier_texts"), dict) else {}
        if phase_dossier_texts:
            modules["phase_dossier_texts"] = copy.deepcopy(phase_dossier_texts)
            module_presence["phase_dossier_texts"] = True

        populated_modules = [
            module_name
            for module_name, present in module_presence.items()
            if present
        ]
        return {
            "contract_version": "llm-analysis-context-v1",
            "analysis_modules": modules,
            "module_presence": module_presence,
            "module_count": len(modules),
            "populated_module_count": len(populated_modules),
            "populated_modules": populated_modules,
        }

    def _resolve_publish_field(
        self,
        containers: List[Any],
        field_names: tuple[str, ...],
    ) -> Any:
        for container in containers:
            if not isinstance(container, dict):
                continue
            for field_name in field_names:
                if field_name not in container:
                    continue
                value = container.get(field_name)
                if value is None:
                    continue
                return copy.deepcopy(value)
        return None

    def _has_publish_payload(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (dict, list, tuple, set)):
            return bool(value)
        return True

    def _build_publish_reasoning_results(
        self,
        context: Dict[str, Any],
        experiment_context: Dict[str, Any],
        experiment_result: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidates = [
            self._resolve_publish_context_reasoning_results(context) or None,
            get_phase_results(analyze_result).get("reasoning_results") if isinstance(analyze_result, dict) else None,
            analyze_results.get("reasoning_results") if isinstance(analyze_results, dict) else None,
            get_phase_results(experiment_result).get("reasoning_results") if isinstance(experiment_result, dict) else None,
        ]
        reasoning_results: Dict[str, Any] = {}
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate:
                reasoning_results = dict(candidate)
                break

        if not isinstance(reasoning_results.get("evidence_records"), list):
            reasoning_results["evidence_records"] = (
                experiment_context.get("weighted_evidence_records")
                or experiment_context.get("evidence_records")
                or []
            )
        if not isinstance(reasoning_results.get("evidence_summary"), dict):
            evidence_profile = experiment_context.get("evidence_profile") or {}
            if isinstance(evidence_profile, dict) and evidence_profile:
                reasoning_results["evidence_summary"] = evidence_profile
        return reasoning_results

    def _resolve_publish_context_reasoning_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        nested_reasoning = get_phase_results(context).get("reasoning_results")
        if isinstance(nested_reasoning, dict):
            return dict(nested_reasoning)

        if is_phase_result_payload(context):
            return {}

        direct_reasoning = context.get("reasoning_results")
        if isinstance(direct_reasoning, dict):
            return dict(direct_reasoning)
        return {}

    def _resolve_publish_data_mining_result(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        value = self._resolve_publish_dict_field(containers, ("data_mining_result", "data_mining", "mining_result"))
        if value:
            return value

        research_artifact = get_phase_value(context, "research_artifact")
        if isinstance(research_artifact, dict):
            nested = research_artifact.get("data_mining_result")
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    def _resolve_publish_statistical_analysis(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("statistical_analysis",))
        if direct:
            return direct
        return {}

    def _build_publish_data_mining_aliases(self, data_mining_result: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    def _enrich_publish_research_artifact(
        self,
        research_artifact: Dict[str, Any],
        statistical_analysis: Dict[str, Any],
        data_mining_result: Dict[str, Any],
        data_mining_aliases: Dict[str, Any],
        similar_formula_graph_evidence_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        enriched = dict(research_artifact) if isinstance(research_artifact, dict) else {}
        for alias_field in _REMOVED_PUBLISH_ANALYSIS_ALIAS_FIELDS:
            enriched.pop(alias_field, None)
        if data_mining_result and not isinstance(enriched.get("data_mining_result"), dict):
            enriched["data_mining_result"] = copy.deepcopy(data_mining_result)
        if statistical_analysis and not isinstance(enriched.get("statistical_analysis"), dict):
            enriched["statistical_analysis"] = copy.deepcopy(statistical_analysis)
        if similar_formula_graph_evidence_summary and not isinstance(
            enriched.get("similar_formula_graph_evidence_summary"),
            dict,
        ):
            enriched["similar_formula_graph_evidence_summary"] = copy.deepcopy(
                similar_formula_graph_evidence_summary
            )

        for alias_key, alias_value in data_mining_aliases.items():
            if alias_key not in enriched:
                enriched[alias_key] = copy.deepcopy(alias_value)
        self._strip_publish_data_mining_aliases(enriched, data_mining_result)
        return enriched

    def _strip_publish_data_mining_aliases(
        self,
        payload: Dict[str, Any],
        data_mining_result: Dict[str, Any],
    ) -> None:
        if not isinstance(payload, dict) or not isinstance(data_mining_result, dict):
            return

        for alias_field in _REMOVED_PUBLISH_DATA_MINING_ALIAS_FIELDS:
            payload.pop(alias_field, None)

    def _resolve_publish_research_perspectives(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("research_perspectives",))
        if direct:
            return direct
        for field_name in ("semantic_analysis", "research_analysis", "analysis_results"):
            nested_container = self._resolve_publish_dict_field(containers, (field_name,))
            if isinstance(nested_container.get("research_perspectives"), dict):
                return dict(nested_container.get("research_perspectives") or {})
        return {}

    def _resolve_publish_similar_formula_graph_evidence_summary(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        research_artifact: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("similar_formula_graph_evidence_summary",))
        if direct:
            return direct
        if isinstance(research_artifact, dict):
            nested = research_artifact.get("similar_formula_graph_evidence_summary")
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    def _resolve_publish_evidence_grade_summary(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        research_artifact: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self._resolve_publish_flag(context, "include_evidence_grade", True):
            return {}

        containers = [context, analyze_result, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("evidence_grade_summary",))
        if direct:
            return direct

        evidence_grade = self._resolve_publish_dict_field(containers, ("evidence_grade",))
        if evidence_grade:
            return self._build_evidence_grade_summary(evidence_grade)

        for container in containers:
            if not isinstance(container, dict):
                continue
            statistical_analysis = container.get("statistical_analysis")
            if not isinstance(statistical_analysis, dict):
                continue
            nested_summary = statistical_analysis.get("evidence_grade_summary")
            if isinstance(nested_summary, dict):
                return dict(nested_summary)

            nested_evidence_grade = statistical_analysis.get("evidence_grade")
            if isinstance(nested_evidence_grade, dict):
                return self._build_evidence_grade_summary(nested_evidence_grade)

        if isinstance(research_artifact, dict):
            nested = research_artifact.get("evidence_grade_summary")
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    def _resolve_publish_evidence_grade_payload(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        containers = [context, analyze_results]
        direct = self._resolve_publish_dict_field(containers, ("evidence_grade",))
        if direct:
            return direct

        for container in (context, analyze_results, analyze_result):
            if not isinstance(container, dict):
                continue
            statistical_analysis = container.get("statistical_analysis")
            if isinstance(statistical_analysis, dict):
                nested_evidence_grade = statistical_analysis.get("evidence_grade")
                if isinstance(nested_evidence_grade, dict):
                    return dict(nested_evidence_grade)
        return {}

    def _resolve_publish_evidence_protocol(
        self,
        context: Dict[str, Any],
        analyze_result: Dict[str, Any],
        analyze_results: Dict[str, Any],
        reasoning_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        direct = self._resolve_publish_dict_field([context, analyze_results], ("evidence_protocol",))
        if direct:
            return direct

        evidence_grade = self._resolve_publish_evidence_grade_payload(
            context,
            analyze_result,
            analyze_results,
        )
        evidence_records = reasoning_results.get("evidence_records") if isinstance(reasoning_results.get("evidence_records"), list) else None
        return build_evidence_protocol(
            reasoning_results,
            evidence_records=evidence_records,
            evidence_grade=evidence_grade,
        )

    def _resolve_publish_limitations(
        self,
        context: Dict[str, Any],
        analyze_results: Dict[str, Any],
        analysis_results_payload: Dict[str, Any],
    ) -> Any:
        statistical_analysis = analysis_results_payload.get("statistical_analysis")
        if isinstance(statistical_analysis, dict) and statistical_analysis.get("limitations"):
            return statistical_analysis.get("limitations")
        if context.get("limitations"):
            return context.get("limitations")
        return []

    def _resolve_publish_paper_iteration_settings(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {}

        resolved: Dict[str, Any] = {}
        field_aliases = {
            "enable_iterative_refinement": (
                "paper_enable_iterative_refinement",
                "enable_iterative_refinement",
            ),
            "max_revision_rounds": (
                "paper_max_revision_rounds",
                "max_revision_rounds",
                "paper_revision_rounds",
            ),
            "min_revision_rounds": (
                "paper_min_revision_rounds",
                "min_revision_rounds",
            ),
            "review_score_threshold": (
                "paper_review_score_threshold",
                "review_score_threshold",
            ),
            "min_section_characters": (
                "paper_min_section_characters",
                "min_section_characters",
            ),
        }

        for target_key, aliases in field_aliases.items():
            for alias in aliases:
                if alias in context and context.get(alias) is not None:
                    resolved[target_key] = context.get(alias)
                    break
        return resolved

    def _resolve_publish_dict_field(
        self,
        containers: List[Any],
        field_names: tuple[str, ...],
    ) -> Dict[str, Any]:
        for container in containers:
            if not isinstance(container, dict):
                continue
            for field_name in field_names:
                value = container.get(field_name)
                if isinstance(value, dict):
                    return dict(value)
        return {}

    def _execute_paper_writer(
        self,
        paper_writer: Any,
        paper_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        paper_writer.initialize()
        try:
            try:
                return paper_writer.execute(paper_context)
            except ImportError:
                fallback_context = dict(paper_context)
                fallback_context["output_formats"] = ["markdown"]
                fallback_context["output_format"] = "markdown"
                return paper_writer.execute(fallback_context)
        finally:
            paper_writer.cleanup()

    def _extract_publish_entities(
        self,
        observe_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        entities = context.get("entities")
        if isinstance(entities, list) and entities:
            return [item for item in entities if isinstance(item, dict)]

        ingestion_pipeline = get_phase_value(observe_result, "ingestion_pipeline", {}) or {}
        documents = ingestion_pipeline.get("documents") or []
        derived: List[Dict[str, Any]] = []
        for document in documents[:5]:
            if not isinstance(document, dict):
                continue
            title = str(document.get("title") or document.get("urn") or "").strip()
            if not title:
                continue
            derived.append({"name": title})
        return derived

    def _merge_publish_output_files(
        self,
        paper_output_files: Dict[str, Any],
        citation_output_files: Dict[str, Any],
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        if isinstance(citation_output_files, dict):
            merged.update({key: value for key, value in citation_output_files.items() if value})
        if isinstance(paper_output_files, dict):
            merged.update({key: value for key, value in paper_output_files.items() if value})
        return merged

    def _safe_researcher_key(self, researchers: List[str]) -> str:
        if not researchers:
            return "research"
        primary = str(researchers[0]).strip() or "research"
        compact = "".join(ch for ch in primary if ch.isalnum())
        return compact[:24] or "research"

    def _build_publications_from_paper_result(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        paper_context: Dict[str, Any],
        paper_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """从 PaperWriter 真实产出构建 publications 列表。"""
        publications: List[Dict[str, Any]] = []

        paper_draft = paper_result.get("paper_draft") or {}
        if not isinstance(paper_draft, dict):
            paper_draft = {}

        title = (
            paper_draft.get("title")
            or paper_context.get("title")
            or context.get("paper_title")
            or f"{cycle.research_objective or cycle.description}研究"
        )
        authors = paper_context.get("authors") or cycle.researchers
        keywords = paper_draft.get("keywords") or paper_context.get("keywords") or []
        journal = paper_context.get("journal") or context.get("journal") or ""
        year = datetime.now().year

        # 主论文条目（来自 PaperWriter 真实产出）
        section_count = paper_result.get("section_count", 0)
        reference_count = paper_result.get("reference_count", 0)
        has_content = bool(paper_draft.get("sections") or paper_draft.get("abstract"))

        publications.append({
            "title": str(title).strip(),
            "journal": journal,
            "authors": authors,
            "keywords": list(keywords)[:20],
            "status": "draft_generated" if has_content else "draft_empty",
            "citation_key": f"{self._safe_researcher_key(authors)}{year}",
            "section_count": section_count,
            "reference_count": reference_count,
            "language": paper_result.get("language", "zh"),
            "review_score": paper_result.get("final_review_score", 0.0),
            "iteration_count": paper_result.get("iteration_count", 0),
        })

        # 若有 IMRD sections，为每个主要章节生成子条目
        sections = paper_draft.get("sections") or []
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                sec_type = str(section.get("section_type") or "").strip()
                sec_title = str(section.get("title") or "").strip()
                sec_content = str(section.get("content") or "").strip()
                if sec_type and sec_content:
                    publications.append({
                        "title": sec_title or f"{title} — {sec_type}",
                        "section_type": sec_type,
                        "authors": authors,
                        "status": "section_generated",
                        "content_length": len(sec_content),
                    })

        return publications
