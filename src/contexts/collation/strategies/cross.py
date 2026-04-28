"""对校（cross collation）：调 PhilologyService 现有版本对校能力。

PhilologyService.``_build_version_collation`` 已实现"witness 提取 + diff + 收敛为 collation_entry"，
本策略仅做适配：构造其期望的 ``context``（含 ``raw_text`` + ``parallel_versions``），
并把结果摘要为 ``differences``。
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


class CrossCollationStrategy:
    """跨版本对校适配层。"""

    name = "cross"

    def __init__(self, *, philology_service: Any = None) -> None:
        self._service = philology_service

    def run(self, document_id: str, *, context: Mapping[str, Any]) -> Dict[str, Any]:
        if self._service is None:
            return {
                "document_id": document_id,
                "enabled": False,
                "reason": "PhilologyService not provided",
                "witness_count": 0,
                "difference_count": 0,
                "witnesses": [],
            }

        raw_text = str(context.get("raw_text") or "")
        parallel_versions = list(context.get("parallel_versions") or [])
        input_metadata = dict(context.get("input_metadata") or {})

        philology_context: Dict[str, Any] = {
            "raw_text": raw_text,
            "metadata": {**input_metadata, "document_id": document_id},
            "parallel_versions": parallel_versions,
        }

        version_collation = self._service._build_version_collation(
            raw_text, philology_context, philology_context["metadata"]
        )

        return {
            "document_id": document_id,
            "enabled": bool(version_collation.get("enabled")),
            "witness_count": int(version_collation.get("witness_count") or 0),
            "difference_count": int(version_collation.get("difference_count") or 0),
            "witnesses": list(version_collation.get("witnesses") or []),
            "summary": list(version_collation.get("summary") or []),
            "collation_entries": list(version_collation.get("collation_entries") or []),
        }


__all__ = ["CrossCollationStrategy"]
