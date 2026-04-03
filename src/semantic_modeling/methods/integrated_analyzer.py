"""集成研究分析器 - Integrated Research Analyzer"""

import copy
from typing import Any, Dict, List, Tuple

from .formula_structure import FormulaStructureAnalyzer
from .herb_properties import HerbPropertyDatabase
from .formula_comparator import FormulaComparator
from .pharmacology import ModernPharmacologyDatabase
from .network_pharmacology import NetworkPharmacologySystemBiologyAnalyzer
from .supramolecular import SupramolecularPhysicochemicalAnalyzer
from .classical_literature import ClassicalLiteratureArchaeologyAnalyzer
from .complexity_science import ComplexityNonlinearDynamicsAnalyzer


class IntegratedResearchAnalyzer:
    """集成研究分析器 - 多维度研究切入点"""

    _perspective_cache: Dict[str, Dict[str, Any]] = {}
    _component_properties_cache: Dict[str, Dict[str, Any]] = {}
    _similar_formulas_cache: Dict[str, List[str]] = {}
    _pharmacology_profile_cache: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    _network_cache: Dict[Tuple[str, Tuple[str, ...]], Dict[str, Any]] = {}
    _supramolecular_cache: Dict[Tuple[str, Tuple[str, ...]], Dict[str, Any]] = {}
    _knowledge_archaeology_cache: Dict[Tuple[str, Tuple[str, ...]], Dict[str, Any]] = {}
    _complexity_cache: Dict[Tuple[str, Tuple[str, ...]], Dict[str, Any]] = {}

    @classmethod
    def generate_research_perspective(cls, formula_name: str) -> Dict:
        """生成综合研究视角"""
        cached = cls._perspective_cache.get(formula_name)
        if cached is not None:
            return copy.deepcopy(cached)

        structure = FormulaStructureAnalyzer.analyze_formula_structure(formula_name)
        component_properties = cls._get_component_properties(formula_name)
        herbs = tuple(sorted(component_properties.keys()))

        analysis = {
            "formula_name": formula_name,
            "structure_analysis": structure,
            "component_properties": component_properties,
            "similar_formulas": cls._get_similar_formulas(formula_name),
            "pharmacological_profile": cls._get_pharmacological_profile(herbs),
            "network_pharmacology": cls._get_network_pharmacology(formula_name, herbs),
            "supramolecular_physicochemical": cls._get_supramolecular_physicochemical(formula_name, herbs),
            "knowledge_archaeology": cls._get_knowledge_archaeology(formula_name, herbs),
            "complexity_dynamics": cls._get_complexity_dynamics(formula_name, herbs),
        }

        cls._perspective_cache[formula_name] = copy.deepcopy(analysis)
        return analysis

    @classmethod
    def _get_component_properties(cls, formula_name: str) -> Dict[str, Any]:
        cached = cls._component_properties_cache.get(formula_name)
        if cached is not None:
            return copy.deepcopy(cached)

        properties: Dict[str, Any] = {}
        composition = FormulaStructureAnalyzer.get_formula_composition(formula_name)
        for herbs in composition.values():
            for herb in herbs:
                if herb not in properties:
                    properties[herb] = HerbPropertyDatabase.get_herb_property(herb)

        cls._component_properties_cache[formula_name] = copy.deepcopy(properties)
        return properties

    @classmethod
    def _get_similar_formulas(cls, formula_name: str) -> List[str]:
        cached = cls._similar_formulas_cache.get(formula_name)
        if cached is not None:
            return list(cached)

        similar: List[str] = []
        for formulas in FormulaComparator.FORMULA_FAMILIES.values():
            if formula_name in formulas:
                similar = [f for f in formulas if f != formula_name]
                break

        cls._similar_formulas_cache[formula_name] = list(similar)
        return similar

    @classmethod
    def _get_pharmacological_profile(cls, herbs: Tuple[str, ...]) -> Dict[str, Any]:
        cached = cls._pharmacology_profile_cache.get(herbs)
        if cached is not None:
            return copy.deepcopy(cached)

        profile: Dict[str, Any] = {}
        for herb in herbs:
            profile[herb] = {
                "components": ModernPharmacologyDatabase.get_active_components(herb),
                "efficacy": ModernPharmacologyDatabase.get_clinical_efficacy(herb),
                "safety": ModernPharmacologyDatabase.get_safety_info(herb),
            }

        cls._pharmacology_profile_cache[herbs] = copy.deepcopy(profile)
        return profile

    @classmethod
    def _get_network_pharmacology(cls, formula_name: str, herbs: Tuple[str, ...]) -> Dict[str, Any]:
        key = (formula_name, herbs)
        cached = cls._network_cache.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        value = NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network(formula_name, list(herbs))
        cls._network_cache[key] = copy.deepcopy(value)
        return value

    @classmethod
    def _get_supramolecular_physicochemical(cls, formula_name: str, herbs: Tuple[str, ...]) -> Dict[str, Any]:
        key = (formula_name, herbs)
        cached = cls._supramolecular_cache.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        value = SupramolecularPhysicochemicalAnalyzer.analyze_formula_physicochemical(formula_name, list(herbs))
        cls._supramolecular_cache[key] = copy.deepcopy(value)
        return value

    @classmethod
    def _get_knowledge_archaeology(cls, formula_name: str, herbs: Tuple[str, ...]) -> Dict[str, Any]:
        key = (formula_name, herbs)
        cached = cls._knowledge_archaeology_cache.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        value = ClassicalLiteratureArchaeologyAnalyzer.analyze_formula_knowledge_archaeology(formula_name, list(herbs))
        cls._knowledge_archaeology_cache[key] = copy.deepcopy(value)
        return value

    @classmethod
    def _get_complexity_dynamics(cls, formula_name: str, herbs: Tuple[str, ...]) -> Dict[str, Any]:
        key = (formula_name, herbs)
        cached = cls._complexity_cache.get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        value = ComplexityNonlinearDynamicsAnalyzer.analyze_formula_complexity_dynamics(formula_name, list(herbs))
        cls._complexity_cache[key] = copy.deepcopy(value)
        return value
