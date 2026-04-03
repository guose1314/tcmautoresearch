# -*- coding: utf-8 -*-
"""带 TTL 的缓存装饰器 — 基于 functools.lru_cache 扩展可选过期机制。"""

import functools
import time
from typing import Any, Callable, Optional


def tcm_cache(maxsize: int = 128, ttl: Optional[int] = None) -> Callable:
    """可参数化缓存装饰器。

    Parameters
    ----------
    maxsize : int
        LRU 缓存最大条目数，``None`` 表示无限。
    ttl : int | None
        缓存存活时间（秒）。为 ``None`` 时永不过期，等同于 ``lru_cache``。
    """

    def decorator(fn: Callable) -> Callable:
        if ttl is None:
            # 无 TTL，直接使用 lru_cache
            cached = functools.lru_cache(maxsize=maxsize)(fn)

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return cached(*args, **kwargs)

            wrapper.cache_clear = cached.cache_clear  # type: ignore[attr-defined]
            wrapper.cache_info = cached.cache_info  # type: ignore[attr-defined]
            return wrapper

        # 有 TTL：用 lru_cache + 时间窗口轮转实现过期
        _epoch = [time.time()]

        def _time_slot() -> int:
            """返回当前时间窗口编号，窗口切换时旧缓存自动被淘汰。"""
            return int((time.time() - _epoch[0]) // ttl)

        @functools.lru_cache(maxsize=maxsize)
        def _cached(_slot: int, *args: Any) -> Any:
            return fn(*args)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if kwargs:
                # lru_cache 不支持 kwargs，回退到直接调用
                return fn(*args, **kwargs)
            return _cached(_time_slot(), *args)

        def cache_clear() -> None:
            _cached.cache_clear()
            _epoch[0] = time.time()

        def cache_info():
            return _cached.cache_info()

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator
