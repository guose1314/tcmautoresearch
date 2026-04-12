"""Cycle 入口运行时配置装配。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from src.infrastructure.runtime_config_assembler import build_runtime_config


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
