# src/infra/__init__.py
"""
基础设施层（Infrastructure） — 向后兼容层

本包已迁移至 ``src.infrastructure``。此处保留重新导出，
确保现有 ``from src.infra import …`` 导入语句继续正常工作。
"""
import warnings as _warnings

_warnings.warn(
    "src.infra 已迁移至 src.infrastructure，请更新导入路径。",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.cache_service import DiskCacheStore, LLMDiskCache, _DiskCache
from src.infrastructure.config_manager import ConfigManager
from src.infrastructure.event_bus import EventBus
from src.infrastructure.lexicon_service import LexiconService, get_lexicon
from src.infrastructure.llm_service import APILLMEngine, CachedLLMService, LLMService

__all__ = [
    "APILLMEngine",
    "CachedLLMService",
    "ConfigManager",
    "DiskCacheStore",
    "EventBus",
    "LLMDiskCache",
    "LLMService",
    "LexiconService",
    "_DiskCache",
    "get_lexicon",
]
