"""GRADE 证据分级与简化偏倚风险评估。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional

from src.collector.literature_retriever import LiteratureRecord

from .quality_assessor import (
    GRADE_HIGH,
    GRADE_LOW,
    GRADE_MODERATE,
    GRADE_VERY_LOW,
)

BIAS_LOW = "low"
BIAS_MODERATE = "moderate"
BIAS_HIGH = "high"

_DESIGN_SCORES = {
    "meta_analysis": 0.95,
    "systematic_review": 0.9,
    "randomized_controlled_trial": 0.88,
    "non_randomized_intervention": 0.72,
    "cohort": 0.6,
    "case_control": 0.55,
    "cross_sectional": 0.45,
    "observational": 0.45,
    "case_series": 0.3,
    "case_report": 0.2,
    "expert_opinion": 0.15,
    "unknown": 0.35,
}

_DESIGN_KEYWORDS = [
    ("meta_analysis", ["meta-analysis", "meta analysis", "荟萃分析"]),
    (
        "systematic_review",
        ["systematic review", "系统综述", "evidence synthesis"],
    ),
    (
        "randomized_controlled_trial",
        [
            "randomized controlled trial",
            "randomised controlled trial",
            "double-blind",
            "双盲",
            "随机对照",
            "随机分组",
            "rct",
        ],
    ),
    (
        "non_randomized_intervention",
        ["non-randomized", "nonrandomized", "quasi-experimental", "before-after", "非随机"],
    ),
    ("cohort", ["cohort", "队列研究", "prospective cohort", "retrospective cohort"]),
    ("case_control", ["case-control", "case control", "病例对照"]),
    ("cross_sectional", ["cross-sectional", "cross sectional", "横断面"]),
    ("case_series", ["case series", "病例系列"]),
    ("case_report", ["case report", "病例报告"]),
    ("expert_opinion", ["expert opinion", "consensus", "guideline", "专家共识", "指南"]),
    ("observational", ["observational", "观察性"]),
]

_SAMPLE_SIZE_PATTERNS = [
    re.compile(r"\b[nN]\s*=\s*(\d{1,5})\b"),
    re.compile(r"\b(\d{2,5})\s+(?:patients|participants|subjects|cases)\b", re.IGNORECASE),
    re.compile(r"纳入(?:了)?\s*(\d{1,5})\s*例"),
    re.compile(r"共\s*(\d{1,5})\s*例"),
    re.compile(r"(\d{1,5})\s*例(?:患者|受试者|病例)"),
    re.compile(r"包括\s*(\d{1,5})\s*名(?:患者|受试者)?"),
]

_CONSISTENCY_POSITIVE_TERMS = [
    "consistent",
    "consistently",
    "low heterogeneity",
    "一致",
    "结果稳定",
    "稳健",
]
_CONSISTENCY_NEGATIVE_TERMS = [
    "heterogeneity",
    "inconsistent",
    "mixed findings",
    "结果不一致",
    "异质性较高",
    "差异较大",
]

_PREPRINT_SOURCES = {"arxiv", "iorxiv"}
_CURATED_SOURCES = {"pubmed", "medline_api", "semantic_scholar", "plos_one"}


@dataclass
class StudyRecord:
    source: str
    title: str
    authors: List[str]
    year: Optional[int]
    doi: str
    url: str
    abstract: str
    citation_count: Optional[int]
    external_id: str
    study_design: str = ""
    sample_size: Optional[int] = None
    consistency_score: Optional[float] = None
    precision_score: Optional[float] = None
    confidence_interval_width: Optional[float] = None
    publication_bias_score: Optional[float] = None
    peer_reviewed: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def study_id(self) -> str:
        if self.doi:
            return self.doi
        if self.external_id:
            return self.external_id
        return self.title or f"{self.source}:{self.year or 'unknown'}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_literature_record(cls, record: Any) -> "StudyRecord":
        if isinstance(record, cls):
            return record

        payload = _coerce_mapping(record)
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            source=str(payload.get("source") or ""),
            title=str(payload.get("title") or ""),
            authors=[str(item) for item in (payload.get("authors") or []) if str(item).strip()],
            year=_coerce_optional_int(payload.get("year")),
            doi=str(payload.get("doi") or ""),
            url=str(payload.get("url") or ""),
            abstract=str(payload.get("abstract") or ""),
            citation_count=_coerce_optional_int(payload.get("citation_count")),
            external_id=str(payload.get("external_id") or ""),
            study_design=str(payload.get("study_design") or metadata.get("study_design") or ""),
            sample_size=_coerce_optional_int(payload.get("sample_size") or metadata.get("sample_size")),
            consistency_score=_coerce_optional_float(
                payload.get("consistency_score") or metadata.get("consistency_score")
            ),
            precision_score=_coerce_optional_float(
                payload.get("precision_score") or metadata.get("precision_score")
            ),
            confidence_interval_width=_coerce_optional_float(
                payload.get("confidence_interval_width") or metadata.get("confidence_interval_width")
            ),
            publication_bias_score=_coerce_optional_float(
                payload.get("publication_bias_score") or metadata.get("publication_bias_score")
            ),
            peer_reviewed=_coerce_optional_bool(
                payload.get("peer_reviewed")
                if "peer_reviewed" in payload
                else metadata.get("peer_reviewed")
            ),
            metadata=metadata,
        )


@dataclass
class BiasRiskAssessment:
    study_id: str
    overall_risk: str
    selection_bias: str
    measurement_bias: str
    confounding_bias: str
    reporting_bias: str
    score: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StudyGRADEAssessment:
    study_id: str
    title: str
    study_design: str
    sample_size: Optional[int]
    grade_level: str
    grade_score: float
    bias_assessment: BiasRiskAssessment
    factor_scores: Dict[str, float] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["bias_assessment"] = self.bias_assessment.to_dict()
        return payload


@dataclass
class GRADEResult:
    overall_grade: str
    overall_score: float
    study_count: int
    factor_averages: Dict[str, float] = field(default_factory=dict)
    bias_risk_distribution: Dict[str, int] = field(default_factory=dict)
    study_results: List[StudyGRADEAssessment] = field(default_factory=list)
    summary: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_grade": self.overall_grade,
            "overall_score": self.overall_score,
            "study_count": self.study_count,
            "factor_averages": dict(self.factor_averages),
            "bias_risk_distribution": dict(self.bias_risk_distribution),
            "study_results": [item.to_dict() for item in self.study_results],
            "summary": list(self.summary),
        }


class EvidenceGrader:
    """GRADE 证据质量评级器。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.grade_thresholds = {
            GRADE_HIGH: float(self.config.get("grade_high_threshold", 0.8)),
            GRADE_MODERATE: float(self.config.get("grade_moderate_threshold", 0.6)),
            GRADE_LOW: float(self.config.get("grade_low_threshold", 0.4)),
        }

    def grade_evidence(self, studies: List[StudyRecord]) -> GRADEResult:
        normalized = [StudyRecord.from_literature_record(item) for item in studies or []]
        if not normalized:
            return GRADEResult(
                overall_grade=GRADE_VERY_LOW,
                overall_score=0.0,
                study_count=0,
                summary=["未提供可评估的研究记录"],
            )

        study_results: List[StudyGRADEAssessment] = []
        factor_buckets: Dict[str, List[float]] = {
            "design": [],
            "sample_size": [],
            "consistency": [],
            "precision": [],
            "publication_bias": [],
            "bias_risk": [],
        }

        for study in normalized:
            assessment = self._grade_single_study(study)
            study_results.append(assessment)
            for key, value in assessment.factor_scores.items():
                factor_buckets.setdefault(key, []).append(value)

        overall_score = round(
            sum(item.grade_score for item in study_results) / len(study_results),
            4,
        )
        factor_averages = {
            key: round(sum(values) / len(values), 4)
            for key, values in factor_buckets.items()
            if values
        }
        if factor_averages.get("consistency", 1.0) < 0.55:
            overall_score = round(max(0.0, overall_score - 0.05), 4)
        if factor_averages.get("publication_bias", 1.0) < 0.5:
            overall_score = round(max(0.0, overall_score - 0.05), 4)

        bias_distribution = Counter(item.bias_assessment.overall_risk for item in study_results)
        overall_grade = self._score_to_grade(overall_score)
        summary = [
            f"纳入 {len(study_results)} 项研究进行 GRADE 评估",
            f"整体证据等级为 {overall_grade}，平均评分 {overall_score:.2f}",
            "偏倚风险分布："
            + "、".join(f"{key} {value} 项" for key, value in sorted(bias_distribution.items()))
            if bias_distribution
            else "偏倚风险分布：无",
        ]

        return GRADEResult(
            overall_grade=overall_grade,
            overall_score=overall_score,
            study_count=len(study_results),
            factor_averages=factor_averages,
            bias_risk_distribution=dict(bias_distribution),
            study_results=study_results,
            summary=summary,
        )

    def assess_bias_risk(self, study: Any) -> BiasRiskAssessment:
        record = StudyRecord.from_literature_record(study)
        design = self._resolve_study_design(record)
        sample_size = self._resolve_sample_size(record)
        abstract_length = len(record.abstract.strip())

        selection_bias = self._selection_bias(design, sample_size)
        measurement_bias = self._measurement_bias(design, abstract_length)
        confounding_bias = self._confounding_bias(design)
        reporting_bias = self._reporting_bias(record, abstract_length)

        risk_values = {
            "selection_bias": selection_bias,
            "measurement_bias": measurement_bias,
            "confounding_bias": confounding_bias,
            "reporting_bias": reporting_bias,
        }
        penalty = sum(_bias_penalty(value) for value in risk_values.values()) / max(1, len(risk_values))
        if penalty >= 0.67:
            overall_risk = BIAS_HIGH
        elif penalty >= 0.34:
            overall_risk = BIAS_MODERATE
        else:
            overall_risk = BIAS_LOW

        reasons: List[str] = []
        if sample_size is None:
            reasons.append("未显式识别到样本量，选择偏倚与不精确风险上升")
        elif sample_size < 50:
            reasons.append(f"样本量较小（n={sample_size}），选择偏倚风险较高")
        if abstract_length < 60:
            reasons.append("摘要信息较少，测量与报告偏倚风险上升")
        if record.source.lower() in _PREPRINT_SOURCES:
            reasons.append("来源为预印本平台，报告偏倚风险较高")
        if not record.doi:
            reasons.append("缺少 DOI，发表偏倚与可追溯性较弱")

        return BiasRiskAssessment(
            study_id=record.study_id,
            overall_risk=overall_risk,
            selection_bias=selection_bias,
            measurement_bias=measurement_bias,
            confounding_bias=confounding_bias,
            reporting_bias=reporting_bias,
            score=round(max(0.0, 1.0 - penalty), 4),
            reasons=reasons,
        )

    def _grade_single_study(self, study: StudyRecord) -> StudyGRADEAssessment:
        design = self._resolve_study_design(study)
        sample_size = self._resolve_sample_size(study)
        bias_assessment = self.assess_bias_risk(study)
        factor_scores = {
            "design": _DESIGN_SCORES.get(design, _DESIGN_SCORES["unknown"]),
            "sample_size": self._sample_size_score(sample_size),
            "consistency": self._resolve_consistency_score(study, design),
            "precision": self._resolve_precision_score(study, sample_size, design),
            "publication_bias": self._resolve_publication_bias_score(study),
            "bias_risk": bias_assessment.score,
        }
        grade_score = round(
            factor_scores["design"] * 0.28
            + factor_scores["sample_size"] * 0.18
            + factor_scores["consistency"] * 0.14
            + factor_scores["precision"] * 0.14
            + factor_scores["publication_bias"] * 0.12
            + factor_scores["bias_risk"] * 0.14,
            4,
        )
        grade_level = self._score_to_grade(grade_score)

        rationale = [f"研究设计识别为 {design}"]
        if sample_size is not None:
            rationale.append(f"识别样本量 n={sample_size}")
        rationale.append(f"偏倚风险评估为 {bias_assessment.overall_risk}")
        if factor_scores["publication_bias"] < 0.5:
            rationale.append("发表偏倚风险较高，降低整体证据等级")
        if factor_scores["precision"] < 0.5:
            rationale.append("精确性较弱，提示估计不稳定")
        if factor_scores["consistency"] < 0.6:
            rationale.append("一致性不足，研究结果之间可能存在异质性")

        return StudyGRADEAssessment(
            study_id=study.study_id,
            title=study.title,
            study_design=design,
            sample_size=sample_size,
            grade_level=grade_level,
            grade_score=grade_score,
            bias_assessment=bias_assessment,
            factor_scores=factor_scores,
            rationale=rationale,
        )

    def _resolve_study_design(self, study: StudyRecord) -> str:
        explicit = str(study.study_design or "").strip().lower()
        if explicit:
            return self._normalize_design_label(explicit)

        haystack = f"{study.title} {study.abstract}".lower()
        for canonical_name, terms in _DESIGN_KEYWORDS:
            if any(term in haystack for term in terms):
                return canonical_name
        return "unknown"

    def _resolve_sample_size(self, study: StudyRecord) -> Optional[int]:
        if study.sample_size is not None:
            return study.sample_size

        haystack = f"{study.title} {study.abstract}"
        matches: List[int] = []
        for pattern in _SAMPLE_SIZE_PATTERNS:
            for result in pattern.findall(haystack):
                try:
                    matches.append(int(result))
                except (TypeError, ValueError):
                    continue
        return max(matches) if matches else None

    def _resolve_consistency_score(self, study: StudyRecord, design: str) -> float:
        if study.consistency_score is not None:
            return _clamp(study.consistency_score)

        haystack = f"{study.title} {study.abstract}".lower()
        if any(term in haystack for term in _CONSISTENCY_NEGATIVE_TERMS):
            return 0.4
        if any(term in haystack for term in _CONSISTENCY_POSITIVE_TERMS):
            return 0.85
        if design in {"meta_analysis", "systematic_review", "randomized_controlled_trial"}:
            return 0.78
        if design in {"cohort", "case_control", "non_randomized_intervention"}:
            return 0.68
        if design in {"cross_sectional", "observational"}:
            return 0.58
        return 0.5

    def _resolve_precision_score(
        self,
        study: StudyRecord,
        sample_size: Optional[int],
        design: str,
    ) -> float:
        if study.precision_score is not None:
            return _clamp(study.precision_score)
        if study.confidence_interval_width is not None:
            ci_width = max(0.0, study.confidence_interval_width)
            if ci_width <= 0.15:
                return 0.9
            if ci_width <= 0.3:
                return 0.75
            if ci_width <= 0.5:
                return 0.55
            return 0.35
        if sample_size is None:
            return 0.5 if design != "unknown" else 0.4
        if sample_size >= 500:
            return 0.9
        if sample_size >= 200:
            return 0.8
        if sample_size >= 100:
            return 0.72
        if sample_size >= 50:
            return 0.58
        if sample_size >= 20:
            return 0.42
        return 0.28

    def _resolve_publication_bias_score(self, study: StudyRecord) -> float:
        if study.publication_bias_score is not None:
            return _clamp(study.publication_bias_score)

        source_name = study.source.lower()
        abstract_length = len(study.abstract.strip())
        score = 0.65
        if source_name in _CURATED_SOURCES:
            score += 0.15
        if source_name in _PREPRINT_SOURCES:
            score -= 0.25
        if study.peer_reviewed is False:
            score -= 0.15
        if study.peer_reviewed is True:
            score += 0.05
        if study.doi:
            score += 0.1
        else:
            score -= 0.15
        if abstract_length >= 120:
            score += 0.05
        elif abstract_length < 60:
            score -= 0.1
        if study.citation_count is not None and study.citation_count >= 50:
            score += 0.05
        return _clamp(score)

    def _sample_size_score(self, sample_size: Optional[int]) -> float:
        if sample_size is None:
            return 0.45
        if sample_size >= 500:
            return 1.0
        if sample_size >= 200:
            return 0.85
        if sample_size >= 100:
            return 0.75
        if sample_size >= 50:
            return 0.6
        if sample_size >= 20:
            return 0.4
        return 0.2

    def _selection_bias(self, design: str, sample_size: Optional[int]) -> str:
        if design in {"meta_analysis", "systematic_review", "randomized_controlled_trial"} and (sample_size or 0) >= 100:
            return BIAS_LOW
        if sample_size is None or (sample_size or 0) < 50:
            return BIAS_HIGH
        if design in {"case_series", "case_report", "expert_opinion", "unknown"}:
            return BIAS_HIGH
        return BIAS_MODERATE

    def _measurement_bias(self, design: str, abstract_length: int) -> str:
        if abstract_length < 40:
            return BIAS_HIGH
        if design in {"meta_analysis", "systematic_review", "randomized_controlled_trial"} and abstract_length >= 120:
            return BIAS_LOW
        if abstract_length >= 80:
            return BIAS_MODERATE
        return BIAS_HIGH

    def _confounding_bias(self, design: str) -> str:
        if design in {"meta_analysis", "systematic_review", "randomized_controlled_trial"}:
            return BIAS_LOW
        if design in {"cohort", "case_control", "non_randomized_intervention"}:
            return BIAS_MODERATE
        return BIAS_HIGH

    def _reporting_bias(self, study: StudyRecord, abstract_length: int) -> str:
        source_name = study.source.lower()
        if source_name in _PREPRINT_SOURCES or (not study.doi and abstract_length < 60):
            return BIAS_HIGH
        if not study.doi or abstract_length < 120:
            return BIAS_MODERATE
        return BIAS_LOW

    def _normalize_design_label(self, design: str) -> str:
        normalized = design.replace("-", "_").replace(" ", "_")
        aliases = {
            "rct": "randomized_controlled_trial",
            "randomised_controlled_trial": "randomized_controlled_trial",
            "randomized_controlled_trial": "randomized_controlled_trial",
            "meta_analysis": "meta_analysis",
            "systematic_review": "systematic_review",
            "cohort_study": "cohort",
            "case_control_study": "case_control",
            "cross_sectional_study": "cross_sectional",
        }
        return aliases.get(normalized, normalized if normalized in _DESIGN_SCORES else "unknown")

    def _score_to_grade(self, score: float) -> str:
        if score >= self.grade_thresholds[GRADE_HIGH]:
            return GRADE_HIGH
        if score >= self.grade_thresholds[GRADE_MODERATE]:
            return GRADE_MODERATE
        if score >= self.grade_thresholds[GRADE_LOW]:
            return GRADE_LOW
        return GRADE_VERY_LOW


def _coerce_mapping(record: Any) -> Dict[str, Any]:
    if isinstance(record, dict):
        return dict(record)
    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, LiteratureRecord):
        return asdict(record)

    keys = [
        "source",
        "title",
        "authors",
        "year",
        "doi",
        "url",
        "abstract",
        "citation_count",
        "external_id",
        "study_design",
        "sample_size",
        "consistency_score",
        "precision_score",
        "confidence_interval_width",
        "publication_bias_score",
        "peer_reviewed",
        "metadata",
    ]
    return {
        key: getattr(record, key)
        for key in keys
        if hasattr(record, key)
    }


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    value_str = str(value).strip().lower()
    if value_str in {"true", "1", "yes", "y"}:
        return True
    if value_str in {"false", "0", "no", "n"}:
        return False
    return None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, float(value))), 4)


def _bias_penalty(risk_level: str) -> float:
    penalties = {
        BIAS_LOW: 0.1,
        BIAS_MODERATE: 0.45,
        BIAS_HIGH: 0.8,
    }
    return penalties.get(risk_level, 0.45)


__all__ = [
    "BIAS_HIGH",
    "BIAS_LOW",
    "BIAS_MODERATE",
    "BiasRiskAssessment",
    "EvidenceGrader",
    "GRADEResult",
    "StudyGRADEAssessment",
    "StudyRecord",
]