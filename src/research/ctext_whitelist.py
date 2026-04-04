"""兼容层 — 已迁移至 src.collector.ctext_whitelist

.. deprecated:: 2.0
    请改用 ``from src.collector.ctext_whitelist import ...``
"""
import warnings as _warnings

_warnings.warn(
    "src.research.ctext_whitelist 已迁移至 src.collector.ctext_whitelist，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.collector.ctext_whitelist import *  # noqa: F401,F403
from src.collector.ctext_whitelist import build_batch_manifest, load_whitelist
