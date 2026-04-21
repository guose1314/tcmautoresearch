# src/research/handlers/experiment_handler.py
"""实验设计阶段处理器：根据选定假设生成实验方案。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline


class ExperimentPhaseHandler(BasePhaseHandler):
    """
    实验设计阶段处理器。

    负责：
    1. 从前序假设阶段选取最优假设
    2. 构建实验上下文（证据矩阵、临床 Gap、数据来源权重）
    3. 调用 TheoreticalFramework.design_experiment() 生成完整实验方案
    4. 输出研究设计、样本量、方法论、验证指标等
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行实验设计阶段，返回 experiments / results / selected_hypothesis 等字段。"""
        return self.pipeline.phase_handlers.execute_experiment_phase(cycle, context or {})
