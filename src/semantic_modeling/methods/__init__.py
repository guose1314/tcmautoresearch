# src/semantic_modeling/methods/__init__.py
"""
research_methods 子模块包 — 向后兼容 re-export shim。

所有公共类/枚举均可通过以下方式访问：
    from src.semantic_modeling.methods import FormulaStructureAnalyzer
或原始路径:
    from src.semantic_modeling.research_methods import FormulaStructureAnalyzer
"""

# 直接从子模块导入，避免与 research_methods.py 形成循环依赖
from src.semantic_modeling.methods.classical_literature import (
    ClassicalLiteratureArchaeologyAnalyzer,
)
from src.semantic_modeling.methods.complexity_science import (
    ComplexityNonlinearDynamicsAnalyzer,
)
from src.semantic_modeling.methods.formula_comparator import (
    FormulaComparator,
    FormulaComparison,
)
from src.semantic_modeling.methods.formula_structure import (
    FormulaDosageForm,
    FormulaComposition,
    FormulaStructure,
    FormulaStructureAnalyzer,
    HerbDosage,
)
from src.semantic_modeling.methods.herb_properties import (
    HerbProperty,
    HerbPropertyDatabase,
    HerbTemperature,
    MeridianType,
)
from src.semantic_modeling.methods.integrated_analyzer import (
    IntegratedResearchAnalyzer,
)
from src.semantic_modeling.methods.network_pharmacology import (
    NetworkPharmacologySystemBiologyAnalyzer,
)
from src.semantic_modeling.methods.pharmacology import (
    ModernPharmacologyDatabase,
    PharmacologicalData,
)
from src.semantic_modeling.methods.scoring_panel import ResearchScoringPanel  # noqa: F811
from src.semantic_modeling.methods.summary_engine import SummaryAnalysisEngine
from src.semantic_modeling.methods.supramolecular import (
    SupramolecularPhysicochemicalAnalyzer,
)
from src.semantic_modeling.methods.meta_analysis import (  # noqa: F401  I-05
    MetaAnalysisEngine,
    MetaAnalysisResult,
    StudyEffect,
)

__all__ = [
    "ClassicalLiteratureArchaeologyAnalyzer",
    "ComplexityNonlinearDynamicsAnalyzer",
    "FormulaComparator",
    "FormulaComparison",
    "FormulaComposition",
    "FormulaDosageForm",
    "FormulaStructure",
    "FormulaStructureAnalyzer",
    "HerbDosage",
    "HerbProperty",
    "HerbPropertyDatabase",
    "HerbTemperature",
    "IntegratedResearchAnalyzer",
    "MeridianType",
    "MetaAnalysisEngine",
    "MetaAnalysisResult",
    "ModernPharmacologyDatabase",
    "NetworkPharmacologySystemBiologyAnalyzer",
    "PharmacologicalData",
    "ResearchScoringPanel",
    "StudyEffect",
    "SummaryAnalysisEngine",
    "SupramolecularPhysicochemicalAnalyzer",
]
