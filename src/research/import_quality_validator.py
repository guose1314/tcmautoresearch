"""外部导入数据质量校验器 — 对 experiment_execution 阶段接收的外部数据进行结构化验证。

ImportQualityValidator 提供：
- 记录级字段完整性校验（必需字段、类型、范围）
- 关系级一致性校验（源/目标存在性、类型合法性）
- 可配置的严格度等级（strict / standard / lenient）
- 汇总验证报告（pass / warn / reject 分类）

用法::

    validator = ImportQualityValidator(strictness="standard")
    report = validator.validate_records(records)
    if report.has_rejections:
        logger.error("导入数据质量不达标: %s", report.summary)
    valid_records = report.accepted_records
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Strictness(Enum):
    """验证严格度等级。"""

    STRICT = "strict"  # 任何缺失/异常 → reject
    STANDARD = "standard"  # 必需字段缺失 → reject；可选字段缺失 → warn
    LENIENT = "lenient"  # 仅类型错误 → reject；其余 → warn


class ValidationSeverity(Enum):
    """单条验证结果级别。"""

    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"


@dataclass
class ValidationIssue:
    """单个验证问题。"""

    record_index: int
    field: str
    severity: ValidationSeverity
    message: str


@dataclass
class ValidationReport:
    """批量验证报告。"""

    total_records: int = 0
    passed: int = 0
    warned: int = 0
    rejected: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    accepted_indices: List[int] = field(default_factory=list)

    @property
    def has_rejections(self) -> bool:
        return self.rejected > 0

    @property
    def acceptance_rate(self) -> float:
        if self.total_records == 0:
            return 1.0
        return self.passed / self.total_records

    @property
    def accepted_records(self) -> List[int]:
        """返回通过验证的记录索引列表。"""
        return list(self.accepted_indices)

    @property
    def summary(self) -> str:
        return (
            f"总计 {self.total_records} 条: "
            f"通过 {self.passed}, 警告 {self.warned}, 拒绝 {self.rejected} "
            f"(接受率 {self.acceptance_rate:.1%})"
        )


# ── 字段规格 ─────────────────────────────────────────────────────────────

_REQUIRED_RECORD_FIELDS = {
    "source_entity": str,
    "target_entity": str,
    "relation_type": str,
}

_OPTIONAL_RECORD_FIELDS = {
    "confidence": (int, float),
    "excerpt": str,
    "evidence_grade": str,
    "entity_spans": list,
    "metadata": dict,
}

_VALID_EVIDENCE_GRADES: Set[str] = {"high", "moderate", "low", "very_low"}

_REQUIRED_RELATIONSHIP_FIELDS = {
    "source": str,
    "target": str,
    "type": str,
}


class ImportQualityValidator:
    """对 experiment_execution 导入数据进行结构化质量校验。

    Parameters
    ----------
    strictness :
        验证严格度（strict / standard / lenient）。
    min_confidence :
        最低可接受置信度（低于此值 → warn/reject 取决于 strictness）。
    """

    def __init__(
        self,
        strictness: str = "standard",
        min_confidence: float = 0.0,
    ) -> None:
        try:
            self._strictness = Strictness(strictness)
        except ValueError:
            self._strictness = Strictness.STANDARD
        self._min_confidence = min_confidence

    @property
    def strictness(self) -> str:
        return self._strictness.value

    def validate_records(self, records: List[Any]) -> ValidationReport:
        """验证一批 execution records。

        Parameters
        ----------
        records :
            导入的记录列表（期望为 List[Dict]）。

        Returns
        -------
        ValidationReport
            包含通过/警告/拒绝统计和具体问题列表。
        """
        report = ValidationReport(total_records=len(records))

        for idx, record in enumerate(records):
            record_issues = self._validate_single_record(idx, record)
            if record_issues:
                report.issues.extend(record_issues)

            # 判断该记录整体状态
            max_severity = max(
                (i.severity for i in record_issues),
                default=ValidationSeverity.PASS,
                key=lambda s: {"pass": 0, "warn": 1, "reject": 2}.get(s.value, 0),
            )

            if max_severity == ValidationSeverity.REJECT:
                report.rejected += 1
            elif max_severity == ValidationSeverity.WARN:
                report.warned += 1
                report.accepted_indices.append(idx)
                report.passed += 1
            else:
                report.accepted_indices.append(idx)
                report.passed += 1

        return report

    def validate_relationships(self, relationships: List[Any]) -> ValidationReport:
        """验证一批 relationships。"""
        report = ValidationReport(total_records=len(relationships))

        for idx, rel in enumerate(relationships):
            rel_issues = self._validate_single_relationship(idx, rel)
            if rel_issues:
                report.issues.extend(rel_issues)

            max_severity = max(
                (i.severity for i in rel_issues),
                default=ValidationSeverity.PASS,
                key=lambda s: {"pass": 0, "warn": 1, "reject": 2}.get(s.value, 0),
            )

            if max_severity == ValidationSeverity.REJECT:
                report.rejected += 1
            elif max_severity == ValidationSeverity.WARN:
                report.warned += 1
                report.accepted_indices.append(idx)
                report.passed += 1
            else:
                report.accepted_indices.append(idx)
                report.passed += 1

        return report

    # ── 单条验证 ──────────────────────────────────────────────────────────

    def _validate_single_record(self, idx: int, record: Any) -> List[ValidationIssue]:
        """验证单条 record。"""
        issues: List[ValidationIssue] = []

        # 基本类型检查
        if not isinstance(record, dict):
            issues.append(ValidationIssue(
                record_index=idx,
                field="(root)",
                severity=ValidationSeverity.REJECT,
                message=f"记录必须为 dict，实际为 {type(record).__name__}",
            ))
            return issues

        # 必需字段
        for field_name, expected_type in _REQUIRED_RECORD_FIELDS.items():
            value = record.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                severity = (
                    ValidationSeverity.REJECT
                    if self._strictness != Strictness.LENIENT
                    else ValidationSeverity.WARN
                )
                issues.append(ValidationIssue(
                    record_index=idx,
                    field=field_name,
                    severity=severity,
                    message=f"必需字段 '{field_name}' 缺失或为空",
                ))
            elif not isinstance(value, expected_type):
                issues.append(ValidationIssue(
                    record_index=idx,
                    field=field_name,
                    severity=ValidationSeverity.REJECT,
                    message=f"字段 '{field_name}' 类型错误: 期望 {expected_type.__name__}，实际 {type(value).__name__}",
                ))

        # 可选字段类型校验
        for field_name, expected_type in _OPTIONAL_RECORD_FIELDS.items():
            value = record.get(field_name)
            if value is None:
                if self._strictness == Strictness.STRICT:
                    issues.append(ValidationIssue(
                        record_index=idx,
                        field=field_name,
                        severity=ValidationSeverity.WARN,
                        message=f"推荐字段 '{field_name}' 缺失",
                    ))
                continue
            if isinstance(expected_type, tuple):
                if not isinstance(value, expected_type):
                    issues.append(ValidationIssue(
                        record_index=idx,
                        field=field_name,
                        severity=ValidationSeverity.WARN,
                        message=f"字段 '{field_name}' 类型不符: 期望 {expected_type}，实际 {type(value).__name__}",
                    ))
            elif not isinstance(value, expected_type):
                issues.append(ValidationIssue(
                    record_index=idx,
                    field=field_name,
                    severity=ValidationSeverity.WARN,
                    message=f"字段 '{field_name}' 类型不符: 期望 {expected_type.__name__}，实际 {type(value).__name__}",
                ))

        # confidence 范围
        confidence = record.get("confidence")
        if isinstance(confidence, (int, float)):
            if confidence < 0.0 or confidence > 1.0:
                issues.append(ValidationIssue(
                    record_index=idx,
                    field="confidence",
                    severity=ValidationSeverity.WARN,
                    message=f"confidence 超出 [0, 1] 范围: {confidence}",
                ))
            elif confidence < self._min_confidence:
                severity = (
                    ValidationSeverity.REJECT
                    if self._strictness == Strictness.STRICT
                    else ValidationSeverity.WARN
                )
                issues.append(ValidationIssue(
                    record_index=idx,
                    field="confidence",
                    severity=severity,
                    message=f"confidence {confidence} 低于最低阈值 {self._min_confidence}",
                ))

        # evidence_grade 合法性
        grade = record.get("evidence_grade")
        if isinstance(grade, str) and grade not in _VALID_EVIDENCE_GRADES:
            issues.append(ValidationIssue(
                record_index=idx,
                field="evidence_grade",
                severity=ValidationSeverity.WARN,
                message=f"evidence_grade '{grade}' 不在合法值集合中",
            ))

        return issues

    def _validate_single_relationship(self, idx: int, rel: Any) -> List[ValidationIssue]:
        """验证单条 relationship。"""
        issues: List[ValidationIssue] = []

        if not isinstance(rel, dict):
            issues.append(ValidationIssue(
                record_index=idx,
                field="(root)",
                severity=ValidationSeverity.REJECT,
                message=f"关系必须为 dict，实际为 {type(rel).__name__}",
            ))
            return issues

        for field_name, expected_type in _REQUIRED_RELATIONSHIP_FIELDS.items():
            value = rel.get(field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                severity = (
                    ValidationSeverity.REJECT
                    if self._strictness != Strictness.LENIENT
                    else ValidationSeverity.WARN
                )
                issues.append(ValidationIssue(
                    record_index=idx,
                    field=field_name,
                    severity=severity,
                    message=f"必需字段 '{field_name}' 缺失或为空",
                ))
            elif not isinstance(value, expected_type):
                issues.append(ValidationIssue(
                    record_index=idx,
                    field=field_name,
                    severity=ValidationSeverity.REJECT,
                    message=f"字段 '{field_name}' 类型错误: 期望 {expected_type.__name__}，实际 {type(value).__name__}",
                ))

        # metadata.confidence 范围
        metadata = rel.get("metadata")
        if isinstance(metadata, dict):
            confidence = metadata.get("confidence")
            if isinstance(confidence, (int, float)):
                if confidence < 0.0 or confidence > 1.0:
                    issues.append(ValidationIssue(
                        record_index=idx,
                        field="metadata.confidence",
                        severity=ValidationSeverity.WARN,
                        message=f"metadata.confidence 超出 [0, 1] 范围: {confidence}",
                    ))

        return issues
