# src/research/handlers/base_handler.py
"""研究阶段处理器基类。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline


class BasePhaseHandler:
    """
    研究阶段处理器基类。

    所有阶段专属 Handler 均继承此类，通过 ``handle()`` 方法实现各阶段业务逻辑。
    通过 ``pipeline`` 属性访问共享的 ResearchPipeline 实例及其 config、模块工厂等资源。
    """

    def __init__(self, pipeline: "ResearchPipeline") -> None:
        self.pipeline = pipeline

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行阶段业务逻辑并返回结构化结果。

        子类必须覆盖此方法。

        Args:
            phase: 当前研究阶段枚举值。
            cycle: 当前研究周期对象。
            context: 调用方传入的执行上下文字典。

        Returns:
            包含 ``phase`` 键及阶段特定输出的字典。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} 未实现 handle() 方法。"
        )
