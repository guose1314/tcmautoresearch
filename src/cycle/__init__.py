# cycle/__init__.py
"""
中医古籍全自动研究系统 - 专业学术迭代循环初始化文件
"""

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于AI的中医古籍智能研究迭代循环系统"

# 导入主要类和函数
from .fixing_stage import FixingStage, RepairAction
from .iteration_cycle import (
    CycleStatus,
    IterationConfig,
    IterationCycle,
    IterationResult,
)
from .module_iteration import ModuleIterationCycle, ModuleIterationResult
from .test_driven_iteration import (
    TestDrivenIteration,
    TestDrivenIterationManager,
    TestResult,
)

try:
    from .system_iteration import SystemIterationCycle, SystemIterationResult
except Exception:  # pragma: no cover - 仅用于可选依赖降级
    SystemIterationCycle = None
    SystemIterationResult = None

# 模块导出
__all__ = [
    'IterationCycle',
    'IterationResult',
    'IterationConfig',
    'CycleStatus',
    'ModuleIterationCycle',
    'ModuleIterationResult',
    'TestDrivenIteration',
    'TestDrivenIterationManager',
    'TestResult',
    'FixingStage',
    'RepairAction'
]

if SystemIterationCycle is not None and SystemIterationResult is not None:
    __all__.extend(['SystemIterationCycle', 'SystemIterationResult'])

# ──────────────────────────────────────────────────────────────────────
# 以下静态配置字典已迁移至 config/reference_constants.yml（无消费者引用）。
# ──────────────────────────────────────────────────────────────────────

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍迭代循环模块已初始化")
