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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from src.infra.cache_service import (
    LLMDiskCache as _DiskCache,  # noqa: F401  re-export alias
)
from src.infra.token_budget_policy import (
    apply_token_budget_to_prompt,
    estimate_text_tokens,
)

logger = logging.getLogger(__name__)


_DEFAULT_SMALL_MODEL_OPTIMIZER_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "phase_overrides": {},
    "purpose_overrides": {"publish": "paper_plugin"},
    "benchmark": {
        "output_dir": "./output/phase_benchmarks",
        "compare_baseline": True,
    },
}


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(existing, value)
        else:
            merged[key] = value
    return merged


def _normalize_dossier_sections(dossier_sections: Optional[Dict[str, Any]]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for name, value in (dossier_sections or {}).items():
        text = str(value or "").strip()
        if text:
            normalized[str(name)] = text
    return normalized


def _load_small_model_optimizer_settings(llm_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if llm_config is None:
        from src.infrastructure.config_loader import load_settings_section

        llm_config = load_settings_section("models.llm", default={})

    payload = llm_config.get("small_model_optimizer") if isinstance(llm_config, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    return _deep_merge_dict(_DEFAULT_SMALL_MODEL_OPTIMIZER_SETTINGS, payload)


@dataclass
class PlannedLLMCall:
    """统一的小模型规划调用上下文。"""

    phase: str
    task_type: str
    purpose: str
    llm_service: Any
    enabled: bool = False
    policy_source: str = ""
    cache_hit_likelihood: float = 0.0
    plan: Optional["CallPlan"] = None
    fallback_path: Optional[str] = None
    prompt_application: Dict[str, Any] = field(default_factory=dict)
    role_profile: Optional[Any] = None  # LLMRoleProfile, 可选；J-3 角色化 prompt 池
    kv_cache_descriptor: Optional[Any] = None  # KVCacheDescriptor, 可选；J-3 KV cache

    @property
    def should_call_llm(self) -> bool:
        if self.llm_service is None or not hasattr(self.llm_service, "generate"):
            return False
        if self.plan is None:
            return True
        return self.plan.should_call_llm

    def build_prompt(self, prompt: str, system_prompt: str = "") -> tuple[str, str]:
        role_prefix = ""
        if self.role_profile is not None:
            role_prefix = str(getattr(self.role_profile, "system_prompt", "") or "").strip()

        if self.plan is None:
            merged_system = "\n\n".join(
                section
                for section in (role_prefix, str(system_prompt or ""))
                if section.strip()
            )
            return str(prompt or ""), merged_system

        prompt_sections = []
        if self.plan.context_text.strip():
            prompt_sections.append(f"【规划上下文】\n{self.plan.context_text}")
        prompt_sections.append(str(prompt or ""))
        if self.plan.output_scaffold.strip():
            prompt_sections.append(f"【输出结构约束】\n{self.plan.output_scaffold}")

        merged_prompt = "\n\n".join(section for section in prompt_sections if section.strip())
        merged_system_prompt = "\n\n".join(
            section
            for section in (
                role_prefix,
                str(system_prompt or ""),
                self.plan.reasoning_directive,
            )
            if section.strip()
        )
        return merged_prompt, merged_system_prompt

    def to_metadata(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "phase": self.phase,
            "task_type": self.task_type,
            "purpose": self.purpose,
            "optimizer_enabled": self.enabled,
            "policy_source": self.policy_source,
            "cache_hit_likelihood": round(float(self.cache_hit_likelihood), 4),
            "should_call_llm": self.should_call_llm,
        }
        if self.plan is not None:
            payload.update(
                {
                    "action": self.plan.action,
                    "framework_name": self.plan.framework_name,
                    "layer_used": self.plan.layer_used,
                    "estimated_tokens": self.plan.estimated_tokens,
                    "decision_reason": self.plan.decision_reason,
                    "degradation_hints": dict(self.plan.degradation_hints),
                    "sub_context_count": len(self.plan.sub_contexts),
                    # Phase I-3 命中率 telemetry
                    "template_hit": bool(getattr(self.plan, "template_hit", False)),
                    "budget_hit": bool(getattr(self.plan, "budget_hit", True)),
                    "layer_hit": bool(getattr(self.plan, "layer_hit", False)),
                    "max_layer_available": int(getattr(self.plan, "max_layer_available", -1)),
                    "complexity_tier": str(getattr(self.plan, "complexity_tier", "medium")),
                }
            )
        if self.fallback_path:
            payload["fallback_path"] = self.fallback_path
        if self.prompt_application:
            payload["prompt_application"] = dict(self.prompt_application)
        if self.role_profile is not None:
            payload["role_name"] = str(getattr(self.role_profile, "role_name", "") or "")
            payload["role_temperature"] = float(
                getattr(self.role_profile, "temperature", 0.0) or 0.0
            )
            cache_key = str(getattr(self.role_profile, "kv_cache_key", "") or "")
            if cache_key:
                payload["role_kv_cache_key"] = cache_key
        if self.kv_cache_descriptor is not None:
            payload["kv_cache_valid"] = bool(
                getattr(self.kv_cache_descriptor, "valid", False)
            )
        return payload

    def get_cost_report(self) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            return get_small_model_optimizer().get_cost_report()
        except Exception:
            return None

    def create_proxy(self) -> Any:
        if self.llm_service is None:
            return None
        if isinstance(self.llm_service, PlannedLLMService):
            return self.llm_service
        return PlannedLLMService(self.llm_service, self)


class PlannedLLMService:
    """在实际 generate 之前注入 planner 产出的上下文、框架与预算。"""

    def __init__(self, engine: Any, planned_call: PlannedLLMCall):
        self._engine = engine
        self.planned_call = planned_call

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.planned_call.should_call_llm:
            return ""

        merged_prompt, merged_system_prompt = self.planned_call.build_prompt(prompt, system_prompt)
        budgeted = apply_token_budget_to_prompt(
            merged_prompt,
            system_prompt=merged_system_prompt,
            task=self.planned_call.task_type,
            purpose=self.planned_call.purpose,
            context_window_tokens=getattr(self._engine, "n_ctx", None),
            max_output_tokens=getattr(self._engine, "max_tokens", None),
        )
        self.planned_call.prompt_application = {
            "trimmed": bool(budgeted.trimmed),
            "input_budget_tokens": int(budgeted.input_budget_tokens),
            "total_input_tokens_before": int(budgeted.total_input_tokens_before),
            "total_input_tokens_after": int(budgeted.total_input_tokens_after),
            "resolution_source": budgeted.resolution_source,
            "task": budgeted.task,
            "purpose": budgeted.purpose,
        }

        response = self._engine.generate(budgeted.user_prompt, budgeted.system_prompt)
        if self.planned_call.enabled:
            try:
                get_small_model_optimizer().invocation_strategy.record_completion(
                    estimate_text_tokens(str(response or ""))
                )
            except Exception:
                logger.debug("记录 planner output tokens 失败", exc_info=True)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)


def prepare_planned_llm_call(
    *,
    phase: str,
    task_type: str,
    dossier_sections: Optional[Dict[str, Any]] = None,
    llm_engine: Any = None,
    purpose: Optional[str] = None,
    template_preferences: Optional[Dict[str, float]] = None,
    cache_hit_likelihood: float = 0.0,
    retry_count: int = 0,
    llm_config: Optional[Dict[str, Any]] = None,
    role: Optional[str] = None,
    kv_cache_descriptor: Any = None,
) -> PlannedLLMCall:
    """为一次业务侧 LLM 调用准备统一 planner 上下文。

    role / kv_cache_descriptor 为 J-3 引入：
      role: LLMRoleProfile.role_name；命中则把角色 system_prompt 注入。
      kv_cache_descriptor: KVCacheDescriptor，仅作元数据透传，由调用方负责
        在加载 LLMEngine 后实际写入/读取 KV cache 文件。
    """

    role_profile = None
    if role:
        from src.research.llm_role_profile import get_role_profile

        role_profile = get_role_profile(role)

    if llm_config is None:
        from src.infrastructure.config_loader import load_settings_section

        llm_config = load_settings_section("models.llm", default={})

    optimizer_settings = _load_small_model_optimizer_settings(llm_config)
    requested_phase = str(phase or "default")
    requested_purpose = (
        str(purpose or "").strip()
        or str((optimizer_settings.get("purpose_overrides") or {}).get(requested_phase) or "").strip()
        or requested_phase
        or "default"
    )
    planner_enabled = bool(optimizer_settings.get("enabled", True))
    phase_overrides = optimizer_settings.get("phase_overrides") or {}
    if requested_phase in phase_overrides:
        planner_enabled = bool(phase_overrides.get(requested_phase))

    resolved_engine = llm_engine or get_llm_service(requested_purpose, llm_config=llm_config)
    if resolved_engine is None or not hasattr(resolved_engine, "generate"):
        return PlannedLLMCall(
            phase=requested_phase,
            task_type=str(task_type or ""),
            purpose=requested_purpose,
            llm_service=resolved_engine,
            enabled=False,
            policy_source="missing_llm_engine",
            cache_hit_likelihood=cache_hit_likelihood,
            fallback_path="rules_engine",
            role_profile=role_profile,
            kv_cache_descriptor=kv_cache_descriptor,
        )

    normalized_sections = _normalize_dossier_sections(dossier_sections)
    if not planner_enabled or not normalized_sections:
        return PlannedLLMCall(
            phase=requested_phase,
            task_type=str(task_type or ""),
            purpose=requested_purpose,
            llm_service=resolved_engine,
            enabled=False,
            policy_source="models.llm.small_model_optimizer.disabled" if not planner_enabled else "empty_dossier",
            cache_hit_likelihood=cache_hit_likelihood,
            role_profile=role_profile,
            kv_cache_descriptor=kv_cache_descriptor,
        )

    plan = get_small_model_optimizer().prepare_call(
        phase=requested_phase,
        task_type=str(task_type or ""),
        dossier_sections=normalized_sections,
        template_preferences=template_preferences,
        cache_hit_likelihood=cache_hit_likelihood,
        retry_count=retry_count,
    )
    fallback_path = None
    if plan.action == "skip":
        fallback_path = str(plan.degradation_hints.get("fallback") or "rules_engine")
    elif plan.action == "retry_simplified":
        fallback_path = str(plan.degradation_hints.get("step") or "retry_simplified")
    elif plan.action == "decompose":
        fallback_path = "planner_decompose"

    return PlannedLLMCall(
        phase=requested_phase,
        task_type=str(task_type or ""),
        purpose=requested_purpose,
        llm_service=resolved_engine,
        enabled=True,
        policy_source="models.llm.small_model_optimizer",
        cache_hit_likelihood=cache_hit_likelihood,
        plan=plan,
        fallback_path=fallback_path,
        role_profile=role_profile,
        kv_cache_descriptor=kv_cache_descriptor,
    )

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

    def generate_registered(self, prompt_name: str, /, **variables: Any) -> str:
        """基于 Prompt Registry 执行一次结构化 prompt 生成。"""

        from src.infra.prompt_registry import call_registered_prompt

        return call_registered_prompt(self, prompt_name, **variables)

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
        **api_options: Any,
    ):
        self.api_url = str(api_url).strip()
        self.model = str(model).strip()
        raw_api_key = api_options.get("api_key")
        self.api_key = str(raw_api_key).strip() if raw_api_key else ""
        self.timeout_seconds = float(api_options.get("timeout_seconds", 60.0))
        self.temperature = float(api_options.get("temperature", 0.3))
        self.max_tokens = int(api_options.get("max_tokens", 1024))
        self.extra_headers = dict(api_options.get("extra_headers") or {})
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

        def _do_sync_request() -> str:
            try:
                with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8")
            except urllib_error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                raise RuntimeError(f"LLM API HTTP 错误: status={exc.code}, detail={detail}") from exc
            except urllib_error.URLError as exc:
                raise RuntimeError(f"LLM API 请求失败: {exc.reason}") from exc

        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 如果不巧在主事件循环中被调用，我们用 run_coroutine_threadsafe 会死锁，
            # 若能 await 最好，但签名是 sync 的。为避免死锁，这里只能降级退回阻塞或报错
            # 但正确的做法是 web 路由不要写成 async def。
            body = _do_sync_request()
        else:
            # 2. 在大模型推演层接入基于 asyncio 的熔断超时
            # 因为在此线程没有 running loop（Starlette 的线程池 worker），
            # 我们可以启动一个专属的高优先级 event loop 来做超时熔断管理。
            async def _breaker_wrapper():
                # 显式挂入线程中，避免阻塞临时 loop 的内部事件
                return await asyncio.to_thread(_do_sync_request)
            
            try:
                # 开启严格的熔断与上下文超时控制
                body = asyncio.run(
                    asyncio.wait_for(_breaker_wrapper(), timeout=self.timeout_seconds + 5.0)
                )
            except asyncio.TimeoutError:
                raise RuntimeError("LLM 推演超时，已触发基于 asyncio 熔断保护 (Circuit Breaker Timeout)")

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
        purpose: str = "default",
    ):
        self._engine = engine
        self._cache_enabled = cache_enabled
        self._cache = _DiskCache(cache_dir, ttl_seconds=cache_ttl_seconds) if cache_enabled else None
        self._hits = 0
        self._misses = 0
        self._purpose = str(purpose or "default")

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
        budgeted = apply_token_budget_to_prompt(
            str(prompt or ""),
            system_prompt=str(system_prompt or ""),
            purpose=self._purpose,
            context_window_tokens=getattr(self._engine, "n_ctx", None),
            max_output_tokens=getattr(self._engine, "max_tokens", None),
        )
        prompt = budgeted.user_prompt
        system_prompt = budgeted.system_prompt

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
        purpose = str(engine_options.get("purpose") or "default")

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
                   cache_enabled=cache_enabled,
                   purpose=purpose)

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
        purpose = str(api_options.get("purpose") or "default")

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
            purpose=purpose,
        )

    @classmethod
    def from_config(
        cls,
        llm_config: dict,
        gap_config: Optional[dict] = None,
        *,
        purpose: str = "default",
    ) -> "CachedLLMService":
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
                purpose=purpose,
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
            purpose=purpose,
        )

    @classmethod
    def from_gap_config(
        cls,
        gap_config: dict,
        llm_config: Optional[dict] = None,
        *,
        purpose: str = "default",
    ) -> "CachedLLMService":
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
        return cls.from_config(lc, gap_config=gap_config, purpose=purpose)


# ─────────────────────────────────────────────────────────────────────────────
# 全局 LLM 提供者 — 按用途单例化
# ─────────────────────────────────────────────────────────────────────────────

# 预定义用途 → 参数覆盖；不在此表中的 purpose 使用全局 models.llm 原值。
_LLM_PURPOSE_PROFILES: dict[str, dict[str, Any]] = {
    "translation": {"temperature": 0.1, "max_tokens": 2048},
    "paper_plugin": {"temperature": 0.2, "max_tokens": 1500},
}

# purpose → CachedLLMService 单例
_llm_registry: dict[str, CachedLLMService] = {}


def get_llm_service(
    purpose: str = "default",
    *,
    llm_config: Optional[dict] = None,
) -> CachedLLMService:
    """按用途获取 ``CachedLLMService`` 单例。

    首次调用会创建实例并缓存；后续相同 *purpose* 立即返回。

    Parameters
    ----------
    purpose :
        用途标识，如 ``"default"``、``"translation"``、``"paper_plugin"``。
        预定义的 purpose 会自动覆盖 temperature / max_tokens 等参数。
    llm_config :
        可选全局 LLM 配置字典（``config["models"]["llm"]``）。
        不提供时通过 ``config_loader`` 从 ``config.yml`` 读取。

    Returns
    -------
    CachedLLMService
        带磁盘缓存的 LLM 服务实例。
    """
    if purpose in _llm_registry:
        return _llm_registry[purpose]

    # 适配性检查 — §10.1 职责分配策略
    try:
        from src.infra.llm_task_policy import check_suitability
        check_suitability(purpose)
    except Exception:  # pragma: no cover — 策略模块不可用时静默
        pass

    if llm_config is None:
        from src.infrastructure.config_loader import load_settings_section
        llm_config = load_settings_section("models.llm", default={})

    overrides = _LLM_PURPOSE_PROFILES.get(purpose, {})
    merged: dict[str, Any] = {**llm_config, **overrides}

    service = CachedLLMService.from_config(merged, purpose=purpose)
    _llm_registry[purpose] = service
    return service


def reset_llm_registry() -> None:
    """清空 provider 单例缓存（测试用）。"""
    _llm_registry.clear()


# ── Phase E: 小模型优化器单例 ────────────────────────────────────────────

_small_model_optimizer: Optional["SmallModelOptimizer"] = None  # type: ignore[name-defined]


def get_small_model_optimizer() -> "SmallModelOptimizer":  # type: ignore[name-defined]
    """获取 SmallModelOptimizer 单例（懒初始化）。

    Returns
    -------
    SmallModelOptimizer
        Phase E 统一优化协调器。
    """
    global _small_model_optimizer
    if _small_model_optimizer is None:
        from src.infra.small_model_optimizer import SmallModelOptimizer
        from src.infrastructure.config_loader import load_settings_section

        llm_config = load_settings_section("models.llm", default={})
        _small_model_optimizer = SmallModelOptimizer.from_config(llm_config)
    return _small_model_optimizer


def reset_small_model_optimizer() -> None:
    """重置优化器单例（测试用）。"""
    global _small_model_optimizer
    _small_model_optimizer = None
