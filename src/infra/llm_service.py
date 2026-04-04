# src/infra/llm_service.py
"""
LLMService — 向后兼容层

实现已迁移至 ``src.infrastructure.llm_service``。
此模块重新导出全部公开符号，确保现有导入无需修改。
"""
import warnings as _warnings

_warnings.warn(
    "src.infra.llm_service 已迁移至 src.infrastructure.llm_service，请更新导入路径。",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.llm_service import (  # noqa: F401, E402
    APILLMEngine,
    CachedLLMService,
    LLMService,
    _DiskCache,
)

__all__ = ["LLMService", "APILLMEngine", "CachedLLMService", "_DiskCache"]
