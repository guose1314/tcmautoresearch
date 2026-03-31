"""src/corpus — 兼容层（已迁移至 src/collector）

.. deprecated::
    请改用 ``from src.collector import ...``，本包保留仅为向后兼容。
"""

import warnings as _warnings

_warnings.warn(
    "src.corpus 已迁移至 src.collector，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.collector.corpus_bundle import (  # noqa: F401
    BUNDLE_SCHEMA_VERSION,
    CorpusBundle,
    CorpusDocument,
    extract_text_entries,
    is_corpus_bundle,
)
from src.collector.local_collector import LocalCorpusCollector  # noqa: F401

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "CorpusBundle",
    "CorpusDocument",
    "extract_text_entries",
    "is_corpus_bundle",
    "LocalCorpusCollector",
]
