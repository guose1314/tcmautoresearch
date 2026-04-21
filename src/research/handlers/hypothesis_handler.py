# src/research/handlers/hypothesis_handler.py
"""假设生成阶段处理器：基于知识图谱缺口生成研究假设。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline


class HypothesisPhaseHandler(BasePhaseHandler):
    """
    假设生成阶段处理器。

    负责：
    1. 构建假设上下文（实体、关系、知识缺口）
    2. 调用 HypothesisEngine 生成候选假设
    3. 对假设进行多维度评分（novelty / feasibility / evidence_support）
    4. 可选：通过 LLM 进行假设精炼与闭环验证
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行假设生成阶段，返回 hypotheses / metadata 等字段。"""
        return self.pipeline.phase_handlers.execute_hypothesis_phase(cycle, context or {})
