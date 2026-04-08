# quality/__init__.py
"""
质量评估子系统

提供研究成果质量评分、指标计算和 GRADE 合规校验能力。
"""

import importlib as _importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evidence_grader import (
        BiasRiskAssessment,
        EvidenceGrader,
        GRADEResult,
        StudyGRADEAssessment,
        StudyRecord,
    )
    from .quality_assessor import (
        ComplianceReport,
        QualityAssessor,
        QualityScore,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "BiasRiskAssessment": ("src.quality.evidence_grader", "BiasRiskAssessment"),
    "EvidenceGrader": ("src.quality.evidence_grader", "EvidenceGrader"),
    "GRADEResult": ("src.quality.evidence_grader", "GRADEResult"),
    "QualityAssessor": ("src.quality.quality_assessor", "QualityAssessor"),
    "QualityScore": ("src.quality.quality_assessor", "QualityScore"),
    "ComplianceReport": ("src.quality.quality_assessor", "ComplianceReport"),
    "StudyGRADEAssessment": ("src.quality.evidence_grader", "StudyGRADEAssessment"),
    "StudyRecord": ("src.quality.evidence_grader", "StudyRecord"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
