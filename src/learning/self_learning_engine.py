# src/learning/self_learning_engine.py
"""自我学习引擎（增强版）。"""

from __future__ import annotations

import hashlib
import logging
import pickle
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

    def _save_learning_data(self) -> None:
        try:
            with open(self.config.get("learning_data_file", "learning_data.pkl"), "wb") as f:
                pickle.dump(
                    {
                        "records": [r.to_dict() for r in self.learning_records],
                        "performance_history": self.performance_history,
                        "model_improvement_log": self.model_improvement_log,
                        "ewma_score": self._ewma_score,
                    },
                    f,
                )
        except Exception as exc:
            self.logger.error("保存学习数据失败: %s", exc)

    def _load_learning_data(self) -> None:
        try:
            file_path = self.config.get("learning_data_file", "learning_data.pkl")
            with open(file_path, "rb") as f:
                data = pickle.load(f)
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
