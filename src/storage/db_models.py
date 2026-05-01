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
LearningInsight = _persistence.LearningInsight
LogStatusEnum = _persistence.LogStatusEnum
ProcessStatusEnum = _persistence.ProcessStatusEnum
ProcessingLog = _persistence.ProcessingLog
ProcessingStatistics = _persistence.ProcessingStatistics
QualityMetrics = _persistence.QualityMetrics
RelationshipCategoryEnum = _persistence.RelationshipCategoryEnum
RelationshipType = _persistence.RelationshipType
ResearchAnalysis = _persistence.ResearchAnalysis
ResearchRecord = _persistence.ResearchRecord

# P3.1 新增
ArtifactTypeEnum = _persistence.ArtifactTypeEnum
PhaseExecution = _persistence.PhaseExecution
PhaseStatusEnum = _persistence.PhaseStatusEnum
ResearchArtifact = _persistence.ResearchArtifact
ResearchSession = _persistence.ResearchSession
SessionStatusEnum = _persistence.SessionStatusEnum

# Phase H / H-2 新增
ReviewAssignment = _persistence.ReviewAssignment

# Phase H / H-3 新增
ReviewDispute = _persistence.ReviewDispute

__all__ = [
    "ArtifactTypeEnum",
    "Base",
    "DatabaseManager",
    "Document",
    "Entity",
    "EntityRelationship",
    "EntityTypeEnum",
    "LearningInsight",
    "LogStatusEnum",
    "PhaseExecution",
    "PhaseStatusEnum",
    "ProcessStatusEnum",
    "ProcessingLog",
    "ProcessingStatistics",
    "QualityMetrics",
    "RelationshipCategoryEnum",
    "RelationshipType",
    "ResearchAnalysis",
    "ResearchArtifact",
    "ResearchRecord",
    "ResearchSession",
    "ReviewAssignment",
    "ReviewDispute",
    "SessionStatusEnum",
]
