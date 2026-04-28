"""ExpertFeedbackLoop — 专家在环反馈编码器。

设计目标
========

把 ReviewWorkbench 中专家裁决（``ReviewDispute``）关闭后的结论，
结构化成 :class:`src.contexts.lfitl.FeedbackEntry` 兼容的 ``record`` 字典，
追加写入 ``research_learning_feedback`` 表，让 LFITL 在下一轮 ``prepare_cycle``
里直接消费。

旧版 ExpertFeedbackLoop 只面向 LLMStrategy 持久化（保留原 API 兼容上层调用），
新增 :meth:`from_review_dispute` / :meth:`record_dispute_feedback` /
:meth:`attach_to_repo` 三个方法接入 ReviewWorkbench dispute 闭环。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from src.contexts.lfitl import FeedbackEntry
from src.core.architecture import ModuleRegistry

logger = logging.getLogger(__name__)


_RESOLUTION_SEVERITY = {
    "rejected": "high",
    "needs_source": "high",
    "accepted": "medium",
    "no_change": "low",
}

_RESOLUTION_SCORE = {
    "rejected": 0.2,
    "needs_source": 0.4,
    "accepted": 0.85,
    "no_change": 0.7,
}


class ExpertFeedbackLoop:
    """知识固化 + 专家在环（HITL）。

    历史职责（保留兼容）：
      * :meth:`persist_strategy` — LLM 策略持久化。
      * :meth:`get_pending_reviews` / :meth:`expert_review` — 旧 dashboard 接口。

    T5.4 新增：
      * :meth:`from_review_dispute` — dispute → FeedbackEntry。
      * :meth:`record_dispute_feedback` — 把 dispute 写进 research_learning_feedback。
      * :meth:`attach_to_repo` — 注册到 ResearchSessionRepository 的 dispute hook。
    """

    def __init__(self, db_driver=None, neo4j_driver=None, repo: Any = None):
        self.db = db_driver
        self.neo4j = neo4j_driver
        # T5.4: 显式注入仓储，便于 record_dispute_feedback 写盘。
        self._repo = repo

    # ------------------------------------------------------------------
    # T5.4 新接口：Dispute → FeedbackEntry → research_learning_feedback
    # ------------------------------------------------------------------

    @staticmethod
    def from_review_dispute(dispute: Mapping[str, Any]) -> FeedbackEntry:
        """把单条 dispute payload 编码成 :class:`FeedbackEntry`。"""
        if not isinstance(dispute, Mapping):
            raise TypeError("dispute must be a mapping")
        resolution = str(dispute.get("resolution") or "").strip().lower()
        severity = _RESOLUTION_SEVERITY.get(resolution, "medium")
        asset_key = str(dispute.get("asset_key") or "")
        asset_type = str(dispute.get("asset_type") or "")
        case_id = str(dispute.get("case_id") or "")
        notes = str(dispute.get("resolution_notes") or "").strip()
        summary = str(dispute.get("summary") or "").strip()
        issues: List[Dict[str, Any]] = []
        if asset_key:
            issues.append(
                {
                    "field": asset_type or "asset",
                    "entity_id": asset_key,
                    "description": notes
                    or summary
                    or f"dispute {case_id} closed: {resolution}",
                }
            )
        violations: List[Dict[str, Any]] = []
        if resolution in {"rejected", "needs_source"}:
            violations.append(
                {
                    "rule_id": f"expert_dispute:{resolution}",
                    "severity": severity,
                    "case_id": case_id,
                }
            )
        return FeedbackEntry(
            source_phase=(
                f"review_workbench:{asset_type}" if asset_type else "review_workbench"
            ),
            issues=issues,
            violations=violations,
            graph_targets=[asset_key] if asset_key else [],
            severity=severity,
            issue_fields=[asset_type] if asset_type else [],
            extra={
                "dispute_case_id": case_id,
                "resolution": resolution,
                "arbitrator": dispute.get("arbitrator"),
                "dispute_status": dispute.get("dispute_status"),
            },
        )

    @classmethod
    def _build_feedback_record(cls, dispute: Mapping[str, Any]) -> Dict[str, Any]:
        entry = cls.from_review_dispute(dispute)
        resolution = entry.extra.get("resolution") or ""
        case_id = entry.extra.get("dispute_case_id") or ""
        score = _RESOLUTION_SCORE.get(resolution, 0.5)
        return {
            "feedback_scope": "expert_dispute",
            "source_phase": "review_workbench",
            "target_phase": "review_workbench",
            "feedback_status": "tracked",
            "overall_score": score,
            "grade_level": entry.severity,
            "issue_count": len(entry.issues),
            "weakness_count": 1 if resolution in {"rejected", "needs_source"} else 0,
            "strength_count": 1 if resolution == "accepted" else 0,
            "issues": entry.issues,
            "details": {
                "dispute": dict(dispute),
                "translated_entry": {
                    "source_phase": entry.source_phase,
                    "severity": entry.severity,
                    "graph_targets": entry.graph_targets,
                    "issue_fields": entry.issue_fields,
                    "violations": entry.violations,
                },
            },
            "metadata": {
                "origin": "expert_feedback_loop",
                "dispute_case_id": case_id,
                "resolution": resolution,
            },
        }

    def record_dispute_feedback(
        self,
        cycle_id: str,
        dispute: Mapping[str, Any],
        *,
        repo: Any = None,
    ) -> Optional[Dict[str, Any]]:
        target_repo = repo or self._repo
        if target_repo is None or not hasattr(
            target_repo, "append_learning_feedback_record"
        ):
            logger.warning(
                "ExpertFeedbackLoop: repo 不可用或缺 append_learning_feedback_record，跳过写盘"
            )
            return None
        record = self._build_feedback_record(dispute)
        try:
            return target_repo.append_learning_feedback_record(cycle_id, record)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ExpertFeedbackLoop.record_dispute_feedback 失败: %s", exc)
            return None

    def attach_to_repo(self, repo: Any) -> None:
        """注册到 :class:`ResearchSessionRepository` 的 dispute hook。"""
        if repo is None:
            return
        self._repo = repo
        register = getattr(repo, "register_dispute_resolution_hook", None)
        if not callable(register):
            logger.warning(
                "ExpertFeedbackLoop.attach_to_repo: repo 缺少 register_dispute_resolution_hook"
            )
            return

        def _hook(cycle_id: str, dispute: Mapping[str, Any]) -> None:
            self.record_dispute_feedback(cycle_id, dispute, repo=repo)

        register(_hook)

    # ------------------------------------------------------------------
    # 旧接口（保留兼容）
    # ------------------------------------------------------------------

    def persist_strategy(
        self,
        task_id: str,
        strategy_data: Dict[str, Any],
        status: str = "pending_review",
    ) -> None:
        logger.info(f"Persisting strategy {task_id} to DB with status: {status}")
        if self.neo4j:
            try:
                cypher = (
                    "MERGE (s:LLMStrategy {task_id: $task_id}) "
                    "SET s.data = $data, s.status = $status"
                )
                with self.neo4j.driver.session(database=self.neo4j.database) as session:
                    session.run(
                        cypher, task_id=task_id, data=str(strategy_data), status=status
                    )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Neo4j Strategy Persistence Failed: {e}")

    def get_pending_reviews(self) -> List[Dict[str, Any]]:
        if not self.neo4j:
            return []
        try:
            cypher = (
                "MATCH (s:LLMStrategy {status: 'pending_review'}) "
                "RETURN s.task_id AS tid, s.data AS data"
            )
            with self.neo4j.driver.session(database=self.neo4j.database) as session:
                return [
                    {"task_id": r["tid"], "data": r["data"]}
                    for r in session.run(cypher)
                ]
        except Exception:
            return []

    def expert_review(self, task_id: str, action: str) -> bool:
        try:
            engine_info = ModuleRegistry.get_instance().get_module(
                "self_learning_engine"
            )
            if not engine_info or not getattr(engine_info, "instance", None):
                logger.error(
                    "SelfLearningEngine not found, cannot apply expert feedback."
                )
                return False
            engine = engine_info.instance
            if action == "approve":
                engine.apply_few_shot_feedback([task_id], 1.0)
                self.persist_strategy(task_id, {"expert_approved": True}, "approved")
                return True
            elif action == "reject":
                engine.apply_few_shot_feedback([task_id], 0.0)
                self.persist_strategy(task_id, {"expert_rejected": True}, "rejected")
                return True
            else:
                logger.warning(f"Unknown expert action: {action}")
                return False
        except Exception as e:  # noqa: BLE001
            logger.error(f"Expert review applying failed: {e}")
            return False


__all__ = ["ExpertFeedbackLoop"]
