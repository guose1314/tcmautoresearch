"""兼容层 - extractors 已迁移至 src.analysis.entity_extractor

.. deprecated:: 2.0
    请改用 ``from src.analysis.entity_extractor import AdvancedEntityExtractor``
"""
import warnings as _warnings

_warnings.warn(
    "src.extractors 已迁移至 src.analysis.entity_extractor，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.analysis.entity_extractor import AdvancedEntityExtractor  # noqa: F401
