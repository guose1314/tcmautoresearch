"""兼容层 — EventBus 权威实现已统一至 src.core.event_bus。

.. deprecated:: 2.0
    请改用 ``from src.core.event_bus import EventBus``
"""
import warnings as _warnings

_warnings.warn(
    "src.infra.event_bus 已统一至 src.core.event_bus，请更新导入路径",
    DeprecationWarning,
    stacklevel=2,
)

from src.core.event_bus import EventBus, EventHandler  # noqa: F401

__all__ = ["EventBus", "EventHandler"]
