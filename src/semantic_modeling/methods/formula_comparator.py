"""类方比较 - Similar Formulas Comparison"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class FormulaComparison:
    """方剂对比数据类"""
    formula1: str
    formula2: str
    
    # 共同特性
    common_herbs: List[str]           # 共同药物
    common_efficacy: List[str]        # 共同功效
    
    # 差异
    unique_herbs_f1: List[str]        # 方剂1特有药物
    unique_herbs_f2: List[str]        # 方剂2特有药物
    efficacy_difference: str          # 功效差异说明
    
    # 应用指导
    clinical_selection: str           # 临床选择指导


class FormulaComparator:
    """方剂对比分析器"""
    
    # 预定义的类方关系
    FORMULA_FAMILIES: Dict[str, List[str]] = {
        "补气方剂": ["补中益气汤", "四君子汤", "六君子汤"],
        "活血化瘀方": ["血府逐瘀汤", "膈下逐瘀汤", "身痛逐瘀汤"],
        "温阳方剂": ["四逆汤", "真武汤", "阳和汤"],
    }
    
    FORMULA_RELATIONSHIPS: Dict[Tuple[str, str], Dict] = {
        ("补中益气汤", "四君子汤"): {
            "common": ["人参", "白术", "甘草"],
            "difference": "补中益气汤添加了黄芪（升阳）和升麻/柴胡（升陷）",
            "selection": "补气虚伴乏力选补中益气汤；单纯脾胃虚弱选四君子汤"
        },
        ("四君子汤", "六君子汤"): {
            "common": ["人参", "白术", "茯苓", "甘草"],
            "difference": "六君子汤添加了半夏（燥湿）和陈皮（理气）",
            "selection": "脾虚健运不足伴湿困选六君子汤；脾虚气虚选四君子汤"
        }
    }
    
    @classmethod
    def compare_formulas(cls, formula1: str, formula2: str) -> Dict:
        """对比两个方剂"""
        relationship = cls.FORMULA_RELATIONSHIPS.get((formula1, formula2)) or \
                      cls.FORMULA_RELATIONSHIPS.get((formula2, formula1))
        
        if relationship:
            return {
                "formula1": formula1,
                "formula2": formula2,
                "common_herbs": relationship.get("common", []),
                "difference": relationship.get("difference", ""),
                "clinical_selection": relationship.get("selection", "")
            }
        return {}
    
    @classmethod
    def get_formula_family(cls, category: str) -> List[str]:
        """获取方剂族群"""
        return cls.FORMULA_FAMILIES.get(category, [])
    
    @classmethod
    def find_similar_formulas(cls, formula_name: str) -> List[Tuple[str, Dict]]:
        """查找相似方剂"""
        similar = []
        for (f1, f2), rel_data in cls.FORMULA_RELATIONSHIPS.items():
            if f1 == formula_name:
                similar.append((f2, rel_data))
            elif f2 == formula_name:
                similar.append((f1, rel_data))
        return similar
