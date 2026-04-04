# src/infra/config_manager.py
"""
ConfigManager — 向后兼容层

实现已迁移至 ``src.infrastructure.config_manager``。
此模块重新导出全部公开符号，确保现有导入无需修改。
"""
import warnings as _warnings

_warnings.warn(
    "src.infra.config_manager 已迁移至 src.infrastructure.config_manager，请更新导入路径。",
    DeprecationWarning,
    stacklevel=2,
)

from src.infrastructure.config_manager import ConfigManager  # noqa: F401, E402

__all__ = ["ConfigManager"]
