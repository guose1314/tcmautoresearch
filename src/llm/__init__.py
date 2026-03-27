# src/llm/__init__.py
"""
本地 LLM 推理模块 — 基于 llama-cpp-python + NVIDIA GPU
"""
from .llm_engine import LLMEngine, setup_cuda_dll_paths

__all__ = ["LLMEngine", "setup_cuda_dll_paths"]
