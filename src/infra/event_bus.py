# src/infra/event_bus.py
"""
EventBus — 向后兼容层

实现已迁移至 ``src.infrastructure.event_bus``。
此模块重新导出全部公开符号，确保现有导入无需修改。
"""
import warnings as _warnings

_warnings.warn(
    "src.infra.event_bus 已迁移至 src.infrastructure.event_bus，请更新导入路径。",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.event_bus import EventBus  # noqa: F401, E402

__all__ = ["EventBus"]
