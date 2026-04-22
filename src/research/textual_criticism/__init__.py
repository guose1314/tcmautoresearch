"""textual_criticism 子域 — 中医文献考据学（环节③）。

公开 API:
  - AuthenticityVerdict / VERDICT_CONTRACT_VERSION
  - DateVerdict / AuthorVerdict / Authenticity 枚举常量
  - assess_catalog_authenticity / assess_catalog_batch
  - build_textual_criticism_summary

依赖最小化：仅依赖 catalog_contract 字段名常量与 evidence 风格。
"""

from src.research.textual_criticism.verdict_contract import (
    AUTHENTICITY_AUTHENTIC,
    AUTHENTICITY_DOUBTFUL,
    AUTHENTICITY_FORGED,
    AUTHENTICITY_INDETERMINATE,
    AUTHENTICITY_LEVELS,
    AUTHOR_VERDICT_ANONYMOUS,
    AUTHOR_VERDICT_ATTRIBUTED,
    AUTHOR_VERDICT_CONFIRMED,
    AUTHOR_VERDICT_DISPUTED,
    AUTHOR_VERDICTS,
    DATE_VERDICT_CONFIRMED,
    DATE_VERDICT_DISPUTED,
    DATE_VERDICT_LEGENDARY,
    DATE_VERDICT_RANGE,
    DATE_VERDICT_UNKNOWN,
    DATE_VERDICTS,
    VERDICT_CONTRACT_VERSION,
    AuthenticityVerdict,
    VerdictEvidence,
    normalize_authenticity_verdicts,
)
from src.research.textual_criticism.textual_criticism_service import (
    TextualCriticismService,
    assess_catalog_authenticity,
    assess_catalog_batch,
    build_textual_criticism_summary,
)

__all__ = [
    "VERDICT_CONTRACT_VERSION",
    "AuthenticityVerdict",
    "VerdictEvidence",
    "DATE_VERDICTS",
    "DATE_VERDICT_CONFIRMED",
    "DATE_VERDICT_RANGE",
    "DATE_VERDICT_DISPUTED",
    "DATE_VERDICT_LEGENDARY",
    "DATE_VERDICT_UNKNOWN",
    "AUTHOR_VERDICTS",
    "AUTHOR_VERDICT_CONFIRMED",
    "AUTHOR_VERDICT_ATTRIBUTED",
    "AUTHOR_VERDICT_ANONYMOUS",
    "AUTHOR_VERDICT_DISPUTED",
    "AUTHENTICITY_LEVELS",
    "AUTHENTICITY_AUTHENTIC",
    "AUTHENTICITY_DOUBTFUL",
    "AUTHENTICITY_FORGED",
    "AUTHENTICITY_INDETERMINATE",
    "TextualCriticismService",
    "assess_catalog_authenticity",
    "assess_catalog_batch",
    "build_textual_criticism_summary",
    "normalize_authenticity_verdicts",
]
