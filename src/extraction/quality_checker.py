"""质量校验与可视化报告模块 — 对提取结果执行完整性/一致性/保真度校验并生成报告。"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.extraction.base import (
    ExtractedItem,
    ExtractionRelation,
    PipelineResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 质量校验结果
# ---------------------------------------------------------------------------

@dataclass
class QualityIssue:
    """单条质量问题。"""
    issue_id: str
    severity: str          # critical / warning / info
    category: str          # completeness / consistency / confidence / coverage
    message: str
    affected_entity: str = ""
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "issue_id": self.issue_id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
        }
        if self.affected_entity:
            d["affected_entity"] = self.affected_entity
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class QualityReport:
    """质量校验总报告。"""
    document_id: str = ""
    timestamp: str = ""
    overall_score: float = 0.0             # 0~100
    grade: str = ""
    issues: List[QualityIssue] = field(default_factory=list)
    completeness: Dict[str, float] = field(default_factory=dict)
    consistency: Dict[str, float] = field(default_factory=dict)
    confidence_distribution: Dict[str, int] = field(default_factory=dict)
    coverage: Dict[str, float] = field(default_factory=dict)
    entity_summary: Dict[str, int] = field(default_factory=dict)
    relation_summary: Dict[str, int] = field(default_factory=dict)
    module_durations: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "timestamp": self.timestamp,
            "overall_score": round(self.overall_score, 2),
            "grade": self.grade,
            "issues": [i.to_dict() for i in self.issues],
            "completeness": self.completeness,
            "consistency": self.consistency,
            "confidence_distribution": self.confidence_distribution,
            "coverage": self.coverage,
            "entity_summary": self.entity_summary,
            "relation_summary": self.relation_summary,
            "module_durations": self.module_durations,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# 提取质量报告",
            "",
            f"- **文档**: {self.document_id}",
            f"- **时间**: {self.timestamp}",
            f"- **综合评分**: {self.overall_score:.1f}/100 ({self.grade})",
            "",
            "## 实体统计",
        ]
        for etype, count in sorted(self.entity_summary.items()):
            lines.append(f"- {etype}: {count}")
        lines.append("")
        lines.append("## 关系统计")
        for rtype, count in sorted(self.relation_summary.items()):
            lines.append(f"- {rtype}: {count}")
        lines.append("")
        lines.append("## 置信度分布")
        for band, count in sorted(self.confidence_distribution.items()):
            lines.append(f"- {band}: {count}")
        lines.append("")
        if self.issues:
            lines.append("## 质量问题")
            for issue in self.issues:
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
                    issue.severity, "⚪"
                )
                lines.append(f"- {icon} [{issue.severity}] {issue.message}")
                if issue.suggestion:
                    lines.append(f"  - 建议: {issue.suggestion}")
        lines.append("")
        if self.module_durations:
            lines.append("## 模块耗时")
            for mod, sec in sorted(self.module_durations.items()):
                lines.append(f"- {mod}: {sec:.3f}s")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 质量校验器
# ---------------------------------------------------------------------------

class QualityChecker:
    """质量校验器 — 从 PipelineResult 生成 QualityReport。"""

    MODULE_NAME = "quality_checker"

    def __init__(
        self,
        min_confidence: float = 0.60,
        min_entity_count: int = 3,
        expected_entity_types: Optional[Set[str]] = None,
    ) -> None:
        self._min_confidence = min_confidence
        self._min_entity_count = min_entity_count
        self._expected_types = expected_entity_types or {
            "herb", "formula", "syndrome", "efficacy",
        }

    def check(self, pipeline_result: PipelineResult, text_length: int = 0) -> QualityReport:
        report = QualityReport(
            document_id=pipeline_result.document_id,
            timestamp=datetime.utcnow().isoformat(),
        )
        items = pipeline_result.all_items
        relations = pipeline_result.all_relations

        # 模块耗时
        report.module_durations = {
            name: r.duration_sec for name, r in pipeline_result.module_results.items()
        }

        # 实体/关系汇总
        report.entity_summary = dict(Counter(i.entity_type for i in items))
        report.relation_summary = dict(Counter(r.relation_type for r in relations))

        # 1) 完整性
        report.completeness, completeness_issues = self._check_completeness(items)
        report.issues.extend(completeness_issues)

        # 2) 一致性
        report.consistency, consistency_issues = self._check_consistency(items, relations)
        report.issues.extend(consistency_issues)

        # 3) 置信度分布
        report.confidence_distribution = self._confidence_distribution(items)

        # 4) 覆盖率
        report.coverage = self._check_coverage(items, text_length)

        # 综合评分
        report.overall_score = self._compute_overall_score(report)
        report.grade = self._grade(report.overall_score)
        return report

    # ------------------------------------------------------------------
    # 完整性
    # ------------------------------------------------------------------

    def _check_completeness(
        self, items: List[ExtractedItem]
    ) -> tuple[Dict[str, float], List[QualityIssue]]:
        issues: List[QualityIssue] = []
        found_types = {i.entity_type for i in items}
        missing = self._expected_types - found_types
        coverage = len(found_types & self._expected_types) / max(len(self._expected_types), 1)

        if missing:
            issues.append(QualityIssue(
                issue_id="completeness_missing_types",
                severity="warning",
                category="completeness",
                message=f"缺少预期实体类型: {', '.join(sorted(missing))}",
                suggestion="检查文本内容是否包含该类信息，或补充对应提取规则",
            ))

        if len(items) < self._min_entity_count:
            issues.append(QualityIssue(
                issue_id="completeness_low_count",
                severity="critical" if len(items) == 0 else "warning",
                category="completeness",
                message=f"提取实体数量偏少 ({len(items)} < {self._min_entity_count})",
                suggestion="检查输入文本质量或扩展词典",
            ))

        return {"type_coverage": coverage, "entity_count_ratio": min(len(items) / max(self._min_entity_count, 1), 1.0)}, issues

    # ------------------------------------------------------------------
    # 一致性
    # ------------------------------------------------------------------

    def _check_consistency(
        self,
        items: List[ExtractedItem],
        relations: List[ExtractionRelation],
    ) -> tuple[Dict[str, float], List[QualityIssue]]:
        issues: List[QualityIssue] = []

        # 检查低置信度实体
        low_conf = [i for i in items if i.confidence < self._min_confidence]
        low_ratio = len(low_conf) / max(len(items), 1)
        if low_ratio > 0.3:
            issues.append(QualityIssue(
                issue_id="consistency_low_confidence_ratio",
                severity="warning",
                category="confidence",
                message=f"{low_ratio:.0%} 的实体置信度低于 {self._min_confidence}",
                suggestion="检查是否使用了过于宽泛的匹配规则",
            ))

        # 检查关系中引用了不存在的实体
        entity_names = {i.name for i in items}
        dangling = 0
        for rel in relations:
            if rel.source not in entity_names and rel.target not in entity_names:
                dangling += 1
        dangling_ratio = dangling / max(len(relations), 1)
        if dangling > 0:
            issues.append(QualityIssue(
                issue_id="consistency_dangling_relations",
                severity="info",
                category="consistency",
                message=f"{dangling} 条关系引用了未识别的实体",
                suggestion="这可能是跨模块或规则引擎直接产生的长文本关系",
            ))

        return {
            "low_confidence_ratio": low_ratio,
            "dangling_relation_ratio": dangling_ratio,
        }, issues

    # ------------------------------------------------------------------
    # 置信度分布
    # ------------------------------------------------------------------

    def _confidence_distribution(self, items: List[ExtractedItem]) -> Dict[str, int]:
        bands = {"0.9-1.0": 0, "0.8-0.9": 0, "0.7-0.8": 0, "0.6-0.7": 0, "<0.6": 0}
        for item in items:
            c = item.confidence
            if c >= 0.9:
                bands["0.9-1.0"] += 1
            elif c >= 0.8:
                bands["0.8-0.9"] += 1
            elif c >= 0.7:
                bands["0.7-0.8"] += 1
            elif c >= 0.6:
                bands["0.6-0.7"] += 1
            else:
                bands["<0.6"] += 1
        return bands

    # ------------------------------------------------------------------
    # 覆盖率
    # ------------------------------------------------------------------

    def _check_coverage(self, items: List[ExtractedItem], text_length: int) -> Dict[str, float]:
        if text_length <= 0:
            return {"char_coverage": 0.0}
        covered_chars = sum(i.length for i in items if i.length > 0)
        return {"char_coverage": min(covered_chars / text_length, 1.0)}

    # ------------------------------------------------------------------
    # 综合得分
    # ------------------------------------------------------------------

    def _compute_overall_score(self, report: QualityReport) -> float:
        base = 70.0
        # 完整性加分
        type_cov = report.completeness.get("type_coverage", 0)
        base += type_cov * 10

        # 覆盖率加分
        char_cov = report.coverage.get("char_coverage", 0)
        base += min(char_cov * 50, 10)

        # 扣分: 问题
        for issue in report.issues:
            if issue.severity == "critical":
                base -= 15
            elif issue.severity == "warning":
                base -= 5
        return max(0, min(base, 100))

    def _grade(self, score: float) -> str:
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 50:
            return "C"
        return "D"
