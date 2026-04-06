"""架构 3.0 持久化层。

提供数据库无关的 SQLAlchemy ORM 模型、连接管理与持久化服务。
阶段 2 默认使用 SQLite，后续可平滑迁移到 PostgreSQL。
"""

from __future__ import annotations

import enum
import json
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence

from sqlalchemy import (
    CHAR,
    JSON,
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
    event,
    or_,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import (
    Session,
    declarative_base,
    relationship,
    scoped_session,
    sessionmaker,
)
from sqlalchemy.types import TypeDecorator

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)

Base = declarative_base()


def _enum_values(enum_cls: type[enum.Enum]) -> List[str]:
    return [member.value for member in enum_cls]


class GUID(TypeDecorator):
    """跨 SQLite/PostgreSQL 的 UUID 类型。"""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PGUUID

            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return parsed if dialect.name == "postgresql" else str(parsed)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class ProcessStatusEnum(str, enum.Enum):
    """文档处理状态。"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityTypeEnum(str, enum.Enum):
    """实体类型。"""

    FORMULA = "formula"
    HERB = "herb"
    SYNDROME = "syndrome"
    EFFICACY = "efficacy"
    PROPERTY = "property"
    TASTE = "taste"
    MERIDIAN = "meridian"
    OTHER = "other"


class RelationshipCategoryEnum(str, enum.Enum):
    """关系类别。"""

    COMPOSITION = "composition"
    THERAPEUTIC = "therapeutic"
    PROPERTY = "property"
    SIMILARITY = "similarity"
    OTHER = "other"


class LogStatusEnum(str, enum.Enum):
    """处理日志状态。"""

    START = "start"
    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"


def _enum_column(enum_cls: type[enum.Enum], **kwargs: Any) -> SQLEnum:
    return SQLEnum(
        enum_cls,
        native_enum=False,
        values_callable=_enum_values,
        validate_strings=True,
        **kwargs,
    )


class Document(Base):
    """文档表。"""

    __tablename__ = "documents"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    source_file = Column(String(500), nullable=False, unique=True)
    processing_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    objective = Column(String(255), nullable=True)
    raw_text_size = Column(Integer, default=0, nullable=False)
    entities_extracted_count = Column(Integer, default=0, nullable=False)
    process_status = Column(
        _enum_column(ProcessStatusEnum, name="process_status_enum"),
        default=ProcessStatusEnum.PENDING,
        nullable=False,
    )
    quality_score = Column(Float, default=0.0, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")
    statistics = relationship(
        "ProcessingStatistics",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    quality = relationship(
        "QualityMetrics",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    analyses = relationship(
        "ResearchAnalysis",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    logs = relationship("ProcessingLog", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_documents_status", "process_status"),
        Index("idx_documents_timestamp", "processing_timestamp"),
        Index("idx_documents_file", "source_file"),
        CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="ck_documents_quality_score"),
    )


class Entity(Base):
    """实体表。"""

    __tablename__ = "entities"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(_enum_column(EntityTypeEnum, name="entity_type_enum"), nullable=False)
    confidence = Column(Float, default=0.5, nullable=False)
    position = Column(Integer, default=0, nullable=False)
    length = Column(Integer, default=0, nullable=False)
    alternative_names = Column(JSON, default=list, nullable=False)
    description = Column(Text, nullable=True)
    entity_metadata = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="entities")
    relationships_out = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.source_entity_id",
        back_populates="source_entity",
    )
    relationships_in = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.target_entity_id",
        back_populates="target_entity",
    )

    __table_args__ = (
        Index("idx_entities_document", "document_id"),
        Index("idx_entities_type", "type"),
        Index("idx_entities_name", "name"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_entities_confidence"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "name": self.name,
            "type": self.type.value,
            "confidence": self.confidence,
            "position": self.position,
            "length": self.length,
            "alternative_names": list(self.alternative_names or []),
            "description": self.description,
            "entity_metadata": dict(self.entity_metadata or {}),
        }


class RelationshipType(Base):
    """关系类型定义表。"""

    __tablename__ = "relationship_types"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    relationship_name = Column(String(100), nullable=False, unique=True)
    relationship_type = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    category = Column(_enum_column(RelationshipCategoryEnum, name="relationship_category_enum"), nullable=True)
    confidence_baseline = Column(Float, default=0.7, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    relationships = relationship("EntityRelationship", back_populates="type")

    __table_args__ = (
        Index("idx_rel_types_name", "relationship_name"),
        Index("idx_rel_types_type", "relationship_type"),
        CheckConstraint(
            "confidence_baseline >= 0 AND confidence_baseline <= 1",
            name="ck_relationship_types_confidence_baseline",
        ),
    )


class EntityRelationship(Base):
    """实体关系表。"""

    __tablename__ = "entity_relationships"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    source_entity_id = Column(GUID(), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    target_entity_id = Column(GUID(), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    relationship_type_id = Column(GUID(), ForeignKey("relationship_types.id"), nullable=False)
    confidence = Column(Float, default=0.5, nullable=False)
    created_by_module = Column(String(100), nullable=True)
    evidence = Column(Text, nullable=True)
    relationship_metadata = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    source_entity = relationship("Entity", foreign_keys=[source_entity_id], back_populates="relationships_out")
    target_entity = relationship("Entity", foreign_keys=[target_entity_id], back_populates="relationships_in")
    type = relationship("RelationshipType", back_populates="relationships")

    __table_args__ = (
        Index("idx_rel_source", "source_entity_id"),
        Index("idx_rel_target", "target_entity_id"),
        Index("idx_rel_type", "relationship_type_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_entity_relationships_confidence"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "source_entity_id": str(self.source_entity_id),
            "target_entity_id": str(self.target_entity_id),
            "relationship_type": self.type.relationship_type if self.type else None,
            "relationship_name": self.type.relationship_name if self.type else None,
            "confidence": self.confidence,
            "created_by_module": self.created_by_module,
            "evidence": self.evidence,
            "relationship_metadata": dict(self.relationship_metadata or {}),
        }


class ProcessingStatistics(Base):
    """处理统计表。"""

    __tablename__ = "processing_statistics"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    formulas_count = Column(Integer, default=0, nullable=False)
    herbs_count = Column(Integer, default=0, nullable=False)
    syndromes_count = Column(Integer, default=0, nullable=False)
    efficacies_count = Column(Integer, default=0, nullable=False)
    relationships_count = Column(Integer, default=0, nullable=False)
    graph_nodes_count = Column(Integer, default=0, nullable=False)
    graph_edges_count = Column(Integer, default=0, nullable=False)
    graph_density = Column(Float, default=0.0, nullable=False)
    connected_components = Column(Integer, default=0, nullable=False)
    source_modules = Column(JSON, default=list, nullable=False)
    processing_time_ms = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="statistics")


class QualityMetrics(Base):
    """质量指标表。"""

    __tablename__ = "quality_metrics"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    confidence_score = Column(Float, default=0.0, nullable=False)
    completeness = Column(Float, default=0.0, nullable=False)
    entity_precision = Column(Float, default=0.0, nullable=False)
    relationship_precision = Column(Float, default=0.0, nullable=False)
    graph_quality_score = Column(Float, default=0.0, nullable=False)
    evaluation_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    evaluator = Column(String(100), nullable=True)
    assessment_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="quality")


class ResearchAnalysis(Base):
    """研究分析表。"""

    __tablename__ = "research_analyses"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    research_perspectives = Column(JSON, default=dict, nullable=False)
    formula_comparisons = Column(JSON, default=dict, nullable=False)
    herb_properties_analysis = Column(JSON, default=dict, nullable=False)
    pharmacology_integration = Column(JSON, default=dict, nullable=False)
    network_pharmacology = Column(JSON, default=dict, nullable=False)
    supramolecular_physicochemistry = Column(JSON, default=dict, nullable=False)
    knowledge_archaeology = Column(JSON, default=dict, nullable=False)
    complexity_dynamics = Column(JSON, default=dict, nullable=False)
    research_scoring_panel = Column(JSON, default=dict, nullable=False)
    summary_analysis = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="analyses")


class ProcessingLog(Base):
    """处理日志表。"""

    __tablename__ = "processing_logs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id = Column(GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    module_name = Column(String(100), nullable=False)
    status = Column(_enum_column(LogStatusEnum, name="log_status_enum"), nullable=False)
    message = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, default=0, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="logs")


class ResearchRecord(Base):
    """研究循环结果记录。"""

    __tablename__ = "research_results"

    cycle_id = Column(String(128), primary_key=True)
    cycle_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(64), nullable=False)
    current_phase = Column(String(64), nullable=True)
    started_at = Column(String(64), nullable=True)
    completed_at = Column(String(64), nullable=True)
    duration = Column(Float, default=0.0, nullable=False)
    research_objective = Column(Text, nullable=True)
    research_scope = Column(Text, nullable=True)
    target_audience = Column(Text, nullable=True)
    outcomes_json = Column(Text, nullable=False, default="[]")
    deliverables_json = Column(Text, nullable=False, default="[]")
    quality_metrics_json = Column(Text, nullable=False, default="{}")
    risk_assessment_json = Column(Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")
    persisted_at = Column(String(64), nullable=False)

    __table_args__ = (
        Index("idx_research_results_status", "status"),
        Index("idx_research_results_persisted_at", "persisted_at"),
    )


# ---------------------------------------------------------------------------
# P3.1  ResearchSession 持久化 — 会话 / 阶段执行 / 工件 三表
# ---------------------------------------------------------------------------


class SessionStatusEnum(str, enum.Enum):
    """研究会话状态。"""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SUSPENDED = "suspended"


class PhaseStatusEnum(str, enum.Enum):
    """阶段执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ArtifactTypeEnum(str, enum.Enum):
    """工件类型。"""

    PAPER = "paper"
    DATASET = "dataset"
    ANALYSIS = "analysis"
    HYPOTHESIS = "hypothesis"
    REPORT = "report"
    VISUALIZATION = "visualization"
    REFERENCE = "reference"
    OTHER = "other"


class ResearchSession(Base):
    """研究会话 — 全生命周期追踪。"""

    __tablename__ = "research_sessions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(String(128), unique=True, nullable=False, index=True)
    cycle_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        _enum_column(SessionStatusEnum, name="session_status_enum"),
        default=SessionStatusEnum.PENDING,
        nullable=False,
    )
    current_phase = Column(String(64), nullable=True)

    # 研究目标
    research_objective = Column(Text, nullable=True)
    research_scope = Column(Text, nullable=True)
    target_audience = Column(Text, nullable=True)

    # 参与者 & 资源（JSON）
    researchers_json = Column(Text, nullable=False, default="[]")
    advisors_json = Column(Text, nullable=False, default="[]")
    resources_json = Column(Text, nullable=False, default="{}")
    budget = Column(Float, default=0.0, nullable=False)
    timeline_json = Column(Text, nullable=False, default="{}")

    # 质量 & 风险（JSON）
    quality_metrics_json = Column(Text, nullable=False, default="{}")
    risk_assessment_json = Column(Text, nullable=False, default="{}")
    expert_reviews_json = Column(Text, nullable=False, default="[]")

    # 分类 & 元数据
    tags_json = Column(Text, nullable=False, default="[]")
    categories_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")

    # 时间戳
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    phase_executions = relationship(
        "PhaseExecution", back_populates="session", cascade="all, delete-orphan", order_by="PhaseExecution.created_at",
    )
    artifacts = relationship(
        "ResearchArtifact", back_populates="session", cascade="all, delete-orphan", order_by="ResearchArtifact.created_at",
    )

    __table_args__ = (
        Index("idx_rs_status", "status"),
        Index("idx_rs_created", "created_at"),
    )


class PhaseExecution(Base):
    """阶段执行记录。"""

    __tablename__ = "phase_executions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(GUID(), ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False)
    phase = Column(String(64), nullable=False)
    status = Column(
        _enum_column(PhaseStatusEnum, name="phase_status_enum"),
        default=PhaseStatusEnum.PENDING,
        nullable=False,
    )

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration = Column(Float, default=0.0, nullable=False)
    input_json = Column(Text, nullable=False, default="{}")
    output_json = Column(Text, nullable=False, default="{}")
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("ResearchSession", back_populates="phase_executions")
    artifacts = relationship(
        "ResearchArtifact", back_populates="phase_execution", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_pe_session_phase", "session_id", "phase"),
    )


class ResearchArtifact(Base):
    """研究工件 / 产出物。"""

    __tablename__ = "research_artifacts"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id = Column(GUID(), ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False)
    phase_execution_id = Column(GUID(), ForeignKey("phase_executions.id", ondelete="SET NULL"), nullable=True)
    artifact_type = Column(
        _enum_column(ArtifactTypeEnum, name="artifact_type_enum"),
        default=ArtifactTypeEnum.OTHER,
        nullable=False,
    )
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    content_json = Column(Text, nullable=False, default="{}")
    file_path = Column(String(1000), nullable=True)
    mime_type = Column(String(128), nullable=True)
    size_bytes = Column(Integer, default=0, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    session = relationship("ResearchSession", back_populates="artifacts")
    phase_execution = relationship("PhaseExecution", back_populates="artifacts")

    __table_args__ = (
        Index("idx_ra_session", "session_id"),
        Index("idx_ra_type", "artifact_type"),
    )


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _json_dumps(value: Any, default: str) -> str:
    if value in (None, ""):
        return default
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


class DatabaseManager:
    """SQLAlchemy 引擎与会话管理器。"""

    def __init__(
        self,
        connection_string: str,
        *,
        echo: bool = False,
        connection_timeout: Optional[int] = None,
        pool_size: Optional[int] = None,
        max_overflow: Optional[int] = None,
    ):
        self.connection_string = connection_string
        self.echo = echo
        self.connection_timeout = connection_timeout
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.engine = None
        self.Session = None

    def _build_engine_kwargs(self) -> Dict[str, Any]:
        url = make_url(self.connection_string)
        kwargs: Dict[str, Any] = {"echo": self.echo}
        connect_args: Dict[str, Any] = {}
        if url.drivername.startswith("sqlite"):
            database = url.database or ""
            if database and database != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(database)), exist_ok=True)
            connect_args["check_same_thread"] = False
            if self.connection_timeout is not None:
                connect_args["timeout"] = int(self.connection_timeout)
        else:
            kwargs["pool_pre_ping"] = True
            if self.pool_size is not None:
                kwargs["pool_size"] = int(self.pool_size)
            if self.max_overflow is not None:
                kwargs["max_overflow"] = int(self.max_overflow)
        if connect_args:
            kwargs["connect_args"] = connect_args
        return kwargs

    def init_db(self) -> None:
        self.engine = create_engine(self.connection_string, **self._build_engine_kwargs())
        if self.connection_string.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.Session = scoped_session(session_factory)
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        if self.Session is None:
            raise RuntimeError("数据库未初始化，请先调用 init_db()")
        return self.Session()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self.Session.remove()

    def remove_session(self) -> None:
        """显式移除当前线程的 scoped session（供 web 请求收尾调用）。"""
        if self.Session is not None:
            self.Session.remove()

    def health_check(self) -> bool:
        if self.engine is None:
            return False
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self.Session is not None:
            self.Session.remove()
        if self.engine is not None:
            self.engine.dispose()

    @staticmethod
    def create_default_relationships(session: Session) -> None:
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
        existing = {
            row.relationship_type: row
            for row in session.query(RelationshipType).all()
        }
        for name, rel_type, desc, category, confidence_base in default_rels:
            if rel_type in existing:
                continue
            session.add(
                RelationshipType(
                    relationship_name=name,
                    relationship_type=rel_type,
                    description=desc,
                    category=category,
                    confidence_baseline=confidence_base,
                )
            )
        session.flush()


class PersistenceService(BaseModule):
    """架构 3.0 持久化服务。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("persistence", config)
        self.database_manager: Optional[DatabaseManager] = None
        self.connection_string = ""

    def _do_initialize(self) -> bool:
        self.connection_string = self._resolve_connection_string(self.config)
        database_cfg = self.config.get("database") or {}
        self.database_manager = DatabaseManager(
            self.connection_string,
            echo=bool(database_cfg.get("echo", self.config.get("echo", False))),
            connection_timeout=database_cfg.get("connection_timeout", self.config.get("connection_timeout")),
            pool_size=database_cfg.get("connection_pool_size", self.config.get("connection_pool_size")),
            max_overflow=database_cfg.get("max_overflow", self.config.get("max_overflow")),
        )
        self.database_manager.init_db()
        with self.database_manager.session_scope() as session:
            DatabaseManager.create_default_relationships(session)
        self.logger.info("PersistenceService 初始化完成: %s", self.connection_string)
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        command = self._normalize_command(context)
        entity_type = command["entity_type"]
        operation = command["operation"]
        data = command["data"]

        if entity_type in {"document_graph", "knowledge_store", "document"}:
            if operation == "get":
                document_id = str(data.get("document_id") or data.get("id") or "").strip()
                source_file = str(data.get("source_file") or "").strip() or None
                return self.get_document_snapshot(document_id=document_id or None, source_file=source_file)
            return self.persist_document_graph(data)

        if entity_type in {"research_record", "research_results"}:
            if operation == "get":
                cycle_id = str(data.get("cycle_id") or data.get("id") or "").strip()
                return self.get_research_record(cycle_id)
            return self.persist_research_record(data)

        if entity_type in {"storage_overview", "overview", "stats"}:
            return self.get_storage_overview()

        raise ValueError(f"不支持的持久化命令: entity_type={entity_type}, operation={operation}")

    def _do_cleanup(self) -> bool:
        if self.database_manager is not None:
            self.database_manager.close()
            self.database_manager = None
        return True

    def persist_document_graph(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        manager = self._require_manager()
        with manager.session_scope() as session:
            DatabaseManager.create_default_relationships(session)
            document_payload = dict(payload.get("document") or payload)
            document = self._upsert_document(session, document_payload)
            replace_children = bool(payload.get("replace_children", True))
            if replace_children:
                self._delete_document_graph_details(session, document.id)

            entities = self._persist_entities(session, document.id, payload.get("entities") or [])
            entity_lookup = self._build_entity_lookup(entities)
            relationships = self._persist_relationships(
                session,
                payload.get("relationships") or [],
                entity_lookup,
            )

            if "statistics" in payload:
                self._upsert_processing_statistics(session, document.id, payload.get("statistics") or {})
            if "quality_metrics" in payload or "quality" in payload:
                self._upsert_quality_metrics(
                    session,
                    document.id,
                    payload.get("quality_metrics") or payload.get("quality") or {},
                )
            if "research_analysis" in payload or "analysis" in payload:
                self._upsert_research_analysis(
                    session,
                    document.id,
                    payload.get("research_analysis") or payload.get("analysis") or {},
                )
            if payload.get("logs"):
                self._persist_logs(session, document.id, payload.get("logs") or [])

            document.entities_extracted_count = len(entities)
            if "quality_score" in document_payload:
                document.quality_score = float(document_payload.get("quality_score") or 0.0)

            session.flush()
            return self._build_document_snapshot(session, document.id, len(relationships))

    def get_document_snapshot(
        self,
        *,
        document_id: Optional[str] = None,
        source_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        manager = self._require_manager()
        with manager.session_scope() as session:
            document = self._get_document(session, document_id=document_id, source_file=source_file)
            if document is None:
                return {"found": False}
            relationship_count = self._count_document_relationships(session, document.id)
            return self._build_document_snapshot(session, document.id, relationship_count)

    def persist_research_record(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        cycle_id = str(payload.get("cycle_id") or payload.get("id") or "").strip()
        if not cycle_id:
            raise ValueError("persist_research_record 需要 cycle_id")

        manager = self._require_manager()
        with manager.session_scope() as session:
            record = session.query(ResearchRecord).filter_by(cycle_id=cycle_id).one_or_none()
            if record is None:
                record = ResearchRecord(cycle_id=cycle_id, cycle_name=str(payload.get("cycle_name") or cycle_id), status="pending", persisted_at="")
                session.add(record)

            record.cycle_name = str(payload.get("cycle_name") or record.cycle_name or cycle_id)
            record.description = self._optional_text(payload.get("description"))
            record.status = self._enum_value(payload.get("status")) or record.status
            record.current_phase = self._enum_value(payload.get("current_phase")) or self._optional_text(payload.get("current_phase"))
            record.started_at = self._optional_text(payload.get("started_at"))
            record.completed_at = self._optional_text(payload.get("completed_at"))
            record.duration = float(payload.get("duration") or 0.0)
            record.research_objective = self._optional_text(payload.get("research_objective"))
            record.research_scope = self._optional_text(payload.get("research_scope"))
            record.target_audience = self._optional_text(payload.get("target_audience"))
            record.outcomes_json = _json_dumps(payload.get("outcomes") or [], "[]")
            record.deliverables_json = _json_dumps(payload.get("deliverables") or [], "[]")
            record.quality_metrics_json = _json_dumps(payload.get("quality_metrics") or {}, "{}")
            record.risk_assessment_json = _json_dumps(payload.get("risk_assessment") or {}, "{}")
            record.metadata_json = _json_dumps(payload.get("metadata") or {}, "{}")
            record.persisted_at = datetime.now().isoformat()
            session.flush()
            return self._research_record_to_dict(record)

    def get_research_record(self, cycle_id: str) -> Dict[str, Any]:
        manager = self._require_manager()
        with manager.session_scope() as session:
            record = session.query(ResearchRecord).filter_by(cycle_id=cycle_id).one_or_none()
            if record is None:
                return {"found": False, "cycle_id": cycle_id}
            return self._research_record_to_dict(record)

    def get_storage_overview(self) -> Dict[str, Any]:
        manager = self._require_manager()
        with manager.session_scope() as session:
            return {
                "documents": session.query(Document).count(),
                "entities": session.query(Entity).count(),
                "relationships": session.query(EntityRelationship).count(),
                "relationship_types": session.query(RelationshipType).count(),
                "research_records": session.query(ResearchRecord).count(),
                "healthy": manager.health_check(),
                "connection_string": self.connection_string,
            }

    def _resolve_connection_string(self, config: Mapping[str, Any]) -> str:
        direct = config.get("connection_string") or config.get("database_url") or config.get("url")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        database_cfg = config.get("database") or {}
        db_type = str(database_cfg.get("type") or config.get("database_type") or "sqlite").strip().lower()
        db_path = str(
            database_cfg.get("path")
            or config.get("db_path")
            or config.get("path")
            or os.path.join("data", "tcmautoresearch.db")
        ).strip()
        if db_type == "sqlite":
            absolute = os.path.abspath(db_path)
            return f"sqlite:///{absolute}"
        return str(database_cfg.get("connection_string") or config.get("connection_string") or "").strip()

    def _normalize_command(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        command = context.get("command") if isinstance(context.get("command"), Mapping) else context
        data = command.get("data") if isinstance(command.get("data"), Mapping) else command
        entity_type = str(command.get("entity_type") or command.get("model") or "document_graph").strip().lower()
        operation = str(command.get("operation") or command.get("action") or "upsert").strip().lower()
        return {
            "entity_type": entity_type,
            "operation": operation,
            "data": dict(data),
        }

    def _require_manager(self) -> DatabaseManager:
        if self.database_manager is None:
            raise RuntimeError("PersistenceService 尚未初始化")
        return self.database_manager

    def _get_document(
        self,
        session: Session,
        *,
        document_id: Optional[str] = None,
        source_file: Optional[str] = None,
    ) -> Optional[Document]:
        if document_id:
            try:
                parsed_id = uuid.UUID(str(document_id))
            except ValueError:
                parsed_id = None
            if parsed_id is not None:
                document = session.query(Document).filter_by(id=parsed_id).one_or_none()
                if document is not None:
                    return document
        if source_file:
            return session.query(Document).filter_by(source_file=source_file).one_or_none()
        return None

    def _upsert_document(self, session: Session, payload: Mapping[str, Any]) -> Document:
        source_file = str(payload.get("source_file") or payload.get("source_ref") or payload.get("path") or "").strip()
        if not source_file:
            raise ValueError("persist_document_graph 需要 source_file/document.source_file")

        document = self._get_document(
            session,
            document_id=str(payload.get("id") or payload.get("document_id") or "").strip() or None,
            source_file=source_file,
        )
        if document is None:
            document = Document(source_file=source_file)
            session.add(document)

        document.processing_timestamp = self._parse_datetime(payload.get("processing_timestamp")) or datetime.utcnow()
        document.objective = self._optional_text(payload.get("objective"))
        document.raw_text_size = int(payload.get("raw_text_size") or payload.get("text_size") or 0)
        document.process_status = self._coerce_process_status(payload.get("process_status") or payload.get("status"))
        document.quality_score = float(payload.get("quality_score") or document.quality_score or 0.0)
        document.notes = self._optional_text(payload.get("notes"))
        document.updated_at = datetime.utcnow()
        session.flush()
        return document

    def _delete_document_graph_details(self, session: Session, document_id: uuid.UUID) -> None:
        entity_ids = [row[0] for row in session.query(Entity.id).filter_by(document_id=document_id).all()]
        if entity_ids:
            session.query(EntityRelationship).filter(
                or_(
                    EntityRelationship.source_entity_id.in_(entity_ids),
                    EntityRelationship.target_entity_id.in_(entity_ids),
                )
            ).delete(synchronize_session=False)
        session.query(Entity).filter_by(document_id=document_id).delete(synchronize_session=False)
        session.query(ProcessingLog).filter_by(document_id=document_id).delete(synchronize_session=False)

    def _persist_entities(self, session: Session, document_id: uuid.UUID, payloads: Sequence[Mapping[str, Any]]) -> List[Entity]:
        entities: List[Entity] = []
        for payload in payloads:
            entity = Entity(
                document_id=document_id,
                name=str(payload.get("name") or "").strip(),
                type=self._coerce_entity_type(payload.get("type") or payload.get("entity_type")),
                confidence=float(payload.get("confidence") or 0.5),
                position=int(payload.get("position") or 0),
                length=int(payload.get("length") or 0),
                alternative_names=list(payload.get("alternative_names") or payload.get("aliases") or []),
                description=self._optional_text(payload.get("description")),
                entity_metadata=dict(payload.get("metadata") or payload.get("entity_metadata") or {}),
            )
            session.add(entity)
            entities.append(entity)
        session.flush()
        return entities

    def _persist_relationships(
        self,
        session: Session,
        payloads: Sequence[Mapping[str, Any]],
        entity_lookup: Mapping[str, Entity],
    ) -> List[EntityRelationship]:
        relationships: List[EntityRelationship] = []
        type_cache = self._relationship_type_cache(session)
        for payload in payloads:
            source = self._resolve_entity(payload, entity_lookup, "source")
            target = self._resolve_entity(payload, entity_lookup, "target")
            if source is None or target is None:
                self.logger.warning("跳过无法解析实体的关系: %s", payload)
                continue
            relationship_type = self._resolve_relationship_type(
                session,
                type_cache,
                str(payload.get("relationship_type") or payload.get("type") or payload.get("relationship_name") or "").strip(),
            )
            relationship = EntityRelationship(
                source_entity_id=source.id,
                target_entity_id=target.id,
                relationship_type_id=relationship_type.id,
                confidence=float(payload.get("confidence") or 0.5),
                created_by_module=self._optional_text(payload.get("created_by_module")) or "persistence_service",
                evidence=self._optional_text(payload.get("evidence")),
                relationship_metadata=dict(payload.get("metadata") or payload.get("relationship_metadata") or {}),
            )
            session.add(relationship)
            relationships.append(relationship)
        session.flush()
        return relationships

    def _persist_logs(self, session: Session, document_id: uuid.UUID, payloads: Sequence[Mapping[str, Any]]) -> None:
        for payload in payloads:
            session.add(
                ProcessingLog(
                    document_id=document_id,
                    module_name=str(payload.get("module_name") or payload.get("module") or "unknown").strip(),
                    status=self._coerce_log_status(payload.get("status")),
                    message=self._optional_text(payload.get("message")),
                    error_details=self._optional_text(payload.get("error_details")),
                    execution_time_ms=int(payload.get("execution_time_ms") or 0),
                    timestamp=self._parse_datetime(payload.get("timestamp")) or datetime.utcnow(),
                )
            )
        session.flush()

    def _upsert_processing_statistics(self, session: Session, document_id: uuid.UUID, payload: Mapping[str, Any]) -> None:
        stats = session.query(ProcessingStatistics).filter_by(document_id=document_id).one_or_none()
        if stats is None:
            stats = ProcessingStatistics(document_id=document_id)
            session.add(stats)
        stats.formulas_count = int(payload.get("formulas_count") or 0)
        stats.herbs_count = int(payload.get("herbs_count") or 0)
        stats.syndromes_count = int(payload.get("syndromes_count") or 0)
        stats.efficacies_count = int(payload.get("efficacies_count") or 0)
        stats.relationships_count = int(payload.get("relationships_count") or 0)
        stats.graph_nodes_count = int(payload.get("graph_nodes_count") or 0)
        stats.graph_edges_count = int(payload.get("graph_edges_count") or 0)
        stats.graph_density = float(payload.get("graph_density") or 0.0)
        stats.connected_components = int(payload.get("connected_components") or 0)
        stats.source_modules = list(payload.get("source_modules") or [])
        stats.processing_time_ms = int(payload.get("processing_time_ms") or 0)
        session.flush()

    def _upsert_quality_metrics(self, session: Session, document_id: uuid.UUID, payload: Mapping[str, Any]) -> None:
        metrics = session.query(QualityMetrics).filter_by(document_id=document_id).one_or_none()
        if metrics is None:
            metrics = QualityMetrics(document_id=document_id)
            session.add(metrics)
        metrics.confidence_score = float(payload.get("confidence_score") or 0.0)
        metrics.completeness = float(payload.get("completeness") or 0.0)
        metrics.entity_precision = float(payload.get("entity_precision") or 0.0)
        metrics.relationship_precision = float(payload.get("relationship_precision") or 0.0)
        metrics.graph_quality_score = float(payload.get("graph_quality_score") or 0.0)
        metrics.evaluation_timestamp = self._parse_datetime(payload.get("evaluation_timestamp")) or datetime.utcnow()
        metrics.evaluator = self._optional_text(payload.get("evaluator"))
        metrics.assessment_notes = self._optional_text(payload.get("assessment_notes"))
        session.flush()

    def _upsert_research_analysis(self, session: Session, document_id: uuid.UUID, payload: Mapping[str, Any]) -> None:
        analysis = session.query(ResearchAnalysis).filter_by(document_id=document_id).one_or_none()
        if analysis is None:
            analysis = ResearchAnalysis(document_id=document_id)
            session.add(analysis)
        analysis.research_perspectives = dict(payload.get("research_perspectives") or {})
        analysis.formula_comparisons = dict(payload.get("formula_comparisons") or {})
        analysis.herb_properties_analysis = dict(payload.get("herb_properties_analysis") or {})
        analysis.pharmacology_integration = dict(payload.get("pharmacology_integration") or {})
        analysis.network_pharmacology = dict(payload.get("network_pharmacology") or {})
        analysis.supramolecular_physicochemistry = dict(payload.get("supramolecular_physicochemistry") or {})
        analysis.knowledge_archaeology = dict(payload.get("knowledge_archaeology") or {})
        analysis.complexity_dynamics = dict(payload.get("complexity_dynamics") or {})
        analysis.research_scoring_panel = dict(payload.get("research_scoring_panel") or {})
        analysis.summary_analysis = dict(payload.get("summary_analysis") or {})
        analysis.updated_at = datetime.utcnow()
        session.flush()

    def _relationship_type_cache(self, session: Session) -> Dict[str, RelationshipType]:
        cache: Dict[str, RelationshipType] = {}
        for row in session.query(RelationshipType).all():
            cache[row.relationship_type.upper()] = row
            cache[row.relationship_name] = row
        return cache

    def _resolve_relationship_type(
        self,
        session: Session,
        cache: Dict[str, RelationshipType],
        raw_value: str,
    ) -> RelationshipType:
        normalized = raw_value.strip()
        if not normalized:
            normalized = "RELATED"
        cached = cache.get(normalized) or cache.get(normalized.upper())
        if cached is not None:
            return cached
        relationship_type = RelationshipType(
            relationship_name=normalized,
            relationship_type=normalized.upper().replace(" ", "_"),
            description=f"自定义关系: {normalized}",
            category=RelationshipCategoryEnum.OTHER,
            confidence_baseline=0.5,
        )
        session.add(relationship_type)
        session.flush()
        cache[normalized] = relationship_type
        cache[relationship_type.relationship_type] = relationship_type
        return relationship_type

    def _build_entity_lookup(self, entities: Sequence[Entity]) -> Dict[str, Entity]:
        lookup: Dict[str, Entity] = {}
        for entity in entities:
            lookup[str(entity.id)] = entity
            lookup[entity.name] = entity
        return lookup

    def _resolve_entity(self, payload: Mapping[str, Any], lookup: Mapping[str, Entity], prefix: str) -> Optional[Entity]:
        direct_id = str(payload.get(f"{prefix}_entity_id") or payload.get(f"{prefix}_id") or "").strip()
        if direct_id and direct_id in lookup:
            return lookup[direct_id]
        by_name = str(
            payload.get(f"{prefix}_entity_name")
            or payload.get(f"{prefix}_name")
            or payload.get(prefix)
            or ""
        ).strip()
        if by_name:
            return lookup.get(by_name)
        return None

    def _count_document_relationships(self, session: Session, document_id: uuid.UUID) -> int:
        entity_ids = [row[0] for row in session.query(Entity.id).filter_by(document_id=document_id).all()]
        if not entity_ids:
            return 0
        return session.query(EntityRelationship).filter(
            EntityRelationship.source_entity_id.in_(entity_ids)
        ).count()

    def _build_document_snapshot(self, session: Session, document_id: uuid.UUID, relationship_count: int) -> Dict[str, Any]:
        document = session.query(Document).filter_by(id=document_id).one()
        entities = [entity.to_dict() for entity in session.query(Entity).filter_by(document_id=document_id).all()]
        logs = [
            {
                "module_name": log.module_name,
                "status": log.status.value,
                "message": log.message,
                "error_details": log.error_details,
                "execution_time_ms": log.execution_time_ms,
                "timestamp": log.timestamp.isoformat(),
            }
            for log in session.query(ProcessingLog).filter_by(document_id=document_id).order_by(ProcessingLog.timestamp.asc()).all()
        ]
        stats = session.query(ProcessingStatistics).filter_by(document_id=document_id).one_or_none()
        quality = session.query(QualityMetrics).filter_by(document_id=document_id).one_or_none()
        analysis = session.query(ResearchAnalysis).filter_by(document_id=document_id).one_or_none()
        return {
            "found": True,
            "document": {
                "id": str(document.id),
                "source_file": document.source_file,
                "processing_timestamp": document.processing_timestamp.isoformat(),
                "objective": document.objective,
                "raw_text_size": document.raw_text_size,
                "entities_extracted_count": document.entities_extracted_count,
                "process_status": document.process_status.value,
                "quality_score": document.quality_score,
                "notes": document.notes,
            },
            "entities": entities,
            "entity_count": len(entities),
            "relationship_count": relationship_count,
            "statistics": None if stats is None else {
                "formulas_count": stats.formulas_count,
                "herbs_count": stats.herbs_count,
                "syndromes_count": stats.syndromes_count,
                "efficacies_count": stats.efficacies_count,
                "relationships_count": stats.relationships_count,
                "graph_nodes_count": stats.graph_nodes_count,
                "graph_edges_count": stats.graph_edges_count,
                "graph_density": stats.graph_density,
                "connected_components": stats.connected_components,
                "source_modules": list(stats.source_modules or []),
                "processing_time_ms": stats.processing_time_ms,
            },
            "quality_metrics": None if quality is None else {
                "confidence_score": quality.confidence_score,
                "completeness": quality.completeness,
                "entity_precision": quality.entity_precision,
                "relationship_precision": quality.relationship_precision,
                "graph_quality_score": quality.graph_quality_score,
                "evaluation_timestamp": quality.evaluation_timestamp.isoformat(),
                "evaluator": quality.evaluator,
                "assessment_notes": quality.assessment_notes,
            },
            "research_analysis": None if analysis is None else {
                "research_perspectives": dict(analysis.research_perspectives or {}),
                "formula_comparisons": dict(analysis.formula_comparisons or {}),
                "herb_properties_analysis": dict(analysis.herb_properties_analysis or {}),
                "pharmacology_integration": dict(analysis.pharmacology_integration or {}),
                "network_pharmacology": dict(analysis.network_pharmacology or {}),
                "supramolecular_physicochemistry": dict(analysis.supramolecular_physicochemistry or {}),
                "knowledge_archaeology": dict(analysis.knowledge_archaeology or {}),
                "complexity_dynamics": dict(analysis.complexity_dynamics or {}),
                "research_scoring_panel": dict(analysis.research_scoring_panel or {}),
                "summary_analysis": dict(analysis.summary_analysis or {}),
            },
            "logs": logs,
        }

    def _research_record_to_dict(self, record: ResearchRecord) -> Dict[str, Any]:
        return {
            "found": True,
            "cycle_id": record.cycle_id,
            "cycle_name": record.cycle_name,
            "description": record.description,
            "status": record.status,
            "current_phase": record.current_phase,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "duration": record.duration,
            "research_objective": record.research_objective,
            "research_scope": record.research_scope,
            "target_audience": record.target_audience,
            "outcomes": _json_loads(record.outcomes_json, []),
            "deliverables": _json_loads(record.deliverables_json, []),
            "quality_metrics": _json_loads(record.quality_metrics_json, {}),
            "risk_assessment": _json_loads(record.risk_assessment_json, {}),
            "metadata": _json_loads(record.metadata_json, {}),
            "persisted_at": record.persisted_at,
        }

    def _enum_value(self, value: Any) -> str:
        if hasattr(value, "value"):
            return str(value.value)
        return str(value or "").strip()

    def _optional_text(self, value: Any) -> Optional[str]:
        text_value = str(value).strip() if value is not None else ""
        return text_value or None

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _coerce_process_status(self, value: Any) -> ProcessStatusEnum:
        raw = self._enum_value(value).lower()
        if not raw:
            return ProcessStatusEnum.PENDING
        return ProcessStatusEnum(raw)

    def _coerce_entity_type(self, value: Any) -> EntityTypeEnum:
        raw = self._enum_value(value).lower()
        if not raw:
            return EntityTypeEnum.OTHER
        try:
            return EntityTypeEnum(raw)
        except ValueError:
            return EntityTypeEnum.OTHER

    def _coerce_log_status(self, value: Any) -> LogStatusEnum:
        raw = self._enum_value(value).lower()
        if not raw:
            return LogStatusEnum.SUCCESS
        return LogStatusEnum(raw)


__all__ = [
    "Base",
    "DatabaseManager",
    "Document",
    "Entity",
    "EntityRelationship",
    "EntityTypeEnum",
    "LogStatusEnum",
    "PersistenceService",
    "ProcessStatusEnum",
    "ProcessingLog",
    "ProcessingStatistics",
    "QualityMetrics",
    "RelationshipCategoryEnum",
    "RelationshipType",
    "ResearchAnalysis",
    "ResearchRecord",
]
