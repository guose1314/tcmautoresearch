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

