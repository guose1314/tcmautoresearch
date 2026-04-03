# src/common/cache.py
"""
缓存装饰器 — 基于 functools.lru_cache，增加可选 TTL 过期机制。

用法示例::

    @tcm_cache(maxsize=128, ttl=3600)
    def expensive_lookup(term: str) -> dict:
        ...
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Optional


def tcm_cache(
    maxsize: int = 128,
    ttl: Optional[int] = None,
) -> Callable:
    """
    带可选 TTL 的 LRU 缓存装饰器。

    Args:
        maxsize: 缓存最大条目数。
        ttl:     缓存生存时间（秒），None 表示永不过期。

    返回的函数额外拥有 ``cache_clear()`` 和 ``cache_info()`` 方法。
    """

    def decorator(func: Callable) -> Callable:
        if ttl is None:
            # 无 TTL：直接使用 lru_cache
            cached = functools.lru_cache(maxsize=maxsize)(func)

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return cached(*args, **kwargs)

            wrapper.cache_clear = cached.cache_clear  # type: ignore[attr-defined]
            wrapper.cache_info = cached.cache_info  # type: ignore[attr-defined]
            return wrapper

        # 有 TTL：自定义过期逻辑
        _cache: dict = {}
        _timestamps: dict = {}

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()

            # 检查缓存是否存在且未过期
            if key in _cache and (now - _timestamps[key]) < ttl:
                return _cache[key]

            # 执行并缓存
            result = func(*args, **kwargs)
            _cache[key] = result
            _timestamps[key] = now

            # 简单 LRU：超出 maxsize 时删除最老条目
            if len(_cache) > maxsize:
                oldest_key = min(_timestamps, key=_timestamps.get)  # type: ignore[arg-type]
                _cache.pop(oldest_key, None)
                _timestamps.pop(oldest_key, None)

            return result

        def cache_clear() -> None:
            _cache.clear()
            _timestamps.clear()

        def cache_info() -> dict:
            return {"size": len(_cache), "maxsize": maxsize, "ttl": ttl}

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator
