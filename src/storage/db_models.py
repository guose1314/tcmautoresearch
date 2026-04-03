"""storage.db_models 兼容层。

架构 3.0 将 ORM 主体下沉到 src.infrastructure.persistence，
这里保留旧导入路径，避免现有 storage 驱动与测试失效。
"""

from src.infrastructure import persistence as _persistence

Base = _persistence.Base
DatabaseManager = _persistence.DatabaseManager
Document = _persistence.Document
Entity = _persistence.Entity
EntityRelationship = _persistence.EntityRelationship
EntityTypeEnum = _persistence.EntityTypeEnum
LogStatusEnum = _persistence.LogStatusEnum
ProcessStatusEnum = _persistence.ProcessStatusEnum
ProcessingLog = _persistence.ProcessingLog
ProcessingStatistics = _persistence.ProcessingStatistics
QualityMetrics = _persistence.QualityMetrics
RelationshipCategoryEnum = _persistence.RelationshipCategoryEnum
RelationshipType = _persistence.RelationshipType
ResearchAnalysis = _persistence.ResearchAnalysis
ResearchRecord = _persistence.ResearchRecord

__all__ = [
    "Base",
    "DatabaseManager",
    "Document",
    "Entity",
    "EntityRelationship",
    "EntityTypeEnum",
    "LogStatusEnum",
    "ProcessStatusEnum",
    "ProcessingLog",
    "ProcessingStatistics",
    "QualityMetrics",
    "RelationshipCategoryEnum",
    "RelationshipType",
    "ResearchAnalysis",
    "ResearchRecord",
]
