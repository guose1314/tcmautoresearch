"""CollationContext: 调度四校策略并聚合结果。"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


class CollationContextError(RuntimeError):
    """Collation 上下文错误。"""


_DEFAULT_STRATEGIES: tuple[str, ...] = ("cross", "intra", "external", "rational")


@dataclass
class StrategyResult:
    """单策略产出。"""

    name: str
    succeeded: bool
    payload: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CollationReport:
    """Collation 总报告。"""

    document_id: str
    strategies: Dict[str, StrategyResult] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "strategies": {k: v.to_dict() for k, v in self.strategies.items()},
            "summary": {
                "total": len(self.strategies),
                "succeeded": sum(1 for r in self.strategies.values() if r.succeeded),
                "failed": sum(1 for r in self.strategies.values() if not r.succeeded),
            },
        }


class CollationContext:
    """协调 cross / intra / external / rational 四校。

    各依赖（philology_service / neo4j_driver / literature_retriever / self_refine_runner /
    db_session_factory）均可为 ``None`` —— 缺失时对应策略会被标记 ``succeeded=False``，
    并给出 error 说明，但不会阻断其他策略执行。
    """

    def __init__(
        self,
        *,
        philology_service: Any = None,
        neo4j_driver: Any = None,
        literature_retriever: Any = None,
        self_refine_runner: Any = None,
        db_session_factory: Any = None,
        neo4j_database: str = "neo4j",
        external_sources: Optional[Sequence[str]] = None,
    ) -> None:
        from .strategies.cross import CrossCollationStrategy
        from .strategies.external import ExternalCollationStrategy
        from .strategies.intra import IntraCollationStrategy
        from .strategies.rational import RationalCollationStrategy

        self._strategies = {
            "cross": CrossCollationStrategy(philology_service=philology_service),
            "intra": IntraCollationStrategy(
                neo4j_driver=neo4j_driver, neo4j_database=neo4j_database
            ),
            "external": ExternalCollationStrategy(
                literature_retriever=literature_retriever,
                db_session_factory=db_session_factory,
                sources=tuple(external_sources or ("arxiv", "google_scholar")),
            ),
            "rational": RationalCollationStrategy(
                self_refine_runner=self_refine_runner
            ),
        }

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #

    def collate(
        self,
        document_id: str,
        strategies: Sequence[str] = _DEFAULT_STRATEGIES,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> CollationReport:
        if not document_id or not isinstance(document_id, str):
            raise CollationContextError("collate() requires a non-empty document_id")
        ctx = dict(context or {})
        report = CollationReport(document_id=document_id)
        for name in strategies:
            key = (name or "").strip().lower()
            strategy = self._strategies.get(key)
            if strategy is None:
                report.strategies[key] = StrategyResult(
                    name=key,
                    succeeded=False,
                    error=f"unknown strategy: {name!r}",
                )
                continue
            try:
                payload = strategy.run(document_id, context=ctx) or {}
                if not isinstance(payload, Mapping):
                    payload = {"value": payload}
                report.strategies[key] = StrategyResult(
                    name=key, succeeded=True, payload=dict(payload)
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("collation strategy %s failed", key)
                report.strategies[key] = StrategyResult(
                    name=key,
                    succeeded=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
        return report


__all__ = [
    "CollationContext",
    "CollationContextError",
    "CollationReport",
    "StrategyResult",
]
