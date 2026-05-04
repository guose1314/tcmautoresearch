"""GraphWeightUpdater：把 :class:`TranslationPlan.graph_weight_actions` 写回 Neo4j。

Cypher 模板（覆盖匹配多 label）::

    MATCH (n) WHERE n.id IN $ids
    SET n.weight = coalesce(n.weight, 1.0) * $factor

返回 ``{"applied": N, "skipped": M, "actions": [...]}``。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .feedback_translator import GraphWeightAction, TranslationPlan

logger = logging.getLogger(__name__)


_CYPHER_APPLY_WEIGHT = (
    "MATCH (n) WHERE n.id IN $ids "
    "SET n.weight = coalesce(n.weight, 1.0) * $factor "
    "RETURN count(n) AS updated"
)

LEARNING_INSIGHT_WEIGHT_TYPES = frozenset(
    {
        "evidence_weight",
        "prompt_bias",
        "method_policy",
        "candidate_edge",
        "candidate_rule_relation",
    }
)


class GraphWeightUpdater:
    """对 Neo4j 应用 ``weight *= factor``。"""

    def __init__(
        self,
        *,
        neo4j_driver: Any = None,
        neo4j_database: str = "neo4j",
        dry_run: bool = False,
    ) -> None:
        self._driver = neo4j_driver
        self._database = neo4j_database
        self._dry_run = bool(dry_run)

    # ------------------------------------------------------------------ #
    def apply(self, plan: TranslationPlan) -> Dict[str, Any]:
        actions = list(plan.graph_weight_actions)
        if not actions:
            return {"applied": 0, "skipped": 0, "actions": []}
        if self._driver is None and not self._dry_run:
            return {
                "applied": 0,
                "skipped": len(actions),
                "error": "neo4j driver missing",
            }

        applied = 0
        skipped = 0
        traces: List[Dict[str, Any]] = []
        opener = self._resolve_session_opener() if not self._dry_run else None

        if self._dry_run or opener is None:
            for action in actions:
                traces.append(
                    {
                        "node_ids": list(action.node_ids),
                        "factor": action.factor,
                        "updated": 0,
                        "dry_run": True,
                    }
                )
            return {
                "applied": 0,
                "skipped": len(actions),
                "actions": traces,
                "dry_run": True,
            }

        with opener(database=self._database) as session:
            for action in actions:
                if not action.node_ids or action.factor == 1.0:
                    skipped += 1
                    continue
                try:
                    result = session.run(
                        _CYPHER_APPLY_WEIGHT,
                        ids=list(action.node_ids),
                        factor=float(action.factor),
                    )
                    updated = self._extract_count(result)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("graph weight update failed")
                    traces.append(
                        {
                            "node_ids": list(action.node_ids),
                            "factor": action.factor,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    skipped += 1
                    continue
                applied += 1
                traces.append(
                    {
                        "node_ids": list(action.node_ids),
                        "factor": action.factor,
                        "updated": updated,
                    }
                )
        return {"applied": applied, "skipped": skipped, "actions": traces}

    def build_weight_hints_from_insights(
        self,
        insights: Sequence[Mapping[str, Any]],
        *,
        min_confidence: float = 0.0,
        now: Optional[datetime] = None,
        allowed_insight_types: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Convert active LearningInsight rows into GraphRAG ranking hints."""
        allowed_types = {
            str(item).strip().lower()
            for item in (allowed_insight_types or LEARNING_INSIGHT_WEIGHT_TYPES)
            if str(item).strip()
        }
        effective_now = _coerce_datetime(now) or datetime.now(timezone.utc)
        threshold = _clamp_confidence(min_confidence)
        hints: List[Dict[str, Any]] = []
        for item in insights or []:
            if not _is_eligible_weight_insight(
                item,
                allowed_types=allowed_types,
                min_confidence=threshold,
                now=effective_now,
            ):
                continue
            node_ids, relationship_ids, target_ids = _extract_hint_targets(item)
            if not node_ids and not relationship_ids and not target_ids:
                continue
            confidence = _clamp_confidence(item.get("confidence"))
            factor, effect, review_status, quality_meta = _resolve_review_factor(
                item, confidence
            )
            if factor == 1.0:
                continue
            hints.append(
                {
                    "insight_id": str(item.get("insight_id") or ""),
                    "source": str(item.get("source") or ""),
                    "target_phase": str(item.get("target_phase") or ""),
                    "insight_type": str(item.get("insight_type") or ""),
                    "confidence": confidence,
                    "boost": factor,
                    "factor": factor,
                    "effect": effect,
                    "review_status": review_status,
                    "node_ids": node_ids,
                    "relationship_ids": relationship_ids,
                    "target_ids": target_ids,
                    "reason": str(item.get("description") or ""),
                    **quality_meta,
                }
            )
        return hints

    # ------------------------------------------------------------------ #
    def _resolve_session_opener(self):
        inner = getattr(self._driver, "driver", None)
        if inner is not None and hasattr(inner, "session"):
            return inner.session
        if hasattr(self._driver, "session"):
            return self._driver.session
        raise RuntimeError("neo4j driver has no .session()")

    @staticmethod
    def _extract_count(result: Any) -> int:
        if result is None:
            return 0
        # neo4j Result-like
        try:
            single = result.single() if hasattr(result, "single") else None
        except Exception:
            single = None
        if single is not None:
            try:
                return int(
                    single.get("updated")
                    if hasattr(single, "get")
                    else single["updated"]
                )
            except Exception:
                return 0
        # fallback: iterable of records
        try:
            records = list(result)
        except Exception:
            return 0
        if not records:
            return 0
        first = records[0]
        if isinstance(first, Mapping):
            return int(first.get("updated") or 0)
        return 0


def _is_eligible_weight_insight(
    insight: Mapping[str, Any],
    *,
    allowed_types: set[str],
    min_confidence: float,
    now: datetime,
) -> bool:
    status = str(insight.get("status") or "active").strip().lower()
    if status not in {
        "active",
        "accepted",
        "rejected",
        "superseded",
    }:
        return False
    insight_type = str(insight.get("insight_type") or "").strip().lower()
    if insight_type not in allowed_types:
        return False
    review_status = _extract_review_status(insight) or status
    negative_feedback = review_status in {"rejected", "superseded"} or bool(
        _extract_repeated_error_type(insight)
    )
    if (
        _clamp_confidence(insight.get("confidence")) < min_confidence
        and not negative_feedback
    ):
        return False
    expires_at = _coerce_datetime(insight.get("expires_at"))
    if expires_at is not None and _as_aware_utc(expires_at) <= _as_aware_utc(now):
        return False
    return True


def _extract_hint_targets(
    insight: Mapping[str, Any],
) -> tuple[List[str], List[str], List[str]]:
    node_ids: List[str] = []
    relationship_ids: List[str] = []
    target_ids: List[str] = []
    refs = insight.get("evidence_refs_json") or insight.get("evidence_refs") or []
    if isinstance(refs, Mapping):
        refs = [refs]
    if not isinstance(refs, list):
        refs = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        _extend_unique(node_ids, ref.get("node_ids"))
        _extend_unique(node_ids, ref.get("graph_targets"))
        _append_unique(node_ids, ref.get("node_id"))
        _append_unique(node_ids, ref.get("entity_id"))
        _append_unique(node_ids, ref.get("source_entity_id"))
        _append_unique(node_ids, ref.get("target_entity_id"))
        _append_unique(node_ids, ref.get("claim_id"))
        _append_unique(node_ids, ref.get("evidence_claim_id"))
        _extend_unique(relationship_ids, ref.get("relationship_ids"))
        _append_unique(relationship_ids, ref.get("relationship_id"))
        _extend_unique(target_ids, ref.get("target_ids"))
        _extend_unique(target_ids, ref.get("ids"))
        _append_unique(target_ids, ref.get("target_id"))
        _append_unique(target_ids, ref.get("candidate_edge_id"))
        candidate_edge = ref.get("candidate_edge")
        if isinstance(candidate_edge, Mapping):
            _append_unique(node_ids, candidate_edge.get("source_entity_id"))
            _append_unique(node_ids, candidate_edge.get("target_entity_id"))
            _append_unique(target_ids, candidate_edge.get("candidate_edge_id"))
    _extend_unique(node_ids, insight.get("node_ids"))
    _extend_unique(relationship_ids, insight.get("relationship_ids"))
    _extend_unique(target_ids, insight.get("target_ids"))
    return node_ids, relationship_ids, target_ids


def _resolve_review_factor(
    insight: Mapping[str, Any], confidence: float
) -> tuple[float, str, str, Dict[str, Any]]:
    explicit = _explicit_factor(insight)
    status = str(insight.get("status") or "active").strip().lower()
    review_status = _extract_review_status(insight) or status
    evidence_grade = _extract_evidence_grade(insight)
    grounding_score = _extract_grounding_score(insight)
    repeated_error_type = _extract_repeated_error_type(insight)
    meta = {
        "evidence_grade": evidence_grade,
        "grounding_score": grounding_score,
        "repeated_error_type": repeated_error_type,
    }

    if explicit is not None:
        effect = "suppress" if explicit < 1.0 else "boost"
        return round(explicit, 4), effect, review_status, meta

    if review_status in {"rejected", "superseded"} or repeated_error_type:
        factor = 0.38
        if repeated_error_type:
            factor = 0.28
        if grounding_score is not None and grounding_score < 0.45:
            factor = min(factor, 0.32)
        if evidence_grade in {"D", "E"}:
            factor = min(factor, 0.3)
        return round(factor, 4), "suppress", review_status, meta

    insight_type = str(insight.get("insight_type") or "").strip().lower()
    if (
        insight_type
        in {"candidate_edge", "candidate_rule_relation", "weak_edge_candidate"}
        and review_status != "accepted"
    ):
        return 1.0, "neutral", review_status, meta

    factor = 1.0 + confidence * 0.35
    if review_status == "accepted":
        factor += 0.2
    factor += {"A": 0.18, "B": 0.1, "C": 0.04}.get(evidence_grade or "", 0.0)
    if grounding_score is not None:
        if grounding_score >= 0.85:
            factor += 0.12
        elif grounding_score >= 0.7:
            factor += 0.06
        elif grounding_score < 0.5:
            factor -= 0.18
    return round(max(1.02, min(factor, 1.75)), 4), "boost", review_status, meta


def _explicit_factor(insight: Mapping[str, Any]) -> Optional[float]:
    for key in ("boost", "weight_boost", "factor", "weight_factor"):
        if insight.get(key) in (None, ""):
            continue
        try:
            value = float(insight.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _extract_review_status(insight: Mapping[str, Any]) -> str:
    refs = _iter_refs(insight)
    for ref in reversed(refs):
        status = (
            str(ref.get("review_status") or ref.get("status") or "").strip().lower()
        )
        if status:
            return status
        vote = str(ref.get("expert_vote") or "").strip().lower()
        if vote in {"accepted", "rejected"}:
            return vote
    return str(insight.get("review_status") or "").strip().lower()


def _extract_evidence_grade(insight: Mapping[str, Any]) -> str:
    for source in [insight, *_iter_refs(insight)]:
        value = (
            str(source.get("evidence_grade") or source.get("grade") or "")
            .strip()
            .upper()
        )
        if value:
            return value[:1]
    return ""


def _extract_grounding_score(insight: Mapping[str, Any]) -> Optional[float]:
    for source in [insight, *_iter_refs(insight)]:
        for key in ("grounding_score", "grounding", "groundedness_score"):
            if source.get(key) in (None, ""):
                continue
            try:
                return _clamp_confidence(source.get(key))
            except (TypeError, ValueError):
                continue
    return None


def _extract_repeated_error_type(insight: Mapping[str, Any]) -> str:
    for source in [insight, *_iter_refs(insight)]:
        for key in ("repeated_error_type", "repeat_error_type", "error_type"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
        decision_type = str(source.get("decision_type") or "").strip()
        if decision_type == "relationship_type_error":
            return decision_type
    return ""


def _iter_refs(insight: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    refs = insight.get("evidence_refs_json") or insight.get("evidence_refs") or []
    if isinstance(refs, Mapping):
        refs = [refs]
    if not isinstance(refs, list):
        return []
    return [ref for ref in refs if isinstance(ref, Mapping)]


def _extend_unique(items: List[str], values: Any) -> None:
    if values in (None, ""):
        return
    if isinstance(values, (str, int, float)):
        _append_unique(items, values)
        return
    try:
        iterator = iter(values)
    except TypeError:
        _append_unique(items, values)
        return
    for value in iterator:
        _append_unique(items, value)


def _append_unique(items: List[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1.0:
        confidence = confidence / 100.0
    return max(0.0, min(1.0, confidence))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["GraphWeightUpdater", "LEARNING_INSIGHT_WEIGHT_TYPES"]
