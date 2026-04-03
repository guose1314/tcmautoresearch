# src/infra/__init__.py
"""
基础设施层（Infrastructure）

提供与具体技术实现（文件、缓存、外部服务）相关的低层组件，
供上层业务模块以接口形式调用，避免业务代码直接依赖存储细节。
"""
from .cache_service import DiskCacheStore, LLMDiskCache, _DiskCache
from .lexicon_service import LexiconService, get_lexicon
from .llm_service import APILLMEngine, CachedLLMService, LLMService

__all__ = [
    "DiskCacheStore",
    "LLMDiskCache",
    "_DiskCache",
    "LexiconService",
    "get_lexicon",
    "LLMService",
    "APILLMEngine",
    "CachedLLMService",
]
