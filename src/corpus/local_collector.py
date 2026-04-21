"""兼容层 — 已迁移至 src.collector.local_collector

.. deprecated:: 使用 ``from src.collector.local_collector import ...``
"""
from src.collector.local_collector import *  # noqa: F401,F403
from src.collector.local_collector import (  # noqa: F401
    LocalCorpusCollector,
    _infer_title,
)
