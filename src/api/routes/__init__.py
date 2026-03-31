"""Router exports for the Architecture 3.0 REST API."""

from src.api.routes.analysis import router as analysis_router
from src.api.routes.collection import router as collection_router
from src.api.routes.research import router as research_router
from src.api.routes.system import router as system_router

__all__ = [
    "analysis_router",
    "collection_router",
    "research_router",
    "system_router",
]