# src/learning/self_learning_engine.py
"""自我学习引擎（增强版）。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


@dataclass
class LearningRecord:
    """单次学习记录。"""

    task_id: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    performance: float
    timestamp: str
    feedback: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "performance": self.performance,
            "timestamp": self.timestamp,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningRecord":
        return cls(
            task_id=data["task_id"],
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            performance=float(data.get("performance", 0.0)),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            feedback=data.get("feedback"),
        )


class SelfLearningEngine(BaseModule):
    """具备模式识别、反馈学习与自适应调参的学习引擎。"""

    _EWMA_DEFAULT_ALPHA = 0.15

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("self_learning_engine", config)
        self.learning_records: List[LearningRecord] = []
        self.performance_history: List[float] = []
        self.model_improvement_log: List[Dict[str, Any]] = []
        self.learning_threshold = self.config.get("learning_threshold", 0.7)
        self.min_performance_for_improvement = self.config.get(
            "min_performance_for_improvement", 0.8
        )
        self._ewma_alpha = float(self.config.get("ewma_alpha", self._EWMA_DEFAULT_ALPHA))
        self._ewma_score: Optional[float] = None
        self._pattern_recognizer = None
        self._adaptive_tuner = None
        # RAG 服务（可选，由外部注入或懒加载）
        self._rag_service: Optional[Any] = None

    def _do_initialize(self) -> bool:
        try:
            self._load_learning_data()
            self._init_submodules()
            self.logger.info("自我学习引擎初始化成功")
            return True
        except Exception as exc:
            self.logger.error("自我学习引擎初始化失败: %s", exc)
            return False

    def _init_submodules(self) -> None:
        try:
            from src.learning.pattern_recognizer import PatternRecognizer

            self._pattern_recognizer = PatternRecognizer(
                min_frequency=self.config.get("pattern_min_frequency", 2),
                anomaly_z_threshold=self.config.get("anomaly_z_threshold", 2.5),
            )
        except Exception:
            self.logger.warning("PatternRecognizer 初始化失败，跳过模式识别")

        try:
            from src.learning.adaptive_tuner import AdaptiveTuner

            self._adaptive_tuner = AdaptiveTuner(
                performance_target=self.config.get("performance_target", 0.80)
            )
        except Exception:
            self.logger.warning("AdaptiveTuner 初始化失败，跳过自适应调参")

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self._record_learning_data(context)

        suggestions = self._evaluate_and_improve(context)

        discovered_patterns: List[Dict[str, Any]] = []
        if self._pattern_recognizer is not None:
            try:
                patterns = self._pattern_recognizer.analyze(context)
                discovered_patterns = [p.to_dict() for p in patterns]
            except Exception as exc:
                self.logger.warning("模式识别执行失败: %s", exc)

        tuned_parameters: Dict[str, float] = {}
        if self._adaptive_tuner is not None and self._ewma_score is not None:
            try:
                tuned_parameters = self._adaptive_tuner.step(
                    {
                        "performance": self._ewma_score,
                        "quality": float(context.get("quality_score", self._ewma_score)),
                        "confidence": float(context.get("confidence_score", 0.5)),
                    }
                )
                if "learning_threshold" in tuned_parameters:
                    self.learning_threshold = tuned_parameters["learning_threshold"]
                if "quality_threshold" in tuned_parameters:
                    self.min_performance_for_improvement = tuned_parameters["quality_threshold"]
            except Exception as exc:
                self.logger.warning("自适应调参执行失败: %s", exc)

        return {
            "learning_suggestions": suggestions,
            "discovered_patterns": discovered_patterns,
            "tuned_parameters": tuned_parameters,
            "ewma_performance": round(self._ewma_score, 4)
            if self._ewma_score is not None
            else None,
            "learning_timestamp": datetime.now().isoformat(),
        }

    def _record_learning_data(self, context: Dict[str, Any]) -> None:
        task_id = self._generate_task_id(context)
        input_data = {
            "text": str(context.get("processed_text", ""))[:200],
            "metadata": context.get("metadata", {}),
        }
        output_data = {
            "entities": context.get("entities", {}),
            "semantic_graph": context.get("semantic_graph", {}),
            "reasoning_results": context.get("reasoning_results", {}),
        }
        performance = self._calculate_performance(context)

        if self._ewma_score is None:
            self._ewma_score = performance
        else:
            self._ewma_score = (
                self._ewma_alpha * performance + (1 - self._ewma_alpha) * self._ewma_score
            )

        record = LearningRecord(
            task_id=task_id,
            input_data=input_data,
            output_data=output_data,
            performance=performance,
            timestamp=datetime.now().isoformat(),
        )
        self.learning_records.append(record)
        self.performance_history.append(performance)
        if len(self.learning_records) > 2000:
            self.learning_records.pop(0)
        if len(self.performance_history) > 2000:
            self.performance_history.pop(0)

        self._save_learning_data()

    def _generate_task_id(self, context: Dict[str, Any]) -> str:
        text_content = str(context.get("processed_text", ""))[:100]
        metadata = str(context.get("metadata", {}))
        combined = text_content + metadata
        return hashlib.md5(combined.encode("utf-8")).hexdigest()[:16]

    def _calculate_performance(self, context: Dict[str, Any]) -> float:
        entities = context.get("entities", [])
        if isinstance(entities, dict):
            entity_count = len(entities)
        elif isinstance(entities, list):
            entity_count = len(entities)
        else:
            entity_count = 0

        confidence = float(context.get("confidence_score", 0.5))

        semantic_graph = context.get("semantic_graph", {})
        graph_bonus = 0.0
        if isinstance(semantic_graph, dict):
            nodes = semantic_graph.get("nodes", [])
            edges = semantic_graph.get("edges", [])
            node_count = len(nodes) if isinstance(nodes, (list, dict)) else 0
            edge_count = len(edges) if isinstance(edges, (list, dict)) else 0
            graph_bonus = min((node_count * 0.01 + edge_count * 0.005), 0.15)

        reasoning = context.get("reasoning_results", {})
        reasoning_bonus = 0.05 if reasoning else 0.0

        entity_score = min(entity_count * 0.05, 0.4)
        performance = confidence * 0.5 + entity_score + graph_bonus + reasoning_bonus
        return max(0.0, min(performance, 1.0))

    def _evaluate_and_improve(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        if len(self.performance_history) >= 10:
            recent = self.performance_history[-10:]
            avg = sum(recent) / len(recent)
            if avg < self.learning_threshold:
                suggestions.append(
                    {
                        "type": "performance_degradation",
                        "message": "检测到近期性能下降，建议调整模型参数或增加训练数据",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            if avg > self.min_performance_for_improvement:
                suggestions.append(
                    {
                        "type": "optimization_opportunity",
                        "message": "当前性能良好，建议进一步优化以提升准确性",
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        suggestions.extend(self._detect_error_patterns(context))
        return suggestions

    def _detect_error_patterns(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        patterns: List[Dict[str, Any]] = []
        entities = context.get("entities", [])
        entity_count = len(entities) if isinstance(entities, (list, dict)) else 0
        if entity_count < 2:
            patterns.append(
                {
                    "type": "low_entity_recognition",
                    "message": "实体识别数量较少，可能存在漏检情况",
                    "suggestion": "增加训练样本或调整识别参数",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        return patterns

    def learn_from_feedback(self, task_id: str, feedback_score: float) -> bool:
        """接收外部反馈并回写历史记录（0-1）。"""
        score = max(0.0, min(1.0, float(feedback_score)))
        for rec in reversed(self.learning_records):
            if rec.task_id == task_id:
                rec.feedback = score
                rec.performance = round((rec.performance * 0.7 + score * 0.3), 4)
                self.model_improvement_log.append(
                    {
                        "task_id": task_id,
                        "feedback_score": score,
                        "updated_performance": rec.performance,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                self._save_learning_data()
                return True
        return False

    # ------------------------------------------------------------------
    # RAG 闭环方法（指令08）
    # ------------------------------------------------------------------

    def set_rag_service(self, rag_service: Any) -> None:
        """注入 RAGService 实例（用于依赖注入或测试）。"""
        self._rag_service = rag_service
        self.logger.info("RAGService 已注入到 SelfLearningEngine")

    def _get_rag_service(self) -> Optional[Any]:
        """懒加载 RAGService，若已注入则直接使用。"""
        if self._rag_service is not None:
            return self._rag_service
        try:
            from src.learning.rag_service import RAGService

            persist_dir = self.config.get("rag_persist_dir", "./data/chroma_db")
            svc = RAGService(persist_dir=persist_dir)
            if svc.available:
                self._rag_service = svc
            return self._rag_service
        except Exception as exc:
            self.logger.debug("RAGService 不可用: %s", exc)
            return None

    def record_outcome(
        self,
        result: Dict[str, Any],
        feedback: float = 0.5,
    ) -> None:
        """
        记录研究阶段结果并在质量达标时写入 RAG 向量库。

        当 ``feedback >= learning_threshold`` 时，将研究摘要与假设写入 ChromaDB，
        供后续研究通过 RAG 检索增强。

        Args:
            result: 研究阶段输出字典（应含 ``summary`` 或 ``hypothesis`` 字段）。
            feedback: 质量反馈分数（0-1），由 QualityAssessor 或人工评分提供。
        """
        score = max(0.0, min(1.0, float(feedback)))

        # 1. 更新 EWMA 性能分数
        if self._ewma_score is None:
            self._ewma_score = score
        else:
            self._ewma_score = (
                self._ewma_alpha * score + (1 - self._ewma_alpha) * self._ewma_score
            )
        self.performance_history.append(score)
        if len(self.performance_history) > 2000:
            self.performance_history.pop(0)

        # 2. 将高质量结论写入 RAG 向量库
        if score >= self.learning_threshold:
            rag = self._get_rag_service()
            if rag is not None:
                self._index_result_to_rag(rag, result)

        # 3. 记录改进日志
        self.model_improvement_log.append(
            {
                "feedback": score,
                "ewma_score": round(self._ewma_score, 4),
                "timestamp": datetime.now().isoformat(),
                "result_phase": result.get("phase", "unknown"),
            }
        )
        self._save_learning_data()

    def improve_prompt(
        self,
        task: str,
        llm: Optional[Any] = None,
    ) -> str:
        """
        利用 RAG 检索历史高质量结论，增强对当前任务的 prompt 上下文。

        若 RAGService 不可用，直接返回原始任务文本。

        Args:
            task: 当前研究任务描述或查询文本。
            llm: 可选的 LLMEngine 实例，若提供则触发 RAG 增强生成。

        Returns:
            增强后的 prompt 字符串或 LLM 生成结果。
        """
        rag = self._get_rag_service()
        if rag is None:
            return task

        if llm is not None:
            return rag.generate_with_rag(task, llm)

        docs = rag.retrieve(task, k=3)
        if not docs:
            return task

        context_lines = [f"[参考{i + 1}] {d['text']}" for i, d in enumerate(docs)]
        return f"{task}\n\n相关历史研究参考：\n" + "\n".join(context_lines)

    def _index_result_to_rag(
        self,
        rag: Any,
        result: Dict[str, Any],
    ) -> None:
        """将研究结果的关键文本片段写入 RAG 向量库。"""
        import hashlib

        phase = result.get("phase", "unknown")
        ts = datetime.now().strftime("%Y%m%d%H%M%S")

        # 提取可索引文本
        text_parts: List[str] = []
        for key in ("summary", "hypothesis", "interpretation", "reflections"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                text_parts.append(val.strip()[:500])
            elif isinstance(val, list):
                for item in val[:3]:
                    part = str(item.get("reflection") or item) if isinstance(item, dict) else str(item)
                    if part.strip():
                        text_parts.append(part.strip()[:200])

        hypotheses = result.get("hypotheses") or (result.get("results") or {}).get("hypotheses") or []
        for h in hypotheses[:3]:
            if isinstance(h, dict) and h.get("title"):
                text_parts.append(str(h["title"]))
            if isinstance(h, dict) and h.get("statement"):
                text_parts.append(str(h["statement"])[:300])

        if not text_parts:
            return

        combined_text = "\n".join(text_parts)
        doc_id = f"outcome_{phase}_{ts}_{hashlib.md5(combined_text.encode(), usedforsecurity=False).hexdigest()[:8]}"
        rag.index_document(
            doc_id=doc_id,
            text=combined_text,
            metadata={"phase": phase, "indexed_at": ts},
        )
        self.logger.debug("高质量结论已写入 RAG: %s", doc_id)

    def _save_learning_data(self) -> None:
        try:
            file_path = self.config.get("learning_data_file", "learning_data.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "records": [r.to_dict() for r in self.learning_records],
                        "performance_history": self.performance_history,
                        "model_improvement_log": self.model_improvement_log,
                        "ewma_score": self._ewma_score,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as exc:
            self.logger.error("保存学习数据失败: %s", exc)

    def _load_learning_data(self) -> None:
        try:
            file_path = self.config.get("learning_data_file", "learning_data.json")
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.learning_records = [
                LearningRecord.from_dict(item) for item in data.get("records", [])
            ]
            self.performance_history = list(data.get("performance_history", []))
            self.model_improvement_log = list(data.get("model_improvement_log", []))
            self._ewma_score = data.get("ewma_score")
            self.logger.info("加载了 %d 条学习记录", len(self.learning_records))
        except FileNotFoundError:
            self.logger.info("未找到学习数据文件，将创建新的学习记录")
        except Exception as exc:
            self.logger.error("加载学习数据失败: %s", exc)

    def _do_cleanup(self) -> bool:
        try:
            self._save_learning_data()
            self.logger.info("自我学习引擎资源清理完成")
            return True
        except Exception as exc:
            self.logger.error("自我学习引擎资源清理失败: %s", exc)
            return False

    def get_learning_stats(self) -> Dict[str, Any]:
        if not self.performance_history:
            return {}
        recent = self.performance_history[-10:]
        return {
            "total_records": len(self.learning_records),
            "average_performance": sum(self.performance_history)
            / len(self.performance_history),
            "recent_performance": recent,
            "ewma_performance": self._ewma_score,
            "model_improvement_log": self.model_improvement_log,
        }
