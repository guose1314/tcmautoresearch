"""Research runtime runner used by Web job transport wrappers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.orchestration.orchestration_contract import OrchestrationResult
from src.orchestration.research_runtime_service import ResearchRuntimeService


class StreamingResearchRunner:
    """Run one research payload through the shared runtime service."""

    def __init__(self, orchestrator_config: Optional[Dict[str, Any]] = None):
        self.runtime_service = ResearchRuntimeService(orchestrator_config or {})

    @staticmethod
    def _optional_text(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    def run(
        self,
        payload: Dict[str, Any],
        emit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> OrchestrationResult:
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise ValueError("topic 不能为空")

        runtime_result = self.runtime_service.run(
            topic,
            phase_contexts=payload.get("phase_contexts") or {},
            cycle_name=payload.get("cycle_name"),
            description=payload.get("description"),
            scope=payload.get("scope"),
            study_type=self._optional_text(payload.get("study_type")),
            primary_outcome=self._optional_text(payload.get("primary_outcome")),
            intervention=self._optional_text(payload.get("intervention")),
            comparison=self._optional_text(payload.get("comparison")),
            emit=emit,
        )
        return runtime_result.orchestration_result
