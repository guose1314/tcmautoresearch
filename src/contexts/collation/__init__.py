"""T4.1: Collation 上下文 — 中医文献四校（cross / intra / external / rational）。

四种校勘策略：
  - ``cross``：跨版本对校 — 适配 ``PhilologyService._build_version_collation``。
  - ``intra``：本校 — 在 Neo4j 同一 Document 子图内寻找 entity 共现的"前后呼应/矛盾"对。
  - ``external``：他校 — 调用 ``LiteratureRetriever``（默认 arxiv + google_scholar），
    结果落入 ``external_evidence`` 表。
  - ``rational``：理校 — 调 ``SelfRefineRunner`` 做"依理推断"。

公共契约：每种策略实现 ``Strategy.run(document_id, *, context) -> dict``，返回值统一并入
``CollationReport.strategies[<name>]``。
"""

from __future__ import annotations

from .service import (
    CollationContext,
    CollationContextError,
    CollationReport,
    StrategyResult,
)
from .strategies.cross import CrossCollationStrategy
from .strategies.external import ExternalCollationStrategy
from .strategies.intra import IntraCollationStrategy
from .strategies.rational import RationalCollationStrategy

__all__ = [
    "CollationContext",
    "CollationContextError",
    "CollationReport",
    "StrategyResult",
    "CrossCollationStrategy",
    "IntraCollationStrategy",
    "ExternalCollationStrategy",
    "RationalCollationStrategy",
]
