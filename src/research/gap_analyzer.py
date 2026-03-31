"""临床/知识缺口分析模块：分离分析逻辑、结构化解析与 LLM 调用。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)

_DEFAULT_CLINICAL_QUESTION = "中医干预在目标人群中的临床有效性与安全性证据缺口是什么？"
_DEFAULT_EXPECTED_SECTIONS = [
    "临床问题重述",
    "现有证据覆盖概览",
    "关键缺口（至少3条）",
    "每条缺口的潜在偏倚或证据局限",
    "可执行研究建议（研究设计、核心终点、样本建议）",
    "优先级排序（高/中/低）",
]
_DEFAULT_REPORT_REQUIREMENTS = [
    "先给出证据覆盖结论，再给出 Gap。",
    "每个 Gap 必须指向具体维度（condition/intervention/outcome/method/knowledge/evidence）。",
    "每个研究建议必须包含：建议设计、核心纳入标准、主要终点。",
    "如果证据不足，明确写出“不足以支持结论”的范围。",
    "优先输出 JSON；若无法输出 JSON，按结构化小标题输出。",
]


@dataclass
class GapAnalyzerConfig:
    """GapAnalyzer 配置对象。"""

    max_summaries: int = 20
    summary_text_limit: int = 450
    use_llm_refinement: bool = True
    default_output_language: str = "zh"
    default_output_mode: str = "report"
    json_indent: int = 2
    default_clinical_question: str = _DEFAULT_CLINICAL_QUESTION
    expected_sections: List[str] = field(default_factory=lambda: list(_DEFAULT_EXPECTED_SECTIONS))
    system_prompt: str = (
        "你是中医临床研究方法学专家与证据综合分析师。"
        "请基于输入数据与预分析结果形成严谨报告，不得编造文献。"
    )
    report_requirements: List[str] = field(default_factory=lambda: list(_DEFAULT_REPORT_REQUIREMENTS))

    @classmethod
    def from_dict(cls, config: Optional[Dict[str, Any]] = None) -> "GapAnalyzerConfig":
        raw = dict(config or {})
        return cls(
            max_summaries=int(raw.get("max_summaries", 20)),
            summary_text_limit=int(raw.get("summary_text_limit", 450)),
            use_llm_refinement=bool(raw.get("use_llm_refinement", True)),
            default_output_language=str(raw.get("default_output_language") or raw.get("output_language") or "zh"),
            default_output_mode=str(raw.get("default_output_mode") or raw.get("output_mode") or "report"),
            json_indent=int(raw.get("json_indent", 2)),
            default_clinical_question=str(raw.get("default_clinical_question") or _DEFAULT_CLINICAL_QUESTION),
            expected_sections=list(raw.get("expected_sections") or _DEFAULT_EXPECTED_SECTIONS),
            system_prompt=str(raw.get("system_prompt") or cls().system_prompt),
            report_requirements=list(raw.get("report_requirements") or _DEFAULT_REPORT_REQUIREMENTS),
        )


@dataclass
class GapAnalysisRequest:
    """临床缺口分析输入。"""

    clinical_question: str
    evidence_matrix: Dict[str, Any]
    literature_summaries: List[Dict[str, Any]]
    output_language: str = "zh"
    output_mode: str = "report"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clinical_question": self.clinical_question,
            "evidence_matrix": self.evidence_matrix,
            "literature_summaries": self.literature_summaries,
            "output_language": self.output_language,
            "output_mode": self.output_mode,
        }


@dataclass
class GapAnalysisResult:
    """临床缺口分析输出。"""

    clinical_question: str
    output_language: str
    report: str
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    priority_summary: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    coverage_overview: Dict[str, Any] = field(default_factory=dict)
    json_payload: Dict[str, Any] = field(default_factory=dict)
    prompt_payload: Dict[str, Any] = field(default_factory=dict)
    core_analysis: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clinical_question": self.clinical_question,
            "output_language": self.output_language,
            "report": self.report,
            "gaps": self.gaps,
            "priority_summary": self.priority_summary,
            "recommendations": self.recommendations,
            "coverage_overview": self.coverage_overview,
            "json_payload": self.json_payload,
            "prompt_payload": self.prompt_payload,
            "core_analysis": self.core_analysis,
            "metadata": self.metadata,
        }


class GapAnalysisCore:
    """纯分析逻辑：构建 payload、推断缺口、生成结构化报告。"""

    def __init__(self, config: Optional[GapAnalyzerConfig] = None):
        self.config = config or GapAnalyzerConfig()
        self.max_summaries = int(self.config.max_summaries)
        self.summary_text_limit = int(self.config.summary_text_limit)

    def build_payload(
        self,
        clinical_question: str,
        evidence_matrix: Dict[str, Any],
        literature_summaries: List[Dict[str, Any]],
        output_language: str,
        output_mode: str,
    ) -> Dict[str, Any]:
        compact_summaries = []
        for row in literature_summaries[: self.max_summaries]:
            compact_summaries.append(
                {
                    "source": row.get("source", ""),
                    "title": row.get("title", ""),
                    "year": row.get("year"),
                    "summary_text": (row.get("summary_text", "") or "")[: self.summary_text_limit],
                }
            )

        return {
            "clinical_question": clinical_question,
            "evidence_matrix": evidence_matrix,
            "literature_summaries": compact_summaries,
            "expected_sections": list(self.config.expected_sections),
            "language": output_language,
            "output_mode": output_mode,
        }

    def analyze_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        summaries = payload.get("literature_summaries") or []
        evidence = payload.get("evidence_matrix") or {}
        dimensions = self._collect_dimensions(evidence)
        knowledge_signals = self._count_knowledge_signals(summaries)

        gaps = []
        if not dimensions["condition"]:
            gaps.append(self._gap("condition", "目标人群/证候定义不完整", "纳入标准可能异质，影响结论泛化", "高"))
        if not dimensions["intervention"]:
            gaps.append(self._gap("intervention", "干预描述不足", "剂量/疗程/配伍信息不完整", "高"))
        if dimensions["outcome_count"] < 2:
            gaps.append(self._gap("outcome", "关键结局覆盖不足", "仅少量终点，难以评估疗效与安全性平衡", "高"))
        if dimensions["method_count"] < 2:
            gaps.append(self._gap("method", "研究设计单一", "缺少多中心或高质量对照研究", "中"))
        if knowledge_signals < 2:
            gaps.append(self._gap("knowledge", "机制证据薄弱", "临床结论与作用机制链条尚未闭环", "中"))

        while len(gaps) < 3:
            gaps.append(self._gap("evidence", "证据密度不足", "现有研究数量或一致性不足以支持稳健结论", "中"))

        recommendations = [
            {
                "target_gap": gap["dimension"],
                "study_design": "前瞻性随机对照研究" if gap["priority"] == "高" else "多中心队列研究",
                "inclusion_criteria": "明确证候分型、年龄分层、基线合并症",
                "primary_endpoint": "临床主要结局 + 安全性复合终点",
            }
            for gap in gaps[:3]
        ]

        return {
            "clinical_question": payload.get("clinical_question", ""),
            "coverage_overview": {
                "literature_count": len(summaries),
                "condition_covered": dimensions["condition"],
                "intervention_covered": dimensions["intervention"],
                "outcome_count": dimensions["outcome_count"],
                "method_count": dimensions["method_count"],
                "knowledge_signal_count": knowledge_signals,
            },
            "gaps": gaps,
            "recommendations": recommendations,
        }

    def build_prompt_payload(self, payload: Dict[str, Any], core_analysis: Dict[str, Any]) -> Dict[str, Any]:
        requirements = "\n".join(
            f"{index}. {item}"
            for index, item in enumerate(self.config.report_requirements, 1)
        )
        output_mode = str(payload.get("output_mode") or "report").strip().lower()
        if output_mode == "json":
            user_prompt = (
                "请基于以下 JSON 输入执行临床/知识缺口分析，并仅输出 JSON 对象，不要输出 Markdown、说明或额外文本。\n"
                "JSON 字段必须包含：clinical_question, coverage_overview, gaps, priority_summary, recommendations。\n"
                f"{json.dumps({'payload': payload, 'core_analysis': core_analysis}, ensure_ascii=False, indent=2)}\n\n"
                "要求：\n"
                f"{requirements}"
            )
        else:
            user_prompt = (
                "请基于以下 JSON 输入执行临床/知识缺口分析。优先输出 JSON，对齐字段："
                "report, gaps, priority_summary, recommendations, coverage_overview。\n"
                f"{json.dumps({'payload': payload, 'core_analysis': core_analysis}, ensure_ascii=False, indent=2)}\n\n"
                "要求：\n"
                f"{requirements}"
            )
        return {
            "system_prompt": self.config.system_prompt,
            "user_prompt": user_prompt,
            "payload": payload,
        }

    def render_structured_report(self, core_analysis: Dict[str, Any], output_language: str) -> str:
        if output_language.lower().startswith("en"):
            return self._render_en(core_analysis)
        return self._render_zh(core_analysis)

    def _collect_dimensions(self, evidence_matrix: Dict[str, Any]) -> Dict[str, Any]:
        condition = bool(evidence_matrix.get("condition") or evidence_matrix.get("population") or evidence_matrix.get("syndrome"))
        intervention = bool(
            evidence_matrix.get("intervention")
            or evidence_matrix.get("formula")
            or evidence_matrix.get("herb")
        )
        outcomes = evidence_matrix.get("outcomes") or evidence_matrix.get("outcome") or []
        methods = evidence_matrix.get("study_designs") or evidence_matrix.get("methods") or []
        outcome_count = len(outcomes) if isinstance(outcomes, list) else (1 if outcomes else 0)
        method_count = len(methods) if isinstance(methods, list) else (1 if methods else 0)
        return {
            "condition": condition,
            "intervention": intervention,
            "outcome_count": outcome_count,
            "method_count": method_count,
        }

    def _count_knowledge_signals(self, summaries: List[Dict[str, Any]]) -> int:
        count = 0
        for item in summaries:
            text = f"{item.get('title', '')} {item.get('summary_text', '')}"
            if any(token in text for token in ["机制", "通路", "靶点", "机制链", "pathway", "mechanism", "target"]):
                count += 1
        return count

    def _gap(self, dimension: str, title: str, limitation: str, priority: str) -> Dict[str, Any]:
        return {
            "dimension": dimension,
            "title": title,
            "limitation": limitation,
            "priority": priority,
        }

    def _render_zh(self, analysis: Dict[str, Any]) -> str:
        coverage = analysis.get("coverage_overview", {})
        lines = [
            "# 临床/知识缺口分析报告",
            f"- 临床问题: {analysis.get('clinical_question', '')}",
            "## 证据覆盖概览",
            f"- 文献摘要数: {coverage.get('literature_count', 0)}",
            f"- 结局覆盖数: {coverage.get('outcome_count', 0)}",
            f"- 方法覆盖数: {coverage.get('method_count', 0)}",
            f"- 机制线索数: {coverage.get('knowledge_signal_count', 0)}",
            "## 关键缺口",
        ]
        for index, gap in enumerate(analysis.get("gaps", []), 1):
            lines.append(
                f"{index}. [{gap.get('priority', '中')}] {gap.get('title', '')} ({gap.get('dimension', '')}) - {gap.get('limitation', '')}"
            )
        lines.append("## 研究建议")
        for index, rec in enumerate(analysis.get("recommendations", []), 1):
            lines.append(
                f"{index}. 设计: {rec.get('study_design', '')}; 纳入: {rec.get('inclusion_criteria', '')}; 终点: {rec.get('primary_endpoint', '')}"
            )
        return "\n".join(lines)

    def _render_en(self, analysis: Dict[str, Any]) -> str:
        coverage = analysis.get("coverage_overview", {})
        lines = [
            "# Clinical/Knowledge Gap Analysis",
            f"- Clinical question: {analysis.get('clinical_question', '')}",
            "## Evidence Coverage",
            f"- Literature summaries: {coverage.get('literature_count', 0)}",
            f"- Outcome coverage count: {coverage.get('outcome_count', 0)}",
            f"- Method coverage count: {coverage.get('method_count', 0)}",
            f"- Mechanism signal count: {coverage.get('knowledge_signal_count', 0)}",
            "## Key Gaps",
        ]
        for index, gap in enumerate(analysis.get("gaps", []), 1):
            lines.append(
                f"{index}. [{gap.get('priority', 'Medium')}] {gap.get('title', '')} ({gap.get('dimension', '')}) - {gap.get('limitation', '')}"
            )
        lines.append("## Recommended Studies")
        for index, rec in enumerate(analysis.get("recommendations", []), 1):
            lines.append(
                f"{index}. Design: {rec.get('study_design', '')}; Inclusion: {rec.get('inclusion_criteria', '')}; Endpoint: {rec.get('primary_endpoint', '')}"
            )
        return "\n".join(lines)


class GapAnalysisLLMAdapter:
    """LLM 调用适配层：负责把 prompt 提交给 llm_service。"""

    def generate_report(self, llm_service: Any, user_prompt: str, system_prompt: str) -> str:
        if llm_service is None or not hasattr(llm_service, "generate"):
            raise RuntimeError("GapAnalysisLLMAdapter 需要支持 generate(prompt, system_prompt) 的 llm_service")
        return str(llm_service.generate(user_prompt, system_prompt))


class GapAnalyzer(BaseModule):
    """临床/知识缺口分析器：组织分析核心、结构化解析与 LLM 适配层。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, llm_service: Any = None):
        super().__init__("gap_analyzer", config)
        self.llm_service = llm_service
        self.settings = GapAnalyzerConfig.from_dict(self.config)
        self.use_llm_refinement = bool(self.settings.use_llm_refinement)
        self.core = GapAnalysisCore(self.settings)
        self.llm_adapter = GapAnalysisLLMAdapter()

    def _do_initialize(self) -> bool:
        self.logger.info("GapAnalyzer 初始化完成")
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        request = self._normalize_request(context)
        payload = self.core.build_payload(
            clinical_question=request.clinical_question,
            evidence_matrix=request.evidence_matrix,
            literature_summaries=request.literature_summaries,
            output_language=request.output_language,
            output_mode=request.output_mode,
        )
        core_analysis = self.core.analyze_payload(payload)
        prompt_data = self.core.build_prompt_payload(payload, core_analysis)

        llm_service = context.get("llm_service") or self.llm_service
        raw_use_llm = context.get("use_llm_refinement")
        use_llm = self.use_llm_refinement if raw_use_llm is None else bool(raw_use_llm)
        report = self.core.render_structured_report(core_analysis, request.output_language)
        used_llm = False
        if use_llm and llm_service is not None and hasattr(llm_service, "generate"):
            report = self.llm_adapter.generate_report(
                llm_service=llm_service,
                user_prompt=prompt_data["user_prompt"],
                system_prompt=prompt_data["system_prompt"],
            )
            used_llm = True

        parsed_analysis = self._parse_structured_output(report)
        resolved_analysis = self._merge_analysis(core_analysis, parsed_analysis)
        json_payload = self._build_json_payload(request, resolved_analysis)
        if request.output_mode == "json":
            report = json.dumps(json_payload, ensure_ascii=False, indent=self.settings.json_indent)
        elif self._looks_like_json_payload(report) and not parsed_analysis.get("report"):
            report = self.core.render_structured_report(resolved_analysis, request.output_language)

        result = GapAnalysisResult(
            clinical_question=request.clinical_question,
            output_language=request.output_language,
            report=report,
            gaps=resolved_analysis.get("gaps", []),
            priority_summary=self._build_priority_summary(resolved_analysis.get("gaps", [])),
            recommendations=resolved_analysis.get("recommendations", []),
            coverage_overview=resolved_analysis.get("coverage_overview", {}),
            json_payload=json_payload,
            prompt_payload=prompt_data["payload"],
            core_analysis=core_analysis,
            metadata={
                "literature_summary_count": len(prompt_data["payload"].get("literature_summaries", [])),
                "expected_sections": prompt_data["payload"].get("expected_sections", []),
                "used_llm_refinement": used_llm,
                "structured_parse_success": bool(parsed_analysis.get("gaps") or parsed_analysis.get("priority_summary")),
                "structured_source": parsed_analysis.get("structured_source", "core_fallback"),
                "output_mode": request.output_mode,
            },
        )
        return result.to_dict()

    def _do_cleanup(self) -> bool:
        self.logger.info("GapAnalyzer 资源清理完成")
        return True

    def analyze(
        self,
        clinical_question: str,
        evidence_matrix: Dict[str, Any],
        literature_summaries: List[Dict[str, Any]],
        output_language: str = "zh",
        output_mode: str = "report",
    ) -> str:
        """便捷方法：返回临床缺口分析报告文本。"""
        auto_initialized = False
        if not self.initialized:
            self.initialize()
            auto_initialized = True

        try:
            result = self.execute(
                {
                    "clinical_question": clinical_question,
                    "evidence_matrix": evidence_matrix,
                    "literature_summaries": literature_summaries,
                    "output_language": output_language,
                    "output_mode": output_mode,
                }
            )
            return str(result.get("report", ""))
        finally:
            if auto_initialized:
                self.cleanup()

    def analyze_structured(
        self,
        clinical_question: str,
        evidence_matrix: Dict[str, Any],
        literature_summaries: List[Dict[str, Any]],
        output_language: str = "zh",
        output_mode: str = "report",
    ) -> Dict[str, Any]:
        auto_initialized = False
        if not self.initialized:
            self.initialize()
            auto_initialized = True

        try:
            return self.execute(
                {
                    "clinical_question": clinical_question,
                    "evidence_matrix": evidence_matrix,
                    "literature_summaries": literature_summaries,
                    "output_language": output_language,
                    "output_mode": output_mode,
                }
            )
        finally:
            if auto_initialized:
                self.cleanup()

    def _normalize_request(self, context: Dict[str, Any]) -> GapAnalysisRequest:
        return GapAnalysisRequest(
            clinical_question=str(
                context.get("clinical_question")
                or context.get("research_topic")
                or context.get("literature_query")
                or self.settings.default_clinical_question
            ),
            evidence_matrix=context.get("evidence_matrix") or {},
            literature_summaries=context.get("literature_summaries") or [],
            output_language=str(
                context.get("output_language")
                or context.get("gap_output_language")
                or self.settings.default_output_language
            ),
            output_mode=self._normalize_output_mode(
                context.get("gap_output_mode")
                or context.get("output_mode")
                or self.settings.default_output_mode
            ),
        )

    def build_prompt_payload(
        self,
        clinical_question: str,
        evidence_matrix: Dict[str, Any],
        literature_summaries: List[Dict[str, Any]],
        output_language: str = "zh",
    ) -> Dict[str, Any]:
        payload = self.core.build_payload(
            clinical_question=clinical_question,
            evidence_matrix=evidence_matrix,
            literature_summaries=literature_summaries,
            output_language=output_language,
            output_mode=self.settings.default_output_mode,
        )
        core_analysis = self.core.analyze_payload(payload)
        return self.core.build_prompt_payload(payload, core_analysis)

    def _build_json_payload(
        self,
        request: GapAnalysisRequest,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "clinical_question": request.clinical_question,
            "output_language": request.output_language,
            "coverage_overview": analysis.get("coverage_overview", {}),
            "gaps": analysis.get("gaps", []),
            "priority_summary": analysis.get("priority_summary") or self._build_priority_summary(analysis.get("gaps", [])),
            "recommendations": analysis.get("recommendations", []),
        }

    def _parse_structured_output(self, report: str) -> Dict[str, Any]:
        parsed_json = self._parse_json_output(report)
        if parsed_json:
            parsed_json["structured_source"] = "llm_json"
            return parsed_json

        parsed_text = self._parse_report_sections(report)
        if parsed_text.get("gaps") or parsed_text.get("recommendations"):
            parsed_text["structured_source"] = "llm_report"
            return parsed_text
        return {}

    def _parse_json_output(self, report: str) -> Dict[str, Any]:
        text = str(report or "").strip()
        if not text:
            return {}
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        if not self._looks_like_json_payload(text):
            return {}
        try:
            payload = json.loads(text)
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            "report": str(payload.get("report") or "").strip(),
            "gaps": self._normalize_gaps(payload.get("gaps") or []),
            "priority_summary": payload.get("priority_summary") or {},
            "recommendations": self._normalize_recommendations(payload.get("recommendations") or []),
            "coverage_overview": payload.get("coverage_overview") or {},
        }

    def _parse_report_sections(self, report: str) -> Dict[str, Any]:
        lines = [line.strip() for line in str(report or "").splitlines()]
        gaps: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        section = ""
        for line in lines:
            if not line:
                continue
            lowered = line.lower()
            if "关键缺口" in line or "key gaps" in lowered:
                section = "gaps"
                continue
            if "研究建议" in line or "recommended studies" in lowered:
                section = "recommendations"
                continue
            if line.startswith("#"):
                continue
            if section == "gaps":
                parsed_gap = self._parse_gap_line(line)
                if parsed_gap:
                    gaps.append(parsed_gap)
                continue
            if section == "recommendations":
                parsed_recommendation = self._parse_recommendation_line(line)
                if parsed_recommendation:
                    recommendations.append(parsed_recommendation)

        return {
            "report": str(report or "").strip(),
            "gaps": gaps,
            "recommendations": recommendations,
        }

    def _parse_gap_line(self, line: str) -> Dict[str, Any]:
        cleaned = re.sub(r"^(?:[-*]|\d+[.)])\s*", "", line).strip()
        if not cleaned:
            return {}
        match = re.match(
            r"(?:\[(?P<priority>[^\]]+)\]\s*)?(?P<title>[^()\-：:]+?)\s*(?:\((?P<dimension>[^)]+)\))?\s*(?:[-：:]\s*(?P<limitation>.+))?$",
            cleaned,
        )
        if not match:
            return {}
        title = str(match.group("title") or "").strip()
        if not title:
            return {}
        return {
            "dimension": self._normalize_dimension(match.group("dimension") or "evidence"),
            "title": title,
            "limitation": str(match.group("limitation") or "").strip(),
            "priority": self._normalize_priority(match.group("priority") or "中"),
        }

    def _parse_recommendation_line(self, line: str) -> Dict[str, Any]:
        cleaned = re.sub(r"^(?:[-*]|\d+[.)])\s*", "", line).strip()
        if not cleaned:
            return {}
        segments = [segment.strip() for segment in re.split(r"[;；]", cleaned) if segment.strip()]
        result: Dict[str, Any] = {}
        for segment in segments:
            if "设计" in segment or segment.lower().startswith("design"):
                result["study_design"] = segment.split(":", 1)[-1].split("：", 1)[-1].strip()
            elif "纳入" in segment or segment.lower().startswith("inclusion"):
                result["inclusion_criteria"] = segment.split(":", 1)[-1].split("：", 1)[-1].strip()
            elif "终点" in segment or segment.lower().startswith("endpoint"):
                result["primary_endpoint"] = segment.split(":", 1)[-1].split("：", 1)[-1].strip()
        return result

    def _merge_analysis(self, core_analysis: Dict[str, Any], parsed_analysis: Dict[str, Any]) -> Dict[str, Any]:
        gaps = self._normalize_gaps(parsed_analysis.get("gaps") or core_analysis.get("gaps") or [])
        recommendations = self._normalize_recommendations(
            parsed_analysis.get("recommendations") or core_analysis.get("recommendations") or []
        )
        return {
            "clinical_question": parsed_analysis.get("clinical_question") or core_analysis.get("clinical_question", ""),
            "coverage_overview": parsed_analysis.get("coverage_overview") or core_analysis.get("coverage_overview") or {},
            "gaps": gaps,
            "recommendations": recommendations,
            "priority_summary": parsed_analysis.get("priority_summary") or self._build_priority_summary(gaps),
        }

    def _normalize_gaps(self, gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in gaps:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            normalized.append(
                {
                    "dimension": self._normalize_dimension(item.get("dimension") or "evidence"),
                    "title": title,
                    "limitation": str(item.get("limitation") or item.get("evidence_limitation") or "").strip(),
                    "priority": self._normalize_priority(item.get("priority") or "中"),
                }
            )
        return normalized

    def _normalize_recommendations(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "target_gap": str(item.get("target_gap") or item.get("dimension") or "").strip(),
                    "study_design": str(item.get("study_design") or "").strip(),
                    "inclusion_criteria": str(item.get("inclusion_criteria") or "").strip(),
                    "primary_endpoint": str(item.get("primary_endpoint") or "").strip(),
                }
            )
        return [item for item in normalized if any(item.values())]

    def _build_priority_summary(self, gaps: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = {"高": 0, "中": 0, "低": 0}
        for item in gaps:
            priority = self._normalize_priority(item.get("priority") or "中")
            counts[priority] = counts.get(priority, 0) + 1
        highest = "低"
        for level in ["高", "中", "低"]:
            if counts.get(level, 0) > 0:
                highest = level
                break
        return {
            "counts": counts,
            "highest_priority": highest,
            "total_gaps": len(gaps),
        }

    def _normalize_priority(self, priority: Any) -> str:
        text = str(priority or "").strip().lower()
        mapping = {
            "高": "高",
            "high": "高",
            "critical": "高",
            "中": "中",
            "medium": "中",
            "moderate": "中",
            "低": "低",
            "low": "低",
        }
        return mapping.get(text, "中")

    def _normalize_dimension(self, dimension: Any) -> str:
        text = str(dimension or "evidence").strip().lower()
        mapping = {
            "condition": "condition",
            "人群": "condition",
            "证候": "condition",
            "intervention": "intervention",
            "干预": "intervention",
            "formula": "intervention",
            "outcome": "outcome",
            "结局": "outcome",
            "method": "method",
            "方法": "method",
            "knowledge": "knowledge",
            "机制": "knowledge",
            "evidence": "evidence",
            "证据": "evidence",
        }
        return mapping.get(text, text or "evidence")

    def _normalize_output_mode(self, output_mode: Any) -> str:
        text = str(output_mode or "report").strip().lower()
        return "json" if text == "json" else "report"

    def _looks_like_json_payload(self, text: str) -> bool:
        stripped = str(text or "").strip()
        return stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("```")


__all__ = [
    "GapAnalyzer",
    "GapAnalyzerConfig",
    "GapAnalysisRequest",
    "GapAnalysisResult",
    "GapAnalysisCore",
    "GapAnalysisLLMAdapter",
]