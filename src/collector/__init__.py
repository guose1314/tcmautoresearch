"""src/collector — BC1: 文献采集上下文（延迟导入优化）

按架构 3.0 重组，聚合原 src/corpus + src/research 中的采集类模块。

公共导出：
* :class:`CorpusBundle`           — 多来源语料束
* :class:`CorpusDocument`         — 单文档统一 schema
* :class:`LocalCorpusCollector`   — 本地文件采集器
* :class:`CTextCorpusCollector`   — ctext.org 古籍采集器
* :class:`LiteratureRetriever`    — 多源文献检索
* :class:`LiteratureRecord`       — 文献记录数据类
"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "BUNDLE_SCHEMA_VERSION": ("src.collector.corpus_bundle", "BUNDLE_SCHEMA_VERSION"),
    "CorpusBundle": ("src.collector.corpus_bundle", "CorpusBundle"),
    "CorpusDocument": ("src.collector.corpus_bundle", "CorpusDocument"),
    "extract_text_entries": ("src.collector.corpus_bundle", "extract_text_entries"),
    "is_corpus_bundle": ("src.collector.corpus_bundle", "is_corpus_bundle"),
    "FormatConverter": ("src.collector.format_converter", "FormatConverter"),
    "ConversionResult": ("src.collector.format_converter", "ConversionResult"),
    "Normalizer": ("src.collector.normalizer", "Normalizer"),
    "NormalizationResult": ("src.collector.normalizer", "NormalizationResult"),
    "LocalCorpusCollector": ("src.collector.local_collector", "LocalCorpusCollector"),
    "CTextCorpusCollector": ("src.collector.ctext_corpus_collector", "CTextCorpusCollector"),
    "LiteratureRetriever": ("src.collector.literature_retriever", "LiteratureRetriever"),
    "LiteratureRecord": ("src.collector.literature_retriever", "LiteratureRecord"),
    "build_batch_manifest": ("src.collector.ctext_whitelist", "build_batch_manifest"),
    "load_whitelist": ("src.collector.ctext_whitelist", "load_whitelist"),
    "SourceWitness": ("src.collector.multi_source_corpus", "SourceWitness"),
    "build_source_collection_plan": ("src.collector.multi_source_corpus", "build_source_collection_plan"),
    "build_witnesses_from_records": ("src.collector.multi_source_corpus", "build_witnesses_from_records"),
    "cross_validate_witnesses": ("src.collector.multi_source_corpus", "cross_validate_witnesses"),
    "load_source_registry": ("src.collector.multi_source_corpus", "load_source_registry"),
    "recognize_classical_format": ("src.collector.multi_source_corpus", "recognize_classical_format"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
