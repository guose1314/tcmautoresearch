"""
高级研究方法模块 - 多维度研究方法切入点
包含：方剂结构、性味归经、类方比较、现代药理学、网络药理学、
超分子化学与物理化学、古典文献知识考古、复杂性非线性动力学
"""

import copy
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple

import networkx as nx
import numpy as np

# ============================================================================
# 1. 方剂结构分析 - Formula Structure Analysis
# ============================================================================

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


# ============================================================================
# 2. 药物性味与归经 - Herb Properties and Meridian Entry
# ============================================================================

class HerbTemperature(Enum):
    """四气（温度性质）"""
    HOT = "hot"           # 热
    WARM = "warm"         # 温
    NEUTRAL = "neutral"   # 平
    COOL = "cool"         # 凉
    COLD = "cold"         # 寒


class MeridianType(Enum):
    """十二正经"""
    LIVER = "liver"               # 肝经
    HEART = "heart"               # 心经
    SPLEEN = "spleen"             # 脾经
    LUNG = "lung"                 # 肺经
    KIDNEY = "kidney"             # 肾经
    PERICARDIUM = "pericardium"   # 心包经
    GALLBLADDER = "gallbladder"   # 胆经
    SMALL_INTESTINE = "si"        # 小肠经
    LARGE_INTESTINE = "li"        # 大肠经
    STOMACH = "stomach"           # 胃经
    BLADDER = "bladder"           # 膀胱经
    TRIPLE_BURNER = "triple_burner"  # 三焦经


@dataclass
class HerbProperty:
    """药物性味与归经"""
    herb_name: str
    
    # 四气五味
    temperature: HerbTemperature      # 四气
    flavors: List[str]               # 五味（酸苦甘辛咸）
    
    # 归经
    meridians: List[MeridianType]     # 归经
    
    # 功效分类
    primary_efficacy: str             # 主要功效
    secondary_efficacy: List[str]     # 次要功效
    
    # 药理特性
    toxicity_level: str = "low"       # 毒性等级 (low/moderate/high)
    contraindications: List[str] = None  # 禁忌症


class HerbPropertyDatabase:
    """药物性味归经数据库"""
    
    HERB_PROPERTIES: Dict[str, Dict] = {
        "黄芪": {
            "temperature": "warm",
            "flavors": ["甘"],
            "meridians": ["lung", "spleen"],
            "primary_efficacy": "补气、固表",
            "secondary_efficacy": ["利水", "消肿", "增强免疫"],
            "toxicity": "low",
            "dosage": "15-30g"
        },
        "人参": {
            "temperature": "warm",
            "flavors": ["甘", "微苦"],
            "meridians": ["spleen", "lung", "heart"],
            "primary_efficacy": "补气、健脾、生津",
            "secondary_efficacy": ["安神", "增强体质"],
            "toxicity": "low",
            "dosage": "10-15g"
        },
        "白术": {
            "temperature": "warm",
            "flavors": ["甘", "苦"],
            "meridians": ["spleen", "stomach"],
            "primary_efficacy": "健脾、燥湿、补气",
            "secondary_efficacy": ["安胎", "止汗"],
            "toxicity": "low",
            "dosage": "10-15g"
        },
        "茯苓": {
            "temperature": "neutral",
            "flavors": ["甘", "淡"],
            "meridians": ["heart", "spleen", "kidney"],
            "primary_efficacy": "利水、健脾、安神",
            "secondary_efficacy": ["消肿", "增强免疫"],
            "toxicity": "low",
            "dosage": "10-30g"
        },
        "甘草": {
            "temperature": "neutral",
            "flavors": ["甘"],
            "meridians": ["all"],  # 归所有经络
            "primary_efficacy": "补气、健脾、解毒、调和诸药",
            "secondary_efficacy": ["缓急止痛", "增强其他药物效果"],
            "toxicity": "low",
            "dosage": "3-10g",
            "note": "使药的代表，常用于调和"
        },
        "丹参": {
            "temperature": "cool",
            "flavors": ["苦"],
            "meridians": ["heart", "pericardium", "liver"],
            "primary_efficacy": "活血、祛瘀、安神",
            "secondary_efficacy": ["cool_blood", "relieve_pain"],
            "toxicity": "low",
            "dosage": "10-15g"
        }
    }
    
    @classmethod
    def get_herb_property(cls, herb_name: str) -> Dict:
        """获取药物性味归经"""
        return cls.HERB_PROPERTIES.get(herb_name, {})
    
    @classmethod
    def get_herbs_by_meridian(cls, meridian: str) -> List[str]:
        """按经络查询药物"""
        herbs = []
        for herb_name, props in cls.HERB_PROPERTIES.items():
            if meridian in props.get("meridians", []):
                herbs.append(herb_name)
        return herbs
    
    @classmethod
    def get_herbs_by_temperature(cls, temperature: str) -> List[str]:
        """按四气查询药物"""
        herbs = []
        for herb_name, props in cls.HERB_PROPERTIES.items():
            if props.get("temperature") == temperature:
                herbs.append(herb_name)
        return herbs


# ============================================================================
# 3. 类方比较 - Similar Formulas Comparison
# ============================================================================

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


# ============================================================================
# 4. 现代药理学与临床研究 - Modern Pharmacology & Clinical Research
# ============================================================================

@dataclass
class PharmacologicalData:
    """现代药理学数据"""
    herb_name: str
    
    # 化学成分
    active_components: Dict[str, str]  # {成分名: 含量描述}
    
    # 药理作用
    pharmacological_actions: List[str] # 体外\体内药理作用
    
    # 临床研究
    clinical_efficacy: Dict[str, float] # {适应症: 有效率}
    
    # 不良反应
    adverse_effects: List[str]          # 已知不良反应
    
    # 相互作用
    drug_interactions: List[str]        # 与现代药物的相互作用


class ModernPharmacologyDatabase:
    """现代药理学与临床数据库"""
    
    PHARMACOLOGY_DATA: Dict[str, Dict] = {
        "黄芪": {
            "active_components": {
                "黄芪多糖": "5-10%",
                "黄芪皂苷": "0.05-0.5%",
                "黄酮": "0.1-0.3%"
            },
            "pharmacological_actions": [
                "增强免疫功能（增加T/B淋巴细胞）",
                "抗疲劳作用",
                "抗肿瘤活性",
                "改善血循环",
                "保护心肌细胞"
            ],
            "clinical_research": {
                "反复呼吸道感染": 0.78,  # 有效率78%
                "慢性心衰": 0.65,
                "肾病综合征": 0.72,
                "糖尿病并发症": 0.68
            },
            "adverse_effects": ["长期大量使用可能引起腹胀"],
            "interactions": ["与某些免疫抑制剂协同作用"]
        },
        "人参": {
            "active_components": {
                "人参皂苷": "2-3%",
                "人参多糖": "6-8%",
                "挥发油": "0.01%"
            },
            "pharmacological_actions": [
                "中枢神经系统调节",
                "增强适应原样作用",
                "改善认知功能",
                "抗疲劳",
                "调节免疫"
            ],
            "clinical_research": {
                "疲劳综合征": 0.80,
                "认知功能下降": 0.73,
                "术后恢复": 0.76
            },
            "adverse_effects": ["过量可能引起兴奋、失眠"],
            "interactions": ["含有caffeine类物质"]
        },
        "丹参": {
            "active_components": {
                "丹酚酸": "6-8%",
                "丹参酮": "0.2-0.4%"
            },
            "pharmacological_actions": [
                "改善微循环",
                "抗血栓",
                "抗缺血",
                "抗氧化",
                "保护心肌"
            ],
            "clinical_research": {
                "冠心病": 0.71,
                "心肌梗死": 0.68,
                "脑卒中": 0.74
            },
            "adverse_effects": ["出血倾向增加（与抗凝血药协同）"],
            "interactions": ["与华法林等抗凝血药相互作用增强"]
        }
    }
    
    @classmethod
    def get_pharmacological_data(cls, herb_name: str) -> Dict:
        """获取药物现代药理学数据"""
        return cls.PHARMACOLOGY_DATA.get(herb_name, {})
    
    @classmethod
    def get_active_components(cls, herb_name: str) -> Dict:
        """获取有效成分"""
        data = cls.PHARMACOLOGY_DATA.get(herb_name, {})
        return data.get("active_components", {})
    
    @classmethod
    def get_clinical_efficacy(cls, herb_name: str) -> Dict:
        """获取临床疗效数据"""
        data = cls.PHARMACOLOGY_DATA.get(herb_name, {})
        return data.get("clinical_research", {})
    
    @classmethod
    def get_safety_info(cls, herb_name: str) -> Dict:
        """获取安全性信息"""
        data = cls.PHARMACOLOGY_DATA.get(herb_name, {})
        return {
            "adverse_effects": data.get("adverse_effects", []),
            "drug_interactions": data.get("interactions", [])
        }
    
    @classmethod
    def find_herbs_for_indication(cls, indication: str) -> List[Tuple[str, float]]:
        """根据临床适应症查询药物"""
        herbs_with_efficacy = []
        for herb_name, data in cls.PHARMACOLOGY_DATA.items():
            clinical_research = data.get("clinical_research", {})
            if indication in clinical_research:
                efficacy_rate = clinical_research[indication]
                herbs_with_efficacy.append((herb_name, efficacy_rate))
        
        # 按疗效率排序
        return sorted(herbs_with_efficacy, key=lambda x: x[1], reverse=True)


# ============================================================================
# 5. 综合研究视角 - Integrated Research Perspective
# ============================================================================

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


# ============================================================================
# 6. 网络药理学与系统性生物学 - Network Pharmacology & Systems Biology
# ============================================================================

class NetworkPharmacologySystemBiologyAnalyzer:
    """网络药理学与系统生物学分析器"""

    HERB_TARGET_MAP: Dict[str, List[str]] = {
        "黄芪": ["IL6", "TNF", "AKT1", "VEGFA"],
        "人参": ["AKT1", "MAPK1", "CASP3", "SIRT1"],
        "白术": ["IL1B", "PPARG", "STAT3"],
        "茯苓": ["HIF1A", "NFKB1", "JUN"],
        "甘草": ["PTGS2", "RELA", "TP53", "IL6"],
        "丹参": ["NOS3", "MMP9", "AKT1", "VEGFA"],
    }

    TARGET_PATHWAY_MAP: Dict[str, List[str]] = {
        "AKT1": ["PI3K-Akt", "Insulin signaling"],
        "IL6": ["JAK-STAT", "NF-kB signaling"],
        "TNF": ["TNF signaling", "NF-kB signaling"],
        "VEGFA": ["Angiogenesis", "HIF-1 signaling"],
        "MAPK1": ["MAPK signaling"],
        "PTGS2": ["Arachidonic acid metabolism"],
    }

    @classmethod
    def analyze_formula_network(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        """构建方剂-靶点-通路网络"""
        herb_target_edges: List[Dict[str, str]] = []
        target_counter: Dict[str, int] = {}
        pathways: Dict[str, int] = {}

        for herb in herbs:
            targets = cls.HERB_TARGET_MAP.get(herb, [])
            for target in targets:
                herb_target_edges.append({"herb": herb, "target": target})
                target_counter[target] = target_counter.get(target, 0) + 1
                for pathway in cls.TARGET_PATHWAY_MAP.get(target, []):
                    pathways[pathway] = pathways.get(pathway, 0) + 1

        key_targets = sorted(target_counter.items(), key=lambda x: x[1], reverse=True)[:8]
        enriched_pathways = sorted(pathways.items(), key=lambda x: x[1], reverse=True)[:8]

        return {
            "formula_name": formula_name,
            "herb_target_edges": herb_target_edges,
            "target_count": len(target_counter),
            "key_targets": [{"target": t, "degree": d} for t, d in key_targets],
            "enriched_pathways": [{"pathway": p, "score": s} for p, s in enriched_pathways],
            "systems_biology_hypothesis": "多成分-多靶点-多通路协同调控炎症与能量代谢网络",
        }


# ============================================================================
# 7. 超分子化学和物理化学 - Supramolecular Chemistry & Physicochemistry
# ============================================================================

class SupramolecularPhysicochemicalAnalyzer:
    """超分子化学与物理化学分析器"""

    HERB_PHYSICOCHEMISTRY: Dict[str, Dict[str, float]] = {
        "黄芪": {"solubility": 0.82, "h_bond": 0.74, "pi_stack": 0.21, "dispersion": 0.66},
        "人参": {"solubility": 0.78, "h_bond": 0.71, "pi_stack": 0.25, "dispersion": 0.64},
        "白术": {"solubility": 0.59, "h_bond": 0.46, "pi_stack": 0.42, "dispersion": 0.77},
        "茯苓": {"solubility": 0.73, "h_bond": 0.67, "pi_stack": 0.18, "dispersion": 0.62},
        "甘草": {"solubility": 0.76, "h_bond": 0.72, "pi_stack": 0.28, "dispersion": 0.69},
        "丹参": {"solubility": 0.52, "h_bond": 0.44, "pi_stack": 0.61, "dispersion": 0.81},
    }

    @classmethod
    def analyze_formula_physicochemical(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        """评估方剂在溶解性、非共价作用与协同稳定性方面的理化特征"""
        profiles = [cls.HERB_PHYSICOCHEMISTRY[h] for h in herbs if h in cls.HERB_PHYSICOCHEMISTRY]
        if not profiles:
            return {"formula_name": formula_name, "available": False}

        metrics = {
            "solubility_index": sum(p["solubility"] for p in profiles) / len(profiles),
            "h_bond_network": sum(p["h_bond"] for p in profiles) / len(profiles),
            "pi_stacking_potential": sum(p["pi_stack"] for p in profiles) / len(profiles),
            "dispersion_stability": sum(p["dispersion"] for p in profiles) / len(profiles),
        }

        supramolecular_synergy = (
            0.35 * metrics["solubility_index"]
            + 0.30 * metrics["h_bond_network"]
            + 0.20 * metrics["dispersion_stability"]
            + 0.15 * metrics["pi_stacking_potential"]
        )

        return {
            "formula_name": formula_name,
            "available": True,
            "metrics": metrics,
            "supramolecular_synergy_score": round(supramolecular_synergy, 4),
            "physicochemical_interpretation": "高氢键网络与中高溶解指数支持复方多组分协同释放",
        }


# ============================================================================
# 8. 古典文献的数字化与知识考古 - Classical Literature Digitization & Knowledge Archaeology
# ============================================================================

class ClassicalLiteratureArchaeologyAnalyzer:
    """古典文献数字化与知识考古分析器"""

    FORMULA_ARCHIVE: Dict[str, Dict[str, Any]] = {
        "补中益气汤": {
            "first_source": "脾胃论",
            "dynasty": "金元",
            "author": "李东垣",
            "variant_names": ["补中汤", "益气升阳汤"],
            "core_indications": ["中气下陷", "气虚发热", "体倦乏力"],
            "evolution_notes": [
                "明清时期强化升阳举陷用于久泻脱肛",
                "近现代扩展至免疫低下与术后康复场景",
            ],
        },
        "四君子汤": {
            "first_source": "太平惠民和剂局方",
            "dynasty": "宋",
            "author": "官修",
            "variant_names": ["四味健脾汤"],
            "core_indications": ["脾胃气虚", "纳呆便溏"],
            "evolution_notes": [
                "作为补气基础方衍生六君子汤、香砂六君子汤",
            ],
        },
    }

    @classmethod
    def analyze_formula_knowledge_archaeology(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        """输出方剂在古典文献中的源流、异名与知识演化信息"""
        archive = cls.FORMULA_ARCHIVE.get(formula_name, {})
        if not archive:
            return {
                "formula_name": formula_name,
                "available": False,
                "digitization_status": "待补充文献语料",
            }

        citation_nodes = [archive.get("first_source")] + archive.get("variant_names", [])
        citation_edges = [
            {"from": archive.get("first_source"), "to": variant, "type": "name_evolution"}
            for variant in archive.get("variant_names", [])
        ]

        return {
            "formula_name": formula_name,
            "available": True,
            "origin": {
                "source": archive.get("first_source"),
                "dynasty": archive.get("dynasty"),
                "author": archive.get("author"),
            },
            "indications": archive.get("core_indications", []),
            "evolution_notes": archive.get("evolution_notes", []),
            "knowledge_graph": {
                "nodes": citation_nodes,
                "edges": citation_edges,
            },
            "herb_mention_count": len(herbs),
        }


# ============================================================================
# 9. 复杂性科学与非线性动力学 - Complexity Science & Nonlinear Dynamics
# ============================================================================

class ComplexityNonlinearDynamicsAnalyzer:
    """复杂性科学与非线性动力学分析器"""

    FORMULA_DYNAMIC_PRIOR: Dict[str, Dict[str, float]] = {
        "补中益气汤": {"stability": 0.79, "adaptivity": 0.74, "feedback_gain": 0.63},
        "四君子汤": {"stability": 0.72, "adaptivity": 0.61, "feedback_gain": 0.52},
        "六君子汤": {"stability": 0.75, "adaptivity": 0.66, "feedback_gain": 0.57},
    }

    @classmethod
    def analyze_formula_complexity_dynamics(cls, formula_name: str, herbs: List[str]) -> Dict[str, Any]:
        """估计方剂系统的稳态恢复能力、非线性响应和协同复杂度"""
        prior = cls.FORMULA_DYNAMIC_PRIOR.get(
            formula_name,
            {"stability": 0.60, "adaptivity": 0.58, "feedback_gain": 0.50},
        )
        herb_factor = min(1.0, 0.08 * len(herbs))
        resilience_index = round(0.6 * prior["stability"] + 0.4 * herb_factor, 4)
        nonlinear_response = round(prior["adaptivity"] * (1 + 0.2 * prior["feedback_gain"]), 4)
        complexity_score = round((resilience_index + nonlinear_response + prior["feedback_gain"]) / 3, 4)

        regime = "稳定吸引子"
        if complexity_score >= 0.78:
            regime = "高鲁棒吸引子"
        elif complexity_score < 0.58:
            regime = "临界波动区"

        return {
            "formula_name": formula_name,
            "stability": prior["stability"],
            "adaptivity": prior["adaptivity"],
            "feedback_gain": prior["feedback_gain"],
            "resilience_index": resilience_index,
            "nonlinear_response": nonlinear_response,
            "complexity_score": complexity_score,
            "dynamic_regime": regime,
            "interpretation": "复方通过多节点反馈抑制波动并促进稳态恢复",
        }


# ============================================================================
# 10. 统一评分面板 - Unified Scoring Panel (8 Dimensions)
# ============================================================================

class ResearchScoringPanel:
    """将8个研究维度映射为0-1标准化评分并给出总分/置信区间"""

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "structure": 0.12,
        "properties": 0.12,
        "comparison": 0.10,
        "pharmacology": 0.14,
        "network": 0.14,
        "supramolecular": 0.12,
        "archaeology": 0.13,
        "complexity": 0.13,
    }

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @classmethod
    def _score_structure(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        herb_count = min(1.0, data.get("herb_count", 0) / 10.0)
        role = data.get("role_distribution", {})
        nonzero_roles = sum(1 for k in ["sovereign_ratio", "minister_ratio", "assistant_ratio", "envoy_ratio"] if role.get(k, 0) > 0)
        role_coverage = nonzero_roles / 4.0
        pairing = min(1.0, len(data.get("pairing_rules", [])) / 4.0)
        return cls._clamp01(0.45 * herb_count + 0.30 * role_coverage + 0.25 * pairing)

    @classmethod
    def _score_properties(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        n = len(data)
        if n == 0:
            return 0.0
        complete = 0
        for item in data.values():
            if item.get("temperature") and item.get("flavors") and item.get("meridians"):
                complete += 1
        return cls._clamp01(complete / n)

    @classmethod
    def _score_comparison(cls, data: List[Any], similar_formulas: List[str]) -> float:
        c1 = min(1.0, len(data or []) / 3.0)
        c2 = min(1.0, len(similar_formulas or []) / 3.0)
        return cls._clamp01(0.6 * c1 + 0.4 * c2)

    @classmethod
    def _score_pharmacology(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        herb_scores: List[float] = []
        for _, item in data.items():
            comp = min(1.0, len(item.get("components", {})) / 4.0)
            eff = min(1.0, len(item.get("efficacy", {})) / 4.0)
            safety = 1.0 if item.get("safety", {}).get("adverse_effects") is not None else 0.0
            herb_scores.append(0.45 * comp + 0.40 * eff + 0.15 * safety)
        return cls._clamp01(sum(herb_scores) / len(herb_scores)) if herb_scores else 0.0

    @classmethod
    def _score_network(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        target = min(1.0, data.get("target_count", 0) / 20.0)
        key_t = min(1.0, len(data.get("key_targets", [])) / 8.0)
        path = min(1.0, len(data.get("enriched_pathways", [])) / 8.0)
        return cls._clamp01(0.4 * target + 0.3 * key_t + 0.3 * path)

    @classmethod
    def _score_supramolecular(cls, data: Dict[str, Any]) -> float:
        if not data or not data.get("available"):
            return 0.0
        score = data.get("supramolecular_synergy_score", 0.0)
        return cls._clamp01(score)

    @classmethod
    def _score_archaeology(cls, data: Dict[str, Any]) -> float:
        if not data or not data.get("available"):
            return 0.0
        origin = 1.0 if data.get("origin", {}).get("source") else 0.0
        evo = min(1.0, len(data.get("evolution_notes", [])) / 3.0)
        nodes = min(1.0, len(data.get("knowledge_graph", {}).get("nodes", [])) / 4.0)
        return cls._clamp01(0.35 * origin + 0.35 * evo + 0.30 * nodes)

    @classmethod
    def _score_complexity(cls, data: Dict[str, Any]) -> float:
        if not data:
            return 0.0
        return cls._clamp01(data.get("complexity_score", 0.0))

    @classmethod
    def _ci95_from_dimension_scores(cls, scores: Dict[str, float]) -> Dict[str, float]:
        values = list(scores.values())
        n = len(values)
        if n == 0:
            return {"mean": 0.0, "lower": 0.0, "upper": 0.0, "margin": 0.0}
        mean = sum(values) / n
        if n == 1:
            return {"mean": round(mean, 4), "lower": round(mean, 4), "upper": round(mean, 4), "margin": 0.0}
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        se = (var ** 0.5) / (n ** 0.5)
        margin = 1.96 * se
        lower = cls._clamp01(mean - margin)
        upper = cls._clamp01(mean + margin)
        return {
            "mean": round(mean, 4),
            "lower": round(lower, 4),
            "upper": round(upper, 4),
            "margin": round(margin, 4),
        }

    @classmethod
    def score_research_perspective(
        cls,
        perspective: Dict[str, Any],
        formula_comparisons: List[Dict[str, Any]] | None = None,
        weights: Dict[str, float] | None = None,
    ) -> Dict[str, Any]:
        """对单个方剂研究视角进行统一评分"""
        weights = weights or cls.DEFAULT_WEIGHTS

        dim_scores = {
            "structure": cls._score_structure(perspective.get("structure_analysis", {})),
            "properties": cls._score_properties(perspective.get("component_properties", {})),
            "comparison": cls._score_comparison(formula_comparisons or [], perspective.get("similar_formulas", [])),
            "pharmacology": cls._score_pharmacology(perspective.get("pharmacological_profile", {})),
            "network": cls._score_network(perspective.get("network_pharmacology", {})),
            "supramolecular": cls._score_supramolecular(perspective.get("supramolecular_physicochemical", {})),
            "archaeology": cls._score_archaeology(perspective.get("knowledge_archaeology", {})),
            "complexity": cls._score_complexity(perspective.get("complexity_dynamics", {})),
        }

        weighted_total = 0.0
        weight_sum = 0.0
        for key, score in dim_scores.items():
            w = weights.get(key, 0.0)
            weighted_total += w * score
            weight_sum += w
        total_score = cls._clamp01(weighted_total / weight_sum) if weight_sum > 0 else 0.0

        ci95 = cls._ci95_from_dimension_scores(dim_scores)
        ranked = sorted(dim_scores.items(), key=lambda x: x[1], reverse=True)

        return {
            "formula_name": perspective.get("formula_name"),
            "dimension_scores": {k: round(v, 4) for k, v in dim_scores.items()},
            "weights": weights,
            "total_score": round(total_score, 4),
            "confidence_interval_95": ci95,
            "strengths": [name for name, _ in ranked[:3]],
            "gaps": [name for name, _ in ranked[-3:]],
            "paper_paragraph_inputs": {
                "headline": f"该方多维研究综合评分为 {round(total_score, 3)}（95%CI {ci95['lower']}-{ci95['upper']}）",
                "method_summary": [
                    f"结构维度={round(dim_scores['structure'],3)}",
                    f"网络药理维度={round(dim_scores['network'],3)}",
                    f"复杂动力学维度={round(dim_scores['complexity'],3)}",
                ],
                "evidence_summary": [
                    f"关键靶点数={perspective.get('network_pharmacology', {}).get('target_count', 0)}",
                    f"文献源流可追溯={bool(perspective.get('knowledge_archaeology', {}).get('origin'))}",
                    f"超分子协同分={perspective.get('supramolecular_physicochemical', {}).get('supramolecular_synergy_score', 0)}",
                ],
            },
        }


# ============================================================================
# 11. 总结分析引擎 - Summary Analysis Engine
# ============================================================================

class SummaryAnalysisEngine:
    """总结分析：频率/卡方、关联规则、复杂网络、聚类与因子、强化剂量、隐结构、时间序列剂量反应、贝叶斯网络"""

    _freq_chi_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _association_cache: Dict[str, Dict[str, Any]] = {}
    _network_cache: Dict[str, Dict[str, Any]] = {}
    _cluster_factor_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _reinforced_dosage_cache: Dict[str, Dict[str, Any]] = {}
    _latent_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    _time_dose_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    _bayes_cache: Dict[str, Dict[str, Any]] = {}

    DEFAULT_FORMULA_RECORDS: List[Dict[str, Any]] = [
        {
            "formula": "补中益气汤",
            "herbs": ["黄芪", "人参", "白术", "茯苓", "甘草", "升麻", "柴胡", "大枣"],
            "syndrome": "气虚证",
            "year": 2019,
            "dose_total": 50,
            "response": 0.72,
        },
        {
            "formula": "四君子汤",
            "herbs": ["人参", "白术", "茯苓", "甘草"],
            "syndrome": "脾胃气虚",
            "year": 2020,
            "dose_total": 40,
            "response": 0.68,
        },
        {
            "formula": "六君子汤",
            "herbs": ["人参", "白术", "茯苓", "甘草", "半夏", "陈皮"],
            "syndrome": "痰湿气虚",
            "year": 2021,
            "dose_total": 46,
            "response": 0.70,
        },
        {
            "formula": "补中益气汤",
            "herbs": ["黄芪", "党参", "白术", "茯苓", "甘草", "升麻", "柴胡"],
            "syndrome": "中气下陷",
            "year": 2022,
            "dose_total": 48,
            "response": 0.74,
        },
        {
            "formula": "四君子汤",
            "herbs": ["党参", "白术", "茯苓", "甘草"],
            "syndrome": "气虚证",
            "year": 2023,
            "dose_total": 42,
            "response": 0.69,
        },
    ]

    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        """稳定序列化签名，用于细粒度缓存键。"""
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return repr(value)

    @classmethod
    def analyze(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        records = context.get("summary_formula_records") or cls.DEFAULT_FORMULA_RECORDS
        transactions = [r.get("herbs", []) for r in records]
        herbs = sorted(list({h for t in transactions for h in t}))

        records_fp = cls._fingerprint(records)
        herbs_fp = cls._fingerprint(herbs)
        tx_fp = cls._fingerprint(transactions)
        ts_fp = cls._fingerprint(context.get("time_series_data"))
        dr_fp = cls._fingerprint(context.get("dose_response_data"))

        freq_key = (records_fp, herbs_fp)
        assoc_key = tx_fp
        network_key = records_fp
        cluster_key = (records_fp, herbs_fp)
        reinforced_key = "default"
        latent_key = (records_fp, herbs_fp)
        time_dose_key = (records_fp, ts_fp, dr_fp)
        bayes_key = records_fp

        if freq_key not in cls._freq_chi_cache:
            cls._freq_chi_cache[freq_key] = cls._frequency_and_chi_square(records, herbs)
        if assoc_key not in cls._association_cache:
            cls._association_cache[assoc_key] = cls._association_rules(transactions)
        if network_key not in cls._network_cache:
            cls._network_cache[network_key] = cls._complex_network_analysis(records)
        if cluster_key not in cls._cluster_factor_cache:
            cls._cluster_factor_cache[cluster_key] = cls._clustering_and_factor_analysis(records, herbs)
        if reinforced_key not in cls._reinforced_dosage_cache:
            cls._reinforced_dosage_cache[reinforced_key] = cls._reinforced_dosage_analysis(records)
        if latent_key not in cls._latent_cache:
            cls._latent_cache[latent_key] = cls._latent_structure_model(records, herbs)
        if time_dose_key not in cls._time_dose_cache:
            cls._time_dose_cache[time_dose_key] = cls._time_series_and_dose_response(records, context)
        if bayes_key not in cls._bayes_cache:
            cls._bayes_cache[bayes_key] = cls._bayesian_network_analysis(records)

        return {
            "frequency_chi_square": copy.deepcopy(cls._freq_chi_cache[freq_key]),
            "association_rules": copy.deepcopy(cls._association_cache[assoc_key]),
            "complex_network": copy.deepcopy(cls._network_cache[network_key]),
            "clustering_factor": copy.deepcopy(cls._cluster_factor_cache[cluster_key]),
            "reinforced_dosage": copy.deepcopy(cls._reinforced_dosage_cache[reinforced_key]),
            "latent_structure": copy.deepcopy(cls._latent_cache[latent_key]),
            "time_series_dose_response": copy.deepcopy(cls._time_dose_cache[time_dose_key]),
            "bayesian_network": copy.deepcopy(cls._bayes_cache[bayes_key]),
        }

    @classmethod
    def _frequency_and_chi_square(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        herb_freq: Dict[str, int] = {h: 0 for h in herbs}
        syndrome_values = sorted(list({r.get("syndrome", "unknown") for r in records}))

        for r in records:
            for h in r.get("herbs", []):
                herb_freq[h] = herb_freq.get(h, 0) + 1

        chi_square_items: List[Dict[str, Any]] = []
        try:
            from scipy.stats import chi2_contingency

            def calc(a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
                chi2, p, _, _ = chi2_contingency([[a, b], [c, d]])
                return float(chi2), float(p)

        except Exception:
            def calc(a: int, b: int, c: int, d: int) -> Tuple[float, Any]:
                # 无 scipy 时采用 2x2 Pearson chi-square 近似（不提供 p 值）
                n = a + b + c + d
                num = n * (a * d - b * c) ** 2
                den = (a + b) * (c + d) * (a + c) * (b + d)
                chi2 = float(num / den) if den > 0 else 0.0
                return chi2, None

        for herb in herbs:
            for syndrome in syndrome_values:
                a = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") == syndrome)
                b = sum(1 for r in records if herb in r.get("herbs", []) and r.get("syndrome") != syndrome)
                c = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") == syndrome)
                d = sum(1 for r in records if herb not in r.get("herbs", []) and r.get("syndrome") != syndrome)
                try:
                    chi2, p = calc(a, b, c, d)
                except Exception:
                    # scipy 在期望频数为0时会报错，回退到近似统计量
                    n = a + b + c + d
                    num = n * (a * d - b * c) ** 2
                    den = (a + b) * (c + d) * (a + c) * (b + d)
                    chi2 = float(num / den) if den > 0 else 0.0
                    p = None
                chi_square_items.append(
                    {
                        "herb": herb,
                        "syndrome": syndrome,
                        "chi2": round(float(chi2), 4),
                        "p_value": round(float(p), 6) if p is not None else None,
                    }
                )

        chi_square_items = sorted(chi_square_items, key=lambda x: x.get("chi2", 0), reverse=True)[:15]
        top_freq = sorted(herb_freq.items(), key=lambda x: x[1], reverse=True)[:15]

        return {
            "herb_frequency": [{"herb": h, "count": c} for h, c in top_freq],
            "chi_square_top": chi_square_items,
        }

    @classmethod
    def _association_rules(cls, transactions: List[List[str]]) -> Dict[str, Any]:
        n = len(transactions)
        if n == 0:
            return {"rules": []}

        item_count: Dict[str, int] = {}
        pair_count: Dict[Tuple[str, str], int] = {}
        for tx in transactions:
            unique = sorted(set(tx))
            for i in unique:
                item_count[i] = item_count.get(i, 0) + 1
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    pair = (unique[i], unique[j])
                    pair_count[pair] = pair_count.get(pair, 0) + 1

        rules: List[Dict[str, Any]] = []
        for (a, b), c_ab in pair_count.items():
            support = c_ab / n
            conf_a_b = c_ab / item_count[a]
            conf_b_a = c_ab / item_count[b]
            lift_a_b = conf_a_b / (item_count[b] / n)
            lift_b_a = conf_b_a / (item_count[a] / n)
            rules.append(
                {
                    "antecedent": [a],
                    "consequent": [b],
                    "support": round(support, 4),
                    "confidence": round(conf_a_b, 4),
                    "lift": round(lift_a_b, 4),
                }
            )
            rules.append(
                {
                    "antecedent": [b],
                    "consequent": [a],
                    "support": round(support, 4),
                    "confidence": round(conf_b_a, 4),
                    "lift": round(lift_b_a, 4),
                }
            )

        rules = sorted(rules, key=lambda x: (x["lift"], x["confidence"]), reverse=True)[:20]
        return {"rules": rules}

    @classmethod
    def _complex_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        herb_graph = nx.Graph()
        for r in records:
            herbs = sorted(set(r.get("herbs", [])))
            for h in herbs:
                herb_graph.add_node(h)
            for i in range(len(herbs)):
                for j in range(i + 1, len(herbs)):
                    u, v = herbs[i], herbs[j]
                    if herb_graph.has_edge(u, v):
                        herb_graph[u][v]["weight"] += 1
                    else:
                        herb_graph.add_edge(u, v, weight=1)

        centrality = nx.degree_centrality(herb_graph) if herb_graph.number_of_nodes() > 0 else {}
        top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
        avg_clustering = nx.average_clustering(herb_graph) if herb_graph.number_of_nodes() > 1 else 0.0

        communities_out: List[List[str]] = []
        try:
            from networkx.algorithms.community import greedy_modularity_communities
            comms = greedy_modularity_communities(herb_graph)
            communities_out = [sorted(list(c)) for c in comms]
        except Exception:
            communities_out = []

        return {
            "nodes": herb_graph.number_of_nodes(),
            "edges": herb_graph.number_of_edges(),
            "density": round(nx.density(herb_graph), 4) if herb_graph.number_of_nodes() > 1 else 0.0,
            "avg_clustering": round(float(avg_clustering), 4),
            "top_central_nodes": [{"node": n, "degree_centrality": round(v, 4)} for n, v in top_nodes],
            "communities": communities_out,
        }

    @classmethod
    def _clustering_and_factor_analysis(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        if not records or not herbs:
            return {"clusters": [], "factors": []}

        X = np.array([[1.0 if h in r.get("herbs", []) else 0.0 for h in herbs] for r in records])
        clusters_out: List[Dict[str, Any]] = []
        factors_out: List[Dict[str, Any]] = []

        try:
            from sklearn.cluster import KMeans
            n_clusters = min(3, len(records))
            model = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
            labels = model.fit_predict(X)
            for i, label in enumerate(labels):
                clusters_out.append(
                    {
                        "formula": records[i].get("formula"),
                        "cluster": int(label),
                    }
                )
        except Exception:
            clusters_out = [{"formula": r.get("formula"), "cluster": 0} for r in records]

        try:
            from sklearn.decomposition import FactorAnalysis
            n_components = min(2, X.shape[1], X.shape[0])
            fa = FactorAnalysis(n_components=n_components, random_state=42)
            fa.fit(X)
            loadings = fa.components_
            for idx, comp in enumerate(loadings):
                pairs = sorted([(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                factors_out.append(
                    {
                        "factor": idx,
                        "top_herbs": [{"herb": h, "loading": round(v, 4)} for h, v in pairs[:5]],
                    }
                )
        except Exception:
            # fallback SVD
            _, _, vt = np.linalg.svd(X, full_matrices=False)
            if vt.size > 0:
                for idx in range(min(2, vt.shape[0])):
                    comp = vt[idx]
                    pairs = sorted([(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                    factors_out.append(
                        {
                            "factor": idx,
                            "top_herbs": [{"herb": h, "loading": round(v, 4)} for h, v in pairs[:5]],
                        }
                    )

        return {"clusters": clusters_out, "factors": factors_out}

    @classmethod
    def _reinforced_dosage_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """基于强化更新策略的剂量分析（轻量近似）"""
        formula_structures = FormulaStructureAnalyzer.FORMULA_STRUCTURES
        optimized: Dict[str, Any] = {}
        for fname, data in formula_structures.items():
            herbs: List[Dict[str, Any]] = []
            for role in ["sovereign", "minister", "assistant", "envoy"]:
                herbs.extend(data.get(role, []))
            if not herbs:
                continue

            # reward: 临床证据+组件可解释性
            scores = []
            for h in herbs:
                name = h.get("name")
                base_ratio = float(h.get("ratio", 0.0))
                clin = ModernPharmacologyDatabase.get_clinical_efficacy(name)
                comp = ModernPharmacologyDatabase.get_active_components(name)
                reward = 0.55 * min(1.0, len(clin) / 4.0) + 0.45 * min(1.0, len(comp) / 4.0)
                new_score = 0.7 * base_ratio + 0.3 * reward
                scores.append((name, new_score))

            total = sum(v for _, v in scores) or 1.0
            optimized[fname] = [
                {"herb": n, "recommended_ratio": round(v / total, 4)}
                for n, v in sorted(scores, key=lambda x: x[1], reverse=True)
            ]

        return {"optimized_ratios": optimized}

    @classmethod
    def _latent_structure_model(cls, records: List[Dict[str, Any]], herbs: List[str]) -> Dict[str, Any]:
        if not records or not herbs:
            return {"topics": []}
        X = np.array([[1.0 if h in r.get("herbs", []) else 0.0 for h in herbs] for r in records])

        topics: List[Dict[str, Any]] = []
        try:
            from sklearn.decomposition import LatentDirichletAllocation
            n_comp = min(2, max(1, X.shape[0]))
            lda = LatentDirichletAllocation(n_components=n_comp, random_state=42)
            lda.fit(X)
            comps = lda.components_
            for i, comp in enumerate(comps):
                pairs = sorted([(herbs[j], float(comp[j])) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                topics.append(
                    {
                        "topic": i,
                        "top_herbs": [{"herb": h, "weight": round(w, 4)} for h, w in pairs[:5]],
                    }
                )
        except Exception:
            # fallback: SVD latent pattern
            _, _, vt = np.linalg.svd(X, full_matrices=False)
            for i in range(min(2, vt.shape[0])):
                comp = vt[i]
                pairs = sorted([(herbs[j], abs(float(comp[j]))) for j in range(len(herbs))], key=lambda x: x[1], reverse=True)
                topics.append(
                    {
                        "topic": i,
                        "top_herbs": [{"herb": h, "weight": round(w, 4)} for h, w in pairs[:5]],
                    }
                )

        return {"topics": topics}

    @classmethod
    def _time_series_and_dose_response(cls, records: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        ts_data = context.get("time_series_data")
        if ts_data:
            years = np.array([float(p.get("time")) for p in ts_data])
            values = np.array([float(p.get("value")) for p in ts_data])
        else:
            years = np.array([float(r.get("year")) for r in records])
            values = np.array([float(r.get("response", 0.0)) for r in records])

        if len(years) >= 2:
            coeff = np.polyfit(years, values, deg=1)
            slope, intercept = float(coeff[0]), float(coeff[1])
        else:
            slope, intercept = 0.0, float(values[0]) if len(values) else 0.0

        # dose-response
        dr_data = context.get("dose_response_data")
        if dr_data:
            doses = np.array([float(p.get("dose")) for p in dr_data])
            responses = np.array([float(p.get("response")) for p in dr_data])
        else:
            doses = np.array([float(r.get("dose_total", 0.0)) for r in records if r.get("dose_total") is not None])
            responses = np.array([float(r.get("response", 0.0)) for r in records if r.get("dose_total") is not None])

        dose_model: Dict[str, Any] = {}
        if len(doses) >= 3:
            try:
                from scipy.optimize import curve_fit

                def hill(x, emax, ec50, h):
                    return emax * (x ** h) / (ec50 ** h + x ** h + 1e-9)

                popt, _ = curve_fit(hill, doses, responses, bounds=(0, [1.5, 200.0, 5.0]), maxfev=20000)
                dose_model = {
                    "model": "hill",
                    "emax": round(float(popt[0]), 4),
                    "ec50": round(float(popt[1]), 4),
                    "hill_coefficient": round(float(popt[2]), 4),
                }
            except Exception:
                c = np.polyfit(doses, responses, deg=1)
                dose_model = {"model": "linear", "slope": round(float(c[0]), 4), "intercept": round(float(c[1]), 4)}
        else:
            dose_model = {"model": "insufficient_data"}

        return {
            "time_series_trend": {
                "slope": round(float(slope), 6),
                "intercept": round(float(intercept), 4),
                "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
            },
            "dose_response": dose_model,
        }

    @classmethod
    def _bayesian_network_analysis(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        # 简化BN: Q(气虚) -> F(使用补中益气汤) -> R(响应改善), Q -> R
        samples: List[Dict[str, int]] = []
        for r in records:
            syndrome = str(r.get("syndrome", ""))
            formula = str(r.get("formula", ""))
            response = float(r.get("response", 0.0))
            samples.append(
                {
                    "Q": 1 if "气虚" in syndrome else 0,
                    "F": 1 if formula == "补中益气汤" else 0,
                    "R": 1 if response >= 0.72 else 0,
                }
            )

        n = len(samples) or 1
        p_q = sum(s["Q"] for s in samples) / n

        def cond_prob(var: str, given: Dict[str, int]) -> float:
            matched = [s for s in samples if all(s[k] == v for k, v in given.items())]
            if not matched:
                return 0.5
            return sum(s[var] for s in matched) / len(matched)

        p_f_q1 = cond_prob("F", {"Q": 1})
        p_f_q0 = cond_prob("F", {"Q": 0})
        p_r_q1_f1 = cond_prob("R", {"Q": 1, "F": 1})
        p_r_q1_f0 = cond_prob("R", {"Q": 1, "F": 0})

        # 示例推断: P(R=1|Q=1,F=1)
        inference = p_r_q1_f1

        return {
            "structure": ["Q->F", "Q->R", "F->R"],
            "priors": {"P(Q=1)": round(float(p_q), 4)},
            "cpd": {
                "P(F=1|Q=1)": round(float(p_f_q1), 4),
                "P(F=1|Q=0)": round(float(p_f_q0), 4),
                "P(R=1|Q=1,F=1)": round(float(p_r_q1_f1), 4),
                "P(R=1|Q=1,F=0)": round(float(p_r_q1_f0), 4),
            },
            "inference_example": {
                "query": "P(R=1|Q=1,F=1)",
                "value": round(float(inference), 4),
            },
        }


# 导出主要类
__all__ = [
    "FormulaStructureAnalyzer",
    "HerbPropertyDatabase",
    "FormulaComparator",
    "ModernPharmacologyDatabase",
    "IntegratedResearchAnalyzer",
    "ResearchScoringPanel",
    "SummaryAnalysisEngine",
    "NetworkPharmacologySystemBiologyAnalyzer",
    "SupramolecularPhysicochemicalAnalyzer",
    "ClassicalLiteratureArchaeologyAnalyzer",
    "ComplexityNonlinearDynamicsAnalyzer",
    "FormulaDosageForm",
    "HerbTemperature",
    "MeridianType",
]
