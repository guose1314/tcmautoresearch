# -*- coding: utf-8 -*-
"""统一重试工具 — 提供 @retry 装饰器，支持 fixed / linear / exponential 退避策略。"""

import functools
import logging
import random
import time
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    backoff_strategy: str = "exponential",
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable:
    """可参数化重试装饰器。

    Parameters
    ----------
    max_attempts : int
        最大尝试次数（含首次调用）。
    backoff_strategy : str
        退避策略，可选 ``"fixed"`` / ``"linear"`` / ``"exponential"``。
    base_delay : float
        基础延迟（秒）。
    max_delay : float
        单次延迟上限（秒）。
    exceptions : tuple
        需要捕获并重试的异常类型元组。
    """

    if backoff_strategy not in ("fixed", "linear", "exponential"):
        raise ValueError(
            f"unsupported backoff_strategy: {backoff_strategy!r}, "
            "choose from 'fixed', 'linear', 'exponential'"
        )

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(
                            "[retry] %s failed after %d attempts: %s",
                            fn.__qualname__,
                            max_attempts,
                            exc,
                        )
                        raise
                    delay = _calc_delay(attempt, backoff_strategy, base_delay, max_delay)
                    logger.warning(
                        "[retry] %s attempt %d/%d failed (%s), retrying in %.2fs …",
                        fn.__qualname__,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
            # unreachable but keeps type checkers happy
            raise last_exc  # type: ignore[misc]

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            import asyncio

            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(
                            "[retry] %s failed after %d attempts: %s",
                            fn.__qualname__,
                            max_attempts,
                            exc,
                        )
                        raise
                    delay = _calc_delay(attempt, backoff_strategy, base_delay, max_delay)
                    logger.warning(
                        "[retry] %s attempt %d/%d failed (%s), retrying in %.2fs …",
                        fn.__qualname__,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        import asyncio

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return wrapper

    return decorator


def _calc_delay(
    attempt: int,
    strategy: str,
    base_delay: float,
    max_delay: float,
) -> float:
    """根据策略计算本次重试延迟（含 ±25% 抖动）。"""
    if strategy == "fixed":
        raw = base_delay
    elif strategy == "linear":
        raw = base_delay * attempt
    else:  # exponential
        raw = base_delay * (2 ** (attempt - 1))
    clamped = min(raw, max_delay)
    # 添加抖动避免 thundering-herd
    jitter = clamped * random.uniform(-0.25, 0.25)  # noqa: S311
    return max(0, clamped + jitter)
