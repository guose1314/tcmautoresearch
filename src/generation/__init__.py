"""src/generation — BC4: 成果输出上下文（延迟导入优化）

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

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.generation.citation_manager import (
        CitationEntry,
        CitationLibrary,
        CitationManager,
    )
    from src.generation.figure_generator import (
        FigureGenerator,
        FigureResult,
        FigureSpec,
    )
    from src.generation.llm_context_adapter import (
        LLMContextAdaptedPaperWriter,
        LLMContextAdapter,
        wrap_paper_writer_with_llm_context,
    )
    from src.generation.output_formatter import OutputGenerator
    from src.generation.paper_writer import PaperDraft, PaperSection, PaperWriter
    from src.generation.report_generator import Report, ReportFormat, ReportGenerator

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "CitationEntry": ("src.generation.citation_manager", "CitationEntry"),
    "CitationLibrary": ("src.generation.citation_manager", "CitationLibrary"),
    "CitationManager": ("src.generation.citation_manager", "CitationManager"),
    "FigureGenerator": ("src.generation.figure_generator", "FigureGenerator"),
    "FigureSpec": ("src.generation.figure_generator", "FigureSpec"),
    "FigureResult": ("src.generation.figure_generator", "FigureResult"),
    "LLMContextAdapter": ("src.generation.llm_context_adapter", "LLMContextAdapter"),
    "LLMContextAdaptedPaperWriter": ("src.generation.llm_context_adapter", "LLMContextAdaptedPaperWriter"),
    "wrap_paper_writer_with_llm_context": ("src.generation.llm_context_adapter", "wrap_paper_writer_with_llm_context"),
    "PaperWriter": ("src.generation.paper_writer", "PaperWriter"),
    "PaperDraft": ("src.generation.paper_writer", "PaperDraft"),
    "PaperSection": ("src.generation.paper_writer", "PaperSection"),
    "OutputGenerator": ("src.generation.output_formatter", "OutputGenerator"),
    "OutputFormatter": ("src.generation.output_formatter", "OutputGenerator"),
    "Report": ("src.generation.report_generator", "Report"),
    "ReportFormat": ("src.generation.report_generator", "ReportFormat"),
    "ReportGenerator": ("src.generation.report_generator", "ReportGenerator"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
