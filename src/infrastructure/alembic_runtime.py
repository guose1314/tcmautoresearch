"""Alembic runtime configuration helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Optional

from src.infrastructure.config_loader import load_settings

DEFAULT_ALEMBIC_SQLALCHEMY_URL = "sqlite:///./data/tcmautoresearch.db"
_ISOLATED_CONFIG_ENV_PREFIXES = ("TCM", "ALEMBIC")
_ISOLATED_CONFIG_ENV_KEYS = ("APP_ENV",)


@dataclass(frozen=True)
class AlembicDatabaseTarget:
    sqlalchemy_url: str
    source: str
    environment: Optional[str]
    config_path: Optional[str]
    root_path: Optional[str]
    loaded_files: tuple[str, ...]
    loaded_secret_files: tuple[str, ...]


def _normalize_optional_value(value: object) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_mapping(mapping: Mapping[str, object] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (mapping or {}).items():
        normalized_key = _normalize_optional_value(key)
        normalized_value = _normalize_optional_value(value)
        if normalized_key is None or normalized_value is None:
            continue
        normalized[normalized_key] = normalized_value
    return normalized


@contextmanager
def _temporary_environment(
    overrides: Mapping[str, str] | None,
    *,
    isolate_config_env: bool = False,
) -> Iterator[None]:
    if overrides is None and not isolate_config_env:
        yield
        return

    sentinel = object()
    previous_values: dict[str, object] = {}
    if isolate_config_env:
        for key in list(os.environ):
            normalized_key = str(key).strip().upper()
            if normalized_key in _ISOLATED_CONFIG_ENV_KEYS or normalized_key.startswith(_ISOLATED_CONFIG_ENV_PREFIXES):
                previous_values[key] = os.environ.get(key, sentinel)
                os.environ.pop(key, None)
    for key, value in overrides.items():
        if key not in previous_values:
            previous_values[key] = os.environ.get(key, sentinel)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, previous in previous_values.items():
            if previous is sentinel:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(previous)


def resolve_alembic_database_target(
    configured_sqlalchemy_url: str | None,
    *,
    x_arguments: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    default_root_path: str | Path | None = None,
) -> AlembicDatabaseTarget:
    x_args = _normalize_mapping(x_arguments)
    env_mapping = env or os.environ

    explicit_url = _normalize_optional_value(
        x_args.get("sqlalchemy_url")
        or x_args.get("url")
        or env_mapping.get("TCM_ALEMBIC_SQLALCHEMY_URL")
        or env_mapping.get("ALEMBIC_DATABASE_URL")
    )
    if explicit_url is not None:
        return AlembicDatabaseTarget(
            sqlalchemy_url=explicit_url,
            source="explicit_url",
            environment=None,
            config_path=None,
            root_path=None,
            loaded_files=(),
            loaded_secret_files=(),
        )

    config_path = _normalize_optional_value(
        x_args.get("config_path")
        or x_args.get("config")
        or env_mapping.get("TCM_ALEMBIC_CONFIG_PATH")
    )
    environment = _normalize_optional_value(
        x_args.get("environment")
        or x_args.get("env")
        or env_mapping.get("TCM_ALEMBIC_ENVIRONMENT")
        or env_mapping.get("TCM_ENV")
    )
    root_path = _normalize_optional_value(
        x_args.get("root_path") or env_mapping.get("TCM_ALEMBIC_ROOT_PATH")
    )
    ini_url = _normalize_optional_value(configured_sqlalchemy_url)

    if (
        ini_url is not None
        and ini_url != DEFAULT_ALEMBIC_SQLALCHEMY_URL
        and config_path is None
        and environment is None
        and root_path is None
    ):
        return AlembicDatabaseTarget(
            sqlalchemy_url=ini_url,
            source="alembic_ini",
            environment=None,
            config_path=None,
            root_path=None,
            loaded_files=(),
            loaded_secret_files=(),
        )

    sqlalchemy_url = DEFAULT_ALEMBIC_SQLALCHEMY_URL
    with _temporary_environment(
        env_mapping if env is not None else None,
        isolate_config_env=env is not None,
    ):
        settings = load_settings(
            root_path=root_path or default_root_path,
            config_path=config_path,
            environment=environment,
        )
        sqlalchemy_url = settings.database_url
    return AlembicDatabaseTarget(
        sqlalchemy_url=sqlalchemy_url,
        source="runtime_settings",
        environment=settings.environment,
        config_path=config_path,
        root_path=root_path,
        loaded_files=settings.loaded_files,
        loaded_secret_files=settings.loaded_secret_files,
    )