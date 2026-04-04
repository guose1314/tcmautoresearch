"""兼容层 — 已迁移至 src.analysis.multimodal_fusion

.. deprecated:: 2.0
    请改用 ``from src.analysis.multimodal_fusion import ...``
"""
import warnings as _warnings

_warnings.warn(
    "src.research.multimodal_fusion 已迁移至 src.analysis.multimodal_fusion，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.analysis.multimodal_fusion import *  # noqa: F401,F403
from src.analysis.multimodal_fusion import FusionStrategy, MultimodalFusionEngine
