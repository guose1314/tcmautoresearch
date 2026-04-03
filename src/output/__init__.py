# src/output/__init__.py
"""
输出生成包 — 将管线处理结果输出为 JSON、Markdown、DOCX 等格式。
"""

from src.output.output_generator import OutputGenerator

__all__ = ["OutputGenerator"]
