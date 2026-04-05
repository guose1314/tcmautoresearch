# -*- coding: utf-8 -*-
"""WebSocket 连接管理器 — 房间管理、广播与事件桥接。

提供：
- ``ConnectionManager``：管理多客户端 WebSocket 连接，支持按频道（room）分组广播
- ``EventBridge``：将 ``EventBus`` 同步事件桥接到 WebSocket 异步广播
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器 — 支持房间分组广播。

    Usage::

        manager = ConnectionManager()

        # 在 WebSocket 端点中
        await manager.connect(ws, room="research:cycle-123")
        manager.disconnect(ws, room="research:cycle-123")

        # 广播到房间
        await manager.broadcast({"type": "progress", "phase": "observe"}, room="research:cycle-123")

        # 广播到所有连接
        await manager.broadcast_all({"type": "system", "message": "server shutting down"})
    """

    def __init__(self) -> None:
        # room → set of active WebSocket connections
        self._rooms: DefaultDict[str, Set[WebSocket]] = defaultdict(set)
        # all connections (for global broadcast)
        self._all: Set[WebSocket] = set()

    @property
    def total_connections(self) -> int:
        return len(self._all)

    def room_size(self, room: str) -> int:
        return len(self._rooms.get(room, set()))

    async def connect(self, ws: WebSocket, room: str = "default") -> None:
        """接受 WebSocket 连接并加入房间。

        **不** 调用 ``ws.accept()`` — 由调用方决定何时 accept。
        """
        self._all.add(ws)
        self._rooms[room].add(ws)
        logger.debug("WS 加入房间 %s (room_size=%d, total=%d)",
                      room, self.room_size(room), self.total_connections)

    def disconnect(self, ws: WebSocket, room: Optional[str] = None) -> None:
        """移除 WebSocket 连接。"""
        self._all.discard(ws)
        if room is not None:
            self._rooms[room].discard(ws)
            if not self._rooms[room]:
                del self._rooms[room]
        else:
            # 从所有房间移除
            empty_rooms: List[str] = []
            for r, conns in self._rooms.items():
                conns.discard(ws)
                if not conns:
                    empty_rooms.append(r)
            for r in empty_rooms:
                del self._rooms[r]

    async def send_json(self, ws: WebSocket, data: Dict[str, Any]) -> bool:
        """向单个连接发送 JSON，失败返回 False。"""
        try:
            await ws.send_json(data)
            return True
        except Exception:
            return False

    async def broadcast(self, data: Dict[str, Any], room: str) -> int:
        """向房间内所有连接广播 JSON，返回成功发送数。"""
        conns = list(self._rooms.get(room, set()))
        if not conns:
            return 0
        sent = 0
        dead: List[WebSocket] = []
        for ws in conns:
            ok = await self.send_json(ws, data)
            if ok:
                sent += 1
            else:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, room)
        return sent

    async def broadcast_all(self, data: Dict[str, Any]) -> int:
        """向所有连接广播 JSON。"""
        conns = list(self._all)
        sent = 0
        dead: List[WebSocket] = []
        for ws in conns:
            ok = await self.send_json(ws, data)
            if ok:
                sent += 1
            else:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        return sent

    def get_rooms(self) -> List[str]:
        """返回当前活跃房间列表。"""
        return list(self._rooms.keys())


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_manager_instance: Optional[ConnectionManager] = None


def get_manager() -> ConnectionManager:
    """获取全局 ConnectionManager 单例。"""
    global _manager_instance  # noqa: PLW0603
    if _manager_instance is None:
        _manager_instance = ConnectionManager()
    return _manager_instance


def reset_manager() -> None:
    """重置单例（测试用）。"""
    global _manager_instance  # noqa: PLW0603
    _manager_instance = None


# ---------------------------------------------------------------------------
# EventBus → WebSocket 桥接
# ---------------------------------------------------------------------------


class EventBridge:
    """将同步 EventBus 事件桥接到 WebSocket 异步广播。

    Parameters
    ----------
    manager : ConnectionManager
        WebSocket 连接管理器。
    loop : asyncio.AbstractEventLoop | None
        事件循环，为 None 时在桥接时尝试自动获取。
    """

    def __init__(
        self,
        manager: Optional[ConnectionManager] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._manager = manager or get_manager()
        self._loop = loop
        self._subscriptions: List[tuple] = []  # [(event_type, handler)]

    def bind(
        self,
        event_bus: Any,
        event_type: str,
        room: str,
    ) -> None:
        """将 EventBus 的某事件类型绑定到 WebSocket 房间。

        Parameters
        ----------
        event_bus : EventBus
            事件总线实例。
        event_type : str
            要监听的事件类型。
        room : str
            推送目标房间。
        """
        def _handler(data: Any) -> None:
            payload: Dict[str, Any] = {
                "type": event_type,
                "data": data if isinstance(data, dict) else {"value": data},
            }
            loop = self._loop
            if loop is None:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    logger.debug("无可用事件循环，跳过 WS 广播: %s", event_type)
                    return

            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._manager.broadcast(payload, room), loop
                )
            else:
                logger.debug("事件循环未运行，跳过 WS 广播: %s", event_type)

        event_bus.subscribe(event_type, _handler)
        self._subscriptions.append((event_type, _handler))

    def unbind_all(self, event_bus: Any) -> None:
        """取消所有已注册的订阅。"""
        for event_type, handler in self._subscriptions:
            event_bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
