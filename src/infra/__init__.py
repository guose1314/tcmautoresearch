# src/infra/__init__.py
"""
基础设施层（Infrastructure）

提供与具体技术实现（文件、缓存、外部服务）相关的低层组件，
供上层业务模块以接口形式调用，避免业务代码直接依赖存储细节。
"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache_service import DiskCacheStore, LLMDiskCache, _DiskCache
    from .lexicon_service import LexiconService, get_lexicon
    from .llm_service import APILLMEngine, CachedLLMService, LLMService, get_llm_service, reset_llm_registry

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "DiskCacheStore": (".cache_service", "DiskCacheStore"),
    "LLMDiskCache": (".cache_service", "LLMDiskCache"),
    "_DiskCache": (".cache_service", "_DiskCache"),
    "LexiconService": (".lexicon_service", "LexiconService"),
    "get_lexicon": (".lexicon_service", "get_lexicon"),
    "LLMService": (".llm_service", "LLMService"),
    "APILLMEngine": (".llm_service", "APILLMEngine"),
    "CachedLLMService": (".llm_service", "CachedLLMService"),
    "get_llm_service": (".llm_service", "get_llm_service"),
    "reset_llm_registry": (".llm_service", "reset_llm_registry"),
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
