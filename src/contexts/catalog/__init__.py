"""Catalog bounded context — Topic / SubjectClass / DynastySlice 视图。

T3.1: 与 ``src.research`` 平级的独立包，负责把 Document 节点映射到
``Topic``、``SubjectClass``、``DynastySlice`` 三种检索视图。
"""

from src.contexts.catalog.service import CatalogContext
from src.contexts.catalog.views import (
    DynastySliceView,
    SubjectClassView,
    TopicView,
)

__all__ = [
    "CatalogContext",
    "TopicView",
    "SubjectClassView",
    "DynastySliceView",
]
