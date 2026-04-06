from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchPipeline


class BasePhaseHandler:
    """Base class for all phase handlers.

    Handlers share pipeline reference and relation conflict constants that are
    required by observe/hypothesis/publish helper methods.
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

    phase_name: str = ""

    def __init__(self, pipeline: "ResearchPipeline") -> None:
        self.pipeline = pipeline
