# quality/__init__.py
"""
质量评估子系统

提供研究成果质量评分、指标计算和 GRADE 合规校验能力。
"""

from importlib import import_module

from .quality_assessor import (
    ComplianceReport,
    QualityAssessor,
    QualityScore,
)

_evidence_grader = import_module("src.quality.evidence_grader")

BiasRiskAssessment = _evidence_grader.BiasRiskAssessment
EvidenceGrader = _evidence_grader.EvidenceGrader
GRADEResult = _evidence_grader.GRADEResult
StudyGRADEAssessment = _evidence_grader.StudyGRADEAssessment
StudyRecord = _evidence_grader.StudyRecord

__all__ = [
    "BiasRiskAssessment",
    "EvidenceGrader",
    "GRADEResult",
    "QualityAssessor",
    "QualityScore",
    "ComplianceReport",
    "StudyGRADEAssessment",
    "StudyRecord",
]
