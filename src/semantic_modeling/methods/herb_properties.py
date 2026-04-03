"""药物性味与归经 - Herb Properties and Meridian Entry"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


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
