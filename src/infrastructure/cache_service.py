# src/infrastructure/cache_service.py
"""
DiskCacheStore — 通用 SQLite 磁盘缓存服务

架构位置
--------
``src/infrastructure/cache_service.py`` 是基础设施层的独立缓存组件，
不依赖任何上层业务模块（LLM、词典、研究流程等均可复用）。

设计要点
--------
* 纯 stdlib 实现（``sqlite3 / hashlib / threading`` — 零额外依赖）。
* 每线程独立 ``sqlite3.Connection``，WAL 日志模式，支持多进程并发读写。
* **Namespace 隔离**：不同功能（llm / embed / pipeline …）使用同一数据库
  文件的不同表，互不影响且易于统一管理。
* 支持 TTL（秒级，``None`` = 永不过期）与手动 ``invalidate()``。
* ``make_key(*parts)`` 对任意字符串组合生成 SHA-256 确定性键，供调用方
  构造业务特定的缓存键策略。

示例
----
::

    from src.infrastructure.cache_service import DiskCacheStore

    cache = DiskCacheStore(cache_dir="./cache", namespace="llm")
    key = DiskCacheStore.make_key("model:qwen", "temp:0.3", prompt_text)
    if (hit := cache.get(key)) is not None:
        return hit
    result = expensive_call(prompt_text)
    cache.put(key, result, meta={"model": "qwen", "temperature": 0.3})
    return result
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DDL 模板（使用 {table} 占位符，按 namespace 动态渲染）
# ─────────────────────────────────────────────────────────────────────────────

_DDL_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {table} (
    cache_key   TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    created_at  REAL NOT NULL,
    meta_json   TEXT NOT NULL DEFAULT '{{}}'
);
CREATE INDEX IF NOT EXISTS idx_{table}_created ON {table}(created_at);
"""


def _safe_table(namespace: str) -> str:
    """将 namespace 转换为合法 SQLite 表名。

    统一加 ``cache_`` 前缀，避免与 SQL 保留字（default / limit / group …）冲突。
    """
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in namespace)
    if not cleaned:
        cleaned = "ns"
    return "cache_" + cleaned


# ─────────────────────────────────────────────────────────────────────────────
# DiskCacheStore
# ─────────────────────────────────────────────────────────────────────────────


class DiskCacheStore:
    """
    通用 SQLite 磁盘缓存，支持 namespace 隔离与可选 TTL。

    Parameters
    ----------
    cache_dir :
        缓存数据库所在目录（不存在时自动创建）。
    namespace :
        逻辑分区名，默认 ``"default"``。
        不同 namespace 使用同一 ``cache_store.db`` 文件中的不同表。
    db_filename :
        数据库文件名，默认 ``"cache_store.db"``。
    ttl_seconds :
        条目有效时长（秒）；``None`` 表示永不过期。
    """

    def __init__(
        self,
        cache_dir: str | Path = "./cache",
        namespace: str = "default",
        db_filename: str = "cache_store.db",
        ttl_seconds: Optional[float] = None,
    ):
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / db_filename
        self._table = _safe_table(namespace)
        self._ttl = ttl_seconds
        self._local = threading.local()
        self._init_db()
        logger.debug(
            "DiskCacheStore ready: db=%s namespace=%s ttl=%s",
            self._db_path, namespace, ttl_seconds,
        )

    # ── 连接 & DDL ────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """每线程独立 Connection（WAL 模式）。"""
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(str(self._db_path), timeout=10, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        with conn:
            yield conn.cursor()

    def _init_db(self) -> None:
        ddl = _DDL_TEMPLATE.format(table=self._table)
        with self._cursor() as cur:
            cur.executescript(ddl)

    # ── 静态工具 ──────────────────────────────────────────────────────────

    @staticmethod
    def make_key(*parts: str) -> str:
        """
        对任意字符串组成的列表生成确定性 SHA-256 缓存键。

        调用方可以自由组织键的构成，例如::

            DiskCacheStore.make_key("llm", model_path, str(temperature), prompt)
        """
        raw = "\x00".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── 读写 API ──────────────────────────────────────────────────────────

    def get(self, cache_key: str) -> Optional[str]:
        """
        读取缓存值。

        Returns
        -------
        str | None
            命中时返回缓存字符串；未命中或已过期返回 ``None``。
        """
        with self._cursor() as cur:
            row = cur.execute(
                f"SELECT value, created_at FROM {self._table} WHERE cache_key = ?",  # noqa: S608
                (cache_key,),
            ).fetchone()

        if row is None:
            return None

        value, created_at = row
        if self._ttl is not None and (time.time() - created_at) > self._ttl:
            self._delete(cache_key)
            return None

        return value

    def put(
        self,
        cache_key: str,
        value: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        写入/更新缓存。

        Parameters
        ----------
        cache_key :
            由 ``make_key()`` 或调用方构造的缓存键。
        value :
            要缓存的字符串（如 LLM 响应、序列化结果等）。
        meta :
            任意附加元数据（JSON 可序列化），用于调试与审计。
        """
        meta_str = json.dumps(meta or {}, ensure_ascii=False)
        with self._cursor() as cur:
            cur.execute(
                f"""
                INSERT OR REPLACE INTO {self._table}
                    (cache_key, value, created_at, meta_json)
                VALUES (?, ?, ?, ?)
                """,  # noqa: S608
                (cache_key, value, time.time(), meta_str),
            )

    def _delete(self, cache_key: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE cache_key = ?",  # noqa: S608
                (cache_key,),
            )

    def invalidate(self) -> int:
        """清除该 namespace 下所有缓存条目，返回删除行数。"""
        with self._cursor() as cur:
            cur.execute(f"DELETE FROM {self._table}")  # noqa: S608
            deleted = cur.rowcount
        logger.info("DiskCacheStore[%s] 已清除 %d 条。", self._table, deleted)
        return deleted

    # ── 统计 ─────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回当前 namespace 的缓存统计信息。"""
        with self._cursor() as cur:
            total = cur.execute(
                f"SELECT COUNT(*) FROM {self._table}"  # noqa: S608
            ).fetchone()[0]
            oldest = cur.execute(
                f"SELECT MIN(created_at) FROM {self._table}"  # noqa: S608
            ).fetchone()[0]
        return {
            "namespace": self._table,
            "total_entries": total,
            "oldest_entry": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
            "ttl_seconds": self._ttl,
            "db_path": str(self._db_path),
        }

    # ── 便捷属性（供 llm_service 兼容访问）──────────────────────────────

    @property
    def db_path(self) -> str:
        return str(self._db_path)


# ─────────────────────────────────────────────────────────────────────────────
# LLMDiskCache — LLM 专用子类（含 LLM 特定键构造方法）
# ─────────────────────────────────────────────────────────────────────────────


class LLMDiskCache(DiskCacheStore):
    """
    LLM 推理结果专用磁盘缓存。

    在 ``DiskCacheStore`` 基础上提供 ``make_llm_key()`` 与 ``put_llm()``
    方法，封装 LLM 特定的键构造逻辑（model × temperature × max_tokens ×
    system_prompt × prompt）。

    也是原 ``_DiskCache`` 的向后兼容替代（同名方法签名相同）。
    """

    def __init__(
        self,
        cache_dir: str | Path = "./cache/llm",
        ttl_seconds: Optional[float] = None,
    ):
        super().__init__(
            cache_dir=cache_dir,
            namespace="llm",
            db_filename="llm_cache.db",
            ttl_seconds=ttl_seconds,
        )

    # ── LLM 专用接口 ──────────────────────────────────────────────────────

    @staticmethod
    def make_llm_key(
        prompt: str,
        system_prompt: str,
        model_id: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """基于 LLM 推理参数生成确定性缓存键（SHA-256），兼容原 ``make_key`` 签名。"""
        raw = json.dumps(
            {
                "p": prompt,
                "s": system_prompt,
                "m": model_id,
                "t": round(temperature, 6),
                "mt": max_tokens,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # 保持对原 _DiskCache.make_key 的调用兼容
    @staticmethod
    def make_key(  # type: ignore[override]
        prompt: str,
        system_prompt: str,
        model_id: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """``make_llm_key`` 的别名，与原 ``_DiskCache.make_key`` 签名完全一致。"""
        return LLMDiskCache.make_llm_key(prompt, system_prompt, model_id, temperature, max_tokens)

    def put_llm(
        self,
        cache_key: str,
        response: str,
        *legacy_args: Any,
        **legacy_kwargs: Any,
    ) -> None:
        """写入 LLM 响应，自动附加 LLM 元数据，兼容原 ``_DiskCache.put`` 签名。"""
        meta = self._build_llm_meta(*legacy_args, **legacy_kwargs)
        self.put(cache_key, response, meta=meta)

    # 供原 _DiskCache 调用方透明切换（旧签名别名）
    def put(  # type: ignore[override]
        self,
        cache_key: str,
        value_or_response: str,
        *legacy_args: Any,
        meta: Optional[dict[str, Any]] = None,
        **legacy_kwargs: Any,
    ) -> None:
        """
        兼容两种调用形式：

        * ``put(key, value, meta={...})`` — 通用形式（继承自 DiskCacheStore）
        * ``put(key, response, prompt, system_prompt, model_id, temperature, max_tokens)``
          — 原 ``_DiskCache.put`` 形式
        """
        has_legacy_llm_args = bool(legacy_args) or any(
            key in legacy_kwargs
            for key in ["prompt", "system_prompt", "model_id", "temperature", "max_tokens"]
        )

        if has_legacy_llm_args:
            combined_meta: dict[str, Any] = self._build_llm_meta(*legacy_args, **legacy_kwargs)
            if meta:
                combined_meta.update(meta)
            super().put(cache_key, value_or_response, meta=combined_meta)
        else:
            super().put(cache_key, value_or_response, meta=meta)

    def _build_llm_meta(self, *legacy_args: Any, **legacy_kwargs: Any) -> dict[str, Any]:
        parsed = self._parse_legacy_llm_args(*legacy_args, **legacy_kwargs)
        return {
            "model_id": parsed["model_id"],
            "temperature": parsed["temperature"],
            "max_tokens": parsed["max_tokens"],
            "system_prompt_len": len(parsed["system_prompt"]),
            "prompt_hash": hashlib.sha256(parsed["prompt"].encode("utf-8")).hexdigest()[:16],
            "cached_at": datetime.now().isoformat(),
        }

    def _parse_legacy_llm_args(self, *legacy_args: Any, **legacy_kwargs: Any) -> dict[str, Any]:
        values = list(legacy_args[:5])
        while len(values) < 5:
            values.append("")

        prompt = str(legacy_kwargs.get("prompt", values[0] or ""))
        system_prompt = str(legacy_kwargs.get("system_prompt", values[1] or ""))
        model_id = str(legacy_kwargs.get("model_id", values[2] or ""))
        temperature = float(legacy_kwargs.get("temperature", values[3] or 0.0))
        max_tokens = int(legacy_kwargs.get("max_tokens", values[4] or 0))
        return {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "model_id": model_id,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 向后兼容别名（原 _DiskCache → LLMDiskCache）
# ─────────────────────────────────────────────────────────────────────────────

#: ``_DiskCache`` 是 ``LLMDiskCache`` 的别名，保持旧引用不破坏。
_DiskCache = LLMDiskCache
