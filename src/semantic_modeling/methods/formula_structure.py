"""方剂结构与药性归经分析。"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


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

    FORMULA_STRUCTURES: Dict[str, Dict] = {
        "补中益气汤": {
            "dosage_form": "decoction",
            "sovereign": [{"name": "黄芪", "amount": 15, "unit": "g", "ratio": 0.30}],
            "minister": [
                {"name": "人参", "amount": 10, "unit": "g", "ratio": 0.20},
                {"name": "党参", "amount": 10, "unit": "g", "ratio": 0.20},
            ],
            "assistant": [
                {"name": "白术", "amount": 10, "unit": "g", "ratio": 0.15},
                {"name": "升麻", "amount": 6, "unit": "g", "ratio": 0.12},
                {"name": "柴胡", "amount": 6, "unit": "g", "ratio": 0.12},
            ],
            "envoy": [
                {"name": "甘草", "amount": 4, "unit": "g", "ratio": 0.08},
                {"name": "大枣", "amount": 3, "unit": "枚", "ratio": 0.03},
            ],
            "total_dosage": 50,
            "characteristics": "扶正培本，升阳益气",
            "pairing_rules": [
                "黄芪甘温，扶正气之主",
                "人参、白术健脾益气",
                "升麻、柴胡升阳举陷",
                "甘草调和诸药",
            ],
        },
        "四君子汤": {
            "dosage_form": "decoction",
            "sovereign": [{"name": "人参", "amount": 10, "unit": "g", "ratio": 0.25}],
            "minister": [{"name": "白术", "amount": 10, "unit": "g", "ratio": 0.25}],
            "assistant": [{"name": "茯苓", "amount": 10, "unit": "g", "ratio": 0.25}],
            "envoy": [{"name": "甘草", "amount": 10, "unit": "g", "ratio": 0.25}],
            "total_dosage": 40,
            "characteristics": "脾胃气虚的基础方，比例均等对称",
            "pairing_rules": ["人参补气健脾", "白术健脾燥湿", "茯苓利水健脾", "甘草调和诸药"],
        },
    }

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

    HERB_PROPERTIES: Dict[str, Dict] = {
        "黄芪": {
            "temperature": "warm",
            "flavors": ["甘"],
            "meridians": ["lung", "spleen"],
            "primary_efficacy": "补气、固表",
            "secondary_efficacy": ["利水", "消肿", "增强免疫"],
            "toxicity": "low",
            "dosage": "15-30g",
        },
        "人参": {
            "temperature": "warm",
            "flavors": ["甘", "微苦"],
            "meridians": ["spleen", "lung", "heart"],
            "primary_efficacy": "补气、健脾、生津",
            "secondary_efficacy": ["安神", "增强体质"],
            "toxicity": "low",
            "dosage": "10-15g",
        },
        "白术": {
            "temperature": "warm",
            "flavors": ["甘", "苦"],
            "meridians": ["spleen", "stomach"],
            "primary_efficacy": "健脾、燥湿、补气",
            "secondary_efficacy": ["安胎", "止汗"],
            "toxicity": "low",
            "dosage": "10-15g",
        },
        "茯苓": {
            "temperature": "neutral",
            "flavors": ["甘", "淡"],
            "meridians": ["heart", "spleen", "kidney"],
            "primary_efficacy": "利水、健脾、安神",
            "secondary_efficacy": ["消肿", "增强免疫"],
            "toxicity": "low",
            "dosage": "10-30g",
        },
        "甘草": {
            "temperature": "neutral",
            "flavors": ["甘"],
            "meridians": ["all"],
            "primary_efficacy": "补气、健脾、解毒、调和诸药",
            "secondary_efficacy": ["缓急止痛", "增强其他药物效果"],
            "toxicity": "low",
            "dosage": "3-10g",
            "note": "使药的代表，常用于调和",
        },
        "丹参": {
            "temperature": "cool",
            "flavors": ["苦"],
            "meridians": ["heart", "pericardium", "liver"],
            "primary_efficacy": "活血、祛瘀、安神",
            "secondary_efficacy": ["cool_blood", "relieve_pain"],
            "toxicity": "low",
            "dosage": "10-15g",
        },
    }

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
