"""src/knowledge — 知识检索层"""

from .embedding_service import (
    EmbeddingItem,
    EmbeddingService,
    SearchResult,
)
from .ontology_manager import OntologyManager, get_default_ontology_manager

__all__ = [
    "EmbeddingItem",
    "EmbeddingService",
    "OntologyManager",
    "SearchResult",
    "get_default_ontology_manager",
]
