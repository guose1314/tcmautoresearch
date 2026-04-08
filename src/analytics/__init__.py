"""Analytics sub-package — DataMiner and related analysis utilities."""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .data_miner import DataMiner

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
	"DataMiner": (".data_miner", "DataMiner"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
	if name in _LAZY_IMPORTS:
		module_path, attr = _LAZY_IMPORTS[name]
		mod = _importlib.import_module(module_path, __name__)
		val = getattr(mod, attr)
		globals()[name] = val
		return val
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
