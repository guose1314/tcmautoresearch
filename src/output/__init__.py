# src/output/__init__.py
"""
输出生成包（已弃用）— 规范导入路径已迁移至 src.generation。
"""
import warnings as _w

_w.warn(
    "src.output 包已弃用，请改用 src.generation",
    DeprecationWarning,
    stacklevel=2,
)

from src.output.output_generator import OutputGenerator

__all__ = ["OutputGenerator"]
