# src/common/exceptions.py
"""TCM 异常层次结构。"""
from __future__ import annotations

from typing import Any, Dict, Optional


class TCMBaseError(Exception):
    """所有 TCM 系统异常的基类。

    Args:
        message: 错误描述。
        code: 错误码（如 ``"ERR_01"``）。
        detail: 额外说明文字。
        context: 附加上下文字典。
    """

    _default_message: str = ""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "UNKNOWN",
        detail: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.context: Dict[str, Any] = context if context is not None else {}
        full = message or self._default_message
        if code != "UNKNOWN":
            full = f"{full} [{code}]" if full else f"[{code}]"
        if detail:
            full = f"{full} {detail}" if full else detail
        super().__init__(full)

    def __str__(self) -> str:
        return self.args[0] if self.args else ""


class TCMConfigError(TCMBaseError):
    """配置错误。"""
    _default_message = "configuration error"


class TCMDataError(TCMBaseError):
    """数据处理错误。"""
    _default_message = "data error"


class TCMHTTPError(TCMBaseError):
    """HTTP 请求错误。"""
    _default_message = "http error"


class TCMLLMError(TCMBaseError):
    """LLM 调用错误。"""
    _default_message = "llm error"


class TCMModuleError(TCMBaseError):
    """模块运行时错误。"""
    _default_message = "module error"


class TCMNetworkError(TCMHTTPError):
    """网络错误（TCMHTTPError 的子类）。"""
    _default_message = "network error"


class TCMParseError(TCMBaseError):
    """解析错误（XML / JSON / YAML 等）。"""
    _default_message = "parse error"


class TCMPipelineError(TCMBaseError):
    """流程执行错误。"""
    _default_message = "pipeline error"


class TCMTimeoutError(TCMBaseError):
    """超时错误。"""
    _default_message = "timeout error"


class TCMValidationError(TCMBaseError):
    """输入验证错误。"""
    _default_message = "validation error"


# ---------------------------------------------------------------------------
# Short-name aliases for backward compatibility
# ---------------------------------------------------------------------------
ConfigError = TCMConfigError
DataError = TCMDataError
LLMError = TCMLLMError
ModuleError = TCMModuleError
NetworkError = TCMNetworkError
PipelineError = TCMPipelineError
ValidationError = TCMValidationError
