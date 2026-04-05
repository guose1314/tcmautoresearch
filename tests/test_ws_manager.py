# -*- coding: utf-8 -*-
"""tests/test_ws_manager.py — WebSocket ConnectionManager 与 EventBridge 单元测试。"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.web.ws_manager import (
    ConnectionManager,
    EventBridge,
    get_manager,
    reset_manager,
)


def _run(coro):
    """在新事件循环中运行协程（避免 pytest-asyncio 配置问题）。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_ws():
    """创建一个 mock WebSocket。"""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# ===================================================================
# ConnectionManager
# ===================================================================


class TestConnectionManager:
    @pytest.fixture()
    def mgr(self):
        return ConnectionManager()

    def test_connect_and_disconnect(self, mgr):
        ws = _make_ws()

        async def go():
            await mgr.connect(ws, "room1")
            assert mgr.total_connections == 1
            assert mgr.room_size("room1") == 1
            mgr.disconnect(ws, "room1")
            assert mgr.total_connections == 0
            assert mgr.room_size("room1") == 0

        _run(go())

    def test_connect_multiple_rooms(self, mgr):
        ws1, ws2 = _make_ws(), _make_ws()

        async def go():
            await mgr.connect(ws1, "room-a")
            await mgr.connect(ws2, "room-b")
            assert mgr.total_connections == 2
            assert mgr.room_size("room-a") == 1
            assert mgr.room_size("room-b") == 1

        _run(go())

    def test_disconnect_without_room(self, mgr):
        ws = _make_ws()

        async def go():
            await mgr.connect(ws, "room1")
            await mgr.connect(ws, "room2")
            mgr.disconnect(ws)  # no room → remove from all
            assert mgr.total_connections == 0
            assert mgr.room_size("room1") == 0
            assert mgr.room_size("room2") == 0

        _run(go())

    def test_broadcast_to_room(self, mgr):
        ws1, ws2, ws_other = _make_ws(), _make_ws(), _make_ws()

        async def go():
            await mgr.connect(ws1, "room-x")
            await mgr.connect(ws2, "room-x")
            await mgr.connect(ws_other, "room-y")
            sent = await mgr.broadcast({"type": "test"}, "room-x")
            assert sent == 2
            ws1.send_json.assert_called_once_with({"type": "test"})
            ws2.send_json.assert_called_once_with({"type": "test"})
            ws_other.send_json.assert_not_called()

        _run(go())

    def test_broadcast_empty_room(self, mgr):
        async def go():
            sent = await mgr.broadcast({"type": "test"}, "nonexistent")
            assert sent == 0

        _run(go())

    def test_broadcast_all(self, mgr):
        ws1, ws2 = _make_ws(), _make_ws()

        async def go():
            await mgr.connect(ws1, "room1")
            await mgr.connect(ws2, "room2")
            sent = await mgr.broadcast_all({"type": "global"})
            assert sent == 2

        _run(go())

    def test_broadcast_removes_dead_connections(self, mgr):
        ws_ok = _make_ws()
        ws_dead = _make_ws()
        ws_dead.send_json.side_effect = RuntimeError("closed")

        async def go():
            await mgr.connect(ws_ok, "room")
            await mgr.connect(ws_dead, "room")
            assert mgr.room_size("room") == 2
            sent = await mgr.broadcast({"type": "test"}, "room")
            assert sent == 1
            assert mgr.room_size("room") == 1

        _run(go())

    def test_send_json_success(self, mgr):
        ws = _make_ws()

        async def go():
            ok = await mgr.send_json(ws, {"hello": 1})
            assert ok is True

        _run(go())

    def test_send_json_failure(self, mgr):
        ws = _make_ws()
        ws.send_json.side_effect = RuntimeError("closed")

        async def go():
            ok = await mgr.send_json(ws, {"hello": 1})
            assert ok is False

        _run(go())

    def test_get_rooms(self, mgr):
        ws = _make_ws()

        async def go():
            await mgr.connect(ws, "alpha")
            await mgr.connect(ws, "beta")
            rooms = mgr.get_rooms()
            assert "alpha" in rooms
            assert "beta" in rooms

        _run(go())


# ===================================================================
# Singleton
# ===================================================================


class TestSingleton:
    def test_get_manager_singleton(self):
        reset_manager()
        m1 = get_manager()
        m2 = get_manager()
        assert m1 is m2
        reset_manager()

    def test_reset_manager(self):
        reset_manager()
        m1 = get_manager()
        reset_manager()
        m2 = get_manager()
        assert m1 is not m2
        reset_manager()


# ===================================================================
# EventBridge
# ===================================================================


class TestEventBridge:
    def test_bind_subscribes_to_event_bus(self):
        mgr = ConnectionManager()
        bridge = EventBridge(manager=mgr)
        bus = MagicMock()
        bridge.bind(bus, "phase_started", "research:123")
        bus.subscribe.assert_called_once()
        args = bus.subscribe.call_args
        assert args[0][0] == "phase_started"

    def test_unbind_all(self):
        mgr = ConnectionManager()
        bridge = EventBridge(manager=mgr)
        bus = MagicMock()
        bridge.bind(bus, "phase_started", "room1")
        bridge.bind(bus, "phase_completed", "room1")
        assert len(bridge._subscriptions) == 2

        bridge.unbind_all(bus)
        assert len(bridge._subscriptions) == 0
        assert bus.unsubscribe.call_count == 2

    def test_bridge_handler_broadcasts(self):
        """验证事件处理函数被调用时会触发广播。"""
        mgr = ConnectionManager()
        ws = _make_ws()

        async def go():
            await mgr.connect(ws, "room-test")

            loop = asyncio.get_event_loop()
            bridge = EventBridge(manager=mgr, loop=loop)

            from src.core.event_bus import EventBus
            bus = EventBus()
            bridge.bind(bus, "test_event", "room-test")

            bus.publish("test_event", {"progress": 50})

            # run_coroutine_threadsafe 的 future 需要等 loop 执行
            await asyncio.sleep(0.1)

            ws.send_json.assert_called()
            call_data = ws.send_json.call_args[0][0]
            assert call_data["type"] == "test_event"
            assert call_data["data"]["progress"] == 50

            bridge.unbind_all(bus)

        _run(go())

    def test_bridge_handler_no_loop(self):
        """无事件循环时不崩溃。"""
        mgr = ConnectionManager()
        bridge = EventBridge(manager=mgr, loop=None)
        bus = MagicMock()
        bridge.bind(bus, "ev", "room")

        handler = bus.subscribe.call_args[0][1]
        with patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")):
            handler({"data": 1})  # should not raise
