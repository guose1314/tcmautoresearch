"""临床/知识缺口分析模块：分离分析逻辑与 LLM 调用。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


@dataclass
class GapAnalysisRequest:
    """临床缺口分析输入。"""

    clinical_question: str
    evidence_matrix: Dict[str, Any]
    literature_summaries: List[Dict[str, Any]]
    output_language: str = "zh"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clinical_question": self.clinical_question,
            "evidence_matrix": self.evidence_matrix,
            "literature_summaries": self.literature_summaries,
            "output_language": self.output_language,
        }


class GapAnalysisCore:
    """纯分析逻辑：构建 payload、推断缺口、生成结构化报告。"""

    def __init__(self, max_summaries: int = 20, summary_text_limit: int = 450):
        self.max_summaries = int(max_summaries)
        self.summary_text_limit = int(summary_text_limit)

    def build_payload(
        self,
        clinical_question: str,
        evidence_matrix: Dict[str, Any],
        literature_summaries: List[Dict[str, Any]],
        output_language: str,
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
            "expected_sections": [
                "临床问题重述",
                "现有证据覆盖概览",
                "关键缺口（至少3条）",
                "每条缺口的潜在偏倚或证据局限",
                "可执行研究建议（研究设计、核心终点、样本建议）",
                "优先级排序（高/中/低）",
            ],
            "language": output_language,
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
        system_prompt = (
            "你是中医临床研究方法学专家与证据综合分析师。"
            "请基于输入数据与预分析结果形成严谨报告，不得编造文献。"
        )
        user_prompt = (
            "请基于以下 JSON 输入执行临床/知识缺口分析，并输出结构化小标题报告。\n"
            f"{json.dumps({'payload': payload, 'core_analysis': core_analysis}, ensure_ascii=False, indent=2)}\n\n"
            "要求：\n"
            "1) 先给出证据覆盖结论，再给出 Gap。\n"
            "2) 每个 Gap 必须指向具体维度（condition/intervention/outcome/method/knowledge）。\n"
            "3) 每个研究建议必须包含：建议设计、核心纳入标准、主要终点。\n"
            "4) 如果证据不足，明确写出“不足以支持结论”的范围。"
        )
        return {
            "system_prompt": system_prompt,
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
    """临床/知识缺口分析器：组织分析核心与 LLM 适配层。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, llm_service: Any = None):
        super().__init__("gap_analyzer", config)
        self.llm_service = llm_service
        self.max_summaries = int(self.config.get("max_summaries", 20))
        self.summary_text_limit = int(self.config.get("summary_text_limit", 450))
        self.use_llm_refinement = bool(self.config.get("use_llm_refinement", True))
        self.core = GapAnalysisCore(self.max_summaries, self.summary_text_limit)
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
        )
        core_analysis = self.core.analyze_payload(payload)
        prompt_data = self.core.build_prompt_payload(payload, core_analysis)

        llm_service = context.get("llm_service") or self.llm_service
        use_llm = bool(context.get("use_llm_refinement", self.use_llm_refinement))
        report = self.core.render_structured_report(core_analysis, request.output_language)
        used_llm = False
        if use_llm and llm_service is not None and hasattr(llm_service, "generate"):
            report = self.llm_adapter.generate_report(
                llm_service=llm_service,
                user_prompt=prompt_data["user_prompt"],
                system_prompt=prompt_data["system_prompt"],
            )
            used_llm = True

        return {
            "clinical_question": request.clinical_question,
            "output_language": request.output_language,
            "report": report,
            "prompt_payload": prompt_data["payload"],
            "core_analysis": core_analysis,
            "metadata": {
                "literature_summary_count": len(prompt_data["payload"].get("literature_summaries", [])),
                "expected_sections": prompt_data["payload"].get("expected_sections", []),
                "used_llm_refinement": used_llm,
            },
        }

    def _do_cleanup(self) -> bool:
        self.logger.info("GapAnalyzer 资源清理完成")
        return True

    def analyze(
        self,
        clinical_question: str,
        evidence_matrix: Dict[str, Any],
        literature_summaries: List[Dict[str, Any]],
        output_language: str = "zh",
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
                }
            )
            return str(result.get("report", ""))
        finally:
            if auto_initialized:
                self.cleanup()

    def _normalize_request(self, context: Dict[str, Any]) -> GapAnalysisRequest:
        return GapAnalysisRequest(
            clinical_question=str(context.get("clinical_question") or ""),
            evidence_matrix=context.get("evidence_matrix") or {},
            literature_summaries=context.get("literature_summaries") or [],
            output_language=str(context.get("output_language") or "zh"),
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
        )
        core_analysis = self.core.analyze_payload(payload)
        return self.core.build_prompt_payload(payload, core_analysis)


__all__ = [
    "GapAnalyzer",
    "GapAnalysisRequest",
    "GapAnalysisCore",
    "GapAnalysisLLMAdapter",
]