"""
TCM 语义关系定义模块 - 君臣佐使及其他中医关系类型
基于T/C IATCM 098-2023标准
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Set, Tuple


class RelationshipType(Enum):
    """中医语义关系类型"""
    # 方剂组成关系
    SOVEREIGN = "sovereign"      # 君药 - 主药，治疗主要症状
    MINISTER = "minister"        # 臣药 - 协助君药治疗次要症状
    ASSISTANT = "assistant"      # 佐药 - 增强效果或制约副作用
    ENVOY = "envoy"             # 使药 - 调和诸药或引药归经
    
    # 功效关系
    EFFICACY = "efficacy"       # 功效 - 中药/方剂的主要功效
    TREATS = "treats"           # 治疗 - 治疗特定证候
    AUGMENTS = "augments"       # 增强 - 增强效果
    COUNTERS = "counters"       # 制约 - 制约毒性或副作用
    
    # 症候关系
    SYMPTOM_OF = "symptom_of"   # 属于 - 症状属于证候
    CAUSE_OF = "cause_of"       # 导致 - 导致某症候
    
    # 经络穴位关系
    ENTERS = "enters"           # 归经 - 进入某经络
    REACHES = "reaches"         # 到达 - 到达某穴位
    
    # 属性关系
    HAS_PROPERTY = "has_property" # 具有 - 具有某种性质（四气五味等）
    COMBINES_WITH = "combines_with" # 相合 - 与其他药物相合


@dataclass
class RelationshipDefinition:
    """关系定义数据类"""
    rel_type: RelationshipType
    source_type: str            # 源实体类型（herb, formula, syndrome等）
    target_type: str            # 目标实体类型
    description: str            # 关系描述
    confidence_base: float      # 基础置信度
    bidirectional: bool = False # 是否双向


class TCMRelationshipDefinitions:
    """TCM 关系定义库"""
    
    # 预定义的方剂君臣佐使组成
    FORMULA_COMPOSITIONS: Dict[str, Dict[str, List[str]]] = {
        # 四君子汤: 人参(君) + 白术(臣) + 茯苓(佐) + 炙甘草(使)
        "四君子汤": {
            "sovereign": ["人参", "党参", "黄芪"],
            "minister": ["白术", "山药"],
            "assistant": ["茯苓", "薏米"],
            "envoy": ["甘草", "炙甘草"],
        },
        # 补中益气汤: 黄芪(君) + 人参(臣) + 白术等(佐) + 甘草(使)
        "补中益气汤": {
            "sovereign": ["黄芪"],
            "minister": ["人参", "党参"],
            "assistant": ["白术", "升麻", "柴胡"],
            "envoy": ["甘草", "大枣"],
        },
        # 六味地黄丸: 熟地黄(君) + 山茱萸等(臣) + 泽泻等(佐) + 甘草(使)
        "六味地黄丸": {
            "sovereign": ["熟地黄", "地黄"],
            "minister": ["山茱萸", "牡丹皮"],
            "assistant": ["泽泻", "茯苓"],
            "envoy": ["甘草"],
        },
        # 小柴胡汤: 柴胡(君) + 黄芩(臣) + 人参等(佐) + 炙甘草(使)
        "小柴胡汤": {
            "sovereign": ["柴胡"],
            "minister": ["黄芩"],
            "assistant": ["人参", "半夏", "生姜"],
            "envoy": ["甘草", "大枣"],
        },
        # 活血化瘀方: 丹参(君) + 赤芍(臣) + 川芎等(佐) + 甘草(使)
        "活血化瘀方": {
            "sovereign": ["丹参", "红花"],
            "minister": ["赤芍", "丹皮"],
            "assistant": ["川芎", "桃仁", "三棱", "莪术"],
            "envoy": ["甘草", "生姜"],
        },
    }
    
    # 中药功效属性映射
    HERB_EFFICACY_MAP: Dict[str, List[str]] = {
        "人参": ["补气", "健脾", "生津"],
        "黄芪": ["补气", "固表", "利水"],
        "党参": ["补气", "健脾", "生津"],
        "白术": ["健脾", "燥湿", "补气"],
        "茯苓": ["健脾", "利水", "安神"],
        "甘草": ["补气", "健脾", "解毒"],
        "当归": ["补血", "活血", "调经"],
        "黄芩": ["清热", "燥湿", "安胎"],
        "柴胡": ["疏肝", "解郁", "升阳"],
        "丹参": ["活血", "祛瘀", "安神"],
        "赤芍": ["活血", "祛瘀", "清热"],
        "川芎": ["活血", "行气", "止痛"],
        "熟地黄": ["补血", "滋阴", "养心"],
        "红花": ["活血", "祛瘀", "止痛"],
    }
    
    # 中药四气五味属性
    HERB_PROPERTIES: Dict[str, Dict[str, str]] = {
        "人参": {"气": "温", "味": "甘、微苦"},
        "黄芪": {"气": "微温", "味": "甘"},
        "白术": {"气": "温", "味": "甘、苦"},
        "甘草": {"气": "平", "味": "甘"},
        "黄芩": {"气": "寒", "味": "苦"},
        "柴胡": {"气": "凉", "味": "苦、辛"},
        "丹参": {"气": "微温", "味": "苦"},
    }

    # 证候定义与典型症状
    SYNDROME_DEFINITIONS: Dict[str, Dict[str, Any]] = {
        "气虚证": {
            "definition": "元气不足，脏腑功能减退",
            "symptoms": ["少气懒言", "神疲乏力", "自汗", "舌淡", "脉虚弱"],
            "pathogenesis": "劳倦内伤、久病耗损、年老体弱致气之化源不足",
        },
        "血虚证": {
            "definition": "血液亏虚，脏腑百脉失养",
            "symptoms": ["面色淡白或萎黄", "唇舌色淡", "头晕眼花", "心悸", "脉细"],
            "pathogenesis": "失血过多或生血不足，血液亏少",
        },
        "阴虚证": {
            "definition": "阴液不足，虚热内生",
            "symptoms": ["潮热盗汗", "五心烦热", "口燥咽干", "舌红少苔", "脉细数"],
            "pathogenesis": "热病伤阴或久病耗损阴液",
        },
        "阳虚证": {
            "definition": "阳气不足，温煦失职",
            "symptoms": ["畏寒肢冷", "面色苍白", "神疲蜷卧", "舌淡胖", "脉沉迟无力"],
            "pathogenesis": "久病伤阳或年老阳衰",
        },
        "痰湿证": {
            "definition": "水湿痰饮停聚体内",
            "symptoms": ["肢体困重", "脘腹胀满", "恶心", "苔腻", "脉滑"],
            "pathogenesis": "脾失健运或外湿侵袭致水液运化失常",
        },
        "血瘀证": {
            "definition": "血液瘀滞不畅",
            "symptoms": ["刺痛拒按", "痛处固定", "面色晦暗", "舌紫暗或有瘀斑", "脉涩"],
            "pathogenesis": "气滞、外伤、寒凝或热灼致血行不畅",
        },
        "湿热证": {
            "definition": "湿与热互结蕴蒸",
            "symptoms": ["身热不扬", "脘痞呕恶", "口苦口黏", "苔黄腻", "脉濡数"],
            "pathogenesis": "外感湿热或脾胃运化失常，湿热内蕴",
        },
    }

    # 经典理论术语简释
    THEORY_TERM_DEFINITIONS: Dict[str, str] = {
        "君臣佐使": "方剂配伍的基本结构原则，君药治主症，臣药助君，佐药制约或兼治，使药调和引经",
        "四气五味": "药物的寒热温凉四气与辛甘酸苦咸五味，是中药药性理论的核心",
        "归经": "药物作用的靶向经络脏腑，指导临床用药定位",
        "七情配伍": "药物相互作用的七种关系：单行、相须、相使、相畏、相杀、相恶、相反",
        "辨证论治": "中医诊疗体系核心，通过四诊合参辨别证型，据证立法选方用药",
        "正邪": "正气为人体抗病能力，邪气为致病因素，发病取决于正邪斗争",
        "升降浮沉": "药物作用的趋向性，升浮药向上向外，沉降药向下向内",
        "表里": "八纲辨证之一，病位在表为表证（外感初期），在里为里证（脏腑病变）",
    }

    
    @classmethod
    def get_formula_composition(cls, formula_name: str) -> Dict[str, List[str]]:
        """
        获取方剂的君臣佐使组成
        
        Args:
            formula_name: 方剂名称
        
        Returns:
            包含 sovereign/minister/assistant/envoy 的字典
        """
        return cls.FORMULA_COMPOSITIONS.get(formula_name, {})
    
    @classmethod
    def get_herb_efficacy(cls, herb_name: str) -> List[str]:
        """
        获取中药功效
        
        Args:
            herb_name: 中药名称
        
        Returns:
            功效列表
        """
        return cls.HERB_EFFICACY_MAP.get(herb_name, [])
    
    @classmethod
    def get_herb_properties(cls, herb_name: str) -> Dict[str, str]:
        """
        获取中药四气五味属性
        
        Args:
            herb_name: 中药名称
        
        Returns:
            属性字典 {气: str, 味: str}
        """
        return cls.HERB_PROPERTIES.get(herb_name, {})

    @classmethod
    def get_syndrome_definition(cls, syndrome_name: str) -> Dict[str, Any]:
        """获取证候定义、典型症状与病机。"""
        return dict(cls.SYNDROME_DEFINITIONS.get(syndrome_name, {}))

    @classmethod
    def get_theory_term_definition(cls, term: str) -> str:
        """获取经典理论术语的简释文本。返回空字符串表示未收录。"""
        return cls.THEORY_TERM_DEFINITIONS.get(term, "")
    
    @classmethod
    def infer_relationship_type(
        cls,
        source_entity: Dict,
        target_entity: Dict,
        formula_name: str = None
    ) -> Tuple[RelationshipType, float]:
        """
        根据实体特征推断关系类型
        
        Args:
            source_entity: 源实体 {"name": str, "type": str, ...}
            target_entity: 目标实体 {"name": str, "type": str, ...}
            formula_name: 所属方剂名称（可选）
        
        Returns:
            (关系类型, 置信度) 元组
        """
        rel_type = RelationshipType.COMBINES_WITH
        confidence = 0.5
        
        source_name = source_entity.get("name", "")
        target_name = target_entity.get("name", "")
        source_type = source_entity.get("type", "")
        target_type = target_entity.get("type", "")
        
        # 【情形1】 方剂 → 药物 的君臣佐使关系
        if source_type == "formula" and target_type == "herb" and formula_name:
            composition = cls.get_formula_composition(formula_name or source_name)
            if composition:
                if target_name in composition.get("sovereign", []):
                    return RelationshipType.SOVEREIGN, 0.95
                elif target_name in composition.get("minister", []):
                    return RelationshipType.MINISTER, 0.95
                elif target_name in composition.get("assistant", []):
                    return RelationshipType.ASSISTANT, 0.95
                elif target_name in composition.get("envoy", []):
                    return RelationshipType.ENVOY, 0.95
        
        # 【情形2】 药物 → 功效 的关系
        if source_type == "herb" and target_type == "efficacy":
            efficacies = cls.get_herb_efficacy(source_name)
            if target_name in efficacies:
                return RelationshipType.EFFICACY, 0.9
        
        # 【情形3】 药物/方剂 → 证候 的治疗关系
        if target_type == "syndrome":
            if source_type == "herb":
                return RelationshipType.TREATS, 0.75
            elif source_type == "formula":
                return RelationshipType.TREATS, 0.85
        
        # 【情形4】 药物 → 经络 的归经关系
        if target_type == "theory" and "经" in target_name:
            if source_type == "herb":
                return RelationshipType.ENTERS, 0.70
        
        return rel_type, confidence
    
    @classmethod
    def get_all_relationship_types(cls) -> List[RelationshipType]:
        """获取所有关系类型"""
        return list(RelationshipType)
    
    @classmethod
    def get_relationship_description(cls, rel_type: RelationshipType) -> str:
        """获取关系类型的描述"""
        descriptions = {
            RelationshipType.SOVEREIGN: "君药 - 主药，治疗主要症状",
            RelationshipType.MINISTER: "臣药 - 协助君药治疗次要症状",
            RelationshipType.ASSISTANT: "佐药 - 增强效果或制约副作用",
            RelationshipType.ENVOY: "使药 - 调和诸药或引药归经",
            RelationshipType.EFFICACY: "功效 - 中药/方剂的主要功效",
            RelationshipType.TREATS: "治疗 - 治疗特定证候",
            RelationshipType.AUGMENTS: "增强 - 增强效果",
            RelationshipType.COUNTERS: "制约 - 制约毒性或副作用",
            RelationshipType.SYMPTOM_OF: "属于 - 症状属于证候",
            RelationshipType.CAUSE_OF: "导致 - 导致某症候",
            RelationshipType.ENTERS: "归经 - 进入某经络",
            RelationshipType.REACHES: "到达 - 到达某穴位",
            RelationshipType.HAS_PROPERTY: "具有 - 具有某种性质",
            RelationshipType.COMBINES_WITH: "相合 - 与其他药物相合",
        }
        return descriptions.get(rel_type, "未知关系")
