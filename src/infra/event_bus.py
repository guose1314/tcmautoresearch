"""
src/infra/event_bus.py
轻量级同步发布-订阅事件总线
"""
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """
    轻量级同步事件总线（单例）。

    用法::

        bus = EventBus.get_instance()
        bus.subscribe("entity_extracted", my_handler)
        bus.publish("entity_extracted", {"entities": [...]})
        bus.unsubscribe("entity_extracted", my_handler)
    """

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
        # event_type -> [handler, ...]
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._on_error: Optional[Callable[[str, Callable, Exception], None]] = None

    # ---------- public API ----------

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """
        订阅事件。

        Args:
            event_type: 事件类型字符串。
            handler: 可调用对象，签名 ``handler(data: Dict) -> Any``。
        """
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("Subscribed %s to event '%s'", handler, event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """
        取消订阅事件。未注册时静默忽略。

        Args:
            event_type: 事件类型字符串。
            handler: 之前注册的可调用对象。
        """
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed %s from event '%s'", handler, event_type)

    def publish(self, event_type: str, data: Dict[str, Any] | None = None) -> int:
        """
        同步发布事件，按注册顺序依次调用所有 handler。

        单个 handler 抛出异常时调用 on_error 回调（如已设置），
        不影响后续 handler 的执行。

        Args:
            event_type: 事件类型字符串。
            data: 传递给 handler 的数据字典（默认空字典）。

        Returns:
            成功调用的 handler 数量。
        """
        if data is None:
            data = {}
        handlers = list(self._handlers.get(event_type, []))
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

    def on_error(self, callback: Callable[[str, Callable, Exception], None]) -> None:
        """
        设置全局错误回调。

        Args:
            callback: ``callback(event_type, handler, exception)``
        """
        self._on_error = callback

    def subscribers(self, event_type: str) -> List[Callable]:
        """返回指定事件类型的当前订阅者列表（副本）。"""
        return list(self._handlers.get(event_type, []))
