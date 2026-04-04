"""兼容层 — 已迁移至 src.collector.literature_retriever

.. deprecated:: 2.0
    请改用 ``from src.collector.literature_retriever import ...``
"""
import warnings as _warnings

_warnings.warn(
    "src.research.literature_retriever 已迁移至 src.collector.literature_retriever，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.collector.literature_retriever import *  # noqa: F401,F403
from src.collector.literature_retriever import LiteratureRecord, LiteratureRetriever
