"""LearningLoopOrchestrator — 学习闭环编排器。

将分散在 ResearchPipeline / ReflectPhase / PhaseOrchestrator /
ResearchRuntimeService 中的学习闭环逻辑集中到一个无状态协调层。

典型生命周期::

    llo = LearningLoopOrchestrator()

    # ① 循环开始前：冻结快照，提取策略
    prep = llo.prepare_cycle(pipeline)
    strategy = prep["learning_strategy"]
    feedback = prep["previous_iteration_feedback"]

    # ② 每个阶段执行前：注入学习上下文
    phase_ctx = llo.inject_phase_context(base_context, strategy, feedback)

    # ③ 每个阶段执行后：登记学习清单
    llo.record_phase_learning(manifest)

    # ④ Reflect 阶段完成后：驱动 SelfLearningEngine 学习
    reflect_result = llo.execute_reflect_learning(pipeline, cycle_assessment)

    # ⑤ 循环结束：生成汇总 + 下一轮策略
    summary = llo.build_cycle_summary(pipeline)
    next_strategy = llo.prepare_next_cycle_strategy(pipeline)
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.learning.policy_adjuster import PolicyAdjuster
from src.research.learning_strategy import (
    build_strategy_diff,
    build_strategy_snapshot,
)

logger = logging.getLogger(__name__)


class LearningLoopOrchestrator:
    """集中协调单个研究循环内的学习闭环生命周期。

    本类不持有 pipeline 引用——每个方法显式接收所需依赖，
    使其可以在不同 pipeline 实例间复用。
    """

    def __init__(self) -> None:
        self._snapshot_before: Dict[str, Any] = {}
        self._phase_manifests: List[Dict[str, Any]] = []
        self._reflect_learning_result: Optional[Dict[str, Any]] = None
        self._policy_adjuster = PolicyAdjuster()

    @property
    def policy_adjuster(self) -> PolicyAdjuster:
        """暴露 PolicyAdjuster 供外部查询策略历史。"""
        return self._policy_adjuster

    # ------------------------------------------------------------------
    # Phase I-3：消费 SmallModel benchmark summary，回灌策略调整。
    # ------------------------------------------------------------------

    def consume_benchmark_summary(self, benchmark_summary: Dict[str, Any]) -> Dict[str, Any]:
        """将 SmallModel benchmark 报告中的命中率回灌至 PolicyAdjuster。

        Returns
        -------
        dict
            ``policy_adjustment``：本次调整摘要（changes/rationale）。
            ``learning_recommendations``：原始建议（拷贝），便于 UI 与日志展示。
        """
        if not isinstance(benchmark_summary, dict) or not benchmark_summary:
            return {
                "policy_adjustment": None,
                "learning_recommendations": {},
                "applied": False,
            }

        adjustment = self._policy_adjuster.apply_benchmark_summary(benchmark_summary)
        recommendations = deepcopy(benchmark_summary.get("learning_recommendations") or {})
        return {
            "policy_adjustment": {
                "evidence_policy": adjustment.evidence_policy,
                "phase_thresholds": adjustment.phase_thresholds,
                "template_preferences": adjustment.template_preferences,
                "changes": adjustment.changes,
                "rationale": adjustment.rationale,
            },
            "learning_recommendations": recommendations,
            "applied": True,
        }

    # ------------------------------------------------------------------
    # ① prepare_cycle — 在循环第一个阶段执行前调用
    # ------------------------------------------------------------------

    def prepare_cycle(self, pipeline: Any) -> Dict[str, Any]:
        """冻结当前策略快照，提取学习策略和上一轮反馈。

        返回 dict 包含:
          - snapshot: 策略快照（含 fingerprint）
          - learning_strategy: 当前学习策略
          - previous_iteration_feedback: 上一轮反馈
        """
        self._phase_manifests = []
        self._reflect_learning_result = None

        # 冻结策略快照
        freeze = getattr(pipeline, "freeze_learning_strategy_snapshot", None)
        if callable(freeze):
            try:
                self._snapshot_before = freeze()
            except Exception as exc:
                logger.warning("冻结学习策略快照失败: %s", exc)
                self._snapshot_before = {}
        else:
            self._snapshot_before = build_strategy_snapshot(None, getattr(pipeline, "config", None))

        # 提取学习策略
        learning_strategy = self._extract_learning_strategy(pipeline)

        # 提取上一轮反馈
        previous_iteration_feedback = self._extract_previous_iteration_feedback(pipeline)

        return {
            "snapshot": dict(self._snapshot_before),
            "learning_strategy": learning_strategy,
            "previous_iteration_feedback": previous_iteration_feedback,
        }

    # ------------------------------------------------------------------
    # ② inject_phase_context — 为每个阶段注入学习上下文
    # ------------------------------------------------------------------

    @staticmethod
    def inject_phase_context(
        phase_context: Dict[str, Any],
        learning_strategy: Optional[Dict[str, Any]] = None,
        previous_iteration_feedback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """将学习策略和上轮反馈合并到阶段上下文中（不覆盖已有值）。"""
        ctx = dict(phase_context)
        if isinstance(learning_strategy, dict) and learning_strategy:
            ctx.setdefault("learning_strategy", deepcopy(learning_strategy))
        if isinstance(previous_iteration_feedback, dict) and previous_iteration_feedback:
            ctx.setdefault("previous_iteration_feedback", deepcopy(previous_iteration_feedback))
        return ctx

    # ------------------------------------------------------------------
    # ③ record_phase_learning — 登记每个阶段的学习清单
    # ------------------------------------------------------------------

    def record_phase_learning(self, manifest: Dict[str, Any]) -> None:
        """记录一个阶段的学习元数据（来自 StrategyApplicationTracker.to_metadata()）。"""
        if isinstance(manifest, dict):
            self._phase_manifests.append(manifest)

    # ------------------------------------------------------------------
    # ④ execute_reflect_learning — Reflect 完成后驱动学习引擎
    # ------------------------------------------------------------------

    def execute_reflect_learning(
        self,
        pipeline: Any,
        cycle_assessment: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将 cycle_assessment 反馈给 SelfLearningEngine，计算策略 diff。

        返回 dict 包含:
          - learning_summary: SelfLearningEngine.learn_from_cycle_reflection 结果
          - snapshot_before / snapshot_after: 策略快照
          - strategy_diff: 策略变化
          - fed: bool 是否成功反馈
        """
        learning_summary = self._feed_self_learning(pipeline, cycle_assessment)
        fed = learning_summary is not None

        # 刷新 pipeline 内部学习策略缓存
        refresh = getattr(pipeline, "refresh_learning_runtime_feedback", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:
                logger.warning("刷新学习策略快照失败: %s", exc)

        snapshot_after = build_strategy_snapshot(None, getattr(pipeline, "config", None))
        strategy_diff = (
            build_strategy_diff(self._snapshot_before, snapshot_after)
            if self._snapshot_before
            else {}
        )

        # ⑤ 根据 reflect 产出调整策略（evidence_policy / template_preferences）
        improvement_plan = cycle_assessment.get("improvement_plan", [])
        tuned_parameters = (
            learning_summary.get("tuned_parameters") if learning_summary else None
        )
        policy_adjustment = self._policy_adjuster.adjust(
            cycle_assessment=cycle_assessment,
            improvement_plan=improvement_plan,
            current_tuned_parameters=tuned_parameters,
        )

        self._reflect_learning_result = {
            "learning_summary": learning_summary,
            "snapshot_before": dict(self._snapshot_before),
            "snapshot_after": snapshot_after,
            "strategy_diff": strategy_diff,
            "policy_adjustment": {
                "evidence_policy": policy_adjustment.evidence_policy,
                "phase_thresholds": policy_adjustment.phase_thresholds,
                "template_preferences": policy_adjustment.template_preferences,
                "changes": policy_adjustment.changes,
                "rationale": policy_adjustment.rationale,
            },
            "fed": fed,
        }
        return dict(self._reflect_learning_result)

    # ------------------------------------------------------------------
    # ⑤ build_cycle_summary — 汇总本循环所有阶段的学习应用
    # ------------------------------------------------------------------

    def build_cycle_summary(self, pipeline: Any) -> Dict[str, Any]:
        """汇总所有阶段的学习应用清单，附加 reflect 结果。

        如果 pipeline 上有 build_learning_application_summary 方法则优先使用，
        否则从本地 _phase_manifests 构建。
        """
        builder = getattr(pipeline, "build_learning_application_summary", None)
        if callable(builder):
            try:
                base_summary = builder()
            except Exception:
                base_summary = self._build_local_summary()
        else:
            base_summary = self._build_local_summary()

        # 附加 reflect 学习结果
        if self._reflect_learning_result:
            base_summary["reflect_learning"] = {
                "fed": self._reflect_learning_result.get("fed", False),
                "strategy_changed": bool(
                    (self._reflect_learning_result.get("strategy_diff") or {}).get("changed")
                ),
                "change_count": (
                    (self._reflect_learning_result.get("strategy_diff") or {}).get("change_count", 0)
                ),
            }

        return base_summary

    # ------------------------------------------------------------------
    # ⑥ prepare_next_cycle_strategy — 准备下一轮的策略上下文
    # ------------------------------------------------------------------

    def prepare_next_cycle_strategy(self, pipeline: Any) -> Dict[str, Any]:
        """刷新 pipeline 学习状态，返回可用于下一轮 inject_phase_context 的策略。

        返回 dict 包含:
          - learning_strategy: 更新后的学习策略
          - previous_iteration_feedback: 更新后的反馈
        """
        refresh = getattr(pipeline, "refresh_learning_runtime_feedback", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:
                logger.warning("准备下一轮策略失败: %s", exc)

        result = {
            "learning_strategy": self._extract_learning_strategy(pipeline),
            "previous_iteration_feedback": self._extract_previous_iteration_feedback(pipeline),
            "evidence_policy": self._policy_adjuster.get_evidence_policy(),
            "template_preferences": self._policy_adjuster.get_active_policy().get("template_preferences", {}),
        }
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_learning_strategy(pipeline: Any) -> Dict[str, Any]:
        getter = getattr(pipeline, "get_learning_strategy", None)
        if callable(getter):
            try:
                strategy = getter()
                if isinstance(strategy, dict):
                    return dict(strategy)
            except Exception as exc:
                logger.warning("提取学习策略失败: %s", exc)

        config = getattr(pipeline, "config", None)
        if isinstance(config, dict) and isinstance(config.get("learning_strategy"), dict):
            return dict(config["learning_strategy"])
        return {}

    @staticmethod
    def _extract_previous_iteration_feedback(pipeline: Any) -> Dict[str, Any]:
        getter = getattr(pipeline, "get_previous_iteration_feedback", None)
        if callable(getter):
            try:
                feedback = getter()
                if isinstance(feedback, dict):
                    return dict(feedback)
            except Exception as exc:
                logger.warning("提取上一轮反馈失败: %s", exc)

        config = getattr(pipeline, "config", None)
        if isinstance(config, dict) and isinstance(config.get("previous_iteration_feedback"), dict):
            return dict(config["previous_iteration_feedback"])
        return {}

    @staticmethod
    def _feed_self_learning(pipeline: Any, cycle_assessment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        config = getattr(pipeline, "config", None)
        if not isinstance(config, dict):
            return None
        engine = config.get("self_learning_engine")
        if engine is None:
            return None
        learn = getattr(engine, "learn_from_cycle_reflection", None)
        if not callable(learn):
            return None
        try:
            return learn(cycle_assessment)
        except Exception as exc:
            logger.warning("SelfLearningEngine 反馈失败: %s", exc)
            return None

    def _build_local_summary(self) -> Dict[str, Any]:
        phases_applied = [m for m in self._phase_manifests if m.get("applied")]
        total_decisions = sum(m.get("decision_count", 0) for m in phases_applied)
        fingerprints = {
            m.get("strategy_fingerprint")
            for m in phases_applied
            if m.get("strategy_fingerprint")
        }
        return {
            "snapshot_fingerprint": self._snapshot_before.get("fingerprint"),
            "phases_with_strategy": [m.get("phase") for m in phases_applied],
            "phase_count": len(phases_applied),
            "total_decision_count": total_decisions,
            "cross_phase_consistent": len(fingerprints) <= 1,
            "distinct_fingerprints": sorted(fingerprints),
            "phase_manifests": list(self._phase_manifests),
        }
