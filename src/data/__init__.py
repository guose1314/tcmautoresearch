# src/data/__init__.py
"""
数据包 — 提供中医领域词典、知识库数据等。
"""

from src.data.tcm_lexicon import TCMLexicon, get_lexicon

__all__ = ["TCMLexicon", "get_lexicon"]
