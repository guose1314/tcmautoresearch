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
from typing import Any, Dict, List, Mapping, Optional

from src.learning.policy_adjuster import PolicyAdjuster
from src.research.learning_strategy import (
    build_strategy_diff,
    build_strategy_snapshot,
)

try:  # T5.2: 可选 LFITL 包依赖，保证老调用者仍可走
    from src.contexts.lfitl import (
        FeedbackTranslator as _LFITLTranslator,
    )
    from src.contexts.lfitl import (
        GraphWeightUpdater as _LFITLGraphWeightUpdater,
    )
    from src.contexts.lfitl import (
        PromptBiasCompiler as _LFITLPromptBiasCompiler,
    )
except Exception:  # noqa: BLE001
    _LFITLTranslator = None  # type: ignore[assignment]
    _LFITLGraphWeightUpdater = None  # type: ignore[assignment]
    _LFITLPromptBiasCompiler = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class LearningLoopOrchestrator:
    """集中协调单个研究循环内的学习闭环生命周期。

    本类不持有 pipeline 引用——每个方法显式接收所需依赖，
    使其可以在不同 pipeline 实例间复用。
    """

    def __init__(
        self,
        *,
        feedback_repo: Optional[Any] = None,
        lfitl_translator: Optional[Any] = None,
        prompt_bias_compiler: Optional[Any] = None,
        graph_weight_updater: Optional[Any] = None,
        learning_insight_repo: Optional[Any] = None,
        recent_feedback_limit: int = 20,
        learning_insight_limit: int = 100,
        learning_insight_min_confidence: float = 0.0,
        apply_graph_weights: bool = False,
    ) -> None:
        self._snapshot_before: Dict[str, Any] = {}
        self._phase_manifests: List[Dict[str, Any]] = []
        self._reflect_learning_result: Optional[Dict[str, Any]] = None
        self._policy_adjuster = PolicyAdjuster()

        # ---- T5.2: LFITL 接入位 ----
        self._feedback_repo = feedback_repo
        if lfitl_translator is None and _LFITLTranslator is not None:
            lfitl_translator = _LFITLTranslator()
        if prompt_bias_compiler is None and _LFITLPromptBiasCompiler is not None:
            prompt_bias_compiler = _LFITLPromptBiasCompiler()
        self._lfitl_translator = lfitl_translator
        self._prompt_bias_compiler = prompt_bias_compiler
        self._graph_weight_updater = graph_weight_updater
        self._learning_insight_repo = learning_insight_repo
        self._recent_feedback_limit = int(recent_feedback_limit)
        self._learning_insight_limit = int(learning_insight_limit)
        self._learning_insight_min_confidence = float(
            learning_insight_min_confidence or 0.0
        )
        self._apply_graph_weights = bool(apply_graph_weights)
        self._last_lfitl_plan: Optional[Dict[str, Any]] = None
        self._last_learning_insight_plan: Optional[Dict[str, Any]] = None
        self._last_prompt_bias_blocks: Dict[str, Dict[str, Any]] = {}

    @property
    def policy_adjuster(self) -> PolicyAdjuster:
        """暴露 PolicyAdjuster 供外部查询策略历史。"""
        return self._policy_adjuster

    # ------------------------------------------------------------------
    # Phase I-3：消费 SmallModel benchmark summary，回灌策略调整。
    # ------------------------------------------------------------------

    def consume_benchmark_summary(
        self, benchmark_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
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
        recommendations = deepcopy(
            benchmark_summary.get("learning_recommendations") or {}
        )
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
            self._snapshot_before = build_strategy_snapshot(
                None, getattr(pipeline, "config", None)
            )

        # 提取学习策略
        learning_strategy = self._extract_learning_strategy(pipeline)

        # 提取上一轮反馈
        previous_iteration_feedback = self._extract_previous_iteration_feedback(
            pipeline
        )

        # ---- T5.2: 从 feedback_repo 拉取近期反馈，生成 LFITL plan ----
        lfitl_plan_dict, prompt_bias_blocks = self._build_lfitl_plan(pipeline)
        learning_insight_plan_dict, learning_insight_blocks = (
            self._build_learning_insight_prompt_bias(pipeline)
        )
        prompt_bias_blocks = self._merge_prompt_bias_blocks(
            prompt_bias_blocks,
            learning_insight_blocks,
        )
        self._last_lfitl_plan = lfitl_plan_dict
        self._last_learning_insight_plan = learning_insight_plan_dict
        self._last_prompt_bias_blocks = prompt_bias_blocks

        return {
            "snapshot": dict(self._snapshot_before),
            "learning_strategy": learning_strategy,
            "previous_iteration_feedback": previous_iteration_feedback,
            "lfitl_plan": lfitl_plan_dict,
            "learning_insight_plan": learning_insight_plan_dict,
            "prompt_bias_blocks": dict(prompt_bias_blocks),
        }

    # ------------------------------------------------------------------
    # ② inject_phase_context — 为每个阶段注入学习上下文
    # ------------------------------------------------------------------

    @staticmethod
    def inject_phase_context(
        phase_context: Dict[str, Any],
        learning_strategy: Optional[Dict[str, Any]] = None,
        previous_iteration_feedback: Optional[Dict[str, Any]] = None,
        prompt_bias_blocks: Optional[Dict[str, Dict[str, Any]]] = None,
        lfitl_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """将学习策略、上轮反馈与 LFITL 输出合并到阶段上下文（不覆盖已有值）。"""
        ctx = dict(phase_context)
        if isinstance(learning_strategy, dict) and learning_strategy:
            ctx.setdefault("learning_strategy", deepcopy(learning_strategy))
        if (
            isinstance(previous_iteration_feedback, dict)
            and previous_iteration_feedback
        ):
            ctx.setdefault(
                "previous_iteration_feedback", deepcopy(previous_iteration_feedback)
            )
        # T5.2: prompt_bias_blocks 供 SelfRefineRunner 调用侧 手动 inject 进 inputs
        if isinstance(prompt_bias_blocks, dict) and prompt_bias_blocks:
            ctx.setdefault("prompt_bias_blocks", deepcopy(prompt_bias_blocks))
        if isinstance(lfitl_plan, dict) and lfitl_plan:
            ctx.setdefault("lfitl_plan", deepcopy(lfitl_plan))
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

        snapshot_after = build_strategy_snapshot(
            None, getattr(pipeline, "config", None)
        )
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
                    (self._reflect_learning_result.get("strategy_diff") or {}).get(
                        "changed"
                    )
                ),
                "change_count": (
                    (self._reflect_learning_result.get("strategy_diff") or {}).get(
                        "change_count", 0
                    )
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
            "previous_iteration_feedback": self._extract_previous_iteration_feedback(
                pipeline
            ),
            "evidence_policy": self._policy_adjuster.get_evidence_policy(),
            "template_preferences": self._policy_adjuster.get_active_policy().get(
                "template_preferences", {}
            ),
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
        if isinstance(config, dict) and isinstance(
            config.get("learning_strategy"), dict
        ):
            return dict(config["learning_strategy"])
        return {}

    # ------------------------------------------------------------------
    # T5.2: LFITL plan 生成
    # ------------------------------------------------------------------
    def _build_lfitl_plan(
        self, pipeline: Any
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """从 feedback_repo 拉取最近 N 条反馈，跑 FeedbackTranslator。

        返回 ``(plan_dict_or_None, prompt_bias_blocks)``；任何缺件都安全降级为 ``(None, {})``。
        """
        repo = self._feedback_repo or self._extract_feedback_repo(pipeline)
        translator = self._lfitl_translator
        if repo is None or translator is None:
            return None, {}
        try:
            recent = self._load_recent_feedback(repo)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LFITL feedback_repo 读取失败: %s", exc)
            return None, {}
        if not recent:
            return {"summary": {"feedback_count": 0}}, {}
        prepared_recent = self._prepare_lfitl_feedback_records(recent)
        if not prepared_recent:
            return {"summary": {"feedback_count": 0}}, {}
        try:
            plan = translator.translate(prepared_recent)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LFITL translate 失败: %s", exc)
            return None, {}

        # 可选：把 graph_weight_actions 写回 Neo4j
        if self._apply_graph_weights and self._graph_weight_updater is not None:
            try:
                self._graph_weight_updater.apply(plan)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LFITL graph_weight_updater.apply 失败: %s", exc)

        # prompt_bias_blocks 供 phase 注入到 SelfRefineRunner.inputs
        bias_blocks: Dict[str, Dict[str, Any]] = {}
        if self._prompt_bias_compiler is not None:
            try:
                bias_blocks = self._prompt_bias_compiler.compile(plan)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LFITL prompt_bias_compiler.compile 失败: %s", exc)
                bias_blocks = {}

        return plan.to_dict(), bias_blocks

    def _load_recent_feedback(self, repo: Any) -> List[Any]:
        recent = getattr(repo, "recent", None)
        if callable(recent):
            return list(recent(limit=self._recent_feedback_limit) or [])

        list_learning_feedback = getattr(repo, "list_learning_feedback", None)
        if not callable(list_learning_feedback):
            return []
        page = list_learning_feedback(limit=self._recent_feedback_limit)
        if isinstance(page, Mapping):
            return list(page.get("items") or [])
        if isinstance(page, list):
            return page
        return []

    @classmethod
    def _prepare_lfitl_feedback_records(
        cls, records: List[Any]
    ) -> List[Dict[str, Any]]:
        prepared: List[Dict[str, Any]] = []
        for record in records or []:
            if not isinstance(record, Mapping):
                continue
            prepared_record = cls._coerce_lfitl_feedback_record(record)
            if prepared_record:
                prepared.append(prepared_record)
        return prepared

    @staticmethod
    def _coerce_lfitl_feedback_record(record: Mapping[str, Any]) -> Dict[str, Any]:
        item = dict(record)
        metadata = (
            item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        )
        details = (
            item.get("details") if isinstance(item.get("details"), Mapping) else {}
        )
        feedback_scope = (
            str(item.get("feedback_scope") or metadata.get("feedback_scope") or "")
            .strip()
            .lower()
        )
        target_phase = (
            str(
                item.get("target_phase")
                or metadata.get("target_phase")
                or details.get("target_phase")
                or ""
            )
            .strip()
            .lower()
        )
        if feedback_scope == "philology_review" and target_phase:
            item["source_phase"] = target_phase
        elif not str(item.get("source_phase") or "").strip() and target_phase:
            item["source_phase"] = target_phase

        issue_fields = (
            LearningLoopOrchestrator._extract_string_list(item.get("issue_fields"))
            or LearningLoopOrchestrator._extract_string_list(
                metadata.get("issue_fields")
            )
            or LearningLoopOrchestrator._extract_string_list(
                details.get("issue_fields")
            )
            or LearningLoopOrchestrator._extract_string_list(
                item.get("improvement_priorities")
            )
        )
        if issue_fields:
            item["issue_fields"] = issue_fields

        violations = (
            LearningLoopOrchestrator._extract_mapping_list(item.get("violations"))
            or LearningLoopOrchestrator._extract_mapping_list(
                metadata.get("violations")
            )
            or LearningLoopOrchestrator._extract_mapping_list(details.get("violations"))
        )
        if violations:
            item["violations"] = violations

        graph_targets = (
            LearningLoopOrchestrator._extract_string_list(item.get("graph_targets"))
            or LearningLoopOrchestrator._extract_string_list(
                metadata.get("graph_targets")
            )
            or LearningLoopOrchestrator._extract_string_list(
                details.get("graph_targets")
            )
        )
        if graph_targets:
            item["graph_targets"] = graph_targets

        severity = (
            str(item.get("severity") or metadata.get("severity") or "").strip().lower()
        )
        if not severity:
            severity = LearningLoopOrchestrator._severity_from_learning_feedback(item)
        if severity:
            item["severity"] = severity
        return item

    @staticmethod
    def _extract_string_list(value: Any) -> List[str]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, (list, tuple, set)):
            text = str(value or "").strip()
            return [text] if text else []
        items: List[str] = []
        for raw in value:
            text = str(raw or "").strip()
            if text and text not in items:
                items.append(text)
        return items

    @staticmethod
    def _extract_mapping_list(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _severity_from_learning_feedback(record: Mapping[str, Any]) -> str:
        grade = str(record.get("grade_level") or "").strip().upper()
        if grade in {"D", "VERY_LOW", "LOW"}:
            return "high"
        if grade in {"C", "MEDIUM"}:
            return "medium"
        status = str(record.get("feedback_status") or "").strip().lower()
        if status == "weakness":
            return "medium"
        return "low"

    def _build_learning_insight_prompt_bias(
        self,
        pipeline: Any,
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """Compile active LearningInsight rows into next-cycle prompt bias."""
        repo = self._learning_insight_repo or self._extract_learning_insight_repo(
            pipeline
        )
        compiler = self._prompt_bias_compiler
        if repo is None or compiler is None:
            return None, {}
        build_plan = getattr(compiler, "build_plan_from_learning_insights", None)
        if not callable(build_plan):
            return None, {}

        limit = self._resolve_learning_insight_limit(pipeline)
        min_confidence = self._resolve_learning_insight_min_confidence(pipeline)
        list_insights = getattr(repo, "list_prompt_bias_eligible", None)
        if not callable(list_insights):
            list_insights = getattr(repo, "list_active", None)
        if not callable(list_insights):
            return None, {}
        try:
            insights = list(list_insights(limit=limit))
        except TypeError:
            try:
                insights = list(list_insights())
            except Exception as exc:  # noqa: BLE001
                logger.warning("LearningInsight eligible list 失败: %s", exc)
                return None, {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("LearningInsight eligible list 失败: %s", exc)
            return None, {}

        try:
            plan = build_plan(insights, min_confidence=min_confidence)
            blocks = compiler.compile(plan)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LearningInsight prompt bias 编译失败: %s", exc)
            return None, {}
        return plan.to_dict(), blocks

    @staticmethod
    def _merge_prompt_bias_blocks(
        primary: Optional[Mapping[str, Mapping[str, Any]]],
        secondary: Optional[Mapping[str, Mapping[str, Any]]],
    ) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {
            str(phase): dict(block) for phase, block in (primary or {}).items()
        }
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        for phase, block in (secondary or {}).items():
            phase_key = str(phase)
            incoming = dict(block)
            if phase_key not in merged:
                merged[phase_key] = incoming
                continue
            current = merged[phase_key]
            current_text = str(current.get("bias_text") or "").strip()
            incoming_text = str(incoming.get("bias_text") or "").strip()
            if incoming_text and incoming_text not in current_text:
                current["bias_text"] = "\n".join(
                    item for item in (current_text, incoming_text) if item
                )
            avoid_fields: List[str] = []
            for item in list(current.get("avoid_fields") or []) + list(
                incoming.get("avoid_fields") or []
            ):
                text = str(item).strip()
                if text and text not in avoid_fields:
                    avoid_fields.append(text)
            current["avoid_fields"] = avoid_fields
            severities = [
                str(current.get("severity") or "medium"),
                str(incoming.get("severity") or "medium"),
            ]
            current["severity"] = max(
                severities,
                key=lambda item: severity_order.get(item, 0),
            )
        return merged

    @staticmethod
    def _extract_feedback_repo(pipeline: Any) -> Optional[Any]:
        """退化路径：试着从 pipeline.config 找 feedback_repo。"""
        for attr in ("feedback_repo", "learning_feedback_repo"):
            repo = getattr(pipeline, attr, None)
            if repo is not None:
                return repo
        config = getattr(pipeline, "config", None)
        if isinstance(config, dict):
            for key in ("feedback_repo", "learning_feedback_repo"):
                if config.get(key) is not None:
                    return config[key]
        return None

    @staticmethod
    def _extract_learning_insight_repo(pipeline: Any) -> Optional[Any]:
        for attr in ("learning_insight_repo", "learning_insights_repo"):
            repo = getattr(pipeline, attr, None)
            if repo is not None:
                return repo
        config = getattr(pipeline, "config", None)
        if isinstance(config, dict):
            for key in ("learning_insight_repo", "learning_insights_repo"):
                if config.get(key) is not None:
                    return config[key]
        return None

    def _resolve_learning_insight_limit(self, pipeline: Any) -> int:
        value = self._learning_insight_limit
        config = getattr(pipeline, "config", None)
        if isinstance(config, dict):
            value = _nested_config_value(
                config,
                ("learning_insights", "limit"),
                ("lfitl", "learning_insight_limit"),
                ("learning_insight_limit",),
                default=value,
            )
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return max(int(self._learning_insight_limit), 0)

    def _resolve_learning_insight_min_confidence(self, pipeline: Any) -> float:
        value = self._learning_insight_min_confidence
        config = getattr(pipeline, "config", None)
        if isinstance(config, dict):
            value = _nested_config_value(
                config,
                ("learning_insights", "prompt_bias_min_confidence"),
                ("learning_insights", "min_confidence"),
                ("lfitl", "learning_insight_min_confidence"),
                ("learning_insight_min_confidence",),
                default=value,
            )
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return max(0.0, min(1.0, self._learning_insight_min_confidence))

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
        if isinstance(config, dict) and isinstance(
            config.get("previous_iteration_feedback"), dict
        ):
            return dict(config["previous_iteration_feedback"])
        return {}

    @staticmethod
    def _feed_self_learning(
        pipeline: Any, cycle_assessment: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
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


def _nested_config_value(
    config: Mapping[str, Any],
    *paths: tuple[str, ...],
    default: Any = None,
) -> Any:
    for path in paths:
        current: Any = config
        for part in path:
            if not isinstance(current, Mapping) or part not in current:
                current = None
                break
            current = current[part]
        if current is not None:
            return current
    return default
