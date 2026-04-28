"""学习策略策策调节器 — 将 reflect 产出的质量信号转化为可执行的策略调整。

PolicyAdjuster 消费 LearningLoopOrchestrator 传来的 cycle_assessment 和
improvement_plan，生成针对：
- evidence_policy（最小置信度、最小证据等级、声称支撑阈值）
- phase_thresholds（阶段级参数微调）
- template_preferences（推理框架偏好权重）

的具体调整建议，并维护策略版本历史（rolling window）。

用法::

    adjuster = PolicyAdjuster()
    adjustment = adjuster.adjust(
        cycle_assessment=cycle_assessment,
        improvement_plan=improvement_plan,
        current_tuned_parameters=tuned_params,
    )
    active_policy = adjuster.get_active_policy()
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timezone
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 常量 ─────────────────────────────────────────────────────────────────
_MAX_POLICY_HISTORY = 50
_EVIDENCE_GRADES = ("high", "moderate", "low", "very_low")

# 默认 evidence policy
_DEFAULT_EVIDENCE_POLICY: Dict[str, Any] = {
    "min_confidence": 0.60,
    "min_evidence_grade": "low",
    "claim_support_threshold": 1,
    "auto_accept_grades": ["high"],
    "max_evidence_records": None,
}

# 默认 template preferences
_DEFAULT_TEMPLATE_PREFERENCES: Dict[str, float] = {
    "analytical": 0.5,
    "dialectical": 0.5,
    "comparative": 0.5,
    "evidential": 0.5,
}

# 阈值调整步长
_CONFIDENCE_STEP = 0.03
_CONFIDENCE_BOUNDS = (0.30, 0.95)


@dataclass
class PolicyVersion:
    """单次策略快照。"""

    version_id: str
    timestamp: str
    evidence_policy: Dict[str, Any]
    phase_thresholds: Dict[str, float]
    template_preferences: Dict[str, float]
    trigger: str  # "reflect" | "manual" | "initial"
    cycle_score: Optional[float] = None
    adjustment_summary: str = ""


@dataclass
class PolicyAdjustment:
    """单次调整结果。"""

    evidence_policy: Dict[str, Any]
    phase_thresholds: Dict[str, float]
    template_preferences: Dict[str, float]
    changes: List[Dict[str, Any]] = field(default_factory=list)
    rationale: str = ""


class PolicyAdjuster:
    """将 reflect 产出转化为策略调整并维护版本历史。

    线程安全：所有可变状态通过 RLock 保护。
    """

    def __init__(
        self,
        initial_evidence_policy: Optional[Dict[str, Any]] = None,
        initial_template_preferences: Optional[Dict[str, float]] = None,
        *,
        adaptive_tuner: Optional[Any] = None,
        adaptive_tuner_specs: Optional[Dict[str, Dict[str, Any]]] = None,
        performance_target: float = 0.80,
    ) -> None:
        self._lock = threading.RLock()
        self._evidence_policy = dict(initial_evidence_policy or _DEFAULT_EVIDENCE_POLICY)
        self._phase_thresholds: Dict[str, float] = {}
        self._template_preferences = dict(initial_template_preferences or _DEFAULT_TEMPLATE_PREFERENCES)
        self._history: Deque[PolicyVersion] = deque(maxlen=_MAX_POLICY_HISTORY)
        self._version_counter = 0

        # T5.6: PolicyAdjuster 现在拥有调参子模块（前 SelfLearningEngine 的职责）
        self._adaptive_tuner = adaptive_tuner
        self._tuner_specs = adaptive_tuner_specs
        self._tuner_target = float(performance_target)

        # 记录初始版本
        self._record_version("initial", cycle_score=None, summary="初始化")

    # ── T5.6: AdaptiveTuner 接口（前 SelfLearningEngine 调参职责） ──────────

    def _ensure_tuner(self) -> Optional[Any]:
        if self._adaptive_tuner is not None:
            return self._adaptive_tuner
        try:
            from src.learning.policy_adjuster_internals.adaptive_tuner import (
                AdaptiveTuner,
            )
        except Exception:  # pragma: no cover
            return None
        try:
            self._adaptive_tuner = AdaptiveTuner(
                specs=self._tuner_specs,
                performance_target=self._tuner_target,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("AdaptiveTuner 初始化失败: %s", exc)
            self._adaptive_tuner = None
        return self._adaptive_tuner

    def tune(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """喂入一轮性能指标，返回最新参数快照。"""
        with self._lock:
            tuner = self._ensure_tuner()
            if tuner is None:
                return {}
            try:
                return dict(tuner.step(dict(metrics)))
            except Exception as exc:
                logger.warning("PolicyAdjuster.tune 失败: %s", exc)
                return self.current_tuned_parameters()

    def current_tuned_parameters(self) -> Dict[str, float]:
        """返回 AdaptiveTuner 当前参数快照。"""
        with self._lock:
            tuner = self._adaptive_tuner
            if tuner is None:
                return {}
            try:
                return dict(tuner.current_values())
            except Exception:  # pragma: no cover
                return {}

    def set_tuned_parameter(self, name: str, value: float) -> None:
        with self._lock:
            tuner = self._ensure_tuner()
            if tuner is None:
                return
            try:
                tuner.set_parameter(name, float(value))
            except Exception as exc:  # pragma: no cover
                logger.warning("set_tuned_parameter(%s) 失败: %s", name, exc)

    # ── 核心 API ─────────────────────────────────────────────────────────

    def adjust(
        self,
        *,
        cycle_assessment: Dict[str, Any],
        improvement_plan: List[Dict[str, Any]],
        current_tuned_parameters: Optional[Dict[str, float]] = None,
    ) -> PolicyAdjustment:
        """根据 reflect 产出调整策略，返回本次调整摘要。

        Parameters
        ----------
        cycle_assessment :
            QualityAssessor 产出的质量评估（含 overall_score, dimensions, weak_phases）。
        improvement_plan :
            Reflect 阶段产出的改进建议列表。
        current_tuned_parameters :
            AdaptiveTuner 最新输出（可选，用于同步 phase_thresholds）。
        """
        with self._lock:
            changes: List[Dict[str, Any]] = []
            overall_score = self._extract_score(cycle_assessment)

            # 1. 调整 evidence policy
            evidence_changes = self._adjust_evidence_policy(overall_score, cycle_assessment, improvement_plan)
            changes.extend(evidence_changes)

            # 2. 同步 phase_thresholds
            if current_tuned_parameters:
                threshold_changes = self._sync_phase_thresholds(current_tuned_parameters)
                changes.extend(threshold_changes)

            # 3. 调整 template preferences
            template_changes = self._adjust_template_preferences(cycle_assessment, improvement_plan)
            changes.extend(template_changes)

            # 4. 记录版本
            rationale = self._build_rationale(overall_score, changes)
            self._record_version("reflect", cycle_score=overall_score, summary=rationale)

            return PolicyAdjustment(
                evidence_policy=dict(self._evidence_policy),
                phase_thresholds=dict(self._phase_thresholds),
                template_preferences=dict(self._template_preferences),
                changes=changes,
                rationale=rationale,
            )

    def get_active_policy(self) -> Dict[str, Any]:
        """返回当前活跃策略。"""
        with self._lock:
            return {
                "evidence_policy": dict(self._evidence_policy),
                "phase_thresholds": dict(self._phase_thresholds),
                "template_preferences": dict(self._template_preferences),
                "version_id": self._current_version_id(),
            }

    # ------------------------------------------------------------------
    # Phase I-3：消费 SmallModel benchmark summary，回灌策略调整。
    # ------------------------------------------------------------------

    def apply_benchmark_summary(
        self,
        benchmark_summary: Dict[str, Any],
        *,
        max_template_delta: float = 0.2,
        max_threshold_delta: float = 0.2,
    ) -> PolicyAdjustment:
        """根据 benchmark report 中的 ``learning_recommendations`` 调整模板偏好与阶段阈值。

        Parameters
        ----------
        benchmark_summary :
            ``run_phase_benchmark`` 输出的 dict，需包含 ``learning_recommendations``。
        max_template_delta :
            单次调用 ``template_preferences[name]`` 最大累计调整量。
        max_threshold_delta :
            单次调用 ``phase_thresholds[key]`` 最大累计调整量。
        """
        with self._lock:
            recommendations = (benchmark_summary or {}).get("learning_recommendations") or {}
            template_adjustments = (recommendations.get("template_preference_adjustments") or {})
            phase_threshold_adjustments = (recommendations.get("phase_threshold_adjustments") or {})

            changes: List[Dict[str, Any]] = []

            for framework_name, raw_delta in template_adjustments.items():
                try:
                    delta = float(raw_delta)
                except (TypeError, ValueError):
                    continue
                if delta == 0.0:
                    continue
                bounded_delta = max(-max_template_delta, min(max_template_delta, delta))
                old_val = self._template_preferences.get(str(framework_name), 0.5)
                new_val = max(0.0, min(1.0, old_val + bounded_delta))
                if new_val == old_val:
                    continue
                self._template_preferences[str(framework_name)] = round(new_val, 4)
                changes.append({
                    "field": f"template_preferences.{framework_name}",
                    "old": old_val,
                    "new": new_val,
                    "direction": "strengthen" if bounded_delta > 0 else "weaken",
                    "source": "benchmark",
                })

            for phase_name, threshold_payload in phase_threshold_adjustments.items():
                if not isinstance(threshold_payload, dict):
                    continue
                for key, raw_delta in threshold_payload.items():
                    try:
                        delta = float(raw_delta)
                    except (TypeError, ValueError):
                        continue
                    if delta == 0.0:
                        continue
                    bounded_delta = max(-max_threshold_delta, min(max_threshold_delta, delta))
                    threshold_key = f"{phase_name}.{key}"
                    old_val = float(self._phase_thresholds.get(threshold_key, 0.0))
                    new_val = round(old_val + bounded_delta, 4)
                    self._phase_thresholds[threshold_key] = new_val
                    changes.append({
                        "field": f"phase_thresholds.{threshold_key}",
                        "old": old_val,
                        "new": new_val,
                        "direction": "strengthen" if bounded_delta > 0 else "weaken",
                        "source": "benchmark",
                    })

            global_summary = (benchmark_summary or {}).get("global_summary") or {}
            quality_score = global_summary.get("average_quality_score")
            try:
                quality_score_f = float(quality_score) if quality_score is not None else None
            except (TypeError, ValueError):
                quality_score_f = None

            rationale = (
                f"benchmark template_default_hit_rate="
                f"{float(global_summary.get('template_default_hit_rate', 0.0)):.2f}, "
                f"budget_proceed_hit_rate="
                f"{float(global_summary.get('budget_proceed_hit_rate', 0.0)):.2f}, "
                f"layer_top_hit_rate="
                f"{float(global_summary.get('layer_top_hit_rate', 0.0)):.2f}, "
                f"changes={len(changes)}"
            )

            self._record_version("benchmark", cycle_score=quality_score_f, summary=rationale)

            return PolicyAdjustment(
                evidence_policy=dict(self._evidence_policy),
                phase_thresholds=dict(self._phase_thresholds),
                template_preferences=dict(self._template_preferences),
                changes=changes,
                rationale=rationale,
            )

    def get_policy_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """返回最近 N 个版本记录。"""
        with self._lock:
            items = list(self._history)[-limit:]
            return [
                {
                    "version_id": v.version_id,
                    "timestamp": v.timestamp,
                    "trigger": v.trigger,
                    "cycle_score": v.cycle_score,
                    "adjustment_summary": v.adjustment_summary,
                }
                for v in items
            ]

    def get_evidence_policy(self) -> Dict[str, Any]:
        """返回当前 evidence policy（只读副本）。"""
        with self._lock:
            return dict(self._evidence_policy)

    @property
    def version_count(self) -> int:
        with self._lock:
            return self._version_counter

    # ── 内部调整逻辑 ──────────────────────────────────────────────────────

    def _adjust_evidence_policy(
        self,
        overall_score: float,
        cycle_assessment: Dict[str, Any],
        improvement_plan: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """根据质量趋势调整证据准入标准。

        规则：
        - 高分 (>= 0.85) → 收紧（提升 min_confidence、提升 min_grade）
        - 中分 (0.65-0.85) → 保持
        - 低分 (< 0.65) → 放松（降低 min_confidence、降低 min_grade）
        - 如果 improvement_plan 提及 evidence 质量 → 额外收紧
        """
        changes: List[Dict[str, Any]] = []
        old_confidence = self._evidence_policy.get("min_confidence", 0.60)
        old_grade = self._evidence_policy.get("min_evidence_grade", "low")

        # 分数驱动的方向
        if overall_score >= 0.85:
            direction = +1  # 收紧
        elif overall_score < 0.65:
            direction = -1  # 放松
        else:
            direction = 0

        # improvement_plan 信号检测
        evidence_mentioned = any(
            "evidence" in str(item).lower() or "证据" in str(item)
            for item in improvement_plan
        )
        if evidence_mentioned and direction >= 0:
            direction = max(direction, 1)

        # 调整 min_confidence
        if direction != 0:
            new_confidence = old_confidence + direction * _CONFIDENCE_STEP
            new_confidence = max(_CONFIDENCE_BOUNDS[0], min(_CONFIDENCE_BOUNDS[1], new_confidence))
            if new_confidence != old_confidence:
                self._evidence_policy["min_confidence"] = round(new_confidence, 4)
                changes.append({
                    "field": "evidence_policy.min_confidence",
                    "old": old_confidence,
                    "new": new_confidence,
                    "direction": "tighten" if direction > 0 else "loosen",
                })

        # 调整 min_evidence_grade
        grade_idx = _EVIDENCE_GRADES.index(old_grade) if old_grade in _EVIDENCE_GRADES else 2
        if direction > 0 and grade_idx > 0:
            new_grade = _EVIDENCE_GRADES[grade_idx - 1]
            self._evidence_policy["min_evidence_grade"] = new_grade
            changes.append({
                "field": "evidence_policy.min_evidence_grade",
                "old": old_grade,
                "new": new_grade,
                "direction": "tighten",
            })
        elif direction < 0 and grade_idx < len(_EVIDENCE_GRADES) - 1:
            new_grade = _EVIDENCE_GRADES[grade_idx + 1]
            self._evidence_policy["min_evidence_grade"] = new_grade
            changes.append({
                "field": "evidence_policy.min_evidence_grade",
                "old": old_grade,
                "new": new_grade,
                "direction": "loosen",
            })

        return changes

    def _sync_phase_thresholds(self, tuned_parameters: Dict[str, float]) -> List[Dict[str, Any]]:
        """将 AdaptiveTuner 输出同步为 phase_thresholds。"""
        changes: List[Dict[str, Any]] = []
        for key, value in tuned_parameters.items():
            if not isinstance(value, (int, float)):
                continue
            old = self._phase_thresholds.get(key)
            if old != value:
                changes.append({
                    "field": f"phase_thresholds.{key}",
                    "old": old,
                    "new": value,
                    "direction": "sync",
                })
                self._phase_thresholds[key] = float(value)
        return changes

    def _adjust_template_preferences(
        self,
        cycle_assessment: Dict[str, Any],
        improvement_plan: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """基于质量维度表现调整推理框架偏好。

        规则：
        - 如果 'analytical' 维度评分高 → 增加 analytical 偏好权重
        - 如果 improvement_plan 建议更多对比 → 增加 comparative
        - 使用温和步长 (0.05)，归一化到 [0.0, 1.0]
        """
        changes: List[Dict[str, Any]] = []
        dimensions = cycle_assessment.get("dimensions", {})
        step = 0.05

        # 维度名 → 模板偏好映射
        dimension_map = {
            "analytical_depth": "analytical",
            "evidence_quality": "evidential",
            "logical_coherence": "dialectical",
            "comprehensiveness": "comparative",
        }

        for dim_name, template_key in dimension_map.items():
            if template_key not in self._template_preferences:
                continue
            dim_score = dimensions.get(dim_name)
            if dim_score is None:
                continue
            # 维度高分 → 强化该模板偏好；低分 → 削弱
            if isinstance(dim_score, (int, float)):
                if dim_score >= 0.8:
                    delta = step
                elif dim_score < 0.5:
                    delta = -step
                else:
                    continue
                old_val = self._template_preferences[template_key]
                new_val = max(0.0, min(1.0, old_val + delta))
                if new_val != old_val:
                    self._template_preferences[template_key] = round(new_val, 4)
                    changes.append({
                        "field": f"template_preferences.{template_key}",
                        "old": old_val,
                        "new": new_val,
                        "direction": "strengthen" if delta > 0 else "weaken",
                    })

        return changes

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _extract_score(self, cycle_assessment: Dict[str, Any]) -> float:
        """从 cycle_assessment 中提取 overall_score。"""
        score = cycle_assessment.get("overall_score")
        if score is None:
            score = cycle_assessment.get("score", 0.0)
        try:
            return float(score)
        except (TypeError, ValueError):
            return 0.0

    def _current_version_id(self) -> str:
        """生成当前版本 ID。"""
        content = f"{self._evidence_policy}{self._phase_thresholds}{self._template_preferences}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def _record_version(self, trigger: str, cycle_score: Optional[float], summary: str) -> None:
        """记录一个策略版本快照。"""
        self._version_counter += 1
        version = PolicyVersion(
            version_id=self._current_version_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            evidence_policy=dict(self._evidence_policy),
            phase_thresholds=dict(self._phase_thresholds),
            template_preferences=dict(self._template_preferences),
            trigger=trigger,
            cycle_score=cycle_score,
            adjustment_summary=summary,
        )
        self._history.append(version)

    def _build_rationale(self, overall_score: float, changes: List[Dict[str, Any]]) -> str:
        """构建调整理由摘要。"""
        if not changes:
            return f"cycle_score={overall_score:.2f}，无调整"
        directions = set(c.get("direction", "") for c in changes)
        return f"cycle_score={overall_score:.2f}，{len(changes)} 项调整（{', '.join(directions)}）"
