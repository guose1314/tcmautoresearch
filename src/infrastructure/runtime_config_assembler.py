"""Shared runtime configuration assembly for CLI, API, and Web entrypoints."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from src.infrastructure.config_loader import AppSettings, load_settings


@dataclass(frozen=True)
class RuntimeAssembly:
    settings: AppSettings
    runtime_config: Dict[str, Any]
    orchestrator_config: Dict[str, Any]


def build_runtime_assembly(
    *,
    settings: Optional[AppSettings] = None,
    root_path: Optional[str | Path] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> RuntimeAssembly:
    resolved_settings = settings or load_settings(
        root_path=root_path,
        config_path=config_path,
        environment=environment,
    )
    runtime_config = resolved_settings.materialize_runtime_config()
    return RuntimeAssembly(
        settings=resolved_settings,
        runtime_config=runtime_config,
        orchestrator_config={"pipeline_config": deepcopy(runtime_config)},
    )


def build_runtime_config(
    *,
    settings: Optional[AppSettings] = None,
    root_path: Optional[str | Path] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    return build_runtime_assembly(
        settings=settings,
        root_path=root_path,
        config_path=config_path,
        environment=environment,
    ).runtime_config


def build_runtime_orchestrator_config(
    *,
    settings: Optional[AppSettings] = None,
    root_path: Optional[str | Path] = None,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    return build_runtime_assembly(
        settings=settings,
        root_path=root_path,
        config_path=config_path,
        environment=environment,
    ).orchestrator_config


__all__ = [
    "RuntimeAssembly",
    "build_runtime_assembly",
    "build_runtime_config",
    "build_runtime_orchestrator_config",
]