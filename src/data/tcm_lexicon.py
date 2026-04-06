# src/data/tcm_lexicon.py
"""TCM 词典兼容层。

该模块保留历史导入路径 ``src.data.tcm_lexicon``，
并将实现统一桥接到 ``src.infra.lexicon_service``。

兼容导出：
- TCMLexicon（等价于 LexiconService）
- get_lexicon
- reset_lexicon
- load_external_lexicon
- add_runtime_terms
- get_lexicon_stats
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from src.infra.lexicon_service import (
    LexiconService,
)
from src.infra.lexicon_service import (
    get_lexicon as _get_lexicon,
)
from src.infra.lexicon_service import (
    reset_lexicon as _reset_lexicon,
)

# 向后兼容：旧代码将 TCMLexicon 视为主类型
TCMLexicon = LexiconService
reset_lexicon = _reset_lexicon


def get_lexicon() -> TCMLexicon:
    """返回全局词典单例。"""
    return _get_lexicon()


def load_external_lexicon(path: str, word_type: str = "common") -> int:
    """兼容旧接口：从外部文件加载词典词条。"""
    return get_lexicon().load_from_file(path, word_type=word_type)


def add_runtime_terms(word_type: str, words: Iterable[str]) -> Dict[str, Any]:
    """运行时追加词条并返回统计信息。"""
    lex = get_lexicon()
    before = lex.get_vocab_size()
    normalized: List[str] = [str(item).strip() for item in words if str(item).strip()]
    lex.add_words(word_type, normalized)
    after = lex.get_vocab_size()
    return {
        "word_type": word_type,
        "input_count": len(normalized),
        "before_vocab_size": before,
        "after_vocab_size": after,
        "added_delta": max(0, after - before),
    }


def get_lexicon_stats() -> Dict[str, int]:
    """返回词典规模统计。"""
    lex = get_lexicon()
    return {
        "herbs": len(lex.herbs),
        "formulas": len(lex.formulas),
        "syndromes": len(lex.syndromes),
        "theory": len(lex.theory),
        "efficacy": len(lex.efficacy),
        "common_words": len(lex.common_words),
        "total": lex.get_vocab_size(),
    }


__all__ = [
    "TCMLexicon",
    "get_lexicon",
    "reset_lexicon",
    "load_external_lexicon",
    "add_runtime_terms",
    "get_lexicon_stats",
]
