# src/infrastructure/llm_gateway.py
"""
LLMGateway — 统一 LLM 调用网关

架构位置
--------
基础设施层的 LLM 统一入口。所有业务模块（AI 助手、假说引擎、论文写作等）
通过 ``LLMGateway`` 调用 LLM，不再直接依赖 ``LLMEngine`` 或 ``CachedLLMService``。

设计目标
--------
* 封装 prompt 构建、token 限制、结果解析、缓存、重试
* 支持 ``generate`` （文本）、``generate_structured``（结构化 JSON）、``embed``（向量化）
* 后端可为本地 GGUF 模型（LLMEngine）或远程 API（APILLMEngine），对调用方透明
* 故障时返回明确错误，不抛出未预期异常

用法
----
::

    from src.infrastructure.llm_gateway import LLMGateway

    gw = LLMGateway()              # 自动读取 config.yml
    gw.load()                      # 加载模型（本地模式）
    reply = gw.generate("请说明附子的毒性机制。")
    data  = gw.generate_structured(prompt, schema=MyModel)
    vecs  = gw.embed(["人参", "黄芪"])
    gw.unload()
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Type

logger = logging.getLogger(__name__)


class LLMGateway:
    """统一 LLM 调用网关。

    Parameters
    ----------
    engine : object | None
        底层推理引擎实例，需具备 ``generate(prompt, system_prompt=...)`` 方法。
        为 ``None`` 时，首次调用 ``load()`` 将根据配置自动创建引擎。
    cache_enabled : bool
        是否启用磁盘缓存（默认 ``True``）。
    cache_dir : str
        缓存目录路径。
    cache_ttl_seconds : int | None
        缓存 TTL，``None`` = 永不过期。
    config : dict | None
        从 config.yml 读取的 ``models.llm`` 配置节。
    """

    def __init__(
        self,
        engine: Optional[Any] = None,
        *,
        cache_enabled: bool = True,
        cache_dir: str = "./cache/llm",
        cache_ttl_seconds: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._engine = engine
        self._cached_service: Optional[Any] = None
        self._embedding_model: Optional[Any] = None
        self._config = config or {}
        self._cache_enabled = cache_enabled
        self._cache_dir = cache_dir
        self._cache_ttl = cache_ttl_seconds
        self._loaded = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """加载底层推理引擎。

        如果未提供 engine，将尝试从配置自动创建 LLMEngine。
        """
        if self._loaded:
            return

        if self._engine is None:
            self._engine = self._create_engine_from_config()

        if self._engine is not None and hasattr(self._engine, "load"):
            try:
                self._engine.load()
            except Exception:
                logger.warning("LLM 引擎 load() 失败，将在首次调用时重试")

        # 包装缓存层
        if self._cache_enabled and self._engine is not None:
            try:
                from src.infrastructure.llm_service import CachedLLMService
                self._cached_service = CachedLLMService(
                    engine=self._engine,
                    cache_dir=self._cache_dir,
                    cache_ttl_seconds=self._cache_ttl,
                )
            except Exception as exc:
                logger.warning("缓存服务初始化失败，将直接调用引擎: %s", exc)

        self._loaded = True
        logger.info("LLMGateway 初始化完成 (engine=%s, cache=%s)",
                     type(self._engine).__name__ if self._engine else "None",
                     self._cache_enabled)

    def unload(self) -> None:
        """释放模型内存。"""
        if self._engine is not None and hasattr(self._engine, "unload"):
            try:
                self._engine.unload()
            except Exception:
                pass
        self._engine = None
        self._cached_service = None
        self._loaded = False
        logger.info("LLMGateway 已卸载")

    @property
    def is_loaded(self) -> bool:
        """返回引擎是否已加载。"""
        return self._loaded and self._engine is not None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Literal["text", "json"] = "text",
    ) -> str:
        """生成文本回复。

        Parameters
        ----------
        prompt : str
            用户提示词。
        system_prompt : str
            系统提示词（可选）。
        temperature : float | None
            采样温度，``None`` 使用引擎默认值。
        max_tokens : int | None
            最大生成 token 数。
        response_format : "text" | "json"
            当为 ``"json"`` 时，在 system_prompt 中追加 JSON 格式约束。

        Returns
        -------
        str
            模型生成的文本。

        Raises
        ------
        RuntimeError
            引擎未加载或生成失败。
        """
        if not self._loaded:
            self.load()

        if self._engine is None:
            raise RuntimeError("LLM 引擎未加载，请检查模型路径和依赖配置。")

        # JSON 模式：追加格式约束
        if response_format == "json":
            json_hint = "\n\n请以严格的 JSON 格式输出，不要添加 JSON 以外的任何文字。"
            system_prompt = (system_prompt + json_hint) if system_prompt else json_hint.strip()

        # 优先使用缓存服务
        service = self._cached_service or self._engine

        try:
            # 支持不同引擎的参数签名
            if hasattr(service, "generate"):
                kwargs: Dict[str, Any] = {}
                if system_prompt:
                    kwargs["system_prompt"] = system_prompt
                return service.generate(prompt, **kwargs)
            raise RuntimeError("引擎不支持 generate() 方法")
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("LLM 生成失败: %s", exc)
            raise RuntimeError(f"LLM 生成失败: {exc}") from exc

    def generate_structured(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        schema: Optional[Type] = None,
        fallback: Optional[Any] = None,
    ) -> Any:
        """生成结构化 JSON 输出。

        尝试让 LLM 输出 JSON 并解析。如果提供了 ``schema``（Pydantic BaseModel 子类），
        将尝试用该模型验证输出。解析失败时返回 ``fallback``。

        Parameters
        ----------
        prompt : str
            用户提示词。
        system_prompt : str
            系统提示词。
        schema : type[BaseModel] | None
            Pydantic 模型类，用于验证输出结构。
        fallback : Any
            解析失败时的返回值。

        Returns
        -------
        dict | BaseModel | Any
            解析后的结构化数据，或 fallback 值。
        """
        raw = self.generate(prompt, system_prompt=system_prompt, response_format="json")

        # 尝试提取 JSON 块（LLM 可能在 JSON 前后添加文字）
        json_str = self._extract_json(raw)
        if json_str is None:
            logger.warning("无法从 LLM 输出中提取 JSON:\n%s", raw[:500])
            return fallback

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            logger.warning("JSON 解析失败: %s\n原文: %s", exc, json_str[:500])
            return fallback

        # Pydantic 验证（如果提供了 schema）
        if schema is not None:
            try:
                return schema.model_validate(data)
            except Exception:
                try:
                    # 兼容 Pydantic v1
                    return schema.parse_obj(data)  # type: ignore[attr-defined]
                except Exception as exc2:
                    logger.warning("Pydantic 验证失败: %s", exc2)
                    return data  # 返回原始 dict

        return data

    def embed(self, texts: List[str]) -> List[List[float]]:
        """将文本转换为向量表示。

        Parameters
        ----------
        texts : list[str]
            待向量化的文本列表。

        Returns
        -------
        list[list[float]]
            向量列表，每个向量维度由 embedding 模型决定。
        """
        model = self._get_embedding_model()
        if model is None:
            raise RuntimeError("Embedding 模型未加载，请检查配置。")

        try:
            return model.encode(texts).tolist()
        except Exception as exc:
            logger.error("Embedding 失败: %s", exc)
            raise RuntimeError(f"Embedding 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_engine_from_config(self) -> Optional[Any]:
        """根据配置创建 LLM 推理引擎。"""
        try:
            from src.llm.llm_engine import LLMEngine
            model_path = self._config.get("path") or None
            return LLMEngine(
                model_path=model_path,
                n_gpu_layers=self._config.get("n_gpu_layers", -1),
                n_ctx=self._config.get("n_ctx", 4096),
                temperature=self._config.get("temperature", 0.3),
                max_tokens=self._config.get("max_tokens", 1024),
                verbose=self._config.get("verbose", False),
            )
        except Exception as exc:
            logger.warning("无法创建 LLMEngine: %s", exc)
            return None

    def _get_embedding_model(self) -> Optional[Any]:
        """惰性加载 embedding 模型。"""
        if self._embedding_model is not None:
            return self._embedding_model
        try:
            from sentence_transformers import SentenceTransformer
            model_name = self._config.get("embedding_model", "all-MiniLM-L6-v2")
            self._embedding_model = SentenceTransformer(model_name)
            return self._embedding_model
        except Exception as exc:
            logger.warning("Embedding 模型加载失败: %s", exc)
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从 LLM 输出中提取 JSON 字符串。

        支持 ```json ... ``` 代码块和裸 JSON。
        """
        # 尝试匹配 ```json ... ``` 代码块
        m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if m:
            return m.group(1).strip()

        # 尝试匹配首个 { ... } 或 [ ... ]
        for start_ch, end_ch in [("{", "}"), ("[", "]")]:
            start = text.find(start_ch)
            if start < 0:
                continue
            end = text.rfind(end_ch)
            if end > start:
                return text[start:end + 1]

        return None


# ---------------------------------------------------------------------------
# 便捷工厂
# ---------------------------------------------------------------------------

def create_llm_gateway(config: Optional[Dict[str, Any]] = None) -> LLMGateway:
    """从配置字典创建 LLMGateway 实例。

    Parameters
    ----------
    config : dict | None
        ``models.llm`` 配置节。为 ``None`` 时尝试从 config.yml 加载。

    Returns
    -------
    LLMGateway
    """
    if config is None:
        try:
            from src.infrastructure.config_loader import load_settings_section
            config = load_settings_section("models", "llm") or {}
        except Exception:
            config = {}

    return LLMGateway(
        config=config,
        cache_enabled=config.get("cache_enabled", True),
        cache_dir=config.get("cache_dir", "./cache/llm"),
        cache_ttl_seconds=config.get("cache_ttl_seconds"),
    )
