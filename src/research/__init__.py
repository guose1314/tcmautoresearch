# research/__init__.py
"""
中医古籍全自动研究系统 - 专业学术研究框架初始化文件
"""

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于AI的中医古籍研究理论框架与科研流程管理系统"

# 导入主要类和函数
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

# 模块导出
__all__ = [
    'TheoreticalFramework',
    'ResearchHypothesis',
    'ResearchExperiment',
    'ResearchInsight',
    'ResearchPipeline',
    'ResearchCycle',
    'ResearchPhase',
    'ResearchCycleStatus',
    'StudySessionManager',
    'ArxivFineTranslationResult',
    'run_arxiv_fine_translation_docker',
    'MarkdownTranslateResult',
    'run_markdown_translate',
    'PdfTranslationResult',
    'run_pdf_full_text_translation',
    'ArxivQuickHelperResult',
    'run_arxiv_quick_helper',
    'AuditHistory',
    'AuditEntry',
    'AUDIT_EVENT_NAMES',
    'AUDIT_EVENT_LEGACY_NAMES',
    'PHASE_LIFECYCLE_EVENT_NAMES',
    'publish_audit_event',
    'publish_phase_lifecycle_event',
    'GoogleScholarHelperResult',
    'run_google_scholar_related_works',
    'DataMiner',
    'GapAnalyzer',
    'GapAnalyzerConfig',
    'GapAnalysisRequest',
    'GapAnalysisResult',
    'Hypothesis',
    'HypothesisEngine',
    'CTextCorpusCollector',
    'LiteratureRetriever',
    'LiteratureRecord',
    'load_whitelist',
    'build_batch_manifest',
    'SourceWitness',
    'load_source_registry',
    'recognize_classical_format',
    'build_source_collection_plan',
    'build_witnesses_from_records',
    'cross_validate_witnesses'
    ,'MultimodalFusionEngine'
    ,'FusionStrategy'
]

# ──────────────────────────────────────────────────────────────────────
# 以下静态配置字典已迁移至 config/reference_constants.yml（无消费者引用）。
# ──────────────────────────────────────────────────────────────────────

# 初始化日志配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍研究框架模块已初始化")
