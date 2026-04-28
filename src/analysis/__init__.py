"""src/analysis — BC2: 文本分析上下文（延迟导入优化）

按架构 3.0 重组，聚合原 preprocessor/ + extractors/ + semantic_modeling/
+ reasoning/ + multimodal_fusion 等分析类模块。

公共导出：
* :class:`DocumentPreprocessor`  — 文档预处理（jieba + opencc）
* :class:`PhilologyService`      — 文献学服务（术语标准化/版本对勘）
* :class:`AdvancedEntityExtractor` — TCM 实体抽取
* :class:`SemanticGraphBuilder`  — 语义图构建
* :class:`ReasoningEngine`       — 推理分析
* :class:`DataMiningService`     — 关联规则/聚类/频繁项集挖掘
* :class:`MultimodalFusionEngine` — 多模态融合
* :class:`GapAnalyzer`           — 间隙分析
"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.analysis.complexity_dynamics import ComplexityNonlinearDynamicsAnalyzer
    from src.analysis.data_mining import DataMiningService
    from src.analysis.entity_extractor import AdvancedEntityExtractor
    from src.analysis.formula_comparator import FormulaComparator
    from src.analysis.formula_structure import FormulaStructureAnalyzer
    from src.analysis.herb_properties import (
        HerbPropertyDatabase,
        HerbTemperature,
        MeridianType,
    )
    from src.analysis.knowledge_archaeology import (
        ClassicalLiteratureArchaeologyAnalyzer,
    )
    from src.analysis.multimodal_fusion import FusionStrategy, MultimodalFusionEngine
    from src.analysis.network_pharmacology import (
        NetworkPharmacologySystemBiologyAnalyzer,
    )
    from src.analysis.pharmacology import (
        ModernPharmacologyDatabase,
        PharmacologicalData,
    )
    from src.analysis.philology_service import PhilologyService
    from src.analysis.preprocessor import DocumentPreprocessor
    from src.analysis.reasoning_engine import ReasoningEngine
    from src.analysis.research_scoring import ResearchScoringPanel
    from src.analysis.semantic_graph import SemanticGraphBuilder
    from src.analysis.summary_analysis import SummaryAnalysisEngine
    from src.analysis.supramolecular import SupramolecularPhysicochemicalAnalyzer
    from src.research.gap_analyzer import GapAnalysisRequest, GapAnalyzer
    from src.semantic_modeling.methods.integrated_analyzer import (
        IntegratedResearchAnalyzer,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "DocumentPreprocessor": ("src.analysis.preprocessor", "DocumentPreprocessor"),
    "PhilologyService": ("src.analysis.philology_service", "PhilologyService"),
    "AdvancedEntityExtractor": ("src.analysis.entity_extractor", "AdvancedEntityExtractor"),
    "SemanticGraphBuilder": ("src.analysis.semantic_graph", "SemanticGraphBuilder"),
    "ReasoningEngine": ("src.analysis.reasoning_engine", "ReasoningEngine"),
    "DataMiningService": ("src.analysis.data_mining", "DataMiningService"),
    "MultimodalFusionEngine": ("src.analysis.multimodal_fusion", "MultimodalFusionEngine"),
    "FusionStrategy": ("src.analysis.multimodal_fusion", "FusionStrategy"),
    "FormulaStructureAnalyzer": ("src.analysis.formula_structure", "FormulaStructureAnalyzer"),
    "FormulaComparator": ("src.analysis.formula_comparator", "FormulaComparator"),
    "HerbTemperature": ("src.analysis.herb_properties", "HerbTemperature"),
    "MeridianType": ("src.analysis.herb_properties", "MeridianType"),
    "HerbPropertyDatabase": ("src.analysis.herb_properties", "HerbPropertyDatabase"),
    "PharmacologicalData": ("src.analysis.pharmacology", "PharmacologicalData"),
    "ModernPharmacologyDatabase": ("src.analysis.pharmacology", "ModernPharmacologyDatabase"),
    "NetworkPharmacologySystemBiologyAnalyzer": ("src.analysis.network_pharmacology", "NetworkPharmacologySystemBiologyAnalyzer"),
    "SupramolecularPhysicochemicalAnalyzer": ("src.analysis.supramolecular", "SupramolecularPhysicochemicalAnalyzer"),
    "ClassicalLiteratureArchaeologyAnalyzer": ("src.analysis.knowledge_archaeology", "ClassicalLiteratureArchaeologyAnalyzer"),
    "ComplexityNonlinearDynamicsAnalyzer": ("src.analysis.complexity_dynamics", "ComplexityNonlinearDynamicsAnalyzer"),
    "ResearchScoringPanel": ("src.analysis.research_scoring", "ResearchScoringPanel"),
    "SummaryAnalysisEngine": ("src.analysis.summary_analysis", "SummaryAnalysisEngine"),
    "GapAnalyzer": ("src.research.gap_analyzer", "GapAnalyzer"),
    "GapAnalysisRequest": ("src.research.gap_analyzer", "GapAnalysisRequest"),
    "IntegratedResearchAnalyzer": ("src.semantic_modeling.methods.integrated_analyzer", "IntegratedResearchAnalyzer"),
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