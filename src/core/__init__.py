# core/__init__.py
"""
中医古籍全自动研究系统 - 专业学术核心模块初始化文件
"""

import logging

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于T/C IATCM 098-2023标准的中医古籍研究系统核心模块"

# 导入主要类和函数
from .algorithm_optimizer import AlgorithmOptimizer
from .architecture import ModuleRegistry, SystemArchitecture
from .contracts import ModuleResult, PipelineContext
from .event_bus import EventBus

# BaseModule is the recommended base class for all modules.
from .module_base import BaseModule
from .module_factory import ModuleFactory

# ModuleInterface and its data classes are kept for backward compatibility.
# New code should inherit BaseModule directly.
from .module_interface import (
    ModuleContext,
    ModuleInterface,
    ModuleOutput,
    ModulePriority,
    ModuleStatus,
)

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

logger = logging.getLogger(__name__)
logger.info("中医古籍核心模块已初始化")
