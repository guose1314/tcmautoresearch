# src/common/__init__.py
"""
公共工具包 — 提供跨模块复用的基础设施。

包含：
- retry_utils: 统一重试装饰器
- http_client: 统一 HTTP 客户端
- exceptions: 统一异常体系
- cache: 缓存装饰器
"""

from src.common.cache import tcm_cache
from src.common.exceptions import (
    ConfigError,
    DataError,
    LLMError,
    ModuleError,
    NetworkError,
    PipelineError,
    TCMBaseError,
    ValidationError,
)
from src.common.http_client import HttpClient
from src.common.retry_utils import retry

__all__ = [
    "retry",
    "HttpClient",
    "tcm_cache",
    "TCMBaseError",
    "ConfigError",
    "DataError",
    "PipelineError",
    "ModuleError",
    "LLMError",
    "NetworkError",
    "ValidationError",
]
