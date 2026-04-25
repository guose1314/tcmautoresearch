# -*- coding: utf-8 -*-
"""统一 HTTP 客户端 — 封装 requests.Session，内置重试、超时与日志。"""

import logging
from typing import Any, Dict, Optional, Union

import requests

from src.common.retry_utils import retry

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 20.0
_DEFAULT_USER_AGENT = (
    "TCMAutoResearch/1.0 (Academic Research Bot; +https://github.com/guose1314/tcmautoresearch)"
)


class HttpClient:
    """封装 ``requests.Session`` 的统一 HTTP 客户端。

    Parameters
    ----------
    timeout : float
        默认请求超时（秒）。
    max_retries : int
        失败自动重试次数。
    user_agent : str | None
        自定义 User-Agent，为 ``None`` 时使用默认值。
    headers : dict | None
        额外默认请求头。
    """

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = 3,
        user_agent: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=200,
            pool_maxsize=200,
            max_retries=max_retries
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._session.headers.update(
            {"User-Agent": user_agent or _DEFAULT_USER_AGENT}
        )
        if headers:
            self._session.headers.update(headers)

    # ------------------------------------------------------------------
    # 核心请求方法
    # ------------------------------------------------------------------

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> requests.Response:
        return self._request("GET", url, params=params, timeout=timeout, **kwargs)

    def post(
        self,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> requests.Response:
        return self._request("POST", url, data=data, json=json, timeout=timeout, **kwargs)

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        """GET 请求并返回解析后的 JSON。"""
        resp = self.get(url, params=params, **kwargs)
        return resp.json()

    def get_text(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
        """GET 请求并返回响应文本。"""
        resp = self.get(url, params=params, **kwargs)
        return resp.text

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", None) or self.timeout

        @retry(
            max_attempts=self.max_retries,
            backoff_strategy="exponential",
            base_delay=0.5,
            max_delay=30.0,
            exceptions=(requests.RequestException,),
        )
        def _do() -> requests.Response:
            logger.debug("[http] %s %s", method, url)
            resp = self._session.request(method, url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            logger.debug(
                "[http] %s %s → %d (%d bytes)",
                method,
                url,
                resp.status_code,
                len(resp.content),
            )
            return resp

        return _do()

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
