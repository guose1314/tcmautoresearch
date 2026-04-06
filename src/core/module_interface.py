# core/module_interface.py
"""
中医古籍全自动研究系统 - 专业学术模块接口（已弃用）

此文件仅保留向后兼容重导出。
ModuleInterface 现在是 BaseModule 的别名，新代码应直接继承 BaseModule。
数据类型（ModuleContext / ModuleOutput / ModuleStatus / ModulePriority）
的权威来源为 src.core.module_base。
"""

from src.core.module_base import (
    BaseModule,
    ModuleContext,
    ModuleOutput,
    ModulePriority,
    ModuleStatus,
)

# 向后兼容别名 — 新代码应直接继承 BaseModule
ModuleInterface = BaseModule

__all__ = [
    'ModuleInterface',
    'ModuleContext',
    'ModuleOutput',
    'ModuleStatus',
    'ModulePriority',
]
