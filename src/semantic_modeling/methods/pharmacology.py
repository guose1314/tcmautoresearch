"""现代药理学与临床研究数据库。"""

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class PharmacologicalData:
    """现代药理学数据。"""

    herb_name: str
    active_components: Dict[str, str]
    pharmacological_actions: List[str]
    clinical_efficacy: Dict[str, float]
    adverse_effects: List[str]
    drug_interactions: List[str]


class ModernPharmacologyDatabase:
    """现代药理学与临床数据库。"""

    PHARMACOLOGY_DATA: Dict[str, Dict] = {
        "黄芪": {
            "active_components": {"黄芪多糖": "5-10%", "黄芪皂苷": "0.05-0.5%", "黄酮": "0.1-0.3%"},
            "pharmacological_actions": ["增强免疫功能（增加T/B淋巴细胞）", "抗疲劳作用", "抗肿瘤活性", "改善血循环", "保护心肌细胞"],
            "clinical_research": {"反复呼吸道感染": 0.78, "慢性心衰": 0.65, "肾病综合征": 0.72, "糖尿病并发症": 0.68},
            "adverse_effects": ["长期大量使用可能引起腹胀"],
            "interactions": ["与某些免疫抑制剂协同作用"],
        },
        "人参": {
            "active_components": {"人参皂苷": "2-3%", "人参多糖": "6-8%", "挥发油": "0.01%"},
            "pharmacological_actions": ["中枢神经系统调节", "增强适应原样作用", "改善认知功能", "抗疲劳", "调节免疫"],
            "clinical_research": {"疲劳综合征": 0.80, "认知功能下降": 0.73, "术后恢复": 0.76},
            "adverse_effects": ["过量可能引起兴奋、失眠"],
            "interactions": ["含有caffeine类物质"],
        },
        "丹参": {
            "active_components": {"丹酚酸": "6-8%", "丹参酮": "0.2-0.4%"},
            "pharmacological_actions": ["改善微循环", "抗血栓", "抗缺血", "抗氧化", "保护心肌"],
            "clinical_research": {"冠心病": 0.71, "心肌梗死": 0.68, "脑卒中": 0.74},
            "adverse_effects": ["出血倾向增加（与抗凝血药协同）"],
            "interactions": ["与华法林等抗凝血药相互作用增强"],
        },
    }

    @classmethod
    def get_pharmacological_data(cls, herb_name: str) -> Dict:
        return cls.PHARMACOLOGY_DATA.get(herb_name, {})

    @classmethod
    def get_active_components(cls, herb_name: str) -> Dict:
        return cls.PHARMACOLOGY_DATA.get(herb_name, {}).get("active_components", {})

    @classmethod
    def get_clinical_efficacy(cls, herb_name: str) -> Dict:
        return cls.PHARMACOLOGY_DATA.get(herb_name, {}).get("clinical_research", {})

    @classmethod
    def get_safety_info(cls, herb_name: str) -> Dict:
        data = cls.PHARMACOLOGY_DATA.get(herb_name, {})
        return {
            "adverse_effects": data.get("adverse_effects", []),
            "drug_interactions": data.get("interactions", []),
        }

    @classmethod
    def find_herbs_for_indication(cls, indication: str) -> List[Tuple[str, float]]:
        herbs_with_efficacy = []
        for herb_name, data in cls.PHARMACOLOGY_DATA.items():
            clinical_research = data.get("clinical_research", {})
            if indication in clinical_research:
                herbs_with_efficacy.append((herb_name, clinical_research[indication]))
        return sorted(herbs_with_efficacy, key=lambda x: x[1], reverse=True)
