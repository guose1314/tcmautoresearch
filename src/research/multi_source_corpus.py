"""兼容层 — 已迁移至 src.collector.multi_source_corpus

.. deprecated:: 2.0
    请改用 ``from src.collector.multi_source_corpus import ...``
"""
import warnings as _warnings

_warnings.warn(
    "src.research.multi_source_corpus 已迁移至 src.collector.multi_source_corpus，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.collector.multi_source_corpus import *  # noqa: F401,F403
from src.collector.multi_source_corpus import (
    SourceWitness,
    build_source_collection_plan,
    build_witnesses_from_records,
    cross_validate_witnesses,
    load_source_registry,
    recognize_classical_format,
)
