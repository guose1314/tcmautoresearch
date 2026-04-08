"""Router exports for the Architecture 3.0 REST API."""

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "analysis_router": ("src.api.routes.analysis", "router"),
    "collection_router": ("src.api.routes.collection", "router"),
    "extraction_router": ("src.api.routes.extraction", "router"),
    "research_router": ("src.api.routes.research", "router"),
    "system_router": ("src.api.routes.system", "router"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")