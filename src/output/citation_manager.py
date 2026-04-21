# src/output/citation_manager.py
"""引用管理器（re-export 到 src.output 命名空间，保持导入兼容性）。"""
from src.generation.citation_manager import (  # noqa: F401
    CitationEntry,
    CitationLibrary,
    CitationManager,
)

__all__ = ["CitationEntry", "CitationLibrary", "CitationManager"]
