"""论文插件双库持久化（PostgreSQL + Neo4j）。

已收口到 StorageBackendFactory + TransactionCoordinator 主链，
保证 PG + Neo4j 原子性与一致性观测。
"""

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _build_paper_config(
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """构造 StorageBackendFactory 所需的 pipeline_config。"""
    return {
        "database": {
            "url": pg_url,
        },
        "neo4j": {
            "enabled": bool(neo4j_uri and neo4j_password),
            "uri": neo4j_uri,
            "user": neo4j_user,
            "password": neo4j_password,
        },
    }


def persist_paper_result_to_dual_storage(
    source_path: str,
    result_payload: Dict[str, Any],
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, str]:
    """将论文插件输出写入 PostgreSQL + Neo4j。

    通过 StorageBackendFactory + TransactionCoordinator 保证
    PG + Neo4j 原子性，失败时自动补偿。
    """
    from src.infrastructure.persistence import (
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
        RelationshipType,
        ResearchAnalysis,
    )
    from src.storage.backend_factory import StorageBackendFactory
    from src.storage.neo4j_driver import (
        Neo4jEdge,
        _safe_cypher_label,
        entity_to_neo4j_node,
    )

    factory = None
    doc_id = None
    try:
        if not neo4j_password:
            return {
                "status": "failed",
                "document_id": "",
                "error": "NEO4J_PASSWORD 未提供，无法完成双库存档",
            }
        if "://@" in pg_url:
            return {
                "status": "failed",
                "document_id": "",
                "error": "PostgreSQL 连接字符串缺少密码",
            }

        config = _build_paper_config(pg_url, neo4j_uri, neo4j_user, neo4j_password)
        factory = StorageBackendFactory(config)
        factory.initialize()

        source_name = Path(source_path).name

        with factory.transaction() as txn:
            pg = txn.pg_session

            # 1. 保存文档
            doc = Document(
                source_file=source_path,
                objective="paper_plugin_archive",
                raw_text_size=int(result_payload.get("char_count", 0)),
                process_status=ProcessStatusEnum.PENDING,
            )
            pg.add(doc)
            pg.flush()
            doc_id = doc.id

            # 2. 创建实体
            entity_defs = [
                {
                    "name": source_name,
                    "type": "OTHER",
                    "confidence": 0.99,
                    "position": 0,
                    "length": len(source_name),
                    "description": "论文来源文件",
                    "metadata": {
                        "source_type": result_payload.get("source_type", "unknown"),
                        "source_path": source_path,
                    },
                },
                {
                    "name": "论文摘要",
                    "type": "OTHER",
                    "confidence": 0.95,
                    "position": 0,
                    "length": len(result_payload.get("summary", "")),
                    "description": result_payload.get("summary", ""),
                    "metadata": {
                        "summary_lang": "中文",
                        "generated_by": "paper_plugin",
                    },
                },
                {
                    "name": "翻译节选",
                    "type": "OTHER",
                    "confidence": 0.90,
                    "position": 0,
                    "length": len(result_payload.get("translation_excerpt", "")),
                    "description": result_payload.get("translation_excerpt", ""),
                    "metadata": {
                        "translated": bool(result_payload.get("translated", False)),
                        "generated_by": "paper_plugin",
                    },
                },
            ]
            entity_ids = []
            for edef in entity_defs:
                entity = Entity(
                    document_id=doc_id,
                    name=edef["name"],
                    type=EntityTypeEnum[edef["type"]],
                    confidence=edef["confidence"],
                    position=edef["position"],
                    length=edef["length"],
                    alternative_names=[],
                    description=edef["description"],
                    entity_metadata=edef["metadata"],
                )
                pg.add(entity)
                pg.flush()
                entity_ids.append(entity.id)

                # Neo4j 节点（延迟执行，commit 时原子提交）
                neo4j_node = entity_to_neo4j_node(entity)
                safe_label = _safe_cypher_label(neo4j_node.label)
                props = dict(neo4j_node.properties or {})
                props["id"] = neo4j_node.id
                txn.neo4j_write(
                    f"MERGE (n:{safe_label} {{id: $id}}) SET n += $props",
                    compensate_cypher=f"MATCH (n:{safe_label} {{id: $id}}) DETACH DELETE n",
                    id=neo4j_node.id,
                    props=props,
                )

            if len(entity_ids) < 3:
                raise RuntimeError("保存实体失败：实体数不足")

            # 3. 创建关系
            rel_types = pg.query(RelationshipType).all()
            rel_type_map = {rt.relationship_type: rt.id for rt in rel_types}

            rel_defs = [
                {
                    "source_idx": 0,
                    "target_idx": 1,
                    "rel_type": "CONTAINS",
                    "confidence": 0.95,
                    "evidence": "论文包含摘要内容",
                    "metadata": {"semantic_role": "summary"},
                },
                {
                    "source_idx": 0,
                    "target_idx": 2,
                    "rel_type": "CONTAINS",
                    "confidence": 0.90,
                    "evidence": "论文包含翻译节选内容",
                    "metadata": {"semantic_role": "translation_excerpt"},
                },
            ]
            rel_ids = []
            for rdef in rel_defs:
                rel_type_id = rel_type_map.get(rdef["rel_type"])
                if not rel_type_id:
                    logger.warning("未找到关系类型: %s", rdef["rel_type"])
                    continue
                rel = EntityRelationship(
                    source_entity_id=entity_ids[rdef["source_idx"]],
                    target_entity_id=entity_ids[rdef["target_idx"]],
                    relationship_type_id=rel_type_id,
                    confidence=rdef["confidence"],
                    created_by_module="paper_plugin",
                    evidence=rdef["evidence"],
                    relationship_metadata=rdef["metadata"],
                )
                pg.add(rel)
                pg.flush()
                rel_ids.append(rel.id)

                # Neo4j 关系（延迟执行）
                safe_rel = _safe_cypher_label(rdef["rel_type"])
                src_id = str(entity_ids[rdef["source_idx"]])
                tgt_id = str(entity_ids[rdef["target_idx"]])
                txn.neo4j_write(
                    f"MATCH (a {{id: $src_id}}) MATCH (b {{id: $tgt_id}}) "
                    f"MERGE (a)-[r:{safe_rel}]->(b) SET r += $props",
                    compensate_cypher=(
                        f"MATCH (a {{id: $src_id}})-[r:{safe_rel}]->"
                        f"(b {{id: $tgt_id}}) DELETE r"
                    ),
                    src_id=src_id,
                    tgt_id=tgt_id,
                    props={
                        "confidence": rdef["confidence"],
                        "created_by_module": "paper_plugin",
                        "evidence": rdef["evidence"],
                    },
                )

            # 4. 统计
            stats = ProcessingStatistics(
                document_id=doc_id,
                formulas_count=0,
                herbs_count=0,
                syndromes_count=0,
                efficacies_count=0,
                relationships_count=len(rel_ids),
                graph_nodes_count=len(entity_ids),
                graph_edges_count=len(rel_ids),
                graph_density=0.0,
                connected_components=1,
                source_modules=["paper_plugin"],
                processing_time_ms=0,
            )
            pg.add(stats)

            # 5. 研究分析
            analysis = ResearchAnalysis(
                document_id=doc_id,
                research_perspectives={},
                formula_comparisons={},
                herb_properties_analysis={},
                pharmacology_integration={},
                network_pharmacology={},
                supramolecular_physicochemistry={},
                knowledge_archaeology={},
                complexity_dynamics={},
                research_scoring_panel={},
                summary_analysis={
                    "paper_summary": result_payload.get("summary", ""),
                    "translation_excerpt": result_payload.get("translation_excerpt", ""),
                    "paper_source_type": result_payload.get("source_type", "unknown"),
                    "paper_output_json": result_payload.get("output_json", ""),
                    "paper_output_markdown": result_payload.get("output_markdown", ""),
                },
            )
            pg.add(analysis)

            # 6. 执行日志
            log = ProcessingLog(
                document_id=doc_id,
                module_name="paper_plugin",
                status=LogStatusEnum("success"),
                message="论文插件结果已完成双库存档",
            )
            pg.add(log)

            # 7. 更新文档状态
            doc.process_status = ProcessStatusEnum("completed")

        # txn auto-commit 保证 PG + Neo4j 原子性
        logger.info("论文插件结果已持久化: %s (doc_id=%s)", source_path, doc_id)
        return {
            "status": "completed",
            "document_id": str(doc_id),
            "error": "",
        }
    except Exception as exc:
        logger.error("论文插件双库存档失败: %s", exc)
        return {
            "status": "failed",
            "document_id": str(doc_id) if doc_id else "",
            "error": str(exc),
        }
    finally:
        if factory is not None:
            factory.close()
