"""方剂结构与药性归经分析。"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from src.data.knowledge_base import load_formula_structures, load_herb_properties


class FormulaDosageForm(Enum):
    """方剂剂型。"""

    DECOCTION = "decoction"
    PILL = "pill"
    POWDER = "powder"
    PASTE = "paste"
    TINCTURE = "tincture"
    EXTRACT = "extract"
    TABLET = "tablet"
    CAPSULE = "capsule"
    INJECTION = "injection"
    LINIMENT = "liniment"


@dataclass
class HerbDosage:
    """药物用量信息。"""

    herb_name: str
    amount: float
    unit: str
    dosage_form: str = "powder"
    role_in_formula: str = "common"


@dataclass
class FormulaStructure:
    """方剂结构数据类。"""

    formula_name: str
    dosage_form: FormulaDosageForm
    sovereign_herbs: List[HerbDosage]
    minister_herbs: List[HerbDosage]
    assistant_herbs: List[HerbDosage]
    envoy_herbs: List[HerbDosage]
    total_herbs: int = 0
    total_dosage: float = 0.0
    dose_ratio: Optional[Dict[str, float]] = None
    pairing_rules: Optional[List[str]] = None


@dataclass
class FormulaComposition:
    """方剂成分数据类。"""

    formula_name: str
    active_compounds: Dict[str, List[str]]
    medicinal_parts: Dict[str, str]
    compatibility_analysis: str


class FormulaStructureAnalyzer:
    """方剂结构分析器。"""

    FORMULA_STRUCTURES: Dict[str, Dict] = load_formula_structures()

    @classmethod
    def analyze_formula_structure(cls, formula_name: str) -> Dict:
        structure = cls.FORMULA_STRUCTURES.get(formula_name, {})
        if not structure:
            return {}

        sovereign_ratio = sum(h.get("ratio", 0) for h in structure.get("sovereign", []))
        minister_ratio = sum(h.get("ratio", 0) for h in structure.get("minister", []))
        assistant_ratio = sum(h.get("ratio", 0) for h in structure.get("assistant", []))
        envoy_ratio = sum(h.get("ratio", 0) for h in structure.get("envoy", []))

        return {
            "formula_name": formula_name,
            "dosage_form": structure.get("dosage_form"),
            "total_dosage": structure.get("total_dosage"),
            "herb_count": (
                len(structure.get("sovereign", []))
                + len(structure.get("minister", []))
                + len(structure.get("assistant", []))
                + len(structure.get("envoy", []))
            ),
            "role_distribution": {
                "sovereign_ratio": sovereign_ratio,
                "minister_ratio": minister_ratio,
                "assistant_ratio": assistant_ratio,
                "envoy_ratio": envoy_ratio,
            },
            "characteristics": structure.get("characteristics"),
            "pairing_rules": structure.get("pairing_rules", []),
        }

    @classmethod
    def get_formula_composition(cls, formula_name: str) -> Dict:
        structure = cls.FORMULA_STRUCTURES.get(formula_name, {})
        if not structure:
            return {}

        composition = {}
        for role in ["sovereign", "minister", "assistant", "envoy"]:
            herbs = structure.get(role, [])
            composition[role] = [h.get("name") for h in herbs]
        return composition


class HerbTemperature(Enum):
    """四气。"""

    HOT = "hot"
    WARM = "warm"
    NEUTRAL = "neutral"
    COOL = "cool"
    COLD = "cold"


class MeridianType(Enum):
    """十二正经。"""

    LIVER = "liver"
    HEART = "heart"
    SPLEEN = "spleen"
    LUNG = "lung"
    KIDNEY = "kidney"
    PERICARDIUM = "pericardium"
    GALLBLADDER = "gallbladder"
    SMALL_INTESTINE = "si"
    LARGE_INTESTINE = "li"
    STOMACH = "stomach"
    BLADDER = "bladder"
    TRIPLE_BURNER = "triple_burner"


@dataclass
class HerbProperty:
    """药物性味与归经。"""

    herb_name: str
    temperature: HerbTemperature
    flavors: List[str]
    meridians: List[MeridianType]
    primary_efficacy: str
    secondary_efficacy: List[str]
    toxicity_level: str = "low"
    contraindications: Optional[List[str]] = None


class HerbPropertyDatabase:
    """药物性味归经数据库。"""

    HERB_PROPERTIES: Dict[str, Dict] = load_herb_properties()

    @classmethod
    def get_herb_property(cls, herb_name: str) -> Dict:
        return cls.HERB_PROPERTIES.get(herb_name, {})

    @classmethod
    def get_herbs_by_meridian(cls, meridian: str) -> List[str]:
        herbs = []
        for herb_name, props in cls.HERB_PROPERTIES.items():
            if meridian in props.get("meridians", []):
                herbs.append(herb_name)
        return herbs

    @classmethod
    def get_herbs_by_temperature(cls, temperature: str) -> List[str]:
        herbs = []
        for herb_name, props in cls.HERB_PROPERTIES.items():
            if props.get("temperature") == temperature:
                herbs.append(herb_name)
        return herbs
