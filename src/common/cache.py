# src/common/cache.py
"""LRU + TTL 缓存装饰器。"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable


def tcm_cache(maxsize: int = 128, ttl: float = 300.0) -> Callable:
    """
    LRU + TTL 缓存装饰器。

    Args:
        maxsize: 最大缓存条目数。
        ttl: 生存时间（秒），0 表示无过期。
    """

    def decorator(func: Callable) -> Callable:
        cache: dict[Any, tuple[Any, float]] = {}
        hits = 0
        misses = 0

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal hits, misses
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()

            if key in cache:
                value, ts = cache[key]
                if ttl <= 0 or (now - ts) < ttl:
                    hits += 1
                    return value
                else:
                    del cache[key]

            misses += 1
            result = func(*args, **kwargs)
            if len(cache) >= maxsize:
                # 移除最旧条目
                oldest_key = next(iter(cache))
                del cache[oldest_key]
            cache[key] = (result, now)
            return result

        wrapper.cache_info = lambda: {"hits": hits, "misses": misses, "size": len(cache)}  # type: ignore[attr-defined]
        wrapper.cache_clear = lambda: cache.clear()  # type: ignore[attr-defined]
        return wrapper

    return decorator
