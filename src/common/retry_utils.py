# src/common/retry_utils.py
"""可重试装饰器，支持固定 / 指数 / 线性退避。支持同步和异步函数。"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional, Sequence, Type

logger = logging.getLogger(__name__)

_DEFAULT_EXCEPTIONS: tuple[Type[Exception], ...] = (Exception,)

_VALID_STRATEGIES = {"fixed", "linear", "exponential"}


def retry(
    max_retries: Optional[int] = None,
    backoff: str = "exponential",
    base_delay: float = 1.0,
    exceptions: Sequence[Type[Exception]] = _DEFAULT_EXCEPTIONS,
    # Backward-compatible aliases
    max_attempts: Optional[int] = None,
    backoff_strategy: Optional[str] = None,
    max_delay: Optional[float] = None,
) -> Callable:
    """
    重试装饰器，支持同步与异步函数。

    Args:
        max_retries: 最大重试次数。
        backoff: 退避策略 — "fixed" / "exponential" / "linear"。
        base_delay: 基础延迟（秒）。
        exceptions: 需要捕获并重试的异常类型。
        max_attempts: max_retries 的别名（向后兼容）。
        backoff_strategy: backoff 的别名（向后兼容）。
        max_delay: 最大单次延迟上限（秒），可选。
    """
    # Resolve aliases
    _max_retries: int = (
        max_retries if max_retries is not None
        else (max_attempts if max_attempts is not None else 3)
    )
    _backoff: str = backoff_strategy if backoff_strategy is not None else backoff

    if _backoff not in _VALID_STRATEGIES:
        raise ValueError(
            f"unsupported backoff strategy '{_backoff}'. "
            f"Choose from: {sorted(_VALID_STRATEGIES)}"
        )

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Exception | None = None
                for attempt in range(_max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except tuple(exceptions) as exc:
                        last_exc = exc
                        if attempt < _max_retries:
                            delay = _compute_delay(_backoff, base_delay, attempt)
                            if max_delay is not None:
                                delay = min(delay, max_delay)
                            logger.warning(
                                "retry %d/%d for %s (delay=%.2fs): %s",
                                attempt + 1,
                                _max_retries,
                                func.__qualname__,
                                delay,
                                exc,
                            )
                            await asyncio.sleep(delay)
                raise last_exc  # type: ignore[misc]

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Exception | None = None
                for attempt in range(_max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except tuple(exceptions) as exc:
                        last_exc = exc
                        if attempt < _max_retries:
                            delay = _compute_delay(_backoff, base_delay, attempt)
                            if max_delay is not None:
                                delay = min(delay, max_delay)
                            logger.warning(
                                "retry %d/%d for %s (delay=%.2fs): %s",
                                attempt + 1,
                                _max_retries,
                                func.__qualname__,
                                delay,
                                exc,
                            )
                            time.sleep(delay)
                raise last_exc  # type: ignore[misc]

            return sync_wrapper

    return decorator


def _compute_delay(strategy: str, base: float, attempt: int) -> float:
    if strategy == "exponential":
        return base * (2**attempt)
    if strategy == "linear":
        return base * (attempt + 1)
    return base  # fixed
