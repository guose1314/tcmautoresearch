# src/common/http_client.py
"""封装 ``requests.Session`` 的 HTTP 客户端。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

from src.common.exceptions import TCMHTTPError, TCMTimeoutError

logger = logging.getLogger(__name__)


class HttpClient:
    """轻量封装 ``requests.Session``，统一超时与错误处理。"""

    def __init__(
        self,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        if headers:
            self._session.headers.update(headers)

    # ------------------------------------------------------------------
    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self._request("POST", url, **kwargs)

    # ------------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        try:
            resp = self._session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout as exc:
            raise TCMTimeoutError(f"请求超时: {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise TCMHTTPError(f"HTTP 请求失败: {url} — {exc}") from exc

    def close(self) -> None:
        self._session.close()
