# src/common — 通用工具包
"""
提供项目范围内的共享工具：

- exceptions: TCMBaseError 异常层次结构
- retry_utils: @retry 重试装饰器
- http_client: HttpClient（requests.Session 封装）
- cache: @tcm_cache（LRU + TTL）
"""

from src.common.exceptions import (
    TCMBaseError,
    TCMConfigError,
    TCMDataError,
    TCMHTTPError,
    TCMModuleError,
    TCMParseError,
    TCMTimeoutError,
    TCMValidationError,
)
from src.common.retry_utils import retry
from src.common.http_client import HttpClient
from src.common.cache import tcm_cache

__all__ = [
    "TCMBaseError",
    "TCMConfigError",
    "TCMDataError",
    "TCMHTTPError",
    "TCMModuleError",
    "TCMParseError",
    "TCMTimeoutError",
    "TCMValidationError",
    "retry",
    "HttpClient",
    "tcm_cache",
]
