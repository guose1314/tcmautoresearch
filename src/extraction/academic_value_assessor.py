"""学术价值评估辅助模块 — 对提取结果进行学术研究价值多维评分。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from src.extraction.base import (
    ExtractedItem,
    ExtractionRelation,
    ExtractionResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 评估维度
# ---------------------------------------------------------------------------

@dataclass
class AcademicValueReport:
    """学术价值评估报告。"""
    overall_score: float = 0.0              # 0~100
    information_density: float = 0.0        # 信息密度 0~1
    entity_diversity: float = 0.0           # 实体类型多样性 0~1
    relation_richness: float = 0.0          # 关系丰富度 0~1
    formula_novelty: float = 0.0            # 方剂创新性 0~1
    cross_reference_density: float = 0.0    # 交叉引用密度 0~1
    historical_significance: float = 0.0    # 历史文献价值 0~1
    clinical_relevance: float = 0.0         # 临床关联性 0~1
    completeness: float = 0.0              # 数据完整性 0~1
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    grade: str = ""                         # A / B / C / D

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2),
            "grade": self.grade,
            "dimension_scores": {k: round(v, 3) for k, v in self.dimension_scores.items()},
            "information_density": round(self.information_density, 3),
            "entity_diversity": round(self.entity_diversity, 3),
            "relation_richness": round(self.relation_richness, 3),
            "formula_novelty": round(self.formula_novelty, 3),
            "cross_reference_density": round(self.cross_reference_density, 3),
            "historical_significance": round(self.historical_significance, 3),
            "clinical_relevance": round(self.clinical_relevance, 3),
            "completeness": round(self.completeness, 3),
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# 评估器
# ---------------------------------------------------------------------------

# 各朝代基础历史权重
_DYNASTY_WEIGHT: Dict[str, float] = {
    "先秦": 1.0, "秦": 0.95, "汉": 0.95, "西汉": 0.95, "东汉": 0.95,
    "三国": 0.90, "魏": 0.90, "晋": 0.88, "南北朝": 0.85,
    "隋": 0.82, "唐": 0.80, "五代": 0.78,
    "宋": 0.75, "北宋": 0.75, "南宋": 0.75,
    "金": 0.73, "元": 0.70, "明": 0.65, "清": 0.55,
    "民国": 0.45, "现代": 0.30, "当代": 0.25,
}

# 临床关联实体类型
_CLINICAL_TYPES: Set[str] = {
    "formula", "herb", "syndrome", "disease", "symptom",
    "dosage", "indication", "contraindication", "administration",
}

# 维度权重
_DIMENSION_WEIGHTS: Dict[str, float] = {
    "information_density": 0.15,
    "entity_diversity": 0.10,
    "relation_richness": 0.15,
    "formula_novelty": 0.10,
    "cross_reference_density": 0.10,
    "historical_significance": 0.10,
    "clinical_relevance": 0.15,
    "completeness": 0.15,
}


class AcademicValueAssessor:
    """学术价值评估器。

    对文献提取结果从 8 个维度进行定量评分，
    输出 AcademicValueReport 和 ExtractionResult。
    """

    MODULE_NAME = "academic_value_assessor"

    def __init__(
        self,
        known_formulas: Optional[Set[str]] = None,
        dimension_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self._known_formulas = known_formulas or set()
        self._weights = dimension_weights or dict(_DIMENSION_WEIGHTS)

    def assess(
        self,
        items: List[ExtractedItem],
        relations: List[ExtractionRelation],
        text_length: int = 0,
        dynasty: str = "",
    ) -> AcademicValueReport:
        """执行多维学术价值评估。"""
        report = AcademicValueReport()

        report.information_density = self._calc_information_density(items, text_length)
        report.entity_diversity = self._calc_entity_diversity(items)
        report.relation_richness = self._calc_relation_richness(items, relations)
        report.formula_novelty = self._calc_formula_novelty(items)
        report.cross_reference_density = self._calc_cross_reference_density(relations)
        report.historical_significance = self._calc_historical_significance(dynasty)
        report.clinical_relevance = self._calc_clinical_relevance(items)
        report.completeness = self._calc_completeness(items, relations)

        report.dimension_scores = {
            "information_density": report.information_density,
            "entity_diversity": report.entity_diversity,
            "relation_richness": report.relation_richness,
            "formula_novelty": report.formula_novelty,
            "cross_reference_density": report.cross_reference_density,
            "historical_significance": report.historical_significance,
            "clinical_relevance": report.clinical_relevance,
            "completeness": report.completeness,
        }

        # 加权综合得分（0~100）
        report.overall_score = sum(
            score * self._weights.get(dim, 0.0) * 100
            for dim, score in report.dimension_scores.items()
        )

        report.grade = self._grade(report.overall_score)
        report.recommendations = self._generate_recommendations(report)
        return report

    def assess_as_result(
        self,
        items: List[ExtractedItem],
        relations: List[ExtractionRelation],
        text_length: int = 0,
        dynasty: str = "",
    ) -> ExtractionResult:
        """输出 ExtractionResult 形式的评估结果（方便管道集成）。"""
        import time
        t0 = time.perf_counter()
        report = self.assess(items, relations, text_length, dynasty)
        duration = time.perf_counter() - t0
        return ExtractionResult(
            module_name=self.MODULE_NAME,
            statistics=report.to_dict(),
            quality_scores=report.dimension_scores,
            duration_sec=duration,
        )

    # ------------------------------------------------------------------
    # 维度计算
    # ------------------------------------------------------------------

    def _calc_information_density(self, items: List[ExtractedItem], text_length: int) -> float:
        if text_length <= 0:
            return 0.0
        entity_chars = sum(i.length for i in items)
        ratio = entity_chars / text_length
        return min(ratio * 5.0, 1.0)  # 20% 覆盖 → 满分

    def _calc_entity_diversity(self, items: List[ExtractedItem]) -> float:
        if not items:
            return 0.0
        types = {i.entity_type for i in items}
        return min(len(types) / 8.0, 1.0)  # 8 种类型 → 满分

    def _calc_relation_richness(
        self, items: List[ExtractedItem], relations: List[ExtractionRelation]
    ) -> float:
        if not items:
            return 0.0
        ratio = len(relations) / max(len(items), 1)
        return min(ratio / 0.5, 1.0)  # 每 2 个实体 1 条关系 → 满分

    def _calc_formula_novelty(self, items: List[ExtractedItem]) -> float:
        """方剂创新性: 出现了不在 known_formulas 中的方剂。"""
        formula_items = [i for i in items if i.entity_type == "formula"]
        if not formula_items:
            return 0.5  # 中性
        if not self._known_formulas:
            return 0.5
        novel_count = sum(
            1 for i in formula_items if i.name not in self._known_formulas
        )
        return min(novel_count / max(len(formula_items), 1), 1.0)

    def _calc_cross_reference_density(self, relations: List[ExtractionRelation]) -> float:
        if not relations:
            return 0.0
        rel_types = {r.relation_type for r in relations}
        return min(len(rel_types) / 5.0, 1.0)  # 5 种关系类型 → 满分

    def _calc_historical_significance(self, dynasty: str) -> float:
        if not dynasty:
            return 0.5
        return _DYNASTY_WEIGHT.get(dynasty, 0.5)

    def _calc_clinical_relevance(self, items: List[ExtractedItem]) -> float:
        if not items:
            return 0.0
        clinical = sum(1 for i in items if i.entity_type in _CLINICAL_TYPES)
        return min(clinical / max(len(items), 1) / 0.6, 1.0)

    def _calc_completeness(
        self, items: List[ExtractedItem], relations: List[ExtractionRelation]
    ) -> float:
        """完整性: 是否同时包含方剂、药物、功效、证候。"""
        types = {i.entity_type for i in items}
        core = {"formula", "herb", "efficacy", "syndrome"}
        found = core & types
        return len(found) / len(core) if core else 0.0

    # ------------------------------------------------------------------
    # 等级 / 建议
    # ------------------------------------------------------------------

    def _grade(self, score: float) -> str:
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 50:
            return "C"
        return "D"

    def _generate_recommendations(self, report: AcademicValueReport) -> List[str]:
        recs: List[str] = []
        if report.information_density < 0.3:
            recs.append("信息密度偏低，建议检查实体匹配覆盖率或补充领域词典")
        if report.entity_diversity < 0.3:
            recs.append("实体类型单一，可尝试扩展疾病/证候/穴位等提取规则")
        if report.relation_richness < 0.3:
            recs.append("关系数量不足，建议补充组成/主治/功效关系提取规则")
        if report.completeness < 0.5:
            recs.append("核心要素不完整，缺少方剂/药物/功效/证候之一")
        if report.clinical_relevance < 0.3:
            recs.append("临床关联性低，文本可能以理论/注解为主")
        return recs
