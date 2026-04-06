# research/__init__.py
"""
中医古籍全自动研究系统 - 专业学术研究框架（延迟导入优化）
"""

import importlib as _importlib
from typing import TYPE_CHECKING

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于AI的中医古籍研究理论框架与科研流程管理系统"

if TYPE_CHECKING:
    from src.analysis.multimodal_fusion import FusionStrategy, MultimodalFusionEngine
    from src.collector.ctext_corpus_collector import CTextCorpusCollector
    from src.collector.ctext_whitelist import build_batch_manifest, load_whitelist
    from src.collector.literature_retriever import LiteratureRecord, LiteratureRetriever
    from src.collector.multi_source_corpus import (
        SourceWitness,
        build_source_collection_plan,
        build_witnesses_from_records,
        cross_validate_witnesses,
        load_source_registry,
        recognize_classical_format,
    )

    from .arxiv_fine_translation import (
        ArxivFineTranslationResult,
        run_arxiv_fine_translation_docker,
    )
    from .arxiv_quick_helper import (
        ArxivQuickHelperResult,
        run_arxiv_quick_helper,
    )
    from .audit_history import AuditEntry, AuditHistory
    from .data_miner import DataMiner
    from .gap_analyzer import (
        GapAnalysisRequest,
        GapAnalysisResult,
        GapAnalyzer,
        GapAnalyzerConfig,
    )
    from .google_scholar_helper import (
        GoogleScholarHelperResult,
        run_google_scholar_related_works,
    )
    from .hypothesis_engine import Hypothesis, HypothesisEngine
    from .markdown_translate import MarkdownTranslateResult, run_markdown_translate
    from .pdf_translation import (
        PdfTranslationResult,
        run_pdf_full_text_translation,
    )
    from .pipeline_events import (
        AUDIT_EVENT_LEGACY_NAMES,
        AUDIT_EVENT_NAMES,
        PHASE_LIFECYCLE_EVENT_NAMES,
        publish_audit_event,
        publish_phase_lifecycle_event,
    )
    from .research_pipeline import ResearchCycle, ResearchPhase, ResearchPipeline
    from .study_session_manager import (
        ResearchCycleStatus,
        StudySessionManager,
    )
    from .theoretical_framework import (
        ResearchExperiment,
        ResearchHypothesis,
        ResearchInsight,
        TheoreticalFramework,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # -- collector re-exports --
    "CTextCorpusCollector": ("src.collector.ctext_corpus_collector", "CTextCorpusCollector"),
    "LiteratureRetriever": ("src.collector.literature_retriever", "LiteratureRetriever"),
    "LiteratureRecord": ("src.collector.literature_retriever", "LiteratureRecord"),
    "load_whitelist": ("src.collector.ctext_whitelist", "load_whitelist"),
    "build_batch_manifest": ("src.collector.ctext_whitelist", "build_batch_manifest"),
    "SourceWitness": ("src.collector.multi_source_corpus", "SourceWitness"),
    "load_source_registry": ("src.collector.multi_source_corpus", "load_source_registry"),
    "recognize_classical_format": ("src.collector.multi_source_corpus", "recognize_classical_format"),
    "build_source_collection_plan": ("src.collector.multi_source_corpus", "build_source_collection_plan"),
    "build_witnesses_from_records": ("src.collector.multi_source_corpus", "build_witnesses_from_records"),
    "cross_validate_witnesses": ("src.collector.multi_source_corpus", "cross_validate_witnesses"),
    # -- analysis re-exports --
    "MultimodalFusionEngine": ("src.analysis.multimodal_fusion", "MultimodalFusionEngine"),
    "FusionStrategy": ("src.analysis.multimodal_fusion", "FusionStrategy"),
    # -- research sub-modules --
    "TheoreticalFramework": (".theoretical_framework", "TheoreticalFramework"),
    "ResearchHypothesis": (".theoretical_framework", "ResearchHypothesis"),
    "ResearchExperiment": (".theoretical_framework", "ResearchExperiment"),
    "ResearchInsight": (".theoretical_framework", "ResearchInsight"),
    "ResearchPipeline": (".research_pipeline", "ResearchPipeline"),
    "ResearchCycle": (".research_pipeline", "ResearchCycle"),
    "ResearchPhase": (".research_pipeline", "ResearchPhase"),
    "ResearchCycleStatus": (".study_session_manager", "ResearchCycleStatus"),
    "StudySessionManager": (".study_session_manager", "StudySessionManager"),
    "ArxivFineTranslationResult": (".arxiv_fine_translation", "ArxivFineTranslationResult"),
    "run_arxiv_fine_translation_docker": (".arxiv_fine_translation", "run_arxiv_fine_translation_docker"),
    "MarkdownTranslateResult": (".markdown_translate", "MarkdownTranslateResult"),
    "run_markdown_translate": (".markdown_translate", "run_markdown_translate"),
    "PdfTranslationResult": (".pdf_translation", "PdfTranslationResult"),
    "run_pdf_full_text_translation": (".pdf_translation", "run_pdf_full_text_translation"),
    "ArxivQuickHelperResult": (".arxiv_quick_helper", "ArxivQuickHelperResult"),
    "run_arxiv_quick_helper": (".arxiv_quick_helper", "run_arxiv_quick_helper"),
    "AuditHistory": (".audit_history", "AuditHistory"),
    "AuditEntry": (".audit_history", "AuditEntry"),
    "AUDIT_EVENT_NAMES": (".pipeline_events", "AUDIT_EVENT_NAMES"),
    "AUDIT_EVENT_LEGACY_NAMES": (".pipeline_events", "AUDIT_EVENT_LEGACY_NAMES"),
    "PHASE_LIFECYCLE_EVENT_NAMES": (".pipeline_events", "PHASE_LIFECYCLE_EVENT_NAMES"),
    "publish_audit_event": (".pipeline_events", "publish_audit_event"),
    "publish_phase_lifecycle_event": (".pipeline_events", "publish_phase_lifecycle_event"),
    "GoogleScholarHelperResult": (".google_scholar_helper", "GoogleScholarHelperResult"),
    "run_google_scholar_related_works": (".google_scholar_helper", "run_google_scholar_related_works"),
    "DataMiner": (".data_miner", "DataMiner"),
    "GapAnalyzer": (".gap_analyzer", "GapAnalyzer"),
    "GapAnalyzerConfig": (".gap_analyzer", "GapAnalyzerConfig"),
    "GapAnalysisRequest": (".gap_analyzer", "GapAnalysisRequest"),
    "GapAnalysisResult": (".gap_analyzer", "GapAnalysisResult"),
    "Hypothesis": (".hypothesis_engine", "Hypothesis"),
    "HypothesisEngine": (".hypothesis_engine", "HypothesisEngine"),
}

# 模块导出
__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        if module_path.startswith("."):
            mod = _importlib.import_module(module_path, __name__)
        else:
            mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
