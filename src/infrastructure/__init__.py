"""BC6: 平台基础设施导出（延迟导入优化）。"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config_loader import (
        AppSettings,
        ConfigCenter,
        ConfigManager,
        load_secret_section,
        load_settings,
        load_settings_section,
    )
    from .monitoring import MonitoringService
    from .persistence import (
        Base,
        DatabaseManager,
        Document,
        Entity,
        EntityRelationship,
        EntityTypeEnum,
        LogStatusEnum,
        PersistenceService,
        ProcessingLog,
        ProcessingStatistics,
        ProcessStatusEnum,
        QualityMetrics,
        RelationshipCategoryEnum,
        RelationshipType,
        ResearchAnalysis,
        ResearchRecord,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "AppSettings": (".config_loader", "AppSettings"),
    "ConfigCenter": (".config_loader", "ConfigCenter"),
    "ConfigManager": (".config_loader", "ConfigManager"),
    "load_secret_section": (".config_loader", "load_secret_section"),
    "load_settings": (".config_loader", "load_settings"),
    "load_settings_section": (".config_loader", "load_settings_section"),
    "MonitoringService": (".monitoring", "MonitoringService"),
    "Base": (".persistence", "Base"),
    "DatabaseManager": (".persistence", "DatabaseManager"),
    "Document": (".persistence", "Document"),
    "Entity": (".persistence", "Entity"),
    "EntityRelationship": (".persistence", "EntityRelationship"),
    "EntityTypeEnum": (".persistence", "EntityTypeEnum"),
    "LogStatusEnum": (".persistence", "LogStatusEnum"),
    "PersistenceService": (".persistence", "PersistenceService"),
    "ProcessingLog": (".persistence", "ProcessingLog"),
    "ProcessingStatistics": (".persistence", "ProcessingStatistics"),
    "ProcessStatusEnum": (".persistence", "ProcessStatusEnum"),
    "QualityMetrics": (".persistence", "QualityMetrics"),
    "RelationshipCategoryEnum": (".persistence", "RelationshipCategoryEnum"),
    "RelationshipType": (".persistence", "RelationshipType"),
    "ResearchAnalysis": (".persistence", "ResearchAnalysis"),
    "ResearchRecord": (".persistence", "ResearchRecord"),
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