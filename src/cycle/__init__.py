"""cycle 包当前仅暴露现行运行时入口。"""

import importlib as _importlib
from typing import TYPE_CHECKING

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "cycle 运行时命令、研究会话与真实模块链入口"

if TYPE_CHECKING:
    from .cycle_cli import build_cycle_demo_arg_parser
    from .cycle_command_executor import execute_cycle_demo_command
    from .cycle_research_session import run_research_session
    from .cycle_runner import execute_real_module_pipeline, run_full_cycle_demo

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "build_cycle_demo_arg_parser": (".cycle_cli", "build_cycle_demo_arg_parser"),
    "execute_cycle_demo_command": (".cycle_command_executor", "execute_cycle_demo_command"),
    "execute_real_module_pipeline": (".cycle_runner", "execute_real_module_pipeline"),
    "run_full_cycle_demo": (".cycle_runner", "run_full_cycle_demo"),
    "run_research_session": (".cycle_research_session", "run_research_session"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr = _LAZY_IMPORTS[name]
    mod = _importlib.import_module(module_path, __name__)
    val = getattr(mod, attr)
    globals()[name] = val
    return val
