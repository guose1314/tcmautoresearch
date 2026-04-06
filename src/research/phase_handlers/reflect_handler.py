from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.reflect_phase import ReflectPhaseMixin

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class ReflectPhaseHandler(BasePhaseHandler, ReflectPhaseMixin):
    phase_name = "reflect"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_reflect_phase(cycle, context or {})
