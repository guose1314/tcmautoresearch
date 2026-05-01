"""3.1 ResearchOrchestrator — 研究全流程编排器

将所有 BC（Building Blocks）组合起来，提供统一的 ``run(topic)`` 入口。
调用方只需传入研究主题字符串，Orchestrator 负责：

1. 配置解析与校验
2. 创建并启动 ResearchPipeline 研究周期
3. 按顺序驱动 OBSERVE → HYPOTHESIS → EXPERIMENT → EXPERIMENT_EXECUTION → ANALYZE → PUBLISH → REFLECT
4. 收集并汇总每阶段结果
5. 输出 ``OrchestrationResult``（含阶段摘要、状态、总耗时）
6. 清理所有子模块资源

设计原则：
- Orchestrator 本身不含业务逻辑，仅做胶水层调用。
- 每个阶段的 ``phase_context`` 通过 ``topic_to_phase_context()`` 从主题
  自动推导，也可由调用方通过 ``phase_contexts`` 参数逐阶段覆盖。
- 阶段失败时记录错误并可配置是否继续后续阶段（``stop_on_failure``）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.orchestration.orchestration_contract import (
    OrchestrationResult,
    PhaseOutcome,
    _slug_topic,
    extract_publish_result_highlights,
    infer_scope,
    resolve_phase_outcome_status,
    summarize_phase_result,
    topic_to_phase_context,
)

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchPhase, ResearchPipeline

# 供单测 patch 的模块级符号（延迟解析，不在导入期触发重依赖）。
ResearchPhase = None
ResearchPipeline = None

logger = logging.getLogger(__name__)

# 默认执行的阶段顺序
_DEFAULT_PHASES = [
    "observe",
    "hypothesis",
    "experiment",
    "experiment_execution",
    "analyze",
    "publish",
    "reflect",
]


def _import_pipeline_symbols():
    """延迟导入研究流水线符号，避免导入期循环依赖。"""
    from src.research.research_pipeline import ResearchPhase, ResearchPipeline

    return ResearchPhase, ResearchPipeline


# ─────────────────────────────────────────────────────────────────────────────
# ResearchOrchestrator
# ─────────────────────────────────────────────────────────────────────────────


class ResearchOrchestrator:
    """全流程研究编排器。

    配置项（``config`` dict）：

    * ``pipeline_config``  : 直接传给 ResearchPipeline 的配置 dict
    * ``phases``           : 要执行的阶段列表（默认全部七个）
    * ``stop_on_failure``  : 某阶段失败后是否中止后续阶段（默认 True）
    * ``researchers``      : 研究人员列表（默认 ["orchestrator"]）
    * ``default_observe_context``   : OBSERVE 阶段默认 context 覆盖
    * ``default_hypothesis_context``: HYPOTHESIS 阶段默认 context 覆盖
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        import warnings

        warnings.warn(
            "ResearchOrchestrator 已弃用，请改用 ResearchRuntimeService。",
            DeprecationWarning,
            stacklevel=2,
        )
        self.config: Dict[str, Any] = config or {}
        self.pipeline_config: Dict[str, Any] = self.config.get("pipeline_config") or {}
        self.stop_on_failure: bool = bool(self.config.get("stop_on_failure", True))
        self.researchers: List[str] = self.config.get("researchers") or ["orchestrator"]
        self._research_phase_cls, self._pipeline_cls = self._resolve_pipeline_symbols()
        self._phases: List[Any] = [
            self._coerce_phase(p)
            for p in (self.config.get("phases") or _DEFAULT_PHASES)
        ]
        self.logger = logging.getLogger(__name__)

    def _resolve_pipeline_symbols(self):
        global ResearchPhase, ResearchPipeline

        imported_phase_cls = None
        imported_pipeline_cls = None
        if ResearchPhase is None or ResearchPipeline is None:
            imported_phase_cls, imported_pipeline_cls = _import_pipeline_symbols()

        if ResearchPhase is None:
            ResearchPhase = imported_phase_cls
        if ResearchPipeline is None:
            ResearchPipeline = imported_pipeline_cls

        return ResearchPhase, ResearchPipeline

    def _coerce_phase(self, phase: Any) -> Any:
        if isinstance(phase, str):
            return self._research_phase_cls(phase)
        return phase

    # ── 공공 API ─────────────────────────────────────────────────────────── #

    def run(
        self,
        topic: str,
        *,
        phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
        cycle_name: Optional[str] = None,
        description: Optional[str] = None,
        scope: Optional[str] = None,
        study_type: Optional[str] = None,
        primary_outcome: Optional[str] = None,
        intervention: Optional[str] = None,
        comparison: Optional[str] = None,
    ) -> OrchestrationResult:
        """执行完整研究流程并返回 :class:`OrchestrationResult`。

        Args:
            topic: 研究主题字符串，如 "麻黄汤治疗风寒感冒的临床研究"。
            phase_contexts: 按阶段名覆盖的 context dict，
                e.g. ``{"observe": {"run_literature_retrieval": True}}``.
            cycle_name: 研究周期名称（默认从 topic 生成）。
            description: 研究周期描述（默认等于 topic）。
            scope: 研究范围描述（默认从 topic 生成）。
            study_type: 显式研究设计类型（如 rct / cohort）。
            primary_outcome: 显式主要结局。
            intervention: 显式干预方案。
            comparison: 显式对照方案。
        """
        if not topic or not topic.strip():
            raise ValueError("topic 不能为空")

        started_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        pipeline, cycle_id, cycle_name, description, scope = (
            self._prepare_pipeline_and_cycle(
                topic=topic,
                cycle_name=cycle_name,
                description=description,
                scope=scope,
            )
        )

        if not pipeline.start_research_cycle(cycle_id):
            completed_at = datetime.now().isoformat()
            return OrchestrationResult(
                topic=topic,
                cycle_id=cycle_id,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                total_duration_sec=time.perf_counter() - t0,
                phases=[],
                pipeline_metadata={"error": "研究周期启动失败"},
            )

        phase_contexts = phase_contexts or {}
        phase_outcomes: List[PhaseOutcome] = []
        overall_status = "completed"

        try:
            phase_outcomes, overall_status = self._execute_phases(
                pipeline=pipeline,
                cycle_id=cycle_id,
                topic=topic,
                phase_contexts=phase_contexts,
                study_type=study_type,
                primary_outcome=primary_outcome,
                intervention=intervention,
                comparison=comparison,
            )
            publish_highlights = self._extract_publish_result_highlights(
                pipeline, cycle_id
            )
        finally:
            pipeline.cleanup()

        # 全部非 skipped 阶段都失败 且 自身未处于 partial → status=failed
        non_skipped = [p for p in phase_outcomes if p.status != "skipped"]
        if (
            non_skipped
            and overall_status != "partial"
            and all(p.status == "failed" for p in non_skipped)
        ):
            overall_status = "failed"

        completed_at = datetime.now().isoformat()
        return OrchestrationResult(
            topic=topic,
            cycle_id=cycle_id,
            status=overall_status,
            started_at=started_at,
            completed_at=completed_at,
            total_duration_sec=time.perf_counter() - t0,
            phases=phase_outcomes,
            pipeline_metadata={
                "cycle_name": cycle_name,
                "description": description,
                "scope": scope,
                "phases_requested": [p.value for p in self._phases],
                "protocol_inputs": {
                    "study_type": study_type,
                    "primary_outcome": primary_outcome,
                    "intervention": intervention,
                    "comparison": comparison,
                },
            },
            analysis_results=publish_highlights.get("analysis_results") or {},
            research_artifact=publish_highlights.get("research_artifact") or {},
        )

    def _prepare_pipeline_and_cycle(
        self,
        topic: str,
        cycle_name: Optional[str],
        description: Optional[str],
        scope: Optional[str],
    ) -> tuple[Any, str, str, str, str]:
        """创建 pipeline 与 cycle，并返回运行所需元信息。"""
        pipeline = self._pipeline_cls(self.pipeline_config)
        resolved_cycle_name = cycle_name or _slug_topic(topic)
        resolved_description = description or topic
        resolved_scope = scope or self._infer_scope(topic)

        cycle = pipeline.create_research_cycle(
            cycle_name=resolved_cycle_name,
            description=resolved_description,
            objective=topic,
            scope=resolved_scope,
            researchers=self.researchers,
        )
        return (
            pipeline,
            cycle.cycle_id,
            resolved_cycle_name,
            resolved_description,
            resolved_scope,
        )

    def _execute_phases(
        self,
        pipeline: Any,
        cycle_id: str,
        topic: str,
        phase_contexts: Dict[str, Dict[str, Any]],
        study_type: Optional[str],
        primary_outcome: Optional[str],
        intervention: Optional[str],
        comparison: Optional[str],
    ) -> tuple[List[PhaseOutcome], str]:
        """顺序执行阶段并处理失败后的中断/继续策略。"""
        outcomes: List[PhaseOutcome] = []
        overall_status = "completed"

        for phase in self._phases:
            ctx = self._build_phase_context(
                topic,
                phase,
                phase_contexts,
                study_type=study_type,
                primary_outcome=primary_outcome,
                intervention=intervention,
                comparison=comparison,
            )
            outcome = self._run_single_phase(pipeline, cycle_id, phase, ctx)
            outcomes.append(outcome)

            if outcome.status != "failed":
                continue

            overall_status = "partial"
            if self.stop_on_failure:
                outcomes.extend(self._build_skipped_outcomes(phase))
                break

        return outcomes, overall_status

    def _build_skipped_outcomes(self, failed_phase: Any) -> List[PhaseOutcome]:
        """在 stop_on_failure 生效时为剩余阶段生成 skipped 结果。"""
        skipped: List[PhaseOutcome] = []
        remaining = self._phases[self._phases.index(failed_phase) + 1 :]
        for phase in remaining:
            skipped.append(
                PhaseOutcome(
                    phase=phase.value,
                    status="skipped",
                    duration_sec=0.0,
                    summary={"reason": f"前置阶段 {failed_phase.value} 失败"},
                )
            )
        return skipped

    # ── 阶段驱动 ──────────────────────────────────────────────────────────  #

    def _run_single_phase(
        self,
        pipeline: Any,
        cycle_id: str,
        phase: Any,
        ctx: Dict[str, Any],
    ) -> PhaseOutcome:
        phase_t0 = time.perf_counter()
        self.logger.info("Orchestrator 开始阶段: %s", phase.value)
        try:
            result = pipeline.execute_research_phase(cycle_id, phase, ctx)
        except Exception as exc:
            self.logger.error("Orchestrator 阶段 %s 异常: %s", phase.value, exc)
            return PhaseOutcome(
                phase=phase.value,
                status="failed",
                duration_sec=time.perf_counter() - phase_t0,
                error=str(exc),
            )

        duration = time.perf_counter() - phase_t0
        if isinstance(result, dict) and result.get("error"):
            return PhaseOutcome(
                phase=phase.value,
                status="failed",
                duration_sec=duration,
                error=result["error"],
                summary=result,
            )

        summary = self._summarize_phase_result(phase, result)
        outcome_status = self._resolve_phase_outcome_status(result)
        self.logger.info("Orchestrator 阶段 %s 完成 (%.2fs)", phase.value, duration)
        return PhaseOutcome(
            phase=phase.value,
            status=outcome_status,
            duration_sec=duration,
            summary=summary,
            error=str(result.get("error") or "") if outcome_status == "failed" else "",
        )

    # ── context 构建 ─────────────────────────────────────────────────────── #

    def _build_phase_context(
        self,
        topic: str,
        phase: Any,
        phase_contexts: Dict[str, Dict[str, Any]],
        *,
        study_type: Optional[str],
        primary_outcome: Optional[str],
        intervention: Optional[str],
        comparison: Optional[str],
    ) -> Dict[str, Any]:
        """将默认 context、config 覆盖、调用方覆盖三层合并。"""
        # 1. 从 topic 自动生成基础 context
        base = topic_to_phase_context(
            topic,
            phase,
            study_type=study_type,
            primary_outcome=primary_outcome,
            intervention=intervention,
            comparison=comparison,
        )

        # 2. config 中的默认覆盖（如 default_observe_context）
        config_key = f"default_{phase.value}_context"
        config_override: Dict[str, Any] = self.config.get(config_key) or {}

        # 3. 调用方逐阶段覆盖（以 phase.value 为 key）
        call_override: Dict[str, Any] = phase_contexts.get(phase.value) or {}

        return {**base, **config_override, **call_override}

    # ── 结果摘要 ─────────────────────────────────────────────────────────── #

    @staticmethod
    def _summarize_phase_result(
        phase: Any,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return summarize_phase_result(phase, result)

    @staticmethod
    def _extract_publish_result_highlights(
        pipeline: Any,
        cycle_id: str,
    ) -> Dict[str, Dict[str, Any]]:
        return extract_publish_result_highlights(pipeline, cycle_id)

    @staticmethod
    def _infer_scope(topic: str) -> str:
        return infer_scope(topic)

    @staticmethod
    def _resolve_phase_outcome_status(result: Dict[str, Any]) -> str:
        return resolve_phase_outcome_status(result)


def run_research(
    topic: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
    cycle_name: Optional[str] = None,
    description: Optional[str] = None,
    scope: Optional[str] = None,
    study_type: Optional[str] = None,
    primary_outcome: Optional[str] = None,
    intervention: Optional[str] = None,
    comparison: Optional[str] = None,
) -> OrchestrationResult:
    """函数式单一入口：一行代码触发完整研究流水线。

    .. deprecated::
        此函数直接实例化 ResearchOrchestrator，绕过 RuntimeConfigAssembler 的统一
        配置组装流程。生产代码请改用 :class:`ResearchRuntimeService`::

            from src.orchestration import ResearchRuntimeService
            svc = ResearchRuntimeService(orchestrator_config)
            result = svc.run(topic, phase_contexts=phase_contexts)

        此函数仅保留用于向后兼容和快速测试场景。
    """
    import warnings

    warnings.warn(
        "run_research() 已弃用，请改用 ResearchRuntimeService。"
        "此函数绕过 RuntimeConfigAssembler，不推荐在生产代码中使用。",
        DeprecationWarning,
        stacklevel=2,
    )
    orchestrator = ResearchOrchestrator(config=config)
    return orchestrator.run(
        topic,
        phase_contexts=phase_contexts,
        cycle_name=cycle_name,
        description=description,
        scope=scope,
        study_type=study_type,
        primary_outcome=primary_outcome,
        intervention=intervention,
        comparison=comparison,
    )
