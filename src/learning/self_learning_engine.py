# src/learning/self_learning_engine.py
"""自我学习引擎（增强版）。"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
    phase: Optional[str] = None
    quality_dimensions: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "task_id": self.task_id,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "performance": self.performance,
            "timestamp": self.timestamp,
            "feedback": self.feedback,
        }
        if self.phase is not None:
            d["phase"] = self.phase
        if self.quality_dimensions is not None:
            d["quality_dimensions"] = self.quality_dimensions
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningRecord":
        return cls(
            task_id=data["task_id"],
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            performance=float(data.get("performance", 0.0)),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            feedback=data.get("feedback"),
            phase=data.get("phase"),
            quality_dimensions=data.get("quality_dimensions"),
        )


class SelfLearningEngine(BaseModule):
    """具备模式识别、反馈学习与自适应调参的学习引擎。"""

    _EWMA_DEFAULT_ALPHA = 0.15
    _MAX_IMPROVEMENT_LOG = 2000

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
        self._dimension_trends: Dict[str, List[float]] = {}
        self._persisted_tuned_parameters: Dict[str, float] = {}
        self._save_dirty = False

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
            self._restore_tuned_parameters()
        except Exception:
            self.logger.warning("AdaptiveTuner 初始化失败，跳过自适应调参")

    def _restore_tuned_parameters(self) -> None:
        if not self._persisted_tuned_parameters:
            return

        if self._adaptive_tuner is not None:
            for name, value in self._persisted_tuned_parameters.items():
                try:
                    self._adaptive_tuner.set_parameter(name, float(value))
                except Exception as exc:
                    self.logger.warning("恢复调参快照失败 %s=%s: %s", name, value, exc)

        self._apply_threshold_overrides(self._persisted_tuned_parameters)

    def _apply_threshold_overrides(self, tuned_parameters: Dict[str, Any]) -> None:
        learning_threshold = tuned_parameters.get("learning_threshold")
        if learning_threshold is not None:
            self.learning_threshold = float(learning_threshold)

        quality_threshold = tuned_parameters.get("quality_threshold")
        if quality_threshold is not None:
            self.min_performance_for_improvement = float(quality_threshold)

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

        self._save_dirty = True

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
                self._save_dirty = True
                return True
        return False

    # ------------------------------------------------------------------
    # 结构化质量反馈接口 — 接收 QualityAssessor 评估结果
    # ------------------------------------------------------------------

    def learn_from_quality_assessment(
        self, phase: str, quality_score: "Any", result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """从 QualityAssessor.assess_quality() 的 QualityScore 学习。

        Args:
            phase: 研究阶段名称 (observe/hypothesis/experiment/analyze/publish/reflect)
            quality_score: QualityScore 对象或包含 overall_score 的 dict
            result: 原始阶段产出 (可选)
        Returns:
            True 表示记录成功
        """
        try:
            if hasattr(quality_score, "overall_score"):
                overall = float(quality_score.overall_score)
                dims = {
                    "completeness": float(quality_score.completeness),
                    "consistency": float(quality_score.consistency),
                    "evidence_quality": float(quality_score.evidence_quality),
                }
                grade = getattr(quality_score, "grade_level", "unknown")
            elif isinstance(quality_score, dict):
                overall = float(quality_score.get("overall_score", 0.0))
                dims = {
                    "completeness": float(quality_score.get("completeness", 0.0)),
                    "consistency": float(quality_score.get("consistency", 0.0)),
                    "evidence_quality": float(quality_score.get("evidence_quality", 0.0)),
                }
                grade = quality_score.get("grade_level", "unknown")
            else:
                return False

            task_id = hashlib.md5(
                f"{phase}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]

            record = LearningRecord(
                task_id=task_id,
                input_data={"phase": phase, "grade": grade},
                output_data={"result_keys": list((result or {}).keys())[:20]},
                performance=overall,
                timestamp=datetime.now().isoformat(),
                feedback=overall,
                phase=phase,
                quality_dimensions=dims,
            )
            self.learning_records.append(record)
            self.performance_history.append(overall)

            if self._ewma_score is None:
                self._ewma_score = overall
            else:
                self._ewma_score = (
                    self._ewma_alpha * overall + (1 - self._ewma_alpha) * self._ewma_score
                )

            # 维度趋势追踪
            self._update_dimension_trends(phase, dims)

            if len(self.learning_records) > 2000:
                self.learning_records.pop(0)
            if len(self.performance_history) > 2000:
                self.performance_history.pop(0)

            self.model_improvement_log.append({
                "type": "quality_assessment",
                "phase": phase,
                "overall_score": overall,
                "grade": grade,
                "dimensions": dims,
                "timestamp": datetime.now().isoformat(),
            })
            self._cap_improvement_log()
            self._save_dirty = True
            return True
        except Exception as exc:
            self.logger.warning("learn_from_quality_assessment 失败: %s", exc)
            return False

    def learn_from_cycle_reflection(self, cycle_assessment: Dict[str, Any]) -> Dict[str, Any]:
        """从 QualityAssessor.assess_cycle_for_reflection() 的完整循环评估学习。

        Args:
            cycle_assessment: 循环评估字典，包含 phase_assessments, weaknesses, strengths, overall_cycle_score
        Returns:
            学习结果摘要: {recorded_phases, weak_phases, improvement_priorities, cycle_trend}
        """
        try:
            overall = float(cycle_assessment.get("overall_cycle_score", 0.0))
            weaknesses = cycle_assessment.get("weaknesses", [])
            strengths = cycle_assessment.get("strengths", [])
            phase_assessments = cycle_assessment.get("phase_assessments", [])

            # 为每个阶段记录质量分
            recorded_phases = []
            for pa in phase_assessments:
                score = pa.get("score")
                phase_name = pa.get("phase", "unknown")
                if score is not None:
                    self.learn_from_quality_assessment(phase_name, score)
                    recorded_phases.append(phase_name)

            # 分析薄弱阶段并生成学习优先级
            weak_phases = []
            for w in weaknesses:
                weak_phases.append({
                    "phase": w.get("phase", "unknown"),
                    "score": w.get("score", 0.0),
                    "issues": w.get("issues", [])[:5],
                })

            # 基于薄弱阶段生成改进优先级
            improvement_priorities = self._derive_improvement_priorities(
                weaknesses, strengths, overall
            )

            # ---- 模式提取 → PatternRecognizer ----
            extracted_patterns = self._extract_reflection_patterns(
                phase_assessments, weaknesses, strengths
            )

            # ---- 调参闭环 → AdaptiveTuner ----
            tuned_parameters = self._tune_from_reflection(overall, weaknesses)

            # 循环级 EWMA 趋势
            cycle_trend = self._compute_cycle_trend(overall)

            summary = {
                "recorded_phases": recorded_phases,
                "weak_phases": weak_phases,
                "improvement_priorities": improvement_priorities,
                "cycle_trend": cycle_trend,
                "overall_score": overall,
                "extracted_patterns": extracted_patterns,
                "tuned_parameters": tuned_parameters,
            }

            self.model_improvement_log.append({
                "type": "cycle_reflection",
                "overall_score": overall,
                "recorded_phases": recorded_phases,
                "weak_phase_count": len(weak_phases),
                "timestamp": datetime.now().isoformat(),
            })
            self._cap_improvement_log()
            self._save_dirty = True
            return summary
        except Exception as exc:
            self.logger.warning("learn_from_cycle_reflection 失败: %s", exc)
            return {"recorded_phases": [], "weak_phases": [], "improvement_priorities": [], "cycle_trend": "unknown"}

    def get_phase_performance(self, phase: str) -> Dict[str, Any]:
        """获取指定阶段的历史性能摘要。"""
        phase_records = [r for r in self.learning_records if r.phase == phase]
        if not phase_records:
            return {"phase": phase, "record_count": 0}
        scores = [r.performance for r in phase_records]
        dim_agg: Dict[str, List[float]] = {}
        for r in phase_records:
            if r.quality_dimensions:
                for k, v in r.quality_dimensions.items():
                    dim_agg.setdefault(k, []).append(v)
        return {
            "phase": phase,
            "record_count": len(phase_records),
            "avg_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "latest_score": scores[-1],
            "avg_dimensions": {k: sum(v) / len(v) for k, v in dim_agg.items()},
        }

    def get_dimension_trends(self) -> Dict[str, List[float]]:
        """返回各维度的历史趋势 (保留最近 50 个数据点)。"""
        return dict(self._dimension_trends)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _update_dimension_trends(self, phase: str, dims: Dict[str, float]) -> None:
        """更新维度历史趋势。"""
        if not hasattr(self, "_dimension_trends"):
            self._dimension_trends: Dict[str, List[float]] = {}
        for key, val in dims.items():
            self._dimension_trends.setdefault(key, []).append(val)
            if len(self._dimension_trends[key]) > 50:
                self._dimension_trends[key].pop(0)

    def _derive_improvement_priorities(
        self,
        weaknesses: List[Dict[str, Any]],
        strengths: List[Dict[str, Any]],
        overall: float,
    ) -> List[str]:
        """基于薄弱阶段和整体评分推导改进优先级。"""
        priorities: List[str] = []
        for w in sorted(weaknesses, key=lambda x: x.get("score", 1.0)):
            phase = w.get("phase", "unknown")
            score = w.get("score", 0.0)
            if score < 0.4:
                priorities.append(f"紧急: 重构{phase}阶段输出规范 (评分 {score:.2f})")
            elif score < 0.6:
                priorities.append(f"优先: 提升{phase}阶段数据完整性 (评分 {score:.2f})")
            else:
                priorities.append(f"建议: 优化{phase}阶段细节 (评分 {score:.2f})")
        if overall < 0.6 and not priorities:
            priorities.append("整体评分偏低，建议全局质量基线提升")
        return priorities

    def _compute_cycle_trend(self, current_overall: float) -> str:
        """基于近期历史判断循环质量趋势。"""
        cycle_logs = [
            entry for entry in self.model_improvement_log
            if entry.get("type") == "cycle_reflection"
        ]
        if len(cycle_logs) < 2:
            return "insufficient_data"
        recent_scores = [entry["overall_score"] for entry in cycle_logs[-5:]]
        recent_scores.append(current_overall)
        if len(recent_scores) < 2:
            return "insufficient_data"
        first_half = recent_scores[: len(recent_scores) // 2]
        second_half = recent_scores[len(recent_scores) // 2 :]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        diff = avg_second - avg_first
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        return "stable"

    # ------------------------------------------------------------------
    # 反馈闭环：模式提取 + 自适应调参
    # ------------------------------------------------------------------

    def _extract_reflection_patterns(
        self,
        phase_assessments: List[Dict[str, Any]],
        weaknesses: List[Dict[str, Any]],
        strengths: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """从反思阶段的质量评估中提取模式，喂给 PatternRecognizer。"""
        context: Dict[str, Any] = {
            "phase_scores": {
                pa.get("phase", "unknown"): (
                    pa["score"].overall_score
                    if hasattr(pa.get("score"), "overall_score")
                    else float(pa.get("score", 0.0))
                )
                for pa in phase_assessments
            },
            "weaknesses": [
                {"phase": w.get("phase"), "score": w.get("score", 0.0)}
                for w in weaknesses
            ],
            "strengths": [
                {"phase": s.get("phase"), "score": s.get("score", 0.0)}
                for s in strengths
            ],
            "dimension_trends": dict(self._dimension_trends),
        }
        try:
            patterns = self._pattern_recognizer.analyze(context)
        except Exception as exc:
            self.logger.warning("反思阶段模式提取失败: %s", exc)
            return []
        return [
            {
                "pattern_id": getattr(p, "pattern_id", None),
                "type": getattr(p, "type", None),
                "description": getattr(p, "description", ""),
                "confidence": getattr(p, "confidence", 0.0),
            }
            for p in (patterns or [])
        ]

    def _tune_from_reflection(
        self,
        overall_score: float,
        weaknesses: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """将反思评分 + 维度趋势转化为 AdaptiveTuner 调参信号。"""
        # 基础 metrics —— 沿用 overall_score 作为 performance 信号
        metrics: Dict[str, float] = {"performance": overall_score}

        # 如果有维度趋势，取最近值作为额外 metrics 供 tuner 感知
        for dim_name, history in self._dimension_trends.items():
            if history:
                metrics[dim_name] = history[-1]

        # 基于弱项调低相关阈值的灵敏度
        weak_scores = [w.get("score", 1.0) for w in weaknesses]
        if weak_scores:
            metrics["min_phase_score"] = min(weak_scores)

        try:
            self._adaptive_tuner.step(metrics)
        except Exception as exc:
            self.logger.warning("反思阶段自适应调参失败: %s", exc)
            return {}

        tuned_parameters = dict(self._adaptive_tuner.current_values())
        self._persisted_tuned_parameters = dict(tuned_parameters)
        self._apply_threshold_overrides(tuned_parameters)
        return tuned_parameters

    def get_tuned_parameters(self) -> Dict[str, float]:
        if self._adaptive_tuner is not None:
            try:
                tuned_parameters = dict(self._adaptive_tuner.current_values())
            except Exception as exc:
                self.logger.warning("读取 AdaptiveTuner 当前参数失败: %s", exc)
            else:
                self._persisted_tuned_parameters = dict(tuned_parameters)
                return tuned_parameters
        return dict(self._persisted_tuned_parameters)

    def has_learning_state(self) -> bool:
        return bool(
            self.learning_records
            or self.model_improvement_log
            or self._persisted_tuned_parameters
            or self._ewma_score is not None
        )

    def get_learning_strategy(self) -> Dict[str, Any]:
        if not self.has_learning_state():
            return {}

        cycle_logs = [
            entry for entry in self.model_improvement_log
            if entry.get("type") == "cycle_reflection"
        ]
        last_cycle = cycle_logs[-1] if cycle_logs else {}
        tuned_parameters = self.get_tuned_parameters()
        strategy: Dict[str, Any] = {
            "strategy_source": "self_learning_engine",
            "strategy_version": "self_learning.v1",
            "learning_threshold": round(float(self.learning_threshold), 6),
            "min_performance_for_improvement": round(
                float(self.min_performance_for_improvement),
                6,
            ),
            "ewma_performance": round(float(self._ewma_score), 4)
            if self._ewma_score is not None
            else None,
            "cycle_reflection_count": len(cycle_logs),
            "last_updated_at": last_cycle.get("timestamp")
            or (self.model_improvement_log[-1].get("timestamp") if self.model_improvement_log else None),
            "tuned_parameters": tuned_parameters,
        }
        if last_cycle:
            strategy["last_cycle_score"] = float(last_cycle.get("overall_score", 0.0))
            strategy["recorded_phases"] = list(last_cycle.get("recorded_phases") or [])
            strategy["weak_phase_count"] = int(last_cycle.get("weak_phase_count", 0))
        return strategy

    def build_previous_iteration_feedback(self) -> Dict[str, Any]:
        strategy = self.get_learning_strategy()
        if not strategy:
            return {}

        last_cycle_score = strategy.get("last_cycle_score")
        feedback: Dict[str, Any] = {
            "status": "completed",
            "iteration_number": int(strategy.get("cycle_reflection_count", 0)),
            "learning_summary": {
                "recorded_phases": list(strategy.get("recorded_phases") or []),
                "weak_phase_count": int(strategy.get("weak_phase_count", 0)),
                "cycle_trend": self._compute_cycle_trend(float(last_cycle_score or 0.0)),
                "tuned_parameters": dict(strategy.get("tuned_parameters") or {}),
            },
        }
        if last_cycle_score is not None:
            feedback["cycle_quality_score"] = float(last_cycle_score)
            feedback["quality_assessment"] = {
                "overall_cycle_score": float(last_cycle_score),
            }
        return feedback

    def _save_learning_data(self) -> None:
        try:
            tuned_parameters = dict(self._persisted_tuned_parameters)
            if self.has_learning_state() and self._adaptive_tuner is not None:
                try:
                    tuned_parameters = dict(self._adaptive_tuner.current_values())
                except Exception as exc:
                    self.logger.warning("保存学习数据时读取调参快照失败: %s", exc)
                else:
                    self._persisted_tuned_parameters = dict(tuned_parameters)
            payload = {
                "records": [r.to_dict() for r in self.learning_records],
                "performance_history": self.performance_history,
                "model_improvement_log": self.model_improvement_log,
                "ewma_score": self._ewma_score,
                "dimension_trends": dict(self._dimension_trends),
                "tuned_parameters": tuned_parameters,
            }
            raw_path = self.config.get("learning_data_file", "learning_data.json")
            file_path = self._resolve_learning_data_path(raw_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, default=str)
            tmp_path.replace(file_path)
            self._save_dirty = False
        except Exception as exc:
            self.logger.error("保存学习数据失败: %s", exc)

    def _load_learning_data(self) -> None:
        raw_path = self.config.get("learning_data_file", "learning_data.json")
        file_path = self._resolve_learning_data_path(raw_path)

        # 优先加载 JSON；若不存在则尝试同名 .pkl 迁移
        if not file_path.exists():
            pkl_path = file_path.with_suffix(".pkl")
            if pkl_path.exists():
                self._migrate_pickle_to_json(pkl_path, file_path)
                return
            self.logger.info("未找到学习数据文件，将创建新的学习记录")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_loaded_data(data)
        except Exception as exc:
            self.logger.error("加载学习数据失败: %s", exc)

    def _migrate_pickle_to_json(self, pkl_path: Path, json_path: Path) -> None:
        """将旧版 pickle 文件一次性迁移为 JSON，然后标记脏写。"""
        import pickle as _pickle  # noqa: S403 — 仅用于一次性迁移

        try:
            with open(pkl_path, "rb") as f:
                data = _pickle.load(f)  # noqa: S301
            self._apply_loaded_data(data)
            self.logger.info("从 pickle 迁移了 %d 条学习记录", len(self.learning_records))
            self._save_dirty = True
            self._save_learning_data()
        except Exception as exc:
            self.logger.error("pickle 迁移失败: %s", exc)

    def _apply_loaded_data(self, data: Dict[str, Any]) -> None:
        self.learning_records = [
            LearningRecord.from_dict(item) for item in data.get("records", [])
        ]
        self.performance_history = list(data.get("performance_history", []))
        self.model_improvement_log = list(data.get("model_improvement_log", []))
        self._ewma_score = data.get("ewma_score")
        self._dimension_trends = data.get("dimension_trends", {})
        self._persisted_tuned_parameters = dict(data.get("tuned_parameters", {}))
        self._apply_threshold_overrides(self._persisted_tuned_parameters)
        self._cap_improvement_log()
        self.logger.info("加载了 %d 条学习记录", len(self.learning_records))

    @staticmethod
    def _resolve_learning_data_path(raw_path: str) -> Path:
        """将配置路径解析为绝对 Path，扩展名统一为 .json。"""
        p = Path(raw_path).expanduser()
        if p.suffix == ".pkl":
            p = p.with_suffix(".json")
        return p

    def _cap_improvement_log(self) -> None:
        if len(self.model_improvement_log) > self._MAX_IMPROVEMENT_LOG:
            self.model_improvement_log = self.model_improvement_log[-self._MAX_IMPROVEMENT_LOG:]

    def _do_cleanup(self) -> bool:
        try:
            if self._save_dirty:
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
