# src/research/handlers/publish_handler.py
"""发布阶段处理器：论文生成、引文管理与报告输出。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.handlers.base_handler import BasePhaseHandler

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline


class PublishPhaseHandler(BasePhaseHandler):
    """
    发布阶段处理器。

    负责：
    1. 整合前序阶段结果（observe / hypothesis / experiment / analyze）
    2. 调用 CitationManager 生成引文（BibTeX / GB/T 7714）
    3. 调用 PaperWriter 生成 IMRD 结构论文草稿（Markdown / DOCX）
    4. 调用 ReportGenerator 生成研究报告
    5. 返回论文草稿、引文、报告路径等
    """

    def handle(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行发布阶段，返回 publications / paper_draft / deliverables 等字段。"""
        return self.pipeline.phase_handlers.execute_publish_phase(cycle, context or {})
