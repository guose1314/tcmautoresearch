# src/llm/llm_service.py
"""
LLM 服务模块 — 向后兼容层

LLMService / CachedLLMService / _DiskCache 的实现已迁移至
src/infra/llm_service.py（基础设施层统一管理）。

本模块重新导出全部公开符号，确保现有的
``from src.llm.llm_service import CachedLLMService``
等导入语句无需修改。
"""
from src.infra import llm_service as _impl

LLMService = _impl.LLMService
APILLMEngine = _impl.APILLMEngine
CachedLLMService = _impl.CachedLLMService
_DiskCache = _impl._DiskCache

__all__ = ["LLMService", "APILLMEngine", "CachedLLMService", "_DiskCache"]
