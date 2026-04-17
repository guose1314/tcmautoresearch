"""
存储模块初始化（延迟导入优化）

提供统一的存储后端管理、事务协调、输出索引和数据保留策略。
"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend_factory import StorageBackendFactory
    from .consistency import (
        MODE_DUAL_WRITE,
        MODE_PG_ONLY,
        MODE_SQLITE_FALLBACK,
        MODE_UNINITIALIZED,
        StorageConsistencyState,
        build_consistency_state,
    )
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
    from .transaction import (
        TransactionCoordinator,
        TransactionResult,
        transaction_scope,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Schema
    "get_init_script": (".database_schema", "get_init_script"),
    "get_cleanup_script": (".database_schema", "get_cleanup_script"),
    "get_backup_script": (".database_schema", "get_backup_script"),
    # Models
    "Base": (".db_models", "Base"),
    "DatabaseManager": (".db_models", "DatabaseManager"),
    "Document": (".db_models", "Document"),
    "Entity": (".db_models", "Entity"),
    "EntityRelationship": (".db_models", "EntityRelationship"),
    "RelationshipType": (".db_models", "RelationshipType"),
    "ProcessingStatistics": (".db_models", "ProcessingStatistics"),
    "QualityMetrics": (".db_models", "QualityMetrics"),
    "ResearchAnalysis": (".db_models", "ResearchAnalysis"),
    "ProcessingLog": (".db_models", "ProcessingLog"),
    # Enums
    "EntityTypeEnum": (".db_models", "EntityTypeEnum"),
    "ProcessStatusEnum": (".db_models", "ProcessStatusEnum"),
    "LogStatusEnum": (".db_models", "LogStatusEnum"),
    "RelationshipCategoryEnum": (".db_models", "RelationshipCategoryEnum"),
    # Neo4j
    "Neo4jDriver": (".neo4j_driver", "Neo4jDriver"),
    "Neo4jNode": (".neo4j_driver", "Neo4jNode"),
    "Neo4jEdge": (".neo4j_driver", "Neo4jEdge"),
    "Neo4jKnowledgeGraph": (".neo4j_driver", "Neo4jKnowledgeGraph"),
    "create_knowledge_graph": (".neo4j_driver", "create_knowledge_graph"),
    "entity_to_neo4j_node": (".neo4j_driver", "entity_to_neo4j_node"),
    "relationship_to_neo4j_edge": (".neo4j_driver", "relationship_to_neo4j_edge"),
    # Graph Interface
    "IKnowledgeGraph": (".graph_interface", "IKnowledgeGraph"),
    "KnowledgeGap": (".graph_interface", "KnowledgeGap"),
    # Unified Driver
    "UnifiedStorageDriver": (".storage_driver", "UnifiedStorageDriver"),
    # Backend Factory + Transaction
    "StorageBackendFactory": (".backend_factory", "StorageBackendFactory"),
    "TransactionCoordinator": (".transaction", "TransactionCoordinator"),
    "TransactionResult": (".transaction", "TransactionResult"),
    "transaction_scope": (".transaction", "transaction_scope"),
    # Consistency State
    "StorageConsistencyState": (".consistency", "StorageConsistencyState"),
    "build_consistency_state": (".consistency", "build_consistency_state"),
    "MODE_DUAL_WRITE": (".consistency", "MODE_DUAL_WRITE"),
    "MODE_PG_ONLY": (".consistency", "MODE_PG_ONLY"),
    "MODE_SQLITE_FALLBACK": (".consistency", "MODE_SQLITE_FALLBACK"),
    "MODE_UNINITIALIZED": (".consistency", "MODE_UNINITIALIZED"),
    # Output Catalog
    "OutputCatalog": (".output_catalog", "OutputCatalog"),
    "ArtifactRecord": (".output_catalog", "ArtifactRecord"),
    # Retention Policy
    "RetentionManager": (".retention", "RetentionManager"),
    "RetentionReport": (".retention", "RetentionReport"),
}

# Backward compatibility for legacy diagnostics and tests.
_LAZY_IMPORTS["Database"] = (".db_models", "DatabaseManager")

__all__ = [k for k in _LAZY_IMPORTS if k != "Database"] + ["Database"]


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path, __name__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
