"""src/knowledge — 知识检索层"""

# 接口与数据结构从 storage.graph_interface 导入（规范出处），此处为向后兼容再导出
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

__all__ = [
    "EmbeddingItem",
    "EmbeddingService",
    "IKnowledgeGraph",
    "KGQueryEngine",
    "KGRAGContext",
    "KGRAGService",
    "KnowledgeGap",
    "OntologyManager",
    "QueryResult",
    "SearchResult",
    "TCMKnowledgeGraph",
    "get_default_ontology_manager",
]
