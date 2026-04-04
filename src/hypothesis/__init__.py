"""假设引擎模块导出（已弃用）— 规范路径为 src.research.hypothesis_engine。"""
import warnings as _w

_w.warn(
    "src.hypothesis 包已弃用，请改用 src.research.hypothesis_engine",
    DeprecationWarning,
    stacklevel=2,
)

from src.research.hypothesis_engine import (
    Hypothesis as HypothesisCandidate,
)
from src.research.hypothesis_engine import (
    HypothesisEngine,
)

# ValidationIteration 已在规范实现中移除；提供占位以兼容旧代码
ValidationIteration = None

__all__ = ["HypothesisEngine", "HypothesisCandidate", "ValidationIteration"]
