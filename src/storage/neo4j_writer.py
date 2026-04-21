# src/storage/neo4j_writer.py
"""
Neo4j 研究结果写入适配器（TCMGraphWriter）。

将研究阶段产出的实体与关系持久化到 Neo4j 图谱，
实现科研知识的跨会话积累。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TCMGraphWriter:
    """
    将研究阶段结果写入 Neo4j 图谱。

    设计原则：
    - 依赖注入：接受外部传入的 Neo4jDriver，便于测试与替换。
    - 故障容忍：写入失败时仅记录日志，不中断研究主流程。
    - 幂等性：通过 MERGE 语义保证重复写入无副作用。

    用法::

        from src.storage.neo4j_driver import Neo4jDriver, Neo4jNode, Neo4jEdge
        driver = Neo4jDriver(uri, auth)
        driver.connect()
        writer = TCMGraphWriter(driver)
        writer.write_analysis_result(result, cycle_id="cycle_001")
    """

    def __init__(self, driver: Any) -> None:
        """
        Args:
            driver: 已连接的 Neo4jDriver 实例。
        """
        self.driver = driver

    def write_analysis_result(
        self,
        result: Dict[str, Any],
        cycle_id: str = "",
    ) -> None:
        """
        将分析结果中的实体与关系写入 Neo4j 图谱。

        Args:
            result: 研究阶段输出字典，支持以下结构：
                - ``entities``: 实体列表 [{"id": ..., "type": ..., ...}]
                - ``relations`` / ``relationships``: 关系列表
                - ``method_results``: ResearchMethodRouter 输出
            cycle_id: 当前研究周期 ID，用于写入 ``_cycle_id`` 属性。
        """
        if not result or not isinstance(result, dict):
            return

        try:
            from src.storage.neo4j_driver import Neo4jEdge, Neo4jNode

            nodes_written = 0
            edges_written = 0

            # 写入实体节点
            entities = result.get("entities") or result.get("results", {}).get("entities") or []
            for entity in self._normalize_entities(entities, cycle_id):
                try:
                    self.driver.create_node(
                        Neo4jNode(
                            id=entity["id"],
                            label=entity.get("type", "Entity"),
                            properties=entity,
                        )
                    )
                    nodes_written += 1
                except Exception as exc:
                    logger.debug("写入实体节点失败 (id=%s): %s", entity.get("id"), exc)

            # 写入关系边
            relations = (
                result.get("relations")
                or result.get("relationships")
                or result.get("aggregate", {}).get("semantic_relationships")
                or []
            )
            for rel in self._normalize_relations(relations, cycle_id):
                try:
                    self.driver.create_relationship(
                        Neo4jEdge(
                            source_id=rel["source_id"],
                            target_id=rel["target_id"],
                            relationship_type=rel["type"],
                            properties=rel.get("properties", {}),
                        )
                    )
                    edges_written += 1
                except Exception as exc:
                    logger.debug("写入关系失败 (%s→%s): %s", rel.get("source_id"), rel.get("target_id"), exc)

            # 写入 method_results 中的额外实体
            for method_key, method_result in (result.get("method_results") or {}).items():
                if isinstance(method_result, dict) and method_result.get("status") == "success":
                    sub_result = method_result.get("result", {})
                    sub_entities = sub_result.get("entities") or sub_result.get("components") or []
                    for entity in self._normalize_entities(sub_entities, cycle_id, source=method_key):
                        try:
                            self.driver.create_node(
                                Neo4jNode(
                                    id=entity["id"],
                                    label=entity.get("type", "Entity"),
                                    properties=entity,
                                )
                            )
                            nodes_written += 1
                        except Exception as exc:
                            logger.debug("写入方法实体失败 (id=%s): %s", entity.get("id"), exc)

            logger.info(
                "Neo4j 写入完成 (cycle=%s): %d 个节点, %d 条关系",
                cycle_id, nodes_written, edges_written,
            )
        except ImportError:
            logger.warning("Neo4j 驱动不可用，跳过图谱写入")
        except Exception as exc:
            logger.error("Neo4j 写入失败 (cycle=%s): %s", cycle_id, exc)

    # ------------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_entities(
        entities: List[Any],
        cycle_id: str,
        source: str = "pipeline",
    ) -> List[Dict[str, Any]]:
        """将不同格式的实体统一为 Neo4j 节点属性字典。"""
        normalized: List[Dict[str, Any]] = []
        for item in entities:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("id") or "").strip()
            if not name:
                continue
            node_id = item.get("id") or f"{source}:{name}"
            props = {
                **item,
                "id": node_id,
                "_cycle_id": cycle_id,
                "_source": source,
            }
            normalized.append(props)
        return normalized

    @staticmethod
    def _normalize_relations(
        relations: List[Any],
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """将不同格式的关系统一为 Neo4j 边属性字典。"""
        normalized: List[Dict[str, Any]] = []
        for item in relations:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or item.get("src") or "").strip()
            target = str(item.get("target") or item.get("dst") or "").strip()
            rel_type = str(item.get("type") or item.get("rel_type") or "RELATED_TO").strip()
            if not source or not target:
                continue
            metadata = item.get("metadata") or {}
            props = {
                "_cycle_id": cycle_id,
                "confidence": float(metadata.get("confidence") or 0.0),
            }
            normalized.append({
                "source_id": source,
                "target_id": target,
                "type": rel_type.upper(),
                "properties": props,
            })
        return normalized
