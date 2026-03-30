"""src/corpus — 多来源 CorpusBundle 包

公共导出：

* :class:`CorpusDocument`     — 单文档统一 schema
* :class:`CorpusBundle`       — 多来源语料束
* :func:`is_corpus_bundle`    — 新旧格式判别
* :func:`extract_text_entries`— 统一文本条目提取（兼容新旧格式）
* :class:`LocalCorpusCollector` — 本地文件采集器
"""

from src.corpus.corpus_bundle import (
    BUNDLE_SCHEMA_VERSION,
    CorpusBundle,
    CorpusDocument,
    extract_text_entries,
    is_corpus_bundle,
)
from src.corpus.local_collector import LocalCorpusCollector

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "CorpusBundle",
    "CorpusDocument",
    "extract_text_entries",
    "is_corpus_bundle",
    "LocalCorpusCollector",
]
