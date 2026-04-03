# src/common/retry_utils.py
"""
统一重试工具 — 为网络请求、API 调用等提供可配置的重试装饰器。

支持策略：
- fixed:       固定等待时间
- linear:      线性递增 base_delay * (attempt + 1)
- exponential: 指数退避 base_delay * 2^attempt（默认）

用法示例::

    @retry(max_attempts=3, backoff_strategy="exponential", base_delay=0.5)
    def fetch_data(url):
        return requests.get(url).json()
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


def _compute_delay(
    strategy: str,
    attempt: int,
    base_delay: float,
    max_delay: float,
) -> float:
    """根据策略计算当前重试等待时间（秒）。"""
    if strategy == "fixed":
        delay = base_delay
    elif strategy == "linear":
        delay = base_delay * (attempt + 1)
    else:  # exponential
        delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


def retry(
    max_attempts: int = 3,
    backoff_strategy: str = "exponential",
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[..., Any]] = None,
) -> Callable:
    """
    重试装饰器。

    Args:
        max_attempts:    最大尝试次数（含首次）。
        backoff_strategy: 退避策略 ("fixed" | "linear" | "exponential")。
        base_delay:      基础延迟秒数。
        max_delay:       最大延迟秒数。
        exceptions:      需要捕获并重试的异常类型元组。
        on_retry:        每次重试前调用的回调 fn(attempt, exception)。

    Returns:
        装饰后的函数。
    """

    if backoff_strategy not in ("fixed", "linear", "exponential"):
        raise ValueError(f"不支持的退避策略: {backoff_strategy}")

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[BaseException] = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        delay = _compute_delay(
                            backoff_strategy, attempt, base_delay, max_delay
                        )
                        logger.warning(
                            "重试 %s 第 %d/%d 次, 等待 %.2fs, 错误: %s",
                            func.__name__,
                            attempt + 1,
                            max_attempts,
                            delay,
                            exc,
                        )
                        if on_retry is not None:
                            on_retry(attempt, exc)
                        time.sleep(delay)
                    else:
                        logger.error(
                            "重试 %s 耗尽 (%d 次), 最终错误: %s",
                            func.__name__,
                            max_attempts,
                            exc,
                        )
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
