# -*- coding: utf-8 -*-
"""
tests/test_web_auth.py
测试 JWT 令牌创建、验证与过期处理。
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

try:
    import jwt as pyjwt
except ModuleNotFoundError:
    from src.web import auth as _web_auth

    pyjwt = _web_auth.jwt

# 使用固定密钥避免依赖 secrets.yml
_TEST_JWT_CONFIG = {
    "secret_key": "test-secret-key-for-unit-tests-only",
    "algorithm": "HS256",
    "default_expires": 3600,
}


@pytest.fixture(autouse=True)
def mock_jwt_config():
    """所有测试统一使用测试密钥，不读取 secrets.yml。"""
    with patch("src.web.auth._load_jwt_config", return_value=_TEST_JWT_CONFIG):
        yield


# ===================================================================
# 令牌签发
# ===================================================================

class TestCreateAccessToken:
    def test_create_token_returns_string(self):
        from src.web.auth import create_access_token
        token = create_access_token("user_001")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_sub_claim(self):
        from src.web.auth import create_access_token, verify_token
        token = create_access_token("admin")
        payload = verify_token(token)
        assert payload["sub"] == "admin"

    def test_token_contains_iat_and_exp(self):
        from src.web.auth import create_access_token, verify_token
        token = create_access_token("u1")
        payload = verify_token(token)
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_custom_expires_delta(self):
        from src.web.auth import create_access_token, verify_token
        token = create_access_token("u1", expires_delta=60)
        payload = verify_token(token)
        # exp - iat 应接近 60 秒
        assert 55 <= (payload["exp"] - payload["iat"]) <= 65

    def test_extra_claims(self):
        from src.web.auth import create_access_token, verify_token
        token = create_access_token("u1", extra_claims={"role": "researcher", "level": 3})
        payload = verify_token(token)
        assert payload["role"] == "researcher"
        assert payload["level"] == 3


# ===================================================================
# 令牌验证
# ===================================================================

class TestVerifyToken:
    def test_valid_token(self):
        from src.web.auth import create_access_token, verify_token
        token = create_access_token("test_user")
        payload = verify_token(token)
        assert payload["sub"] == "test_user"

    def test_expired_token_raises(self):
        from src.web.auth import verify_token
        # 手动创建一个已过期的 token
        expired_payload = {
            "sub": "expired_user",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
        token = pyjwt.encode(
            expired_payload,
            _TEST_JWT_CONFIG["secret_key"],
            algorithm=_TEST_JWT_CONFIG["algorithm"],
        )
        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_token(token)

    def test_invalid_signature_raises(self):
        from src.web.auth import verify_token
        payload = {"sub": "u1", "iat": int(time.time()), "exp": int(time.time()) + 3600}
        token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token(token)

    def test_malformed_token_raises(self):
        from src.web.auth import verify_token
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token("not.a.valid.jwt")


# ===================================================================
# FastAPI 依赖 get_current_user
# ===================================================================

class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user_dict(self):
        from src.web.auth import create_access_token, get_current_user
        token = create_access_token("researcher_01")
        user = await get_current_user(token=token)
        assert user["user_id"] == "researcher_01"
        assert "sub" in user
        assert "exp" in user

    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self):
        from fastapi import HTTPException

        from src.web.auth import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        from fastapi import HTTPException

        from src.web.auth import get_current_user
        expired_payload = {
            "sub": "u1",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
        token = pyjwt.encode(
            expired_payload,
            _TEST_JWT_CONFIG["secret_key"],
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token)
        assert exc_info.value.status_code == 401
        assert "过期" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_token_without_sub_raises_401(self):
        from fastapi import HTTPException

        from src.web.auth import get_current_user
        payload = {"iat": int(time.time()), "exp": int(time.time()) + 3600}
        token = pyjwt.encode(
            payload,
            _TEST_JWT_CONFIG["secret_key"],
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token=token)
        assert exc_info.value.status_code == 401
