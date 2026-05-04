"""学习模块导出。"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adaptive_tuner import AdaptiveTuner
    from .kg_node_self_learning import KGNodeSelfLearningEnhancer
    from .pattern_recognizer import PatternRecognizer
    from .self_learning_engine import SelfLearningEngine
    from .weak_edge_candidate_repo import WeakEdgeCandidateRepository

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "SelfLearningEngine": (".self_learning_engine", "SelfLearningEngine"),
    "PatternRecognizer": (".pattern_recognizer", "PatternRecognizer"),
    "AdaptiveTuner": (".adaptive_tuner", "AdaptiveTuner"),
    "KGNodeSelfLearningEnhancer": (
        ".kg_node_self_learning",
        "KGNodeSelfLearningEnhancer",
    ),
    "WeakEdgeCandidateRepository": (
        ".weak_edge_candidate_repo",
        "WeakEdgeCandidateRepository",
    ),
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
