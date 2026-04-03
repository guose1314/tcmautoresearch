"""轻量事件总线：发布订阅 + 同步请求响应。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, List, Optional

EventHandler = Callable[[Any], Any]


class EventBus:
    """进程内事件总线。"""

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(self, event_type: str, data: Any) -> None:
        for handler in list(self._handlers.get(event_type, [])):
            handler(data)

    def request(self, event_type: str, data: Any) -> Optional[Any]:
        """同步请求：返回第一个非 None 结果。"""
        for handler in list(self._handlers.get(event_type, [])):
            result = handler(data)
            if result is not None:
                return result
        return None
