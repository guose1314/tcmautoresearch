from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.analyze_phase import AnalyzePhaseMixin
from src.research.phases.experiment_execution_phase import ExperimentExecutionPhaseMixin

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class ExperimentExecutionPhaseHandler(BasePhaseHandler, ExperimentExecutionPhaseMixin, AnalyzePhaseMixin):
    """Independent execution-import phase handler."""

    phase_name = "experiment_execution"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_experiment_execution_phase(cycle, context or {})