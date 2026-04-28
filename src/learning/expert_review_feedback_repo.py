"""ExpertReviewFeedbackRepo — T7.2: 把专家评审反馈适配成 LFITL ``recent()`` 契约。

LearningLoopOrchestrator 依赖一个具备 ``recent(limit) -> List[Dict]`` 接口的
feedback_repo（参见 ``tests/unit/test_learning_loop_lfitl.py``）。本适配器从
``research_learning_feedback`` 表里挑出 ``feedback_scope="expert_review"`` 的高
权重记录，重新拼成 :class:`src.contexts.lfitl.FeedbackEntry` 兼容的 dict，从而
让 :class:`FeedbackTranslator` 在下一轮 ``prepare_cycle`` 直接把专家结论编译进
prompt bias。

设计要点
========

* **专家信号优先**：通过 ``feedback_scope="expert_review"`` 与
  ``metadata.weight`` 把专家行从普通 phase 反馈中区分出来。
* **保形输出**：``source_phase / severity / issue_fields / violations /
  graph_targets`` 全部从 ``metadata`` 还原；旧 schema 缺字段时安全降级。
* **可注入** ``feedback_scopes`` 参数，未来想合并 ``expert_dispute`` 等其它高
  权重 scope 时只需改一行。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


_DEFAULT_SCOPES: tuple[str, ...] = ("expert_review",)


class ExpertReviewFeedbackRepo:
    """把 ``ResearchSessionRepository`` 的 expert_review 行翻译成 LFITL ``recent()`` 契约。"""

    def __init__(
        self,
        session_repo: Any,
        *,
        feedback_scopes: Sequence[str] = _DEFAULT_SCOPES,
        default_severity: str = "medium",
    ) -> None:
        if session_repo is None:
            raise ValueError("session_repo is required")
        if not hasattr(session_repo, "list_learning_feedback"):
            raise TypeError(
                "session_repo must expose list_learning_feedback(...)",
            )
        self._repo = session_repo
        self._scopes = tuple(
            str(s).strip().lower() for s in feedback_scopes if str(s).strip()
        ) or _DEFAULT_SCOPES
        self._default_severity = str(default_severity or "medium").lower()

    # ------------------------------------------------------------------ #
    # LFITL 契约
    # ------------------------------------------------------------------ #

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """按 ``created_at desc`` 拉取每个 scope 的最近 ``limit`` 条，合并后返回。"""
        clamped_limit = max(int(limit or 0), 0)
        if clamped_limit == 0:
            return []
        merged: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for scope in self._scopes:
            try:
                page = self._repo.list_learning_feedback(
                    feedback_scope=scope,
                    limit=clamped_limit,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "ExpertReviewFeedbackRepo.recent: list_learning_feedback(%s) 失败: %s",
                    scope,
                    exc,
                )
                continue
            for item in (page or {}).get("items", []) or []:
                if not isinstance(item, Mapping):
                    continue
                row_id = str(item.get("id") or "")
                if row_id and row_id in seen_ids:
                    continue
                if row_id:
                    seen_ids.add(row_id)
                entry = self._row_to_feedback_entry(item)
                if entry:
                    merged.append(entry)
                if len(merged) >= clamped_limit:
                    return merged
        return merged

    # ------------------------------------------------------------------ #
    # 行 → FeedbackEntry-兼容 dict
    # ------------------------------------------------------------------ #

    def _row_to_feedback_entry(self, row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        details = row.get("details") if isinstance(row.get("details"), Mapping) else {}

        severity = (
            str(metadata.get("severity") or "").strip().lower()
            or self._grade_to_severity(row.get("grade_level"))
            or self._default_severity
        )
        source_phase = (
            str(metadata.get("source_phase") or "").strip()
            or str(row.get("target_phase") or "").strip()
            or str(row.get("source_phase") or "").strip()
            or "expert_review"
        )
        issue_fields = list(_iter_strings(metadata.get("issue_fields") or details.get("issue_fields")))
        violations = list(_iter_mappings(metadata.get("violations") or details.get("violations")))
        graph_targets = list(_iter_strings(metadata.get("graph_targets") or details.get("graph_targets")))

        # 如果专家明确给了 D 级（high）或 C 级（medium）但没有 violations，
        # 我们造一条规则 id=expert_review:<grade>，让 PromptBiasCompiler 一定会
        # 输出 prompt_bias_action（其要求 violations 非空 或 issue_fields 非空）。
        grade = (str(row.get("grade_level") or "").strip().upper() or "")
        if not violations and grade in {"C", "D"}:
            violations = [
                {
                    "rule_id": f"expert_review:{grade}",
                    "severity": severity,
                }
            ]
        if not issue_fields:
            hint = str(details.get("hypothesis_statement") or "").strip()
            if hint:
                # 给一个 catch-all field，避免 bias_block 为空
                issue_fields = ["hypothesis"]

        # extra 透传给 FeedbackEntry.from_dict，方便下游审计
        extra = {
            "feedback_scope": row.get("feedback_scope"),
            "cycle_id": row.get("cycle_id"),
            "weight": metadata.get("weight"),
            "expert_grade": grade or None,
            "expert_notes": details.get("expert_notes"),
            "expert_review_id": metadata.get("expert_review_id"),
        }

        return {
            "source_phase": source_phase,
            "severity": severity,
            "issue_fields": issue_fields,
            "violations": violations,
            "graph_targets": graph_targets,
            "issues": [],
            **extra,
        }

    @staticmethod
    def _grade_to_severity(grade: Any) -> str:
        text = str(grade or "").strip().upper()
        return {
            "A": "low",
            "B": "low",
            "C": "medium",
            "D": "high",
        }.get(text, "")


def _iter_strings(value: Any) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        text = str(value).strip()
        return (text,) if text else ()
    if isinstance(value, Sequence):
        out: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                out.append(text)
        return out
    return ()


def _iter_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return ()


__all__ = ["ExpertReviewFeedbackRepo"]
