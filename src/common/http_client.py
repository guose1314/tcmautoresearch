# src/common/http_client.py
"""
统一 HTTP 客户端 — 封装 requests.Session，内置重试、超时、日志。

用法示例::

    client = HttpClient(timeout=20, retry_count=3)
    data = client.get_json("https://api.example.com/data", params={"q": "中药"})
    text = client.get_text("https://api.example.com/page")
    client.close()
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

from src.common.exceptions import NetworkError
from src.common.retry_utils import retry as retry_decorator

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = (
    "TCM-AutoResearch/2.0 (https://github.com/tcmautoresearch)"
)


class HttpClient:
    """统一 HTTP 客户端，内置重试与限速。"""

    def __init__(
        self,
        timeout: float = 20.0,
        retry_count: int = 3,
        backoff_strategy: str = "exponential",
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        request_interval: float = 0.0,
        user_agent: str = _DEFAULT_USER_AGENT,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.timeout = timeout
        self.retry_count = retry_count
        self.backoff_strategy = backoff_strategy
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.request_interval = request_interval

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if headers:
            self.session.headers.update(headers)

    def close(self) -> None:
        """关闭底层 session。"""
        self.session.close()

    # ------------------------------------------------------------------
    # 基础请求
    # ------------------------------------------------------------------

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """
        发送 GET 请求（带重试）。

        Raises:
            NetworkError: 所有重试耗尽后抛出。
        """
        return self._request("GET", url, params=params, timeout=timeout, **kwargs)

    def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """
        发送 POST 请求（带重试）。

        Raises:
            NetworkError: 所有重试耗尽后抛出。
        """
        return self._request(
            "POST", url, data=data, json=json, timeout=timeout, **kwargs
        )

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """GET 并返回 JSON dict。"""
        resp = self.get(url, params=params, timeout=timeout)
        return resp.json()

    def get_text(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """GET 并返回响应文本。"""
        resp = self.get(url, params=params, timeout=timeout)
        return resp.text

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """发送请求，带重试和限速。"""
        timeout = kwargs.pop("timeout", None) or self.timeout
        last_exc: Optional[Exception] = None

        for attempt in range(self.retry_count + 1):
            try:
                # Use method-specific calls (get/post) to maintain mock compatibility
                method_fn = getattr(self.session, method.lower(), self.session.request)
                if method_fn is self.session.request:
                    response = self.session.request(
                        method, url, timeout=timeout, **kwargs
                    )
                else:
                    response = method_fn(url, timeout=timeout, **kwargs)
                response.raise_for_status()
                if self.request_interval > 0:
                    time.sleep(self.request_interval)
                return response
            except Exception as exc:
                last_exc = exc
                if attempt < self.retry_count:
                    from src.common.retry_utils import _compute_delay

                    delay = _compute_delay(
                        self.backoff_strategy, attempt, self.base_delay, self.max_delay
                    )
                    logger.warning(
                        "HTTP %s %s 失败 (第 %d/%d 次), 等待 %.2fs: %s",
                        method,
                        url,
                        attempt + 1,
                        self.retry_count + 1,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "HTTP %s %s 最终失败 (%d 次): %s",
                        method,
                        url,
                        self.retry_count + 1,
                        exc,
                    )

        raise NetworkError(
            f"请求失败: {method} {url}",
            detail=str(last_exc),
            context={"method": method, "url": url},
        )
