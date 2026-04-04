"""src/knowledge — 知识检索层"""

from .embedding_service import (
    EmbeddingItem,
    EmbeddingService,
    SearchResult,
)
from .kg_service import (
    EntityDTO,
    KGQueryResult,
    KnowledgeGraphService,
    RelationDTO,
    SubGraphDTO,
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
    "EntityDTO",
    "IKnowledgeGraph",
    "KGQueryResult",
    "KnowledgeGap",
    "KnowledgeGraphService",
    "OntologyManager",
    "RelationDTO",
    "SearchResult",
    "SubGraphDTO",
    "TCMKnowledgeGraph",
    "get_default_ontology_manager",
]
