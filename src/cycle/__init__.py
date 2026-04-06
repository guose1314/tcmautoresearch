# cycle/__init__.py
"""
中医古籍全自动研究系统 - 专业学术迭代循环（延迟导入优化）
"""

import importlib as _importlib
from typing import TYPE_CHECKING

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于AI的中医古籍智能研究迭代循环系统"

if TYPE_CHECKING:
    from .fixing_stage import FixingStage, RepairAction
    from .iteration_cycle import (
        CycleStatus,
        IterationConfig,
        IterationCycle,
        IterationResult,
    )
    from .module_iteration import ModuleIterationCycle, ModuleIterationResult
    from .system_iteration import SystemIterationCycle, SystemIterationResult
    from .test_driven_iteration import (
        TestDrivenIteration,
        TestDrivenIterationManager,
        TestResult,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "FixingStage": (".fixing_stage", "FixingStage"),
    "RepairAction": (".fixing_stage", "RepairAction"),
    "IterationCycle": (".iteration_cycle", "IterationCycle"),
    "IterationResult": (".iteration_cycle", "IterationResult"),
    "IterationConfig": (".iteration_cycle", "IterationConfig"),
    "CycleStatus": (".iteration_cycle", "CycleStatus"),
    "ModuleIterationCycle": (".module_iteration", "ModuleIterationCycle"),
    "ModuleIterationResult": (".module_iteration", "ModuleIterationResult"),
    "TestDrivenIteration": (".test_driven_iteration", "TestDrivenIteration"),
    "TestDrivenIterationManager": (".test_driven_iteration", "TestDrivenIterationManager"),
    "TestResult": (".test_driven_iteration", "TestResult"),
}

# 模块导出
__all__ = list(_LAZY_IMPORTS.keys())

# SystemIterationCycle 可选依赖
_OPTIONAL_IMPORTS: dict[str, tuple[str, str]] = {
    "SystemIterationCycle": (".system_iteration", "SystemIterationCycle"),
    "SystemIterationResult": (".system_iteration", "SystemIterationResult"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path, __name__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    if name in _OPTIONAL_IMPORTS:
        module_path, attr = _OPTIONAL_IMPORTS[name]
        try:
            mod = _importlib.import_module(module_path, __name__)
            val = getattr(mod, attr)
        except Exception:
            val = None
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
