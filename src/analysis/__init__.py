"""src/analysis — BC2: 文本分析上下文

按架构 3.0 重组，聚合原 preprocessor/ + extractors/ + semantic_modeling/
+ reasoning/ + multimodal_fusion 等分析类模块。

公共导出：
* :class:`DocumentPreprocessor`  — 文档预处理（jieba + opencc）
* :class:`AdvancedEntityExtractor` — TCM 实体抽取
* :class:`SemanticGraphBuilder`  — 语义图构建
* :class:`ReasoningEngine`       — 推理分析
* :class:`DataMiningService`     — 关联规则/聚类/频繁项集挖掘
* :class:`MultimodalFusionEngine` — 多模态融合
* :class:`GapAnalyzer`           — 间隙分析
"""

from src.analysis.complexity_dynamics import ComplexityNonlinearDynamicsAnalyzer
from src.analysis.data_mining import DataMiningService
from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.formula_comparator import FormulaComparator
from src.analysis.formula_structure import FormulaStructureAnalyzer
from src.research.gap_analyzer import GapAnalysisRequest, GapAnalyzer
from src.analysis.herb_properties import (
    HerbPropertyDatabase,
    HerbTemperature,
    MeridianType,
)
from src.analysis.knowledge_archaeology import ClassicalLiteratureArchaeologyAnalyzer
from src.analysis.multimodal_fusion import FusionStrategy, MultimodalFusionEngine
from src.analysis.network_pharmacology import NetworkPharmacologySystemBiologyAnalyzer
from src.analysis.pharmacology import ModernPharmacologyDatabase, PharmacologicalData
from src.analysis.preprocessor import DocumentPreprocessor
from src.analysis.reasoning_engine import ReasoningEngine
from src.analysis.research_scoring import ResearchScoringPanel
from src.analysis.semantic_graph import SemanticGraphBuilder
from src.analysis.summary_analysis import SummaryAnalysisEngine
from src.analysis.supramolecular import SupramolecularPhysicochemicalAnalyzer

__all__ = [
    "DocumentPreprocessor",
    "AdvancedEntityExtractor",
    "SemanticGraphBuilder",
    "ReasoningEngine",
    "DataMiningService",
    "MultimodalFusionEngine",
    "FusionStrategy",
    "FormulaStructureAnalyzer",
    "FormulaComparator",
    "HerbTemperature",
    "MeridianType",
    "HerbPropertyDatabase",
    "PharmacologicalData",
    "ModernPharmacologyDatabase",
    "NetworkPharmacologySystemBiologyAnalyzer",
    "SupramolecularPhysicochemicalAnalyzer",
    "ClassicalLiteratureArchaeologyAnalyzer",
    "ComplexityNonlinearDynamicsAnalyzer",
    "ResearchScoringPanel",
    "SummaryAnalysisEngine",
    "GapAnalyzer",
    "GapAnalysisRequest",
]