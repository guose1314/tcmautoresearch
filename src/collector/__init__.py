"""src/collector — BC1: 文献采集上下文

按架构 3.0 重组，聚合原 src/corpus + src/research 中的采集类模块。

公共导出：
* :class:`CorpusBundle`           — 多来源语料束
* :class:`CorpusDocument`         — 单文档统一 schema
* :class:`LocalCorpusCollector`   — 本地文件采集器
* :class:`CTextCorpusCollector`   — ctext.org 古籍采集器
* :class:`LiteratureRetriever`    — 多源文献检索
* :class:`LiteratureRecord`       — 文献记录数据类
"""

from src.collector.corpus_bundle import (
    BUNDLE_SCHEMA_VERSION,
    CorpusBundle,
    CorpusDocument,
    extract_text_entries,
    is_corpus_bundle,
)
from src.collector.ctext_corpus_collector import CTextCorpusCollector
from src.collector.ctext_whitelist import build_batch_manifest, load_whitelist
from src.collector.format_converter import ConversionResult, FormatConverter
from src.collector.literature_retriever import LiteratureRecord, LiteratureRetriever
from src.collector.local_collector import LocalCorpusCollector
from src.collector.multi_source_corpus import (
    SourceWitness,
    build_source_collection_plan,
    build_witnesses_from_records,
    cross_validate_witnesses,
    load_source_registry,
    recognize_classical_format,
)
from src.collector.normalizer import NormalizationResult, Normalizer

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "CorpusBundle",
    "CorpusDocument",
    "extract_text_entries",
    "is_corpus_bundle",
    "FormatConverter",
    "ConversionResult",
    "Normalizer",
    "NormalizationResult",
    "LocalCorpusCollector",
    "CTextCorpusCollector",
    "LiteratureRetriever",
    "LiteratureRecord",
    "build_batch_manifest",
    "load_whitelist",
    "SourceWitness",
    "build_source_collection_plan",
    "build_witnesses_from_records",
    "cross_validate_witnesses",
    "load_source_registry",
    "recognize_classical_format",
]
