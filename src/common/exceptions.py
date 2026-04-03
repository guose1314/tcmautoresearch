# src/common/exceptions.py
"""TCM 异常层次结构。"""


class TCMBaseError(Exception):
    """所有 TCM 系统异常的基类。"""


class TCMConfigError(TCMBaseError):
    """配置错误。"""


class TCMDataError(TCMBaseError):
    """数据处理错误。"""


class TCMHTTPError(TCMBaseError):
    """HTTP 请求错误。"""


class TCMModuleError(TCMBaseError):
    """模块运行时错误。"""


class TCMParseError(TCMBaseError):
    """解析错误（XML / JSON / YAML 等）。"""


class TCMTimeoutError(TCMBaseError):
    """超时错误。"""


class TCMValidationError(TCMBaseError):
    """输入验证错误。"""
