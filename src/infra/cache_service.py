# src/infra/cache_service.py
"""
DiskCacheStore — 向后兼容层

实现已迁移至 ``src.infrastructure.cache_service``。
此模块重新导出全部公开符号，确保现有导入无需修改。
"""
import warnings as _warnings

_warnings.warn(
    "src.infra.cache_service 已迁移至 src.infrastructure.cache_service，请更新导入路径。",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.cache_service import (  # noqa: F401, E402
    DiskCacheStore,
    LLMDiskCache,
    _DiskCache,
)

__all__ = ["DiskCacheStore", "LLMDiskCache", "_DiskCache"]
