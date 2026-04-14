"""Cycle 入口运行时配置装配。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from src.infrastructure.runtime_config_assembler import (
    RuntimeAssembly,
    build_runtime_assembly,
    build_runtime_config,
)


def build_cycle_runtime_config(
    *,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """解析并物化 cycle 入口运行时配置。"""
    return build_runtime_config(
        config_path=config_path,
        environment=environment,
    )


def build_cycle_runtime_assembly(
    *,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> RuntimeAssembly:
    """解析 cycle/research 入口的完整运行时装配。"""
    return build_runtime_assembly(
        config_path=config_path,
        environment=environment,
        entrypoint="demo",
    )


def build_cycle_orchestrator_config(
    *,
    config_path: Optional[str | Path] = None,
    environment: Optional[str] = None,
) -> Dict[str, Any]:
    """返回 cycle/research 入口使用的 shared runtime orchestrator 配置。"""
    return dict(
        build_cycle_runtime_assembly(
            config_path=config_path,
            environment=environment,
        ).orchestrator_config
    )
