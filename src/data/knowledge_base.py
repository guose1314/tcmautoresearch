# src/data/knowledge_base.py
"""
知识库数据加载接口 — 为语义建模子模块提供结构化数据。

数据优先级：
1. 配置文件 / 数据库（运行时注入）
2. 内置精简知识库（离线回退）

所有函数均返回 ``dict``，调用方不应假设数据完整性（空值合法）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内置精简知识库（离线回退用）
# ---------------------------------------------------------------------------

_FORMULA_ARCHIVE: Dict[str, Dict[str, Any]] = {
    "补中益气汤": {
        "dynasty": "金元",
        "author": "李东垣",
        "source": "脾胃论",
        "indications": ["气虚发热", "中气下陷", "劳倦内伤"],
    },
    "四君子汤": {
        "dynasty": "宋",
        "author": "佚名",
        "source": "太平惠民和剂局方",
        "indications": ["脾胃气虚", "食少便溏"],
    },
    "六味地黄丸": {
        "dynasty": "宋",
        "author": "钱乙",
        "source": "小儿药证直诀",
        "indications": ["肾阴亏损", "头晕耳鸣", "腰膝酸软"],
    },
    "桂枝汤": {
        "dynasty": "汉",
        "author": "张仲景",
        "source": "伤寒论",
        "indications": ["外感风寒表虚", "自汗恶风"],
    },
    "麻黄汤": {
        "dynasty": "汉",
        "author": "张仲景",
        "source": "伤寒论",
        "indications": ["外感风寒表实", "无汗而喘"],
    },
}

_FORMULA_STRUCTURES: Dict[str, Dict[str, Any]] = {
    "补中益气汤": {
        "sovereign": [{"name": "黄芪", "ratio": 0.25}],
        "minister": [{"name": "人参", "ratio": 0.15}, {"name": "白术", "ratio": 0.15}],
        "assistant": [{"name": "当归", "ratio": 0.12}, {"name": "陈皮", "ratio": 0.10}],
        "envoy": [{"name": "甘草", "ratio": 0.10}, {"name": "升麻", "ratio": 0.07}, {"name": "柴胡", "ratio": 0.06}],
    },
    "四君子汤": {
        "sovereign": [{"name": "人参", "ratio": 0.30}],
        "minister": [{"name": "白术", "ratio": 0.25}],
        "assistant": [{"name": "茯苓", "ratio": 0.25}],
        "envoy": [{"name": "甘草", "ratio": 0.20}],
    },
}

_HERB_PROPERTIES: Dict[str, Dict[str, Any]] = {
    "黄芪": {"temperature": "微温", "flavor": ["甘"], "meridians": ["肺", "脾"]},
    "人参": {"temperature": "微温", "flavor": ["甘", "微苦"], "meridians": ["心", "肺", "脾"]},
    "白术": {"temperature": "温", "flavor": ["甘", "苦"], "meridians": ["脾", "胃"]},
    "茯苓": {"temperature": "平", "flavor": ["甘", "淡"], "meridians": ["心", "脾", "肾"]},
    "甘草": {"temperature": "平", "flavor": ["甘"], "meridians": ["心", "肺", "脾", "胃"]},
    "当归": {"temperature": "温", "flavor": ["甘", "辛"], "meridians": ["肝", "心", "脾"]},
    "附子": {"temperature": "大热", "flavor": ["辛", "甘"], "meridians": ["心", "肾", "脾"]},
    "桂枝": {"temperature": "温", "flavor": ["辛", "甘"], "meridians": ["心", "肺", "膀胱"]},
}

_HERB_TARGETS: Dict[str, List[str]] = {
    "黄芪": ["VEGF", "TNF-α", "IL-6", "NF-κB", "TGF-β"],
    "人参": ["STAT3", "PI3K", "AKT", "mTOR", "Bcl-2"],
    "当归": ["TP53", "EGFR", "VEGF", "TNF-α", "IL-1β"],
    "甘草": ["COX-2", "NF-κB", "TNF-α", "IL-6", "iNOS"],
    "附子": ["SCN5A", "CACNA1C", "ADRB1", "ADRB2", "CHRM2"],
    "白术": ["IL-6", "TNF-α", "NF-κB", "TGF-β", "SMAD2"],
}

_TARGET_PATHWAYS: Dict[str, List[str]] = {
    "TNF-α": ["TNF signaling pathway", "NF-κB signaling", "Apoptosis"],
    "VEGF": ["HIF-1 signaling", "Angiogenesis", "VEGF signaling pathway"],
    "NF-κB": ["NF-κB signaling", "Inflammatory pathway", "Apoptosis"],
    "IL-6": ["JAK-STAT signaling", "Cytokine-cytokine receptor interaction"],
    "STAT3": ["JAK-STAT signaling", "PI3K-Akt signaling"],
    "PI3K": ["PI3K-Akt signaling", "mTOR signaling pathway"],
    "TP53": ["p53 signaling pathway", "Cell cycle", "Apoptosis"],
    "COX-2": ["Arachidonic acid metabolism", "Inflammatory pathway"],
}


# ---------------------------------------------------------------------------
# 公共加载函数
# ---------------------------------------------------------------------------


def load_formula_archive() -> Dict[str, Dict[str, Any]]:
    """加载方剂文献档案（方剂名 → 历史信息字典）。"""
    return dict(_FORMULA_ARCHIVE)


def load_formula_structures() -> Dict[str, Dict[str, Any]]:
    """加载方剂君臣佐使结构（方剂名 → 结构字典）。"""
    return dict(_FORMULA_STRUCTURES)


def load_herb_properties() -> Dict[str, Dict[str, Any]]:
    """加载药物性味归经数据（药物名 → 性质字典）。"""
    return dict(_HERB_PROPERTIES)


def load_herb_targets() -> Dict[str, List[str]]:
    """加载草药–靶点映射（药物名 → 靶点列表）。"""
    return dict(_HERB_TARGETS)


def load_target_pathways() -> Dict[str, List[str]]:
    """加载靶点–通路映射（靶点 → 通路列表）。"""
    return dict(_TARGET_PATHWAYS)
