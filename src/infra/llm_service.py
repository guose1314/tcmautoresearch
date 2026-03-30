# src/infra/llm_service.py
"""
LLMService — LLM 调用抽象接口 + SQLite 磁盘缓存装饰器

架构位置
--------
本模块是基础设施层（``src/infra``）的 LLM 抽象组件。
业务层（``src/llm``、``src/research`` 等）通过 ``src.llm.llm_service``
或直接通过 ``src.infra.llm_service`` 导入，两者等价。

设计目标
--------
* ``LLMService`` 是轻量 ABC，只声明 ``generate`` / ``load`` / ``unload`` 三个方法。
  ``LLMEngine`` 在结构上满足此接口（duck typing），无需修改。
* ``CachedLLMService`` 以组合方式包装任何满足接口的 engine，在其前插入
  基于 SQLite 的磁盘缓存：相同 (prompt, system_prompt, model, temperature,
  max_tokens) 命中时直接返回，跳过 GPU 推理。
* 缓存使用 Python 内置 ``sqlite3``（零新依赖），WAL 模式确保多进程安全。
* 支持 TTL（单位秒，``None`` = 永不过期）和 ``invalidate_cache()`` 手动清除。

快速上手
--------
::

    from src.infra.llm_service import CachedLLMService

    svc = CachedLLMService.from_engine_config(
        model_path="./models/qwen.gguf",
        cache_dir="./cache/llm",
        cache_ttl_seconds=None,   # 永不过期
    )
    svc.load()
    reply = svc.generate("请说明附子的毒性机制。")
    svc.unload()
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from src.infra.cache_service import (
    LLMDiskCache as _DiskCache,  # noqa: F401  re-export alias
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 抽象接口
# ─────────────────────────────────────────────────────────────────────────────


class LLMService(ABC):
    """LLM 服务统一接口。

    ``LLMEngine`` 在结构上满足此接口（duck typing），无需显式继承。
    其他实现（如 OpenAI 客户端包装）也可继承此类。
    """

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """执行一次生成推理，返回模型的文本响应。"""

    def load(self) -> None:
        """（可选）初始化/加载资源。默认无操作。"""

    def unload(self) -> None:
        """（可选）释放资源。默认无操作。"""


class APILLMEngine(LLMService):
    """OpenAI 兼容 API 的轻量引擎实现。"""

    def __init__(
        self,
        api_url: str,
        model: str,
        api_key: Optional[str] = None,
        timeout_seconds: float = 60.0,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        extra_headers: Optional[dict[str, str]] = None,
    ):
        self.api_url = str(api_url).strip()
        self.model = str(model).strip()
        self.api_key = str(api_key).strip() if api_key else ""
        self.timeout_seconds = float(timeout_seconds)
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.extra_headers = dict(extra_headers or {})
        self.llm_mode = "api"

        if not self.api_url:
            raise ValueError("api_url 不能为空")
        if not self.model:
            raise ValueError("model 不能为空")

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        return headers

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        req = urllib_request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"LLM API HTTP 错误: status={exc.code}, detail={detail}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"LLM API 请求失败: {exc.reason}") from exc

        data = json.loads(body)

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise RuntimeError("API 响应缺少 choices 字段")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("API 响应缺少有效 message.content")
        return content


# ─────────────────────────────────────────────────────────────────────────────
# CachedLLMService
# ─────────────────────────────────────────────────────────────────────────────


class CachedLLMService(LLMService):
    """
    在任意 LLM engine 前插入 SQLite 磁盘缓存的装饰器服务。

    相同的 (prompt, system_prompt, model, temperature, max_tokens)
    组合将直接从磁盘返回，完全跳过模型推理，大幅缩短研发迭代等待时间。

    Parameters
    ----------
    engine :
        任何拥有 ``generate(prompt, system_prompt) -> str`` 方法的对象，
        典型值为 ``LLMEngine`` 实例。
    cache_dir :
        磁盘缓存目录，默认 ``./cache/llm``。
    cache_ttl_seconds :
        缓存条目有效期（秒）。``None`` 表示永不过期。
    cache_enabled :
        全局开关，为 ``False`` 时退化为纯透传，方便临时绕过缓存。
    """

    def __init__(
        self,
        engine: Any,
        cache_dir: str | Path = "./cache/llm",
        cache_ttl_seconds: Optional[float] = None,
        cache_enabled: bool = True,
    ):
        self._engine = engine
        self._cache_enabled = cache_enabled
        self._cache = _DiskCache(cache_dir, ttl_seconds=cache_ttl_seconds) if cache_enabled else None
        self._hits = 0
        self._misses = 0

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def load(self) -> None:
        """透传到底层 engine。"""
        if hasattr(self._engine, "load"):
            self._engine.load()

    def unload(self) -> None:
        """透传到底层 engine。"""
        if hasattr(self._engine, "unload"):
            self._engine.unload()

    # ── 核心接口 ──────────────────────────────────────────────────────────

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """先查磁盘缓存，命中则直接返回；未命中则调用 engine 并缓存结果。"""
        if not self._cache_enabled or self._cache is None:
            return self._engine.generate(prompt, system_prompt)

        model_id = self._resolve_model_id()
        temperature = float(getattr(self._engine, "temperature", 0.3))
        max_tokens = int(getattr(self._engine, "max_tokens", 1024))

        key = _DiskCache.make_key(prompt, system_prompt, model_id, temperature, max_tokens)

        cached = self._cache.get(key)
        if cached is not None:
            self._hits += 1
            logger.debug("LLM 缓存命中 (key=%.16s…, hits=%d)", key, self._hits)
            return cached

        self._misses += 1
        logger.debug("LLM 缓存未命中，调用模型推理… (misses=%d)", self._misses)
        response = self._engine.generate(prompt, system_prompt)
        self._cache.put(key, response, prompt, system_prompt, model_id, temperature, max_tokens)
        return response

    def _resolve_model_id(self) -> str:
        mode = str(getattr(self._engine, "llm_mode", "local"))
        raw_model = (
            getattr(self._engine, "model_path", None)
            or getattr(self._engine, "model", None)
            or getattr(self._engine, "model_name", None)
            or "unknown"
        )
        return f"{mode}:{raw_model}"

    # ── 便捷透传（TCM helper methods 委托给底层 engine）─────────────────

    def __getattr__(self, name: str) -> Any:
        """透传所有未定义属性/方法到底层 engine（如 TCM 科研便捷方法）。"""
        return getattr(self._engine, name)

    # ── 缓存管理 ──────────────────────────────────────────────────────────

    def cache_stats(self) -> dict:
        """返回本次运行的缓存命中统计与磁盘缓存状态。"""
        stats: dict = {
            "session_hits": self._hits,
            "session_misses": self._misses,
            "cache_enabled": self._cache_enabled,
        }
        if self._cache:
            stats.update(self._cache.stats())
        return stats

    def invalidate_cache(self) -> int:
        """清除全部磁盘缓存，返回删除行数。"""
        if self._cache:
            deleted = self._cache.invalidate()
            logger.info("LLM 磁盘缓存已清除，共删除 %d 条。", deleted)
            return deleted
        return 0

    # ── 工厂方法 ──────────────────────────────────────────────────────────

    @classmethod
    def from_engine_config(
        cls,
        model_path: Optional[str] = None,
        **engine_options: Any,
    ) -> "CachedLLMService":
        """
        便捷工厂：直接从 engine 参数创建 ``CachedLLMService``。

        示例::

            svc = CachedLLMService.from_engine_config(
                model_path="./models/qwen.gguf",
                cache_dir="./cache/llm",
            )
        """
        # 延迟导入，避免 llama-cpp-python 未安装时影响其他模块
        from src.llm.llm_engine import LLMEngine  # noqa: PLC0415

        n_gpu_layers = int(engine_options.get("n_gpu_layers", -1))
        n_ctx = int(engine_options.get("n_ctx", 4096))
        temperature = float(engine_options.get("temperature", 0.3))
        max_tokens = int(engine_options.get("max_tokens", 1024))
        verbose = bool(engine_options.get("verbose", False))
        cache_dir = engine_options.get("cache_dir", "./cache/llm")
        cache_ttl_seconds = engine_options.get("cache_ttl_seconds", None)
        cache_enabled = bool(engine_options.get("cache_enabled", True))

        engine = LLMEngine(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            temperature=temperature,
            max_tokens=max_tokens,
            verbose=verbose,
        )
        return cls(engine, cache_dir=cache_dir,
                   cache_ttl_seconds=cache_ttl_seconds,
                   cache_enabled=cache_enabled)

    @classmethod
    def from_api_config(
        cls,
        api_url: str,
        model: str,
        **api_options: Any,
    ) -> "CachedLLMService":
        """便捷工厂：从 OpenAI 兼容 API 配置创建服务。"""
        api_key = api_options.get("api_key")
        timeout_seconds = float(api_options.get("timeout_seconds", 60.0))
        temperature = float(api_options.get("temperature", 0.3))
        max_tokens = int(api_options.get("max_tokens", 1024))
        cache_dir = api_options.get("cache_dir", "./cache/llm")
        cache_ttl_seconds = api_options.get("cache_ttl_seconds", None)
        cache_enabled = bool(api_options.get("cache_enabled", True))
        extra_headers = api_options.get("extra_headers")

        engine = APILLMEngine(
            api_url=api_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_headers=extra_headers,
        )
        return cls(
            engine,
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
            cache_enabled=cache_enabled,
        )

    @classmethod
    def from_config(cls, llm_config: dict, gap_config: Optional[dict] = None) -> "CachedLLMService":
        """统一工厂：根据 mode 选择 local/api 引擎。"""
        gc = gap_config or {}
        lc = llm_config or {}

        mode = str(gc.get("mode") or lc.get("mode") or "local").strip().lower()
        cache_dir = lc.get("cache_dir", "./cache/llm")
        cache_ttl_seconds = lc.get("cache_ttl_seconds", None)
        cache_enabled = bool(lc.get("cache_enabled", True))

        if mode == "api":
            api_url = gc.get("api_url") or lc.get("api_url") or lc.get("api_base_url")
            model = gc.get("api_model") or gc.get("model") or lc.get("api_model") or lc.get("model") or lc.get("name")
            if not api_url:
                raise ValueError("API 模式缺少 api_url/api_base_url 配置")
            if not model:
                raise ValueError("API 模式缺少 model/api_model 配置")
            api_key = gc.get("api_key") or lc.get("api_key")
            timeout_seconds = float(gc.get("timeout_seconds", lc.get("timeout_seconds", 60.0)))
            temperature = float(gc.get("temperature", lc.get("temperature", 0.3)))
            max_tokens = int(gc.get("max_tokens", lc.get("max_tokens", 1024)))
            return cls.from_api_config(
                api_url=api_url,
                model=model,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                max_tokens=max_tokens,
                cache_dir=cache_dir,
                cache_ttl_seconds=cache_ttl_seconds,
                cache_enabled=cache_enabled,
            )

        return cls.from_engine_config(
            model_path=gc.get("model_path") or lc.get("path"),
            n_gpu_layers=int(gc.get("n_gpu_layers", -1)),
            n_ctx=int(gc.get("n_ctx", 4096)),
            temperature=float(gc.get("temperature", lc.get("temperature", 0.15))),
            max_tokens=int(gc.get("max_tokens", lc.get("max_tokens", 1024))),
            verbose=bool(gc.get("verbose", False)),
            cache_dir=cache_dir,
            cache_ttl_seconds=cache_ttl_seconds,
            cache_enabled=cache_enabled,
        )

    @classmethod
    def from_gap_config(cls, gap_config: dict, llm_config: Optional[dict] = None) -> "CachedLLMService":
        """
        从 ``config.yml`` 的 ``clinical_gap_analysis`` 节点创建服务。

        Parameters
        ----------
        gap_config :
            ``self.config.get("clinical_gap_analysis", {})`` 返回的字典。
        llm_config :
            ``config["models"]["llm"]`` 或 ``None``（使用默认值）。
        """
        lc = llm_config or {}
        return cls.from_config(lc, gap_config=gap_config)
