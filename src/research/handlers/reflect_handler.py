# src/research/handlers/reflect_handler.py
"""反思阶段处理器：方法论改进、数据质量反馈与下一轮规划。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase


class ReflectPhaseHandler(BasePhaseHandler):
    """
    反思阶段处理器。

    负责：
    1. 对本轮研究过程进行方法论反思
    2. 分析数据质量问题
    3. 生成改进计划，供下一轮迭代参考
    4. 可选：触发 SelfLearningEngine 学习
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行反思阶段，返回 reflections / improvement_plan 等字段。"""
        return self.pipeline.phase_handlers.execute_reflect_phase(cycle, context or {})
