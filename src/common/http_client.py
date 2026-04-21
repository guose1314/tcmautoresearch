# src/common/http_client.py
"""封装 ``requests.Session`` 的 HTTP 客户端，支持超时、重试与统一错误处理。"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

from src.common.exceptions import TCMHTTPError, TCMTimeoutError

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = "TCMAutoResearch/1.0"


class HttpClient:
    """轻量封装 ``requests.Session``，统一超时与错误处理。

    Args:
        timeout: 请求超时秒数。
        headers: 附加请求头。
        max_retries: 最大尝试次数（含首次调用）。0 或 1 表示不重试。
        user_agent: 自定义 User-Agent；默认为 ``TCMAutoResearch/1.0``。
    """

    def __init__(
        self,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 1,
        user_agent: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self._max_retries = max(1, max_retries)  # 至少尝试一次
        self._session = requests.Session()
        # 默认 User-Agent
        self._session.headers["User-Agent"] = user_agent or _DEFAULT_USER_AGENT
        if headers:
            self._session.headers.update(headers)

    # ------------------------------------------------------------------
    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """发起 GET 请求。"""
        kwargs.setdefault("timeout", self.timeout)
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """发起 POST 请求。"""
        kwargs.setdefault("timeout", self.timeout)
        return self._request("POST", url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        """发起 GET 请求并将响应体解析为 JSON 返回。"""
        resp = self.get(url, **kwargs)
        return resp.json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        """发起 GET 请求并将响应体作为文本返回。"""
        resp = self.get(url, **kwargs)
        return resp.text

    # ------------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """内部重试循环。共最多尝试 _max_retries 次。

        连接错误（ConnectionError）和超时在最后一次失败时穿透原始异常；
        HTTP 错误（HTTPError）则包装为 TCMHTTPError。
        """
        last_exc: Exception | None = None
        is_last = False
        for attempt in range(self._max_retries):
            is_last = attempt == self._max_retries - 1
            try:
                resp = self._session.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                if is_last:
                    raise TCMTimeoutError(f"请求超时: {url}") from exc
                logger.warning("请求超时（第 %d 次），重试: %s", attempt + 1, url)
                time.sleep(0.5 * (attempt + 1))
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                if is_last:
                    raise  # 穿透原始 ConnectionError，便于测试和调用方处理
                logger.warning("连接错误（第 %d 次），重试: %s — %s", attempt + 1, url, exc)
                time.sleep(0.5 * (attempt + 1))
            except requests.exceptions.HTTPError as exc:
                raise TCMHTTPError(f"HTTP 错误: {url} — {exc}") from exc
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                if is_last:
                    raise TCMHTTPError(f"HTTP 请求失败: {url} — {exc}") from exc
                logger.warning("请求失败（第 %d 次），重试: %s — %s", attempt + 1, url, exc)
                time.sleep(0.5 * (attempt + 1))
        # 不应到达这里
        raise TCMHTTPError(f"HTTP 请求失败（已耗尽重试）: {url}")  # pragma: no cover

    def close(self) -> None:
        """关闭底层 Session。"""
        self._session.close()

    # 上下文管理器支持
    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
