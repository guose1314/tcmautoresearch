# quality/quality_assessor.py
"""
QualityAssessor — 研究成果质量评估器

职责：
  1. assess_quality(result)      — 评估研究结果的综合质量，返回 QualityScore
  2. calculate_metrics(data)     — 从流程数据计算 pipeline 级别指标，返回 Dict
  3. validate_compliance(result) — 校验 GRADE 合规性，返回 ComplianceReport
  4. build_pipeline_analysis_summary(...)
                                 — 汇总循环完成率/失败率等分析摘要（从 ResearchPipeline 迁入）

存储：
  - quality_metrics  {cycle_completion_rate, phase_efficiency, researcher_productivity, quality_assurance}
  - resource_usage   {cpu_usage, memory_usage, storage_usage, network_usage}
  通过字典引用共享给 ResearchPipeline，使 pipeline.quality_metrics 等属性始终指向同一对象。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.core.phase_tracker import PhaseTrackerMixin

# ---------------------------------------------------------------------------
# GRADE 等级常量
# ---------------------------------------------------------------------------
GRADE_HIGH = "high"
GRADE_MODERATE = "moderate"
GRADE_LOW = "low"
GRADE_VERY_LOW = "very_low"

_GRADE_THRESHOLDS = [
    (0.8, GRADE_HIGH),
    (0.6, GRADE_MODERATE),
    (0.4, GRADE_LOW),
]

# 结果中视为"完整性指标"的预期字段集合
_EXPECTED_RESULT_KEYS = frozenset(
    ["status", "phase", "results", "artifacts", "metadata", "error"]
)
_REQUIRED_COMPLIANCE_KEYS = frozenset(["status", "phase"])


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class QualityScore:
    """综合质量评分（0.0–1.0 区间，grade_level 遵循 GRADE 框架）。"""

    overall_score: float = 0.0
    completeness: float = 0.0
    consistency: float = 0.0
    evidence_quality: float = 0.0
    grade_level: str = GRADE_VERY_LOW
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceReport:
    """GRADE 合规检查报告。"""

    is_compliant: bool = True
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    grade_assessment: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class QualityAssessor(PhaseTrackerMixin):
    """
    研究成果质量评估器。

    被 ResearchPipeline 以组合方式持有；通过共享字典引用使
    pipeline.quality_metrics / pipeline.resource_usage 始终与此对象同步。
    """

    def __init__(self) -> None:
        # 这两个字典被 ResearchPipeline.__init__ 直接引用
        self.quality_metrics: Dict[str, float] = {
            "cycle_completion_rate": 0.0,
            "phase_efficiency": 0.0,
            "researcher_productivity": 0.0,
            "quality_assurance": 0.0,
        }
        self.resource_usage: Dict[str, float] = {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "storage_usage": 0.0,
            "network_usage": 0.0,
        }

    # ------------------------------------------------------------------
    # 核心 API
    # ------------------------------------------------------------------

    def assess_quality(self, result: Dict[str, Any]) -> QualityScore:
        """
        评估单个研究结果的综合质量。

        评分维度：
          - completeness   : 预期字段存在比例
          - consistency    : status 字段值合理性
          - evidence_quality: 结果字段丰富程度（含 results / artifacts）
          - overall_score  : 上述三者加权均值 (0.4 / 0.3 / 0.3)
        """
        if not isinstance(result, dict):
            return QualityScore(details={"error": "result is not a dict"})

        # completeness — 预期字段覆盖率
        present = sum(1 for k in _EXPECTED_RESULT_KEYS if k in result)
        completeness = present / len(_EXPECTED_RESULT_KEYS)

        # consistency — status 值合法性
        status = result.get("status", "")
        valid_statuses = {"completed", "success", "ok", "done", "failed", "error", "pending"}
        consistency = 1.0 if isinstance(status, str) and status.lower() in valid_statuses else 0.5

        # evidence_quality — 深度指标
        evidence_keys = {"results", "artifacts", "evidence", "citations", "outcomes"}
        evidence_present = sum(1 for k in evidence_keys if result.get(k))
        evidence_quality = min(1.0, evidence_present / max(1, len(evidence_keys)))

        overall = round(0.4 * completeness + 0.3 * consistency + 0.3 * evidence_quality, 4)
        grade_level = self._score_to_grade(overall)

        return QualityScore(
            overall_score=overall,
            completeness=round(completeness, 4),
            consistency=round(consistency, 4),
            evidence_quality=round(evidence_quality, 4),
            grade_level=grade_level,
            details={
                "present_keys": [k for k in _EXPECTED_RESULT_KEYS if k in result],
                "status_value": status,
                "evidence_keys_found": [k for k in evidence_keys if result.get(k)],
            },
        )

    def calculate_metrics(self, data: Dict[str, Any]) -> Dict[str, float]:
        """
        从流程快照数据计算质量指标并更新 self.quality_metrics。

        期望 data 包含：
          research_cycles   : Dict[str, cycle]   (有 .status 属性)
          execution_history : List[Dict]
          failed_operations : List[Dict]
        返回更新后的 quality_metrics 字典（与 self.quality_metrics 同一对象）。
        """
        cycles: Dict[str, Any] = data.get("research_cycles") or {}
        history: List[Dict] = data.get("execution_history") or []
        failed_ops: List[Dict] = data.get("failed_operations") or []

        total = len(cycles)
        if total:
            from src.research.study_session_manager import ResearchCycleStatus
            completed = sum(
                1 for c in cycles.values()
                if getattr(c, "status", None) == ResearchCycleStatus.COMPLETED
            )
            completion_rate = round(completed / total, 4)
        else:
            completion_rate = 0.0

        # phase_efficiency: 成功阶段数 / 总阶段执行数
        executed = len(history)
        failed_phase_count = sum(1 for op in failed_ops if op.get("operation"))
        successful = max(0, executed - failed_phase_count)
        phase_efficiency = round(successful / executed, 4) if executed else 0.0

        # quality_assurance: 简化版 — 与 completion_rate 正相关，失败操作负相关
        penalty = min(1.0, len(failed_ops) * 0.1)
        quality_assurance = round(max(0.0, completion_rate - penalty), 4)

        self.quality_metrics.update(
            {
                "cycle_completion_rate": completion_rate,
                "phase_efficiency": phase_efficiency,
                "researcher_productivity": phase_efficiency,  # 同源，可独立扩展
                "quality_assurance": quality_assurance,
            }
        )
        return self.quality_metrics

    def validate_compliance(self, result: Dict[str, Any]) -> ComplianceReport:
        """
        校验结果是否满足 GRADE 最低合规要求。

        违规（violations）: 必须字段缺失
        警告（warnings）  : 可选字段缺失或值异常
        """
        if not isinstance(result, dict):
            return ComplianceReport(
                is_compliant=False,
                violations=["result must be a dict"],
                grade_assessment="non_compliant",
                details={"input_type": type(result).__name__},
            )

        violations: List[str] = []
        warnings: List[str] = []

        # 必须字段检查
        for key in sorted(_REQUIRED_COMPLIANCE_KEYS):
            if key not in result:
                violations.append(f"missing required field: '{key}'")

        # 可选最佳实践字段
        recommended = {"results", "metadata", "artifacts"}
        for key in sorted(recommended):
            if key not in result:
                warnings.append(f"recommended field absent: '{key}'")

        # status 值合规性
        status = result.get("status", "")
        valid_terminal = {"completed", "failed", "success", "error"}
        if status and isinstance(status, str) and status.lower() not in valid_terminal:
            warnings.append(f"non-terminal status value: '{status}'")

        is_compliant = len(violations) == 0
        score = self.assess_quality(result)
        grade_assessment = (
            f"GRADE:{score.grade_level} overall={score.overall_score}"
        )

        return ComplianceReport(
            is_compliant=is_compliant,
            violations=violations,
            warnings=warnings,
            grade_assessment=grade_assessment,
            details={
                "quality_score": score.overall_score,
                "grade_level": score.grade_level,
                "checked_required": sorted(_REQUIRED_COMPLIANCE_KEYS),
                "checked_recommended": sorted(recommended),
            },
        )

    # ------------------------------------------------------------------
    # 流程分析摘要（从 ResearchPipeline._build_pipeline_analysis_summary 迁入）
    # ------------------------------------------------------------------

    def build_pipeline_analysis_summary(
        self,
        research_cycles: Dict[str, Any],
        failed_operations: List[Dict[str, Any]],
        governance_config: Dict[str, Any],
        pipeline_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        汇总研究流程中各循环的完成情况与健康状态。

        原本属于 ResearchPipeline._build_pipeline_analysis_summary；
        现迁移到此处，通过参数注入解耦。
        """
        from src.research.study_session_manager import ResearchCycleStatus

        total = len(research_cycles)
        completed = sum(
            1
            for c in research_cycles.values()
            if getattr(c, "status", None) == ResearchCycleStatus.COMPLETED
        )
        failed = sum(
            1
            for c in research_cycles.values()
            if getattr(c, "status", None) == ResearchCycleStatus.FAILED
        )
        completion_rate = (completed / total) if total else 0.0

        min_rate = float(governance_config.get("minimum_stable_completion_rate", 0.8))
        status = "idle"
        if failed_operations:
            status = "needs_followup"
        elif total > 0:
            status = (
                "stable"
                if completion_rate >= min_rate and failed == 0
                else "degraded"
            )

        return {
            "total_cycles": total,
            "completed_cycles": completed,
            "failed_cycles": failed,
            "completion_rate": round(completion_rate, 4),
            "failed_operation_count": len(failed_operations),
            "status": status,
            "last_completed_phase": pipeline_metadata.get("last_completed_phase"),
            "failed_phase": pipeline_metadata.get("failed_phase"),
            "final_status": pipeline_metadata.get("final_status", "initialized"),
        }

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置所有指标为零初值（清理时调用，保持字典对象不变以保留外部引用）。"""
        self.quality_metrics.clear()
        self.quality_metrics.update(
            {
                "cycle_completion_rate": 0.0,
                "phase_efficiency": 0.0,
                "researcher_productivity": 0.0,
                "quality_assurance": 0.0,
            }
        )
        self.resource_usage.clear()
        self.resource_usage.update(
            {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "storage_usage": 0.0,
                "network_usage": 0.0,
            }
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _score_to_grade(score: float) -> str:
        for threshold, level in _GRADE_THRESHOLDS:
            if score >= threshold:
                return level
        return GRADE_VERY_LOW
