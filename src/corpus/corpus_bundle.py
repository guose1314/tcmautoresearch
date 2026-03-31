"""兼容层 — 已迁移至 src.collector.corpus_bundle

.. deprecated:: 使用 ``from src.collector.corpus_bundle import ...``
"""
from src.collector.corpus_bundle import *  # noqa: F401,F403
from src.collector.corpus_bundle import (
    BUNDLE_SCHEMA_VERSION,
    CorpusBundle,
    CorpusDocument,
    _make_bundle_id,
    _make_doc_id,
    extract_text_entries,
    is_corpus_bundle,
)
