"""
tests/test_event_bus.py
EventBus 单元测试：发布/订阅、多订阅者、异常隔离、取消订阅
"""
import pytest

from src.core.event_bus import EventBus


@pytest.fixture(autouse=True)
def reset_bus():
    """每个测试前后重置单例，保证隔离。"""
    EventBus.reset()
    yield
    EventBus.reset()


@pytest.fixture
def bus():
    return EventBus.get_instance()


# ---------- 单例 ----------

class TestSingleton:
    def test_same_instance(self):
        a = EventBus.get_instance()
        b = EventBus.get_instance()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = EventBus.get_instance()
        EventBus.reset()
        b = EventBus.get_instance()
        assert a is not b


# ---------- 发布 / 订阅 ----------

class TestPublishSubscribe:
    def test_handler_called_on_publish(self, bus):
        received = []
        bus.subscribe("evt", lambda d: received.append(d))
        bus.publish("evt", {"x": 1})
        assert received == [{"x": 1}]

    def test_no_handler_no_error(self, bus):
        count = bus.publish("unknown_event", {"a": "b"})
        assert count == 0

    def test_publish_returns_success_count(self, bus):
        bus.subscribe("e", lambda d: None)
        bus.subscribe("e", lambda d: None)
        assert bus.publish("e") == 2

    def test_default_data_is_empty_dict(self, bus):
        received = []
        bus.subscribe("e", lambda d: received.append(d))
        bus.publish("e")
        assert received == [{}]

    def test_subscribe_same_handler_twice_registers_once(self, bus):
        calls = []
        h = lambda d: calls.append(d)
        bus.subscribe("e", h)
        bus.subscribe("e", h)
        bus.publish("e", {})
        assert len(calls) == 1


# ---------- 多订阅者 ----------

class TestMultipleSubscribers:
    def test_all_handlers_called(self, bus):
        results = []
        bus.subscribe("e", lambda d: results.append("h1"))
        bus.subscribe("e", lambda d: results.append("h2"))
        bus.subscribe("e", lambda d: results.append("h3"))
        bus.publish("e", {})
        assert results == ["h1", "h2", "h3"]

    def test_handlers_called_in_registration_order(self, bus):
        order = []
        for i in range(5):
            idx = i
            bus.subscribe("e", lambda d, i=idx: order.append(i))
        bus.publish("e", {})
        assert order == [0, 1, 2, 3, 4]

    def test_independent_event_types(self, bus):
        a_calls, b_calls = [], []
        bus.subscribe("a", lambda d: a_calls.append(1))
        bus.subscribe("b", lambda d: b_calls.append(1))
        bus.publish("a", {})
        assert a_calls == [1]
        assert b_calls == []


# ---------- 异常隔离 ----------

class TestExceptionIsolation:
    def test_failing_handler_does_not_block_next(self, bus):
        results = []
        bus.subscribe("e", lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("e", lambda d: results.append("ok"))
        bus.publish("e", {})
        assert results == ["ok"]

    def test_failing_handler_counted_as_fail(self, bus):
        bus.subscribe("e", lambda d: 1 / 0)
        bus.subscribe("e", lambda d: None)
        count = bus.publish("e", {})
        assert count == 1  # only the second handler succeeded

    def test_on_error_callback_invoked(self, bus):
        errors = []
        bus.on_error(lambda et, h, exc: errors.append((et, exc)))
        bus.subscribe("e", lambda d: (_ for _ in ()).throw(ValueError("err")))
        bus.publish("e", {})
        assert len(errors) == 1
        assert errors[0][0] == "e"
        assert isinstance(errors[0][1], ValueError)

    def test_on_error_callback_exception_ignored(self, bus):
        """on_error 自身抛出异常时不应中断流程。"""
        def bad_error_cb(et, h, exc):
            raise RuntimeError("error in error handler")
        bus.on_error(bad_error_cb)
        results = []
        bus.subscribe("e", lambda d: (_ for _ in ()).throw(ValueError("x")))
        bus.subscribe("e", lambda d: results.append("safe"))
        bus.publish("e", {})
        assert results == ["safe"]


# ---------- 取消订阅 ----------

class TestUnsubscribe:
    def test_unsubscribed_handler_not_called(self, bus):
        calls = []
        h = lambda d: calls.append(1)
        bus.subscribe("e", h)
        bus.unsubscribe("e", h)
        bus.publish("e", {})
        assert calls == []

    def test_unsubscribe_nonexistent_handler_no_error(self, bus):
        bus.unsubscribe("e", lambda d: None)  # should not raise

    def test_unsubscribe_only_target_handler(self, bus):
        calls = []
        h1 = lambda d: calls.append("h1")
        h2 = lambda d: calls.append("h2")
        bus.subscribe("e", h1)
        bus.subscribe("e", h2)
        bus.unsubscribe("e", h1)
        bus.publish("e", {})
        assert calls == ["h2"]

    def test_subscribers_returns_copy(self, bus):
        h = lambda d: None
        bus.subscribe("e", h)
        subs = bus.subscribers("e")
        subs.clear()
        assert bus.subscribers("e") == [h]
