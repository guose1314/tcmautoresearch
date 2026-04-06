# -*- coding: utf-8 -*-
"""JWT 认证模块 — 令牌签发、验证与 FastAPI 依赖。"""

import base64
import binascii
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import time
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

try:
    _pyjwt = import_module("jwt") if importlib.util.find_spec("jwt") else None
except Exception:
    _pyjwt = None

logger = logging.getLogger(__name__)


class _FallbackExpiredSignatureError(Exception):
    """Fallback: token signature is valid but already expired."""


class _FallbackInvalidTokenError(Exception):
    """Fallback: token is malformed, unsigned, or otherwise invalid."""


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


class _FallbackJwtModule:
    """PyJWT-compatible minimal implementation for HS256 only."""

    ExpiredSignatureError = _FallbackExpiredSignatureError
    InvalidTokenError = _FallbackInvalidTokenError

    @staticmethod
    def encode(payload: Dict[str, Any], key: str, algorithm: str = "HS256") -> str:
        if algorithm != "HS256":
            raise _FallbackInvalidTokenError("仅支持 HS256")

        header = {"alg": algorithm, "typ": "JWT"}
        header_part = _base64url_encode(
            json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        payload_part = _base64url_encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        signature_part = _base64url_encode(signature)
        return f"{header_part}.{payload_part}.{signature_part}"

    @staticmethod
    def decode(token: str, key: str, algorithms: Optional[list[str]] = None) -> Dict[str, Any]:
        if not isinstance(token, str):
            raise _FallbackInvalidTokenError("令牌格式错误")

        try:
            header_part, payload_part, signature_part = token.split(".")
        except ValueError as exc:
            raise _FallbackInvalidTokenError("令牌结构错误") from exc

        try:
            header_data = json.loads(_base64url_decode(header_part).decode("utf-8"))
            payload_data = json.loads(_base64url_decode(payload_part).decode("utf-8"))
            actual_signature = _base64url_decode(signature_part)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _FallbackInvalidTokenError("令牌内容损坏") from exc

        algorithm = str(header_data.get("alg") or "")
        if algorithms and algorithm not in algorithms:
            raise _FallbackInvalidTokenError("令牌算法不在允许列表")
        if algorithm != "HS256":
            raise _FallbackInvalidTokenError("仅支持 HS256")

        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected_signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise _FallbackInvalidTokenError("令牌签名校验失败")

        exp = payload_data.get("exp")
        if exp is not None:
            try:
                exp_value = float(exp)
            except (TypeError, ValueError) as exc:
                raise _FallbackInvalidTokenError("令牌 exp 声明无效") from exc
            if time.time() >= exp_value:
                raise _FallbackExpiredSignatureError("令牌已过期")

        return payload_data


jwt = _pyjwt or _FallbackJwtModule()
if _pyjwt is None:
    logger.warning("PyJWT 未安装，已启用内置最小 JWT 兜底实现（仅 HS256）。")

# FastAPI OAuth2 scheme — tokenUrl 指向登录端点（后续路由注册）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# ---- 配置读取 ----

_DEFAULT_ALGORITHM = "HS256"
_DEFAULT_EXPIRES = 3600  # 秒
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_jwt_config() -> Dict[str, Any]:
    """从 secrets.yml / config.yml / 环境变量加载 JWT 配置。"""
    secret_key = os.environ.get("JWT_SECRET_KEY")
    algorithm = os.environ.get("JWT_ALGORITHM", _DEFAULT_ALGORITHM)
    expires = int(os.environ.get("JWT_EXPIRES_SECONDS", _DEFAULT_EXPIRES))

    if not secret_key:
        try:
            from src.infrastructure.config_loader import load_settings

            settings = load_settings()
            if hasattr(settings, "get_secret"):
                secret_key = str(
                    settings.get_secret("security.jwt_secret_key", default=secret_key)
                    or secret_key
                )
            if hasattr(settings, "get"):
                algorithm = str(settings.get("security.jwt_algorithm", algorithm) or algorithm)
                expires = int(settings.get("security.jwt_expires_seconds", expires) or expires)
        except Exception:
            pass

    if not secret_key:
        # 从 secrets 文件直接读取（优先项目根目录，避免依赖当前工作目录）
        candidates = [
            _PROJECT_ROOT / "secrets.yml",
            _PROJECT_ROOT / "secrets.yaml",
            Path("secrets.yml"),
            Path("secrets.yaml"),
        ]
        seen: set[str] = set()
        for secrets_path in candidates:
            normalized = str(secrets_path.resolve(strict=False))
            if normalized in seen:
                continue
            seen.add(normalized)
            if not secrets_path.exists():
                continue
            try:
                yaml_module = import_module("yaml")
                secrets = yaml_module.safe_load(secrets_path.read_text(encoding="utf-8")) or {}
                sec = secrets.get("security", {}) if isinstance(secrets, dict) else {}
                if not isinstance(sec, dict):
                    continue
                secret_key = str(sec.get("jwt_secret_key", "") or "")
                algorithm = str(sec.get("jwt_algorithm", algorithm) or algorithm)
                expires = int(sec.get("jwt_expires_seconds", expires) or expires)
                if secret_key:
                    break
            except Exception:
                continue

    if not secret_key:
        raise RuntimeError(
            "JWT secret key 未配置。请在 secrets.yml 的 security.jwt_secret_key "
            "或环境变量 JWT_SECRET_KEY 中设置。"
        )

    return {
        "secret_key": secret_key,
        "algorithm": algorithm,
        "default_expires": expires,
    }


# ---- 令牌操作 ----


def create_access_token(
    user_id: str,
    expires_delta: int = 0,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """签发 JWT access token。

    Parameters
    ----------
    user_id : str
        用户唯一标识，写入 ``sub`` 声明。
    expires_delta : int
        过期时间（秒），为 0 时使用配置默认值。
    extra_claims : dict | None
        额外自定义声明。
    """
    cfg = _load_jwt_config()
    now = time.time()
    exp = now + (expires_delta or cfg["default_expires"])
    payload: Dict[str, Any] = {
        "sub": user_id,
        "iat": int(now),
        "exp": int(exp),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, cfg["secret_key"], algorithm=cfg["algorithm"])
    if isinstance(token, bytes):
        return token.decode("utf-8")
    return str(token)


def verify_token(token: str) -> Dict[str, Any]:
    """验证并解码 JWT。

    Returns
    -------
    dict
        解码后的 payload。

    Raises
    ------
    jwt.ExpiredSignatureError
        令牌已过期。
    jwt.InvalidTokenError
        令牌无效。
    """
    cfg = _load_jwt_config()
    return jwt.decode(token, cfg["secret_key"], algorithms=[cfg["algorithm"]])


# ---- FastAPI 依赖 ----


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """FastAPI 依赖：从请求中提取并验证 JWT，返回用户信息。"""
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = verify_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="令牌已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("[auth] 无效令牌: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="令牌缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user_id": user_id, **payload}
