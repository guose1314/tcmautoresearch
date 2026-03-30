"""research 层兼容导出：假设引擎。"""

from src.hypothesis import hypothesis_engine as _hypothesis_engine

HypothesisEngine = _hypothesis_engine.HypothesisEngine
HypothesisCandidate = _hypothesis_engine.HypothesisCandidate
ValidationIteration = _hypothesis_engine.ValidationIteration

__all__ = ["HypothesisEngine", "HypothesisCandidate", "ValidationIteration"]
