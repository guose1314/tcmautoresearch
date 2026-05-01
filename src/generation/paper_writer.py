"""论文撰写服务 — IMRD 结构论文生成、摘要生成、参考文献格式化。"""

from __future__ import annotations

import copy
import importlib
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.core.module_base import BaseModule
from src.generation.citation_manager import CitationManager
from src.research.phase_result import (
    get_phase_artifact_map,
    get_phase_results,
    get_phase_value,
    is_phase_result_payload,
)

logger = logging.getLogger(__name__)

_SECTION_ORDER = ["introduction", "methods", "results", "discussion", "conclusion"]
_TCM_EXTRA_SECTION_ORDER = ["formula_interpretation", "pattern_analysis", "commentary"]
PAPER_TEMPLATE_DEFAULT = "imrd"
PAPER_TEMPLATE_TCM = "tcm"
SUPPORTED_PAPER_TEMPLATES: tuple[str, ...] = (
    PAPER_TEMPLATE_DEFAULT,
    PAPER_TEMPLATE_TCM,
)
_ZH_SECTION_TITLES = {
    "introduction": "1 引言（Introduction）",
    "methods": "2 方法（Methods）",
    "results": "3 结果（Results）",
    "discussion": "4 讨论（Discussion）",
    "conclusion": "5 结论（Conclusion）",
    "formula_interpretation": "附 A 方义阐释",
    "pattern_analysis": "附 B 证治分析",
    "commentary": "附 C 按语",
}
_EN_SECTION_TITLES = {
    "introduction": "1. Introduction",
    "methods": "2. Methods",
    "results": "3. Results",
    "discussion": "4. Discussion",
    "conclusion": "5. Conclusion",
    "formula_interpretation": "Appendix A. Formula Interpretation",
    "pattern_analysis": "Appendix B. Pattern Analysis",
    "commentary": "Appendix C. Commentary",
}
_GRADE_LABELS_ZH = {
    "high": "高",
    "moderate": "中等",
    "low": "低",
    "very_low": "极低",
}
_BIAS_LABELS_ZH = {
    "low": "低",
    "moderate": "中等",
    "high": "高",
}
_LLM_ANALYSIS_MODULE_ALIASES: Dict[str, tuple[str, ...]] = {
    "research_perspectives": ("research_perspectives",),
    "formula_comparisons": ("formula_comparisons",),
    "herb_properties_analysis": ("herb_properties_analysis", "herb_properties"),
    "pharmacology_integration": ("pharmacology_integration",),
    "network_pharmacology": (
        "network_pharmacology",
        "network_pharmacology_systems_biology",
    ),
    "supramolecular_physicochemistry": ("supramolecular_physicochemistry",),
    "knowledge_archaeology": ("knowledge_archaeology",),
    "complexity_dynamics": ("complexity_dynamics", "complexity_nonlinear_dynamics"),
    "research_scoring_panel": ("research_scoring_panel",),
    "summary_analysis": ("summary_analysis",),
    "publish_graph_context": ("publish_graph_context",),
    "graph_rag_citations": ("graph_rag_citations",),
}
_LLM_ANALYSIS_MODULE_LABELS_ZH = {
    "research_perspectives": "研究视角",
    "formula_comparisons": "方剂比较",
    "herb_properties_analysis": "药性分析",
    "pharmacology_integration": "药理整合",
    "network_pharmacology": "网络药理学",
    "supramolecular_physicochemistry": "超分子理化",
    "knowledge_archaeology": "知识考古",
    "complexity_dynamics": "复杂性动力学",
    "research_scoring_panel": "研究评分",
    "summary_analysis": "总结分析",
    "publish_graph_context": "图谱引用追溯",
    "graph_rag_citations": "GraphRAG 引文",
}


@dataclass
class PaperSection:
    """论文章节。"""

    section_type: str = ""
    title: str = ""
    content: str = ""
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PaperDraft:
    """论文初稿。"""

    title: str = ""
    abstract: str = ""
    keywords: List[str] = field(default_factory=list)
    sections: List[PaperSection] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    output_format: str = "markdown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["sections"] = [section.to_dict() for section in self.sections]
        return payload


class PaperWriter(BaseModule):
    """论文撰写器 — 生成 IMRD 结构论文初稿。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("paper_writer", config)
        self.output_dir = os.path.abspath(
            str(self.config.get("output_dir", "output/papers"))
        )
        self.language = str(self.config.get("language", "zh")).lower()
        self.default_formats = self._normalize_formats(
            self.config.get("output_formats")
            or self.config.get("output_format")
            or ["markdown", "docx"]
        )
        self.include_conclusion = bool(self.config.get("include_conclusion", True))
        self.reference_format = str(
            self.config.get("reference_format", "GB/T 7714-2015")
        )
        self.embed_figures = bool(self.config.get("embed_figures", False))
        self.enable_iterative_refinement = bool(
            self.config.get("enable_iterative_refinement", True)
        )
        self.template = self._coerce_template(
            self.config.get("template", PAPER_TEMPLATE_DEFAULT)
        )
        self.max_revision_rounds = self._coerce_iteration_limit(
            self.config.get("max_revision_rounds", 2)
        )
        self.min_revision_rounds = self._coerce_iteration_limit(
            self.config.get("min_revision_rounds", 1),
            upper=self.max_revision_rounds,
        )
        self.review_score_threshold = self._coerce_score_threshold(
            self.config.get("review_score_threshold", 0.86)
        )
        self.min_section_characters = max(
            120,
            self._coerce_iteration_limit(
                self.config.get("min_section_characters", 220), maximum=2000
            ),
        )
        self._Document: Any = None
        self._DocumentType: Any = None
        self._WD_ALIGN_CENTER: Any = None
        self._Pt: Any = None
        self._Inches: Any = None
        self._citation_manager = CitationManager(
            {"format": self.reference_format, "include_abstract": False}
        )

    def _do_initialize(self) -> bool:
        os.makedirs(self.output_dir, exist_ok=True)
        self._citation_manager.initialize()
        try:
            docx_module = importlib.import_module("docx")
            document_module = importlib.import_module("docx.document")
            text_module = importlib.import_module("docx.enum.text")
            shared_module = importlib.import_module("docx.shared")
            self._Document = docx_module.Document
            self._DocumentType = document_module.Document
            self._WD_ALIGN_CENTER = text_module.WD_PARAGRAPH_ALIGNMENT.CENTER
            self._Pt = shared_module.Pt
            self._Inches = getattr(shared_module, "Inches", None)
        except Exception as exc:
            self._Document = None
            logger.warning(
                "PaperWriter 未能加载 python-docx，DOCX 导出将不可用: %s", exc
            )
        logger.info("PaperWriter 初始化完成: output_dir=%s", self.output_dir)
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        initial_draft = self.build_draft(context)
        draft, iteration_history, review_summary = self._run_iterative_refinement(
            initial_draft, context
        )
        formats = self._normalize_formats(
            context.get("output_formats")
            or context.get("output_format")
            or self.default_formats
        )
        output_files = self.export_draft(draft, formats=formats, context=context)
        return {
            "success": True,
            "paper_draft": draft.to_dict(),
            "initial_paper_draft": initial_draft.to_dict(),
            "output_files": output_files,
            "section_count": len(draft.sections),
            "reference_count": len(draft.references),
            "figure_count": len(self._resolve_figure_paths(context)),
            "language": draft.metadata.get("language", self.language),
            "iteration_count": int(review_summary.get("rounds_completed") or 0),
            "final_review_score": float(review_summary.get("final_score") or 0.0),
            "iteration_history": iteration_history,
            "review_summary": review_summary,
        }

    def _do_cleanup(self) -> bool:
        self._citation_manager.cleanup()
        return True

    def build_draft(self, context: Dict[str, Any]) -> PaperDraft:
        language = str(context.get("language") or self.language or "zh").lower()
        template = self._coerce_template(context.get("template") or self.template)
        title = self._resolve_title(context)
        keywords = self._resolve_keywords(context)
        references = self._resolve_references(context)
        section_overrides = self._resolve_section_overrides(context, language)

        section_order = list(_SECTION_ORDER)
        if template == PAPER_TEMPLATE_TCM:
            section_order = section_order + list(_TCM_EXTRA_SECTION_ORDER)

        sections: List[PaperSection] = []
        for section_type in section_order:
            if section_type == "conclusion" and not self.include_conclusion:
                continue
            title_text = self._section_title(section_type, language)
            content = section_overrides.get(
                section_type
            ) or self._generate_section_content(
                section_type, context, title, language, references
            )
            sections.append(
                PaperSection(
                    section_type=section_type,
                    title=title_text,
                    content=content.strip(),
                    references=self._section_reference_markers(
                        section_type, references
                    ),
                )
            )

        abstract_text = self._resolve_abstract(context, title, sections, language)
        publish_graph_context = self._resolve_publish_graph_context(context)
        graph_rag_citations = self._resolve_graph_rag_citations(
            context, publish_graph_context
        )
        metadata = {
            "language": language,
            "generated_at": datetime.now().isoformat(),
            "reference_format": self.reference_format,
            "author": self._resolve_author_text(context),
            "affiliation": str(context.get("affiliation") or "").strip(),
            "journal": str(context.get("journal") or "").strip(),
            "figure_paths": self._resolve_figure_paths(context),
            "section_overrides": sorted(section_overrides.keys()),
            "template": template,
            "publish_graph_context": copy.deepcopy(publish_graph_context),
            "graph_rag_citation_count": len(graph_rag_citations),
            "unsupported_claim_warning_count": int(
                publish_graph_context.get("unsupported_claim_warning_count") or 0
            ),
        }
        return PaperDraft(
            title=title,
            abstract=abstract_text,
            keywords=keywords,
            sections=sections,
            references=references,
            output_format="+".join(self.default_formats),
            metadata=metadata,
        )

    def _run_iterative_refinement(
        self,
        draft: PaperDraft,
        context: Dict[str, Any],
    ) -> tuple[PaperDraft, List[Dict[str, Any]], Dict[str, Any]]:
        enabled_flag = context.get("enable_iterative_refinement")
        enabled = (
            self.enable_iterative_refinement
            if enabled_flag is None
            else bool(enabled_flag)
        )
        if not enabled:
            return draft, [], self._make_disabled_refinement_summary()

        max_rounds = self._coerce_iteration_limit(
            context.get("max_revision_rounds")
            or context.get("paper_revision_rounds")
            or self.max_revision_rounds,
        )
        min_rounds = self._coerce_iteration_limit(
            context.get("min_revision_rounds") or self.min_revision_rounds,
            upper=max_rounds,
        )
        score_threshold = self._coerce_score_threshold(
            context.get("review_score_threshold")
            if context.get("review_score_threshold") is not None
            else self.review_score_threshold
        )

        current_draft = self._clone_draft(draft)
        history: List[Dict[str, Any]] = []

        for round_index in range(1, max_rounds + 1):
            review = self._review_draft(current_draft, context, round_index)
            score = float(review.get("score") or 0.0)
            should_continue = round_index < max_rounds and (
                score < score_threshold or round_index < min_rounds
            )

            applied_revisions: List[str] = []
            decision = "accept"
            if should_continue:
                current_draft, applied_revisions = self._revise_draft(
                    current_draft,
                    context,
                    review,
                    round_index,
                )
                decision = "revise"

            history.append(
                {
                    "round": round_index,
                    "score": round(score, 3),
                    "metrics": review.get("metrics", {}),
                    "issues": review.get("issues", []),
                    "suggestions": review.get("suggestions", []),
                    "decision": decision,
                    "applied_revisions": applied_revisions,
                }
            )

            if not should_continue:
                break

        final_score = float(history[-1].get("score") or 0.0) if history else 0.0
        summary = {
            "enabled": True,
            "rounds_completed": len(history),
            "max_rounds": max_rounds,
            "min_rounds": min_rounds,
            "score_threshold": score_threshold,
            "final_score": round(final_score, 3),
            "accepted": final_score >= score_threshold,
            "issue_overview": self._summarize_review_issues(history),
        }
        metadata = dict(current_draft.metadata)
        metadata["review_summary"] = summary
        metadata["iteration_history"] = history
        current_draft.metadata = metadata
        return current_draft, history, summary

    def _make_disabled_refinement_summary(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "rounds_completed": 0,
            "max_rounds": 0,
            "min_rounds": 0,
            "score_threshold": self.review_score_threshold,
            "final_score": 0.0,
            "accepted": True,
            "issue_overview": [],
        }

    def _review_draft(
        self,
        draft: PaperDraft,
        context: Dict[str, Any],
        round_index: int,
    ) -> Dict[str, Any]:
        language = str(
            draft.metadata.get("language")
            or context.get("language")
            or self.language
            or "zh"
        ).lower()
        expected_sections = [
            item
            for item in _SECTION_ORDER
            if item != "conclusion" or self.include_conclusion
        ]
        section_map = {section.section_type: section for section in draft.sections}
        missing_sections = [
            item for item in expected_sections if item not in section_map
        ]
        short_sections = [
            section.section_type
            for section in draft.sections
            if len(str(section.content or "").strip()) < self.min_section_characters
        ]
        abstract_length = len(str(draft.abstract or "").strip())
        reference_count = len(
            [ref for ref in draft.references if str(ref or "").strip()]
        )
        keyword_count = len(
            [keyword for keyword in draft.keywords if str(keyword or "").strip()]
        )

        structure_score = max(
            0.0, 1.0 - len(missing_sections) / max(1, len(expected_sections))
        )
        depth_score = max(0.0, 1.0 - len(short_sections) / max(1, len(draft.sections)))
        abstract_score = min(
            1.0, abstract_length / float(self._minimum_abstract_characters(language))
        )
        reference_target = 5 if language == "en" else 4
        reference_score = min(1.0, reference_count / float(reference_target))
        keyword_score = min(1.0, keyword_count / 4.0)

        score = round(
            0.30 * structure_score
            + 0.30 * depth_score
            + 0.20 * abstract_score
            + 0.15 * reference_score
            + 0.05 * keyword_score,
            3,
        )

        metrics_dict = {
            "structure_score": round(structure_score, 3),
            "depth_score": round(depth_score, 3),
            "abstract_score": round(abstract_score, 3),
            "reference_score": round(reference_score, 3),
            "keyword_score": round(keyword_score, 3),
            "missing_sections": missing_sections,
            "short_sections": short_sections,
            "abstract_length": abstract_length,
            "reference_count": reference_count,
            "keyword_count": keyword_count,
        }

        issues, suggestions = self._collect_review_issues(
            language,
            missing_sections,
            short_sections,
            abstract_length,
            reference_count,
            keyword_count,
        )

        return {
            "round": round_index,
            "score": score,
            "metrics": metrics_dict,
            "issues": issues,
            "suggestions": suggestions,
        }

    def _collect_review_issues(
        self,
        language: str,
        missing_sections: List[str],
        short_sections: List[str],
        abstract_length: int,
        reference_count: int,
        keyword_count: int,
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        issues: List[Dict[str, Any]] = []
        suggestions: List[str] = []
        if missing_sections:
            issues.append({"code": "missing_sections", "detail": missing_sections})
            suggestions.append(
                "Add missing IMRD sections to complete manuscript structure."
                if language == "en"
                else "补全缺失章节，确保 IMRD 结构完整。"
            )
        if short_sections:
            issues.append({"code": "short_sections", "detail": short_sections})
            suggestions.append(
                "Expand short sections with clearer methods, evidence chains, and interpretation details."
                if language == "en"
                else "扩展过短章节，补充方法细节、证据链和解释逻辑。"
            )
        if abstract_length < self._minimum_abstract_characters(language):
            issues.append({"code": "abstract_too_short", "detail": abstract_length})
            suggestions.append(
                "Regenerate abstract to include background, methods, key results, and conclusion."
                if language == "en"
                else "重写摘要，补全背景、方法、核心结果和结论信息。"
            )
        if reference_count < 2:
            issues.append(
                {"code": "insufficient_references", "detail": reference_count}
            )
            suggestions.append(
                "Increase reference coverage to support claims in results and discussion."
                if language == "en"
                else "补充参考文献覆盖，支撑结果与讨论中的关键论断。"
            )
        if keyword_count < 3:
            issues.append({"code": "insufficient_keywords", "detail": keyword_count})
            suggestions.append(
                "Add at least three representative keywords for indexing."
                if language == "en"
                else "补充至少 3 个代表性关键词，提升检索与索引质量。"
            )
        return issues, suggestions

    def _revise_draft(
        self,
        draft: PaperDraft,
        context: Dict[str, Any],
        review: Dict[str, Any],
        round_index: int,
    ) -> tuple[PaperDraft, List[str]]:
        revised = self._clone_draft(draft)
        language = str(
            revised.metadata.get("language")
            or context.get("language")
            or self.language
            or "zh"
        ).lower()
        raw_metrics = review.get("metrics") if isinstance(review, dict) else None
        metrics: Dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
        protected_sections = set(revised.metadata.get("section_overrides") or [])
        applied: List[str] = []

        applied += self._revise_expand_short_sections(
            revised, metrics, context, language, round_index, protected_sections
        )
        applied += self._revise_add_missing_sections(
            revised, metrics, context, language, round_index
        )
        applied += self._revise_abstract(revised, metrics, context, language)
        applied += self._revise_references(revised, metrics, context)
        applied += self._revise_keywords(revised, metrics, context)

        if not applied and revised.sections:
            applied += self._revise_enhance_fallback(
                revised, context, language, round_index, protected_sections
            )

        updated_metadata = dict(revised.metadata)
        updated_metadata["last_revision_round"] = round_index
        updated_metadata["last_revision_actions"] = applied
        updated_metadata["last_revision_at"] = datetime.now().isoformat()
        revised.metadata = updated_metadata
        return revised, applied

    def _revise_expand_short_sections(
        self,
        revised: PaperDraft,
        metrics: Dict[str, Any],
        context: Dict[str, Any],
        language: str,
        round_index: int,
        protected_sections: set,
    ) -> List[str]:
        applied: List[str] = []
        short_sections = set(metrics.get("short_sections") or [])
        for section in revised.sections:
            if (
                section.section_type not in short_sections
                or section.section_type in protected_sections
            ):
                continue
            addition = self._build_revision_paragraph(
                section.section_type, context, language, round_index
            )
            if not addition:
                continue
            section.content = (
                f"{str(section.content or '').rstrip()}\n\n{addition}".strip()
            )
            applied.append(f"扩展章节: {section.section_type}")
        return applied

    def _revise_add_missing_sections(
        self,
        revised: PaperDraft,
        metrics: Dict[str, Any],
        context: Dict[str, Any],
        language: str,
        round_index: int,
    ) -> List[str]:
        applied: List[str] = []
        missing_sections = list(metrics.get("missing_sections") or [])
        for section_type in missing_sections:
            if section_type == "conclusion" and not self.include_conclusion:
                continue
            content = self._generate_section_content(
                section_type, context, revised.title, language, revised.references
            )
            if len(str(content or "").strip()) < self.min_section_characters:
                addition = self._build_revision_paragraph(
                    section_type, context, language, round_index
                )
                content = (
                    f"{str(content or '').strip()}\n\n{addition}".strip()
                    if addition
                    else str(content or "").strip()
                )
            revised.sections.append(
                PaperSection(
                    section_type=section_type,
                    title=self._section_title(section_type, language),
                    content=content,
                    references=self._section_reference_markers(
                        section_type, revised.references
                    ),
                )
            )
            applied.append(f"补全章节: {section_type}")
        if missing_sections:
            revised.sections = self._sort_sections_by_order(revised.sections)
        return applied

    def _revise_abstract(
        self,
        revised: PaperDraft,
        metrics: Dict[str, Any],
        context: Dict[str, Any],
        language: str,
    ) -> List[str]:
        if int(metrics.get("abstract_length") or 0) < self._minimum_abstract_characters(
            language
        ):
            revised_abstract_context = {**context, "abstract": ""}
            revised.abstract = self._resolve_abstract(
                revised_abstract_context, revised.title, revised.sections, language
            )
            return ["重写摘要"]
        return []

    def _revise_references(
        self, revised: PaperDraft, metrics: Dict[str, Any], context: Dict[str, Any]
    ) -> List[str]:
        if int(metrics.get("reference_count") or 0) >= 2:
            return []
        candidates = self._resolve_references(context)
        merged_references = list(revised.references)
        for item in candidates:
            text = str(item or "").strip()
            if text and text not in merged_references:
                merged_references.append(text)
        if len(merged_references) > len(revised.references):
            revised.references = merged_references
            return ["补充参考文献"]
        return []

    def _revise_keywords(
        self, revised: PaperDraft, metrics: Dict[str, Any], context: Dict[str, Any]
    ) -> List[str]:
        if int(metrics.get("keyword_count") or 0) >= 3:
            return []
        keyword_candidates = self._resolve_keywords(context)
        merged_keywords = list(revised.keywords)
        for item in keyword_candidates:
            text = str(item or "").strip()
            if text and text not in merged_keywords:
                merged_keywords.append(text)
        if len(merged_keywords) > len(revised.keywords):
            revised.keywords = merged_keywords[:8]
            return ["补充关键词"]
        return []

    def _revise_enhance_fallback(
        self,
        revised: PaperDraft,
        context: Dict[str, Any],
        language: str,
        round_index: int,
        protected_sections: set,
    ) -> List[str]:
        section = next(
            (
                item
                for item in revised.sections
                if item.section_type not in protected_sections
            ),
            revised.sections[0],
        )
        addition = self._build_revision_paragraph(
            section.section_type, context, language, round_index
        )
        if addition:
            section.content = (
                f"{str(section.content or '').rstrip()}\n\n{addition}".strip()
            )
            return [f"增强章节: {section.section_type}"]
        return []

    def _summarize_review_issues(
        self, history: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        bucket: Dict[str, int] = {}
        for entry in history:
            for issue in entry.get("issues") or []:
                code = str((issue or {}).get("code") or "unknown")
                bucket[code] = bucket.get(code, 0) + 1
        return [
            {"code": code, "count": count}
            for code, count in sorted(
                bucket.items(), key=lambda item: (-item[1], item[0])
            )
        ]

    def _build_revision_paragraph(
        self,
        section_type: str,
        context: Dict[str, Any],
        language: str,
        round_index: int,
    ) -> str:
        objective = str(context.get("objective") or "提升论文证据表达质量").strip()
        if language == "en":
            templates_en = {
                "introduction": f"Revision round {round_index} enriches the background rationale around {objective}, clarifies unresolved evidence gaps, and strengthens the problem statement.",
                "methods": f"Revision round {round_index} expands methodological transparency, including data-source selection, analysis workflow, and quality-control checkpoints.",
                "results": f"Revision round {round_index} adds clearer result interpretation, linking extracted evidence with statistical and mining outcomes for reproducibility.",
                "discussion": f"Revision round {round_index} broadens implication analysis, highlights limitations, and aligns findings with downstream validation priorities.",
                "conclusion": f"Revision round {round_index} refines the concluding claims to match reported evidence scope and practical manuscript deliverables.",
            }
            return templates_en.get(
                section_type,
                f"Revision round {round_index} enhances the {section_type} section by improving evidence coherence and narrative completeness.",
            )

        templates_zh = {
            "introduction": f"第 {round_index} 轮修订补充了研究背景与问题界定，围绕“{objective}”进一步明确证据缺口与研究动机。",
            "methods": f"第 {round_index} 轮修订细化了方法流程，补充了数据来源选择依据、分析步骤和质量控制要点。",
            "results": f"第 {round_index} 轮修订强化了结果阐释，将证据抽取、统计分析与数据挖掘结果进行对应说明。",
            "discussion": f"第 {round_index} 轮修订完善了讨论深度，补充了局限性说明与后续验证方向。",
            "conclusion": f"第 {round_index} 轮修订收敛了结论表达，使结论与证据范围、研究目标及交付产物保持一致。",
        }
        return templates_zh.get(
            section_type,
            f"第 {round_index} 轮修订增强了本节叙事完整性，补充了证据链说明与关键结论支撑。",
        )

    def _clone_draft(self, draft: PaperDraft) -> PaperDraft:
        return PaperDraft(
            title=draft.title,
            abstract=draft.abstract,
            keywords=list(draft.keywords),
            sections=[
                PaperSection(
                    section_type=section.section_type,
                    title=section.title,
                    content=section.content,
                    references=list(section.references),
                )
                for section in draft.sections
            ],
            references=list(draft.references),
            output_format=draft.output_format,
            metadata=dict(draft.metadata),
        )

    def _sort_sections_by_order(
        self, sections: Sequence[PaperSection]
    ) -> List[PaperSection]:
        order_map = {name: index for index, name in enumerate(_SECTION_ORDER)}
        return sorted(
            list(sections),
            key=lambda item: (
                order_map.get(item.section_type, len(order_map)),
                item.section_type,
            ),
        )

    def _minimum_abstract_characters(self, language: str) -> int:
        return 320 if language == "en" else 180

    def _coerce_iteration_limit(
        self,
        value: Any,
        *,
        minimum: int = 1,
        maximum: int = 6,
        upper: Optional[int] = None,
    ) -> int:
        if upper is not None:
            maximum = min(maximum, max(minimum, int(upper)))
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            coerced = minimum
        return max(minimum, min(maximum, coerced))

    def _coerce_score_threshold(self, value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.86
        return max(0.0, min(1.0, score))

    def export_draft(
        self,
        draft: PaperDraft,
        formats: Sequence[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        exec_context = context or {}
        output_dir = os.path.abspath(
            str(exec_context.get("output_dir") or self.output_dir)
        )
        os.makedirs(output_dir, exist_ok=True)
        file_stem = self._resolve_file_stem(exec_context, draft.title)
        outputs: Dict[str, str] = {}
        for fmt in formats:
            if fmt == "markdown":
                path = self._resolve_output_path(
                    exec_context, output_dir, file_stem, fmt
                )
                outputs[fmt] = self._export_markdown(draft, path)
            elif fmt == "docx":
                path = self._resolve_output_path(
                    exec_context, output_dir, file_stem, fmt
                )
                outputs[fmt] = self._export_docx(draft, path, exec_context)
            else:
                raise ValueError(f"不支持的论文输出格式: {fmt}")
        return outputs

    def _resolve_title(self, context: Dict[str, Any]) -> str:
        for key in ("title", "paper_title", "draft_title"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        objective = str(context.get("objective") or "").strip()
        research_domain = str(context.get("research_domain") or "中医古籍研究").strip()
        if objective:
            return f"{research_domain}：{objective}"
        return f"{research_domain} IMRD 初稿"

    def _resolve_author_text(self, context: Dict[str, Any]) -> str:
        authors = context.get("authors") or context.get("author") or []
        if isinstance(authors, str):
            return authors.strip()
        if isinstance(authors, (list, tuple, set)):
            return ", ".join(str(item).strip() for item in authors if str(item).strip())
        return ""

    def _resolve_keywords(self, context: Dict[str, Any]) -> List[str]:
        raw_keywords = context.get("keywords") or context.get("keyword") or []
        if isinstance(raw_keywords, str):
            candidates = re.split(r"[;,；，、\n]+", raw_keywords)
        else:
            candidates = list(raw_keywords)

        normalized = self._deduplicate_keyword_candidates(candidates)
        if normalized:
            return normalized[:6]

        derived = self._derive_keywords_from_entities(context)
        if derived:
            return derived[:6]

        derived = self._derive_keywords_from_mining(context, derived)
        return derived[:6] or ["中医古籍", "科研初稿", "IMRD"]

    def _deduplicate_keyword_candidates(self, candidates: List[Any]) -> List[str]:
        normalized: List[str] = []
        for item in candidates:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def _derive_keywords_from_entities(self, context: Dict[str, Any]) -> List[str]:
        derived: List[str] = []
        for entity in list(context.get("entities") or [])[:6]:
            if isinstance(entity, dict):
                value = entity.get("name") or entity.get("text") or entity.get("entity")
            else:
                value = entity
            text = str(value or "").strip()
            if text and text not in derived:
                derived.append(text)
        return derived

    def _derive_keywords_from_mining(
        self, context: Dict[str, Any], existing: List[str]
    ) -> List[str]:
        derived = list(existing)
        data_mining = self._resolve_data_mining_result(context)
        cluster_summary = list(
            data_mining.get("clustering", {}).get("cluster_summary", []) or []
        )
        if cluster_summary:
            top_items = list(cluster_summary[0].get("top_items", []) or [])
            for item in top_items:
                text = str(item.get("item") or "").strip()
                if text and text not in derived:
                    derived.append(text)
        return derived

    def _resolve_references(self, context: Dict[str, Any]) -> List[str]:
        explicit_references = context.get("formatted_references")
        if isinstance(explicit_references, str) and explicit_references.strip():
            return [
                line.strip()
                for line in explicit_references.splitlines()
                if line.strip()
            ]
        if isinstance(explicit_references, list):
            return [
                str(item).strip() for item in explicit_references if str(item).strip()
            ]

        raw_records = (
            context.get("citation_records")
            or context.get("reference_records")
            or context.get("literature_records")
            or self._extract_literature_records(context)
        )
        if not raw_records:
            return []

        citation_result = self._citation_manager.execute(
            {"records": raw_records, "format": self.reference_format}
        )
        formatted = citation_result.get("formatted_references", "")
        return [line.strip() for line in str(formatted).splitlines() if line.strip()]

    def _extract_literature_records(
        self, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        literature_pipeline = get_phase_value(context, "literature_pipeline")
        if isinstance(literature_pipeline, dict):
            records = literature_pipeline.get("records")
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]
        analysis_results = get_phase_value(context, "analysis_results")
        if isinstance(analysis_results, dict):
            literature_pipeline = get_phase_value(
                analysis_results, "literature_pipeline"
            )
            if isinstance(literature_pipeline, dict):
                records = literature_pipeline.get("records")
                if isinstance(records, list):
                    return [record for record in records if isinstance(record, dict)]
        return []

    def _resolve_section_overrides(
        self, context: Dict[str, Any], language: str
    ) -> Dict[str, str]:
        overrides: Dict[str, str] = {}
        for key in _SECTION_ORDER:
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                overrides[key] = value.strip()

        self._parse_sections_payload(context, overrides)

        abstract_override = context.get("abstract")
        if isinstance(abstract_override, str) and abstract_override.strip():
            overrides["abstract"] = abstract_override.strip()
        return overrides

    def _parse_sections_payload(
        self, context: Dict[str, Any], overrides: Dict[str, str]
    ) -> None:
        sections_payload = (
            context.get("sections") or context.get("paper_sections") or []
        )
        if isinstance(sections_payload, dict):
            sections_iterable = [sections_payload]
        else:
            sections_iterable = sections_payload
        for item in sections_iterable:
            if not isinstance(item, dict):
                continue
            section_type = self._normalize_section_type(
                str(
                    item.get("section_type")
                    or item.get("type")
                    or item.get("name")
                    or ""
                )
            )
            content = str(item.get("content") or "").strip()
            if section_type and content:
                overrides[section_type] = content

    def _normalize_section_type(self, raw_value: str) -> str:
        aliases = {
            "intro": "introduction",
            "introduction": "introduction",
            "background": "introduction",
            "methods": "methods",
            "method": "methods",
            "materials": "methods",
            "results": "results",
            "findings": "results",
            "discussion": "discussion",
            "discuss": "discussion",
            "conclusion": "conclusion",
            "conclusions": "conclusion",
        }
        return aliases.get(raw_value.strip().lower(), raw_value.strip().lower())

    def _resolve_abstract(
        self,
        context: Dict[str, Any],
        title: str,
        sections: Sequence[PaperSection],
        language: str,
    ) -> str:
        explicit = context.get("abstract")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

        objective = str(
            context.get("objective") or "围绕中医古籍与现代证据的协同分析"
        ).strip()
        record_count = len(self._extract_literature_records(context))
        evidence_count = len(self._resolve_evidence(context))
        mining = self._resolve_data_mining_result(context)
        rule_count = len(mining.get("association_rules", {}).get("rules", []) or [])
        cluster_count = len(
            mining.get("clustering", {}).get("cluster_summary", []) or []
        )
        methods_line = (
            "本研究采用格式转换、信息统一化、实体抽取、语义分析与数据挖掘联合流程。"
        )
        results_line = f"共整合 {record_count} 条文献记录、{evidence_count} 条证据记录，识别 {rule_count} 条候选关联规则与 {cluster_count} 个聚类模式。"
        conclusion_line = (
            "结果为中医古籍研究提供了结构化证据基础，并支持后续科研论文与图表生成。"
        )

        if language == "en":
            return (
                f"Background: {title} addresses {objective}. "
                f"Methods: A workflow combining format conversion, normalization, entity extraction, semantic analysis, and data mining was applied. "
                f"Results: {record_count} literature records and {evidence_count} evidence records were consolidated, yielding {rule_count} association rules and {cluster_count} cluster patterns. "
                f"Conclusion: The draft provides a structured evidence base for follow-up TCM manuscript development."
            )

        return (
            f"【背景】{title}聚焦于{objective}。\n"
            f"【方法】{methods_line}\n"
            f"【结果】{results_line}\n"
            f"【结论】{conclusion_line}"
        )

    def _generate_section_content(
        self,
        section_type: str,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        builders = {
            "introduction": self._build_introduction,
            "methods": self._build_methods,
            "results": self._build_results,
            "discussion": self._build_discussion,
            "conclusion": self._build_conclusion,
            "formula_interpretation": self._build_formula_interpretation,
            "pattern_analysis": self._build_pattern_analysis,
            "commentary": self._build_commentary,
        }
        builder = builders.get(section_type)
        if builder is None:
            return ""
        return builder(context, title, language, references)

    def _build_introduction(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        objective = str(
            context.get("objective") or "阐明中医古籍证据与现代研究之间的关联"
        ).strip()
        research_domain = str(context.get("research_domain") or "中医古籍研究").strip()
        gap = self._resolve_gap_summary(context)
        record_count = len(self._extract_literature_records(context))
        reference_note = (
            f"当前纳入 {record_count} 条文献记录作为研究背景支持。"
            if record_count
            else "现有研究背景主要来自多源文献与古籍证据。"
        )
        if language == "en":
            return (
                f"This draft manuscript focuses on {research_domain.lower()} and is organized around the objective of {objective}. "
                f"The topic was selected because available literature and classical evidence still show unresolved gaps in evidence integration and interpretation. "
                f"{gap} {reference_note} The study therefore aims to form a reproducible IMRD-style manuscript scaffold for subsequent validation and submission."
            )
        return (
            f"{title}围绕{research_domain}中的核心问题展开，研究目标是{objective}。"
            f"现有古籍知识、现代文献和数据分析结果之间仍存在证据整合不足、研究叙事分散的问题。"
            f"{gap}{reference_note} 因此，本研究尝试构建一套可复用的 IMRD 初稿框架，为后续学术投稿与专家修订提供基础文本。"
        )

    def _build_methods(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        sources = self._resolve_source_list(context)
        figure_paths = self._resolve_figure_paths(context)
        mining = self._resolve_data_mining_result(context)
        analysis_results = self._resolve_analysis_results(context)
        evidence_protocol = (
            analysis_results.get("evidence_protocol")
            if isinstance(analysis_results, dict)
            else {}
        )
        evidence_record_count = (
            len(evidence_protocol.get("evidence_records") or [])
            if isinstance(evidence_protocol, dict)
            else 0
        )
        claim_count = (
            len(evidence_protocol.get("claims") or [])
            if isinstance(evidence_protocol, dict)
            else 0
        )
        mining_methods = list(mining.get("methods_executed") or [])
        protocol_text = self._build_evidence_protocol_text(
            language, evidence_record_count, claim_count
        )
        if language == "en":
            return (
                f"A structured analytical workflow was used for {title}. "
                f"Data sources included {', '.join(sources) if sources else 'classical texts and modern literature databases'}. "
                f"The pipeline covered format conversion, normalization, entity extraction, semantic reasoning, and data mining. "
                f"Applied mining procedures included {', '.join(mining_methods) if mining_methods else 'association analysis and clustering'}. "
                f"All outputs were organized into a manuscript-ready IMRD structure for reproducible reporting."
                f"{protocol_text}"
            )
        methods = [
            "格式转换",
            "信息统一化",
            "实体抽取",
            "语义分析",
            "数据挖掘",
            "结果格式化",
        ]
        if figure_paths:
            methods.append("科研图片生成")
        methods_text = "、".join(methods)
        return (
            f"本研究采用结构化研究流程，对与{title}相关的古籍文本和现代文献进行整合分析。"
            f"数据来源包括{'、'.join(sources) if sources else '古籍文本与现代数据库文献'}。"
            f"整体流程涵盖{methods_text}等步骤，确保原始资料、分析结果与最终初稿之间保持可追溯关联。"
            f"数据挖掘环节主要执行{'、'.join(mining_methods) if mining_methods else '关联规则与聚类分析'}，并将结果纳入论文叙事。"
            f"{protocol_text}"
        )

    def _build_evidence_protocol_text(
        self, language: str, evidence_record_count: int, claim_count: int
    ) -> str:
        if not (evidence_record_count or claim_count):
            return ""
        if language == "en":
            return (
                f" The evidence protocol normalized {evidence_record_count} evidence records"
                f" and {claim_count} candidate claims for downstream writing consistency."
            )
        return (
            f"证据协议层同步规整了 {evidence_record_count} 条证据记录"
            f"和 {claim_count} 条候选论断，便于后续正文引用与复核。"
        )

    def _build_results(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        entities = list(context.get("entities") or [])
        evidence = self._resolve_evidence(context)
        mining = self._resolve_data_mining_result(context)
        analysis_results = self._resolve_analysis_results(context)
        statistical_analysis = self._resolve_statistical_analysis(context)
        evidence_grade_summary = self._resolve_evidence_grade_summary(context)
        llm_analysis_modules = self._resolve_llm_analysis_modules(
            context, analysis_results
        )
        rule_count = len(mining.get("association_rules", {}).get("rules", []) or [])
        cluster_summary = list(
            mining.get("clustering", {}).get("cluster_summary", []) or []
        )
        figure_paths = self._resolve_figure_paths(context)
        graph_evidence_section = self._build_similar_formula_graph_evidence_section(
            context, language
        )
        analysis_note = self._build_analysis_result_note(
            language, statistical_analysis, analysis_results
        )
        evidence_grade_note = self._build_evidence_grade_result_note(
            language, evidence_grade_summary
        )
        llm_context_note = self._build_llm_analysis_context_note(
            language, llm_analysis_modules
        )
        top_cluster_text = self._build_top_cluster_text(cluster_summary)
        base = self._assemble_results_text(
            language,
            len(entities),
            len(evidence),
            rule_count,
            cluster_summary,
            top_cluster_text,
            analysis_note,
            evidence_grade_note,
            llm_context_note,
            figure_paths,
        )
        return (
            f"{base}\n\n{graph_evidence_section}".strip()
            if graph_evidence_section
            else base
        )

    def _build_top_cluster_text(self, cluster_summary: List[Any]) -> str:
        if not cluster_summary:
            return ""
        first_cluster = cluster_summary[0]
        top_items = [
            item.get("item")
            for item in list(first_cluster.get("top_items", []) or [])[:3]
            if item.get("item")
        ]
        if top_items:
            return f"其中最主要的聚类特征集中在{'、'.join(top_items)}。"
        return ""

    def _assemble_results_text(
        self,
        language: str,
        entity_count: int,
        evidence_count: int,
        rule_count: int,
        cluster_summary: List[Any],
        top_cluster_text: str,
        analysis_note: str,
        evidence_grade_note: str,
        llm_context_note: str,
        figure_paths: List[str],
    ) -> str:
        if language == "en":
            return (
                f"The integrated workflow identified {entity_count} entities and consolidated {evidence_count} evidence records. "
                f"Data mining yielded {rule_count} association rules and {len(cluster_summary)} cluster summaries. "
                f"{top_cluster_text or ''} {analysis_note} {evidence_grade_note} {llm_context_note} {('Figures were generated to support the narrative interpretation.' if figure_paths else '')}".strip()
            )
        figure_note = "；相关结果已与图表输出对齐" if figure_paths else ""
        return (
            f"研究结果显示，当前流程共汇总 {entity_count} 个核心实体、{evidence_count} 条证据记录。"
            f"数据挖掘模块进一步识别出 {rule_count} 条关联规则和 {len(cluster_summary)} 个聚类摘要。"
            f"{top_cluster_text}{analysis_note}{evidence_grade_note}{llm_context_note}{figure_note} 这些结果为后续结果展示、图表引用和讨论部分的证据解释提供了结构化支撑。"
        )

    def _build_similar_formula_graph_evidence_section(
        self, context: Dict[str, Any], language: str
    ) -> str:
        summary = self._resolve_similar_formula_graph_evidence_summary(context)
        matches = list(summary.get("matches") or [])
        if not matches:
            return ""

        top_matches = matches[:3]
        heading = (
            "Class-like Formula Graph Evidence" if language == "en" else "类方图谱证据"
        )
        lines = [heading]
        for match in top_matches:
            lines.append(self._format_formula_graph_match(match, language))
        return "\n\n".join(lines)

    def _format_formula_graph_match(self, match: Dict[str, Any], language: str) -> str:
        score = float(match.get("evidence_score", 0.0) or 0.0)
        similarity_score = match.get("similarity_score")
        formula_a = match.get("formula_name", "")
        formula_b = match.get("similar_formula_name", "")
        if language == "en":
            shared_herbs = (
                ", ".join(
                    str(item) for item in list(match.get("shared_herbs") or []) if item
                )
                or "none"
            )
            shared_syndromes = (
                ", ".join(
                    str(item)
                    for item in list(match.get("shared_syndromes") or [])
                    if item
                )
                or "none"
            )
            similarity_text = (
                f", similarity score {similarity_score:.2f}"
                if isinstance(similarity_score, (int, float))
                else ""
            )
            return f"- {formula_a} vs {formula_b}: graph evidence score {score:.2f}{similarity_text}; shared herbs {shared_herbs}; shared syndromes {shared_syndromes}."
        shared_herbs = (
            "、".join(
                str(item) for item in list(match.get("shared_herbs") or []) if item
            )
            or "暂无"
        )
        shared_syndromes = (
            "、".join(
                str(item) for item in list(match.get("shared_syndromes") or []) if item
            )
            or "暂无"
        )
        similarity_text = (
            f"，embedding 相似度 {float(similarity_score):.2f}"
            if isinstance(similarity_score, (int, float))
            else ""
        )
        return f"- {formula_a} 与 {formula_b} 的图谱证据分数为 {score:.2f}{similarity_text}；共享药物包括 {shared_herbs}；共享证候包括 {shared_syndromes}。"

    def _build_discussion(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        hypothesis = self._resolve_hypothesis(context)
        mining = self._resolve_data_mining_result(context)
        quality_metrics = self._resolve_quality_metrics(context)
        recommendations = self._resolve_recommendations(context)
        evidence_grade_summary = self._resolve_evidence_grade_summary(context)
        llm_analysis_modules = self._resolve_llm_analysis_modules(context)
        association_rules = list(
            mining.get("association_rules", {}).get("rules", []) or []
        )
        high_rule = association_rules[0] if association_rules else None
        rule_text = ""
        if high_rule:
            antecedent = "、".join(high_rule.get("antecedent", []))
            consequent = "、".join(high_rule.get("consequent", []))
            rule_text = (
                f"关联规则提示 {antecedent} 与 {consequent} 之间存在稳定共现关系。"
            )
        limitation = self._resolve_limitations_text(context)
        hypothesis_text = ""
        if hypothesis:
            hypothesis_text = f"已有假设结果进一步提示：{hypothesis}。"
        hypothesis_audit_text = self._build_hypothesis_audit_text(context, language)
        evidence_grade_text = self._build_evidence_grade_discussion_text(
            language, evidence_grade_summary
        )
        quality_text = self._build_quality_discussion_text(
            language, quality_metrics, recommendations
        )
        llm_discussion_text = self._build_llm_analysis_discussion_text(
            language, llm_analysis_modules
        )
        graph_citation_text = self._build_graph_citation_discussion_text(
            language, context
        )
        if language == "en":
            return (
                f"The manuscript draft suggests that integrated evidence processing can improve coherence between classical knowledge and modern analysis. "
                f"{rule_text} {hypothesis_text}{hypothesis_audit_text}{evidence_grade_text}{quality_text}{llm_discussion_text}{graph_citation_text} A key limitation is that {limitation}"
            )
        return (
            f"讨论部分表明，将古籍知识、现代文献与结构化分析结果整合到统一写作框架中，有助于提升科研叙事的一致性与可追溯性。"
            f"{rule_text}{hypothesis_text}{hypothesis_audit_text}{evidence_grade_text}{quality_text}{llm_discussion_text}{graph_citation_text}{limitation} 因此，本初稿更适合作为投稿前的研究骨架和专家协作底稿，而非最终定稿。"
        )

    def _build_conclusion(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        objective = str(
            context.get("objective") or "构建可复用的中医古籍研究写作流程"
        ).strip()
        if language == "en":
            return f"In conclusion, this IMRD draft operationalizes {objective} and provides a manuscript-ready scaffold for subsequent expert revision, figure integration, and journal submission."
        return f"综上，本服务围绕“{objective}”生成了可直接修订的 IMRD 论文初稿，能够把证据、数据挖掘结果与图表产物汇聚为统一稿件，为后续学术投稿提供基础。"

    # ── 中医论文模板（template="tcm" 启用） ────────────────────────────

    def _coerce_template(self, raw: Any) -> str:
        value = str(raw or "").strip().lower()
        if value in SUPPORTED_PAPER_TEMPLATES:
            return value
        return PAPER_TEMPLATE_DEFAULT

    def _build_formula_interpretation(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        """方义阐释：从上下文挑选君臣佐使药味与功效，给出结构化阐释。"""
        formulas = list(context.get("formulas") or [])
        herbs = list(context.get("herbs") or [])
        primary_formula = ""
        if formulas:
            first = formulas[0]
            if isinstance(first, dict):
                primary_formula = str(
                    first.get("name") or first.get("canonical") or ""
                ).strip()
            else:
                primary_formula = str(first).strip()
        herb_names: List[str] = []
        for item in herbs:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("canonical") or "").strip()
            else:
                name = str(item or "").strip()
            if name and name not in herb_names:
                herb_names.append(name)
        head_herbs = (
            "、".join(herb_names[:5]) if herb_names else "（待补充君臣佐使药味）"
        )
        if language == "en":
            formula_text = primary_formula or "the principal formula"
            return (
                f"This appendix interprets the compositional intent of {formula_text}. "
                f"Sovereign and minister herbs include {head_herbs}. The interpretation traces "
                f"how each herb addresses the targeted pattern, supporting the IMRD discussion above."
            )
        formula_text = primary_formula or "本研究主方"
        return (
            f"本节围绕『{formula_text}』展开方义阐释，梳理君臣佐使的配伍意图。"
            f"主要药味为：{head_herbs}。各药协同针对所论证候，与正文讨论形成互证。"
        )

    def _build_pattern_analysis(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        """证治分析：列出 syndrome → 治法/方剂 映射。"""
        syndromes = list(context.get("syndromes") or [])
        if not syndromes:
            evidence_records = self._resolve_evidence(context) or []
            for rec in evidence_records:
                if isinstance(rec, dict) and rec.get("syndrome"):
                    syndromes.append(rec.get("syndrome"))
        seen: List[str] = []
        for s in syndromes:
            text = str(s.get("name") if isinstance(s, dict) else s or "").strip()
            if text and text not in seen:
                seen.append(text)
        if not seen:
            seen = ["（待补充核心证候）"]
        treatment_hint = str(context.get("treatment_principle") or "辨证论治").strip()
        if language == "en":
            return (
                f"Pattern analysis groups the identified syndromes ({', '.join(seen)}) "
                f"and aligns each with the corresponding treatment principle: {treatment_hint}. "
                f"This appendix supports the discussion section by making the pattern-treatment "
                f"mapping explicit."
            )
        return (
            f"本节对识别到的证候 {('、'.join(seen))} 逐一进行证治分析，"
            f"对应治法以『{treatment_hint}』为纲，与讨论部分相互印证。"
        )

    def _build_commentary(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        """按语：研究者立场说明 + 取舍理由 + 后续研究展望。"""
        commentary_text = str(context.get("commentary") or "").strip()
        if commentary_text:
            return commentary_text
        objective = str(context.get("objective") or "本研究目标").strip()
        limitation = str(self._resolve_limitations_text(context) or "").strip()
        if language == "en":
            return (
                f"Commentary: this draft accepts existing classical interpretations as primary evidence "
                f"while prioritizing reproducibility for {objective}. {limitation} "
                f"Future revisions should incorporate expert clinical validation."
            )
        return (
            f"按语：本研究在『{objective}』的目标下，先以经典文献为基线，再结合现代证据加以校核。"
            f"{limitation}后续修订建议引入临床专家进一步验证与补订。"
        )

    def _resolve_gap_summary(self, context: Dict[str, Any]) -> str:
        gap_payload = context.get("gap_analysis") or context.get("clinical_gap") or {}
        if isinstance(gap_payload, dict):
            summary = (
                gap_payload.get("summary")
                or gap_payload.get("gap_summary")
                or gap_payload.get("description")
            )
            if isinstance(summary, str) and summary.strip():
                return summary.strip() + (
                    "。" if not summary.strip().endswith("。") else ""
                )
        return (
            "当前研究仍需进一步明确古籍理论、现代证据与可验证科研问题之间的映射路径。"
        )

    def _resolve_source_list(self, context: Dict[str, Any]) -> List[str]:
        sources = []
        for record in self._extract_literature_records(context):
            source = (
                record.get("source") or record.get("journal") or record.get("venue")
            )
            text = str(source or "").strip()
            if text and text not in sources:
                sources.append(text)
        for source in context.get("sources") or []:
            text = str(source or "").strip()
            if text and text not in sources:
                sources.append(text)
        return sources[:6]

    def _resolve_output_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        output_data = get_phase_value(context, "output_data")
        return output_data if isinstance(output_data, dict) else {}

    def _resolve_research_artifact(self, context: Dict[str, Any]) -> Dict[str, Any]:
        research_artifact = get_phase_value(context, "research_artifact")
        if isinstance(research_artifact, dict):
            return research_artifact

        output_data = self._resolve_output_data(context)
        nested = get_phase_value(output_data, "research_artifact")
        return nested if isinstance(nested, dict) else {}

    def _resolve_hypothesis(self, context: Dict[str, Any]) -> str:
        hypothesis = (
            get_phase_value(context, "hypothesis")
            or get_phase_value(context, "hypotheses")
            or []
        )
        if isinstance(hypothesis, str):
            return hypothesis.strip()
        if isinstance(hypothesis, dict):
            return str(
                hypothesis.get("title") or hypothesis.get("statement") or ""
            ).strip()
        if isinstance(hypothesis, list) and hypothesis:
            first = hypothesis[0]
            if isinstance(first, dict):
                return str(first.get("title") or first.get("statement") or "").strip()
            return str(first).strip()
        research_artifact = self._resolve_research_artifact(context)
        if isinstance(research_artifact, dict) and research_artifact:
            return self._resolve_hypothesis(research_artifact)
        return ""

    def _build_hypothesis_audit_text(
        self, context: Dict[str, Any], language: str
    ) -> str:
        summary = self._resolve_hypothesis_audit_summary(context)
        if not summary:
            return ""

        mechanism_score = float(summary.get("selected_mechanism_completeness") or 0.0)
        merged_sources = [
            str(item).strip()
            for item in (summary.get("merged_sources") or [])
            if str(item).strip()
        ]
        relationship_count = int(summary.get("relationship_count") or 0)

        if language == "en":
            source_text = (
                ", ".join(merged_sources)
                if merged_sources
                else "multiple evidence channels"
            )
            relation_text = (
                f" across {relationship_count} audited relations"
                if relationship_count
                else ""
            )
            return (
                f"Audit evidence indicates a mechanism-chain completeness score of {mechanism_score:.2f}"
                f" with merged relation sources from {source_text}{relation_text}. "
            )

        source_text = "、".join(merged_sources) if merged_sources else "多源关系证据"
        relation_text = (
            f"，共覆盖 {relationship_count} 条审计关系" if relationship_count else ""
        )
        return (
            f"假设审计显示，当前优先假设的机制链完整性评分为 {mechanism_score:.2f}，"
            f"关系证据融合自 {source_text}{relation_text}。"
        )

    def _resolve_hypothesis_audit_summary(
        self, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        direct = get_phase_value(context, "hypothesis_audit_summary")
        if isinstance(direct, dict) and direct:
            return direct

        research_artifact = self._resolve_research_artifact(context)
        if isinstance(research_artifact, dict):
            nested = research_artifact.get("hypothesis_audit_summary")
            if isinstance(nested, dict) and nested:
                return nested

        output_data = self._resolve_output_data(context)
        if isinstance(output_data, dict):
            artifact = get_phase_value(output_data, "research_artifact")
            if isinstance(artifact, dict):
                nested = artifact.get("hypothesis_audit_summary")
                if isinstance(nested, dict) and nested:
                    return nested
        return {}

    def _resolve_evidence_grade_summary(
        self, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        direct = get_phase_value(context, "evidence_grade_summary")
        if isinstance(direct, dict) and direct:
            return direct

        analysis_results = self._resolve_analysis_results(context)
        resolved = self._extract_evidence_grade_summary(analysis_results)
        if resolved:
            return resolved

        research_artifact = get_phase_value(context, "research_artifact")
        if isinstance(research_artifact, dict):
            resolved = self._extract_evidence_grade_summary(research_artifact)
            if resolved:
                return resolved

        output_data = self._resolve_output_data(context)
        if isinstance(output_data, dict):
            resolved = self._extract_evidence_grade_summary(
                get_phase_value(output_data, "analysis_results")
            )
            if resolved:
                return resolved
            resolved = self._extract_evidence_grade_summary(
                get_phase_value(output_data, "research_artifact")
            )
            if resolved:
                return resolved
        return {}

    def _extract_evidence_grade_summary(self, container: Any) -> Dict[str, Any]:
        if not isinstance(container, dict) or not container:
            return {}

        summary = container.get("evidence_grade_summary")
        if isinstance(summary, dict) and summary:
            return dict(summary)

        evidence_grade = container.get("evidence_grade")
        if isinstance(evidence_grade, dict) and evidence_grade:
            return self._normalize_evidence_grade_summary(evidence_grade)

        statistical_analysis = container.get("statistical_analysis")
        if isinstance(statistical_analysis, dict):
            nested = self._extract_evidence_grade_summary(statistical_analysis)
            if nested:
                return nested
        return {}

    def _normalize_evidence_grade_summary(
        self, evidence_grade: Dict[str, Any]
    ) -> Dict[str, Any]:
        bias_distribution: Dict[str, int] = {}
        for key, value in (evidence_grade.get("bias_risk_distribution") or {}).items():
            try:
                bias_distribution[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

        summary_lines = [
            str(item).strip()
            for item in (evidence_grade.get("summary") or [])
            if str(item).strip()
        ]

        try:
            overall_score = round(float(evidence_grade.get("overall_score") or 0.0), 4)
        except (TypeError, ValueError):
            overall_score = 0.0

        study_results = evidence_grade.get("study_results") or []
        study_count = evidence_grade.get("study_count") or len(study_results)
        try:
            normalized_study_count = int(study_count)
        except (TypeError, ValueError):
            normalized_study_count = 0

        return {
            "overall_grade": str(evidence_grade.get("overall_grade") or ""),
            "overall_score": overall_score,
            "study_count": normalized_study_count,
            "bias_risk_distribution": bias_distribution,
            "summary": summary_lines,
        }

    def _resolve_evidence(self, context: Dict[str, Any]) -> List[Any]:
        for source in self._iter_evidence_sources(context):
            if isinstance(source, list):
                return source
        return []

    def _iter_evidence_sources(self, context: Dict[str, Any]):
        reasoning = self._resolve_reasoning_results(context)
        if isinstance(reasoning, dict):
            yield reasoning.get("evidence_records")
        analysis_results = self._resolve_analysis_results(context)
        if isinstance(analysis_results, dict):
            evidence_protocol = analysis_results.get("evidence_protocol")
            if isinstance(evidence_protocol, dict):
                yield evidence_protocol.get("evidence_records")
        nested_reasoning = (
            analysis_results.get("reasoning_results", {})
            if isinstance(analysis_results, dict)
            else {}
        )
        if isinstance(nested_reasoning, dict):
            yield nested_reasoning.get("evidence_records")
        research_artifact = self._resolve_research_artifact(context)
        if isinstance(research_artifact, dict):
            yield research_artifact.get("evidence")
        yield get_phase_value(context, "evidence", []) or []

    def _resolve_reasoning_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        phase_results = get_phase_results(context)
        nested_reasoning = phase_results.get("reasoning_results")
        if isinstance(nested_reasoning, dict):
            return dict(nested_reasoning)

        if is_phase_result_payload(context):
            return {}

        direct_reasoning = context.get("reasoning_results")
        if isinstance(direct_reasoning, dict):
            return dict(direct_reasoning)
        return {}

    def _resolve_data_mining_result(self, context: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("data_mining_result", "data_mining", "mining_result"):
            value = get_phase_value(context, key)
            if isinstance(value, dict):
                return value
        research_artifact = self._resolve_research_artifact(context)
        if isinstance(research_artifact, dict):
            value = research_artifact.get("data_mining_result")
            if isinstance(value, dict):
                return value
        analysis_results = get_phase_value(context, "analysis_results")
        if isinstance(analysis_results, dict):
            value = get_phase_value(analysis_results, "data_mining_result")
            if isinstance(value, dict):
                return value
        output_data = self._resolve_output_data(context)
        if isinstance(output_data, dict):
            research_artifact = get_phase_value(output_data, "research_artifact")
            if isinstance(research_artifact, dict):
                value = research_artifact.get("data_mining_result")
                if isinstance(value, dict):
                    return value
        return {}

    def _resolve_analysis_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        analysis_results = get_phase_value(context, "analysis_results")
        if isinstance(analysis_results, dict):
            return analysis_results
        output_data = self._resolve_output_data(context)
        if isinstance(output_data, dict):
            nested = get_phase_value(output_data, "analysis_results")
            if isinstance(nested, dict):
                return nested
        return {}

    def _resolve_llm_analysis_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = get_phase_value(context, "llm_analysis_context")
        if isinstance(direct, dict) and direct:
            return direct

        analysis_results = self._resolve_analysis_results(context)
        nested = (
            analysis_results.get("llm_analysis_context")
            if isinstance(analysis_results, dict)
            else None
        )
        if isinstance(nested, dict) and nested:
            return nested
        return {}

    def _resolve_llm_analysis_modules(
        self,
        context: Dict[str, Any],
        analysis_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if analysis_results is None:
            analysis_results = self._resolve_analysis_results(context)

        llm_analysis_context = self._resolve_llm_analysis_context(context)
        direct_modules = (
            llm_analysis_context.get("analysis_modules")
            if isinstance(llm_analysis_context, dict)
            else None
        )

        containers: List[Any] = [
            direct_modules,
            context,
            analysis_results,
        ]
        research_artifact = self._resolve_research_artifact(context)
        if isinstance(research_artifact, dict):
            containers.append(research_artifact)
        output_data = self._resolve_output_data(context)
        if isinstance(output_data, dict):
            containers.append(output_data)
            nested_analysis = get_phase_value(output_data, "analysis_results")
            if isinstance(nested_analysis, dict):
                containers.append(nested_analysis)

        modules: Dict[str, Any] = {}
        for module_name, aliases in _LLM_ANALYSIS_MODULE_ALIASES.items():
            resolved = self._resolve_module_from_containers(containers, aliases)
            modules[module_name] = resolved if resolved is not None else {}
        return modules

    def _resolve_module_from_containers(
        self,
        containers: Sequence[Any],
        field_names: Sequence[str],
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
                return self._clone_analysis_payload(value)
        return None

    def _clone_analysis_payload(self, value: Any) -> Any:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        return value

    def _has_analysis_payload(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (dict, list, tuple, set)):
            return bool(value)
        return True

    def _build_llm_analysis_context_note(
        self,
        language: str,
        analysis_modules: Dict[str, Any],
    ) -> str:
        if not isinstance(analysis_modules, dict) or not analysis_modules:
            return ""

        populated = [
            module_name
            for module_name, module_value in analysis_modules.items()
            if self._has_analysis_payload(module_value)
        ]
        if not populated:
            return ""

        total_count = len(_LLM_ANALYSIS_MODULE_ALIASES)
        if language == "en":
            preview = ", ".join(
                module_name.replace("_", " ") for module_name in populated[:4]
            )
            if len(populated) > 4:
                preview = f"{preview}, ..."
            return (
                f"LLM analysis context covered {len(populated)}/{total_count} analytical modules"
                f" ({preview}), grounding the manuscript content in real analysis outputs."
            )

        labels = [
            _LLM_ANALYSIS_MODULE_LABELS_ZH.get(module_name, module_name)
            for module_name in populated[:4]
        ]
        label_text = "、".join(labels)
        if len(populated) > 4:
            label_text = f"{label_text}等模块"
        return (
            f"LLM 分析上下文已覆盖 {len(populated)}/{total_count} 个分析模块（{label_text}），"
            "当前段落叙述基于真实分析结果。"
        )

    def _build_llm_analysis_discussion_text(
        self,
        language: str,
        analysis_modules: Dict[str, Any],
    ) -> str:
        has_summary = self._has_analysis_payload(
            (analysis_modules or {}).get("summary_analysis")
        )
        has_scoring = self._has_analysis_payload(
            (analysis_modules or {}).get("research_scoring_panel")
        )
        if not has_summary and not has_scoring:
            return ""

        if language == "en":
            return " The discussion also cross-checked summary analysis and research scoring outputs to keep claims aligned with quantitative evidence."
        return "讨论还结合总结分析与研究评分结果对关键论断进行了交叉校验，确保结论与量化证据一致。"

    def _build_graph_citation_discussion_text(
        self,
        language: str,
        context: Dict[str, Any],
    ) -> str:
        publish_graph_context = self._resolve_publish_graph_context(context)
        if not publish_graph_context:
            return ""
        trace_counts = publish_graph_context.get("trace_counts")
        if not isinstance(trace_counts, dict):
            traces = publish_graph_context.get("traces")
            trace_counts = {
                trace_type: len(values)
                for trace_type, values in (traces or {}).items()
                if isinstance(values, list)
            }
        evidence_claim_count = int(trace_counts.get("EvidenceClaim") or 0)
        version_witness_count = int(trace_counts.get("VersionWitness") or 0)
        citation_record_count = int(trace_counts.get("CitationRecord") or 0)
        unsupported_count = int(
            publish_graph_context.get("unsupported_claim_warning_count") or 0
        )
        if (
            evidence_claim_count <= 0
            and version_witness_count <= 0
            and citation_record_count <= 0
            and unsupported_count <= 0
        ):
            return ""

        if language == "en":
            warning_text = (
                f" {unsupported_count} manuscript claims still lack graph-backed support and should be reviewed before submission."
                if unsupported_count
                else ""
            )
            return (
                f" Graph traceability links {evidence_claim_count} evidence claims, "
                f"{version_witness_count} version witnesses, and {citation_record_count} citation records to the draft discussion."
                f"{warning_text}"
            )

        warning_text = (
            f"仍有 {unsupported_count} 条论断缺少图谱证据支撑，投稿前需进一步复核。"
            if unsupported_count
            else ""
        )
        return (
            f"图谱引用追溯已将 {evidence_claim_count} 条 EvidenceClaim、"
            f"{version_witness_count} 条 VersionWitness 与 {citation_record_count} 条 CitationRecord "
            f"纳入讨论依据。{warning_text}"
        )

    def _resolve_publish_graph_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = get_phase_value(context, "publish_graph_context")
        if isinstance(direct, dict) and direct:
            return direct

        analysis_results = self._resolve_analysis_results(context)
        nested = get_phase_value(analysis_results, "publish_graph_context")
        if isinstance(nested, dict) and nested:
            return nested

        research_artifact = get_phase_value(context, "research_artifact")
        if isinstance(research_artifact, dict):
            nested = get_phase_value(research_artifact, "publish_graph_context")
            if isinstance(nested, dict) and nested:
                return nested
        return {}

    def _resolve_graph_rag_citations(
        self,
        context: Dict[str, Any],
        publish_graph_context: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        direct = get_phase_value(context, "graph_rag_citations")
        if isinstance(direct, list):
            return [dict(item) for item in direct if isinstance(item, dict)]

        graph_context = publish_graph_context or self._resolve_publish_graph_context(
            context
        )
        nested = (
            graph_context.get("graph_rag_citations")
            if isinstance(graph_context, dict)
            else []
        )
        if isinstance(nested, list):
            return [dict(item) for item in nested if isinstance(item, dict)]
        return []

    def _resolve_statistical_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        analysis_results = self._resolve_analysis_results(context)
        statistical_analysis = analysis_results.get("statistical_analysis")
        if isinstance(statistical_analysis, dict):
            return statistical_analysis
        return {}

    def _resolve_quality_metrics(self, context: Dict[str, Any]) -> Dict[str, Any]:
        quality_metrics = get_phase_value(context, "quality_metrics")
        if isinstance(quality_metrics, dict):
            return quality_metrics
        analysis_results = self._resolve_analysis_results(context)
        quality_metrics = analysis_results.get("quality_metrics")
        if isinstance(quality_metrics, dict):
            return quality_metrics
        output_data = self._resolve_output_data(context)
        if isinstance(output_data, dict):
            nested = get_phase_value(output_data, "quality_metrics")
            if isinstance(nested, dict):
                return nested
        return {}

    def _resolve_recommendations(self, context: Dict[str, Any]) -> List[str]:
        recommendations = get_phase_value(context, "recommendations")
        if isinstance(recommendations, list):
            return [str(item).strip() for item in recommendations if str(item).strip()]
        analysis_results = self._resolve_analysis_results(context)
        recommendations = (
            analysis_results.get("recommendations")
            if isinstance(analysis_results, dict)
            else None
        )
        if isinstance(recommendations, list):
            return [str(item).strip() for item in recommendations if str(item).strip()]
        output_data = self._resolve_output_data(context)
        nested_recommendations = (
            get_phase_value(output_data, "recommendations")
            if isinstance(output_data, dict)
            else None
        )
        if isinstance(nested_recommendations, list):
            return [
                str(item).strip()
                for item in nested_recommendations
                if str(item).strip()
            ]
        return []

    def _resolve_limitations_text(self, context: Dict[str, Any]) -> str:
        statistical_analysis = self._resolve_statistical_analysis(context)
        raw_limitations = (
            statistical_analysis.get("limitations")
            if isinstance(statistical_analysis, dict)
            else None
        )
        if not raw_limitations and not is_phase_result_payload(context):
            raw_limitations = context.get("limitations")

        if isinstance(raw_limitations, str):
            limitation_text = raw_limitations.strip()
        elif isinstance(raw_limitations, (list, tuple, set)):
            limitation_text = "；".join(
                str(item).strip() for item in raw_limitations if str(item).strip()
            )
        else:
            limitation_text = ""

        if not limitation_text:
            limitation_text = (
                "当前结果仍依赖自动化抽取与结构化规则，尚需结合专家复核与外部验证"
            )
        if not limitation_text.endswith(("。", ".")):
            limitation_text = f"{limitation_text}。"
        return limitation_text

    def _build_analysis_result_note(
        self,
        language: str,
        statistical_analysis: Dict[str, Any],
        analysis_results: Dict[str, Any],
    ) -> str:
        if not isinstance(statistical_analysis, dict):
            statistical_analysis = {}
        interpretation = str(statistical_analysis.get("interpretation") or "").strip()
        p_value = statistical_analysis.get("p_value")
        confidence_level = statistical_analysis.get("confidence_level")
        effect_size = statistical_analysis.get("effect_size")
        significance = statistical_analysis.get("statistical_significance")

        has_signal = (
            significance is True
            or p_value is not None
            or confidence_level is not None
            or effect_size is not None
        )
        metric_bits = self._format_statistical_metric_bits(
            language, p_value, confidence_level, effect_size
        )

        fragments: List[str] = []
        if language == "en":
            if has_signal:
                fragments.append(
                    "Statistical analysis suggested a meaningful signal"
                    + (f" ({', '.join(metric_bits)})" if metric_bits else "")
                    + "."
                )
            if interpretation:
                fragments.append(f"Interpretation: {interpretation}.")
            return " ".join(fragments).strip()

        if has_signal:
            fragments.append(
                "统计分析提示当前结果具有稳定信号"
                + (f"（{'，'.join(metric_bits)}）" if metric_bits else "")
                + "。"
            )
        if interpretation:
            fragments.append(f"综合解释认为：{interpretation}。")
        return "".join(fragments).strip()

    def _format_statistical_metric_bits(
        self,
        language: str,
        p_value: Any,
        confidence_level: Any,
        effect_size: Any,
    ) -> List[str]:
        bits: List[str] = []
        if p_value is not None:
            bits.append(f"p={p_value}")
        if confidence_level is not None:
            bits.append(
                f"confidence level {confidence_level}"
                if language == "en"
                else f"置信水平 {confidence_level}"
            )
        if effect_size is not None:
            bits.append(
                f"effect size {effect_size}"
                if language == "en"
                else f"效应量 {effect_size}"
            )
        return bits

    def _build_evidence_grade_result_note(
        self,
        language: str,
        evidence_grade_summary: Dict[str, Any],
    ) -> str:
        if not isinstance(evidence_grade_summary, dict) or not evidence_grade_summary:
            return ""

        study_count = int(evidence_grade_summary.get("study_count") or 0)
        if study_count <= 0:
            return ""

        overall_grade_raw = (
            str(evidence_grade_summary.get("overall_grade") or "").strip().lower()
        )
        overall_grade = self._format_grade_label(overall_grade_raw, language)
        try:
            overall_score = float(evidence_grade_summary.get("overall_score") or 0.0)
        except (TypeError, ValueError):
            overall_score = 0.0

        bias_bits = self._format_bias_distribution_bits(
            evidence_grade_summary, language
        )
        return self._assemble_evidence_grade_sentence(
            language, study_count, overall_grade, overall_score, bias_bits
        )

    def _format_bias_distribution_bits(
        self, evidence_grade_summary: Dict[str, Any], language: str
    ) -> List[str]:
        bits: List[str] = []
        for key, value in sorted(
            (evidence_grade_summary.get("bias_risk_distribution") or {}).items()
        ):
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            if language == "en":
                bits.append(f"{count} {key}")
            else:
                bits.append(
                    f"{self._format_bias_label(str(key), language)}风险 {count} 项"
                )
        return bits

    def _assemble_evidence_grade_sentence(
        self,
        language: str,
        study_count: int,
        overall_grade: str,
        overall_score: float,
        bias_bits: List[str],
    ) -> str:
        if language == "en":
            sentence = f"GRADE assessment across {study_count} studies indicated overall evidence certainty of {overall_grade}"
            if overall_score > 0:
                sentence += f" (score {overall_score:.2f})"
            sentence += "."
            if bias_bits:
                sentence += f" Bias distribution: {', '.join(bias_bits)}."
            return sentence

        sentence = f"GRADE 证据分级显示，纳入 {study_count} 项研究后整体证据等级为{overall_grade}"
        if overall_score > 0:
            sentence += f"，平均评分 {overall_score:.2f}"
        sentence += "。"
        if bias_bits:
            sentence += f"偏倚风险分布为{'、'.join(bias_bits)}。"
        return sentence

    def _build_evidence_grade_discussion_text(
        self,
        language: str,
        evidence_grade_summary: Dict[str, Any],
    ) -> str:
        if not isinstance(evidence_grade_summary, dict) or not evidence_grade_summary:
            return ""

        study_count = int(evidence_grade_summary.get("study_count") or 0)
        if study_count <= 0:
            return ""

        overall_grade = (
            str(evidence_grade_summary.get("overall_grade") or "").strip().lower()
        )
        if language == "en":
            if overall_grade in {"high", "moderate"}:
                return " The GRADE profile suggests that the current narrative is supported by at least moderate evidence certainty."
            return " The GRADE profile suggests that the current narrative remains constrained by low-certainty evidence and should be interpreted cautiously."

        if overall_grade in {"high", "moderate"}:
            return "GRADE 证据谱提示当前结论已获得至少中等强度的文献支持，但仍需持续跟踪高偏倚来源。"
        return (
            "GRADE 证据谱提示当前结论仍受低确定性证据限制，后续应优先补充更高质量研究。"
        )

    def _build_quality_discussion_text(
        self,
        language: str,
        quality_metrics: Dict[str, Any],
        recommendations: List[str],
    ) -> str:
        confidence_score = (
            quality_metrics.get("confidence_score")
            if isinstance(quality_metrics, dict)
            else None
        )
        completeness = (
            quality_metrics.get("completeness")
            if isinstance(quality_metrics, dict)
            else None
        )
        recommendation_text = "；".join(recommendations[:2]) if recommendations else ""
        metric_bits = self._format_quality_metric_bits(
            language, confidence_score, completeness
        )
        return self._assemble_quality_discussion(
            language, metric_bits, recommendation_text
        )

    def _format_quality_metric_bits(
        self, language: str, confidence_score: Any, completeness: Any
    ) -> List[str]:
        bits: List[str] = []
        if confidence_score is not None:
            bits.append(
                f"confidence score {confidence_score}"
                if language == "en"
                else f"置信分数 {confidence_score}"
            )
        if completeness is not None:
            bits.append(
                f"completeness {completeness}"
                if language == "en"
                else f"完整度 {completeness}"
            )
        return bits

    def _assemble_quality_discussion(
        self, language: str, metric_bits: List[str], recommendation_text: str
    ) -> str:
        if language == "en":
            parts: List[str] = []
            if metric_bits:
                parts.append(f"Quality review indicated {' and '.join(metric_bits)}.")
            if recommendation_text:
                parts.append(f"Recommended next steps include {recommendation_text}.")
            return (" " + " ".join(parts)).rstrip() if parts else ""
        parts = []
        if metric_bits:
            parts.append(f"质量评估显示当前输出的{'、'.join(metric_bits)}。")
        if recommendation_text:
            parts.append(f"后续建议优先关注：{recommendation_text}。")
        return "".join(parts)

    def _format_grade_label(self, grade: str, language: str) -> str:
        if language == "en":
            return grade.replace("_", " ") if grade else "unknown"
        return _GRADE_LABELS_ZH.get(grade, grade or "未知")

    def _format_bias_label(self, risk_level: str, language: str) -> str:
        if language == "en":
            return risk_level
        return _BIAS_LABELS_ZH.get(risk_level, risk_level)

    def _resolve_similar_formula_graph_evidence_summary(
        self, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        value = get_phase_value(context, "similar_formula_graph_evidence_summary")
        if isinstance(value, dict):
            return value

        research_artifact = self._resolve_research_artifact(context)
        if isinstance(research_artifact, dict):
            value = research_artifact.get("similar_formula_graph_evidence_summary")
            if isinstance(value, dict):
                return value

        for container in (
            self._resolve_analysis_results(context),
            self._resolve_output_data(context),
        ):
            if isinstance(container, dict):
                nested_artifact = get_phase_value(container, "research_artifact")
                if isinstance(nested_artifact, dict):
                    value = nested_artifact.get(
                        "similar_formula_graph_evidence_summary"
                    )
                    if isinstance(value, dict):
                        return value
        return {}

    def _resolve_figure_paths(self, context: Dict[str, Any]) -> List[str]:
        if isinstance(context.get("figure_paths"), list):
            return [
                str(path).strip()
                for path in context.get("figure_paths", [])
                if str(path).strip()
            ]
        figure_result = context.get("figure_result") or {}
        if isinstance(figure_result, dict) and isinstance(
            figure_result.get("figure_paths"), list
        ):
            return [
                str(path).strip()
                for path in figure_result.get("figure_paths", [])
                if str(path).strip()
            ]
        return []

    def _section_title(self, section_type: str, language: str) -> str:
        if language == "en":
            return _EN_SECTION_TITLES.get(section_type, section_type.title())
        return _ZH_SECTION_TITLES.get(section_type, section_type.title())

    def _section_reference_markers(
        self, section_type: str, references: Sequence[str]
    ) -> List[str]:
        if not references:
            return []
        if section_type == "introduction":
            return list(references[: min(3, len(references))])
        if section_type in {"results", "discussion"}:
            return list(references[: min(2, len(references))])
        return list(references[:1])

    def _normalize_formats(self, raw_formats: Any) -> List[str]:
        if isinstance(raw_formats, str):
            candidates = re.split(r"[;,，、\s]+", raw_formats)
        else:
            candidates = list(raw_formats or [])
        normalized: List[str] = []
        for item in candidates:
            value = str(item or "").strip().lower()
            if not value:
                continue
            if value == "both":
                for fmt in ("markdown", "docx"):
                    if fmt not in normalized:
                        normalized.append(fmt)
                continue
            if value == "md":
                value = "markdown"
            if value not in {"markdown", "docx"}:
                continue
            if value not in normalized:
                normalized.append(value)
        return normalized or ["markdown"]

    def _resolve_file_stem(self, context: Dict[str, Any], title: str) -> str:
        file_stem = str(
            context.get("file_stem") or context.get("base_name") or ""
        ).strip()
        if file_stem:
            return file_stem
        output_file = str(context.get("output_file") or "").strip()
        if output_file:
            return os.path.splitext(os.path.basename(output_file))[0]
        return _slugify(title)

    def _resolve_output_path(
        self, context: Dict[str, Any], output_dir: str, file_stem: str, fmt: str
    ) -> str:
        output_files = get_phase_artifact_map(context)
        if fmt in output_files:
            return os.path.abspath(str(output_files[fmt]))
        output_file = str(context.get("output_file") or "").strip()
        if (
            output_file
            and len(
                self._normalize_formats(
                    context.get("output_formats")
                    or context.get("output_format")
                    or self.default_formats
                )
            )
            == 1
        ):
            return os.path.abspath(output_file)
        extension = ".md" if fmt == "markdown" else ".docx"
        return os.path.abspath(os.path.join(output_dir, f"{file_stem}{extension}"))

    def _export_markdown(self, draft: PaperDraft, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        language = draft.metadata.get("language")
        lines = [f"# {draft.title}", ""]
        lines.extend(self._build_markdown_front_matter(draft))

        lines.extend(
            [("## 摘要" if language != "en" else "## Abstract"), draft.abstract, ""]
        )
        keyword_label = "关键词" if language != "en" else "Keywords"
        lines.append(f"{keyword_label}：{'；'.join(draft.keywords)}")
        lines.append("")

        for section in draft.sections:
            lines.append(f"## {section.title}")
            lines.append(section.content)
            lines.append("")

        figure_paths = list(draft.metadata.get("figure_paths") or [])
        if figure_paths:
            lines.append("## Figures")
            for index, path in enumerate(figure_paths, start=1):
                lines.append(f"- Figure {index}: {path}")
            lines.append("")

        ref_heading = "参考文献" if language != "en" else "References"
        lines.append(f"## {ref_heading}")
        if draft.references:
            lines.extend(draft.references)
        else:
            lines.append("[待补充参考文献]")
        lines.append("")
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).strip() + "\n")
        return output_path

    def _build_markdown_front_matter(self, draft: PaperDraft) -> List[str]:
        lines: List[str] = []
        author = str(draft.metadata.get("author") or "").strip()
        affiliation = str(draft.metadata.get("affiliation") or "").strip()
        if author:
            lines.append(f"作者：{author}")
        if affiliation:
            lines.append(f"单位：{affiliation}")
        if lines:
            lines.append("")
        return lines

    def _export_docx(
        self, draft: PaperDraft, output_path: str, context: Dict[str, Any]
    ) -> str:
        if self._Document is None:
            raise ImportError("DOCX 导出依赖 python-docx，请先安装 python-docx")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        document = self._Document()
        language = draft.metadata.get("language", self.language)
        self._set_default_font(document, language)
        self._write_docx_front_matter(document, draft)

        abstract_heading = "摘要" if language != "en" else "Abstract"
        keyword_label = "关键词" if language != "en" else "Keywords"
        keyword_text = (
            "；".join(draft.keywords) if language != "en" else "; ".join(draft.keywords)
        )
        document.add_heading(abstract_heading, level=1)
        document.add_paragraph(draft.abstract)
        document.add_paragraph(f"{keyword_label}：{keyword_text}")

        for section in draft.sections:
            document.add_heading(section.title, level=1)
            for paragraph_text in self._split_paragraphs(section.content):
                self._write_docx_section_block(document, paragraph_text)

        self._write_docx_figures(
            document, list(draft.metadata.get("figure_paths") or [])
        )

        ref_heading = "参考文献" if language != "en" else "References"
        document.add_heading(ref_heading, level=1)
        if draft.references:
            for reference in draft.references:
                document.add_paragraph(reference)
        else:
            document.add_paragraph("[待补充参考文献]")

        document.save(output_path)
        return output_path

    def _write_docx_front_matter(self, document: Any, draft: PaperDraft) -> None:
        title_paragraph = document.add_paragraph(draft.title)
        title_paragraph.alignment = self._WD_ALIGN_CENTER
        title_run = title_paragraph.runs[0]
        title_run.bold = True
        title_run.font.size = self._Pt(16)

        author = str(draft.metadata.get("author") or "").strip()
        affiliation = str(draft.metadata.get("affiliation") or "").strip()
        journal = str(draft.metadata.get("journal") or "").strip()
        for line in [
            author,
            affiliation,
            journal and f"Target journal: {journal}",
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ]:
            if not line:
                continue
            paragraph = document.add_paragraph(line)
            paragraph.alignment = self._WD_ALIGN_CENTER

    def _write_docx_figures(self, document: Any, figure_paths: List[str]) -> None:
        if not figure_paths:
            return
        document.add_heading("Figures", level=1)
        for index, path in enumerate(figure_paths, start=1):
            paragraph = document.add_paragraph(
                f"Figure {index}: {os.path.basename(path)}"
            )
            if self.embed_figures and os.path.exists(path) and self._Inches is not None:
                try:
                    document.add_picture(path, width=self._Inches(5.8))
                except Exception:
                    paragraph.add_run(f" ({path})")
            else:
                paragraph.add_run(f" ({path})")

    def _set_default_font(self, document: Any, language: str) -> None:
        style = document.styles["Normal"]
        font = style.font
        font.size = self._Pt(12)
        font.name = "Times New Roman"

    def _split_paragraphs(self, content: str) -> List[str]:
        parts = [
            segment.strip()
            for segment in re.split(r"\n{2,}", content)
            if segment.strip()
        ]
        return parts or [""]

    def _write_docx_section_block(self, document: Any, paragraph_text: str) -> None:
        if self._is_docx_subsection_heading(paragraph_text):
            document.add_heading(paragraph_text, level=2)
            return
        document.add_paragraph(paragraph_text)

    def _is_docx_subsection_heading(self, paragraph_text: str) -> bool:
        normalized = str(paragraph_text or "").strip()
        return normalized in {"类方图谱证据", "Class-like Formula Graph Evidence"}


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(text or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "paper_draft"
