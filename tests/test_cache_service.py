# tests/test_cache_service.py
"""
DiskCacheStore / LLMDiskCache 单元测试

覆盖要点
--------
* DiskCacheStore: 读写、TTL 过期、invalidate、stats、namespace 隔离
* make_key 确定性与敏感性
* LLMDiskCache: make_key / put / get 兼容旧 _DiskCache 签名
* _DiskCache 别名可用
* 线程安全基线
* 文件路径自动创建
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infra.cache_service import DiskCacheStore, LLMDiskCache, _DiskCache
from src.infra.layered_cache import LayeredTaskCache, describe_llm_engine

# ─────────────────────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────────────────────


def _store(namespace: str = "test", ttl: float | None = None) -> DiskCacheStore:
    tmp = tempfile.mkdtemp()
    return DiskCacheStore(tmp, namespace=namespace, ttl_seconds=ttl)


def _llm_cache(ttl: float | None = None) -> LLMDiskCache:
    tmp = tempfile.mkdtemp()
    return LLMDiskCache(tmp, ttl_seconds=ttl)


# ─────────────────────────────────────────────────────────────────────────────
# DiskCacheStore — 基础读写
# ─────────────────────────────────────────────────────────────────────────────


class TestDiskCacheStoreBasic(unittest.TestCase):
    def test_get_nonexistent_none(self):
        c = _store()
        self.assertIsNone(c.get("no_such_key"))

    def test_put_then_get(self):
        c = _store()
        c.put("k1", "v1")
        self.assertEqual(c.get("k1"), "v1")

    def test_put_replace(self):
        c = _store()
        c.put("k1", "v1")
        c.put("k1", "v2")
        self.assertEqual(c.get("k1"), "v2")

    def test_meta_stored_does_not_affect_value(self):
        c = _store()
        c.put("k1", "hello", meta={"foo": "bar"})
        self.assertEqual(c.get("k1"), "hello")

    def test_db_file_created(self):
        tmp = tempfile.mkdtemp()
        c = DiskCacheStore(tmp)
        self.assertTrue((Path(tmp) / "cache_store.db").exists())

    def test_dir_autocreated(self):
        tmp = Path(tempfile.mkdtemp()) / "nested" / "dir"
        c = DiskCacheStore(tmp)
        self.assertTrue(tmp.exists())
        del c  # suppress unused warning


# ─────────────────────────────────────────────────────────────────────────────
# TTL
# ─────────────────────────────────────────────────────────────────────────────


class TestDiskCacheStoreTTL(unittest.TestCase):
    def test_within_ttl_returns_value(self):
        c = _store(ttl=60)
        c.put("k", "v")
        self.assertEqual(c.get("k"), "v")

    def test_expired_returns_none(self):
        c = _store(ttl=0.01)
        c.put("k", "v")
        time.sleep(0.05)
        self.assertIsNone(c.get("k"))

    def test_no_ttl_never_expires(self):
        c = _store(ttl=None)
        c.put("k", "v")
        time.sleep(0.02)
        self.assertEqual(c.get("k"), "v")


# ─────────────────────────────────────────────────────────────────────────────
# invalidate & stats
# ─────────────────────────────────────────────────────────────────────────────


class TestDiskCacheStoreInvalidate(unittest.TestCase):
    def test_invalidate_clears_entries(self):
        c = _store()
        c.put("a", "1")
        c.put("b", "2")
        deleted = c.invalidate()
        self.assertEqual(deleted, 2)
        self.assertIsNone(c.get("a"))

    def test_stats_total_entries(self):
        c = _store()
        c.put("x", "1")
        c.put("y", "2")
        s = c.stats()
        self.assertEqual(s["total_entries"], 2)

    def test_stats_fields(self):
        c = _store(namespace="myns")
        s = c.stats()
        self.assertIn("namespace", s)
        self.assertIn("total_entries", s)
        self.assertIn("db_path", s)
        self.assertIn("ttl_seconds", s)
        self.assertIn("oldest_entry", s)


# ─────────────────────────────────────────────────────────────────────────────
# Namespace 隔离
# ─────────────────────────────────────────────────────────────────────────────


class TestNamespaceIsolation(unittest.TestCase):
    def test_two_namespaces_do_not_share_entries(self):
        tmp = tempfile.mkdtemp()
        ca = DiskCacheStore(tmp, namespace="ns_a")
        cb = DiskCacheStore(tmp, namespace="ns_b")
        ca.put("shared_key", "from_a")
        self.assertIsNone(cb.get("shared_key"))
        self.assertEqual(ca.get("shared_key"), "from_a")

    def test_invalidate_only_affects_own_namespace(self):
        tmp = tempfile.mkdtemp()
        ca = DiskCacheStore(tmp, namespace="ns_x")
        cb = DiskCacheStore(tmp, namespace="ns_y")
        ca.put("k", "va")
        cb.put("k", "vb")
        ca.invalidate()
        self.assertIsNone(ca.get("k"))
        self.assertEqual(cb.get("k"), "vb")


# ─────────────────────────────────────────────────────────────────────────────
# make_key
# ─────────────────────────────────────────────────────────────────────────────


class TestMakeKey(unittest.TestCase):
    def test_deterministic(self):
        k1 = DiskCacheStore.make_key("a", "b", "c")
        k2 = DiskCacheStore.make_key("a", "b", "c")
        self.assertEqual(k1, k2)

    def test_different_parts_different_keys(self):
        k1 = DiskCacheStore.make_key("a", "b")
        k2 = DiskCacheStore.make_key("a", "c")
        self.assertNotEqual(k1, k2)

    def test_order_matters(self):
        k1 = DiskCacheStore.make_key("x", "y")
        k2 = DiskCacheStore.make_key("y", "x")
        self.assertNotEqual(k1, k2)

    def test_returns_64_hex_chars(self):
        key = DiskCacheStore.make_key("hello")
        self.assertEqual(len(key), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in key))


# ─────────────────────────────────────────────────────────────────────────────
# LLMDiskCache — make_key / put / get
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMDiskCache(unittest.TestCase):
    def test_make_key_deterministic(self):
        k1 = LLMDiskCache.make_key("prompt", "sys", "/m", 0.3, 512)
        k2 = LLMDiskCache.make_key("prompt", "sys", "/m", 0.3, 512)
        self.assertEqual(k1, k2)

    def test_make_key_sensitive_to_prompt(self):
        k1 = LLMDiskCache.make_key("A", "", "/m", 0.3, 512)
        k2 = LLMDiskCache.make_key("B", "", "/m", 0.3, 512)
        self.assertNotEqual(k1, k2)

    def test_make_key_sensitive_to_temperature(self):
        k1 = LLMDiskCache.make_key("p", "", "/m", 0.3, 512)
        k2 = LLMDiskCache.make_key("p", "", "/m", 0.9, 512)
        self.assertNotEqual(k1, k2)

    def test_make_key_is_llm_key_alias(self):
        k1 = LLMDiskCache.make_key("p", "s", "/m", 0.3, 512)
        k2 = LLMDiskCache.make_llm_key("p", "s", "/m", 0.3, 512)
        self.assertEqual(k1, k2)

    def test_put_and_get_old_signature(self):
        c = _llm_cache()
        key = LLMDiskCache.make_key("p", "s", "/m", 0.3, 512)
        c.put(key, "response", "p", "s", "/m", 0.3, 512)
        self.assertEqual(c.get(key), "response")

    def test_put_and_get_new_signature(self):
        c = _llm_cache()
        key = DiskCacheStore.make_key("test_key")
        c.put(key, "value", meta={"x": 1})
        self.assertEqual(c.get(key), "value")

    def test_put_llm_accepts_legacy_kwargs(self):
        c = _llm_cache()
        key = LLMDiskCache.make_key("p", "s", "/m", 0.3, 512)
        c.put_llm(
            key,
            "response",
            prompt="p",
            system_prompt="s",
            model_id="/m",
            temperature=0.3,
            max_tokens=512,
        )
        self.assertEqual(c.get(key), "response")

    def test_database_filename_is_llm_cache_db(self):
        tmp = tempfile.mkdtemp()
        c = LLMDiskCache(tmp)
        self.assertTrue((Path(tmp) / "llm_cache.db").exists())

    def test_ttl_expired(self):
        c = _llm_cache(ttl=0.01)
        key = LLMDiskCache.make_key("p", "", "/m", 0.3, 512)
        c.put(key, "r", "p", "", "/m", 0.3, 512)
        time.sleep(0.05)
        self.assertIsNone(c.get(key))

    def test_invalidate(self):
        c = _llm_cache()
        k1 = LLMDiskCache.make_key("p1", "", "/m", 0.3, 512)
        k2 = LLMDiskCache.make_key("p2", "", "/m", 0.3, 512)
        c.put(k1, "r1", "p1", "", "/m", 0.3, 512)
        c.put(k2, "r2", "p2", "", "/m", 0.3, 512)
        deleted = c.invalidate()
        self.assertEqual(deleted, 2)

    def test_stats(self):
        c = _llm_cache()
        s = c.stats()
        self.assertIn("total_entries", s)
        self.assertIn("db_path", s)


# ─────────────────────────────────────────────────────────────────────────────
# _DiskCache 别名
# ─────────────────────────────────────────────────────────────────────────────


class TestDiskCacheAlias(unittest.TestCase):
    def test_alias_is_llm_disk_cache(self):
        self.assertIs(_DiskCache, LLMDiskCache)

    def test_alias_usable(self):
        tmp = tempfile.mkdtemp()
        c = _DiskCache(tmp)
        key = _DiskCache.make_key("p", "s", "/m", 0.3, 512)
        c.put(key, "v", "p", "s", "/m", 0.3, 512)
        self.assertEqual(c.get(key), "v")


# ─────────────────────────────────────────────────────────────────────────────
# 线程安全基线
# ─────────────────────────────────────────────────────────────────────────────


class TestThreadSafety(unittest.TestCase):
    def test_concurrent_put_get_no_error(self):
        c = _store(namespace="thread_test")
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                key = DiskCacheStore.make_key(f"prompt_{i}")
                c.put(key, f"value_{i}")
                result = c.get(key)
                assert result == f"value_{i}", f"unexpected: {result}"
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"线程错误: {errors}")

    def test_concurrent_invalidate_safe(self):
        c = _store(namespace="inv_test")
        for i in range(10):
            c.put(DiskCacheStore.make_key(str(i)), str(i))

        errors: list[Exception] = []

        def worker() -> None:
            try:
                c.invalidate()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestLayeredTaskCache(unittest.TestCase):
    def test_prompt_and_evidence_layers_are_isolated(self):
        tmp = tempfile.mkdtemp()
        cache = LayeredTaskCache(
            settings={
                "enabled": True,
                "cache_dir": tmp,
                "prompt": {"enabled": True, "namespace": "prompt", "ttl_seconds": None},
                "evidence": {"enabled": True, "namespace": "evidence", "ttl_seconds": None},
                "artifact": {"enabled": False},
            }
        )

        payload = {"task": "same"}
        cache.put_text("prompt", "task-a", payload, "prompt-value")
        cache.put_text("evidence", "task-a", payload, "evidence-value")

        self.assertEqual(cache.get_text("prompt", "task-a", payload), "prompt-value")
        self.assertEqual(cache.get_text("evidence", "task-a", payload), "evidence-value")

    def test_put_json_round_trip(self):
        tmp = tempfile.mkdtemp()
        cache = LayeredTaskCache(
            settings={
                "enabled": True,
                "cache_dir": tmp,
                "prompt": {"enabled": False},
                "evidence": {"enabled": False},
                "artifact": {"enabled": True, "namespace": "artifact", "ttl_seconds": None},
            }
        )

        payload = {"objective": "artifact"}
        value = {"output_data": {"metadata": {"objective": "artifact"}}}
        cache.put_json("artifact", "output_generator.execute", payload, value)
        self.assertEqual(cache.get_json("artifact", "output_generator.execute", payload), value)

    def test_describe_llm_engine_prefers_wrapped_engine_attributes(self):
        class Engine:
            llm_mode = "local"
            model_path = "./models/qwen.gguf"
            temperature = 0.2
            max_tokens = 512

        class Wrapper:
            def __init__(self):
                self._engine = Engine()

        descriptor = describe_llm_engine(Wrapper())
        self.assertEqual(descriptor["mode"], "local")
        self.assertEqual(descriptor["model"], "./models/qwen.gguf")
        self.assertEqual(descriptor["temperature"], 0.2)
        self.assertEqual(descriptor["max_tokens"], 512)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
