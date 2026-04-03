# -*- coding: utf-8 -*-
"""统一异常体系 — 为各模块提供结构化、可区分的异常类型。"""

from typing import Any, Dict, Optional


class TCMBaseError(Exception):
    """所有 TCM 系统异常的基类。

    Parameters
    ----------
    message : str
        人类可读的错误描述。
    code : str
        机器可读的错误码，如 ``"CFG_MISSING_KEY"``。
    detail : str
        补充说明或建议。
    context : dict | None
        与错误相关的上下文数据。
    """

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "UNKNOWN",
        detail: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail
        self.context = context or {}

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.code != "UNKNOWN":
            parts.append(f"[{self.code}]")
        if self.detail:
            parts.append(self.detail)
        return " ".join(parts)


class ConfigError(TCMBaseError):
    """配置加载或校验失败。"""

    def __init__(self, message: str = "configuration error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class DataError(TCMBaseError):
    """数据加载、解析或验证失败。"""

    def __init__(self, message: str = "data error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class PipelineError(TCMBaseError):
    """研究管线执行异常。"""

    def __init__(self, message: str = "pipeline error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class ModuleError(TCMBaseError):
    """模块生命周期（初始化/执行/清理）异常。"""

    def __init__(self, message: str = "module error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class LLMError(TCMBaseError):
    """LLM 推理调用失败。"""

    def __init__(self, message: str = "LLM error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class NetworkError(TCMBaseError):
    """网络请求失败（超时、连接、HTTP 错误等）。"""

    def __init__(self, message: str = "network error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)


class ValidationError(TCMBaseError):
    """输入参数或数据格式校验失败。"""

    def __init__(self, message: str = "validation error", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
