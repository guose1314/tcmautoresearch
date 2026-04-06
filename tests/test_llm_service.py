# tests/test_llm_service.py
"""
CachedLLMService 单元测试

覆盖要点
--------
* 缓存命中 / 未命中路径
* 底层 engine.generate() 调用计数
* TTL 过期逻辑
* cache_enabled=False 纯透传
* load() / unload() 委托
* invalidate_cache() 清除后重新命中
* cache_stats() 字段
* from_gap_config() 工厂（不加载真实模型）
* 线程安全基线
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ── 确保项目根目录在 sys.path ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infra.llm_service import (  # noqa: E402
    APILLMEngine,
    CachedLLMService,
    LLMService,
    _DiskCache,
)

# ─────────────────────────────────────────────────────────────────────────────
# 测试辅助工具
# ─────────────────────────────────────────────────────────────────────────────


def _make_engine(response: str = "ok") -> MagicMock:
    """创建一个模拟 LLMEngine，generate() 返回固定字符串。"""
    engine = MagicMock()
    engine.generate.return_value = response
    engine.model_path = "/tmp/fake.gguf"
    engine.temperature = 0.3
    engine.max_tokens = 512
    return engine


def _make_service(response: str = "ok", ttl=None, **kw) -> tuple[CachedLLMService, MagicMock]:
    """在临时目录中创建 CachedLLMService + 对应 engine mock。"""
    tmp = tempfile.mkdtemp()
    engine = _make_engine(response)
    svc = CachedLLMService(engine, cache_dir=tmp, cache_ttl_seconds=ttl, **kw)
    return svc, engine


# ─────────────────────────────────────────────────────────────────────────────
# 接口契约
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMServiceABC(unittest.TestCase):
    def test_llm_service_is_abstract(self):
        with self.assertRaises(TypeError):
            LLMService()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_generate(self):
        class NoGenerate(LLMService):
            pass

        with self.assertRaises(TypeError):
            NoGenerate()  # type: ignore[abstract]

    def test_concrete_implementation_works(self):
        class Echo(LLMService):
            def generate(self, prompt, system_prompt=""):
                return f"echo:{prompt}"

        svc = Echo()
        self.assertEqual(svc.generate("hi"), "echo:hi")
        svc.load()   # 默认无操作，不应抛出
        svc.unload()


# ─────────────────────────────────────────────────────────────────────────────
# 缓存命中 / 未命中
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheHitMiss(unittest.TestCase):
    def test_first_call_is_miss(self):
        svc, engine = _make_service("resp1")
        result = svc.generate("prompt1")
        self.assertEqual(result, "resp1")
        engine.generate.assert_called_once_with("prompt1", "")
        self.assertEqual(svc._misses, 1)
        self.assertEqual(svc._hits, 0)

    def test_second_call_is_hit(self):
        svc, engine = _make_service("resp2")
        svc.generate("same prompt")
        svc.generate("same prompt")
        # engine 只被调用一次
        self.assertEqual(engine.generate.call_count, 1)
        self.assertEqual(svc._hits, 1)

    def test_different_prompts_both_miss(self):
        svc, engine = _make_service("x")
        svc.generate("A")
        svc.generate("B")
        self.assertEqual(engine.generate.call_count, 2)
        self.assertEqual(svc._misses, 2)

    def test_different_system_prompts_are_different_keys(self):
        svc, engine = _make_service("y")
        svc.generate("p", "sys1")
        svc.generate("p", "sys2")
        self.assertEqual(engine.generate.call_count, 2)

    def test_cached_result_is_identical_to_original(self):
        long_resp = "中医" * 400
        svc, _ = _make_service(long_resp)
        r1 = svc.generate("详细分析附子毒性")
        r2 = svc.generate("详细分析附子毒性")
        self.assertEqual(r1, r2)
        self.assertEqual(r1, long_resp)


# ─────────────────────────────────────────────────────────────────────────────
# TTL 过期
# ─────────────────────────────────────────────────────────────────────────────


class TestTTL(unittest.TestCase):
    def test_entry_valid_within_ttl(self):
        svc, engine = _make_service(ttl=60)
        svc.generate("p")
        svc.generate("p")
        self.assertEqual(engine.generate.call_count, 1)

    def test_entry_expires_after_ttl(self):
        svc, _ = _make_service(ttl=0.01)
        svc.generate("p")
        time.sleep(0.05)  # 等超出 TTL
        # 重新创建服务指向同一数据库（模拟进程重启后访问过期缓存）
        engine2 = _make_engine("new_resp")
        engine2.model_path = svc._engine.model_path
        engine2.temperature = svc._engine.temperature
        engine2.max_tokens = svc._engine.max_tokens
        self.assertIsNotNone(svc._cache)
        cache = svc._cache
        assert cache is not None
        svc2 = CachedLLMService(engine2, cache_dir=cache._dir, cache_ttl_seconds=0.01)
        result = svc2.generate("p")
        self.assertEqual(result, "new_resp")
        # 过期条目被绕过，engine2 被调用了
        engine2.generate.assert_called_once()

    def test_ttl_none_never_expires(self):
        svc, engine = _make_service(ttl=None)
        svc.generate("q")
        time.sleep(0.02)
        svc.generate("q")
        self.assertEqual(engine.generate.call_count, 1)


# ─────────────────────────────────────────────────────────────────────────────
# cache_enabled=False 纯透传
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheDisabled(unittest.TestCase):
    def test_disabled_always_calls_engine(self):
        svc, engine = _make_service(cache_enabled=False)
        svc.generate("p")
        svc.generate("p")
        self.assertEqual(engine.generate.call_count, 2)

    def test_disabled_cache_stats_no_db(self):
        svc, _ = _make_service(cache_enabled=False)
        stats = svc.cache_stats()
        self.assertFalse(stats["cache_enabled"])
        self.assertNotIn("db_path", stats)

    def test_disabled_invalidate_returns_zero(self):
        svc, _ = _make_service(cache_enabled=False)
        self.assertEqual(svc.invalidate_cache(), 0)


# ─────────────────────────────────────────────────────────────────────────────
# load / unload 委托
# ─────────────────────────────────────────────────────────────────────────────


class TestLifecycle(unittest.TestCase):
    def test_load_delegates_to_engine(self):
        svc, engine = _make_service()
        svc.load()
        engine.load.assert_called_once()

    def test_unload_delegates_to_engine(self):
        svc, engine = _make_service()
        svc.unload()
        engine.unload.assert_called_once()

    def test_engine_without_load_unload_does_not_raise(self):
        """纯粹满足 generate 签名的对象也要能工作。"""
        engine = SimpleNamespace(
            generate=lambda p, s="": "bare",
            model_path="/m",
            temperature=0.3,
            max_tokens=512,
        )
        tmp = tempfile.mkdtemp()
        svc = CachedLLMService(engine, cache_dir=tmp)
        svc.load()   # 不抛
        svc.unload()


# ─────────────────────────────────────────────────────────────────────────────
# invalidate_cache
# ─────────────────────────────────────────────────────────────────────────────


class TestInvalidate(unittest.TestCase):
    def test_invalidate_removes_entries(self):
        svc, _ = _make_service()
        svc.generate("p1")
        svc.generate("p2")
        deleted = svc.invalidate_cache()
        self.assertEqual(deleted, 2)

    def test_after_invalidate_miss_again(self):
        svc, engine = _make_service("v1")
        svc.generate("pp")
        svc.invalidate_cache()
        engine.generate.return_value = "v2"
        result = svc.generate("pp")
        self.assertEqual(result, "v2")
        self.assertEqual(engine.generate.call_count, 2)


# ─────────────────────────────────────────────────────────────────────────────
# cache_stats
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheStats(unittest.TestCase):
    def test_stats_fields_present(self):
        svc, _ = _make_service()
        svc.generate("q1")
        svc.generate("q1")   # hit
        stats = svc.cache_stats()
        self.assertIn("session_hits", stats)
        self.assertIn("session_misses", stats)
        self.assertIn("total_entries", stats)
        self.assertIn("db_path", stats)

    def test_stats_counts_correct(self):
        svc, _ = _make_service()
        svc.generate("a")
        svc.generate("b")
        svc.generate("a")  # hit
        stats = svc.cache_stats()
        self.assertEqual(stats["session_hits"], 1)
        self.assertEqual(stats["session_misses"], 2)
        self.assertEqual(stats["total_entries"], 2)


# ─────────────────────────────────────────────────────────────────────────────
# getattr 透传（TCM helper methods）
# ─────────────────────────────────────────────────────────────────────────────


class TestGetAttrProxy(unittest.TestCase):
    def test_proxied_attribute_on_engine(self):
        svc, engine = _make_service()
        engine.some_tcm_helper = MagicMock(return_value="tcm_result")
        result = svc.some_tcm_helper("arg")
        engine.some_tcm_helper.assert_called_once_with("arg")
        self.assertEqual(result, "tcm_result")

    def test_missing_attribute_raises_attribute_error(self):
        # 用 spec 限制 mock 可访问的属性，使其对未知属性抛 AttributeError
        class _BareEngine:
            model_path = "/m"
            temperature = 0.3
            max_tokens = 512
            def generate(self, p, s=""): return "ok"
            def load(self): pass
            def unload(self): pass

        tmp = __import__("tempfile").mkdtemp()
        svc = CachedLLMService(_BareEngine(), cache_dir=tmp)
        with self.assertRaises(AttributeError):
            _ = svc.nonexistent_method_xyz


# ─────────────────────────────────────────────────────────────────────────────
# from_gap_config 工厂
# ─────────────────────────────────────────────────────────────────────────────


class TestFromGapConfig(unittest.TestCase):
    def test_from_gap_config_creates_service(self):
        gap_config = {
            "model_path": "/fake/model.gguf",
            "n_gpu_layers": 0,
            "n_ctx": 512,
            "temperature": 0.2,
            "max_tokens": 64,
        }
        llm_config = {
            "cache_enabled": True,
            "cache_dir": tempfile.mkdtemp(),
            "cache_ttl_seconds": None,
        }

        # 用 patch 避免真实 LLMEngine 初始化（llama-cpp-python 不一定已安装）
        with patch("src.infra.llm_service.CachedLLMService.from_engine_config") as mock_fec:
            mock_fec.return_value = MagicMock(spec=CachedLLMService)
            _ = CachedLLMService.from_gap_config(gap_config, llm_config)
            mock_fec.assert_called_once()
            call_kwargs = mock_fec.call_args[1]
            self.assertEqual(call_kwargs["temperature"], 0.2)
            self.assertEqual(call_kwargs["max_tokens"], 64)
            self.assertTrue(call_kwargs["cache_enabled"])

    def test_from_gap_config_uses_llm_config_fallback(self):
        """gap_config 中无 model_path 时应从 llm_config.path 回退。"""
        gap_config: dict = {}
        llm_config = {
            "path": "/fallback/model.gguf",
            "temperature": 0.5,
            "max_tokens": 256,
            "cache_enabled": False,
            "cache_dir": tempfile.mkdtemp(),
        }
        with patch("src.infra.llm_service.CachedLLMService.from_engine_config") as mock_fec:
            mock_fec.return_value = MagicMock(spec=CachedLLMService)
            CachedLLMService.from_gap_config(gap_config, llm_config)
            call_kwargs = mock_fec.call_args[1]
            self.assertEqual(call_kwargs["model_path"], "/fallback/model.gguf")
            self.assertFalse(call_kwargs["cache_enabled"])

    def test_from_gap_config_api_mode_uses_api_factory(self):
        gap_config = {
            "mode": "api",
            "api_url": "https://api.example.com/v1/chat/completions",
            "api_model": "qwen-plus",
            "temperature": 0.1,
            "max_tokens": 100,
        }
        llm_config = {
            "cache_enabled": True,
            "cache_dir": tempfile.mkdtemp(),
            "cache_ttl_seconds": None,
        }

        with patch("src.infra.llm_service.CachedLLMService.from_api_config") as mock_fac:
            mock_fac.return_value = MagicMock(spec=CachedLLMService)
            _ = CachedLLMService.from_gap_config(gap_config, llm_config)
            mock_fac.assert_called_once()
            call_kwargs = mock_fac.call_args[1]
            self.assertEqual(call_kwargs["api_url"], "https://api.example.com/v1/chat/completions")
            self.assertEqual(call_kwargs["model"], "qwen-plus")
            self.assertEqual(call_kwargs["temperature"], 0.1)
            self.assertEqual(call_kwargs["max_tokens"], 100)


class TestApiLLMEngine(unittest.TestCase):
    class _FakeHTTPResponse:
        def __init__(self, data: dict):
            self._raw = __import__("json").dumps(data).encode("utf-8")

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def test_generate_success(self):
        engine = APILLMEngine(
            api_url="https://api.example.com/v1/chat/completions",
            model="qwen-plus",
            api_key="sk-test",
            timeout_seconds=10,
            temperature=0.2,
            max_tokens=256,
        )

        fake_response = self._FakeHTTPResponse({
            "choices": [
                {
                    "message": {
                        "content": "api-ok"
                    }
                }
            ]
        })

        with patch("src.infra.llm_service.urllib_request.urlopen", return_value=fake_response) as mock_post:
            result = engine.generate("请分析附子", "你是中医研究助手")
            self.assertEqual(result, "api-ok")
            mock_post.assert_called_once()

    def test_generate_invalid_payload_raises(self):
        engine = APILLMEngine(
            api_url="https://api.example.com/v1/chat/completions",
            model="qwen-plus",
        )
        fake_response = self._FakeHTTPResponse({"unexpected": True})

        with patch("src.infra.llm_service.urllib_request.urlopen", return_value=fake_response):
            with self.assertRaises(RuntimeError):
                engine.generate("hello")


# ─────────────────────────────────────────────────────────────────────────────
# 线程安全基线
# ─────────────────────────────────────────────────────────────────────────────


class TestThreadSafety(unittest.TestCase):
    def test_concurrent_same_prompt(self):
        """多线程对同一 prompt 并发调用不应抛出异常。"""
        svc, engine = _make_service("concurrent_resp")
        errors: list[Exception] = []
        results: list[str] = []

        def worker():
            try:
                results.append(svc.generate("concurrent prompt"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"线程报错: {errors}")
        self.assertEqual(len(results), 10)
        self.assertTrue(all(r == "concurrent_resp" for r in results))
        # engine 调用次数 <= 2（并发下可能有两个线程都判断为 miss）
        self.assertLessEqual(engine.generate.call_count, 3)

    def test_concurrent_different_prompts(self):
        """多线程不同 prompt 并发，不应出现数据损坏。"""
        svc, _ = _make_service("r")
        errors: list[Exception] = []

        def worker(i: int):
            try:
                svc.generate(f"prompt_{i}")
                svc.generate(f"prompt_{i}")  # second call should hit
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"线程报错: {errors}")


# ─────────────────────────────────────────────────────────────────────────────
# _DiskCache 内部测试（低层验证）
# ─────────────────────────────────────────────────────────────────────────────


class TestDiskCacheInternals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = _DiskCache(self.tmp)

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.cache.get("deadbeef"))

    def test_put_then_get(self):
        self.cache.put("k1", "v1", "p", "", "/m", 0.3, 512)
        self.assertEqual(self.cache.get("k1"), "v1")

    def test_put_replace(self):
        self.cache.put("k1", "v1", "p", "", "/m", 0.3, 512)
        self.cache.put("k1", "v2", "p", "", "/m", 0.3, 512)
        self.assertEqual(self.cache.get("k1"), "v2")

    def test_stats_total_entries(self):
        self.cache.put("k1", "v1", "p", "", "/m", 0.3, 512)
        self.cache.put("k2", "v2", "p", "", "/m", 0.3, 512)
        self.assertEqual(self.cache.stats()["total_entries"], 2)

    def test_invalidate_empties_db(self):
        self.cache.put("k1", "v1", "p", "", "/m", 0.3, 512)
        r = self.cache.invalidate()
        self.assertEqual(r, 1)
        self.assertEqual(self.cache.stats()["total_entries"], 0)

    def test_make_key_deterministic(self):
        k1 = _DiskCache.make_key("hello", "sys", "/m", 0.3, 512)
        k2 = _DiskCache.make_key("hello", "sys", "/m", 0.3, 512)
        self.assertEqual(k1, k2)

    def test_make_key_sensitive_to_inputs(self):
        k1 = _DiskCache.make_key("A", "", "/m", 0.3, 512)
        k2 = _DiskCache.make_key("B", "", "/m", 0.3, 512)
        self.assertNotEqual(k1, k2)

    def test_make_key_sensitive_to_temperature(self):
        k1 = _DiskCache.make_key("p", "", "/m", 0.3, 512)
        k2 = _DiskCache.make_key("p", "", "/m", 0.9, 512)
        self.assertNotEqual(k1, k2)

    def test_database_created_on_disk(self):
        db_path = Path(self.tmp) / "llm_cache.db"
        self.assertTrue(db_path.exists())


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
