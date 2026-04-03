"""
高级研究方法模块 - 多维度研究方法切入点（向后兼容重导出层）

所有实现已拆分至 src/semantic_modeling/methods/ 子包。
本文件仅保留重导出以确保现有 import 路径不中断。
"""

from src.semantic_modeling.methods import *  # noqa: F401,F403
from src.semantic_modeling.methods import __all__  # noqa: F401

# --- 以下为旧代码，已迁移至 methods/ 子包，保留注释供追溯 ---
# 原文件 1538 行已拆分为 11 个子模块：
# - methods/formula_structure.py
# - methods/herb_properties.py
# - methods/formula_comparator.py
# - methods/pharmacology.py
# - methods/network_pharmacology.py
# - methods/supramolecular.py
# - methods/classical_literature.py
# - methods/complexity_science.py
# - methods/integrated_analyzer.py
# - methods/scoring_panel.py
# - methods/summary_engine.py
