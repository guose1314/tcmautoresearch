# src/data/__init__.py
"""
数据包 — 提供中医领域词典、知识库数据等。
"""

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
	"TCMLexicon": ("src.data.tcm_lexicon", "TCMLexicon"),
	"get_lexicon": ("src.data.tcm_lexicon", "get_lexicon"),
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
