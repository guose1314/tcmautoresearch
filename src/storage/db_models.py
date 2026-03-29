"""
SQLAlchemy ORM模型定义 - PostgreSQL对象映射
中医古籍全自动研究系统
"""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


# ==================== 枚举类型 ====================

class ProcessStatusEnum(str, enum.Enum):
    """文档处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityTypeEnum(str, enum.Enum):
    """实体类型"""
    FORMULA = "formula"
    HERB = "herb"
    SYNDROME = "syndrome"
    EFFICACY = "efficacy"
    PROPERTY = "property"
    TASTE = "taste"
    MERIDIAN = "meridian"
    OTHER = "other"


class RelationshipCategoryEnum(str, enum.Enum):
    """关系类别"""
    COMPOSITION = "composition"
    THERAPEUTIC = "therapeutic"
    PROPERTY = "property"
    SIMILARITY = "similarity"
    OTHER = "other"


class LogStatusEnum(str, enum.Enum):
    """处理日志状态"""
    START = "start"
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"


# ==================== 表模型 ====================

class Document(Base):
    """文档表 - 记录处理的源文件"""
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_file = Column(String(500), nullable=False, unique=True)
    processing_timestamp = Column(DateTime, default=datetime.utcnow)
    objective = Column(String(255), nullable=True)
    raw_text_size = Column(Integer, default=0)
    entities_extracted_count = Column(Integer, default=0)
    process_status = Column(SQLEnum(ProcessStatusEnum), default=ProcessStatusEnum.PENDING)
    quality_score = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")
    statistics = relationship("ProcessingStatistics", back_populates="document", uselist=False)
    quality = relationship("QualityMetrics", back_populates="document", uselist=False)
    analyses = relationship("ResearchAnalysis", back_populates="document", uselist=False)
    logs = relationship("ProcessingLog", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_documents_status', 'process_status'),
        Index('idx_documents_timestamp', 'processing_timestamp'),
        Index('idx_documents_file', 'source_file'),
        CheckConstraint('quality_score >= 0 AND quality_score <= 1'),
    )
    
    def __repr__(self):
        return f"<Document(source_file='{self.source_file}', status={self.process_status})>"


class Entity(Base):
    """实体表 - 核心实体数据"""
    __tablename__ = "entities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(SQLEnum(EntityTypeEnum), nullable=False)
    confidence = Column(Float, default=0.5)
    position = Column(Integer, nullable=False)
    length = Column(Integer, nullable=False)
    alternative_names = Column(ARRAY(String), default=[])
    description = Column(Text, nullable=True)
    entity_metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="entities")
    
    # 自关系：作为源的关系
    relationships_out = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.source_entity_id",
        back_populates="source_entity"
    )
    # 自关系：作为目标的关系
    relationships_in = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.target_entity_id",
        back_populates="target_entity"
    )
    
    __table_args__ = (
        Index('idx_entities_document', 'document_id'),
        Index('idx_entities_type', 'type'),
        Index('idx_entities_name', 'name'),
        Index('idx_entities_confidence', 'confidence'),
        CheckConstraint('confidence >= 0 AND confidence <= 1'),
    )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': str(self.id),
            'name': self.name,
            'type': self.type.value,
            'confidence': self.confidence,
            'position': self.position,
            'length': self.length,
            'alternative_names': self.alternative_names,
            'description': self.description,
            'entity_metadata': self.entity_metadata,
        }
    
    def __repr__(self):
        return f"<Entity(name='{self.name}', type={self.type})>"


class RelationshipType(Base):
    """关系类型定义表"""
    __tablename__ = "relationship_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    relationship_name = Column(String(100), nullable=False, unique=True)
    relationship_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(SQLEnum(RelationshipCategoryEnum), nullable=True)
    confidence_baseline = Column(Float, default=0.7)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    relationships = relationship("EntityRelationship", back_populates="type")
    
    __table_args__ = (
        Index('idx_rel_types_name', 'relationship_name'),
        CheckConstraint('confidence_baseline >= 0 AND confidence_baseline <= 1'),
    )
    
    def __repr__(self):
        return f"<RelationshipType(name='{self.relationship_name}')>"


class EntityRelationship(Base):
    """实体关系表 - 记录实体间的关系"""
    __tablename__ = "entity_relationships"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    target_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    relationship_type_id = Column(UUID(as_uuid=True), ForeignKey("relationship_types.id"), nullable=False)
    confidence = Column(Float, default=0.5)
    created_by_module = Column(String(100), nullable=True)
    evidence = Column(Text, nullable=True)
    relationship_metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    source_entity = relationship("Entity", foreign_keys=[source_entity_id], back_populates="relationships_out")
    target_entity = relationship("Entity", foreign_keys=[target_entity_id], back_populates="relationships_in")
    type = relationship("RelationshipType", back_populates="relationships")
    
    __table_args__ = (
        Index('idx_rel_source', 'source_entity_id'),
        Index('idx_rel_target', 'target_entity_id'),
        Index('idx_rel_type', 'relationship_type_id'),
        Index('idx_rel_module', 'created_by_module'),
        CheckConstraint('confidence >= 0 AND confidence <= 1'),
    )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': str(self.id),
            'source_entity_id': str(self.source_entity_id),
            'target_entity_id': str(self.target_entity_id),
            'relationship_type': self.type.relationship_type if self.type else None,
            'confidence': self.confidence,
            'evidence': self.evidence,
        }
    
    def __repr__(self):
        return f"<EntityRelationship(source={self.source_entity_id}, target={self.target_entity_id})>"


class ProcessingStatistics(Base):
    """处理统计表"""
    __tablename__ = "processing_statistics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    formulas_count = Column(Integer, default=0)
    herbs_count = Column(Integer, default=0)
    syndromes_count = Column(Integer, default=0)
    efficacies_count = Column(Integer, default=0)
    relationships_count = Column(Integer, default=0)
    graph_nodes_count = Column(Integer, default=0)
    graph_edges_count = Column(Integer, default=0)
    graph_density = Column(Float, default=0.0)
    connected_components = Column(Integer, default=0)
    source_modules = Column(ARRAY(String), default=[])
    processing_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="statistics")
    
    __table_args__ = (
        Index('idx_stats_document', 'document_id'),
    )
    
    def __repr__(self):
        return f"<ProcessingStatistics(doc_id={self.document_id}, entities={self.formulas_count + self.herbs_count})>"


class QualityMetrics(Base):
    """质量指标表"""
    __tablename__ = "quality_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    confidence_score = Column(Float, default=0.0)
    completeness = Column(Float, default=0.0)
    entity_precision = Column(Float, default=0.0)
    relationship_precision = Column(Float, default=0.0)
    graph_quality_score = Column(Float, default=0.0)
    evaluation_timestamp = Column(DateTime, default=datetime.utcnow)
    evaluator = Column(String(100), nullable=True)
    assessment_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="quality")
    
    __table_args__ = (
        Index('idx_quality_document', 'document_id'),
        Index('idx_quality_score', 'confidence_score'),
    )
    
    def __repr__(self):
        return f"<QualityMetrics(doc_id={self.document_id}, score={self.confidence_score})>"


class ResearchAnalysis(Base):
    """研究分析表 - 存储复杂的分析结果"""
    __tablename__ = "research_analyses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    research_perspectives = Column(JSONB, default={})
    formula_comparisons = Column(JSONB, default={})
    herb_properties_analysis = Column(JSONB, default={})
    pharmacology_integration = Column(JSONB, default={})
    network_pharmacology = Column(JSONB, default={})
    supramolecular_physicochemistry = Column(JSONB, default={})
    knowledge_archaeology = Column(JSONB, default={})
    complexity_dynamics = Column(JSONB, default={})
    research_scoring_panel = Column(JSONB, default={})
    summary_analysis = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="analyses")
    
    __table_args__ = (
        Index('idx_analysis_document', 'document_id'),
    )
    
    def __repr__(self):
        return f"<ResearchAnalysis(doc_id={self.document_id})>"


class ProcessingLog(Base):
    """处理日志表 - 审计追踪"""
    __tablename__ = "processing_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    module_name = Column(String(100), nullable=False)
    status = Column(SQLEnum(LogStatusEnum), nullable=False)
    message = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship("Document", back_populates="logs")
    
    __table_args__ = (
        Index('idx_logs_document', 'document_id'),
        Index('idx_logs_module', 'module_name'),
        Index('idx_logs_status', 'status'),
        Index('idx_logs_timestamp', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<ProcessingLog(module={self.module_name}, status={self.status})>"


# ==================== 会话和引擎管理 ====================

class DatabaseManager:
    """数据库连接管理器"""
    
    def __init__(self, connection_string: str):
        """
        初始化数据库管理器
        
        Args:
            connection_string: PostgreSQL连接字符串
                格式: postgresql://user:password@host:port/database
        """
        self.connection_string = connection_string
        self.engine = None
        self.Session = None
    
    def init_db(self):
        """初始化数据库连接和表"""
        self.engine = create_engine(self.connection_string, echo=False, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        
        # 创建所有表
        Base.metadata.create_all(self.engine)
    
    def get_session(self):
        """获取新会话"""
        if self.Session is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return self.Session()
    
    def close(self):
        """关闭所有连接"""
        if self.engine:
            self.engine.dispose()
    
    @staticmethod
    def create_default_relationships(session):
        """创建默认关系类型"""
        default_rels = [
            ("君", "SOVEREIGN", "方剂中的主要成分，发挥主要治疗作用", RelationshipCategoryEnum.COMPOSITION, 0.95),
            ("臣", "MINISTER", "方剂中的辅助成分，协助君药发挥作用", RelationshipCategoryEnum.COMPOSITION, 0.92),
            ("佐", "ASSISTANT", "方剂中的配合成分，起支持或对抗作用", RelationshipCategoryEnum.COMPOSITION, 0.90),
            ("使", "ENVOY", "方剂中的调和成分，促进诸药的协调", RelationshipCategoryEnum.COMPOSITION, 0.88),
            ("治疗", "TREATS", "中药/方剂治疗特定症候", RelationshipCategoryEnum.THERAPEUTIC, 0.75),
            ("功效", "HAS_EFFICACY", "中药具有特定功效", RelationshipCategoryEnum.PROPERTY, 0.82),
            ("类似", "SIMILAR_TO", "两个方剂或中药成分相似", RelationshipCategoryEnum.SIMILARITY, 0.70),
            ("包含", "CONTAINS", "方剂包含特定中药", RelationshipCategoryEnum.COMPOSITION, 0.99),
        ]
        
        for name, rel_type, desc, category, confidence_base in default_rels:
            existing = session.query(RelationshipType).filter_by(relationship_name=name).first()
            if not existing:
                rel = RelationshipType(
                    relationship_name=name,
                    relationship_type=rel_type,
                    description=desc,
                    category=category,
                    confidence_baseline=confidence_base
                )
                session.add(rel)
        
        session.commit()
