"""3.1 ResearchOrchestrator — 研究全流程编排器

将所有 BC（Building Blocks）组合起来，提供统一的 ``run(topic)`` 入口。
调用方只需传入研究主题字符串，Orchestrator 负责：

1. 配置解析与校验
2. 创建并启动 ResearchPipeline 研究周期
3. 按顺序驱动 OBSERVE → HYPOTHESIS → EXPERIMENT → ANALYZE → PUBLISH → REFLECT
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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.research.research_pipeline import ResearchPhase, ResearchPipeline

logger = logging.getLogger(__name__)

# 默认执行的阶段顺序
_DEFAULT_PHASES = [
    ResearchPhase.OBSERVE,
    ResearchPhase.HYPOTHESIS,
    ResearchPhase.EXPERIMENT,
    ResearchPhase.ANALYZE,
    ResearchPhase.PUBLISH,
    ResearchPhase.REFLECT,
]


# ─────────────────────────────────────────────────────────────────────────────
# 结果数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PhaseOutcome:
    """单阶段执行结果摘要。"""

    phase: str
    status: str            # "completed" | "failed" | "skipped"
    duration_sec: float
    error: str = ""
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "duration_sec": round(self.duration_sec, 3),
            "error": self.error,
            "summary": self.summary,
        }


@dataclass
class OrchestrationResult:
    """``run()`` 的最终输出。"""

    topic: str
    cycle_id: str
    status: str            # "completed" | "partial" | "failed"
    started_at: str
    completed_at: str
    total_duration_sec: float
    phases: List[PhaseOutcome]
    pipeline_metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "cycle_id": self.cycle_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_sec": round(self.total_duration_sec, 3),
            "phases": [p.to_dict() for p in self.phases],
            "pipeline_metadata": self.pipeline_metadata,
        }

    @property
    def succeeded_phases(self) -> List[str]:
        return [p.phase for p in self.phases if p.status == "completed"]

    @property
    def failed_phases(self) -> List[str]:
        return [p.phase for p in self.phases if p.status == "failed"]


# ─────────────────────────────────────────────────────────────────────────────
# ResearchOrchestrator
# ─────────────────────────────────────────────────────────────────────────────

class ResearchOrchestrator:
    """全流程研究编排器。

    配置项（``config`` dict）：

    * ``pipeline_config``  : 直接传给 ResearchPipeline 的配置 dict
    * ``phases``           : 要执行的阶段列表（默认全部六个）
    * ``stop_on_failure``  : 某阶段失败后是否中止后续阶段（默认 True）
    * ``researchers``      : 研究人员列表（默认 ["orchestrator"]）
    * ``default_observe_context``   : OBSERVE 阶段默认 context 覆盖
    * ``default_hypothesis_context``: HYPOTHESIS 阶段默认 context 覆盖
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = config or {}
        self.pipeline_config: Dict[str, Any] = self.config.get("pipeline_config") or {}
        self.stop_on_failure: bool = bool(self.config.get("stop_on_failure", True))
        self.researchers: List[str] = self.config.get("researchers") or ["orchestrator"]
        self._phases: List[ResearchPhase] = [
            ResearchPhase(p) if isinstance(p, str) else p
            for p in (self.config.get("phases") or _DEFAULT_PHASES)
        ]
        self.logger = logging.getLogger(__name__)

    # ── 공공 API ─────────────────────────────────────────────────────────── #

    def run(
        self,
        topic: str,
        *,
        phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
        cycle_name: Optional[str] = None,
        description: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> OrchestrationResult:
        """执行完整研究流程并返回 :class:`OrchestrationResult`。

        Args:
            topic: 研究主题字符串，如 "麻黄汤治疗风寒感冒的临床研究"。
            phase_contexts: 按阶段名覆盖的 context dict，
                e.g. ``{"observe": {"run_literature_retrieval": True}}``.
            cycle_name: 研究周期名称（默认从 topic 生成）。
            description: 研究周期描述（默认等于 topic）。
            scope: 研究范围描述（默认从 topic 生成）。
        """
        if not topic or not topic.strip():
            raise ValueError("topic 不能为空")

        started_at = datetime.now().isoformat()
        t0 = time.perf_counter()

        pipeline, cycle_id, cycle_name, description, scope = self._prepare_pipeline_and_cycle(
            topic=topic,
            cycle_name=cycle_name,
            description=description,
            scope=scope,
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
            )
        finally:
            pipeline.cleanup()

        # 全部非 skipped 阶段都失败 且 自身未处于 partial → status=failed
        non_skipped = [p for p in phase_outcomes if p.status != "skipped"]
        if non_skipped and overall_status != "partial" and all(p.status == "failed" for p in non_skipped):
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
            },
        )

    def _prepare_pipeline_and_cycle(
        self,
        topic: str,
        cycle_name: Optional[str],
        description: Optional[str],
        scope: Optional[str],
    ) -> tuple[ResearchPipeline, str, str, str, str]:
        """创建 pipeline 与 cycle，并返回运行所需元信息。"""
        pipeline = ResearchPipeline(self.pipeline_config)
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
        return pipeline, cycle.cycle_id, resolved_cycle_name, resolved_description, resolved_scope

    def _execute_phases(
        self,
        pipeline: ResearchPipeline,
        cycle_id: str,
        topic: str,
        phase_contexts: Dict[str, Dict[str, Any]],
    ) -> tuple[List[PhaseOutcome], str]:
        """顺序执行阶段并处理失败后的中断/继续策略。"""
        outcomes: List[PhaseOutcome] = []
        overall_status = "completed"

        for phase in self._phases:
            ctx = self._build_phase_context(topic, phase, phase_contexts)
            outcome = self._run_single_phase(pipeline, cycle_id, phase, ctx)
            outcomes.append(outcome)

            if outcome.status != "failed":
                continue

            overall_status = "partial"
            if self.stop_on_failure:
                outcomes.extend(self._build_skipped_outcomes(phase))
                break

        return outcomes, overall_status

    def _build_skipped_outcomes(self, failed_phase: ResearchPhase) -> List[PhaseOutcome]:
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
        pipeline: ResearchPipeline,
        cycle_id: str,
        phase: ResearchPhase,
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
        self.logger.info("Orchestrator 阶段 %s 完成 (%.2fs)", phase.value, duration)
        return PhaseOutcome(
            phase=phase.value,
            status="completed",
            duration_sec=duration,
            summary=summary,
        )

    # ── context 构建 ─────────────────────────────────────────────────────── #

    def _build_phase_context(
        self,
        topic: str,
        phase: ResearchPhase,
        phase_contexts: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """将默认 context、config 覆盖、调用方覆盖三层合并。"""
        # 1. 从 topic 自动生成基础 context
        base = topic_to_phase_context(topic, phase)

        # 2. config 中的默认覆盖（如 default_observe_context）
        config_key = f"default_{phase.value}_context"
        config_override: Dict[str, Any] = self.config.get(config_key) or {}

        # 3. 调用方逐阶段覆盖（以 phase.value 为 key）
        call_override: Dict[str, Any] = phase_contexts.get(phase.value) or {}

        return {**base, **config_override, **call_override}

    # ── 结果摘要 ─────────────────────────────────────────────────────────── #

    @staticmethod
    def _summarize_phase_result(
        phase: ResearchPhase,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从各阶段原始结果中提取关键指标。"""
        if phase == ResearchPhase.OBSERVE:
            return {
                "observation_count": len(result.get("observations", [])),
                "finding_count": len(result.get("findings", [])),
                "data_source": (result.get("metadata") or {}).get("data_source", "unknown"),
                "corpus_schema": (result.get("metadata") or {}).get("corpus_schema"),
                "literature_records": (result.get("literature_pipeline") or {}).get("record_count", 0),
            }
        if phase == ResearchPhase.HYPOTHESIS:
            hyps = result.get("hypotheses") or []
            return {
                "hypothesis_count": len(hyps),
                "validated_count": sum(1 for h in hyps if h.get("status") == "validated"),
                "domain": result.get("domain", ""),
            }
        if phase == ResearchPhase.EXPERIMENT:
            return {
                "experiment_count": len(result.get("experiments", [])),
                "success_rate": result.get("success_rate", 0.0),
            }
        if phase == ResearchPhase.ANALYZE:
            return {
                "analysis_methods": result.get("methods_used", []),
                "key_findings": result.get("key_findings", [])[:3],
            }
        if phase == ResearchPhase.PUBLISH:
            return {
                "deliverable_count": len(result.get("deliverables", [])),
                "abstract_word_count": len(str(result.get("abstract", "")).split()),
            }
        if phase == ResearchPhase.REFLECT:
            return {
                "improvement_suggestions": result.get("improvements", [])[:3],
                "next_cycle_focus": result.get("next_cycle_focus", ""),
            }
        return {}

    @staticmethod
    def _infer_scope(topic: str) -> str:
        keywords = ["古籍", "方剂", "本草", "临床", "药理", "证候", "针灸", "经络"]
        hits = [kw for kw in keywords if kw in topic]
        if hits:
            return "+".join(hits[:3])
        return "中医古籍与现代研究"


def run_research(
    topic: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    phase_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
    cycle_name: Optional[str] = None,
    description: Optional[str] = None,
    scope: Optional[str] = None,
) -> OrchestrationResult:
    """函数式单一入口：一行代码触发完整研究流水线。"""
    orchestrator = ResearchOrchestrator(config=config)
    return orchestrator.run(
        topic,
        phase_contexts=phase_contexts,
        cycle_name=cycle_name,
        description=description,
        scope=scope,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数（可单独复用）
# ─────────────────────────────────────────────────────────────────────────────

def topic_to_phase_context(topic: str, phase: ResearchPhase) -> Dict[str, Any]:
    """从研究主题字符串为各阶段自动生成基础 context。

    生成的 context 为保守默认值，不触发任何需要网络或 LLM 的操作，
    除非调用方在 ``phase_contexts`` 中显式开启。
    """
    base: Dict[str, Any] = {"research_topic": topic}

    if phase == ResearchPhase.OBSERVE:
        return {
            **base,
            "run_literature_retrieval": False,
            "run_preprocess_and_extract": False,
            "use_ctext_whitelist": False,
            "data_source": "manual",
            "literature_query": topic,
        }
    if phase == ResearchPhase.HYPOTHESIS:
        return {
            **base,
            "research_objective": topic,
        }
    if phase == ResearchPhase.EXPERIMENT:
        return {**base}
    if phase == ResearchPhase.ANALYZE:
        return {**base}
    if phase == ResearchPhase.PUBLISH:
        return {**base}
    if phase == ResearchPhase.REFLECT:
        return {**base}
    return base


def _slug_topic(topic: str, max_len: int = 40) -> str:
    """将主题字符串转为合法的 cycle_name（截断 + 去除特殊字符）。"""
    clean = "".join(c for c in topic if c.isalnum() or c in "-_ ，。·")
    clean = clean.strip().replace(" ", "_")[:max_len] or "research_cycle"
    return clean
