# src/common/retry_utils.py
"""可重试装饰器，支持固定 / 指数 / 线性退避。"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Sequence, Type

logger = logging.getLogger(__name__)

_DEFAULT_EXCEPTIONS: tuple[Type[Exception], ...] = (Exception,)


def retry(
    max_retries: int = 3,
    backoff: str = "exponential",
    base_delay: float = 1.0,
    exceptions: Sequence[Type[Exception]] = _DEFAULT_EXCEPTIONS,
) -> Callable:
    """
    重试装饰器。

    Args:
        max_retries: 最大重试次数。
        backoff: 退避策略 — ``"fixed"`` / ``"exponential"`` / ``"linear"``。
        base_delay: 基础延迟（秒）。
        exceptions: 需要捕获并重试的异常类型。
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except tuple(exceptions) as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = _compute_delay(backoff, base_delay, attempt)
                        logger.warning(
                            "retry %d/%d for %s (delay=%.2fs): %s",
                            attempt + 1,
                            max_retries,
                            func.__qualname__,
                            delay,
                            exc,
                        )
                        time.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def _compute_delay(strategy: str, base: float, attempt: int) -> float:
    if strategy == "exponential":
        return base * (2**attempt)
    if strategy == "linear":
        return base * (attempt + 1)
    return base  # fixed
