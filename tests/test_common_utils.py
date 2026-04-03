# -*- coding: utf-8 -*-
"""
tests/test_common_utils.py
测试 @retry 装饰器、HttpClient（Mock 请求）、异常层次结构
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.common.exceptions import (
    ConfigError,
    DataError,
    LLMError,
    ModuleError,
    NetworkError,
    PipelineError,
    TCMBaseError,
    ValidationError,
)
from src.common.http_client import HttpClient
from src.common.retry_utils import retry

# ===================================================================
# 1. 异常层次结构
# ===================================================================

class TestExceptionHierarchy:
    """所有自定义异常均继承 TCMBaseError → Exception。"""

    @pytest.mark.parametrize("exc_cls", [
        ConfigError, DataError, PipelineError, ModuleError,
        LLMError, NetworkError, ValidationError,
    ])
    def test_subclass_of_tcm_base_error(self, exc_cls):
        assert issubclass(exc_cls, TCMBaseError)
        assert issubclass(exc_cls, Exception)

    def test_tcm_base_error_attributes(self):
        err = TCMBaseError("test msg", code="ERR_01", detail="some detail", context={"k": 1})
        assert str(err) == "test msg [ERR_01] some detail"
        assert err.code == "ERR_01"
        assert err.detail == "some detail"
        assert err.context == {"k": 1}

    def test_tcm_base_error_defaults(self):
        err = TCMBaseError()
        assert err.code == "UNKNOWN"
        assert err.detail == ""
        assert err.context == {}

    def test_specific_exception_default_message(self):
        assert str(ConfigError()).startswith("configuration error")
        assert str(DataError()).startswith("data error")
        assert str(NetworkError()).startswith("network error")

    def test_catch_specific_via_base(self):
        with pytest.raises(TCMBaseError):
            raise ValidationError("bad input", code="VAL_001")

    def test_exception_context_dict(self):
        err = PipelineError("fail", context={"step": 3, "module": "preprocess"})
        assert err.context["step"] == 3


# ===================================================================
# 2. @retry 装饰器
# ===================================================================

class TestRetryDecorator:
    """测试 fixed / linear / exponential 策略及成功/失败/重试场景。"""

    def test_success_no_retry(self):
        call_count = 0

        @retry(max_attempts=3, backoff_strategy="fixed", base_delay=0.01)
        def ok():
            nonlocal call_count
            call_count += 1
            return "done"

        assert ok() == "done"
        assert call_count == 1

    def test_fail_then_succeed(self):
        attempts = []

        @retry(max_attempts=3, backoff_strategy="fixed", base_delay=0.01)
        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ValueError("not yet")
            return "ok"

        assert flaky() == "ok"
        assert len(attempts) == 3

    def test_all_fail_raises(self):
        @retry(max_attempts=2, backoff_strategy="fixed", base_delay=0.01)
        def always_fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            always_fail()

    def test_only_catches_specified_exceptions(self):
        @retry(max_attempts=3, backoff_strategy="fixed", base_delay=0.01, exceptions=(ValueError,))
        def wrong_exc():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            wrong_exc()

    @pytest.mark.parametrize("strategy", ["fixed", "linear", "exponential"])
    def test_all_strategies_work(self, strategy):
        attempts = []

        @retry(max_attempts=2, backoff_strategy=strategy, base_delay=0.01)
        def fn():
            attempts.append(1)
            if len(attempts) < 2:
                raise ValueError("retry")
            return "done"

        assert fn() == "done"

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="unsupported"):
            @retry(backoff_strategy="invalid")
            def fn():
                pass

    @pytest.mark.asyncio
    async def test_async_retry_success(self):
        attempts = []

        @retry(max_attempts=3, backoff_strategy="fixed", base_delay=0.01)
        async def async_fn():
            attempts.append(1)
            if len(attempts) < 2:
                raise ValueError("retry")
            return "async_ok"

        result = await async_fn()
        assert result == "async_ok"
        assert len(attempts) == 2


# ===================================================================
# 3. HttpClient（Mock 网络请求）
# ===================================================================

class TestHttpClient:
    """使用 unittest.mock.patch 模拟 requests.Session。"""

    def test_default_headers(self):
        client = HttpClient()
        assert "User-Agent" in client._session.headers
        assert "TCMAutoResearch" in client._session.headers["User-Agent"]
        client.close()

    def test_custom_headers(self):
        client = HttpClient(headers={"X-Custom": "test"})
        assert client._session.headers["X-Custom"] == "test"
        client.close()

    def test_context_manager(self):
        with HttpClient() as client:
            assert isinstance(client, HttpClient)

    @patch.object(requests.Session, "request")
    def test_get_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"result": "ok"}'
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        with HttpClient(max_retries=1) as client:
            resp = client.get("https://example.com/api")
        assert resp.status_code == 200
        mock_request.assert_called_once()

    @patch.object(requests.Session, "request")
    def test_post_json(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.content = b'{"id": 1}'
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        with HttpClient(max_retries=1) as client:
            resp = client.post("https://example.com/api", json={"name": "test"})
        assert resp.status_code == 201

    @patch.object(requests.Session, "request")
    def test_get_json(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"key": "value"}
        mock_resp.content = b'{"key":"value"}'
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        with HttpClient(max_retries=1) as client:
            data = client.get_json("https://example.com/api")
        assert data == {"key": "value"}

    @patch.object(requests.Session, "request")
    def test_get_text(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.text = "hello"
        mock_resp.content = b"hello"
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        with HttpClient(max_retries=1) as client:
            text = client.get_text("https://example.com/api")
        assert text == "hello"

    @patch.object(requests.Session, "request")
    def test_retry_on_failure(self, mock_request):
        mock_request.side_effect = [
            requests.ConnectionError("fail"),
            requests.ConnectionError("fail again"),
        ]

        with HttpClient(max_retries=2) as client:
            with pytest.raises(requests.ConnectionError):
                client.get("https://example.com/api")
        assert mock_request.call_count == 2

    def test_custom_timeout(self):
        client = HttpClient(timeout=5.0)
        assert client.timeout == 5.0
        client.close()
