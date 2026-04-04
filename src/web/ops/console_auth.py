"""Console username/password authentication with short-lived session tokens."""

from __future__ import annotations

import hashlib
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from src.infrastructure.config_loader import AppSettings


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
            continue
        merged[key] = value
    return merged


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ConsoleUser:
    username: str
    principal: str
    password: str = ""
    password_sha256: str = ""
    disabled: bool = False


@dataclass(frozen=True)
class ConsoleSession:
    token: str
    username: str
    principal: str
    auth_source: str
    issued_at: str
    expires_at: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "principal": self.principal,
            "auth_source": self.auth_source,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


class ConsoleAuthService:
    """Holds console users and issues opaque session tokens."""

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._lock = threading.Lock()
        self._sessions: dict[str, ConsoleSession] = {}
        self._config = self._load_console_auth_config(settings)
        self._users = self._load_users(self._config.get("users"))
        self.session_ttl_seconds = self._resolve_session_ttl(self._config, settings)

    @property
    def supports_password_login(self) -> bool:
        return bool(self._users)

    @property
    def supports_api_key_login(self) -> bool:
        candidates = (
            self._settings.get_secret(
                "security.management_api_key",
                "security.access_control.management_api_key",
                "api.management_api_key",
                default="",
            ),
            self._settings.get("security.management_api_key", ""),
            self._settings.get("security.access_control.management_api_key", ""),
            self._settings.get("api.management_api_key", ""),
        )
        return any(str(value or "").strip() for value in candidates)

    @property
    def auth_mode(self) -> str:
        if self.supports_password_login:
            return "password"
        if self.supports_api_key_login:
            return "management_api_key"
        return "open"

    @property
    def auth_required(self) -> bool:
        return self.auth_mode != "open"

    def status_payload(self) -> dict[str, Any]:
        if self.supports_password_login:
            credential_label = "登录密码"
            credential_placeholder = "输入控制台登录密码"
        elif self.supports_api_key_login:
            credential_label = "管理 API Key"
            credential_placeholder = "输入管理 API Key"
        else:
            credential_label = "可选访问令牌"
            credential_placeholder = "开放模式下可留空"

        return {
            "auth_required": self.auth_required,
            "auth_mode": self.auth_mode,
            "token_label": "控制台会话令牌",
            "credential_label": credential_label,
            "credential_placeholder": credential_placeholder,
            "supports_password_login": self.supports_password_login,
            "supports_api_key_login": self.supports_api_key_login,
            "guest_allowed": not self.auth_required,
            "session_ttl_seconds": self.session_ttl_seconds,
        }

    def authenticate_password(self, username: str, password: str) -> ConsoleUser | None:
        normalized_username = str(username or "").strip().lower()
        presented_password = str(password or "")
        if not normalized_username or not presented_password:
            return None

        user = self._users.get(normalized_username)
        if user is None or user.disabled:
            return None
        if not self._verify_password(user, presented_password):
            return None
        return user

    def create_session(self, *, username: str, principal: str, auth_source: str) -> ConsoleSession:
        issued_at = _utc_now()
        expires_at = issued_at + timedelta(seconds=self.session_ttl_seconds)
        session = ConsoleSession(
            token=secrets.token_urlsafe(32),
            username=str(username or "").strip() or auth_source,
            principal=str(principal or "").strip() or "控制台用户",
            auth_source=str(auth_source or "session").strip() or "session",
            issued_at=_isoformat(issued_at),
            expires_at=_isoformat(expires_at),
        )
        with self._lock:
            self._prune_expired_sessions_locked(issued_at)
            self._sessions[session.token] = session
        return session

    def resolve_session(self, token: str) -> ConsoleSession | None:
        normalized_token = str(token or "").strip()
        if not normalized_token:
            return None
        with self._lock:
            now = _utc_now()
            self._prune_expired_sessions_locked(now)
            return self._sessions.get(normalized_token)

    def revoke_session(self, token: str) -> bool:
        normalized_token = str(token or "").strip()
        if not normalized_token:
            return False
        with self._lock:
            return self._sessions.pop(normalized_token, None) is not None

    def _verify_password(self, user: ConsoleUser, password: str) -> bool:
        if user.password_sha256:
            digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return secrets.compare_digest(digest, user.password_sha256)
        if user.password:
            return secrets.compare_digest(password, user.password)
        return False

    def _prune_expired_sessions_locked(self, now: datetime) -> None:
        expired_tokens = [
            token
            for token, session in self._sessions.items()
            if self._is_session_expired(session, now)
        ]
        for token in expired_tokens:
            self._sessions.pop(token, None)

    @staticmethod
    def _is_session_expired(session: ConsoleSession, now: datetime) -> bool:
        try:
            expires_at = datetime.fromisoformat(session.expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        return now >= expires_at

    @staticmethod
    def _resolve_session_ttl(config: Mapping[str, Any], settings: AppSettings) -> int:
        raw_ttl = config.get("session_ttl_seconds")
        if raw_ttl in (None, ""):
            raw_ttl = settings.get("security.access_control.session_timeout", 3600)
        try:
            resolved_ttl = int(raw_ttl)
        except (TypeError, ValueError):
            resolved_ttl = 3600
        return max(300, resolved_ttl)

    @staticmethod
    def _load_console_auth_config(settings: AppSettings) -> dict[str, Any]:
        config_section = settings.get_section("security.console_auth", "web_console.auth", default={})
        secret_section = settings.get_secret_section("security.console_auth", "web_console.auth", default={})
        return _deep_merge(config_section, secret_section)

    @staticmethod
    def _load_users(raw_users: Any) -> dict[str, ConsoleUser]:
        users: dict[str, ConsoleUser] = {}
        if isinstance(raw_users, Mapping):
            iterable = []
            for username, payload in raw_users.items():
                if isinstance(payload, Mapping):
                    iterable.append((username, payload))
                else:
                    iterable.append((username, {"password": payload}))
        elif isinstance(raw_users, list):
            iterable = []
            for payload in raw_users:
                if not isinstance(payload, Mapping):
                    continue
                username = str(payload.get("username") or "").strip()
                iterable.append((username, payload))
        else:
            iterable = []

        for fallback_username, payload in iterable:
            username = str(payload.get("username") or fallback_username or "").strip()
            if not username:
                continue
            user = ConsoleUser(
                username=username,
                principal=str(payload.get("display_name") or payload.get("principal") or username).strip() or username,
                password=str(payload.get("password") or ""),
                password_sha256=str(payload.get("password_sha256") or ""),
                disabled=bool(payload.get("disabled", False)),
            )
            if not user.password and not user.password_sha256:
                continue
            users[username.lower()] = user
        return users


__all__ = ["ConsoleAuthService", "ConsoleSession", "ConsoleUser"]
