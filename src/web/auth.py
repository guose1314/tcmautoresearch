# -*- coding: utf-8 -*-
"""JWT 认证模块 — 令牌签发、验证与 FastAPI 依赖。"""

import logging
import os
import time
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger(__name__)

# FastAPI OAuth2 scheme — tokenUrl 指向登录端点（后续路由注册）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# ---- 配置读取 ----

_DEFAULT_ALGORITHM = "HS256"
_DEFAULT_EXPIRES = 3600  # 秒


def _load_jwt_config() -> Dict[str, Any]:
    """从 secrets.yml / config.yml / 环境变量加载 JWT 配置。"""
    secret_key = os.environ.get("JWT_SECRET_KEY")
    algorithm = os.environ.get("JWT_ALGORITHM", _DEFAULT_ALGORITHM)
    expires = int(os.environ.get("JWT_EXPIRES_SECONDS", _DEFAULT_EXPIRES))

    if not secret_key:
        try:
            from src.infrastructure.config_loader import load_settings

            settings = load_settings()
            sec = getattr(settings, "raw", {}).get("security", {})
            secret_key = sec.get("jwt_secret_key", "")
            algorithm = sec.get("jwt_algorithm", algorithm)
            expires = int(sec.get("jwt_expires_seconds", expires))
        except Exception:
            pass

    if not secret_key:
        # 从 secrets.yml 直接读取
        try:
            from pathlib import Path

            import yaml

            secrets_path = Path("secrets.yml")
            if secrets_path.exists():
                with open(secrets_path, "r", encoding="utf-8") as f:
                    secrets = yaml.safe_load(f) or {}
                sec = secrets.get("security", {})
                secret_key = sec.get("jwt_secret_key", "")
        except Exception:
            pass

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
    return jwt.encode(payload, cfg["secret_key"], algorithm=cfg["algorithm"])


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
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = verify_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("[auth] 无效令牌: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user_id": user_id, **payload}
