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
    {"evidence_weight", "prompt_bias", "method_policy"}
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
            boost = _resolve_hint_boost(item, confidence)
            hints.append(
                {
                    "insight_id": str(item.get("insight_id") or ""),
                    "source": str(item.get("source") or ""),
                    "target_phase": str(item.get("target_phase") or ""),
                    "insight_type": str(item.get("insight_type") or ""),
                    "confidence": confidence,
                    "boost": boost,
                    "factor": boost,
                    "node_ids": node_ids,
                    "relationship_ids": relationship_ids,
                    "target_ids": target_ids,
                    "reason": str(item.get("description") or ""),
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
    if str(insight.get("status") or "active").strip().lower() != "active":
        return False
    insight_type = str(insight.get("insight_type") or "").strip().lower()
    if insight_type not in allowed_types:
        return False
    if _clamp_confidence(insight.get("confidence")) < min_confidence:
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
        _append_unique(node_ids, ref.get("claim_id"))
        _append_unique(node_ids, ref.get("evidence_claim_id"))
        _extend_unique(relationship_ids, ref.get("relationship_ids"))
        _append_unique(relationship_ids, ref.get("relationship_id"))
        _extend_unique(target_ids, ref.get("target_ids"))
        _extend_unique(target_ids, ref.get("ids"))
        _append_unique(target_ids, ref.get("target_id"))
    _extend_unique(node_ids, insight.get("node_ids"))
    _extend_unique(relationship_ids, insight.get("relationship_ids"))
    _extend_unique(target_ids, insight.get("target_ids"))
    return node_ids, relationship_ids, target_ids


def _resolve_hint_boost(insight: Mapping[str, Any], confidence: float) -> float:
    for key in ("boost", "weight_boost", "factor", "weight_factor"):
        if insight.get(key) in (None, ""):
            continue
        try:
            value = float(insight.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return round(1.0 + confidence, 4)


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
