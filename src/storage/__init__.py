"""
存储模块初始化

提供统一的存储后端管理、事务协调、输出索引和数据保留策略。
"""

# Phase 3: 存储增强
from .backend_factory import StorageBackendFactory
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
from .graph_interface import IKnowledgeGraph, KnowledgeGap
from .neo4j_driver import (
    Neo4jDriver,
    Neo4jEdge,
    Neo4jKnowledgeGraph,
    Neo4jNode,
    create_knowledge_graph,
    entity_to_neo4j_node,
    relationship_to_neo4j_edge,
)
from .output_catalog import ArtifactRecord, OutputCatalog
from .retention import RetentionManager, RetentionReport
from .storage_driver import UnifiedStorageDriver
from .transaction import TransactionCoordinator, TransactionResult, transaction_scope

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
    'Neo4jKnowledgeGraph',
    'create_knowledge_graph',
    'entity_to_neo4j_node',
    'relationship_to_neo4j_edge',

    # Graph Interface
    'IKnowledgeGraph',
    'KnowledgeGap',

    # Unified Driver (legacy)
    'UnifiedStorageDriver',

    # Phase 3: Backend Factory + Transaction
    'StorageBackendFactory',
    'TransactionCoordinator',
    'TransactionResult',
    'transaction_scope',

    # Phase 3: Output Catalog
    'OutputCatalog',
    'ArtifactRecord',

    # Phase 3: Retention Policy
    'RetentionManager',
    'RetentionReport',
]
