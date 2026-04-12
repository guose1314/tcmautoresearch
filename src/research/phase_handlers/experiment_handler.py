from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.experiment_phase import ExperimentPhaseMixin
from src.research.phases.hypothesis_phase import HypothesisPhaseMixin

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class ExperimentPhaseHandler(BasePhaseHandler, ExperimentPhaseMixin, HypothesisPhaseMixin):
    """Independent protocol-design phase handler.

    Mixes hypothesis helpers to reuse hypothesis selection logic.
    """

    phase_name = "experiment"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_experiment_phase(cycle, context or {})
