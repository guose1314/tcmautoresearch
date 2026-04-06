"""src/knowledge — 知识检索层（延迟导入优化）"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage.graph_interface import IKnowledgeGraph, KnowledgeGap

    from .embedding_service import (
        EmbeddingItem,
        EmbeddingService,
        SearchResult,
    )
    from .kg_query_engine import KGQueryEngine, QueryResult
    from .kg_rag import KGRAGContext, KGRAGService
    from .ontology_manager import OntologyManager, get_default_ontology_manager
    from .tcm_knowledge_graph import (
        TCMKnowledgeGraph,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "IKnowledgeGraph": ("src.storage.graph_interface", "IKnowledgeGraph"),
    "KnowledgeGap": ("src.storage.graph_interface", "KnowledgeGap"),
    "EmbeddingItem": (".embedding_service", "EmbeddingItem"),
    "EmbeddingService": (".embedding_service", "EmbeddingService"),
    "SearchResult": (".embedding_service", "SearchResult"),
    "KGQueryEngine": (".kg_query_engine", "KGQueryEngine"),
    "QueryResult": (".kg_query_engine", "QueryResult"),
    "KGRAGContext": (".kg_rag", "KGRAGContext"),
    "KGRAGService": (".kg_rag", "KGRAGService"),
    "OntologyManager": (".ontology_manager", "OntologyManager"),
    "get_default_ontology_manager": (".ontology_manager", "get_default_ontology_manager"),
    "TCMKnowledgeGraph": (".tcm_knowledge_graph", "TCMKnowledgeGraph"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        if module_path.startswith("."):
            mod = _importlib.import_module(module_path, __name__)
        else:
            mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
