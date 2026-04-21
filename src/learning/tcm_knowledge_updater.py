# src/learning/tcm_knowledge_updater.py
"""
中医知识自更新模块（TCMKnowledgeUpdater）。

从已分析的中医文献中自动提取新知识实体与关系，
写入 Neo4j 知识图谱、ChromaDB 向量库及 PostgreSQL 学习记录，
实现"研究→知识积累→检索增强"的持续自我学习闭环。

知识本体结构（TCM Ontology）：
  医籍(Corpus) ──收录──> 方剂(Formula) ──包含──> 药物(Herb)
  药物(Herb) ──具有──> 功效(Effect)
  方剂(Formula) ──主治──> 证候(Syndrome)
  证候(Syndrome) ──属于──> 疾病(Disease)

参考：
  - Self-RAG (Asai et al., 2023): https://arxiv.org/abs/2310.11511
  - GraphRAG (Edge et al., 2024): https://arxiv.org/abs/2404.16130
  - BioMedRAG (Yang et al., 2024): 领域知识图谱增强检索

用法::

    updater = TCMKnowledgeUpdater()
    stats = updater.update_from_research_result(research_result, "桂枝汤研究")
    print(stats)  # {"entities_added": 12, "relations_added": 8, ...}
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 中医实体识别规则（正则 + 种子词表） ──────────────────────────────────────

# 中医核心药物词表（部分，用于快速识别）
_HERB_SEEDS: List[str] = [
    "人参", "黄芪", "当归", "甘草", "白术", "茯苓", "川芎", "熟地黄", "生地黄",
    "附子", "干姜", "桂枝", "麻黄", "柴胡", "黄连", "黄芩", "大黄", "白芍",
    "赤芍", "丹参", "三七", "五味子", "山药", "泽泻", "车前子", "薏苡仁",
    "陈皮", "半夏", "天南星", "枳实", "厚朴", "木香", "砂仁", "佛手",
    "龙骨", "牡蛎", "石膏", "知母", "黄柏", "苍术", "防风", "羌活",
]

# 证候词表（部分）
_SYNDROME_SEEDS: List[str] = [
    "气虚证", "血虚证", "阴虚证", "阳虚证", "气阴两虚证", "气血两虚证",
    "痰湿证", "湿热证", "气滞血瘀证", "寒凝血瘀证", "肝郁气滞证",
    "脾胃气虚证", "肾阳虚证", "肾阴虚证", "心肾不交证", "肝肾阴虚证",
    "风寒表证", "风热表证", "少阳证", "阳明证", "太阴证",
]

# 疾病词表（部分）
_DISEASE_SEEDS: List[str] = [
    "消渴", "胸痹", "中风", "痹证", "水肿", "泄泻", "便秘", "咳嗽",
    "喘证", "眩晕", "失眠", "心悸", "腹痛", "胃痛", "胁痛", "痛经",
    "月经不调", "崩漏", "不孕症", "阳痿", "遗精",
]

# 方剂识别正则（常见方剂命名模式）
_FORMULA_PATTERN = re.compile(
    r'[\u4e00-\u9fff]{2,8}(?:汤|丸|散|饮|丹|膏|片|颗粒|口服液|注射液|合剂)'
)


@dataclass
class KnowledgeEntity:
    """中医知识图谱实体。"""

    entity_id: str
    entity_type: str  # Herb / Formula / Syndrome / Disease / Corpus
    name: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeRelation:
    """中医知识图谱关系。"""

    relation_id: str
    source_id: str
    target_id: str
    relation_type: str  # CONTAINS / HAS_EFFECT / TREATS / BELONGS_TO / CITED_IN
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateStats:
    """知识更新统计结果。"""

    entities_added: int = 0
    entities_updated: int = 0
    relations_added: int = 0
    vectors_indexed: int = 0
    records_logged: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转为字典。"""
        return {
            "entities_added": self.entities_added,
            "entities_updated": self.entities_updated,
            "relations_added": self.relations_added,
            "vectors_indexed": self.vectors_indexed,
            "records_logged": self.records_logged,
            "errors": self.errors,
        }


class TCMKnowledgeUpdater:
    """中医知识自更新模块。

    从研究结果中提取结构化 TCM 知识，写入三个持久化层：
      - Neo4j: 实体与关系（知识图谱）
      - ChromaDB: 文本向量（RAG 检索增强）
      - PostgreSQL: 学习记录与更新日志

    Parameters
    ----------
    storage_gateway :
        StorageGateway 实例（可选）。为 None 时尝试自动创建。
    rag_service :
        RAGService 实例（可选）。为 None 时尝试自动创建。
    """

    def __init__(
        self,
        storage_gateway: Optional[Any] = None,
        rag_service: Optional[Any] = None,
    ) -> None:
        self._storage = storage_gateway
        self._rag = rag_service
        self._init_backends()

    def _init_backends(self) -> None:
        """延迟初始化后端存储，失败时降级而不崩溃。"""
        if self._storage is None:
            try:
                from src.storage.storage_gateway import StorageGateway
                self._storage = StorageGateway()
            except Exception as exc:
                logger.warning("StorageGateway 初始化失败，知识图谱写入将跳过: %s", exc)

        if self._rag is None:
            try:
                from src.learning.rag_service import RAGService
                self._rag = RAGService()
            except Exception as exc:
                logger.warning("RAGService 初始化失败，向量索引将跳过: %s", exc)

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def update_from_research_result(
        self,
        research_result: Any,
        topic: str = "",
    ) -> UpdateStats:
        """从 TCMResearchResult 对象中提取知识并更新存储。

        Args:
            research_result: TCMResearchResult 实例或包含 ``report``/``phases`` 的字典。
            topic:           研究课题名称（用于日志和标注）。

        Returns:
            UpdateStats 包含各项操作的统计数据。
        """
        stats = UpdateStats()
        session_id = f"update_{uuid.uuid4().hex[:8]}"
        logger.info("🔄 启动知识更新会话 [%s]: %s", session_id, topic)

        # 统一获取文本内容
        texts = self._extract_texts_from_result(research_result)
        if not texts:
            logger.warning("知识更新：未能从研究结果中提取文本内容")
            return stats

        all_text = "\n".join(texts)

        # Step 1: 实体提取
        entities = self._extract_entities(all_text, topic)
        logger.info("实体提取完成，共 %d 个实体", len(entities))

        # Step 2: 关系推断
        relations = self._infer_relations(entities, all_text)
        logger.info("关系推断完成，共 %d 条关系", len(relations))

        # Step 3: 写入 Neo4j
        neo4j_stats = self._write_to_neo4j(entities, relations)
        stats.entities_added += neo4j_stats.get("entities_added", 0)
        stats.entities_updated += neo4j_stats.get("entities_updated", 0)
        stats.relations_added += neo4j_stats.get("relations_added", 0)
        stats.errors.extend(neo4j_stats.get("errors", []))

        # Step 4: 索引到 ChromaDB
        rag_stats = self._index_to_chromadb(texts, topic, session_id)
        stats.vectors_indexed += rag_stats.get("indexed", 0)
        stats.errors.extend(rag_stats.get("errors", []))

        # Step 5: 记录学习日志到 PostgreSQL
        log_stats = self._log_learning_record(session_id, topic, stats, entities)
        stats.records_logged += log_stats.get("logged", 0)

        logger.info(
            "✅ 知识更新完成 [%s]: 实体+%d, 关系+%d, 向量+%d",
            session_id,
            stats.entities_added,
            stats.relations_added,
            stats.vectors_indexed,
        )
        return stats

    def update_from_corpus(
        self,
        corpus: Dict[str, Any],
        topic: str = "",
    ) -> UpdateStats:
        """直接从文献语料更新知识库（无需完整研究流程）。

        Args:
            corpus: 语料字典，含 ``documents`` 或 ``texts``。
            topic:  研究课题/来源标注。

        Returns:
            UpdateStats。
        """
        stats = UpdateStats()
        texts: List[str] = []

        if "documents" in corpus:
            for doc in corpus["documents"]:
                if isinstance(doc, dict):
                    content = doc.get("content") or doc.get("text", "")
                    if content:
                        texts.append(str(content))
        elif "texts" in corpus:
            texts = [str(t) for t in corpus["texts"] if t]
        elif "text" in corpus:
            texts = [str(corpus["text"])]

        if not texts:
            return stats

        all_text = "\n".join(texts)
        entities = self._extract_entities(all_text, topic)
        relations = self._infer_relations(entities, all_text)

        neo4j_stats = self._write_to_neo4j(entities, relations)
        stats.entities_added += neo4j_stats.get("entities_added", 0)
        stats.relations_added += neo4j_stats.get("relations_added", 0)

        rag_stats = self._index_to_chromadb(texts, topic, f"corpus_{uuid.uuid4().hex[:6]}")
        stats.vectors_indexed += rag_stats.get("indexed", 0)

        return stats

    # ── 实体提取 ──────────────────────────────────────────────────────────────

    def _extract_entities(
        self, text: str, topic: str = ""
    ) -> List[KnowledgeEntity]:
        """从文本中提取中医知识实体。"""
        entities: List[KnowledgeEntity] = []
        seen: set = set()

        # 提取药物
        for herb in _HERB_SEEDS:
            if herb in text and herb not in seen:
                count = text.count(herb)
                entities.append(KnowledgeEntity(
                    entity_id=f"herb_{uuid.uuid4().hex[:8]}",
                    entity_type="Herb",
                    name=herb,
                    properties={"frequency": count, "source_topic": topic},
                ))
                seen.add(herb)

        # 提取方剂（正则匹配）
        for m in _FORMULA_PATTERN.finditer(text):
            formula = m.group()
            if formula not in seen:
                entities.append(KnowledgeEntity(
                    entity_id=f"formula_{uuid.uuid4().hex[:8]}",
                    entity_type="Formula",
                    name=formula,
                    properties={"source_topic": topic, "position": m.start()},
                ))
                seen.add(formula)

        # 提取证候
        for syndrome in _SYNDROME_SEEDS:
            if syndrome in text and syndrome not in seen:
                entities.append(KnowledgeEntity(
                    entity_id=f"syndrome_{uuid.uuid4().hex[:8]}",
                    entity_type="Syndrome",
                    name=syndrome,
                    properties={"frequency": text.count(syndrome), "source_topic": topic},
                ))
                seen.add(syndrome)

        # 提取疾病
        for disease in _DISEASE_SEEDS:
            if disease in text and disease not in seen:
                entities.append(KnowledgeEntity(
                    entity_id=f"disease_{uuid.uuid4().hex[:8]}",
                    entity_type="Disease",
                    name=disease,
                    properties={"frequency": text.count(disease), "source_topic": topic},
                ))
                seen.add(disease)

        return entities

    # ── 关系推断 ──────────────────────────────────────────────────────────────

    def _infer_relations(
        self, entities: List[KnowledgeEntity], text: str
    ) -> List[KnowledgeRelation]:
        """根据实体在文本中的共现关系推断知识关系。"""
        relations: List[KnowledgeRelation] = []

        formulas = [e for e in entities if e.entity_type == "Formula"]
        herbs = [e for e in entities if e.entity_type == "Herb"]
        syndromes = [e for e in entities if e.entity_type == "Syndrome"]
        diseases = [e for e in entities if e.entity_type == "Disease"]

        # 方剂→药物：共现窗口内视为包含关系
        for formula in formulas:
            idx = text.find(formula.name)
            if idx < 0:
                continue
            window = text[max(0, idx - 100): idx + 200]
            for herb in herbs:
                if herb.name in window:
                    relations.append(KnowledgeRelation(
                        relation_id=f"rel_{uuid.uuid4().hex[:8]}",
                        source_id=formula.entity_id,
                        target_id=herb.entity_id,
                        relation_type="CONTAINS",
                        properties={"confidence": 0.7},
                    ))

        # 方剂→证候：主治关系
        for formula in formulas:
            idx = text.find(formula.name)
            if idx < 0:
                continue
            window = text[max(0, idx - 50): idx + 300]
            for syndrome in syndromes:
                if syndrome.name in window:
                    relations.append(KnowledgeRelation(
                        relation_id=f"rel_{uuid.uuid4().hex[:8]}",
                        source_id=formula.entity_id,
                        target_id=syndrome.entity_id,
                        relation_type="TREATS_SYNDROME",
                        properties={"confidence": 0.65},
                    ))

        # 证候→疾病：归属关系
        for syndrome in syndromes:
            for disease in diseases:
                if syndrome.name in text and disease.name in text:
                    # 简化：同文本内同时出现则建立归属关系
                    relations.append(KnowledgeRelation(
                        relation_id=f"rel_{uuid.uuid4().hex[:8]}",
                        source_id=syndrome.entity_id,
                        target_id=disease.entity_id,
                        relation_type="BELONGS_TO_DISEASE",
                        properties={"confidence": 0.5},
                    ))

        return relations

    # ── 存储写入 ──────────────────────────────────────────────────────────────

    def _write_to_neo4j(
        self,
        entities: List[KnowledgeEntity],
        relations: List[KnowledgeRelation],
    ) -> Dict[str, Any]:
        """将实体和关系写入 Neo4j 知识图谱。"""
        result: Dict[str, Any] = {
            "entities_added": 0, "entities_updated": 0,
            "relations_added": 0, "errors": [],
        }
        if self._storage is None:
            return result

        # 写入实体
        entity_records = [
            {
                "id": e.entity_id,
                "type": e.entity_type,
                "name": e.name,
                **e.properties,
            }
            for e in entities
        ]
        try:
            if hasattr(self._storage, "save_entities"):
                self._storage.save_entities(entity_records)
                result["entities_added"] = len(entities)
        except Exception as exc:
            result["errors"].append(f"Neo4j 实体写入失败: {exc}")
            logger.warning("Neo4j 实体写入失败: %s", exc)

        # 写入关系
        relation_records = [
            {
                "id": r.relation_id,
                "source": r.source_id,
                "target": r.target_id,
                "type": r.relation_type,
                **r.properties,
            }
            for r in relations
        ]
        try:
            if hasattr(self._storage, "save_relations"):
                self._storage.save_relations(relation_records)
                result["relations_added"] = len(relations)
        except Exception as exc:
            result["errors"].append(f"Neo4j 关系写入失败: {exc}")
            logger.warning("Neo4j 关系写入失败: %s", exc)

        return result

    def _index_to_chromadb(
        self, texts: List[str], topic: str, session_id: str
    ) -> Dict[str, Any]:
        """将研究文本写入 ChromaDB 向量库，用于未来 RAG 检索。"""
        result: Dict[str, Any] = {"indexed": 0, "errors": []}
        if self._rag is None or not texts:
            return result

        try:
            if hasattr(self._rag, "index_documents"):
                docs = [
                    {"id": f"{session_id}_{i}", "content": t, "metadata": {"topic": topic}}
                    for i, t in enumerate(texts)
                ]
                self._rag.index_documents(docs)
                result["indexed"] = len(texts)
            elif hasattr(self._rag, "index"):
                for i, text in enumerate(texts):
                    self._rag.index(
                        doc_id=f"{session_id}_{i}",
                        content=text,
                        metadata={"topic": topic, "session": session_id},
                    )
                    result["indexed"] += 1
        except Exception as exc:
            result["errors"].append(f"ChromaDB 向量索引失败: {exc}")
            logger.warning("ChromaDB 向量索引失败: %s", exc)

        return result

    def _log_learning_record(
        self,
        session_id: str,
        topic: str,
        stats: UpdateStats,
        entities: List[KnowledgeEntity],
    ) -> Dict[str, Any]:
        """将学习记录写入 PostgreSQL（通过 StorageGateway）。"""
        result: Dict[str, Any] = {"logged": 0}
        if self._storage is None:
            return result

        record = {
            "session_id": session_id,
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "entities_extracted": len(entities),
            "entity_types": list({e.entity_type for e in entities}),
            "stats": stats.to_dict(),
        }
        try:
            if hasattr(self._storage, "save_research_result"):
                self._storage.save_research_result(f"learn_{session_id}", record)
                result["logged"] = 1
        except Exception as exc:
            logger.warning("学习记录写入失败: %s", exc)

        return result

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _extract_texts_from_result(self, research_result: Any) -> List[str]:
        """从不同格式的研究结果中提取文本列表。"""
        texts: List[str] = []
        if research_result is None:
            return texts

        # 若为 TCMResearchResult dataclass
        if hasattr(research_result, "report") and research_result.report:
            texts.append(research_result.report)
        if hasattr(research_result, "phases"):
            for phase in research_result.phases:
                if hasattr(phase, "ai_output") and phase.ai_output:
                    texts.append(phase.ai_output)

        # 若为字典
        if isinstance(research_result, dict):
            if "report" in research_result:
                texts.append(str(research_result["report"]))
            for phase_data in research_result.get("phases", []):
                if isinstance(phase_data, dict) and phase_data.get("ai_output"):
                    texts.append(str(phase_data["ai_output"]))

        return [t for t in texts if t.strip()]


__all__ = [
    "TCMKnowledgeUpdater",
    "KnowledgeEntity",
    "KnowledgeRelation",
    "UpdateStats",
]
