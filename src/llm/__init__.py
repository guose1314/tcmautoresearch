# src/llm/__init__.py
"""
本地 LLM 推理模块 — 基于 llama-cpp-python + NVIDIA GPU
"""

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "LLMEngine": (".llm_engine", "LLMEngine"),
    "setup_cuda_dll_paths": (".llm_engine", "setup_cuda_dll_paths"),
    "LLMService": ("src.infra.llm_service", "LLMService"),
    "APILLMEngine": ("src.infra.llm_service", "APILLMEngine"),
    "CachedLLMService": ("src.infra.llm_service", "CachedLLMService"),
    "LLMGateway": (".llm_gateway", "LLMGateway"),
    "LLMGatewayRequest": (".llm_gateway", "LLMGatewayRequest"),
    "LLMGatewayResult": (".llm_gateway", "LLMGatewayResult"),
    "generate_with_gateway": (".llm_gateway", "generate_with_gateway"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        if module_path.startswith("."):
            mod = _importlib.import_module(module_path, __name__)
        else:
            mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
