from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from src.research.phase_handlers import (
    AnalyzePhaseHandler,
    ExperimentExecutionPhaseHandler,
    ExperimentPhaseHandler,
    HypothesisPhaseHandler,
    ObservePhaseHandler,
    PublishPhaseHandler,
    ReflectPhaseHandler,
)

if TYPE_CHECKING:
    from src.research.research_pipeline import (
        ResearchCycle,
        ResearchPhase,
        ResearchPipeline,
    )


class ResearchPhaseHandlers:
    """阶段处理器注册中心与分发器。

    各阶段以独立 Handler 类实现并按 phase 维度注册，
    当前类只负责调度与显式阶段接口。
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
        self._handlers: Dict[str, Any] = {
            "observe": ObservePhaseHandler(pipeline),
            "hypothesis": HypothesisPhaseHandler(pipeline),
            "experiment": ExperimentPhaseHandler(pipeline),
            "experiment_execution": ExperimentExecutionPhaseHandler(pipeline),
            "analyze": AnalyzePhaseHandler(pipeline),
            "publish": PublishPhaseHandler(pipeline),
            "reflect": ReflectPhaseHandler(pipeline),
        }

    def get_handler(self, phase_name: str) -> Any:
        return self._handlers.get(str(phase_name), None)

    def _get_required_handler(self, phase_name: str) -> Any:
        handler = self.get_handler(phase_name)
        if handler is None:
            raise RuntimeError(f"阶段处理器不可用: {phase_name}")
        return handler

    def get_observe_handler(self) -> ObservePhaseHandler:
        return self._get_required_handler("observe")

    def get_hypothesis_handler(self) -> HypothesisPhaseHandler:
        return self._get_required_handler("hypothesis")

    def get_experiment_handler(self) -> ExperimentPhaseHandler:
        return self._get_required_handler("experiment")

    def get_experiment_execution_handler(self) -> ExperimentExecutionPhaseHandler:
        return self._get_required_handler("experiment_execution")

    def get_analyze_handler(self) -> AnalyzePhaseHandler:
        return self._get_required_handler("analyze")

    def get_publish_handler(self) -> PublishPhaseHandler:
        return self._get_required_handler("publish")

    def get_reflect_handler(self) -> ReflectPhaseHandler:
        return self._get_required_handler("reflect")

    def execute_phase_internal(
        self,
        phase: "ResearchPhase",
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        handler = self._handlers.get(phase.value)
        if handler is None or not hasattr(handler, "execute"):
            return {"error": f"未知阶段: {phase.value}"}
        return handler.execute(cycle, context)

    def execute_observe_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_observe_handler().execute_observe_phase(cycle, context or {})

    def execute_hypothesis_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_hypothesis_handler().execute_hypothesis_phase(cycle, context or {})

    def execute_experiment_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_experiment_handler().execute_experiment_phase(cycle, context or {})

    def execute_experiment_execution_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_experiment_execution_handler().execute_experiment_execution_phase(cycle, context or {})

    def execute_analyze_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_analyze_handler().execute_analyze_phase(cycle, context or {})

    def execute_publish_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_publish_handler().execute_publish_phase(cycle, context or {})

    def execute_reflect_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.get_reflect_handler().execute_reflect_phase(cycle, context or {})

    # --- Explicit cross-phase helper interfaces (no implicit __getattr__) ---

    def run_observe_ingestion_pipeline(
        self,
        corpus_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.get_observe_handler()._run_observe_ingestion_pipeline(corpus_result, context)

    def extract_corpus_text_entries(self, corpus_result: Dict[str, Any]) -> List[Dict[str, str]]:
        return self.get_observe_handler()._extract_corpus_text_entries(corpus_result)

    def merge_observe_relationship_sources(
        self,
        *relationship_groups: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self.get_observe_handler()._merge_relationship_sources(*relationship_groups)

    def build_hypothesis_context(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.get_hypothesis_handler()._build_hypothesis_context(cycle, context)

    def infer_hypothesis_domain(
        self,
        cycle: "ResearchCycle",
        observations: List[str],
        findings: List[str],
    ) -> str:
        return self.get_hypothesis_handler()._infer_hypothesis_domain(cycle, observations, findings)

    def collect_citation_records(
        self,
        cycle: "ResearchCycle",
        context: Dict[str, Any],
        literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return self.get_publish_handler().collect_citation_records(cycle, context, literature_pipeline)
