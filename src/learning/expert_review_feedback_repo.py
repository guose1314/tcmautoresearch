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

from src.learning.expert_review_consensus import (
    EXPERT_SIGNAL_CONSENSUS,
    EXPERT_SIGNAL_DISPUTE,
    EXPERT_SIGNAL_SINGLE,
    build_expert_review_consensus_index,
    classify_expert_review_signal,
    normalize_dispute_flag,
    resolve_expert_review_group_key,
)

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
        self._scopes = (
            tuple(str(s).strip().lower() for s in feedback_scopes if str(s).strip())
            or _DEFAULT_SCOPES
        )
        self._default_severity = str(default_severity or "medium").lower()

    # ------------------------------------------------------------------ #
    # LFITL 契约
    # ------------------------------------------------------------------ #

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """按 ``created_at desc`` 拉取每个 scope 的最近 ``limit`` 条，合并后返回。"""
        clamped_limit = max(int(limit or 0), 0)
        if clamped_limit == 0:
            return []
        rows: List[Mapping[str, Any]] = []
        seen_ids: set[str] = set()
        fetch_limit = max(clamped_limit * 5, 50)
        for scope in self._scopes:
            try:
                page = self._repo.list_learning_feedback(
                    feedback_scope=scope,
                    limit=fetch_limit,
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
                rows.append(item)

        consensus_index = build_expert_review_consensus_index(rows)
        merged: List[Dict[str, Any]] = []
        for row in rows:
            consensus = consensus_index.get(resolve_expert_review_group_key(row), {})
            entry = self._row_to_feedback_entry(row, consensus)
            if entry:
                merged.append(entry)
        merged.sort(key=self._entry_priority)
        return merged[:clamped_limit]

    # ------------------------------------------------------------------ #
    # 行 → FeedbackEntry-兼容 dict
    # ------------------------------------------------------------------ #

    def _row_to_feedback_entry(
        self,
        row: Mapping[str, Any],
        consensus: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        metadata = (
            row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        )
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
        issue_fields = list(
            _iter_strings(metadata.get("issue_fields") or details.get("issue_fields"))
        )
        violations = list(
            _iter_mappings(metadata.get("violations") or details.get("violations"))
        )
        graph_targets = list(
            _iter_strings(metadata.get("graph_targets") or details.get("graph_targets"))
        )
        expert_signal = classify_expert_review_signal(row, consensus)
        if expert_signal == EXPERT_SIGNAL_DISPUTE:
            severity = self._max_severity(severity, "high")

        # 如果专家明确给了 D 级（high）或 C 级（medium）但没有 violations，
        # 我们造一条规则 id=expert_review:<grade>，让 PromptBiasCompiler 一定会
        # 输出 prompt_bias_action（其要求 violations 非空 或 issue_fields 非空）。
        grade = str(row.get("grade_level") or "").strip().upper() or ""
        if not violations and grade in {"C", "D"}:
            violations = [
                {
                    "rule_id": f"expert_review:{grade}",
                    "severity": severity,
                }
            ]
        signal_rule_id = self._build_signal_rule_id(expert_signal, grade, consensus)
        if signal_rule_id and not any(
            str((violation or {}).get("rule_id") or "") == signal_rule_id
            for violation in violations
        ):
            violations.insert(
                0,
                {
                    "rule_id": signal_rule_id,
                    "severity": severity,
                    "expert_signal": expert_signal,
                },
            )
        if not issue_fields:
            hint = str(details.get("hypothesis_statement") or "").strip()
            if hint or expert_signal:
                # 给一个 catch-all field，避免 bias_block 为空
                issue_fields = ["hypothesis"]

        # extra 透传给 FeedbackEntry.from_dict，方便下游审计
        consensus_summary = dict(consensus or {})
        extra = {
            "feedback_scope": row.get("feedback_scope"),
            "cycle_id": row.get("cycle_id"),
            "weight": metadata.get("weight"),
            "expert_grade": grade or None,
            "expert_notes": details.get("expert_notes"),
            "expert_review_id": metadata.get("expert_review_id"),
            "expert_review_identity": metadata.get("expert_review_identity"),
            "reviewer_id": metadata.get("reviewer_id") or details.get("reviewer_id"),
            "review_round": metadata.get("review_round") or details.get("review_round"),
            "blind_group": metadata.get("blind_group") or details.get("blind_group"),
            "confidence": metadata.get("confidence") or details.get("confidence"),
            "dispute_flag": normalize_dispute_flag(
                metadata.get("dispute_flag") or details.get("dispute_flag")
            ),
            "consensus_group_id": metadata.get("consensus_group_id")
            or details.get("consensus_group_id"),
            "expert_signal": expert_signal,
            "consensus_summary": consensus_summary,
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
    def _entry_priority(entry: Mapping[str, Any]) -> tuple:
        signal_rank = {
            EXPERT_SIGNAL_DISPUTE: 0,
            EXPERT_SIGNAL_CONSENSUS: 1,
            EXPERT_SIGNAL_SINGLE: 2,
        }
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        consensus = (
            entry.get("consensus_summary")
            if isinstance(entry.get("consensus_summary"), Mapping)
            else {}
        )
        confidence = entry.get("confidence") or consensus.get("average_confidence") or 0
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0
        review_count = int(consensus.get("review_count") or 1)
        return (
            signal_rank.get(str(entry.get("expert_signal") or ""), 9),
            severity_rank.get(str(entry.get("severity") or "medium"), 2),
            -confidence_value,
            -review_count,
        )

    @staticmethod
    def _build_signal_rule_id(
        expert_signal: str,
        grade: str,
        consensus: Optional[Mapping[str, Any]],
    ) -> str:
        consensus_payload = consensus if isinstance(consensus, Mapping) else {}
        majority_grade = str(
            consensus_payload.get("majority_grade") or grade or ""
        ).strip()
        if expert_signal == EXPERT_SIGNAL_CONSENSUS:
            return f"expert_consensus:{majority_grade or 'ungraded'}"
        if expert_signal == EXPERT_SIGNAL_DISPUTE:
            return f"expert_dispute:{majority_grade or 'mixed'}"
        if expert_signal == EXPERT_SIGNAL_SINGLE:
            return f"single_expert_review:{grade or 'ungraded'}"
        return ""

    @staticmethod
    def _max_severity(current: str, minimum: str) -> str:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        current_text = str(current or "medium").strip().lower()
        minimum_text = str(minimum or "medium").strip().lower()
        if order.get(current_text, 1) >= order.get(minimum_text, 1):
            return current_text
        return minimum_text

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
