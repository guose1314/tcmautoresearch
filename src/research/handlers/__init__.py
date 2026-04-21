# src/research/handlers/__init__.py
"""
研究阶段处理器子包。

每个阶段的执行逻辑已从 research_pipeline_phase_handlers.py 拆分到独立文件，
以满足单一职责原则，降低圈复杂度，便于独立测试。

阶段 → Handler 映射：
  observe      → ObservePhaseHandler
  hypothesis   → HypothesisPhaseHandler
  experiment   → ExperimentPhaseHandler
  analyze      → AnalyzePhaseHandler
  publish      → PublishPhaseHandler
  reflect      → ReflectPhaseHandler
"""

from src.research.handlers.base_handler import BasePhaseHandler
from src.research.handlers.analyze_handler import AnalyzePhaseHandler
from src.research.handlers.experiment_handler import ExperimentPhaseHandler
from src.research.handlers.hypothesis_handler import HypothesisPhaseHandler
from src.research.handlers.observe_handler import ObservePhaseHandler
from src.research.handlers.publish_handler import PublishPhaseHandler
from src.research.handlers.reflect_handler import ReflectPhaseHandler

__all__ = [
    "BasePhaseHandler",
    "AnalyzePhaseHandler",
    "ExperimentPhaseHandler",
    "HypothesisPhaseHandler",
    "ObservePhaseHandler",
    "PublishPhaseHandler",
    "ReflectPhaseHandler",
]
