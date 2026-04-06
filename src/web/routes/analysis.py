# -*- coding: utf-8 -*-
"""分析路由 — 方剂分析、文本处理链、知识图谱数据。"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from src.web.auth import get_current_user

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


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_preprocessor = None
_extractor = None
_graph_builder = None
_kg_instance = None

_KG_DB_PATH = Path("data") / "knowledge_graph.db"


def _get_kg():
    """获取全局 TCMKnowledgeGraph 实例（SQLite 持久化）。"""
    global _kg_instance  # noqa: PLW0603
    if _kg_instance is None:
        from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph
        _kg_instance = TCMKnowledgeGraph(
            db_path=_KG_DB_PATH, preload_formulas=True,
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/formula")
async def analyze_formula(
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
async def analyze_text(
    request: Request,
    body: TextAnalysisRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """文本处理链 — 预处理 → 实体抽取 → 语义建模 → 知识沉淀。"""
    try:
        # 1) 预处理
        preprocessor = _get_preprocessor()
        preprocess_ctx: Dict[str, Any] = {"raw_text": body.raw_text}
        if body.source_file:
            preprocess_ctx["source_file"] = body.source_file
        if body.metadata:
            preprocess_ctx["metadata"] = body.metadata
        preprocess_result = preprocessor.execute(preprocess_ctx)

        # 2) 实体抽取
        extractor = _get_extractor()
        extraction_result = extractor.execute(preprocess_result)

        # 3) 语义建模
        graph_builder = _get_graph_builder()
        semantic_result = graph_builder.execute(extraction_result)

        # 4) 知识沉淀 — 将实体和关系持久化到本地 KG 数据库
        entities = extraction_result.get("entities", [])
        graph_data = semantic_result.get("semantic_graph", {})
        persisted = _persist_to_kg(entities, graph_data)

        # 5) 写入主应用数据库 (ORM)
        orm_result = _persist_to_orm(
            request, entities, graph_data,
            source_file=body.source_file,
            created_by="text_analysis",
        )

        kg = _get_kg()
        return {
            "message": "文本分析完成",
            "preprocessing": {
                "processed_text": preprocess_result.get("processed_text", ""),
                "processing_steps": preprocess_result.get("processing_steps", []),
            },
            "entities": {
                "items": entities,
                "statistics": extraction_result.get("statistics", {}),
            },
            "semantic_graph": {
                "graph": graph_data,
                "statistics": semantic_result.get("graph_statistics", {}),
            },
            "knowledge_accumulation": {
                "new_entities": persisted["new_entities"],
                "new_relations": persisted["new_relations"],
                "total_entities": kg.entity_count,
                "total_relations": kg.relation_count,
                "orm_entities": orm_result["orm_entities"],
                "orm_relations": orm_result["orm_relations"],
            },
        }
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
        meta = {k: v for k, v in ent.items() if k not in ("name", "type", "entity_type")}
        ent_rows.append({"name": name, "type": etype, **meta})
    if ent_rows:
        kg.bulk_add_entities(ent_rows)

    # 关系
    edges = graph_data.get("edges", [])
    rel_rows = []
    for e in edges:
        src = e.get("source") or e.get("from", "")
        dst = e.get("target") or e.get("to", "")
        rel = e.get("relation") or e.get("rel_type") or e.get("label") or "related"
        if src and dst:
            meta = {k: v for k, v in e.items()
                    if k not in ("source", "target", "from", "to", "relation", "rel_type", "label")}
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
    "herb": "herb", "formula": "formula", "syndrome": "syndrome",
    "efficacy": "efficacy", "property": "property", "taste": "taste",
    "meridian": "meridian", "symptom": "other", "theory": "other",
    "generic": "other",
}

# 关系名 → ORM RelationshipType.relationship_type 映射
_REL_TYPE_MAP = {
    "君": "SOVEREIGN", "臣": "MINISTER", "佐": "ASSISTANT", "使": "ENVOY",
    "治疗": "TREATS", "treats": "TREATS",
    "功效": "HAS_EFFICACY", "has_efficacy": "HAS_EFFICACY", "efficacy": "HAS_EFFICACY",
    "类似": "SIMILAR_TO", "similar_to": "SIMILAR_TO",
    "包含": "CONTAINS", "contains": "CONTAINS", "composition": "CONTAINS",
    "related": "CONTAINS",
}


def _persist_to_orm(
    request: Request,
    entities: List[Dict[str, Any]],
    graph_data: Dict[str, Any],
    source_file: Optional[str] = None,
    created_by: str = "text_analysis",
) -> Dict[str, int]:
    """将抽取结果写入主应用数据库 (ORM 表)。

    返回 {"orm_entities": N, "orm_relations": N}。
    """
    db_mgr = getattr(getattr(request, "app", None), "state", None)
    db_mgr = getattr(db_mgr, "db_manager", None) if db_mgr else None
    if db_mgr is None:
        logger.debug("DatabaseManager 未就绪，跳过 ORM 持久化")
        return {"orm_entities": 0, "orm_relations": 0}

    from src.infrastructure.persistence import (
        Document,
        Entity,
        EntityRelationship,
        EntityTypeEnum,
        ProcessStatusEnum,
        RelationshipType,
    )

    orm_ent_count = 0
    orm_rel_count = 0

    try:
        with db_mgr.session_scope() as session:
            # 1) 创建 Document 记录（source_file 需唯一）
            import time as _time
            import uuid as _uuid
            uid = _uuid.uuid4().hex[:8]
            ts = _time.strftime('%Y%m%d_%H%M%S')
            sf = f"{source_file or created_by}_{ts}_{uid}"
            doc = Document(
                source_file=sf,
                raw_text_size=sum(len(e.get("name", "")) for e in entities),
                entities_extracted_count=len(entities),
                process_status=ProcessStatusEnum.COMPLETED,
                notes=f"由 {created_by} 自动写入",
            )
            session.add(doc)
            session.flush()  # 获取 doc.id

            # 2) 预加载 RelationshipType 映射
            rel_types = {
                rt.relationship_type: rt
                for rt in session.query(RelationshipType).all()
            }

            # 3) 写入实体，同时建 name → Entity 映射
            name_to_entity: Dict[str, Entity] = {}
            for ent in entities:
                name = ent.get("name") or ent.get("text") or ent.get("value", "")
                if not name or name in name_to_entity:
                    continue
                raw_type = (ent.get("type") or ent.get("entity_type") or "generic").lower()
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
                    entity_metadata={k: v for k, v in ent.items()
                                     if k not in ("name", "type", "entity_type", "confidence")},
                )
                session.add(entity_obj)
                name_to_entity[name] = entity_obj
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
                # 若目标实体不在本批实体中，自动补录
                if dst_ent is None and dst_name:
                    plain_dst = dst_name.split(":", 1)[-1] if ":" in dst_name else dst_name
                    prefix_type = dst_name.split(":", 1)[0] if ":" in dst_name else "other"
                    mapped = _TYPE_MAP.get(prefix_type, "other")
                    try:
                        etype = EntityTypeEnum(mapped)
                    except ValueError:
                        etype = EntityTypeEnum.OTHER
                    dst_ent = Entity(
                        document_id=doc.id, name=plain_dst,
                        type=etype, confidence=0.4,
                    )
                    session.add(dst_ent)
                    session.flush()
                    name_to_entity[plain_dst] = dst_ent
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
                rel_obj = EntityRelationship(
                    source_entity_id=src_ent.id,
                    target_entity_id=dst_ent.id,
                    relationship_type_id=rt_obj.id,
                    confidence=edge_confidence,
                    created_by_module=created_by,
                    evidence=e.get("evidence") or attrs.get("description"),
                    relationship_metadata={k: v for k, v in e.items()
                                           if k not in ("source", "target", "from", "to",
                                                        "relation", "rel_type", "label",
                                                        "confidence", "evidence", "attributes")},
                )
                session.add(rel_obj)
                orm_rel_count += 1
            # session_scope 自动 commit
    except Exception:
        logger.exception("ORM 持久化失败（不影响 KG 侧已写入的数据）")

    return {"orm_entities": orm_ent_count, "orm_relations": orm_rel_count}


# ---------------------------------------------------------------------------
# LLM 知识蒸馏
# ---------------------------------------------------------------------------

_LLM_DISTILL_PROMPT = """\
从下文提取中医知识三元组，输出JSON：
{{"entities":[{{"name":"…","type":"herb|formula|syndrome|symptom|efficacy"}}],"relations":[{{"source":"…","relation":"…","target":"…"}}]}}
文本：{text}
仅输出JSON。"""

# 中文约 2 token/字；4096 上下文 - 1024 生成 - ~200 prompt ≈ 1400 字
_DISTILL_TEXT_LIMIT = 1400


@router.post("/distill")
async def llm_distill(
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
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="本地 LLM 引擎未加载，无法进行知识蒸馏",
            )

        # 分片蒸馏 — 长文本按 _DISTILL_TEXT_LIMIT 切片逐段调用 LLM
        full_text = body.raw_text
        chunks = [
            full_text[i:i + _DISTILL_TEXT_LIMIT]
            for i in range(0, len(full_text), _DISTILL_TEXT_LIMIT)
        ]
        llm_entities: List[Dict[str, Any]] = []
        llm_relations: List[Dict[str, Any]] = []

        for idx, chunk in enumerate(chunks):
            try:
                prompt = _LLM_DISTILL_PROMPT.format(text=chunk)
                raw_output = llm.generate(
                    prompt,
                    system_prompt="中医知识图谱专家，仅输出JSON。",
                )

                json_text = raw_output.strip()
                if "```json" in json_text:
                    json_text = json_text.split("```json", 1)[1]
                    json_text = json_text.split("```", 1)[0]
                elif "```" in json_text:
                    json_text = json_text.split("```", 1)[1]
                    json_text = json_text.split("```", 1)[0]

                parsed = _json.loads(json_text.strip())
                # LLM 可能返回 dict 或 list
                if isinstance(parsed, dict):
                    llm_entities.extend(parsed.get("entities", []))
                    llm_relations.extend(parsed.get("relations", []))
                elif isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        if "source" in item and "target" in item:
                            llm_relations.append(item)
                        elif "name" in item or "type" in item:
                            llm_entities.append(item)
            except (_json.JSONDecodeError, Exception) as chunk_err:
                logger.warning("LLM 蒸馏第 %d/%d 片段解析失败: %s", idx + 1, len(chunks), chunk_err)

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
        semantic_result = graph_builder.execute(extraction_result)
        rule_graph = semantic_result.get("semantic_graph", {})

        # 合并 LLM 实体（去重）
        seen_names = {(e.get("name") or e.get("text", "")) for e in rule_entities}
        merged_entities = list(rule_entities)
        for ent in llm_entities:
            name = ent.get("name", "")
            if name and name not in seen_names:
                merged_entities.append({
                    "name": name,
                    "type": ent.get("type", "generic"),
                    "source": "llm_distill",
                })
                seen_names.add(name)

        # 合并 LLM 关系
        rule_edges = rule_graph.get("edges", [])
        seen_edges = {
            (e.get("source", ""), e.get("target", ""))
            for e in rule_edges
        }
        merged_edges = list(rule_edges)
        for rel in llm_relations:
            key = (rel.get("source", ""), rel.get("target", ""))
            if key[0] and key[1] and key not in seen_edges:
                merged_edges.append({
                    "source": rel["source"],
                    "target": rel["target"],
                    "relation": rel.get("relation", "related"),
                    "source_method": "llm_distill",
                })
                seen_edges.add(key)

        merged_graph = {**rule_graph, "edges": merged_edges}

        # 持久化到知识图谱
        persisted = _persist_to_kg(merged_entities, merged_graph)

        # 写入主应用数据库 (ORM)
        orm_result = _persist_to_orm(
            request, merged_entities, merged_graph,
            source_file=body.source_file,
            created_by="llm_distill",
        )

        kg = _get_kg()
        return {
            "message": "LLM 知识蒸馏完成",
            "llm_extracted": {
                "entities": len(llm_entities),
                "relations": len(llm_relations),
            },
            "rule_extracted": {
                "entities": len(rule_entities),
                "relations": len(rule_edges),
            },
            "merged": {
                "entities": len(merged_entities),
                "relations": len(merged_edges),
            },
            "knowledge_accumulation": {
                "new_entities": persisted["new_entities"],
                "new_relations": persisted["new_relations"],
                "total_entities": kg.entity_count,
                "total_relations": kg.relation_count,
                "orm_entities": orm_result["orm_entities"],
                "orm_relations": orm_result["orm_relations"],
            },
            "entities": {"items": merged_entities},
            "semantic_graph": {
                "graph": {"nodes": merged_graph.get("nodes", []), "edges": merged_edges},
            },
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


@router.get("/kg/stats")
async def kg_stats(
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
                orm_stats["orm_entities"] = sess.query(sa_func.count(Entity.id)).scalar() or 0
                orm_stats["orm_relations"] = sess.query(sa_func.count(EntityRelationship.id)).scalar() or 0
                orm_stats["orm_documents"] = sess.query(sa_func.count(Document.id)).scalar() or 0
                rows = sess.query(Entity.type, sa_func.count(Entity.id)).group_by(Entity.type).all()
                orm_stats["orm_entity_types"] = {str(r[0].value if hasattr(r[0], 'value') else r[0]): r[1] for r in rows}
        except Exception as exc:
            logger.warning("ORM 统计查询失败: %s", exc)

    return {
        "total_entities": kg.entity_count,
        "total_relations": kg.relation_count,
        "entity_types": type_counts,
        "relation_types": rel_type_counts,
        **orm_stats,
    }


# 图谱类型 → 过滤条件映射
_GRAPH_TYPE_FILTERS: Dict[str, Dict[str, Any]] = {
    "herb_relations": {
        "node_types": {"herb", "efficacy", "中药", "功效", "药性"},
        "rel_types": {"efficacy", "synergy", "antagonism", "related",
                      "配伍", "功效", "归经", "性味"},
        "label": "药物关系图",
    },
    "formula_composition": {
        "node_types": {"formula", "herb", "方剂", "中药"},
        "rel_types": {"sovereign", "minister", "assistant", "envoy",
                      "contains", "组成", "君", "臣", "佐", "使"},
        "label": "方剂组成图",
    },
    "syndrome_treatment": {
        "node_types": {"syndrome", "formula", "symptom", "method",
                       "证候", "方剂", "症状", "治法"},
        "rel_types": {"treats", "indicates", "associated_target",
                      "主治", "适应", "治疗"},
        "label": "证治关系图",
    },
    "literature_citation": {
        "node_types": None,  # 所有类型
        "rel_types": {"cites", "references", "cited_in", "引用", "出处"},
        "label": "文献引用图",
    },
}


@router.get("/kg/subgraph")
async def kg_subgraph(
    graph_type: str = Query(
        ..., description="图谱类型: herb_relations | formula_composition | syndrome_treatment | literature_citation"
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
                edges.append({
                    "source": u, "target": v,
                    "relation": rt,
                })

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

    return {
        "graph_type": graph_type,
        "label": filt["label"],
        "nodes": nodes[:500],
        "edges": edges[:1000],
        "statistics": {
            "nodes_count": len(nodes),
            "edges_count": len(edges),
        },
    }


@router.get("/graph/{research_id}")
async def get_knowledge_graph(
    research_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """获取知识图谱数据（JSON 格式，供前端可视化）。"""
    try:
        from src.research.research_pipeline import ResearchPipeline

        pipeline = ResearchPipeline()
        cycles = getattr(pipeline, "research_cycles", None)
        if cycles is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="研究编排器未初始化",
            )

        cycle = cycles.get(research_id)
        if cycle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到研究课题: {research_id}",
            )

        # 从阶段执行结果中提取图谱数据
        from src.research.study_session_manager import ResearchPhase

        phase_data = {}
        if hasattr(cycle, "phase_executions"):
            phase_data = cycle.phase_executions or {}

        graph_data: Dict[str, Any] = {"nodes": [], "edges": [], "statistics": {}}

        # 尝试从 OBSERVE 阶段获取语义图谱
        observe_result = phase_data.get(ResearchPhase.OBSERVE, phase_data.get("observe", {}))
        if isinstance(observe_result, dict):
            graph_data["nodes"] = observe_result.get("semantic_graph", {}).get("nodes", [])
            graph_data["edges"] = observe_result.get("semantic_graph", {}).get("edges", [])
            graph_data["statistics"] = observe_result.get("graph_statistics", {})

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
