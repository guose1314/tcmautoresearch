"""GraphWeightUpdater：把 :class:`TranslationPlan.graph_weight_actions` 写回 Neo4j。

Cypher 模板（覆盖匹配多 label）::

    MATCH (n) WHERE n.id IN $ids
    SET n.weight = coalesce(n.weight, 1.0) * $factor

返回 ``{"applied": N, "skipped": M, "actions": [...]}``。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from .feedback_translator import GraphWeightAction, TranslationPlan

logger = logging.getLogger(__name__)


_CYPHER_APPLY_WEIGHT = (
    "MATCH (n) WHERE n.id IN $ids "
    "SET n.weight = coalesce(n.weight, 1.0) * $factor "
    "RETURN count(n) AS updated"
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
            return {"applied": 0, "skipped": len(actions), "error": "neo4j driver missing"}

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
            return {"applied": 0, "skipped": len(actions), "actions": traces, "dry_run": True}

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
                return int(single.get("updated") if hasattr(single, "get") else single["updated"])
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


__all__ = ["GraphWeightUpdater"]
