# src/research/handlers/observe_handler.py
"""观察阶段处理器：文献采集、预处理、实体抽取与语义建模。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline


class ObservePhaseHandler(BasePhaseHandler):
    """
    观察阶段处理器。

    负责：
    1. 从 CText / 本地语料库 / 文献数据库采集原始数据
    2. 文档预处理（分词、标准化）
    3. 实体抽取与语义图构建
    4. 推理引擎运行
    5. 临床 Gap Analysis（可选）
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行观察阶段，返回 observations / findings / corpus_collection 等字段。"""
        # 委托给原 ResearchPhaseHandlers 实现，保持完整业务逻辑不变
        return self.pipeline.phase_handlers.execute_observe_phase(cycle, context or {})
