from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from src.research.phase_handlers.base import BasePhaseHandler
from src.research.phases.analyze_phase import AnalyzePhaseMixin

try:
    from src.quality import EvidenceGrader
except Exception:
    EvidenceGrader = None

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle


class AnalyzePhaseHandler(BasePhaseHandler, AnalyzePhaseMixin):
    phase_name = "analyze"

    def execute(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute_analyze_phase(cycle, context or {})

    def _create_evidence_grader(self) -> Any:
        grader_config = dict(self.pipeline.config.get("evidence_grading") or {})
        if EvidenceGrader is None:
            raise RuntimeError("EvidenceGrader 不可用")
        return EvidenceGrader(grader_config)
