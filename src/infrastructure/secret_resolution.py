"""Helpers for resolving secret values from config sections."""

from __future__ import annotations

import os
from typing import Any, Mapping


def resolve_config_password(
    config: Mapping[str, Any] | None,
    *,
    password_key: str = "password",
    password_env_key: str = "password_env",
    default_env_name: str = "",
) -> str:
    """Resolve a password from config, preferring explicit values over env indirection.

    If a non-empty ``password`` is provided in the config mapping, it wins.
    Otherwise, the function falls back to ``password_env`` and reads that
    environment variable when available.
    """

    payload = config or {}
    explicit_password = payload.get(password_key)
    if explicit_password is not None:
        explicit_text = str(explicit_password).strip()
        if explicit_text:
            return explicit_text

    env_name = str(payload.get(password_env_key, default_env_name) or "").strip()
    if not env_name:
        return ""
    return os.environ.get(env_name, "")


__all__ = ["resolve_config_password"]