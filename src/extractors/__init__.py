"""src/extractors — 兼容层（已迁移至 src/analysis/entity_extractor）

.. deprecated::
    请改用 ``from src.analysis.entity_extractor import ...``，本包保留仅为向后兼容。
"""

import warnings as _warnings

_warnings.warn(
    "src.extractors 已迁移至 src.analysis.entity_extractor，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.analysis.entity_extractor import AdvancedEntityExtractor  # noqa: F401

__all__ = ["AdvancedEntityExtractor"]
