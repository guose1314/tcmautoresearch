# -*- coding: utf-8 -*-
"""src.common — 公共工具包，为各模块提供通用辅助函数与常量。"""

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "retry": ("src.common.retry_utils", "retry"),
    "HttpClient": ("src.common.http_client", "HttpClient"),
    "tcm_cache": ("src.common.cache", "tcm_cache"),
    "TCMBaseError": ("src.common.exceptions", "TCMBaseError"),
    "ConfigError": ("src.common.exceptions", "ConfigError"),
    "DataError": ("src.common.exceptions", "DataError"),
    "PipelineError": ("src.common.exceptions", "PipelineError"),
    "ModuleError": ("src.common.exceptions", "ModuleError"),
    "LLMError": ("src.common.exceptions", "LLMError"),
    "NetworkError": ("src.common.exceptions", "NetworkError"),
    "ValidationError": ("src.common.exceptions", "ValidationError"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
