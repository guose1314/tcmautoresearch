"""分层任务缓存：prompt / evidence / artifact。"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from src.infra.cache_service import DiskCacheStore

logger = logging.getLogger(__name__)

DEFAULT_LAYERED_CACHE_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "cache_dir": "./cache/task_layers",
    "prompt": {
        "enabled": True,
        "namespace": "prompt",
        "ttl_seconds": None,
    },
    "evidence": {
        "enabled": True,
        "namespace": "evidence",
        "ttl_seconds": None,
    },
    "artifact": {
        "enabled": True,
        "namespace": "artifact",
        "ttl_seconds": None,
    },
}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
            continue
        merged[key] = value
    return merged


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        normalized = [_json_safe(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    return str(value)


def stable_cache_payload(value: Any) -> Any:
    """将任意对象规整为稳定的 JSON 友好结构。"""

    return _json_safe(value)


def stable_cache_json(value: Any) -> str:
    """生成稳定的 JSON 串，用于缓存 key 与缓存值序列化。"""

    return json.dumps(stable_cache_payload(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@lru_cache(maxsize=1)
def load_layered_cache_settings() -> Dict[str, Any]:
    """读取分层缓存配置。"""

    try:
        from src.infrastructure.config_loader import load_settings_section

        payload = load_settings_section("iteration_cycle.research_pipeline.layered_cache", default={})
    except Exception:
        payload = {}

    resolved = dict(DEFAULT_LAYERED_CACHE_SETTINGS)
    if isinstance(payload, Mapping):
        resolved = _deep_merge(DEFAULT_LAYERED_CACHE_SETTINGS, payload)
    return resolved


def reset_layered_cache_settings_cache() -> None:
    """清空分层缓存配置缓存，供测试使用。"""

    load_layered_cache_settings.cache_clear()
    get_layered_task_cache.cache_clear()


def describe_llm_engine(llm_engine: Any) -> Dict[str, Any]:
    """提取 LLM 引擎的稳定描述，用于 prompt cache key。"""

    engine = getattr(llm_engine, "_engine", llm_engine)
    mode = str(
        getattr(engine, "llm_mode", None)
        or getattr(llm_engine, "llm_mode", None)
        or "local"
    )
    model = (
        getattr(engine, "model_path", None)
        or getattr(engine, "model", None)
        or getattr(engine, "model_name", None)
        or getattr(llm_engine, "model_path", None)
        or getattr(llm_engine, "model", None)
        or getattr(llm_engine, "model_name", None)
        or "unknown"
    )

    temperature = getattr(engine, "temperature", getattr(llm_engine, "temperature", 0.3))
    max_tokens = getattr(engine, "max_tokens", getattr(llm_engine, "max_tokens", 1024))
    try:
        temperature = float(temperature)
    except (TypeError, ValueError):
        temperature = 0.3
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = 1024

    return {
        "mode": mode,
        "model": str(model),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


class LayeredTaskCache:
    """统一管理 prompt / evidence / artifact 三层缓存。"""

    def __init__(self, settings: Optional[Mapping[str, Any]] = None):
        resolved = dict(load_layered_cache_settings() if settings is None else settings)
        self.settings = _deep_merge(DEFAULT_LAYERED_CACHE_SETTINGS, resolved)
        self._stores: Dict[str, DiskCacheStore] = {}

    def is_enabled(self, layer: str) -> bool:
        if not self.settings.get("enabled", True):
            return False
        layer_cfg = self.settings.get(layer) or {}
        if not isinstance(layer_cfg, Mapping):
            return False
        return bool(layer_cfg.get("enabled", True))

    def _get_store(self, layer: str) -> Optional[DiskCacheStore]:
        if not self.is_enabled(layer):
            return None
        if layer not in self._stores:
            layer_cfg = self.settings.get(layer) or {}
            cache_dir = self.settings.get("cache_dir") or DEFAULT_LAYERED_CACHE_SETTINGS["cache_dir"]
            namespace = str(layer_cfg.get("namespace") or layer)
            ttl_seconds = layer_cfg.get("ttl_seconds")
            self._stores[layer] = DiskCacheStore(
                cache_dir=cache_dir,
                namespace=namespace,
                ttl_seconds=ttl_seconds,
            )
        return self._stores[layer]

    def make_key(
        self,
        layer: str,
        task_name: str,
        payload: Any,
        *,
        extra_parts: Optional[Iterable[Any]] = None,
    ) -> str:
        parts = ["layered-cache-v1", layer, task_name, stable_cache_json(payload)]
        for item in extra_parts or ():
            parts.append(stable_cache_json(item))
        return DiskCacheStore.make_key(*(str(part) for part in parts))

    def get_text(
        self,
        layer: str,
        task_name: str,
        payload: Any,
        *,
        extra_parts: Optional[Iterable[Any]] = None,
    ) -> Optional[str]:
        store = self._get_store(layer)
        if store is None:
            return None
        key = self.make_key(layer, task_name, payload, extra_parts=extra_parts)
        return store.get(key)

    def put_text(
        self,
        layer: str,
        task_name: str,
        payload: Any,
        value: str,
        *,
        extra_parts: Optional[Iterable[Any]] = None,
        meta: Optional[Mapping[str, Any]] = None,
    ) -> None:
        store = self._get_store(layer)
        if store is None:
            return
        key = self.make_key(layer, task_name, payload, extra_parts=extra_parts)
        record_meta = {
            "layer": layer,
            "task_name": task_name,
        }
        if isinstance(meta, Mapping):
            record_meta.update(stable_cache_payload(meta))
        store.put(key, str(value), meta=record_meta)

    def get_json(
        self,
        layer: str,
        task_name: str,
        payload: Any,
        *,
        extra_parts: Optional[Iterable[Any]] = None,
    ) -> Optional[Any]:
        raw = self.get_text(layer, task_name, payload, extra_parts=extra_parts)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Layered cache 条目 JSON 解析失败，忽略该命中: layer=%s task=%s", layer, task_name)
            return None

    def put_json(
        self,
        layer: str,
        task_name: str,
        payload: Any,
        value: Any,
        *,
        extra_parts: Optional[Iterable[Any]] = None,
        meta: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.put_text(
            layer,
            task_name,
            payload,
            stable_cache_json(value),
            extra_parts=extra_parts,
            meta=meta,
        )

    def stats(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"enabled": bool(self.settings.get("enabled", True))}
        for layer in ("prompt", "evidence", "artifact"):
            store = self._get_store(layer)
            result[layer] = store.stats() if store is not None else {"enabled": False}
        return result

    def close(self) -> None:
        for store in self._stores.values():
            store.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


@lru_cache(maxsize=1)
def get_layered_task_cache() -> LayeredTaskCache:
    """返回分层任务缓存单例。"""

    return LayeredTaskCache()