"""研究方法子模块（架构3.0拆分）。"""

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "FormulaDosageForm": ("src.semantic_modeling.methods.formula_structure", "FormulaDosageForm"),
    "HerbDosage": ("src.semantic_modeling.methods.formula_structure", "HerbDosage"),
    "FormulaStructure": ("src.semantic_modeling.methods.formula_structure", "FormulaStructure"),
    "FormulaComposition": ("src.semantic_modeling.methods.formula_structure", "FormulaComposition"),
    "FormulaStructureAnalyzer": ("src.semantic_modeling.methods.formula_structure", "FormulaStructureAnalyzer"),
    "HerbTemperature": ("src.semantic_modeling.methods.formula_structure", "HerbTemperature"),
    "MeridianType": ("src.semantic_modeling.methods.formula_structure", "MeridianType"),
    "HerbProperty": ("src.semantic_modeling.methods.formula_structure", "HerbProperty"),
    "HerbPropertyDatabase": ("src.semantic_modeling.methods.formula_structure", "HerbPropertyDatabase"),
    "FormulaComparison": ("src.semantic_modeling.methods.formula_comparator", "FormulaComparison"),
    "FormulaComparator": ("src.semantic_modeling.methods.formula_comparator", "FormulaComparator"),
    "PharmacologicalData": ("src.semantic_modeling.methods.pharmacology", "PharmacologicalData"),
    "ModernPharmacologyDatabase": ("src.semantic_modeling.methods.pharmacology", "ModernPharmacologyDatabase"),
    "NetworkPharmacologySystemBiologyAnalyzer": ("src.semantic_modeling.methods.network_pharmacology", "NetworkPharmacologySystemBiologyAnalyzer"),
    "SupramolecularPhysicochemicalAnalyzer": ("src.semantic_modeling.methods.supramolecular", "SupramolecularPhysicochemicalAnalyzer"),
    "ClassicalLiteratureArchaeologyAnalyzer": ("src.semantic_modeling.methods.classical_literature", "ClassicalLiteratureArchaeologyAnalyzer"),
    "ComplexityNonlinearDynamicsAnalyzer": ("src.semantic_modeling.methods.complexity_science", "ComplexityNonlinearDynamicsAnalyzer"),
    "IntegratedResearchAnalyzer": ("src.semantic_modeling.methods.integrated_analyzer", "IntegratedResearchAnalyzer"),
    "ResearchScoringPanel": ("src.semantic_modeling.methods.scoring_panel", "ResearchScoringPanel"),
    "SummaryAnalysisEngine": ("src.semantic_modeling.methods.summary_engine", "SummaryAnalysisEngine"),
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
