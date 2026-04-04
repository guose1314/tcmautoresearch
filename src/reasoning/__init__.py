"""兼容层 — reasoning 已迁移至 src.analysis.reasoning_engine

.. deprecated:: 2.0
    请改用 ``from src.analysis.reasoning_engine import ReasoningEngine``
"""
import warnings as _warnings

_warnings.warn(
    "src.reasoning 已迁移至 src.analysis.reasoning_engine，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.analysis.reasoning_engine import ReasoningEngine  # noqa: F401
