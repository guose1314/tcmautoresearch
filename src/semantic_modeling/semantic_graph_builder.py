"""兼容层 - 已迁移至 src.analysis.semantic_graph.SemanticGraphService

.. deprecated:: 2.0
    请改用 ``from src.analysis.semantic_graph import SemanticGraphService``。
    ``SemanticGraphBuilder`` 仅作为旧实现兼容符号保留。
"""

import warnings as _warnings

_warnings.warn(
    "src.semantic_modeling.semantic_graph_builder 已迁移至 "
    "src.analysis.semantic_graph.SemanticGraphService，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.analysis.semantic_graph import *  # noqa: F401,F403
from src.analysis.semantic_graph import SemanticGraphBuilder, SemanticGraphService
