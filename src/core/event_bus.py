"""轻量事件总线：发布订阅 + 同步请求响应。

唯一权威实现。原 ``src.infra.event_bus`` 已改为重导出本模块。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List, Optional

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Any]


class EventBus:
    """进程内事件总线（支持单例模式）。"""

    _instance: "Optional[EventBus]" = None

    # ---------- singleton ----------

    @classmethod
    def get_instance(cls) -> "EventBus":
        """返回全局单例，不存在则创建。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """清空单例状态，供测试使用。"""
        cls._instance = None

    # ---------- lifecycle ----------

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[EventHandler]] = defaultdict(list)
        self._on_error: Optional[Callable[[str, Callable, Exception], None]] = None

    # ---------- public API ----------

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event_type: str, data: Any = None) -> int:
        """同步发布事件。返回成功调用的 handler 数量。

        无订阅者时记录 dead-letter WARNING，便于排查管道断裂。
        """
        if data is None:
            data = {}
        handlers = list(self._handlers.get(event_type, []))
        if not handlers:
            logger.warning(
                "Dead-letter: 事件 '%s' 无订阅者，数据被丢弃 (keys=%s)",
                event_type,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            return 0
        success = 0
        for handler in handlers:
            try:
                handler(data)
                success += 1
            except Exception as exc:
                logger.warning(
                    "Handler %s raised exception for event '%s': %s",
                    handler, event_type, exc,
                )
                if self._on_error is not None:
                    try:
                        self._on_error(event_type, handler, exc)
                    except Exception:
                        pass
        return success

    def request(self, event_type: str, data: Any) -> Optional[Any]:
        """同步请求：返回第一个非 None 结果。"""
        for handler in list(self._handlers.get(event_type, [])):
            result = handler(data)
            if result is not None:
                return result
        return None

    def on_error(self, callback: Callable[[str, Callable, Exception], None]) -> None:
        """设置全局错误回调。"""
        self._on_error = callback

    def subscribers(self, event_type: str) -> List[Callable]:
        """返回指定事件类型的当前订阅者列表（副本）。"""
        return list(self._handlers.get(event_type, []))
