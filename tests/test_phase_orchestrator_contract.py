from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from src.research.phase_orchestrator import PhaseOrchestrator
from src.research.pipeline_phase_handlers import ResearchPhaseHandlers
from src.research.research_pipeline import ResearchPipeline


class _FakeEventBus:

    def __init__(self) -> None:
        self.subscriptions: List[Tuple[str, Any]] = []

    def subscribe(self, event_type: str, handler: Any) -> None:
        self.subscriptions.append((event_type, handler))

    def request(self, _event_type: str, _payload: Dict[str, Any]) -> Any:
        return None


class _ObserveHandler:

    def execute(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "observe"}

    def execute_observe_phase(self, _cycle: Any, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "observe", "context": context}

    def _build_observe_seed_lists(self) -> Tuple[List[str], List[str]]:
        return ["seed"], ["finding"]


class _HypothesisHandler:

    def execute(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "hypothesis"}

    def execute_hypothesis_phase(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "hypothesis"}

    def _build_hypothesis_context(self, _cycle: Any, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"source": "hypothesis_handler", **context}

    def _infer_hypothesis_domain(self, _cycle: Any, _observations: List[str], _findings: List[str]) -> str:
        return "integrative_research"


class _ExperimentHandler:

    def execute(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "experiment"}

    def execute_experiment_phase(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "experiment"}


class _AnalyzeHandler:

    def execute(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "analyze"}

    def execute_analyze_phase(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "analyze"}


class _PublishHandler:

    def execute(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "publish"}

    def execute_publish_phase(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "publish"}

    def collect_citation_records(
        self,
        _cycle: Any,
        _context: Dict[str, Any],
        _literature_pipeline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return [{"title": "contract-citation"}]


class _ReflectHandler:

    def execute(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "reflect"}

    def execute_reflect_phase(self, _cycle: Any, _context: Dict[str, Any]) -> Dict[str, Any]:
        return {"phase": "reflect"}


class _PhaseHandlersNoImplicitForward:

    def __init__(self) -> None:
        self._handlers = {
            "observe": _ObserveHandler(),
            "hypothesis": _HypothesisHandler(),
            "experiment": _ExperimentHandler(),
            "analyze": _AnalyzeHandler(),
            "publish": _PublishHandler(),
            "reflect": _ReflectHandler(),
        }

    def get_handler(self, phase_name: str) -> Any:
        return self._handlers.get(str(phase_name))

    def execute_phase_internal(self, phase: Any, cycle: Any, context: Dict[str, Any]) -> Dict[str, Any]:
        phase_name = getattr(phase, "value", str(phase))
        handler = self.get_handler(phase_name)
        if handler is None:
            return {"error": "unknown"}
        return handler.execute(cycle, context)

    def __getattr__(self, _name: str) -> Any:
        raise AssertionError("PhaseOrchestrator should not rely on implicit phase_handlers helper forwarding")


class _FakePipeline:

    def __init__(self) -> None:
        self.event_bus = _FakeEventBus()
        self.phase_handlers = _PhaseHandlersNoImplicitForward()
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)


def test_phase_orchestrator_observe_contract_uses_explicit_handler() -> None:
    orchestrator = PhaseOrchestrator(_FakePipeline())
    observe_handler = orchestrator.get_handler("observe")

    observations, findings = observe_handler._build_observe_seed_lists()
    assert observations == ["seed"]
    assert findings == ["finding"]

    result = observe_handler.execute_observe_phase({}, {"k": "v"})
    assert result["phase"] == "observe"
    assert result["context"] == {"k": "v"}


def test_phase_orchestrator_hypothesis_contract_uses_explicit_handler() -> None:
    orchestrator = PhaseOrchestrator(_FakePipeline())
    hypothesis_handler = orchestrator.get_handler("hypothesis")

    hypothesis_context = hypothesis_handler._build_hypothesis_context({}, {"foo": "bar"})
    assert hypothesis_context["source"] == "hypothesis_handler"
    assert hypothesis_context["foo"] == "bar"

    domain = hypothesis_handler._infer_hypothesis_domain({}, ["o"], ["f"])
    assert domain == "integrative_research"


def test_phase_orchestrator_publish_reflect_contract_uses_explicit_handlers() -> None:
    orchestrator = PhaseOrchestrator(_FakePipeline())
    publish_handler = orchestrator.get_handler("publish")
    reflect_handler = orchestrator.get_handler("reflect")

    citations = publish_handler.collect_citation_records({}, {}, {})
    assert citations == [{"title": "contract-citation"}]

    publish_result = publish_handler.execute_publish_phase({}, {})
    reflect_result = reflect_handler.execute_reflect_phase({}, {})
    assert publish_result["phase"] == "publish"
    assert reflect_result["phase"] == "reflect"


def test_phase_orchestrator_removes_phase_passthrough_bridge() -> None:
    assert "get_handler" in PhaseOrchestrator.__dict__
    for method_name in (
        "_execute_observe_phase",
        "_build_observe_seed_lists",
        "_collect_observe_corpus_if_enabled",
        "_run_observe_ingestion_pipeline",
        "_execute_hypothesis_phase",
        "_build_hypothesis_context",
        "_infer_hypothesis_domain",
        "_execute_publish_phase",
        "_collect_citation_records",
        "_execute_reflect_phase",
    ):
        assert method_name not in PhaseOrchestrator.__dict__


def test_research_phase_handlers_remove_implicit_getattr_bridge() -> None:
    assert "__getattr__" not in ResearchPhaseHandlers.__dict__
    assert "__getattr__" not in ResearchPipeline.__dict__
    for method_name in (
        "run_observe_ingestion_pipeline",
        "extract_corpus_text_entries",
        "merge_observe_relationship_sources",
        "build_hypothesis_context",
        "infer_hypothesis_domain",
        "collect_citation_records",
    ):
        assert method_name in ResearchPhaseHandlers.__dict__
