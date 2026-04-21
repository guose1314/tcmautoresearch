# src/research/handlers/hypothesis_handler.py
"""假设生成阶段处理器：基于知识图谱缺口生成研究假设，融合 LLM 推理（I-02）。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase

logger = logging.getLogger(__name__)


class HypothesisPhaseHandler(BasePhaseHandler):
    """
    假设生成阶段处理器（指令 I-02 增强版）。

    负责：
    1. 构建假设上下文（实体、关系、知识缺口）
    2. 调用 HypothesisEngine 生成候选假设
    3. 对假设进行多维度评分（novelty / feasibility / evidence_support）
    4. 【I-02 新增】通过 LLMResearchAdvisor 进行假设精炼与 Self-RAG 验证
    5. 【I-02 新增】合并 LLM 生成假设与规则生成假设
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行假设生成阶段，返回 hypotheses / metadata 等字段。"""
        # 1. 执行基础假设生成
        result = self.pipeline.phase_handlers.execute_hypothesis_phase(cycle, context or {})

        # 2. LLMResearchAdvisor 假设精炼（I-02）
        llm_hypotheses = self._generate_llm_hypotheses(result, cycle, context or {})
        if llm_hypotheses:
            result["llm_hypotheses"] = llm_hypotheses
            # 将 LLM 生成的假设合并到主假设列表
            existing = result.get("hypotheses") or []
            result["hypotheses"] = self._merge_hypotheses(existing, llm_hypotheses)

        return result

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    def _generate_llm_hypotheses(
        self,
        result: Dict[str, Any],
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """通过 LLMResearchAdvisor 生成研究假设（I-02）。"""
        try:
            from src.research.llm_research_advisor import LLMResearchAdvisor

            llm = getattr(self.pipeline, "_llm_engine", None)
            rag = getattr(self.pipeline, "_rag_service", None)

            if llm is None:
                return []

            advisor = LLMResearchAdvisor(llm_engine=llm, rag_service=rag)

            # 提取知识缺口
            gaps = self._extract_knowledge_gaps(result, cycle)
            if not gaps:
                return []

            advisory = advisor.advise(
                phase="hypothesis",
                context={"gaps": gaps},
                use_rag=True,
                use_hyde=True,
            )

            if not advisory.conclusion:
                return []

            # 将 AdvisoryResult 转为假设列表格式
            llm_hyps: List[Dict[str, Any]] = [{
                "title": f"LLM假设：{advisory.conclusion[:60]}",
                "statement": advisory.conclusion,
                "evidence_support": advisory.evidence,
                "confidence": advisory.confidence,
                "source_refs": advisory.source_refs,
                "is_llm_generated": True,
                "is_grounded": advisory.is_grounded,
            }]

            logger.debug(
                "HypothesisHandler: LLM 生成 %d 条假设，confidence=%.2f",
                len(llm_hyps),
                advisory.confidence,
            )
            return llm_hyps
        except Exception as exc:
            logger.warning("HypothesisHandler: LLM 假设生成失败（跳过）: %s", exc)
            return []

    def _extract_knowledge_gaps(
        self,
        result: Dict[str, Any],
        cycle: "ResearchCycle",
    ) -> str:
        """从观察阶段提取知识缺口描述。"""
        parts: List[str] = []

        # 从上一阶段（observe）提取信息
        try:
            from src.research.research_pipeline import ResearchPhase
            observe_result = cycle.phase_executions.get(
                ResearchPhase.OBSERVE, {}
            ).get("result", {})
            findings = observe_result.get("findings", [])
            for f in findings[:3]:
                parts.append(str(f))
        except Exception:
            pass

        # 使用当前假设阶段的初始发现
        hypotheses = result.get("hypotheses") or []
        if hypotheses:
            parts.append(f"已有 {len(hypotheses)} 条初始假设，需要深化研究")

        # 研究主题
        topic = getattr(cycle, "topic", "") or getattr(cycle, "research_topic", "")
        if topic:
            parts.insert(0, f"研究主题：{topic}")

        return "\n".join(parts)[:600] if parts else ""

    @staticmethod
    def _merge_hypotheses(
        existing: List[Any],
        llm_hyps: List[Dict[str, Any]],
    ) -> List[Any]:
        """合并规则生成假设与 LLM 生成假设（LLM 假设排在前面）。"""
        return llm_hyps + [h for h in existing if isinstance(h, dict)]
