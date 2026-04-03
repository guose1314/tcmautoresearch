# src/common/exceptions.py
"""
统一异常体系 — 为 TCMAutoResearch 提供分层异常类型。

异常层次：
    TCMBaseError
    ├── ConfigError         # 配置相关
    ├── DataError           # 数据加载/验证
    ├── PipelineError       # 管线执行
    ├── ModuleError         # 模块生命周期
    ├── LLMError            # LLM 推理
    ├── NetworkError        # 网络请求
    └── ValidationError     # 输入验证
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class TCMBaseError(Exception):
    """TCMAutoResearch 所有异常的基类。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "TCM_ERROR",
        detail: str = "",
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.detail = detail or message
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": type(self).__name__,
            "code": self.code,
            "message": str(self),
            "detail": self.detail,
            "context": self.context,
        }


class ConfigError(TCMBaseError):
    """配置相关错误（文件缺失、格式错误、值非法等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="CONFIG_ERROR", **kwargs)


class DataError(TCMBaseError):
    """数据加载或验证错误（文件缺失、格式不匹配、数据损坏等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="DATA_ERROR", **kwargs)


class PipelineError(TCMBaseError):
    """管线执行错误（阶段失败、依赖缺失等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="PIPELINE_ERROR", **kwargs)


class ModuleError(TCMBaseError):
    """模块生命周期错误（初始化失败、执行异常、清理错误等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="MODULE_ERROR", **kwargs)


class LLMError(TCMBaseError):
    """LLM 推理错误（模型不可用、超时、格式异常等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="LLM_ERROR", **kwargs)


class NetworkError(TCMBaseError):
    """网络请求错误（连接失败、超时、HTTP 错误等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="NETWORK_ERROR", **kwargs)


class ValidationError(TCMBaseError):
    """输入验证错误（参数缺失、类型错误、范围超出等）。"""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, code="VALIDATION_ERROR", **kwargs)
