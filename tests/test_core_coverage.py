"""core 层覆盖率补齐测试 — event_bus / module_factory / architecture / module_interface。"""

import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.core.architecture import (
    ModuleInfo,
    ModuleRegistry,
    ModuleType,
    SystemArchitecture,
    SystemConfiguration,
)
from src.core.event_bus import EventBus
from src.core.module_base import ModuleContext, ModuleOutput, ModuleStatus
from src.core.module_factory import ModuleFactory


# ===================================================================
# EventBus
# ===================================================================
class TestEventBus(unittest.TestCase):
    def test_subscribe_and_publish(self):
        bus = EventBus()
        results = []
        handler = lambda data: results.append(data)
        bus.subscribe("test", handler)
        bus.publish("test", "hello")
        self.assertEqual(results, ["hello"])

    def test_unsubscribe(self):
        bus = EventBus()
        results = []
        handler = lambda data: results.append(data)
        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        bus.publish("test", "hello")
        self.assertEqual(results, [])

    def test_unsubscribe_not_subscribed(self):
        bus = EventBus()
        handler = lambda data: None
        bus.unsubscribe("test", handler)  # should not raise

    def test_request_returns_first_non_none(self):
        bus = EventBus()
        bus.subscribe("calc", lambda d: None)
        bus.subscribe("calc", lambda d: d * 2)
        bus.subscribe("calc", lambda d: d * 3)
        result = bus.request("calc", 5)
        self.assertEqual(result, 10)

    def test_request_all_none(self):
        bus = EventBus()
        bus.subscribe("calc", lambda d: None)
        result = bus.request("calc", 5)
        self.assertIsNone(result)

    def test_request_no_handlers(self):
        bus = EventBus()
        result = bus.request("nothing", 1)
        self.assertIsNone(result)

    def test_publish_no_handlers(self):
        bus = EventBus()
        bus.publish("nothing", "data")  # should not raise

    def test_duplicate_subscribe_ignored(self):
        bus = EventBus()
        results = []
        handler = lambda data: results.append(data)
        bus.subscribe("test", handler)
        bus.subscribe("test", handler)
        bus.publish("test", "x")
        self.assertEqual(len(results), 1)


# ===================================================================
# ModuleFactory
# ===================================================================
class TestModuleFactory(unittest.TestCase):
    def test_register_and_create(self):
        factory = ModuleFactory()
        factory.register("test", lambda cfg: {"created": True, **cfg})
        result = factory.create("test", {"key": "val"})
        self.assertTrue(result["created"])
        self.assertEqual(result["key"], "val")

    def test_register_empty_key_raises(self):
        factory = ModuleFactory()
        with self.assertRaises(ValueError):
            factory.register("", lambda cfg: None)

    def test_create_unknown_key_raises(self):
        factory = ModuleFactory()
        with self.assertRaises(KeyError):
            factory.create("nonexistent")

    def test_has(self):
        factory = ModuleFactory()
        self.assertFalse(factory.has("x"))
        factory.register("x", lambda c: None)
        self.assertTrue(factory.has("x"))

    def test_register_path(self):
        factory = ModuleFactory()
        factory.register_path("normalizer", "src.collector.normalizer:Normalizer")
        result = factory.create("normalizer")
        from src.collector.normalizer import Normalizer
        self.assertIsInstance(result, Normalizer)

    def test_register_path_invalid_format(self):
        factory = ModuleFactory()
        with self.assertRaises(ValueError):
            factory.register_path("bad", "no_colon_here")

    def test_from_config_with_providers(self):
        factory = ModuleFactory.from_config({
            "providers": {
                "bus": "src.core.event_bus:EventBus",
            }
        })
        self.assertTrue(factory.has("bus"))

    def test_from_config_empty(self):
        factory = ModuleFactory.from_config(None)
        self.assertFalse(factory.has("anything"))

    def test_from_config_non_string_value_ignored(self):
        factory = ModuleFactory.from_config({"providers": {"x": 123}})
        self.assertFalse(factory.has("x"))

    def test_create_with_none_config(self):
        factory = ModuleFactory()
        factory.register("t", lambda cfg: cfg)
        result = factory.create("t")
        self.assertEqual(result, {})


# ===================================================================
# ModuleRegistry
# ===================================================================
class TestModuleRegistry(unittest.TestCase):
    def _make_info(self, mod_id="m1", name="模块1", deps=None, status=ModuleStatus.ACTIVE):
        return ModuleInfo(
            module_id=mod_id,
            module_name=name,
            module_type=ModuleType.ANALYSIS,
            version="1.0",
            status=status,
            created_at=datetime.now().isoformat(),
            dependencies=deps or [],
        )

    def test_register_and_get(self):
        reg = ModuleRegistry()
        info = self._make_info()
        self.assertTrue(reg.register_module(info))
        self.assertIsNotNone(reg.get_module("m1"))

    def test_register_duplicate_replaces(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(name="v1"))
        reg.register_module(self._make_info(name="v2"))
        self.assertEqual(reg.get_module("m1").module_name, "v2")

    def test_unregister(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info())
        self.assertTrue(reg.unregister_module("m1"))
        self.assertIsNone(reg.get_module("m1"))

    def test_unregister_nonexistent(self):
        reg = ModuleRegistry()
        self.assertFalse(reg.unregister_module("nope"))

    def test_get_module_by_name(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="m1", name="分析器"))
        self.assertIsNotNone(reg.get_module_by_name("分析器"))
        self.assertIsNone(reg.get_module_by_name("不存在"))

    def test_get_modules_by_type(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="m1"))
        reg.register_module(self._make_info(mod_id="m2"))
        results = reg.get_modules_by_type(ModuleType.ANALYSIS)
        self.assertEqual(len(results), 2)

    def test_activate_and_deactivate(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(status=ModuleStatus.INACTIVE))
        self.assertTrue(reg.activate_module("m1"))
        self.assertEqual(reg.get_module("m1").status, ModuleStatus.ACTIVE)
        self.assertTrue(reg.deactivate_module("m1"))
        self.assertEqual(reg.get_module("m1").status, ModuleStatus.INACTIVE)

    def test_activate_nonexistent(self):
        reg = ModuleRegistry()
        self.assertFalse(reg.activate_module("nope"))

    def test_deactivate_nonexistent(self):
        reg = ModuleRegistry()
        self.assertFalse(reg.deactivate_module("nope"))

    def test_get_dependencies(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="base"))
        reg.register_module(self._make_info(mod_id="child", deps=["base"]))
        deps = reg.get_module_dependencies("child")
        self.assertIn("base", deps)

    def test_get_dependents(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="base"))
        reg.register_module(self._make_info(mod_id="child", deps=["base"]))
        dependents = reg.get_module_dependents("base")
        self.assertIn("child", dependents)

    def test_get_dependencies_nonexistent(self):
        reg = ModuleRegistry()
        self.assertEqual(reg.get_module_dependencies("nope"), [])

    def test_get_dependents_nonexistent(self):
        reg = ModuleRegistry()
        self.assertEqual(reg.get_module_dependents("nope"), [])

    def test_get_module_graph(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info())
        graph = reg.get_module_graph()
        self.assertTrue(graph.has_node("m1"))

    def test_validate_compatibility_ok(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="base"))
        reg.register_module(self._make_info(mod_id="child", deps=["base"]))
        result = reg.validate_module_compatibility("child")
        self.assertTrue(result["valid"])

    def test_validate_compatibility_missing_dep(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="child", deps=["missing"]))
        result = reg.validate_module_compatibility("child")
        self.assertFalse(result["valid"])
        self.assertIn("不可用", result["error"])

    def test_validate_compatibility_inactive_dep(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="base", status=ModuleStatus.INACTIVE))
        reg.register_module(self._make_info(mod_id="child", deps=["base"]))
        result = reg.validate_module_compatibility("child")
        self.assertFalse(result["valid"])

    def test_validate_compatibility_nonexistent_module(self):
        reg = ModuleRegistry()
        result = reg.validate_module_compatibility("nope")
        self.assertFalse(result["valid"])

    def test_get_system_health(self):
        reg = ModuleRegistry()
        reg.register_module(self._make_info(mod_id="m1", status=ModuleStatus.ACTIVE))
        reg.register_module(self._make_info(mod_id="m2", status=ModuleStatus.ERROR))
        health = reg.get_system_health()
        self.assertEqual(health["total_modules"], 2)
        self.assertEqual(health["active_modules"], 1)
        self.assertEqual(health["error_modules"], 1)
        self.assertIn("health_score", health)

    def test_get_system_health_empty(self):
        reg = ModuleRegistry()
        health = reg.get_system_health()
        self.assertEqual(health["total_modules"], 0)


# ===================================================================
# SystemArchitecture
# ===================================================================
class TestSystemArchitecture(unittest.TestCase):
    def test_init_default(self):
        arch = SystemArchitecture()
        self.assertEqual(arch.system_status, "initialized")
        self.assertIsNotNone(arch.module_registry)

    def test_init_custom_config(self):
        arch = SystemArchitecture({"system_name": "测试系统", "version": "3.0"})
        self.assertEqual(arch.config.system_name, "测试系统")

    def test_phase_tracking(self):
        arch = SystemArchitecture()
        started = arch._start_phase("test_phase", {"key": "val"})
        self.assertIsInstance(started, float)
        arch._complete_phase("test_phase", started, {"result": "ok"})
        self.assertIn("test_phase", arch.completed_phases)
        self.assertIn("test_phase", arch.phase_timings)

    def test_fail_phase(self):
        arch = SystemArchitecture()
        started = arch._start_phase("bad_phase")
        arch._fail_phase("bad_phase", started, RuntimeError("boom"), {"ctx": "info"})
        self.assertEqual(arch.failed_phase, "bad_phase")
        self.assertEqual(arch.final_status, "failed")
        self.assertTrue(len(arch.failed_operations) >= 1)

    def test_phase_tracking_disabled(self):
        arch = SystemArchitecture({"enable_phase_tracking": False})
        started = arch._start_phase("ignored")
        arch._complete_phase("ignored", started)
        # phase_history should be empty
        self.assertEqual(len(arch.phase_history), 0)

    def test_serialize_value(self):
        arch = SystemArchitecture()
        self.assertEqual(arch._serialize_value(42), 42)
        self.assertEqual(arch._serialize_value("str"), "str")

    def test_module_registry_integration(self):
        arch = SystemArchitecture()
        info = ModuleInfo(
            module_id="test1",
            module_name="测试模块",
            module_type=ModuleType.ANALYSIS,
            version="1.0",
            status=ModuleStatus.ACTIVE,
            created_at=datetime.now().isoformat(),
        )
        arch.module_registry.register_module(info)
        self.assertIsNotNone(arch.module_registry.get_module("test1"))


# ===================================================================
# ModuleInterface (ModuleContext / ModuleOutput)
# ===================================================================
class TestModuleContext(unittest.TestCase):
    def test_context_creation(self):
        ctx = ModuleContext(
            context_id="ctx1",
            module_id="mod1",
            module_name="test",
            timestamp=datetime.now().isoformat(),
            input_data={"key": "val"},
        )
        self.assertEqual(ctx.context_id, "ctx1")
        self.assertEqual(ctx.input_data["key"], "val")


class TestModuleOutput(unittest.TestCase):
    def test_output_creation(self):
        out = ModuleOutput(
            output_id="out1",
            module_id="mod1",
            module_name="test",
            timestamp=datetime.now().isoformat(),
            success=True,
            output_data={"result": 42},
            metadata={},
            execution_time=0.5,
        )
        self.assertTrue(out.success)
        self.assertEqual(out.execution_time, 0.5)


if __name__ == "__main__":
    unittest.main()
