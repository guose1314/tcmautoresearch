# -*- coding: utf-8 -*-
"""分析路由 — 方剂分析、文本处理链、知识图谱数据。"""

import logging
import warnings
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.analysis.ingestion_service import AnalysisIngestionService
from src.analysis.unsupervised_research_enhancer import (
    apply_unsupervised_annotations,
    build_unsupervised_research_view,
)
from src.contexts.llm_reasoning.philology_templates import (
    render_philology_reasoning_prompt,
)
from src.extraction.rule_relation_quality import (
    CANDIDATE_RULE_TIERS,
    is_promotable_rule_edge,
    rule_quality_tier_counts,
)
from src.learning.weak_edge_candidate_repo import (
    build_weak_edge_learning_insight,
    extract_weak_edge_candidate_payload,
    weak_edge_candidate_insight_id,
)
from src.llm.llm_gateway import LLMGateway, LLMGatewayRequest
from src.research.evidence.text_segment_provenance import (
    TextSegmentIndex,
    attach_provenance_to_edges,
    attach_provenance_to_entities,
    attach_provenance_to_research_view,
)
from src.web.auth import get_current_user
from src.web.ops.research_session_service import (
    get_research_observe_graph,
    get_research_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class FormulaAnalysisRequest(BaseModel):
    """方剂综合分析请求。"""

    perspective: Dict[str, Any] = Field(..., description="研究视角数据")
    formula_comparisons: Optional[List[Dict[str, Any]]] = None
    weights: Optional[Dict[str, float]] = None


class TextAnalysisRequest(BaseModel):
    """文本处理链请求。"""

    raw_text: str = Field(..., min_length=1, max_length=500_000)
    source_file: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMDistillRequest(BaseModel):
    """LLM 知识蒸馏请求。"""

    raw_text: str = Field(..., min_length=1, max_length=500_000)
    source_file: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_preprocessor = None
_extractor = None
_graph_builder = None
_kg_instance = None

_KG_DB_PATH = Path("data") / "knowledge_graph.db"


def _get_neo4j_driver():
    """Deprecated: Web analysis no longer creates a local Neo4j driver."""
    warnings.warn(
        "src.web.routes.analysis._get_neo4j_driver() is deprecated; use "
        "AnalysisIngestionService.project_graph_assets() with StorageBackendFactory "
        "or graph outbox instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return None


def _project_to_neo4j(
    projection_entities: List[Dict[str, Any]],
    projection_relations: List[Dict[str, Any]],
    *,
    session: Any = None,
    db_manager: Any = None,
    storage_factory: Any = None,
    service: Optional[AnalysisIngestionService] = None,
    cycle_id: Optional[str] = None,
    phase: str = "analysis",
    source_file: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, int]:
    """Deprecated compatibility wrapper for legacy graph projection callers."""
    warnings.warn(
        "src.web.routes.analysis._project_to_neo4j() is deprecated; use "
        "AnalysisIngestionService.project_graph_assets() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    projection_service = service or AnalysisIngestionService()
    return projection_service.project_graph_assets(
        projection_entities,
        projection_relations,
        session=session,
        db_manager=db_manager,
        storage_factory=storage_factory,
        cycle_id=cycle_id,
        phase=phase,
        source_file=source_file,
        idempotency_key=idempotency_key,
    )


def _get_kg():
    """获取全局 TCMKnowledgeGraph 实例（SQLite 持久化）。"""
    global _kg_instance  # noqa: PLW0603
    if _kg_instance is None:
        from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph

        _kg_instance = TCMKnowledgeGraph(
            db_path=_KG_DB_PATH,
            preload_formulas=True,
        )
        logger.info(
            "知识图谱已加载: %d 实体, %d 关系 (db=%s)",
            _kg_instance.entity_count,
            _kg_instance.relation_count,
            _KG_DB_PATH,
        )
    return _kg_instance


def _get_preprocessor():
    global _preprocessor  # noqa: PLW0603
    if _preprocessor is None:
        from src.analysis.preprocessor import DocumentPreprocessor

        inst = DocumentPreprocessor()
        inst.initialize()
        _preprocessor = inst
    return _preprocessor


def _get_extractor():
    global _extractor  # noqa: PLW0603
    if _extractor is None:
        from src.analysis.entity_extractor import AdvancedEntityExtractor

        inst = AdvancedEntityExtractor()
        inst.initialize()
        _extractor = inst
    return _extractor


def _get_graph_builder():
    global _graph_builder  # noqa: PLW0603
    if _graph_builder is None:
        from src.analysis.semantic_graph import SemanticGraphBuilder

        inst = SemanticGraphBuilder()
        inst.initialize()
        _graph_builder = inst
    return _graph_builder


def _get_analysis_ingestion_service(request: Request) -> AnalysisIngestionService:
    state = getattr(getattr(request, "app", None), "state", None)
    service_factory = getattr(state, "analysis_ingestion_service_factory", None)
    if service_factory is not None:
        return service_factory(request)
    service = getattr(state, "analysis_ingestion_service", None)
    if service is not None:
        return service

    def _persist_orm(**kwargs: Any) -> Dict[str, int]:
        return _persist_to_orm(request, **kwargs)

    return AnalysisIngestionService(
        preprocessor_provider=_get_preprocessor,
        extractor_provider=_get_extractor,
        graph_builder_provider=_get_graph_builder,
        kg_provider=_get_kg,
        unsupervised_builder=_build_unsupervised_research_assets,
        kg_persistor=_persist_to_kg,
        orm_persistor=_persist_orm,
        research_summary_builder=_build_research_response_summary,
    )


def _json_ready(value: Any) -> Any:
    """递归转换为可稳定写入 JSON 列的数据结构。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, (tuple, set)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "value") and not isinstance(
        value, (str, bytes, int, float, bool)
    ):
        return _json_ready(value.value)
    return value


def _flat_neo4j_props(values: Mapping[str, Any]) -> Dict[str, Any]:
    """Neo4j 属性仅允许标量或标量数组，这里做扁平化过滤。"""
    flattened: Dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            flattened[str(key)] = value
            continue
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            if all(isinstance(item, (str, int, float, bool)) for item in items):
                flattened[str(key)] = items
    return flattened


def _mapping_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _replace_provenance_document_id(value: Any, document_id: str) -> Any:
    if isinstance(value, list):
        return [_replace_provenance_document_id(item, document_id) for item in value]
    if isinstance(value, Mapping):
        payload = {
            key: _replace_provenance_document_id(item, document_id)
            for key, item in value.items()
        }
        if "segment_id" in payload and "quote_text" in payload:
            payload["document_id"] = str(document_id)
        return payload
    return value


def _edge_provenance(edge: Mapping[str, Any]) -> List[Dict[str, Any]]:
    direct = edge.get("provenance")
    if isinstance(direct, list):
        return [dict(item) for item in direct if isinstance(item, Mapping)]
    attrs = (
        edge.get("attributes") if isinstance(edge.get("attributes"), Mapping) else {}
    )
    nested = attrs.get("provenance")
    if isinstance(nested, list):
        return [dict(item) for item in nested if isinstance(item, Mapping)]
    return []


def _edge_rule_quality(edge: Mapping[str, Any]) -> Dict[str, Any]:
    direct = edge.get("rule_quality")
    if isinstance(direct, Mapping):
        return dict(direct)
    attrs = (
        edge.get("attributes") if isinstance(edge.get("attributes"), Mapping) else {}
    )
    nested = attrs.get("rule_quality")
    return dict(nested) if isinstance(nested, Mapping) else {}


def _edge_relation_label(edge: Mapping[str, Any]) -> str:
    attrs = (
        edge.get("attributes") if isinstance(edge.get("attributes"), Mapping) else {}
    )
    return str(
        edge.get("relation")
        or edge.get("rel_type")
        or attrs.get("relationship_type")
        or edge.get("label")
        or "related"
    ).strip()


def _edge_name(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if ":" in text else text


def _store_candidate_relation_insight(
    session: Any,
    LearningInsight: Any,
    *,
    document_id: str,
    source_file: str,
    edge: Mapping[str, Any],
    reason: str,
    source_entity_id: str = "",
    target_entity_id: str = "",
    source_type: str = "",
    target_type: str = "",
) -> bool:
    source = _edge_name(edge.get("source") or edge.get("from"))
    target = _edge_name(edge.get("target") or edge.get("to"))
    relation = _edge_relation_label(edge)
    quality = _edge_rule_quality(edge)
    provenance = _edge_provenance(edge)
    snippet = next(
        (
            str(
                item.get("quote_text") or item.get("text") or item.get("excerpt") or ""
            ).strip()
            for item in provenance
            if isinstance(item, Mapping)
            and str(
                item.get("quote_text") or item.get("text") or item.get("excerpt") or ""
            ).strip()
        ),
        "",
    )
    candidate = {
        "source_entity_id": str(source_entity_id or "").strip(),
        "target_entity_id": str(target_entity_id or "").strip(),
        "source_name": source,
        "target_name": target,
        "source_type": str(source_type or "").strip(),
        "target_type": str(target_type or "").strip(),
        "relationship_type": relation,
        "confidence": float(quality.get("score") or 0.0),
        "source": "rule_relation_quality",
        "signals": [str(quality.get("tier") or "candidate_rule")],
        "evidence": {
            "snippet": snippet,
            "reason": reason,
            "rule_quality": quality,
            "provenance": provenance,
            "document_id": str(document_id),
            "source_file": source_file,
        },
        "created_at": datetime.utcnow().replace(tzinfo=None).isoformat(),
    }
    insight_id = weak_edge_candidate_insight_id(candidate)
    row = session.get(LearningInsight, insight_id)
    existing_payload = {}
    if row is not None:
        existing_payload = extract_weak_edge_candidate_payload(
            {
                "insight_type": row.insight_type,
                "source": row.source,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "evidence_refs_json": list(row.evidence_refs_json or []),
            }
        )
    if row is None:
        row = LearningInsight(insight_id=insight_id)
        session.add(row)
    insight = build_weak_edge_learning_insight(
        candidate,
        target_phase="analysis",
        source_algorithm="rule_relation_quality",
        existing_payload=existing_payload,
        existing_status=row.status if row is not None else None,
        created_at=row.created_at if row is not None else None,
        discovered_at=candidate.get("created_at"),
        legacy_insight_types=["candidate_rule_relation"],
    )
    row.source = str(insight.get("source") or "weak_edge_candidate_repo")
    row.target_phase = str(insight.get("target_phase") or "analysis")
    row.insight_type = str(insight.get("insight_type") or "weak_edge_candidate")
    row.description = str(insight.get("description") or "")
    row.confidence = float(insight.get("confidence") or 0.0)
    row.evidence_refs_json = _json_ready(list(insight.get("evidence_refs_json") or []))
    row.status = str(insight.get("status") or "needs_review")
    created_at = str(insight.get("created_at") or "").strip()
    if created_at:
        row.created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return True


def _build_unsupervised_research_assets(
    raw_text: str,
    source_file: Optional[str],
    entities: List[Dict[str, Any]],
    graph_data: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    research_view = build_unsupervised_research_view(
        raw_text,
        entities,
        graph_data,
        source_file=source_file,
    )
    enriched_entities, enriched_graph = apply_unsupervised_annotations(
        entities,
        graph_data,
        research_view,
    )
    return enriched_entities, enriched_graph, research_view


def _build_research_response_summary(
    research_view: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "document_signature": _json_ready(
            research_view.get("document_signature") or {}
        ),
        "community_topics": _json_ready(
            list(research_view.get("community_topics") or [])[:5]
        ),
        "bridge_entities": _json_ready(
            list(research_view.get("bridge_entities") or [])[:5]
        ),
        "novelty_candidates": _json_ready(
            list(research_view.get("novelty_candidates") or [])[:5]
        ),
        "hypothesis_candidates": _json_ready(
            list(
                research_view.get("hypotheses")
                or research_view.get("hypothesis_candidates")
                or research_view.get("novelty_candidates")
                or []
            )[:5]
        ),
        "literature_alignment": _json_ready(
            list(research_view.get("literature_alignment") or [])
        ),
    }


def _build_summary_analysis(
    semantic_result: Optional[Dict[str, Any]],
    research_view: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    summary = dict(_json_ready((semantic_result or {}).get("summary_analysis") or {}))
    research_view = research_view or {}
    summary["unsupervised_learning"] = {
        "document_signature": _json_ready(
            research_view.get("document_signature") or {}
        ),
        "community_topics": _json_ready(
            list(research_view.get("community_topics") or [])[:8]
        ),
        "bridge_entities": _json_ready(
            list(research_view.get("bridge_entities") or [])[:10]
        ),
        "salient_relations": _json_ready(
            list(research_view.get("salient_relations") or [])[:10]
        ),
        "novelty_candidates": _json_ready(
            list(research_view.get("novelty_candidates") or [])[:10]
        ),
    }
    summary["literature_alignment"] = _json_ready(
        list(research_view.get("literature_alignment") or [])
    )
    return summary


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/formula")
def analyze_formula(
    body: FormulaAnalysisRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """方剂综合分析 — 调用 ResearchScoringPanel。"""
    try:
        from src.analysis.research_scoring import ResearchScoringPanel

        result = ResearchScoringPanel.score_research_perspective(
            perspective=body.perspective,
            formula_comparisons=body.formula_comparisons,
            weights=body.weights,
        )
        return {"message": "方剂分析完成", "result": result}
    except Exception as exc:
        logger.exception("方剂分析失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"方剂分析失败: {exc}",
        ) from exc


@router.post("/text")
def analyze_text(
    request: Request,
    body: TextAnalysisRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """文本处理链 — 预处理 → 实体抽取 → 语义建模 → 知识沉淀。"""
    try:
        service = _get_analysis_ingestion_service(request)
        return service.analyze_and_persist(
            body.raw_text,
            body.source_file,
            body.metadata,
        )
    except Exception as exc:
        logger.exception("文本分析链失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文本分析失败: {exc}",
        ) from exc


def _persist_to_kg(
    entities: List[Dict[str, Any]],
    graph_data: Dict[str, Any],
) -> Dict[str, int]:
    """将抽取的实体与关系写入持久化知识图谱。"""
    kg = _get_kg()
    before_ent = kg.entity_count
    before_rel = kg.relation_count

    # 实体
    ent_rows = []
    for ent in entities:
        name = ent.get("name") or ent.get("text") or ent.get("value", "")
        if not name:
            continue
        etype = ent.get("type") or ent.get("entity_type") or "generic"
        meta = {
            k: v for k, v in ent.items() if k not in ("name", "type", "entity_type")
        }
        ent_rows.append({"name": name, "type": etype, **meta})
    if ent_rows:
        kg.bulk_add_entities(ent_rows)

    # 关系
    edges = graph_data.get("edges", [])
    rel_rows = []
    for e in edges:
        if not is_promotable_rule_edge(e):
            continue
        src = e.get("source") or e.get("from", "")
        dst = e.get("target") or e.get("to", "")
        rel = e.get("relation") or e.get("rel_type") or e.get("label") or "related"
        if src and dst:
            meta = {
                k: v
                for k, v in e.items()
                if k
                not in (
                    "source",
                    "target",
                    "from",
                    "to",
                    "relation",
                    "rel_type",
                    "label",
                )
            }
            rel_rows.append((src, rel, dst, meta))
    if rel_rows:
        kg.bulk_add_relations(rel_rows)

    return {
        "new_entities": kg.entity_count - before_ent,
        "new_relations": kg.relation_count - before_rel,
    }


# ---------------------------------------------------------------------------
# 主数据库 ORM 持久化
# ---------------------------------------------------------------------------

# 实体类型映射：KG 域名 → ORM EntityTypeEnum
_TYPE_MAP = {
    "herb": "herb",
    "formula": "formula",
    "syndrome": "syndrome",
    "efficacy": "efficacy",
    "property": "property",
    "taste": "taste",
    "meridian": "meridian",
    "symptom": "other",
    "theory": "other",
    "generic": "other",
}

# 关系名 → ORM RelationshipType.relationship_type 映射
_REL_TYPE_MAP = {
    "君": "SOVEREIGN",
    "臣": "MINISTER",
    "佐": "ASSISTANT",
    "使": "ENVOY",
    "sovereign": "SOVEREIGN",
    "minister": "MINISTER",
    "assistant": "ASSISTANT",
    "envoy": "ENVOY",
    "治疗": "TREATS",
    "treats": "TREATS",
    "功效": "HAS_EFFICACY",
    "has_efficacy": "HAS_EFFICACY",
    "efficacy": "HAS_EFFICACY",
    "类似": "SIMILAR_TO",
    "similar_to": "SIMILAR_TO",
    "包含": "CONTAINS",
    "contains": "CONTAINS",
    "composition": "CONTAINS",
    "related": "CONTAINS",
}


def _slugify_topic_key(value: str) -> str:
    """把任意 community label / id 收敛成稳定 Topic.key（ASCII 优先，空格/标点变 _）。"""
    raw = (value or "").strip()
    if not raw:
        return ""
    cleaned = []
    for ch in raw:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            cleaned.append(ch)
        elif ch in "-_":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    key = "".join(cleaned).strip("_")
    return key[:128] if key else ""


def _sync_community_topics_to_catalog(
    document_id: str,
    community_topics: List[Dict[str, Any]],
) -> int:
    """Deprecated: topic membership is now queued through graph projection outbox."""
    if not document_id or not community_topics:
        return 0
    logger.debug(
        "Catalog topic sync deferred to graph outbox (document_id=%s, topics=%d)",
        document_id,
        len(community_topics),
    )
    return 0


def _persist_to_orm(
    request: Request,
    entities: List[Dict[str, Any]],
    graph_data: Dict[str, Any],
    source_file: Optional[str] = None,
    created_by: str = "text_analysis",
    raw_text: str = "",
    metadata: Optional[Mapping[str, Any]] = None,
    semantic_result: Optional[Dict[str, Any]] = None,
    research_view: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """将抽取结果写入主应用数据库，并通过 graph outbox 排队投影。"""
    db_mgr = getattr(getattr(request, "app", None), "state", None)
    db_mgr = getattr(db_mgr, "db_manager", None) if db_mgr else None
    if db_mgr is None:
        logger.debug("DatabaseManager 未就绪，跳过 ORM 持久化")
        return {
            "orm_entities": 0,
            "orm_relations": 0,
            "candidate_relations": 0,
            "orm_statistics": 0,
            "orm_analyses": 0,
            "neo4j_nodes": 0,
            "neo4j_edges": 0,
            "needs_backfill": False,
        }

    from src.infrastructure.persistence import (
        Document,
        Entity,
        EntityRelationship,
        EntityTypeEnum,
        LearningInsight,
        ProcessingStatistics,
        ProcessStatusEnum,
        RelationshipType,
        ResearchAnalysis,
    )

    orm_ent_count = 0
    orm_rel_count = 0
    candidate_relation_count = 0
    orm_stats_count = 0
    orm_analysis_count = 0
    projection_entities: List[Dict[str, Any]] = []
    projection_relations: List[Dict[str, Any]] = []
    neo4j_proj: Dict[str, Any] = {
        "neo4j_nodes": 0,
        "neo4j_edges": 0,
        "graph_projection_status": "skipped",
        "graph_projection_mode": "outbox",
        "needs_backfill": False,
    }
    semantic_result = semantic_result or {}
    research_view = research_view or {}
    request_metadata = dict(metadata or {}) if isinstance(metadata, Mapping) else {}

    def _document_identity_fields() -> Dict[str, Any]:
        identity = request_metadata.get("canonical_document_identity") or {}
        if not isinstance(identity, Mapping):
            return {}
        fields: Dict[str, Any] = {}
        for key in (
            "canonical_document_key",
            "canonical_title",
            "normalized_title",
            "source_file_hash",
            "edition_hint",
            "document_key_version",
            "dynasty",
            "author",
        ):
            value = str(identity.get(key) or "").strip()
            if value:
                fields[key] = (
                    value.lower()
                    if key.endswith("hash") or key == "canonical_document_key"
                    else value
                )
        return fields

    def _apply_document_identity(doc: Any, identity_fields: Mapping[str, Any]) -> None:
        for key, value in identity_fields.items():
            if value and not getattr(doc, key, None):
                setattr(doc, key, value)
        if identity_fields.get("canonical_title") and not doc.document_title:
            doc.document_title = str(identity_fields["canonical_title"])
        if identity_fields.get("canonical_title") and not doc.work_title:
            doc.work_title = str(identity_fields["canonical_title"])
        if identity_fields.get("edition_hint") and not doc.edition:
            doc.edition = str(identity_fields["edition_hint"])

        version_metadata = dict(doc.version_metadata_json or {})
        encoding_report = request_metadata.get("encoding_report")
        if isinstance(encoding_report, Mapping):
            version_metadata["corpus_encoding"] = _json_ready(encoding_report)
        canonical_identity = request_metadata.get("canonical_document_identity")
        if isinstance(canonical_identity, Mapping):
            version_metadata["canonical_document_identity"] = _json_ready(
                canonical_identity
            )
        if version_metadata:
            doc.version_metadata_json = version_metadata

    try:
        with db_mgr.session_scope() as session:
            # 1) 创建/复用 Document 记录
            #    T2.3: source_file 不再叠加时间戳后缀；自然键变为
            #    (source_file, content_hash)，以 SHA-256 内容指纹去重。
            #    ingest_run_id 保留时间维度信息便于审计/回放。
            import hashlib as _hashlib
            import time as _time
            import uuid as _uuid

            ts = _time.strftime("%Y%m%d_%H%M%S")
            uid = _uuid.uuid4().hex[:8]
            sf = (source_file or created_by or "").strip() or created_by
            text_for_hash = raw_text or ""
            provenance_index = (
                TextSegmentIndex(text_for_hash, document_id="")
                if text_for_hash
                else None
            )
            content_hash = _hashlib.sha256(
                text_for_hash.encode("utf-8", errors="replace")
            ).hexdigest()
            ingest_run_id = f"{ts}_{uid}"
            identity_fields = _document_identity_fields()
            canonical_document_key = identity_fields.get("canonical_document_key")
            existing = None
            if canonical_document_key:
                existing = (
                    session.query(Document)
                    .filter_by(canonical_document_key=canonical_document_key)
                    .order_by(Document.created_at.asc())
                    .first()
                )
            if existing is None:
                existing = (
                    session.query(Document)
                    .filter_by(source_file=sf, content_hash=content_hash)
                    .one_or_none()
                )
            if existing is not None:
                _apply_document_identity(existing, identity_fields)
                session.flush()
                # T2.3 dedup short-circuit: 同 source_file + 同内容 hash 已入库 → 返回 no-op，
                # 避免重复 entities/relationships 写入。
                logger.info(
                    "documents dedup hit: source_file=%s content_hash=%s doc_id=%s — skip re-ingest",
                    sf,
                    content_hash[:12],
                    existing.id,
                )
                return {
                    "orm_entities": 0,
                    "orm_relations": 0,
                    "candidate_relations": 0,
                    "orm_statistics": 0,
                    "orm_analyses": 0,
                    "neo4j_nodes": 0,
                    "neo4j_edges": 0,
                    "needs_backfill": False,
                    "deduplicated": True,
                    "document_id": str(existing.id),
                    "content_hash": content_hash,
                    "canonical_document_key": existing.canonical_document_key,
                }
            doc = Document(
                source_file=sf,
                content_hash=content_hash,
                ingest_run_id=ingest_run_id,
                canonical_document_key=identity_fields.get("canonical_document_key"),
                canonical_title=identity_fields.get("canonical_title"),
                normalized_title=identity_fields.get("normalized_title"),
                source_file_hash=identity_fields.get("source_file_hash"),
                edition_hint=identity_fields.get("edition_hint"),
                document_key_version=identity_fields.get("document_key_version"),
                dynasty=identity_fields.get("dynasty"),
                author=identity_fields.get("author"),
                document_title=identity_fields.get("canonical_title"),
                work_title=identity_fields.get("canonical_title"),
                edition=identity_fields.get("edition_hint"),
                raw_text_size=len(text_for_hash)
                or sum(len(e.get("name", "")) for e in entities),
                entities_extracted_count=len(entities),
                process_status=ProcessStatusEnum.COMPLETED,
                notes=f"由 {created_by} 自动写入；已附加无监督科研增强信号",
            )
            _apply_document_identity(doc, identity_fields)
            session.add(doc)
            session.flush()  # 获取 doc.id
            if provenance_index is not None:
                provenance_index.document_id = str(doc.id)
                provenance_index.segments = [
                    segment.with_document_id(str(doc.id))
                    for segment in provenance_index.segments
                ]

            entities = (
                attach_provenance_to_entities(entities, provenance_index)
                if provenance_index is not None
                else entities
            )
            graph_data = (
                {
                    **graph_data,
                    "edges": attach_provenance_to_edges(
                        graph_data.get("edges", []), provenance_index
                    ),
                }
                if provenance_index is not None
                else graph_data
            )

            # 2) 预加载 RelationshipType 映射
            rel_types = {
                rt.relationship_type: rt for rt in session.query(RelationshipType).all()
            }

            # 3) 写入实体，同时建 name → Entity 映射
            name_to_entity: Dict[str, Entity] = {}
            entity_payload_by_name: Dict[str, Dict[str, Any]] = {}
            for ent in entities:
                name = ent.get("name") or ent.get("text") or ent.get("value", "")
                if not name or name in name_to_entity:
                    continue
                raw_type = (
                    ent.get("type") or ent.get("entity_type") or "generic"
                ).lower()
                mapped = _TYPE_MAP.get(raw_type, "other")
                try:
                    etype = EntityTypeEnum(mapped)
                except ValueError:
                    etype = EntityTypeEnum.OTHER
                entity_obj = Entity(
                    document_id=doc.id,
                    name=name,
                    type=etype,
                    confidence=float(ent.get("confidence", 0.6)),
                    entity_metadata=_json_ready(
                        _replace_provenance_document_id(
                            {
                                k: v
                                for k, v in ent.items()
                                if k
                                not in ("name", "type", "entity_type", "confidence")
                            },
                            str(doc.id),
                        )
                    ),
                )
                session.add(entity_obj)
                name_to_entity[name] = entity_obj
                entity_payload_by_name[name] = dict(ent)
                orm_ent_count += 1
            session.flush()  # 让所有 entity_obj 获得 id

            # 4) 写入关系
            #    边的 source/target 可能带类型前缀（如 "herb:甘草"），需剥离
            def _resolve_entity(raw_name: str):
                """按原名 → 去前缀 → 冒号后部分 查找已入库实体。"""
                ent = name_to_entity.get(raw_name)
                if ent is not None:
                    return ent
                # 去掉 "herb:" 等前缀
                if ":" in raw_name:
                    plain = raw_name.split(":", 1)[1]
                    ent = name_to_entity.get(plain)
                    if ent is not None:
                        return ent
                return None

            edges = graph_data.get("edges", [])
            default_rt = rel_types.get("CONTAINS")
            for e in edges:
                src_name = e.get("source") or e.get("from", "")
                dst_name = e.get("target") or e.get("to", "")
                if not src_name or not dst_name:
                    continue
                src_ent = _resolve_entity(src_name)
                dst_ent = _resolve_entity(dst_name)
                source_type = (
                    getattr(src_ent.type, "value", src_ent.type)
                    if src_ent is not None
                    and getattr(src_ent, "type", None) is not None
                    else ""
                )
                target_type = (
                    getattr(dst_ent.type, "value", dst_ent.type)
                    if dst_ent is not None
                    and getattr(dst_ent, "type", None) is not None
                    else ""
                )
                edge_quality = _edge_rule_quality(e)
                edge_provenance = _edge_provenance(e)
                edge_tier = str(edge_quality.get("tier") or "").strip()
                if edge_quality and (
                    edge_tier in CANDIDATE_RULE_TIERS
                    or not is_promotable_rule_edge(e)
                    or not edge_provenance
                ):
                    if _store_candidate_relation_insight(
                        session,
                        LearningInsight,
                        document_id=str(doc.id),
                        source_file=sf,
                        edge=e,
                        reason=str(
                            edge_quality.get("evidence_reason")
                            or "candidate_or_missing_provenance"
                        ),
                        source_entity_id=str(src_ent.id) if src_ent is not None else "",
                        target_entity_id=str(dst_ent.id) if dst_ent is not None else "",
                        source_type=str(source_type),
                        target_type=str(target_type),
                    ):
                        candidate_relation_count += 1
                    continue
                if not edge_provenance:
                    if _store_candidate_relation_insight(
                        session,
                        LearningInsight,
                        document_id=str(doc.id),
                        source_file=sf,
                        edge=e,
                        reason="missing_text_segment",
                        source_entity_id=str(src_ent.id) if src_ent is not None else "",
                        target_entity_id=str(dst_ent.id) if dst_ent is not None else "",
                        source_type=str(source_type),
                        target_type=str(target_type),
                    ):
                        candidate_relation_count += 1
                    continue
                # 若目标实体不在本批实体中，自动补录
                if dst_ent is None and dst_name:
                    plain_dst = (
                        dst_name.split(":", 1)[-1] if ":" in dst_name else dst_name
                    )
                    prefix_type = (
                        dst_name.split(":", 1)[0] if ":" in dst_name else "other"
                    )
                    mapped = _TYPE_MAP.get(prefix_type, "other")
                    try:
                        etype = EntityTypeEnum(mapped)
                    except ValueError:
                        etype = EntityTypeEnum.OTHER
                    dst_ent = Entity(
                        document_id=doc.id,
                        name=plain_dst,
                        type=etype,
                        confidence=0.4,
                        entity_metadata=_json_ready(
                            {
                                "auto_created_from_relation": True,
                                "unsupervised_learning": (
                                    research_view.get("entity_annotations") or {}
                                ).get(plain_dst, {}),
                            }
                        ),
                    )
                    session.add(dst_ent)
                    session.flush()
                    name_to_entity[plain_dst] = dst_ent
                    entity_payload_by_name[plain_dst] = {
                        "name": plain_dst,
                        "type": prefix_type,
                        "unsupervised_learning": (
                            research_view.get("entity_annotations") or {}
                        ).get(plain_dst, {}),
                    }
                    orm_ent_count += 1
                if src_ent is None or dst_ent is None:
                    continue
                # 关系类型可能在顶层或 attributes 子字典中
                attrs = e.get("attributes") or {}
                raw_rel = (
                    e.get("relation")
                    or e.get("rel_type")
                    or attrs.get("relationship_type")
                    or e.get("label")
                    or "related"
                )
                mapped_rel = _REL_TYPE_MAP.get(raw_rel, "CONTAINS")
                rt_obj = rel_types.get(mapped_rel, default_rt)
                if rt_obj is None:
                    continue
                edge_confidence = float(
                    e.get("confidence") or attrs.get("confidence", 0.5)
                )
                relationship_metadata = {
                    k: v
                    for k, v in e.items()
                    if k
                    not in (
                        "source",
                        "target",
                        "from",
                        "to",
                        "relation",
                        "rel_type",
                        "label",
                        "confidence",
                        "evidence",
                        "attributes",
                    )
                }
                if attrs:
                    relationship_metadata["attributes"] = attrs
                relationship_metadata = _replace_provenance_document_id(
                    relationship_metadata, str(doc.id)
                )
                rel_obj = EntityRelationship(
                    source_entity_id=src_ent.id,
                    target_entity_id=dst_ent.id,
                    relationship_type_id=rt_obj.id,
                    confidence=edge_confidence,
                    created_by_module=created_by,
                    evidence=e.get("evidence") or attrs.get("description"),
                    relationship_metadata=_json_ready(relationship_metadata),
                )
                session.add(rel_obj)
                orm_rel_count += 1
                # 收集 Neo4j 投影
                salience = attrs.get("salience") or {}
                novelty = attrs.get("novelty") or {}
                projection_relations.append(
                    {
                        "src_id": src_ent.id,
                        "dst_id": dst_ent.id,
                        "rel_type": mapped_rel,
                        "props": _flat_neo4j_props(
                            {
                                "confidence": edge_confidence,
                                "created_by": created_by,
                                "association_score": salience.get("association_score"),
                                "cross_community": salience.get("cross_community"),
                                "novelty_score": novelty.get("novelty_score"),
                                "novelty_reason": novelty.get("reason"),
                            }
                        ),
                    }
                )

            entity_type_counts = Counter(
                e_obj.type.value if hasattr(e_obj.type, "value") else str(e_obj.type)
                for e_obj in name_to_entity.values()
            )
            doc_signature = dict(research_view.get("document_signature") or {})
            source_modules = [
                created_by,
                "semantic_graph",
                "unsupervised_research_enhancer",
            ]
            if candidate_relation_count:
                source_modules.append("rule_relation_quality")
            processing_stats = ProcessingStatistics(
                document_id=doc.id,
                formulas_count=int(entity_type_counts.get("formula", 0)),
                herbs_count=int(entity_type_counts.get("herb", 0)),
                syndromes_count=int(entity_type_counts.get("syndrome", 0)),
                efficacies_count=int(entity_type_counts.get("efficacy", 0)),
                relationships_count=orm_rel_count,
                graph_nodes_count=int(
                    doc_signature.get("entity_count", len(name_to_entity))
                ),
                graph_edges_count=int(doc_signature.get("relation_count", len(edges))),
                graph_density=float(doc_signature.get("graph_density", 0.0)),
                connected_components=int(doc_signature.get("connected_components", 0)),
                source_modules=list(dict.fromkeys(source_modules)),
                processing_time_ms=0,
            )
            session.add(processing_stats)
            orm_stats_count = 1

            research_analysis = ResearchAnalysis(
                document_id=doc.id,
                research_perspectives=_json_ready(
                    {
                        **_mapping_payload(
                            semantic_result.get("research_perspectives")
                        ),
                        "latent_topics": list(
                            research_view.get("community_topics") or []
                        ),
                        "document_signature": research_view.get("document_signature")
                        or {},
                    }
                ),
                formula_comparisons=_json_ready(
                    semantic_result.get("formula_comparisons") or {}
                ),
                herb_properties_analysis=_json_ready(
                    semantic_result.get("herb_properties_analysis")
                    or semantic_result.get("herb_properties")
                    or {}
                ),
                pharmacology_integration=_json_ready(
                    semantic_result.get("pharmacology_integration") or {}
                ),
                network_pharmacology=_json_ready(
                    semantic_result.get("network_pharmacology")
                    or semantic_result.get("network_pharmacology_systems_biology")
                    or {}
                ),
                supramolecular_physicochemistry=_json_ready(
                    semantic_result.get("supramolecular_physicochemistry") or {}
                ),
                knowledge_archaeology=_json_ready(
                    {
                        **_mapping_payload(
                            semantic_result.get("knowledge_archaeology")
                        ),
                        "bridge_entities": list(
                            research_view.get("bridge_entities") or []
                        ),
                        "literature_alignment": list(
                            research_view.get("literature_alignment") or []
                        ),
                    }
                ),
                complexity_dynamics=_json_ready(
                    {
                        **_mapping_payload(
                            semantic_result.get("complexity_dynamics")
                            or semantic_result.get("complexity_nonlinear_dynamics")
                        ),
                        "salient_relations": list(
                            research_view.get("salient_relations") or []
                        ),
                        "novelty_candidates": list(
                            research_view.get("novelty_candidates") or []
                        ),
                    }
                ),
                research_scoring_panel=_json_ready(
                    semantic_result.get("research_scoring_panel") or {}
                ),
                summary_analysis=_json_ready(
                    _build_summary_analysis(semantic_result, research_view)
                ),
            )
            session.add(research_analysis)
            orm_analysis_count = 1

            # 在 commit 前收集所有 entity 投影
            session.flush()
            for e_obj in name_to_entity.values():
                entity_payload = entity_payload_by_name.get(e_obj.name, {})
                unsupervised_meta = (
                    entity_payload.get("unsupervised_learning")
                    or (
                        (entity_payload.get("metadata") or {}).get(
                            "unsupervised_learning"
                        )
                        if isinstance(entity_payload.get("metadata"), dict)
                        else {}
                    )
                    or {}
                )
                projection_entities.append(
                    {
                        "id": e_obj.id,
                        "name": e_obj.name,
                        "type": (
                            e_obj.type.value
                            if hasattr(e_obj.type, "value")
                            else str(e_obj.type)
                        ),
                        "props": _flat_neo4j_props(
                            {
                                "confidence": float(e_obj.confidence or 0.0),
                                "community_id": unsupervised_meta.get("community_id"),
                                "topic_label": unsupervised_meta.get("topic_label"),
                                "topic_size": unsupervised_meta.get("topic_size"),
                                "pagerank": unsupervised_meta.get("pagerank"),
                                "bridge_score": unsupervised_meta.get("bridge_score"),
                            }
                        ),
                    }
                )

            document_projection_key = str(doc_signature.get("document_key") or "")
            for node in list(
                research_view.get("neo4j_projection", {}).get("nodes") or []
            ):
                projection_node = dict(node)
                if projection_node.get("type") == "research_document":
                    projection_node["id"] = str(doc.id)
                    projection_node["name"] = doc.source_file
                projection_node["props"] = _flat_neo4j_props(
                    projection_node.get("props") or {}
                )
                projection_entities.append(projection_node)
            for relation in list(
                research_view.get("neo4j_projection", {}).get("edges") or []
            ):
                projection_relation = dict(relation)
                if (
                    str(projection_relation.get("src_id") or "")
                    == document_projection_key
                ):
                    projection_relation["src_id"] = str(doc.id)
                if (
                    str(projection_relation.get("dst_id") or "")
                    == document_projection_key
                ):
                    projection_relation["dst_id"] = str(doc.id)
                member_name = str(projection_relation.get("dst_id") or "")
                if member_name in name_to_entity:
                    projection_relation["dst_id"] = name_to_entity[member_name].id
                src_name = str(projection_relation.get("src_id") or "")
                if src_name in name_to_entity:
                    projection_relation["src_id"] = name_to_entity[src_name].id
                projection_relation["props"] = _flat_neo4j_props(
                    projection_relation.get("props") or {}
                )
                projection_relations.append(projection_relation)

            # T6.1+: 同事务向 graph outbox 写入投影任务，便于后台 worker 异步消费 Neo4j。
            try:
                neo4j_proj = AnalysisIngestionService().project_graph_assets(
                    projection_entities,
                    projection_relations,
                    session=session,
                    cycle_id=str(doc.id),
                    phase="analysis",
                    source_file=sf,
                    idempotency_key=f"web-analysis:{doc.id}:{content_hash}",
                )
            except Exception:
                logger.debug("graph outbox enqueue skipped", exc_info=True)
            # session_scope 自动 commit
    except Exception:
        logger.exception("ORM 持久化失败（不影响 KG 侧已写入的数据）")

    # T3.2: 把 community_topics 同步到 Catalog (Topic / BELONGS_TO_TOPIC)。
    # 旧 ResearchTopic / HAS_LATENT_TOPIC / HAS_TOPIC_MEMBER 边由 _build_neo4j_projection
    # 继续生成（已发 DeprecationWarning），后续版本删除。
    catalog_topic_count = 0
    try:
        document_id_for_catalog = ""
        # 从 projection_entities 取出 research_document 节点（其 id 已替换为 ORM doc.id）
        for node in projection_entities:
            if str(node.get("type")) == "research_document":
                document_id_for_catalog = str(node.get("id") or "")
                break
        if document_id_for_catalog and research_view:
            catalog_topic_count = _sync_community_topics_to_catalog(
                document_id_for_catalog,
                research_view.get("community_topics") or [],
            )
    except Exception:
        logger.warning("CatalogContext sync failed (non-fatal)", exc_info=True)

    if orm_ent_count > 0 or orm_rel_count > 0:
        logger.info(
            "ORM 持久化完成 (entities=%d, relations=%d, candidate_relations=%d, statistics=%d, analyses=%d); Neo4j 投影 (nodes=%d, edges=%d); Catalog topics=%d",
            orm_ent_count,
            orm_rel_count,
            candidate_relation_count,
            orm_stats_count,
            orm_analysis_count,
            neo4j_proj.get("neo4j_nodes", 0),
            neo4j_proj.get("neo4j_edges", 0),
            catalog_topic_count,
        )

    return {
        "orm_entities": orm_ent_count,
        "orm_relations": orm_rel_count,
        "candidate_relations": candidate_relation_count,
        "orm_statistics": orm_stats_count,
        "orm_analyses": orm_analysis_count,
        "neo4j_nodes": neo4j_proj.get("neo4j_nodes", 0),
        "neo4j_edges": neo4j_proj.get("neo4j_edges", 0),
        "catalog_topics": catalog_topic_count,
        "needs_backfill": False,
    }


# ---------------------------------------------------------------------------
# LLM 知识蒸馏
# ---------------------------------------------------------------------------
import re as _re

_LLM_DISTILL_PROMPT = """\
你是中医知识图谱专家。请从下面的古医籍文本中提取中医知识三元组，严格按照JSON格式输出。

规则：
1. entities：只提取"中药"、"方剂"、"证候/病症"、"功效"四类实体，名称必须是规范中医术语，长度不超过10个汉字。
2. relations：source 和 target 必须来自已提取的实体，relation 只能是以下之一：
   contains（含有）、treats（主治）、has_efficacy（功效）、has_property（药性）、
   contraindicated_with（禁忌）、belongs_to_formula（属于方剂）、transforms_to（证候转化）
3. 不得捏造文本中不存在的内容，不得输出完整句子作为实体名称。
4. 仅输出JSON，不加任何说明，格式如下：
{{"entities":[{{"name":"麻黄","type":"herb"}},{{"name":"麻黄汤","type":"formula"}}],"relations":[{{"source":"麻黄汤","relation":"contains","target":"麻黄"}}]}}

文本：
{text}"""

# 中文约 2 token/字；4096 上下文 - 640 生成 - ~350 prompt ≈ 900 字 / 片
_DISTILL_TEXT_LIMIT = 900
_DISTILL_MAX_TOKENS = 640

# 用于后处理：实体名合法性验证
_ENTITY_NOISE_RE = _re.compile(r"[，。、；：！？,\.;:?!（）()\[\]「」\"'" "''\s]")
_ENTITY_NOISE_PREFIXES = (
    "加",
    "各",
    "每",
    "或",
    "若",
    "用",
    "以",
    "再",
    "另",
    "将",
    "兼",
    "并",
    "如",
    "且",
    "即",
    "是",
    "此",
    "故",
    "则",
    "凡",
    "宜",
    "当",
)
_ENTITY_NOISE_EXACT = {
    "小儿",
    "妇人",
    "男子",
    "病人",
    "病者",
    "诸药",
    "上药",
    "服药",
    "共享",
    "以上",
    "上述",
    "主治",
    "功效",
    "方药",
    "治法",
    "疗法",
}
_RELATION_CN_TO_EN = {
    "含有": "contains",
    "主治": "treats",
    "功效": "has_efficacy",
    "药性": "has_property",
    "禁忌": "contraindicated_with",
    "属于": "belongs_to_formula",
    "转化": "transforms_to",
    "related": "related",
}


def _repair_json(raw: str) -> str:
    """尝试修复常见 LLM JSON 幻觉：去除尾逗号、替换单引号、补齐括号。"""
    # 去 markdown 块
    if "```" in raw:
        inner = raw.split("```", 1)[1]
        if inner.startswith("json"):
            inner = inner[4:]
        raw = inner.split("```", 1)[0]
    text = raw.strip()
    # 移除 JSON 对象/数组末尾多余逗号
    text = _re.sub(r",\s*([}\]])", r"\1", text)
    # 替换单引号键值（简单情况）
    text = _re.sub(r"(?<![\w\\])'", '"', text)
    # 移除控制字符
    text = _re.sub(r"[\x00-\x1f\x7f]", " ", text)
    return text


def _validate_entity_name(name: str, max_len: int = 10) -> bool:
    """返回 True 表示实体名合法。"""
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    if len(name) < 2 or len(name) > max_len:
        return False
    if _ENTITY_NOISE_RE.search(name):
        return False
    if name in _ENTITY_NOISE_EXACT:
        return False
    if any(name.startswith(p) for p in _ENTITY_NOISE_PREFIXES):
        return False
    return True


def _normalize_relation(rel_type: str) -> str:
    """将中文/非标准关系类型映射到英文标准名；未知则保留原值。"""
    if not isinstance(rel_type, str):
        return "related"
    return _RELATION_CN_TO_EN.get(rel_type.strip(), rel_type.strip() or "related")


def _resolve_distill_template_task(metadata: Optional[Mapping[str, Any]]) -> str:
    metadata = dict(metadata or {}) if isinstance(metadata, Mapping) else {}
    requested = str(
        metadata.get("distill_template_task")
        or metadata.get("llm_reasoning_task")
        or metadata.get("llm_task_type")
        or "entity_extraction"
    ).strip()
    if requested == "relation_judgment":
        return "relation_judgement"
    if requested in {"entity_extraction", "relation_judgement"}:
        return requested
    return "entity_extraction"


def _resolve_positive_int_from_metadata(
    metadata: Optional[Mapping[str, Any]], keys: List[str]
) -> Optional[int]:
    if not isinstance(metadata, Mapping):
        return None
    for key in keys:
        value = metadata.get(key)
        if value in (None, ""):
            continue
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized > 0:
            return normalized
    return None


def _build_distill_prompt_version(metadata: Mapping[str, Any]) -> str:
    template_id = str(metadata.get("template_id") or "analysis.distill").strip()
    version = str(
        metadata.get("template_version") or metadata.get("version") or "unknown"
    ).strip()
    if template_id and version and "@" not in template_id:
        return f"{template_id}@{version}"
    return template_id or version or "analysis.distill@unknown"


def _summarize_llm_gateway_result(result: Any, *, chunk_index: int) -> Dict[str, Any]:
    metadata = dict(getattr(result, "metadata", {}) or {})
    return {
        "chunk_index": chunk_index,
        "prompt_version": getattr(result, "prompt_version", None)
        or metadata.get("prompt_version"),
        "model_id": getattr(result, "model_id", None) or metadata.get("model_id"),
        "latency_s": getattr(result, "latency_s", None) or metadata.get("latency_s"),
        "token_budget": getattr(result, "token_budget", None)
        or metadata.get("token_budget"),
        "json_repair_status": getattr(result, "json_repair_status", None)
        or metadata.get("json_repair_status"),
        "attempts_used": metadata.get("attempts_used"),
        "retry_count": metadata.get("retry_count"),
        "timeout_s": metadata.get("timeout_s"),
        "gpu_params": metadata.get("gpu_params") or {},
        "warnings": list(getattr(result, "warnings", []) or []),
    }


def _summarize_llm_gateway_calls(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    statuses = Counter(
        str(item.get("json_repair_status") or "unknown") for item in calls
    )
    latency_values = [
        float(item.get("latency_s") or 0.0)
        for item in calls
        if item.get("latency_s") is not None
    ]
    return {
        "call_count": len(calls),
        "prompt_versions": sorted(
            {str(item.get("prompt_version") or "unknown") for item in calls}
        ),
        "model_ids": sorted({str(item.get("model_id") or "unknown") for item in calls}),
        "json_repair_status_counts": dict(statuses),
        "latency_s_total": round(sum(latency_values), 4),
    }


@router.post("/distill")
def llm_distill(
    request: Request,
    body: LLMDistillRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """LLM 知识蒸馏 — 用本地大模型从文本中抽取知识三元组并沉淀到知识图谱。"""
    import json as _json

    try:
        # 获取 LLM 引擎（复用 assistant 路由的单例）
        from src.web.routes.assistant import _get_engine

        assistant = _get_engine()
        llm = assistant._get_llm()
        if llm is None:
            reason = (
                getattr(assistant, "_last_llm_load_error", "")
                or "未知原因，请检查模型文件是否存在与 llm 配置"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"本地 LLM 引擎未加载，无法进行知识蒸馏：{reason}",
            )
        llm_gateway = LLMGateway(llm)

        # 分片蒸馏 — 长文本按 _DISTILL_TEXT_LIMIT 切片逐段调用 LLM
        full_text = body.raw_text
        provenance_index = TextSegmentIndex(
            full_text,
            document_id=(body.source_file or "llm_distill"),
            max_segment_chars=_DISTILL_TEXT_LIMIT,
        )
        chunks = [
            full_text[i : i + _DISTILL_TEXT_LIMIT]
            for i in range(0, len(full_text), _DISTILL_TEXT_LIMIT)
        ]
        llm_entities: List[Dict[str, Any]] = []
        llm_relations: List[Dict[str, Any]] = []
        distill_template_task = _resolve_distill_template_task(body.metadata)
        distill_template_metadata: Dict[str, Any] = {}
        llm_gateway_calls: List[Dict[str, Any]] = []
        distill_token_budget = _resolve_positive_int_from_metadata(
            body.metadata,
            ["token_budget", "llm_token_budget", "distill_token_budget"],
        )
        distill_retry_count = _resolve_positive_int_from_metadata(
            body.metadata,
            ["retry_count", "llm_retry_count", "distill_retry_count"],
        )
        distill_timeout_s = _resolve_positive_int_from_metadata(
            body.metadata,
            ["timeout_s", "llm_timeout_s", "distill_timeout_s"],
        )

        # 临时收紧 max_tokens 以加速蒸馏（结束后恢复）
        _saved_max_tokens = getattr(llm, "max_tokens", None)
        try:
            llm.max_tokens = _DISTILL_MAX_TOKENS
        except Exception:
            pass

        for idx, chunk in enumerate(chunks):
            try:
                rendered_prompt = render_philology_reasoning_prompt(
                    distill_template_task,
                    payload={
                        "text": chunk,
                        "source_file": body.source_file or "",
                        "chunk_index": idx,
                        "chunk_count": len(chunks),
                        "metadata": body.metadata or {},
                    },
                    context={
                        "route": "analysis.distill",
                        "task": distill_template_task,
                    },
                )
                distill_template_metadata = dict(rendered_prompt.metadata)
                prompt = rendered_prompt.user_prompt
                gateway_result = llm_gateway.generate(
                    LLMGatewayRequest(
                        prompt=prompt,
                        system_prompt=rendered_prompt.system_prompt,
                        prompt_version=_build_distill_prompt_version(
                            distill_template_metadata
                        ),
                        phase="analysis",
                        purpose="knowledge_distill",
                        task_type=distill_template_task,
                        token_budget=distill_token_budget,
                        timeout_s=distill_timeout_s,
                        retry_count=distill_retry_count or 1,
                        json_output=True,
                        context={
                            "route": "analysis.distill",
                            "source_file": body.source_file or "",
                            "chunk_index": idx,
                            "chunk_count": len(chunks),
                        },
                        metadata={
                            "prompt_name": distill_template_metadata.get("template_id"),
                            "prompt_version": _build_distill_prompt_version(
                                distill_template_metadata
                            ),
                            "schema_version": distill_template_metadata.get(
                                "template_version"
                            ),
                            "response_format": "json",
                        },
                    )
                )
                llm_gateway_calls.append(
                    _summarize_llm_gateway_result(gateway_result, chunk_index=idx)
                )

                json_text = gateway_result.text or _repair_json(gateway_result.text)
                parsed = _json.loads(json_text)

                # LLM 可能返回 dict 或 list
                if isinstance(parsed, dict):
                    chunk_ents = parsed.get("entities", [])
                    chunk_rels = parsed.get("relations", [])
                elif isinstance(parsed, list):
                    chunk_ents, chunk_rels = [], []
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        if "source" in item and "target" in item:
                            chunk_rels.append(item)
                        elif "name" in item:
                            chunk_ents.append(item)
                else:
                    chunk_ents, chunk_rels = [], []

                # 验证并清洗实体
                for ent in chunk_ents:
                    if not isinstance(ent, dict):
                        continue
                    name = ent.get("name", "")
                    if isinstance(name, list):
                        name = name[0] if name else ""
                    name = str(name).strip()
                    if _validate_entity_name(name):
                        llm_entities.append(
                            {"name": name, "type": ent.get("type", "generic")}
                        )

                # 验证并清洗关系
                for rel in chunk_rels:
                    if not isinstance(rel, dict):
                        continue
                    src = rel.get("source", "")
                    tgt = rel.get("target", "")
                    if isinstance(src, list):
                        src = src[0] if src else ""
                    if isinstance(tgt, list):
                        tgt = tgt[0] if tgt else ""
                    src = str(src).strip()
                    tgt = str(tgt).strip()
                    if _validate_entity_name(src) and _validate_entity_name(tgt):
                        rel_type = _normalize_relation(rel.get("relation", "related"))
                        llm_relations.append(
                            {"source": src, "relation": rel_type, "target": tgt}
                        )

            except (_json.JSONDecodeError, Exception) as chunk_err:
                logger.warning(
                    "LLM 蒸馏第 %d/%d 片段解析失败: %s", idx + 1, len(chunks), chunk_err
                )

        # 恢复 max_tokens
        if _saved_max_tokens is not None:
            try:
                llm.max_tokens = _saved_max_tokens
            except Exception:
                pass

        # 同时也走规则管线进行基础抽取
        preprocessor = _get_preprocessor()
        preprocess_ctx: Dict[str, Any] = {"raw_text": body.raw_text}
        if body.source_file:
            preprocess_ctx["source_file"] = body.source_file
        preprocess_result = preprocessor.execute(preprocess_ctx)

        extractor = _get_extractor()
        extraction_result = extractor.execute(preprocess_result)
        rule_entities = extraction_result.get("entities", [])

        graph_builder = _get_graph_builder()
        semantic_input = {
            **extraction_result,
            "processed_text": preprocess_result.get("processed_text") or body.raw_text,
            "raw_text": body.raw_text,
        }
        semantic_result = graph_builder.execute(semantic_input)
        rule_graph = semantic_result.get("semantic_graph", {})

        # 合并 LLM 实体（去重）
        seen_names = {(e.get("name") or e.get("text", "")) for e in rule_entities}
        merged_entities = list(rule_entities)
        for ent in llm_entities:
            name = ent.get("name", "")
            if isinstance(name, list):
                name = name[0] if name else ""
            elif not isinstance(name, str):
                name = str(name)
            if name and name not in seen_names:
                merged_entities.append(
                    {
                        "name": name,
                        "type": ent.get("type", "generic"),
                        "source": "llm_distill",
                    }
                )
                seen_names.add(name)

        # 合并 LLM 关系
        rule_edges = rule_graph.get("edges", [])
        rule_tier_counts = rule_quality_tier_counts(rule_edges)
        seen_edges = {(e.get("source", ""), e.get("target", "")) for e in rule_edges}
        merged_edges = list(rule_edges)
        for rel in llm_relations:
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            if isinstance(src, list):
                src = src[0] if src else ""
            elif not isinstance(src, str):
                src = str(src)
            if isinstance(tgt, list):
                tgt = tgt[0] if tgt else ""
            elif not isinstance(tgt, str):
                tgt = str(tgt)

            key = (src, tgt)
            if key[0] and key[1] and key not in seen_edges:
                merged_edges.append(
                    {
                        "source": src,
                        "target": tgt,
                        "relation": rel.get("relation", "related"),
                        "source_method": "llm_distill",
                    }
                )
                seen_edges.add(key)

        merged_graph = {**rule_graph, "edges": merged_edges}
        merged_entities, merged_graph, research_view = (
            _build_unsupervised_research_assets(
                body.raw_text,
                body.source_file,
                merged_entities,
                merged_graph,
            )
        )
        merged_entities = attach_provenance_to_entities(
            merged_entities, provenance_index
        )
        merged_graph = {
            **merged_graph,
            "edges": attach_provenance_to_edges(
                merged_graph.get("edges", []), provenance_index
            ),
        }
        research_view = attach_provenance_to_research_view(
            research_view, provenance_index
        )
        logger.info(
            "distill rule relation tiers: strong=%d weak=%d candidate=%d rejected=%d",
            rule_tier_counts.get("strong_rule", 0),
            rule_tier_counts.get("weak_rule", 0),
            rule_tier_counts.get("candidate_rule", 0),
            rule_tier_counts.get("rejected_rule", 0),
        )

        # 持久化到知识图谱
        persisted = _persist_to_kg(merged_entities, merged_graph)

        # 写入主应用数据库 (ORM)
        persist_metadata = (
            dict(body.metadata or {}) if isinstance(body.metadata, Mapping) else {}
        )
        if distill_template_metadata:
            persist_metadata["llm_reasoning_template"] = distill_template_metadata
        llm_gateway_summary = _summarize_llm_gateway_calls(llm_gateway_calls)
        persist_metadata["llm_gateway"] = {
            "summary": llm_gateway_summary,
            "calls": llm_gateway_calls,
        }
        orm_result = _persist_to_orm(
            request,
            merged_entities,
            merged_graph,
            source_file=body.source_file,
            created_by="llm_distill",
            raw_text=body.raw_text,
            metadata=persist_metadata,
            semantic_result=semantic_result,
            research_view=research_view,
        )

        kg = _get_kg()
        return {
            "message": "LLM 知识蒸馏完成",
            "llm_extracted": {
                "entities": len(llm_entities),
                "relations": len(llm_relations),
                "template": distill_template_metadata,
                "llm_gateway": {
                    "summary": llm_gateway_summary,
                    "calls": llm_gateway_calls,
                },
            },
            "llm_reasoning_template": distill_template_metadata,
            "llm_gateway": {
                "summary": llm_gateway_summary,
                "calls": llm_gateway_calls,
            },
            "rule_extracted": {
                "entities": len(rule_entities),
                "relations": len(rule_edges),
                "quality_tiers": rule_tier_counts,
            },
            "merged": {
                "entities": len(merged_entities),
                "relations": len(merged_graph.get("edges", [])),
            },
            "knowledge_accumulation": {
                "new_entities": persisted["new_entities"],
                "new_relations": persisted["new_relations"],
                "total_entities": kg.entity_count,
                "total_relations": kg.relation_count,
                "orm_entities": orm_result["orm_entities"],
                "orm_relations": orm_result["orm_relations"],
                "orm_statistics": orm_result["orm_statistics"],
                "orm_analyses": orm_result["orm_analyses"],
                "neo4j_nodes": orm_result["neo4j_nodes"],
                "neo4j_edges": orm_result["neo4j_edges"],
                "candidate_relations": orm_result.get("candidate_relations", 0),
            },
            "entities": {"items": merged_entities},
            "semantic_graph": {
                "graph": {
                    "nodes": merged_graph.get("nodes", []),
                    "edges": merged_graph.get("edges", []),
                },
            },
            "research_enhancement": _build_research_response_summary(research_view),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("LLM 知识蒸馏失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM 知识蒸馏失败: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# KG 累积查询接口
# ---------------------------------------------------------------------------


def _get_graph_schema_info() -> Dict[str, Any]:
    """返回 graph_schema 版本与 drift 信息（不依赖 Neo4j 连接）。"""
    try:
        from src.storage.graph_schema import GRAPH_SCHEMA_VERSION, get_schema_summary

        summary = get_schema_summary()
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "schema_node_label_count": summary["node_label_count"],
            "schema_rel_type_count": summary["rel_type_count"],
        }
    except Exception:
        return {}


@router.get("/kg/stats")
def kg_stats(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """查询知识图谱累积统计（KG 图 + ORM 主库）。"""
    kg = _get_kg()
    graph = kg._graph

    type_counts: Dict[str, int] = {}
    for _, data in graph.nodes(data=True):
        t = data.get("type", "generic")
        type_counts[t] = type_counts.get(t, 0) + 1

    rel_type_counts: Dict[str, int] = {}
    for _, _, data in graph.edges(data=True):
        rt = data.get("rel_type", "unknown")
        rel_type_counts[rt] = rel_type_counts.get(rt, 0) + 1

    # ------ ORM 主库统计 ------
    orm_stats: Dict[str, Any] = {
        "orm_entities": 0,
        "orm_relations": 0,
        "orm_documents": 0,
        "orm_entity_types": {},
    }
    db_mgr = getattr(getattr(request, "app", None), "state", None)
    db_mgr = getattr(db_mgr, "db_manager", None) if db_mgr else None
    if db_mgr is not None:
        try:
            from sqlalchemy import func as sa_func

            from src.infrastructure.persistence import (
                Document,
                Entity,
                EntityRelationship,
            )

            with db_mgr.session_scope() as sess:
                orm_stats["orm_entities"] = (
                    sess.query(sa_func.count(Entity.id)).scalar() or 0
                )
                orm_stats["orm_relations"] = (
                    sess.query(sa_func.count(EntityRelationship.id)).scalar() or 0
                )
                orm_stats["orm_documents"] = (
                    sess.query(sa_func.count(Document.id)).scalar() or 0
                )
                rows = (
                    sess.query(Entity.type, sa_func.count(Entity.id))
                    .group_by(Entity.type)
                    .all()
                )
                orm_stats["orm_entity_types"] = {
                    str(r[0].value if hasattr(r[0], "value") else r[0]): r[1]
                    for r in rows
                }
        except Exception as exc:
            logger.warning("ORM 统计查询失败: %s", exc)

    return {
        "total_entities": kg.entity_count,
        "total_relations": kg.relation_count,
        "entity_types": type_counts,
        "relation_types": rel_type_counts,
        **orm_stats,
        **_get_graph_schema_info(),
    }


# 图谱类型 → 过滤条件映射
_GRAPH_TYPE_FILTERS: Dict[str, Dict[str, Any]] = {
    "herb_relations": {
        "node_types": {"herb", "efficacy", "中药", "功效", "药性"},
        "rel_types": {
            "efficacy",
            "synergy",
            "antagonism",
            "related",
            "配伍",
            "功效",
            "归经",
            "性味",
        },
        "label": "药物关系图",
    },
    "formula_composition": {
        "node_types": {"formula", "herb", "方剂", "中药"},
        "rel_types": {
            "sovereign",
            "minister",
            "assistant",
            "envoy",
            "contains",
            "组成",
            "君",
            "臣",
            "佐",
            "使",
        },
        "label": "方剂组成图",
    },
    "syndrome_treatment": {
        "node_types": {
            "syndrome",
            "formula",
            "symptom",
            "method",
            "证候",
            "方剂",
            "症状",
            "治法",
        },
        "rel_types": {
            "treats",
            "indicates",
            "associated_target",
            "主治",
            "适应",
            "治疗",
        },
        "label": "证治关系图",
    },
    "literature_citation": {
        "node_types": None,  # 所有类型
        "rel_types": {"cites", "references", "cited_in", "引用", "出处"},
        "label": "文献引用图",
    },
}


@router.get("/kg/subgraph")
def kg_subgraph(
    graph_type: str = Query(
        ...,
        description="图谱类型: herb_relations | formula_composition | syndrome_treatment | literature_citation",
    ),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """按图谱类型获取过滤后的子图数据，用于前端分类可视化。"""
    filt = _GRAPH_TYPE_FILTERS.get(graph_type)
    if filt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的图谱类型: {graph_type}，可选: {list(_GRAPH_TYPE_FILTERS.keys())}",
        )

    kg = _get_kg()
    graph = kg._graph
    allowed_node_types = filt["node_types"]
    allowed_rel_types = filt["rel_types"]

    # 筛选节点
    nodes = []
    node_ids = set()
    for n, data in graph.nodes(data=True):
        ntype = data.get("type", "generic")
        if allowed_node_types is None or ntype in allowed_node_types:
            nodes.append({"id": n, "name": n, "type": ntype})
            node_ids.add(n)

    # 筛选边（两端均需在筛选后的节点集中）
    edges = []
    for u, v, data in graph.edges(data=True):
        rt = data.get("rel_type", "unknown")
        if u in node_ids and v in node_ids:
            if allowed_rel_types is None or rt in allowed_rel_types:
                edges.append(
                    {
                        "source": u,
                        "target": v,
                        "relation": rt,
                    }
                )

    # 若 literature_citation 类型但无专有文献边，回退显示全图
    if graph_type == "literature_citation" and not edges:
        nodes = [
            {"id": n, "name": n, "type": d.get("type", "generic")}
            for n, d in graph.nodes(data=True)
        ]
        edges = [
            {"source": u, "target": v, "relation": d.get("rel_type", "unknown")}
            for u, v, d in graph.edges(data=True)
        ]

    total_nodes = len(nodes)
    total_edges = len(edges)

    # 优先保留与边相连的节点；若存在边，仅渲染连通节点以避免大量孤儿点污染画布
    NODE_CAP = 500
    EDGE_CAP = 1000
    edges_capped = edges[:EDGE_CAP]
    connected_ids = set()
    for e in edges_capped:
        connected_ids.add(e["source"])
        connected_ids.add(e["target"])
    connected_nodes = [n for n in nodes if n["id"] in connected_ids]
    isolated_nodes = [n for n in nodes if n["id"] not in connected_ids]
    if edges_capped:
        nodes_out = connected_nodes[:NODE_CAP]
    else:
        # 无边：仅展示少量孤立节点作为概览
        nodes_out = isolated_nodes[: min(NODE_CAP, 80)]

    return {
        "graph_type": graph_type,
        "label": filt["label"],
        "nodes": nodes_out,
        "edges": edges_capped,
        "statistics": {
            "nodes_count": total_nodes,
            "edges_count": total_edges,
            "rendered_nodes": len(nodes_out),
            "rendered_edges": len(edges_capped),
            "connected_nodes": len(connected_nodes),
            "isolated_nodes_total": len(isolated_nodes),
        },
    }


@router.get("/graph/{research_id}")
def get_knowledge_graph(
    research_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取知识图谱数据（JSON 格式，供前端可视化）。"""
    try:
        cycle = get_research_session(request.app, research_id)
        if cycle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到研究课题: {research_id}",
            )
        graph_data = get_research_observe_graph(request.app, research_id) or {
            "nodes": [],
            "edges": [],
            "statistics": {},
        }

        return {
            "research_id": research_id,
            "graph": graph_data,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("获取知识图谱失败: %s", research_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取知识图谱失败: {exc}",
        ) from exc
