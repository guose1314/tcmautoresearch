"""方剂结构分析 - Formula Structure Analysis"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class FormulaDosageForm(Enum):
    """方剂剂型"""
    DECOCTION = "decoction"           # 汤剂
    PILL = "pill"                     # 丸剂
    POWDER = "powder"                 # 散剂
    PASTE = "paste"                   # 膏剂
    TINCTURE = "tincture"             # 酒剂
    EXTRACT = "extract"               # 浓缩物
    TABLET = "tablet"                 # 片剂
    CAPSULE = "capsule"               # 胶囊
    INJECTION = "injection"           # 注射液
    LINIMENT = "liniment"             # 搽剂


@dataclass
class HerbDosage:
    """药物用量信息"""
    herb_name: str
    amount: float                     # 用量数值
    unit: str                         # 单位（克、两等）
    dosage_form: str = "powder"       # 炮制形式
    role_in_formula: str = "common"  # 在方剂中的角色


@dataclass
class FormulaStructure:
    """方剂结构数据类"""
    formula_name: str                 # 方剂名称
    dosage_form: FormulaDosageForm    # 剂型
    
    # 组成比例 (君臣佐使 + 用量)
    sovereign_herbs: List[HerbDosage]     # 君药 
    minister_herbs: List[HerbDosage]      # 臣药
    assistant_herbs: List[HerbDosage]     # 佐药
    envoy_herbs: List[HerbDosage]         # 使药
    
    # 结构特征
    total_herbs: int = 0              # 中药味数
    total_dosage: float = 0.0         # 总用量（克）
    dose_ratio: Dict[str, float] = None  # 各角色用量比例
    
    # 配伍规律
    pairing_rules: List[str] = None   # 配伍规律说明


@dataclass
class FormulaComposition:
    """方剂成分数据类"""
    formula_name: str
    active_compounds: Dict[str, List[str]]  # {化学成分: [来源药物]}
    medicinal_parts: Dict[str, str]         # {药物: 药用部位}
    compatibility_analysis: str             # 配伍分析


class FormulaStructureAnalyzer:
    """方剂结构分析器"""
    
    # 预定义的方剂结构
    FORMULA_STRUCTURES: Dict[str, Dict] = {
        "补中益气汤": {
            "dosage_form": "decoction",
            "sovereign": [
                {"name": "黄芪", "amount": 15, "unit": "g", "ratio": 0.30},
            ],
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
                "甘草调和诸药"
            ]
        },
        "四君子汤": {
            "dosage_form": "decoction",
            "sovereign": [
                {"name": "人参", "amount": 10, "unit": "g", "ratio": 0.25},
            ],
            "minister": [
                {"name": "白术", "amount": 10, "unit": "g", "ratio": 0.25},
            ],
            "assistant": [
                {"name": "茯苓", "amount": 10, "unit": "g", "ratio": 0.25},
            ],
            "envoy": [
                {"name": "甘草", "amount": 10, "unit": "g", "ratio": 0.25},
            ],
            "total_dosage": 40,
            "characteristics": "脾胃气虚的基础方，比例均等对称",
            "pairing_rules": [
                "人参补气健脾",
                "白术健脾燥湿",
                "茯苓利水健脾",
                "甘草调和诸药"
            ]
        }
    }
    
    @classmethod
    def analyze_formula_structure(cls, formula_name: str) -> Dict:
        """分析方剂结构"""
        structure = cls.FORMULA_STRUCTURES.get(formula_name, {})
        if not structure:
            return {}
        
        # 计算比例分布
        sovereign_ratio = sum(h.get("ratio", 0) for h in structure.get("sovereign", []))
        minister_ratio = sum(h.get("ratio", 0) for h in structure.get("minister", []))
        assistant_ratio = sum(h.get("ratio", 0) for h in structure.get("assistant", []))
        envoy_ratio = sum(h.get("ratio", 0) for h in structure.get("envoy", []))
        
        return {
            "formula_name": formula_name,
            "dosage_form": structure.get("dosage_form"),
            "total_dosage": structure.get("total_dosage"),
            "herb_count": (len(structure.get("sovereign", [])) + 
                          len(structure.get("minister", [])) + 
                          len(structure.get("assistant", [])) + 
                          len(structure.get("envoy", []))),
            "role_distribution": {
                "sovereign_ratio": sovereign_ratio,
                "minister_ratio": minister_ratio,
                "assistant_ratio": assistant_ratio,
                "envoy_ratio": envoy_ratio
            },
            "characteristics": structure.get("characteristics"),
            "pairing_rules": structure.get("pairing_rules", [])
        }
    
    @classmethod
    def get_formula_composition(cls, formula_name: str) -> Dict:
        """获取方剂的详细组成"""
        structure = cls.FORMULA_STRUCTURES.get(formula_name, {})
        if not structure:
            return {}
        
        composition = {}
        for role in ["sovereign", "minister", "assistant", "envoy"]:
            herbs = structure.get(role, [])
            composition[role] = [h.get("name") for h in herbs]
        
        return composition
