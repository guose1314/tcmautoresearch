"""
存储模块初始化
"""

from .database_schema import get_backup_script, get_cleanup_script, get_init_script
from .db_models import (
    Base,
    DatabaseManager,
    Document,
    Entity,
    EntityRelationship,
    EntityTypeEnum,
    LogStatusEnum,
    ProcessingLog,
    ProcessingStatistics,
    ProcessStatusEnum,
    QualityMetrics,
    RelationshipCategoryEnum,
    RelationshipType,
    ResearchAnalysis,
)
from .neo4j_driver import (
    Neo4jDriver,
    Neo4jEdge,
    Neo4jNode,
    entity_to_neo4j_node,
    relationship_to_neo4j_edge,
)
from .storage_driver import UnifiedStorageDriver

# Backward compatibility for legacy diagnostics and tests.
Database = DatabaseManager

__all__ = [
    # Schema
    'get_init_script',
    'get_cleanup_script',
    'get_backup_script',
    
    # Models
    'Base',
    'Database',
    'DatabaseManager',
    'Document',
    'Entity',
    'EntityRelationship',
    'RelationshipType',
    'ProcessingStatistics',
    'QualityMetrics',
    'ResearchAnalysis',
    'ProcessingLog',
    
    # Enums
    'EntityTypeEnum',
    'ProcessStatusEnum',
    'LogStatusEnum',
    'RelationshipCategoryEnum',
    
    # Neo4j
    'Neo4jDriver',
    'Neo4jNode',
    'Neo4jEdge',
    'entity_to_neo4j_node',
    'relationship_to_neo4j_edge',
    
    # Unified Driver
    'UnifiedStorageDriver',
]
