"""
src/infra/config_manager.py — **已弃用**

已迁移至 src/infrastructure/config_loader.py。
请改用 ``from src.infrastructure.config_loader import load_settings``。
此文件仅保留向后兼容导入，将在后续版本删除。
"""
import warnings as _w

_w.warn(
    "src.infra.config_manager 已弃用，请改用 "
    "from src.infrastructure.config_loader import load_settings",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.config_loader import ConfigManager  # noqa: F401

__all__ = ["ConfigManager"]
