# research/__init__.py
"""
中医古籍全自动研究系统 - 专业学术研究框架初始化文件
"""

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于AI的中医古籍研究理论框架与科研流程管理系统"

# 导入主要类和函数
from .arxiv_fine_translation import (
    ArxivFineTranslationResult,
    run_arxiv_fine_translation_docker,
)
from .arxiv_quick_helper import (
    ArxivQuickHelperResult,
    run_arxiv_quick_helper,
)
from .audit_history import AuditEntry, AuditHistory
from .ctext_corpus_collector import CTextCorpusCollector
from .ctext_whitelist import build_batch_manifest, load_whitelist
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
from .literature_retriever import LiteratureRecord, LiteratureRetriever
from .markdown_translate import MarkdownTranslateResult, run_markdown_translate
from .multi_source_corpus import (
    SourceWitness,
    build_source_collection_plan,
    build_witnesses_from_records,
    cross_validate_witnesses,
    load_source_registry,
    recognize_classical_format,
)
from .multimodal_fusion import FusionStrategy, MultimodalFusionEngine
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

# 系统配置
SYSTEM_CONFIG = {
    'research_framework': {
        'name': '中医古籍全自动研究框架',
        'version': '2.0.0',
        'standards': ['T/C IATCM 098-2023', 'GB/T 15657', 'ISO 21000'],
        'principles': [
            '系统性原则',
            '科学性原则', 
            '实用性原则',
            '创新性原则'
        ]
    },
    'research_phases': [
        '观察',
        '假设',
        '实验',
        '分析',
        '发布',
        '反思'
    ],
    'academic_levels': {
        'basic': '基础研究',
        'applied': '应用研究',
        'innovative': '创新研究',
        'comprehensive': '综合研究'
    },
    'evaluation_metrics': {
        'scientific_validity': 0.3,
        'methodological_quality': 0.25,
        'innovation_degree': 0.2,
        'practical_value': 0.25
    }
}

# 研究范式
RESEARCH_PARADIGMS = {
    'traditional': {
        'name': '传统研究范式',
        'characteristics': ['经验总结', '案例分析', '理论归纳'],
        'applications': ['古籍整理', '经验传承', '理论建构']
    },
    'modern': {
        'name': '现代研究范式',
        'characteristics': ['数据驱动', '模型构建', '实证分析'],
        'applications': ['知识发现', '智能推理', '预测建模']
    },
    'hybrid': {
        'name': '混合研究范式',
        'characteristics': ['传统+现代', '定性+定量', '经验+理论'],
        'applications': ['智能古籍研究', '跨学科融合', '系统工程']
    }
}

# 研究方法论
RESEARCH_METHODS = {
    'qualitative': {
        'name': '定性研究方法',
        'approaches': ['文本分析', '案例研究', '专家访谈'],
        'tools': ['内容分析', '主题分析', '话语分析']
    },
    'quantitative': {
        'name': '定量研究方法',
        'approaches': ['统计分析', '机器学习', '数据挖掘'],
        'tools': ['TF-IDF', 'Word2Vec', 'BERT']
    },
    'mixed': {
        'name': '混合研究方法',
        'approaches': ['混合分析', '多方法融合', '跨学科研究'],
        'tools': ['多模态分析', '知识图谱', '深度学习']
    }
}

# 学术规范
ACADEMIC_STANDARDS = {
    'ethics': {
        'data_privacy': '严格遵守数据隐私保护规定',
        'research_integrity': '确保研究过程的客观性和真实性',
        'citation_standard': '遵循GB/T 7714-2015标准'
    },
    'quality_control': {
        'peer_review': '实施同行评议制度',
        'reproducibility': '确保研究结果可重现',
        'validation': '建立多维度验证机制'
    },
    'publication_requirements': {
        'journal_standards': ['SCI', 'EI', '核心期刊'],
        'format_requirements': ['学术论文', '研究报告', '技术报告'],
        'review_process': ['初审', '外审', '终审']
    }
}

# 初始化日志配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍研究框架模块已初始化")

# 版本兼容性声明
VERSION_COMPATIBILITY = {
    'python': '>=3.8',
    'numpy': '>=1.21.0',
    'pandas': '>=1.3.0',
    'torch': '>=1.9.0',
    'transformers': '>=4.20.0',
    'networkx': '>=2.6.0'
}
