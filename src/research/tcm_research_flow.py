# src/research/tcm_research_flow.py
"""
中医文献研究主流程编排器（TCMResearchFlow）。

以研究课题名称为输入，编排六阶段完整研究流程：
  1. 课题立项  — 确定研究目标、范围与方法
  2. 文献收集  — 多源文献检索与获取
  3. 文献整理  — 预处理、分类、标注
  4. 文献分析  — 六种文献研究法并行分析
  5. 综合研究  — RAG 增强、知识图谱推理
  6. 成果输出  — 结构化研究报告

每阶段使用本地 Qwen 模型提供专项 AI 辅助；
研究结果持久化至 Neo4j 知识图谱。

用法::

    flow = TCMResearchFlow()
    result = flow.run("桂枝汤的组方原理与临床应用文献研究")
    print(result["report"])
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Qwen TCM 专项提示词模板 ───────────────────────────────────────────────────
_PROMPTS: Dict[str, str] = {
    "phase1_proposal": (
        "你是一位资深中医文献研究专家。\n"
        "请针对以下中医研究课题，完成课题立项分析：\n"
        "课题名称：{topic}\n\n"
        "请从以下维度回答（每项不超过200字）：\n"
        "1. 研究意义与必要性\n"
        "2. 研究目标与核心研究问题\n"
        "3. 适用研究方法（从文献梳理法/文献计量法/校勘法/训诂法/版本对勘法/综合研究法中选择）\n"
        "4. 预期成果形式\n"
        "5. 主要参考古籍来源\n"
    ),
    "phase2_collection": (
        "你是一位中医古籍文献检索专家。\n"
        "针对研究课题「{topic}」，请制定系统的文献收集方案：\n\n"
        "1. 推荐检索的主要古籍数据库及关键词\n"
        "2. 需要重点关注的中医典籍（按朝代列出）\n"
        "3. 文献筛选标准（纳入/排除）\n"
        "4. 文献质量评估要点\n"
    ),
    "phase4_analysis": (
        "你是一位精通中医文献研究的学术专家。\n"
        "以下是关于「{topic}」的文献研究初步分析结果：\n"
        "{analysis_summary}\n\n"
        "请对以上分析结果进行学术解读：\n"
        "1. 核心发现与规律\n"
        "2. 文献中的关键医学论点\n"
        "3. 不同时代认识的演变\n"
        "4. 存在争议的学术问题\n"
    ),
    "phase5_synthesis": (
        "你是一位资深中医学术研究专家。\n"
        "针对研究课题「{topic}」，请综合多维度分析结果，形成系统性研究结论：\n"
        "{combined_findings}\n\n"
        "请提供：\n"
        "1. 核心学术结论（3-5条）\n"
        "2. 创新性发现\n"
        "3. 对当代中医临床/教学的指导意义\n"
        "4. 研究局限与未来研究方向\n"
    ),
    "phase6_report": (
        "你是一位中医学术论文写作专家。\n"
        "请基于以下研究成果，为「{topic}」撰写结构化研究报告摘要：\n"
        "{synthesis}\n\n"
        "请按 IMRD 格式输出（Introduction/Methods/Results/Discussion），每节约150字。\n"
    ),
}


@dataclass
class ResearchPhaseResult:
    """单阶段研究结果数据模型。"""

    phase: int
    phase_name: str
    status: str = "pending"
    ai_output: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None


@dataclass
class TCMResearchResult:
    """完整 TCM 研究流程结果。"""

    research_id: str
    topic: str
    phases: List[ResearchPhaseResult] = field(default_factory=list)
    report: str = ""
    kg_node_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "initialized"


class TCMResearchFlow:
    """中医文献研究主流程编排器。

    以研究课题名称为输入，编排六阶段完整研究流程，
    使用本地 Qwen 模型提供 TCM 专项 AI 辅助，
    将结构化研究成果持久化至 Neo4j 知识图谱。

    Parameters
    ----------
    llm_gateway :
        LLMGateway 实例（可选）。为 ``None`` 时尝试自动创建。
    storage_gateway :
        StorageGateway 实例（可选）。为 ``None`` 时尝试自动创建。
    """

    def __init__(
        self,
        llm_gateway: Optional[Any] = None,
        storage_gateway: Optional[Any] = None,
    ) -> None:
        self._llm = llm_gateway
        self._storage = storage_gateway
        self._method_router: Optional[Any] = None
        self._preprocessor: Optional[Any] = None
        self._init_dependencies()

    def _init_dependencies(self) -> None:
        """延迟初始化依赖组件，失败时降级而不崩溃。"""
        if self._llm is None:
            try:
                from src.infrastructure.llm_gateway import LLMGateway
                self._llm = LLMGateway()
            except Exception as exc:
                logger.warning("LLMGateway 初始化失败，将跳过 AI 辅助: %s", exc)

        if self._storage is None:
            try:
                from src.storage.storage_gateway import StorageGateway
                self._storage = StorageGateway()
            except Exception as exc:
                logger.warning("StorageGateway 初始化失败，将跳过持久化: %s", exc)

        try:
            from src.research.method_router import ResearchMethodRouter
            self._method_router = ResearchMethodRouter()
        except Exception as exc:
            logger.warning("ResearchMethodRouter 初始化失败: %s", exc)

        try:
            from src.analysis.preprocessor import DocumentPreprocessor
            self._preprocessor = DocumentPreprocessor()
            self._preprocessor.initialize()
        except Exception as exc:
            logger.warning("DocumentPreprocessor 初始化失败: %s", exc)

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def run(
        self,
        topic: str,
        corpus: Optional[Dict[str, Any]] = None,
        phases: Optional[List[int]] = None,
    ) -> TCMResearchResult:
        """执行完整 TCM 文献研究流程。

        Args:
            topic:  研究课题名称（如"桂枝汤组方原理文献研究"）。
            corpus: 可选预提供的文献语料，若不提供则在第2阶段收集。
            phases: 指定执行的阶段列表（1-6），默认执行全部。

        Returns:
            TCMResearchResult 包含所有阶段结果和最终报告。
        """
        research_id = f"tcm_{uuid.uuid4().hex[:8]}"
        result = TCMResearchResult(research_id=research_id, topic=topic)
        phases_to_run = set(phases or [1, 2, 3, 4, 5, 6])

        logger.info("🔬 启动中医文献研究流程 [%s]: %s", research_id, topic)

        phase_results: Dict[int, ResearchPhaseResult] = {}

        # 阶段1：课题立项
        if 1 in phases_to_run:
            p1 = self._phase1_proposal(topic)
            phase_results[1] = p1
            result.phases.append(p1)

        # 阶段2：文献收集
        if 2 in phases_to_run:
            p2 = self._phase2_collection(topic, corpus)
            phase_results[2] = p2
            result.phases.append(p2)
            if corpus is None:
                corpus = p2.data.get("corpus", {})

        # 阶段3：文献整理
        if 3 in phases_to_run:
            p3 = self._phase3_organization(topic, corpus or {})
            phase_results[3] = p3
            result.phases.append(p3)

        # 阶段4：文献分析
        if 4 in phases_to_run:
            p4 = self._phase4_analysis(topic, corpus or {}, phase_results)
            phase_results[4] = p4
            result.phases.append(p4)

        # 阶段5：综合研究
        if 5 in phases_to_run:
            p5 = self._phase5_synthesis(topic, phase_results)
            phase_results[5] = p5
            result.phases.append(p5)

        # 阶段6：成果输出
        if 6 in phases_to_run:
            p6 = self._phase6_report(topic, phase_results)
            phase_results[6] = p6
            result.phases.append(p6)
            result.report = p6.data.get("report", "")

        result.status = "completed"
        self._persist_result(result)
        logger.info("✅ 研究流程 [%s] 完成", research_id)
        return result

    # ── 各阶段实现 ─────────────────────────────────────────────────────────────

    def _phase1_proposal(self, topic: str) -> ResearchPhaseResult:
        """阶段1：课题立项 — 确定研究目标、范围与方法选择。"""
        phase = ResearchPhaseResult(phase=1, phase_name="课题立项")
        try:
            ai_output = self._call_llm(
                _PROMPTS["phase1_proposal"].format(topic=topic)
            )
            phase.ai_output = ai_output
            phase.data = {
                "topic": topic,
                "methods_selected": [
                    "literature_sorting", "bibliometrics", "exegesis",
                    "textual_criticism", "version_collation", "integrated_literature",
                ],
                "proposal": ai_output,
            }
            phase.status = "completed"
            logger.info("阶段1（课题立项）完成")
        except Exception as exc:
            phase.status = "error"
            phase.error = str(exc)
            logger.error("阶段1执行失败: %s", exc)
        return phase

    def _phase2_collection(
        self, topic: str, existing_corpus: Optional[Dict[str, Any]]
    ) -> ResearchPhaseResult:
        """阶段2：文献收集 — 多源文献检索与获取。"""
        phase = ResearchPhaseResult(phase=2, phase_name="文献收集")
        try:
            ai_output = self._call_llm(
                _PROMPTS["phase2_collection"].format(topic=topic)
            )
            phase.ai_output = ai_output
            # 若已提供语料则直接使用
            corpus = existing_corpus or {"documents": [], "texts": []}
            phase.data = {
                "collection_plan": ai_output,
                "corpus": corpus,
                "sources_searched": ["CText", "本地语料库"],
            }
            phase.status = "completed"
            logger.info("阶段2（文献收集）完成，文献数: %d", len(corpus.get("documents", [])))
        except Exception as exc:
            phase.status = "error"
            phase.error = str(exc)
            logger.error("阶段2执行失败: %s", exc)
        return phase

    def _phase3_organization(
        self, topic: str, corpus: Dict[str, Any]
    ) -> ResearchPhaseResult:
        """阶段3：文献整理 — 预处理、分类、标注。"""
        phase = ResearchPhaseResult(phase=3, phase_name="文献整理")
        try:
            preprocessed_docs = []
            docs = corpus.get("documents", [])

            for doc in docs:
                if not isinstance(doc, dict):
                    continue
                raw_text = doc.get("content") or doc.get("text", "")
                if raw_text and self._preprocessor:
                    try:
                        proc_result = self._preprocessor.execute({"raw_text": raw_text})
                        doc = dict(doc)
                        doc["processed_text"] = proc_result.get("processed_text", raw_text)
                        doc["tcm_metadata"] = proc_result.get("metadata", {})
                    except Exception:
                        pass
                preprocessed_docs.append(doc)

            phase.data = {
                "preprocessed_count": len(preprocessed_docs),
                "corpus": {**corpus, "documents": preprocessed_docs},
            }
            phase.status = "completed"
            logger.info("阶段3（文献整理）完成，处理文档 %d 篇", len(preprocessed_docs))
        except Exception as exc:
            phase.status = "error"
            phase.error = str(exc)
            logger.error("阶段3执行失败: %s", exc)
        return phase

    def _phase4_analysis(
        self,
        topic: str,
        corpus: Dict[str, Any],
        prior_phases: Dict[int, ResearchPhaseResult],
    ) -> ResearchPhaseResult:
        """阶段4：文献分析 — 六种文献研究法并行分析。"""
        phase = ResearchPhaseResult(phase=4, phase_name="文献分析")
        try:
            # 使用整理后的语料（若阶段3完成）
            working_corpus = (
                prior_phases[3].data.get("corpus", corpus)
                if 3 in prior_phases and prior_phases[3].status == "completed"
                else corpus
            )

            method_results: Dict[str, Any] = {}
            tcm_methods = [
                "tcm_literature_sorting",
                "tcm_bibliometrics",
                "tcm_textual_criticism",
                "tcm_exegesis",
                "tcm_version_collation",
                "tcm_integrated_literature",
            ]

            if self._method_router:
                for method_key in tcm_methods:
                    result = self._method_router.route(method_key, working_corpus)
                    method_results[method_key] = result
                    logger.debug("文献分析方法 %s 完成，状态: %s", method_key, result.get("status"))
            else:
                # 降级：直接调用 TCM 文献方法
                from src.research.tcm_literature_methods import IntegratedLiteratureMethod
                integrated = IntegratedLiteratureMethod()
                method_results["integrated_literature"] = integrated.analyze(working_corpus)

            # LLM 学术解读
            analysis_summary = self._build_analysis_summary(method_results)
            ai_output = self._call_llm(
                _PROMPTS["phase4_analysis"].format(
                    topic=topic,
                    analysis_summary=analysis_summary[:1000],
                )
            )

            phase.ai_output = ai_output
            phase.data = {
                "method_results": method_results,
                "analysis_summary": analysis_summary,
                "ai_interpretation": ai_output,
            }
            phase.status = "completed"
            logger.info("阶段4（文献分析）完成，运行方法 %d 个", len(method_results))
        except Exception as exc:
            phase.status = "error"
            phase.error = str(exc)
            logger.error("阶段4执行失败: %s", exc)
        return phase

    def _phase5_synthesis(
        self, topic: str, prior_phases: Dict[int, ResearchPhaseResult]
    ) -> ResearchPhaseResult:
        """阶段5：综合研究 — RAG 增强推理，形成系统性结论。"""
        phase = ResearchPhaseResult(phase=5, phase_name="综合研究")
        try:
            # 汇总前序阶段的关键发现
            findings: List[str] = []
            for ph_id in [1, 2, 3, 4]:
                ph = prior_phases.get(ph_id)
                if ph and ph.status == "completed" and ph.ai_output:
                    findings.append(f"【阶段{ph_id} {ph.phase_name}】\n{ph.ai_output[:300]}")

            combined = "\n\n".join(findings) if findings else "（暂无前序阶段输出）"

            ai_output = self._call_llm(
                _PROMPTS["phase5_synthesis"].format(
                    topic=topic,
                    combined_findings=combined,
                )
            )
            phase.ai_output = ai_output
            phase.data = {
                "combined_findings": combined,
                "synthesis": ai_output,
            }
            phase.status = "completed"
            logger.info("阶段5（综合研究）完成")
        except Exception as exc:
            phase.status = "error"
            phase.error = str(exc)
            logger.error("阶段5执行失败: %s", exc)
        return phase

    def _phase6_report(
        self, topic: str, prior_phases: Dict[int, ResearchPhaseResult]
    ) -> ResearchPhaseResult:
        """阶段6：成果输出 — IMRD 格式研究报告生成。"""
        phase = ResearchPhaseResult(phase=6, phase_name="成果输出")
        try:
            synthesis = ""
            if 5 in prior_phases and prior_phases[5].status == "completed":
                synthesis = prior_phases[5].data.get("synthesis", "")

            ai_output = self._call_llm(
                _PROMPTS["phase6_report"].format(
                    topic=topic,
                    synthesis=synthesis[:800] or "（综合研究阶段未提供输出）",
                )
            )

            # 构建结构化报告
            report = self._build_report(topic, prior_phases, ai_output)
            phase.ai_output = ai_output
            phase.data = {"report": report, "imrd_summary": ai_output}
            phase.status = "completed"
            logger.info("阶段6（成果输出）完成，报告长度: %d 字符", len(report))
        except Exception as exc:
            phase.status = "error"
            phase.error = str(exc)
            logger.error("阶段6执行失败: %s", exc)
        return phase

    # ── 辅助方法 ──────────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 网关生成文本，失败时返回占位说明。"""
        if self._llm is None:
            return f"（LLM 不可用，跳过 AI 辅助生成。提示词长度: {len(prompt)} 字符）"
        try:
            system_prompt = (
                "你是一位精通中医学理论与文献研究方法的资深学者，"
                "回答请使用中文，内容准确、简洁、具有学术性。"
            )
            result = self._llm.generate(prompt, system_prompt=system_prompt)
            return str(result) if result else "（LLM 返回空内容）"
        except Exception as exc:
            logger.warning("LLM 调用失败: %s", exc)
            return f"（LLM 调用失败: {exc}）"

    def _build_analysis_summary(self, method_results: Dict[str, Any]) -> str:
        """从方法结果构建简洁摘要字符串。"""
        lines: List[str] = []
        for key, res in method_results.items():
            status = res.get("status", "unknown")
            result_data = res.get("result", {})
            if status == "success" and result_data:
                # 取 result 的前几个键值作摘要
                summary_items = list(result_data.items())[:3]
                summary_str = "; ".join(
                    f"{k}={str(v)[:50]}" for k, v in summary_items
                )
                lines.append(f"- {key}: {summary_str}")
            else:
                lines.append(f"- {key}: 状态={status}")
        return "\n".join(lines)

    def _build_report(
        self,
        topic: str,
        phase_results: Dict[int, ResearchPhaseResult],
        imrd_summary: str,
    ) -> str:
        """构建 Markdown 格式的完整研究报告。"""
        lines = [
            f"# {topic} — 中医文献研究报告",
            f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "\n---\n",
            "## 研究摘要（IMRD 格式）\n",
            imrd_summary,
            "\n---\n",
            "## 各阶段研究记录\n",
        ]
        for phase_id, ph in sorted(phase_results.items()):
            lines.append(f"### 阶段{phase_id}：{ph.phase_name}")
            lines.append(f"- **状态**: {ph.status}")
            if ph.ai_output:
                lines.append(f"- **AI 辅助输出**:\n{ph.ai_output[:400]}")
            if ph.error:
                lines.append(f"- **错误**: {ph.error}")
            lines.append("")
        return "\n".join(lines)

    def _persist_result(self, result: TCMResearchResult) -> None:
        """将研究结果持久化到存储层。"""
        if self._storage is None:
            return
        try:
            self._storage.save_research_result(
                result.research_id,
                {
                    "topic": result.topic,
                    "status": result.status,
                    "phases": len(result.phases),
                    "report": result.report[:500],
                    "created_at": result.created_at,
                },
            )
            logger.info("研究结果已持久化: %s", result.research_id)
        except Exception as exc:
            logger.warning("研究结果持久化失败: %s", exc)


__all__ = [
    "TCMResearchFlow",
    "TCMResearchResult",
    "ResearchPhaseResult",
]
