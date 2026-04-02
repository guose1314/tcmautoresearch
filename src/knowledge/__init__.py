"""src/knowledge — 知识检索层"""

from .embedding_service import (
    EmbeddingItem,
    EmbeddingService,
    SearchResult,
)
from .ontology_manager import OntologyManager, get_default_ontology_manager
from .tcm_knowledge_graph import (
    IKnowledgeGraph,
    KnowledgeGap,
    TCMKnowledgeGraph,
)

__all__ = [
    "EmbeddingItem",
    "EmbeddingService",
    "IKnowledgeGraph",
    "KnowledgeGap",
    "OntologyManager",
    "SearchResult",
    "TCMKnowledgeGraph",
    "get_default_ontology_manager",
]
