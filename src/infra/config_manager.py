"""
src/infra/config_manager.py
已迁移至 src/infrastructure/config_loader.py — 此文件仅保留向后兼容导入。
"""
from src.infrastructure.config_loader import ConfigManager  # noqa: F401

__all__ = ["ConfigManager"]
