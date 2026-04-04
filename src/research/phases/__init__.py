"""src/research/phases — 阶段处理器拆分模块。

每个文件包含一个 Mixin 类，由 ResearchPhaseHandlers 通过多重继承组合。
"""

from .observe_phase import ObservePhaseMixin
from .hypothesis_phase import HypothesisPhaseMixin
from .experiment_phase import ExperimentPhaseMixin
from .analyze_phase import AnalyzePhaseMixin
from .publish_phase import PublishPhaseMixin
from .reflect_phase import ReflectPhaseMixin

__all__ = [
    "ObservePhaseMixin",
    "HypothesisPhaseMixin",
    "ExperimentPhaseMixin",
    "AnalyzePhaseMixin",
    "PublishPhaseMixin",
    "ReflectPhaseMixin",
]
