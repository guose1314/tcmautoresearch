"""兼容层 — preprocessor 已迁移至 src.analysis.preprocessor

.. deprecated:: 2.0
    请改用 ``from src.analysis.preprocessor import DocumentPreprocessor``
"""
import warnings as _warnings

_warnings.warn(
    "src.preprocessor 已迁移至 src.analysis.preprocessor，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.analysis.preprocessor import DocumentPreprocessor  # noqa: F401
