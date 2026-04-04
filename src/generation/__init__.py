"""src/generation — BC4: 成果输出上下文

按架构 3.0 新增，聚合论文撰写、科研图片、引用管理、输出格式化等模块。

公共导出：
* :class:`CitationManager`   — BibTeX 引用管理
* :class:`CitationEntry`     — 引用条目数据类
* :class:`CitationLibrary`   — 参考文献库摘要
* :class:`FigureGenerator`   — 科研图片生成
* :class:`FigureSpec`        — 图片规格
* :class:`FigureResult`      — 图片结果
* :class:`PaperWriter`       — IMRD 论文初稿撰写
* :class:`PaperDraft`        — 初稿数据结构
* :class:`PaperSection`      — 章节数据结构
* :class:`OutputFormatter`   — 输出格式化（原 OutputGenerator）
"""

from src.generation.citation_manager import (
    CitationEntry,
    CitationLibrary,
    CitationManager,
)
from src.generation.figure_generator import FigureGenerator, FigureResult, FigureSpec
from src.generation.output_formatter import OutputGenerator
from src.generation.paper_writer import PaperDraft, PaperSection, PaperWriter
from src.generation.report_generator import Report, ReportFormat, ReportGenerator

# 架构 3.0 规范名称
OutputFormatter = OutputGenerator

__all__ = [
    "CitationEntry",
    "CitationLibrary",
    "CitationManager",
    "FigureGenerator",
    "FigureSpec",
    "FigureResult",
    "PaperWriter",
    "PaperDraft",
    "PaperSection",
    "OutputGenerator",
    "OutputFormatter",
    "Report",
    "ReportFormat",
    "ReportGenerator",
]
