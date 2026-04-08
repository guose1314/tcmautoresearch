# -*- coding: utf-8 -*-
"""可视化模块 — 知识图谱渲染与交互式展示。"""

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
	"KnowledgeGraphRenderer": ("src.visualization.graph_renderer", "KnowledgeGraphRenderer"),
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
