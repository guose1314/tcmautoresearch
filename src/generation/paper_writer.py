"""论文撰写服务 — IMRD 结构论文生成、摘要生成、参考文献格式化。"""

from __future__ import annotations

import importlib
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.core.module_base import BaseModule
from src.generation.citation_manager import CitationManager

logger = logging.getLogger(__name__)

_SECTION_ORDER = ["introduction", "methods", "results", "discussion", "conclusion"]
_ZH_SECTION_TITLES = {
    "introduction": "1 引言（Introduction）",
    "methods": "2 方法（Methods）",
    "results": "3 结果（Results）",
    "discussion": "4 讨论（Discussion）",
    "conclusion": "5 结论（Conclusion）",
}
_EN_SECTION_TITLES = {
    "introduction": "1. Introduction",
    "methods": "2. Methods",
    "results": "3. Results",
    "discussion": "4. Discussion",
    "conclusion": "5. Conclusion",
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
        self.output_dir = os.path.abspath(str(self.config.get("output_dir", "output/papers")))
        self.language = str(self.config.get("language", "zh")).lower()
        self.default_formats = self._normalize_formats(
            self.config.get("output_formats") or self.config.get("output_format") or ["markdown", "docx"]
        )
        self.include_conclusion = bool(self.config.get("include_conclusion", True))
        self.reference_format = str(self.config.get("reference_format", "GB/T 7714-2015"))
        self.embed_figures = bool(self.config.get("embed_figures", False))
        self._Document: Any = None
        self._DocumentType: Any = None
        self._WD_ALIGN_CENTER: Any = None
        self._Pt: Any = None
        self._Inches: Any = None
        self._citation_manager = CitationManager({"format": self.reference_format, "include_abstract": False})

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
            logger.warning("PaperWriter 未能加载 python-docx，DOCX 导出将不可用: %s", exc)
        logger.info("PaperWriter 初始化完成: output_dir=%s", self.output_dir)
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        draft = self.build_draft(context)
        formats = self._normalize_formats(context.get("output_formats") or context.get("output_format") or self.default_formats)
        output_files = self.export_draft(draft, formats=formats, context=context)
        return {
            "success": True,
            "paper_draft": draft.to_dict(),
            "output_files": output_files,
            "section_count": len(draft.sections),
            "reference_count": len(draft.references),
            "figure_count": len(self._resolve_figure_paths(context)),
            "language": draft.metadata.get("language", self.language),
        }

    def _do_cleanup(self) -> bool:
        self._citation_manager.cleanup()
        return True

    def build_draft(self, context: Dict[str, Any]) -> PaperDraft:
        language = str(context.get("language") or self.language or "zh").lower()
        title = self._resolve_title(context)
        keywords = self._resolve_keywords(context)
        references = self._resolve_references(context)
        section_overrides = self._resolve_section_overrides(context, language)

        sections: List[PaperSection] = []
        for section_type in _SECTION_ORDER:
            if section_type == "conclusion" and not self.include_conclusion:
                continue
            title_text = self._section_title(section_type, language)
            content = section_overrides.get(section_type) or self._generate_section_content(section_type, context, title, language, references)
            sections.append(
                PaperSection(
                    section_type=section_type,
                    title=title_text,
                    content=content.strip(),
                    references=self._section_reference_markers(section_type, references),
                )
            )

        abstract_text = self._resolve_abstract(context, title, sections, language)
        metadata = {
            "language": language,
            "generated_at": datetime.now().isoformat(),
            "reference_format": self.reference_format,
            "author": self._resolve_author_text(context),
            "affiliation": str(context.get("affiliation") or "").strip(),
            "journal": str(context.get("journal") or "").strip(),
            "figure_paths": self._resolve_figure_paths(context),
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

    def export_draft(
        self,
        draft: PaperDraft,
        formats: Sequence[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        exec_context = context or {}
        output_dir = os.path.abspath(str(exec_context.get("output_dir") or self.output_dir))
        os.makedirs(output_dir, exist_ok=True)
        file_stem = self._resolve_file_stem(exec_context, draft.title)
        outputs: Dict[str, str] = {}
        for fmt in formats:
            if fmt == "markdown":
                path = self._resolve_output_path(exec_context, output_dir, file_stem, fmt)
                outputs[fmt] = self._export_markdown(draft, path)
            elif fmt == "docx":
                path = self._resolve_output_path(exec_context, output_dir, file_stem, fmt)
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

        normalized: List[str] = []
        for item in candidates:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)

        if normalized:
            return normalized[:6]

        derived = []
        for entity in list(context.get("entities") or [])[:6]:
            if isinstance(entity, dict):
                value = entity.get("name") or entity.get("text") or entity.get("entity")
            else:
                value = entity
            text = str(value or "").strip()
            if text and text not in derived:
                derived.append(text)
        if derived:
            return derived[:6]

        data_mining = self._resolve_data_mining_result(context)
        cluster_summary = list(data_mining.get("clustering", {}).get("cluster_summary", []) or [])
        if cluster_summary:
            top_items = list(cluster_summary[0].get("top_items", []) or [])
            for item in top_items:
                text = str(item.get("item") or "").strip()
                if text and text not in derived:
                    derived.append(text)
        return derived[:6] or ["中医古籍", "科研初稿", "IMRD"]

    def _resolve_references(self, context: Dict[str, Any]) -> List[str]:
        explicit_references = context.get("formatted_references")
        if isinstance(explicit_references, str) and explicit_references.strip():
            return [line.strip() for line in explicit_references.splitlines() if line.strip()]
        if isinstance(explicit_references, list):
            return [str(item).strip() for item in explicit_references if str(item).strip()]

        raw_records = (
            context.get("citation_records")
            or context.get("reference_records")
            or context.get("literature_records")
            or self._extract_literature_records(context)
        )
        if not raw_records:
            return []

        citation_result = self._citation_manager.execute({"records": raw_records, "format": self.reference_format})
        formatted = citation_result.get("formatted_references", "")
        return [line.strip() for line in str(formatted).splitlines() if line.strip()]

    def _extract_literature_records(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        literature_pipeline = context.get("literature_pipeline")
        if isinstance(literature_pipeline, dict):
            records = literature_pipeline.get("records")
            if isinstance(records, list):
                return [record for record in records if isinstance(record, dict)]
        analysis_results = context.get("analysis_results")
        if isinstance(analysis_results, dict):
            literature_pipeline = analysis_results.get("literature_pipeline")
            if isinstance(literature_pipeline, dict):
                records = literature_pipeline.get("records")
                if isinstance(records, list):
                    return [record for record in records if isinstance(record, dict)]
        return []

    def _resolve_section_overrides(self, context: Dict[str, Any], language: str) -> Dict[str, str]:
        overrides: Dict[str, str] = {}
        for key in _SECTION_ORDER:
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                overrides[key] = value.strip()

        sections_payload = context.get("sections") or context.get("paper_sections") or []
        if isinstance(sections_payload, dict):
            sections_iterable = [sections_payload]
        else:
            sections_iterable = sections_payload
        for item in sections_iterable:
            if not isinstance(item, dict):
                continue
            section_type = self._normalize_section_type(str(item.get("section_type") or item.get("type") or item.get("name") or ""))
            content = str(item.get("content") or "").strip()
            if section_type and content:
                overrides[section_type] = content

        abstract_override = context.get("abstract")
        if isinstance(abstract_override, str) and abstract_override.strip():
            overrides["abstract"] = abstract_override.strip()
        return overrides

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

        objective = str(context.get("objective") or "围绕中医古籍与现代证据的协同分析").strip()
        record_count = len(self._extract_literature_records(context))
        evidence_count = len(self._resolve_evidence(context))
        mining = self._resolve_data_mining_result(context)
        rule_count = len(mining.get("association_rules", {}).get("rules", []) or [])
        cluster_count = len(mining.get("clustering", {}).get("cluster_summary", []) or [])
        methods_line = "本研究采用格式转换、信息统一化、实体抽取、语义分析与数据挖掘联合流程。"
        results_line = f"共整合 {record_count} 条文献记录、{evidence_count} 条证据记录，识别 {rule_count} 条候选关联规则与 {cluster_count} 个聚类模式。"
        conclusion_line = "结果为中医古籍研究提供了结构化证据基础，并支持后续科研论文与图表生成。"

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
        objective = str(context.get("objective") or "阐明中医古籍证据与现代研究之间的关联").strip()
        research_domain = str(context.get("research_domain") or "中医古籍研究").strip()
        gap = self._resolve_gap_summary(context)
        record_count = len(self._extract_literature_records(context))
        reference_note = f"当前纳入 {record_count} 条文献记录作为研究背景支持。" if record_count else "现有研究背景主要来自多源文献与古籍证据。"
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
        evidence_protocol = analysis_results.get("evidence_protocol") if isinstance(analysis_results, dict) else {}
        evidence_record_count = len(evidence_protocol.get("evidence_records") or []) if isinstance(evidence_protocol, dict) else 0
        claim_count = len(evidence_protocol.get("claims") or []) if isinstance(evidence_protocol, dict) else 0
        methods = ["格式转换", "信息统一化", "实体抽取", "语义分析", "数据挖掘", "结果格式化"]
        if figure_paths:
            methods.append("科研图片生成")
        methods_text = "、".join(methods)
        mining_methods = list(mining.get("methods_executed") or [])
        protocol_text = ""
        if evidence_record_count or claim_count:
            if language == "en":
                protocol_text = (
                    f" The evidence protocol normalized {evidence_record_count} evidence records"
                    f" and {claim_count} candidate claims for downstream writing consistency."
                )
            else:
                protocol_text = (
                    f"证据协议层同步规整了 {evidence_record_count} 条证据记录"
                    f"和 {claim_count} 条候选论断，便于后续正文引用与复核。"
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
        return (
            f"本研究采用结构化研究流程，对与{title}相关的古籍文本和现代文献进行整合分析。"
            f"数据来源包括{ '、'.join(sources) if sources else '古籍文本与现代数据库文献' }。"
            f"整体流程涵盖{methods_text}等步骤，确保原始资料、分析结果与最终初稿之间保持可追溯关联。"
            f"数据挖掘环节主要执行{ '、'.join(mining_methods) if mining_methods else '关联规则与聚类分析' }，并将结果纳入论文叙事。"
            f"{protocol_text}"
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
        rule_count = len(mining.get("association_rules", {}).get("rules", []) or [])
        cluster_summary = list(mining.get("clustering", {}).get("cluster_summary", []) or [])
        figure_paths = self._resolve_figure_paths(context)
        figure_note = "；相关结果已与图表输出对齐" if figure_paths else ""
        graph_evidence_section = self._build_similar_formula_graph_evidence_section(context, language)
        analysis_note = self._build_analysis_result_note(language, statistical_analysis, analysis_results)
        evidence_grade_note = self._build_evidence_grade_result_note(language, evidence_grade_summary)
        top_cluster_text = ""
        if cluster_summary:
            first_cluster = cluster_summary[0]
            top_items = [item.get("item") for item in list(first_cluster.get("top_items", []) or [])[:3] if item.get("item")]
            if top_items:
                top_cluster_text = f"其中最主要的聚类特征集中在{'、'.join(top_items)}。"
        if language == "en":
            base = (
                f"The integrated workflow identified {len(entities)} entities and consolidated {len(evidence)} evidence records. "
                f"Data mining yielded {rule_count} association rules and {len(cluster_summary)} cluster summaries. "
                f"{top_cluster_text or ''} {analysis_note} {evidence_grade_note} {('Figures were generated to support the narrative interpretation.' if figure_paths else '')}".strip()
            )
            return f"{base}\n\n{graph_evidence_section}".strip() if graph_evidence_section else base
        base = (
            f"研究结果显示，当前流程共汇总 {len(entities)} 个核心实体、{len(evidence)} 条证据记录。"
            f"数据挖掘模块进一步识别出 {rule_count} 条关联规则和 {len(cluster_summary)} 个聚类摘要。"
            f"{top_cluster_text}{analysis_note}{evidence_grade_note}{figure_note} 这些结果为后续结果展示、图表引用和讨论部分的证据解释提供了结构化支撑。"
        )
        return f"{base}\n\n{graph_evidence_section}".strip() if graph_evidence_section else base

    def _build_similar_formula_graph_evidence_section(self, context: Dict[str, Any], language: str) -> str:
        summary = self._resolve_similar_formula_graph_evidence_summary(context)
        matches = list(summary.get("matches") or [])
        if not matches:
            return ""

        top_matches = matches[:3]
        if language == "en":
            lines = ["Class-like Formula Graph Evidence"]
            for match in top_matches:
                shared_herbs = ", ".join(str(item) for item in list(match.get("shared_herbs") or []) if item) or "none"
                shared_syndromes = ", ".join(str(item) for item in list(match.get("shared_syndromes") or []) if item) or "none"
                score = match.get("evidence_score", 0.0)
                similarity_score = match.get("similarity_score")
                similarity_text = f", similarity score {similarity_score:.2f}" if isinstance(similarity_score, (int, float)) else ""
                lines.append(
                    f"- {match.get('formula_name', '')} vs {match.get('similar_formula_name', '')}: graph evidence score {score:.2f}{similarity_text}; shared herbs {shared_herbs}; shared syndromes {shared_syndromes}."
                )
            return "\n\n".join(lines)

        lines = ["类方图谱证据"]
        for match in top_matches:
            shared_herbs = "、".join(str(item) for item in list(match.get("shared_herbs") or []) if item) or "暂无"
            shared_syndromes = "、".join(str(item) for item in list(match.get("shared_syndromes") or []) if item) or "暂无"
            score = float(match.get("evidence_score", 0.0) or 0.0)
            similarity_score = match.get("similarity_score")
            similarity_text = f"，embedding 相似度 {float(similarity_score):.2f}" if isinstance(similarity_score, (int, float)) else ""
            lines.append(
                f"- {match.get('formula_name', '')} 与 {match.get('similar_formula_name', '')} 的图谱证据分数为 {score:.2f}{similarity_text}；共享药物包括 {shared_herbs}；共享证候包括 {shared_syndromes}。"
            )
        return "\n\n".join(lines)

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
        association_rules = list(mining.get("association_rules", {}).get("rules", []) or [])
        high_rule = association_rules[0] if association_rules else None
        rule_text = ""
        if high_rule:
            antecedent = "、".join(high_rule.get("antecedent", []))
            consequent = "、".join(high_rule.get("consequent", []))
            rule_text = f"关联规则提示 {antecedent} 与 {consequent} 之间存在稳定共现关系。"
        limitation = self._resolve_limitations_text(context)
        hypothesis_text = ""
        if hypothesis:
            hypothesis_text = f"已有假设结果进一步提示：{hypothesis}。"
        hypothesis_audit_text = self._build_hypothesis_audit_text(context, language)
        evidence_grade_text = self._build_evidence_grade_discussion_text(language, evidence_grade_summary)
        quality_text = self._build_quality_discussion_text(language, quality_metrics, recommendations)
        if language == "en":
            return (
                f"The manuscript draft suggests that integrated evidence processing can improve coherence between classical knowledge and modern analysis. "
                f"{rule_text} {hypothesis_text}{hypothesis_audit_text}{evidence_grade_text}{quality_text} A key limitation is that {limitation}"
            )
        return (
            f"讨论部分表明，将古籍知识、现代文献与结构化分析结果整合到统一写作框架中，有助于提升科研叙事的一致性与可追溯性。"
            f"{rule_text}{hypothesis_text}{hypothesis_audit_text}{evidence_grade_text}{quality_text}{limitation} 因此，本初稿更适合作为投稿前的研究骨架和专家协作底稿，而非最终定稿。"
        )

    def _build_conclusion(
        self,
        context: Dict[str, Any],
        title: str,
        language: str,
        references: Sequence[str],
    ) -> str:
        objective = str(context.get("objective") or "构建可复用的中医古籍研究写作流程").strip()
        if language == "en":
            return (
                f"In conclusion, this IMRD draft operationalizes {objective} and provides a manuscript-ready scaffold for subsequent expert revision, figure integration, and journal submission."
            )
        return (
            f"综上，本服务围绕“{objective}”生成了可直接修订的 IMRD 论文初稿，能够把证据、数据挖掘结果与图表产物汇聚为统一稿件，为后续学术投稿提供基础。"
        )

    def _resolve_gap_summary(self, context: Dict[str, Any]) -> str:
        gap_payload = context.get("gap_analysis") or context.get("clinical_gap") or {}
        if isinstance(gap_payload, dict):
            summary = gap_payload.get("summary") or gap_payload.get("gap_summary") or gap_payload.get("description")
            if isinstance(summary, str) and summary.strip():
                return summary.strip() + ("。" if not summary.strip().endswith("。") else "")
        return "当前研究仍需进一步明确古籍理论、现代证据与可验证科研问题之间的映射路径。"

    def _resolve_source_list(self, context: Dict[str, Any]) -> List[str]:
        sources = []
        for record in self._extract_literature_records(context):
            source = record.get("source") or record.get("journal") or record.get("venue")
            text = str(source or "").strip()
            if text and text not in sources:
                sources.append(text)
        for source in context.get("sources") or []:
            text = str(source or "").strip()
            if text and text not in sources:
                sources.append(text)
        return sources[:6]

    def _resolve_hypothesis(self, context: Dict[str, Any]) -> str:
        hypothesis = context.get("hypothesis") or context.get("hypotheses") or []
        if isinstance(hypothesis, str):
            return hypothesis.strip()
        if isinstance(hypothesis, dict):
            return str(hypothesis.get("title") or hypothesis.get("statement") or "").strip()
        if isinstance(hypothesis, list) and hypothesis:
            first = hypothesis[0]
            if isinstance(first, dict):
                return str(first.get("title") or first.get("statement") or "").strip()
            return str(first).strip()
        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict):
            return self._resolve_hypothesis(research_artifact)
        return ""

    def _build_hypothesis_audit_text(self, context: Dict[str, Any], language: str) -> str:
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
            source_text = ", ".join(merged_sources) if merged_sources else "multiple evidence channels"
            relation_text = f" across {relationship_count} audited relations" if relationship_count else ""
            return (
                f"Audit evidence indicates a mechanism-chain completeness score of {mechanism_score:.2f}"
                f" with merged relation sources from {source_text}{relation_text}. "
            )

        source_text = "、".join(merged_sources) if merged_sources else "多源关系证据"
        relation_text = f"，共覆盖 {relationship_count} 条审计关系" if relationship_count else ""
        return (
            f"假设审计显示，当前优先假设的机制链完整性评分为 {mechanism_score:.2f}，"
            f"关系证据融合自 {source_text}{relation_text}。"
        )

    def _resolve_hypothesis_audit_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = context.get("hypothesis_audit_summary")
        if isinstance(direct, dict) and direct:
            return direct

        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict):
            nested = research_artifact.get("hypothesis_audit_summary")
            if isinstance(nested, dict) and nested:
                return nested

        output_data = context.get("output_data")
        if isinstance(output_data, dict):
            artifact = output_data.get("research_artifact")
            if isinstance(artifact, dict):
                nested = artifact.get("hypothesis_audit_summary")
                if isinstance(nested, dict) and nested:
                    return nested
        return {}

    def _resolve_evidence_grade_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = context.get("evidence_grade_summary")
        if isinstance(direct, dict) and direct:
            return direct

        analysis_results = self._resolve_analysis_results(context)
        resolved = self._extract_evidence_grade_summary(analysis_results)
        if resolved:
            return resolved

        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict):
            resolved = self._extract_evidence_grade_summary(research_artifact)
            if resolved:
                return resolved

        output_data = context.get("output_data")
        if isinstance(output_data, dict):
            resolved = self._extract_evidence_grade_summary(output_data.get("analysis_results"))
            if resolved:
                return resolved
            resolved = self._extract_evidence_grade_summary(output_data.get("research_artifact"))
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

    def _normalize_evidence_grade_summary(self, evidence_grade: Dict[str, Any]) -> Dict[str, Any]:
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
        reasoning = context.get("reasoning_results") or {}
        if isinstance(reasoning, dict) and isinstance(reasoning.get("evidence_records"), list):
            return list(reasoning.get("evidence_records") or [])
        analysis_results = self._resolve_analysis_results(context)
        reasoning = analysis_results.get("reasoning_results") if isinstance(analysis_results, dict) else {}
        if isinstance(reasoning, dict) and isinstance(reasoning.get("evidence_records"), list):
            return list(reasoning.get("evidence_records") or [])
        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict) and isinstance(research_artifact.get("evidence"), list):
            return list(research_artifact.get("evidence") or [])
        evidence = context.get("evidence") or []
        if isinstance(evidence, list):
            return evidence
        return []

    def _resolve_data_mining_result(self, context: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("data_mining_result", "data_mining", "mining_result"):
            value = context.get(key)
            if isinstance(value, dict):
                return value
        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict):
            value = research_artifact.get("data_mining_result")
            if isinstance(value, dict):
                return value
        analysis_results = context.get("analysis_results")
        if isinstance(analysis_results, dict):
            value = analysis_results.get("data_mining_result")
            if isinstance(value, dict):
                return value
        output_data = context.get("output_data")
        if isinstance(output_data, dict):
            research_artifact = output_data.get("research_artifact")
            if isinstance(research_artifact, dict):
                value = research_artifact.get("data_mining_result")
                if isinstance(value, dict):
                    return value
        return {}

    def _resolve_analysis_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        analysis_results = context.get("analysis_results")
        if isinstance(analysis_results, dict):
            return analysis_results
        output_data = context.get("output_data")
        if isinstance(output_data, dict):
            nested = output_data.get("analysis_results")
            if isinstance(nested, dict):
                return nested
        return {}

    def _resolve_statistical_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        analysis_results = self._resolve_analysis_results(context)
        statistical_analysis = analysis_results.get("statistical_analysis")
        if isinstance(statistical_analysis, dict):
            return statistical_analysis
        fallback = {
            key: analysis_results.get(key)
            for key in ("statistical_significance", "confidence_level", "effect_size", "p_value", "interpretation", "limitations")
            if key in analysis_results
        }
        return fallback if fallback else {}

    def _resolve_quality_metrics(self, context: Dict[str, Any]) -> Dict[str, Any]:
        quality_metrics = context.get("quality_metrics")
        if isinstance(quality_metrics, dict):
            return quality_metrics
        analysis_results = self._resolve_analysis_results(context)
        quality_metrics = analysis_results.get("quality_metrics")
        if isinstance(quality_metrics, dict):
            return quality_metrics
        output_data = context.get("output_data")
        if isinstance(output_data, dict):
            nested = output_data.get("quality_metrics")
            if isinstance(nested, dict):
                return nested
        return {}

    def _resolve_recommendations(self, context: Dict[str, Any]) -> List[str]:
        recommendations = context.get("recommendations")
        if isinstance(recommendations, list):
            return [str(item).strip() for item in recommendations if str(item).strip()]
        analysis_results = self._resolve_analysis_results(context)
        recommendations = analysis_results.get("recommendations") if isinstance(analysis_results, dict) else None
        if isinstance(recommendations, list):
            return [str(item).strip() for item in recommendations if str(item).strip()]
        output_data = context.get("output_data")
        if isinstance(output_data, dict) and isinstance(output_data.get("recommendations"), list):
            return [str(item).strip() for item in output_data.get("recommendations", []) if str(item).strip()]
        return []

    def _resolve_limitations_text(self, context: Dict[str, Any]) -> str:
        raw_limitations = context.get("limitations")
        if not raw_limitations:
            statistical_analysis = self._resolve_statistical_analysis(context)
            raw_limitations = statistical_analysis.get("limitations") if isinstance(statistical_analysis, dict) else None

        if isinstance(raw_limitations, str):
            limitation_text = raw_limitations.strip()
        elif isinstance(raw_limitations, (list, tuple, set)):
            limitation_text = "；".join(str(item).strip() for item in raw_limitations if str(item).strip())
        else:
            limitation_text = ""

        if not limitation_text:
            limitation_text = "当前结果仍依赖自动化抽取与结构化规则，尚需结合专家复核与外部验证"
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
        interpretation = str(statistical_analysis.get("interpretation") or analysis_results.get("interpretation") or "").strip()
        p_value = statistical_analysis.get("p_value")
        confidence_level = statistical_analysis.get("confidence_level")
        effect_size = statistical_analysis.get("effect_size")
        significance = statistical_analysis.get("statistical_significance")

        fragments: List[str] = []
        if language == "en":
            if significance is True or p_value is not None or confidence_level is not None or effect_size is not None:
                metric_bits = []
                if p_value is not None:
                    metric_bits.append(f"p={p_value}")
                if confidence_level is not None:
                    metric_bits.append(f"confidence level {confidence_level}")
                if effect_size is not None:
                    metric_bits.append(f"effect size {effect_size}")
                fragments.append(
                    "Statistical analysis suggested a meaningful signal"
                    + (f" ({', '.join(metric_bits)})" if metric_bits else "")
                    + "."
                )
            if interpretation:
                fragments.append(f"Interpretation: {interpretation}.")
            return " ".join(fragments).strip()

        if significance is True or p_value is not None or confidence_level is not None or effect_size is not None:
            metric_bits = []
            if p_value is not None:
                metric_bits.append(f"p={p_value}")
            if confidence_level is not None:
                metric_bits.append(f"置信水平 {confidence_level}")
            if effect_size is not None:
                metric_bits.append(f"效应量 {effect_size}")
            fragments.append(
                "统计分析提示当前结果具有稳定信号"
                + (f"（{'，'.join(metric_bits)}）" if metric_bits else "")
                + "。"
            )
        if interpretation:
            fragments.append(f"综合解释认为：{interpretation}。")
        return "".join(fragments).strip()

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

        overall_grade_raw = str(evidence_grade_summary.get("overall_grade") or "").strip().lower()
        overall_grade = self._format_grade_label(overall_grade_raw, language)
        try:
            overall_score = float(evidence_grade_summary.get("overall_score") or 0.0)
        except (TypeError, ValueError):
            overall_score = 0.0

        bias_bits: List[str] = []
        for key, value in sorted((evidence_grade_summary.get("bias_risk_distribution") or {}).items()):
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            if language == "en":
                bias_bits.append(f"{count} {key}")
            else:
                bias_bits.append(f"{self._format_bias_label(str(key), language)}风险 {count} 项")

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

        overall_grade = str(evidence_grade_summary.get("overall_grade") or "").strip().lower()
        if language == "en":
            if overall_grade in {"high", "moderate"}:
                return " The GRADE profile suggests that the current narrative is supported by at least moderate evidence certainty."
            return " The GRADE profile suggests that the current narrative remains constrained by low-certainty evidence and should be interpreted cautiously."

        if overall_grade in {"high", "moderate"}:
            return "GRADE 证据谱提示当前结论已获得至少中等强度的文献支持，但仍需持续跟踪高偏倚来源。"
        return "GRADE 证据谱提示当前结论仍受低确定性证据限制，后续应优先补充更高质量研究。"

    def _build_quality_discussion_text(
        self,
        language: str,
        quality_metrics: Dict[str, Any],
        recommendations: List[str],
    ) -> str:
        confidence_score = quality_metrics.get("confidence_score") if isinstance(quality_metrics, dict) else None
        completeness = quality_metrics.get("completeness") if isinstance(quality_metrics, dict) else None
        recommendation_text = "；".join(recommendations[:2]) if recommendations else ""
        if language == "en":
            parts: List[str] = []
            if confidence_score is not None or completeness is not None:
                metric_bits = []
                if confidence_score is not None:
                    metric_bits.append(f"confidence score {confidence_score}")
                if completeness is not None:
                    metric_bits.append(f"completeness {completeness}")
                parts.append(f"Quality review indicated {' and '.join(metric_bits)}.")
            if recommendation_text:
                parts.append(f"Recommended next steps include {recommendation_text}.")
            return (" " + " ".join(parts)).rstrip() if parts else ""

        parts = []
        if confidence_score is not None or completeness is not None:
            metric_bits = []
            if confidence_score is not None:
                metric_bits.append(f"置信分数 {confidence_score}")
            if completeness is not None:
                metric_bits.append(f"完整度 {completeness}")
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

    def _resolve_similar_formula_graph_evidence_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("similar_formula_graph_evidence_summary",):
            value = context.get(key)
            if isinstance(value, dict):
                return value

        research_artifact = context.get("research_artifact")
        if isinstance(research_artifact, dict):
            value = research_artifact.get("similar_formula_graph_evidence_summary")
            if isinstance(value, dict):
                return value

        for key in ("analysis_results", "output_data"):
            container = context.get(key)
            if isinstance(container, dict):
                nested_artifact = container.get("research_artifact")
                if isinstance(nested_artifact, dict):
                    value = nested_artifact.get("similar_formula_graph_evidence_summary")
                    if isinstance(value, dict):
                        return value
        return {}

    def _resolve_figure_paths(self, context: Dict[str, Any]) -> List[str]:
        if isinstance(context.get("figure_paths"), list):
            return [str(path).strip() for path in context.get("figure_paths", []) if str(path).strip()]
        figure_result = context.get("figure_result") or {}
        if isinstance(figure_result, dict) and isinstance(figure_result.get("figure_paths"), list):
            return [str(path).strip() for path in figure_result.get("figure_paths", []) if str(path).strip()]
        return []

    def _section_title(self, section_type: str, language: str) -> str:
        if language == "en":
            return _EN_SECTION_TITLES.get(section_type, section_type.title())
        return _ZH_SECTION_TITLES.get(section_type, section_type.title())

    def _section_reference_markers(self, section_type: str, references: Sequence[str]) -> List[str]:
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
        file_stem = str(context.get("file_stem") or context.get("base_name") or "").strip()
        if file_stem:
            return file_stem
        output_file = str(context.get("output_file") or "").strip()
        if output_file:
            return os.path.splitext(os.path.basename(output_file))[0]
        return _slugify(title)

    def _resolve_output_path(self, context: Dict[str, Any], output_dir: str, file_stem: str, fmt: str) -> str:
        output_files = context.get("output_files")
        if isinstance(output_files, dict) and fmt in output_files:
            return os.path.abspath(str(output_files[fmt]))
        output_file = str(context.get("output_file") or "").strip()
        if output_file and len(self._normalize_formats(context.get("output_formats") or context.get("output_format") or self.default_formats)) == 1:
            return os.path.abspath(output_file)
        extension = ".md" if fmt == "markdown" else ".docx"
        return os.path.abspath(os.path.join(output_dir, f"{file_stem}{extension}"))

    def _export_markdown(self, draft: PaperDraft, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        lines = [f"# {draft.title}", ""]
        author = str(draft.metadata.get("author") or "").strip()
        affiliation = str(draft.metadata.get("affiliation") or "").strip()
        if author:
            lines.append(f"作者：{author}")
        if affiliation:
            lines.append(f"单位：{affiliation}")
        if author or affiliation:
            lines.append("")

        lines.extend(["## 摘要" if draft.metadata.get("language") != "en" else "## Abstract", draft.abstract, ""])
        keyword_label = "关键词" if draft.metadata.get("language") != "en" else "Keywords"
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

        ref_heading = "参考文献" if draft.metadata.get("language") != "en" else "References"
        lines.append(f"## {ref_heading}")
        if draft.references:
            lines.extend(draft.references)
        else:
            lines.append("[待补充参考文献]")
        lines.append("")
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines).strip() + "\n")
        return output_path

    def _export_docx(self, draft: PaperDraft, output_path: str, context: Dict[str, Any]) -> str:
        if self._Document is None:
            raise ImportError("DOCX 导出依赖 python-docx，请先安装 python-docx")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        document = self._Document()
        self._set_default_font(document, draft.metadata.get("language", self.language))

        title_paragraph = document.add_paragraph(draft.title)
        title_paragraph.alignment = self._WD_ALIGN_CENTER
        title_run = title_paragraph.runs[0]
        title_run.bold = True
        title_run.font.size = self._Pt(16)

        author = str(draft.metadata.get("author") or "").strip()
        affiliation = str(draft.metadata.get("affiliation") or "").strip()
        journal = str(draft.metadata.get("journal") or "").strip()
        for line in [author, affiliation, journal and f"Target journal: {journal}", f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M')}"]:
            if not line:
                continue
            paragraph = document.add_paragraph(line)
            paragraph.alignment = self._WD_ALIGN_CENTER

        abstract_heading = "摘要" if draft.metadata.get("language") != "en" else "Abstract"
        keyword_label = "关键词" if draft.metadata.get("language") != "en" else "Keywords"
        keyword_text = "；".join(draft.keywords) if draft.metadata.get("language") != "en" else "; ".join(draft.keywords)
        document.add_heading(abstract_heading, level=1)
        document.add_paragraph(draft.abstract)
        document.add_paragraph(f"{keyword_label}：{keyword_text}")

        for section in draft.sections:
            document.add_heading(section.title, level=1)
            for paragraph_text in self._split_paragraphs(section.content):
                self._write_docx_section_block(document, paragraph_text)

        figure_paths = list(draft.metadata.get("figure_paths") or [])
        if figure_paths:
            document.add_heading("Figures", level=1)
            for index, path in enumerate(figure_paths, start=1):
                paragraph = document.add_paragraph(f"Figure {index}: {os.path.basename(path)}")
                if self.embed_figures and os.path.exists(path) and self._Inches is not None:
                    try:
                        document.add_picture(path, width=self._Inches(5.8))
                    except Exception:
                        paragraph.add_run(f" ({path})")
                else:
                    paragraph.add_run(f" ({path})")

        ref_heading = "参考文献" if draft.metadata.get("language") != "en" else "References"
        document.add_heading(ref_heading, level=1)
        if draft.references:
            for reference in draft.references:
                document.add_paragraph(reference)
        else:
            document.add_paragraph("[待补充参考文献]")

        document.save(output_path)
        return output_path

    def _set_default_font(self, document: Any, language: str) -> None:
        style = document.styles["Normal"]
        font = style.font
        font.size = self._Pt(12)
        font.name = "Times New Roman"

    def _split_paragraphs(self, content: str) -> List[str]:
        parts = [segment.strip() for segment in re.split(r"\n{2,}", content) if segment.strip()]
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
