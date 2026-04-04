"""BC6: 平台基础设施导出。"""

from .cache_service import DiskCacheStore, LLMDiskCache, _DiskCache
from .config_loader import (
    AppSettings,
    ConfigCenter,
    load_secret_section,
    load_settings,
    load_settings_section,
)
from .config_manager import ConfigManager
from .event_bus import EventBus
from .lexicon_service import LexiconService, get_lexicon
from .llm_service import APILLMEngine, CachedLLMService, LLMService

# Monitoring and persistence have deep dependency chains that may fail in
# lightweight environments. Import them defensively so the core infra symbols
# remain accessible regardless.
try:
    from .monitoring import MonitoringService
except Exception:  # noqa: BLE001
    MonitoringService = None  # type: ignore[assignment,misc]

try:
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
except Exception:  # noqa: BLE001
    Base = None  # type: ignore[assignment,misc]
    DatabaseManager = None  # type: ignore[assignment,misc]
    Document = None  # type: ignore[assignment,misc]
    Entity = None  # type: ignore[assignment,misc]
    EntityRelationship = None  # type: ignore[assignment,misc]
    EntityTypeEnum = None  # type: ignore[assignment,misc]
    LogStatusEnum = None  # type: ignore[assignment,misc]
    PersistenceService = None  # type: ignore[assignment,misc]
    ProcessingLog = None  # type: ignore[assignment,misc]
    ProcessingStatistics = None  # type: ignore[assignment,misc]
    ProcessStatusEnum = None  # type: ignore[assignment,misc]
    QualityMetrics = None  # type: ignore[assignment,misc]
    RelationshipCategoryEnum = None  # type: ignore[assignment,misc]
    RelationshipType = None  # type: ignore[assignment,misc]
    ResearchAnalysis = None  # type: ignore[assignment,misc]
    ResearchRecord = None  # type: ignore[assignment,misc]

__all__ = [
    "APILLMEngine",
    "AppSettings",
    "Base",
    "CachedLLMService",
    "ConfigCenter",
    "ConfigManager",
    "DatabaseManager",
    "DiskCacheStore",
    "Document",
    "Entity",
    "EntityRelationship",
    "EntityTypeEnum",
    "EventBus",
    "LLMDiskCache",
    "LLMService",
    "LexiconService",
    "LogStatusEnum",
    "MonitoringService",
    "PersistenceService",
    "ProcessStatusEnum",
    "ProcessingLog",
    "ProcessingStatistics",
    "QualityMetrics",
    "RelationshipCategoryEnum",
    "RelationshipType",
    "ResearchAnalysis",
    "ResearchRecord",
    "_DiskCache",
    "get_lexicon",
    "load_secret_section",
    "load_settings",
    "load_settings_section",
]