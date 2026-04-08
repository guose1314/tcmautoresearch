"""src/research/phases — 阶段处理器拆分模块。

每个文件包含一个 Mixin 类，由 ResearchPhaseHandlers 通过多重继承组合。
"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .analyze_phase import AnalyzePhaseMixin
    from .experiment_phase import ExperimentPhaseMixin
    from .hypothesis_phase import HypothesisPhaseMixin
    from .observe_phase import ObservePhaseMixin
    from .publish_phase import PublishPhaseMixin
    from .reflect_phase import ReflectPhaseMixin

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "ObservePhaseMixin": (".observe_phase", "ObservePhaseMixin"),
    "HypothesisPhaseMixin": (".hypothesis_phase", "HypothesisPhaseMixin"),
    "ExperimentPhaseMixin": (".experiment_phase", "ExperimentPhaseMixin"),
    "AnalyzePhaseMixin": (".analyze_phase", "AnalyzePhaseMixin"),
    "PublishPhaseMixin": (".publish_phase", "PublishPhaseMixin"),
    "ReflectPhaseMixin": (".reflect_phase", "ReflectPhaseMixin"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path, __name__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
