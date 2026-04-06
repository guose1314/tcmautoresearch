# core/__init__.py
"""
中医古籍全自动研究系统 - 专业学术核心模块（延迟导入优化）
"""

import importlib as _importlib
import logging
from typing import TYPE_CHECKING

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于T/C IATCM 098-2023标准的中医古籍研究系统核心模块"

if TYPE_CHECKING:
    from .algorithm_optimizer import AlgorithmOptimizer
    from .architecture import ModuleRegistry, SystemArchitecture
    from .contracts import ModuleResult, PipelineContext
    from .event_bus import EventBus
    from .module_base import (
        BaseModule,
        ModuleContext,
        ModuleOutput,
        ModulePriority,
        ModuleStatus,
    )
    from .module_factory import ModuleFactory
    from .module_interface import ModuleInterface

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "AlgorithmOptimizer": (".algorithm_optimizer", "AlgorithmOptimizer"),
    "SystemArchitecture": (".architecture", "SystemArchitecture"),
    "ModuleRegistry": (".architecture", "ModuleRegistry"),
    "PipelineContext": (".contracts", "PipelineContext"),
    "ModuleResult": (".contracts", "ModuleResult"),
    "EventBus": (".event_bus", "EventBus"),
    "BaseModule": (".module_base", "BaseModule"),
    "ModuleContext": (".module_base", "ModuleContext"),
    "ModuleOutput": (".module_base", "ModuleOutput"),
    "ModuleStatus": (".module_base", "ModuleStatus"),
    "ModulePriority": (".module_base", "ModulePriority"),
    "ModuleFactory": (".module_factory", "ModuleFactory"),
    "ModuleInterface": (".module_interface", "ModuleInterface"),
}

# 模块导出
__all__ = [
    # Recommended
    'BaseModule',
    'SystemArchitecture',
    'AlgorithmOptimizer',
    'ModuleRegistry',
    'EventBus',
    'ModuleFactory',
    'PipelineContext',
    'ModuleResult',
    # Deprecated — kept for backward compatibility
    'ModuleInterface',
    'ModuleContext',
    'ModuleOutput',
    'ModuleStatus',
    'ModulePriority',
]

# ──────────────────────────────────────────────────────────────────────
# 以下静态配置字典已迁移至 config/reference_constants.yml（无消费者引用）。
# 如需加载，请使用: yaml.safe_load(open("config/reference_constants.yml"))
# ──────────────────────────────────────────────────────────────────────

# 初始化日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path, __name__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
