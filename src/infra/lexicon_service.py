# src/infra/lexicon_service.py
"""
LexiconService — 向后兼容层

实现已迁移至 ``src.infrastructure.lexicon_service``。
此模块重新导出全部公开符号，确保现有导入无需修改。
"""
import warnings as _warnings

_warnings.warn(
    "src.infra.lexicon_service 已迁移至 src.infrastructure.lexicon_service，请更新导入路径。",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.lexicon_service import (  # noqa: F401, E402
    LexiconService,
    get_lexicon,
    reset_lexicon,
)

__all__ = ["LexiconService", "get_lexicon", "reset_lexicon"]
