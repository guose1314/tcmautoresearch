from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.analyze_phase import AnalyzePhaseMixin
from src.research.phases.experiment_phase import ExperimentPhaseMixin
from src.research.phases.hypothesis_phase import HypothesisPhaseMixin
from src.research.phases.observe_phase import ObservePhaseMixin
from src.research.phases.publish_phase import PublishPhaseMixin

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class PublishPhaseHandler(
    BasePhaseHandler,
    PublishPhaseMixin,
    ExperimentPhaseMixin,
    HypothesisPhaseMixin,
    AnalyzePhaseMixin,
    ObservePhaseMixin,
):
    """Independent publish phase handler.

    Publish reuses experiment/hypothesis/analyze helper methods to build report
    context and evidence summary while keeping execution entry isolated.
    """

    phase_name = "publish"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_publish_phase(cycle, context or {})
