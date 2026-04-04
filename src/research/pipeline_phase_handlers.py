from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phases import (
    AnalyzePhaseMixin,
    ExperimentPhaseMixin,
    HypothesisPhaseMixin,
    ObservePhaseMixin,
    PublishPhaseMixin,
    ReflectPhaseMixin,
)

if TYPE_CHECKING:
    from src.research.research_pipeline import (
        ResearchCycle,
        ResearchPhase,
        ResearchPipeline,
    )


class ResearchPhaseHandlers(
    ObservePhaseMixin,
    HypothesisPhaseMixin,
    ExperimentPhaseMixin,
    AnalyzePhaseMixin,
    PublishPhaseMixin,
    ReflectPhaseMixin,
):
    """阶段处理器：负责研究阶段分发与执行。

    各阶段实现拆分于 ``src/research/phases/`` 子包，
    本类通过多重继承 (Mixin) 组合所有阶段方法。
    """

    _RELATION_SOURCE_PRIORITY = {
        "observe_reasoning_engine": 3,
        "observe_semantic_graph": 2,
        "pipeline_hypothesis_context": 1,
    }
    _RELATION_CONFLICT_STRATEGIES = {
        "source_priority_then_confidence",
        "confidence_then_source_priority",
    }

    def __init__(self, pipeline: "ResearchPipeline"):
        self.pipeline = pipeline
    def execute_phase_internal(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        dispatch = {
            "observe": self.execute_observe_phase,
            "hypothesis": self.execute_hypothesis_phase,
            "experiment": self.execute_experiment_phase,
            "analyze": self.execute_analyze_phase,
            "publish": self.execute_publish_phase,
            "reflect": self.execute_reflect_phase,
        }
        handler = dispatch.get(phase.value)
        if handler is None:
            return {"error": f"未知阶段: {phase.value}"}
        return handler(cycle, context)
