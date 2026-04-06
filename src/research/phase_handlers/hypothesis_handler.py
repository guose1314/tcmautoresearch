from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.hypothesis_phase import HypothesisPhaseMixin
from src.research.phases.observe_phase import ObservePhaseMixin

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class HypothesisPhaseHandler(BasePhaseHandler, HypothesisPhaseMixin, ObservePhaseMixin):
    """Independent hypothesis phase handler.

    It also mixes observe helpers for relationship dedup/summary merge utilities.
    """

    phase_name = "hypothesis"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_hypothesis_phase(cycle, context or {})
