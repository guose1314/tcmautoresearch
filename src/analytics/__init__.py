"""src/analytics — 兼容层（已迁移至 src/analysis/data_mining）

.. deprecated::
    请改用 ``from src.analysis.data_mining import ...``，本包保留仅为向后兼容。
"""

import warnings as _warnings

_warnings.warn(
    "src.analytics 已迁移至 src.analysis.data_mining，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from .data_miner import DataMiner  # noqa: F401

__all__ = ["DataMiner"]
