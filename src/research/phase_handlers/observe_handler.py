from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.observe_phase import ObservePhaseMixin

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class ObservePhaseHandler(BasePhaseHandler, ObservePhaseMixin):
    phase_name = "observe"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_observe_phase(cycle, context or {})
