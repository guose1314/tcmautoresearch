"""兼容层 — 已迁移至 src.collector.ctext_corpus_collector

.. deprecated:: 2.0
    请改用 ``from src.collector.ctext_corpus_collector import ...``
"""
import warnings as _warnings

_warnings.warn(
    "src.research.ctext_corpus_collector 已迁移至 src.collector.ctext_corpus_collector，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.collector.ctext_corpus_collector import *  # noqa: F401,F403
from src.collector.ctext_corpus_collector import CTextCorpusCollector
