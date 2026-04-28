"""理校（rational collation）：调 SelfRefineRunner 做"依理推断"。

把待校文本送入 ``SelfRefineRunner.run(purpose='collation_rational', ...)``，
最终输出与改动建议作为本校结果返回。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)


class RationalCollationStrategy:
    """理校（依理推断）。"""

    name = "rational"

    def __init__(self, *, self_refine_runner: Any = None) -> None:
        self._runner = self_refine_runner

    def run(self, document_id: str, *, context: Mapping[str, Any]) -> Dict[str, Any]:
        if self._runner is None:
            return {
                "document_id": document_id,
                "enabled": False,
                "reason": "SelfRefineRunner not provided",
                "rounds": 0,
                "issues_found": 0,
            }

        raw_text = str(context.get("raw_text") or "")
        if not raw_text:
            return {
                "document_id": document_id,
                "enabled": False,
                "reason": "no raw_text provided",
                "rounds": 0,
                "issues_found": 0,
            }

        rounds = int(context.get("rational_rounds") or 1)
        task_description = str(
            context.get("rational_task")
            or "对给定中医古籍/文献片段做理校：识别并修正违背中医基本理论或前后矛盾的表述。"
        )

        result = self._runner.run(
            purpose="collation_rational",
            inputs={
                "task_description": task_description,
                "input_payload": raw_text,
            },
            max_refine_rounds=rounds,
        )

        issues_total = sum(len(r.issues) for r in result.rounds)
        return {
            "document_id": document_id,
            "enabled": True,
            "rounds": len(result.rounds),
            "issues_found": issues_total,
            "succeeded": result.succeeded,
            "final_output": result.final_output,
            "issues": [
                {"round": r.round_index, "items": r.issues} for r in result.rounds
            ],
            "violations": list(result.last_violations),
        }


__all__ = ["RationalCollationStrategy"]
