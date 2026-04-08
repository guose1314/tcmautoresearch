"""论文插件双库持久化（PostgreSQL + Neo4j）。"""

import importlib
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def persist_paper_result_to_dual_storage(
    source_path: str,
    result_payload: Dict[str, Any],
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, str]:
    """将论文插件输出写入 PostgreSQL + Neo4j。"""
    storage_driver_module = importlib.import_module("src.storage.storage_driver")
    UnifiedStorageDriver = getattr(storage_driver_module, "UnifiedStorageDriver")

    storage = None
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

        storage = UnifiedStorageDriver(pg_url, neo4j_uri, (neo4j_user, neo4j_password))
        storage.initialize()

        doc_id = storage.save_document(
            source_file=source_path,
            objective="paper_plugin_archive",
            raw_text_size=int(result_payload.get("char_count", 0)),
        )
        if not doc_id:
            return {
                "status": "failed",
                "document_id": "",
                "error": "保存文档失败",
            }

        storage.update_document_status(doc_id, "processing")
        storage.log_module_execution(
            document_id=doc_id,
            module_name="paper_plugin",
            status="start",
            message="论文插件结果开始双库存档",
        )

        source_name = Path(source_path).name
        entities = [
            {
                "name": source_name,
                "type": "other",
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
                "type": "other",
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
                "type": "other",
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
        entity_ids = storage.save_entities(doc_id, entities)
        if len(entity_ids) < 3:
            storage.update_document_status(doc_id, "failed")
            return {
                "status": "failed",
                "document_id": str(doc_id),
                "error": "保存实体失败",
            }

        relationships = [
            {
                "source_entity_id": entity_ids[0],
                "target_entity_id": entity_ids[1],
                "relationship_type": "CONTAINS",
                "confidence": 0.95,
                "created_by_module": "paper_plugin",
                "evidence": "论文包含摘要内容",
                "metadata": {"semantic_role": "summary"},
            },
            {
                "source_entity_id": entity_ids[0],
                "target_entity_id": entity_ids[2],
                "relationship_type": "CONTAINS",
                "confidence": 0.90,
                "created_by_module": "paper_plugin",
                "evidence": "论文包含翻译节选内容",
                "metadata": {"semantic_role": "translation_excerpt"},
            },
        ]
        rel_ids = storage.save_relationships(doc_id, relationships)

        storage.save_statistics(
            doc_id,
            {
                "formulas_count": 0,
                "herbs_count": 0,
                "syndromes_count": 0,
                "efficacies_count": 0,
                "relationships_count": len(rel_ids),
                "graph_nodes_count": len(entity_ids),
                "graph_edges_count": len(rel_ids),
                "graph_density": 0.0,
                "connected_components": 1,
                "source_modules": ["paper_plugin"],
                "processing_time_ms": 0,
            },
        )

        storage.save_research_analysis(
            doc_id,
            {
                "summary_analysis": {
                    "paper_summary": result_payload.get("summary", ""),
                    "translation_excerpt": result_payload.get("translation_excerpt", ""),
                    "paper_source_type": result_payload.get("source_type", "unknown"),
                    "paper_output_json": result_payload.get("output_json", ""),
                    "paper_output_markdown": result_payload.get("output_markdown", ""),
                }
            },
        )

        storage.log_module_execution(
            document_id=doc_id,
            module_name="paper_plugin",
            status="success",
            message="论文插件结果已完成双库存档",
        )
        storage.update_document_status(doc_id, "completed")
        return {
            "status": "completed",
            "document_id": str(doc_id),
            "error": "",
        }
    except Exception as exc:
        if storage and doc_id:
            try:
                storage.log_module_execution(
                    document_id=doc_id,
                    module_name="paper_plugin",
                    status="failure",
                    message="论文插件双库存档失败",
                    error_details=str(exc),
                )
                storage.update_document_status(doc_id, "failed")
            except Exception:
                pass
        return {
            "status": "failed",
            "document_id": str(doc_id) if doc_id else "",
            "error": str(exc),
        }
    finally:
        if storage:
            storage.close()
