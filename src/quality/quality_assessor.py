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

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.phase_tracker import PhaseTrackerMixin
from src.llm.llm_gateway import generate_with_gateway

logger = logging.getLogger(__name__)

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
# Phase I-4: Fallback 质量评测原语
# ---------------------------------------------------------------------------

# 默认接受阈值：optimized 路径的质量分相对 baseline 不得劣化超过此值
DEFAULT_FALLBACK_DELTA_THRESHOLD = 0.1

# 哪些 action 视为"发生了 fallback"，需要进入质量矩阵评测
FALLBACK_ACTIONS = frozenset({"skip", "decompose", "retry_simplified"})


def assess_fallback_quality(
    *,
    action: str,
    baseline_score: float,
    optimized_score: float,
    delta_threshold: float = DEFAULT_FALLBACK_DELTA_THRESHOLD,
    reason_extra: Optional[str] = None,
) -> Dict[str, Any]:
    """评估单次 fallback 是否可被接受。

    返回字段::

        {
          "action": str,
          "fallback_quality_score": float,    # 0..1，等于 optimized_score
          "baseline_score": float,
          "delta": float,                     # optimized - baseline，可正可负
          "delta_threshold": float,
          "fallback_acceptance": bool,        # delta >= -threshold OR action == "proceed"
          "fallback_reason": str,
        }
    """
    try:
        baseline = float(baseline_score)
    except (TypeError, ValueError):
        baseline = 0.0
    try:
        optimized = float(optimized_score)
    except (TypeError, ValueError):
        optimized = 0.0
    try:
        threshold = float(delta_threshold)
    except (TypeError, ValueError):
        threshold = DEFAULT_FALLBACK_DELTA_THRESHOLD
    threshold = max(0.0, threshold)

    delta = round(optimized - baseline, 4)
    action_label = str(action or "").strip() or "unknown"
    if action_label == "proceed":
        accepted = True
    else:
        accepted = delta >= -threshold

    if action_label == "proceed":
        reason = "no_fallback"
    elif accepted:
        reason = f"{action_label}_within_threshold"
    else:
        reason = f"{action_label}_below_baseline"
    if reason_extra:
        reason = f"{reason}:{reason_extra}"

    return {
        "action": action_label,
        "fallback_quality_score": round(max(0.0, min(1.0, optimized)), 4),
        "baseline_score": round(max(0.0, min(1.0, baseline)), 4),
        "delta": delta,
        "delta_threshold": round(threshold, 4),
        "fallback_acceptance": bool(accepted),
        "fallback_reason": reason,
    }


def build_phase_fallback_metadata(
    *,
    action: str,
    baseline_score: float,
    optimized_score: float,
    delta_threshold: float = DEFAULT_FALLBACK_DELTA_THRESHOLD,
    reason_extra: Optional[str] = None,
) -> Dict[str, Any]:
    """构造 phase metadata 三件套：fallback_quality_score / fallback_acceptance / fallback_reason。

    供各 phase mixin 在发生 fallback 时附加到 metadata，避免重复键拼写。
    """
    matrix = assess_fallback_quality(
        action=action,
        baseline_score=baseline_score,
        optimized_score=optimized_score,
        delta_threshold=delta_threshold,
        reason_extra=reason_extra,
    )
    return {
        "fallback_quality_score": matrix["fallback_quality_score"],
        "fallback_acceptance": matrix["fallback_acceptance"],
        "fallback_reason": matrix["fallback_reason"],
        "fallback_quality_matrix": matrix,
    }


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
        valid_statuses = {
            "completed",
            "success",
            "ok",
            "done",
            "failed",
            "error",
            "pending",
            "degraded",
            "blocked",
        }
        consistency = (
            1.0 if isinstance(status, str) and status.lower() in valid_statuses else 0.5
        )

        # evidence_quality — 深度指标
        evidence_keys = {"results", "artifacts", "evidence", "citations", "outcomes"}
        evidence_present = sum(1 for k in evidence_keys if result.get(k))
        evidence_quality = min(1.0, evidence_present / max(1, len(evidence_keys)))

        overall = round(
            0.4 * completeness + 0.3 * consistency + 0.3 * evidence_quality, 4
        )
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
                1
                for c in cycles.values()
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
        valid_terminal = {
            "completed",
            "failed",
            "success",
            "error",
            "degraded",
            "blocked",
        }
        if status and isinstance(status, str) and status.lower() not in valid_terminal:
            warnings.append(f"non-terminal status value: '{status}'")

        is_compliant = len(violations) == 0
        score = self.assess_quality(result)
        grade_assessment = f"GRADE:{score.grade_level} overall={score.overall_score}"

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
                "stable" if completion_rate >= min_rate and failed == 0 else "degraded"
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
    # Reflect 阶段支撑
    # ------------------------------------------------------------------

    def assess_cycle_for_reflection(
        self, outcomes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """评估循环中各阶段产出，汇总质量强弱项供 ReflectPhase 使用。

        Args:
            outcomes: ``cycle.outcomes`` — 每项形如 ``{phase: str, result: dict}``。

        Returns:
            包含 ``phase_assessments``, ``weaknesses``, ``strengths``,
            ``overall_cycle_score`` 的字典。
        """
        phase_assessments: List[Dict[str, Any]] = []
        weaknesses: List[Dict[str, Any]] = []
        strengths: List[Dict[str, Any]] = []

        for outcome in outcomes:
            phase_name = outcome.get("phase", "unknown")
            result = outcome.get("result") or {}
            score = self.assess_quality(result)
            compliance = self.validate_compliance(result)

            phase_assessments.append(
                {"phase": phase_name, "score": score, "compliance": compliance}
            )

            if score.overall_score < 0.6:
                weaknesses.append(
                    {
                        "phase": phase_name,
                        "score": score.overall_score,
                        "grade": score.grade_level,
                        "issues": compliance.violations + compliance.warnings,
                    }
                )
            elif score.overall_score >= 0.8:
                strengths.append(
                    {
                        "phase": phase_name,
                        "score": score.overall_score,
                        "grade": score.grade_level,
                    }
                )

        total = len(phase_assessments)
        overall = (
            round(sum(a["score"].overall_score for a in phase_assessments) / total, 4)
            if total
            else 0.0
        )
        return {
            "phase_assessments": phase_assessments,
            "weaknesses": weaknesses,
            "strengths": strengths,
            "overall_cycle_score": overall,
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

    # ------------------------------------------------------------------
    # LLM 驱动质量评估
    # ------------------------------------------------------------------

    def assess_quality_with_llm(
        self,
        result: Dict[str, Any],
        llm_engine: Any,
    ) -> QualityScore:
        """结合规则评分与 LLM 深度评估，返回增强版 QualityScore。

        LLM 评估四个维度（0.0–1.0）：
          - methodological_rigor : 方法学严谨性
          - evidence_coherence   : 证据链连贯性
          - domain_relevance     : 中医领域相关性
          - reproducibility      : 可复现性

        最终分 = 0.4 × rule_score + 0.6 × llm_score（LLM 可用时）。
        LLM 不可用或解析失败时回退到纯规则评分。
        """
        rule_score = self.assess_quality(result)

        llm_assessment = self._invoke_llm_quality_assessment(result, llm_engine)
        if llm_assessment is None:
            return rule_score

        llm_overall = self._compute_llm_overall(llm_assessment)
        blended = round(0.4 * rule_score.overall_score + 0.6 * llm_overall, 4)
        grade_level = self._score_to_grade(blended)

        return QualityScore(
            overall_score=blended,
            completeness=rule_score.completeness,
            consistency=rule_score.consistency,
            evidence_quality=rule_score.evidence_quality,
            grade_level=grade_level,
            details={
                **rule_score.details,
                "llm_enhanced": True,
                "rule_score": rule_score.overall_score,
                "llm_score": llm_overall,
                "llm_dimensions": llm_assessment,
                "blend_weights": {"rule": 0.4, "llm": 0.6},
            },
        )

    def assess_cycle_for_reflection_with_llm(
        self,
        outcomes: List[Dict[str, Any]],
        llm_engine: Any,
    ) -> Dict[str, Any]:
        """LLM 增强版循环评估 — 在规则评估基础上追加 LLM 综合诊断。

        若 LLM 不可用则回退到 :meth:`assess_cycle_for_reflection`。
        """
        base = self.assess_cycle_for_reflection(outcomes)

        llm_diagnosis = self._invoke_llm_cycle_diagnosis(base, llm_engine)
        if llm_diagnosis is not None:
            base["llm_diagnosis"] = llm_diagnosis

        return base

    # ------------------------------------------------------------------
    # LLM 内部辅助
    # ------------------------------------------------------------------

    def _invoke_llm_quality_assessment(
        self,
        result: Dict[str, Any],
        llm_engine: Optional[Any],
    ) -> Optional[Dict[str, float]]:
        """调用 LLM 评估单个结果，返回四维分数字典或 None。"""
        if llm_engine is None or not hasattr(llm_engine, "generate"):
            return None

        result_summary = self._build_result_summary_for_llm(result)
        user_prompt = (
            "请评估以下中医研究阶段产出的质量。\n\n"
            f"## 待评估结果摘要\n{result_summary}\n\n"
            "请从以下四个维度评分（0.0–1.0），并给出简要理由：\n"
            "1. methodological_rigor — 方法学严谨性（数据来源、分析流程、统计检验）\n"
            "2. evidence_coherence — 证据链连贯性（假设→实验→结论的逻辑链完整度）\n"
            "3. domain_relevance — 中医领域相关性（术语准确、辨证论治逻辑）\n"
            "4. reproducibility — 可复现性（数据可获取、流程可重复、参数有记录）\n\n"
            "请以 JSON 格式输出：\n"
            "```json\n"
            "{\n"
            '  "methodological_rigor": 0.0,\n'
            '  "evidence_coherence": 0.0,\n'
            '  "domain_relevance": 0.0,\n'
            '  "reproducibility": 0.0,\n'
            '  "rationale": "简要综合理由"\n'
            "}\n"
            "```"
        )

        try:
            gateway_result = generate_with_gateway(
                llm_engine,
                user_prompt,
                _QUALITY_SYSTEM_PROMPT,
                prompt_version="quality_assessor.phase_quality@v1",
                phase=str(result.get("phase") or "analyze"),
                purpose="quality_assessment",
                task_type="quality_assessment",
                json_output=True,
                metadata={
                    "prompt_name": "quality_assessor.phase_quality",
                    "response_format": "json",
                    "dossier_sections": {
                        "result_summary": result_summary,
                        "phase": str(result.get("phase") or "analyze"),
                        "status": str(result.get("status") or "unknown"),
                    },
                },
            )
            raw = gateway_result.text
            parsed = self._parse_llm_quality_response(raw)
            if parsed is not None:
                parsed["planner"] = dict(
                    gateway_result.metadata.get("planned_call") or {}
                )
                parsed["llm_gateway"] = dict(gateway_result.metadata or {})
            return parsed
        except Exception as exc:
            logger.warning("LLM 质量评估调用失败，回退规则评分: %s", exc)
            return None

    def _invoke_llm_cycle_diagnosis(
        self,
        base_assessment: Dict[str, Any],
        llm_engine: Optional[Any],
    ) -> Optional[Dict[str, Any]]:
        """调用 LLM 对整个循环做综合诊断，返回诊断字典或 None。"""
        if llm_engine is None or not hasattr(llm_engine, "generate"):
            return None

        weaknesses = base_assessment.get("weaknesses", [])
        strengths = base_assessment.get("strengths", [])
        overall = base_assessment.get("overall_cycle_score", 0.0)

        weakness_text = (
            "\n".join(
                f"- {w['phase']}: score={w['score']}, issues={w.get('issues', [])}"
                for w in weaknesses
            )
            or "无明显弱项"
        )
        strength_text = (
            "\n".join(f"- {s['phase']}: score={s['score']}" for s in strengths)
            or "无突出强项"
        )

        user_prompt = (
            "请对以下中医研究循环做综合质量诊断，并给出改进建议。\n\n"
            f"## 循环总分: {overall}\n\n"
            f"## 弱项阶段\n{weakness_text}\n\n"
            f"## 强项阶段\n{strength_text}\n\n"
            "请以 JSON 格式输出：\n"
            "```json\n"
            "{\n"
            '  "diagnosis": "整体质量诊断（1-2句话）",\n'
            '  "root_causes": ["根因1", "根因2"],\n'
            '  "priority_improvements": ["最高优先改进1", "改进2"],\n'
            '  "confidence": 0.0\n'
            "}\n"
            "```"
        )

        try:
            gateway_result = generate_with_gateway(
                llm_engine,
                user_prompt,
                _QUALITY_SYSTEM_PROMPT,
                prompt_version="quality_assessor.cycle_diagnosis@v1",
                phase="reflect",
                purpose="reflect",
                task_type="reflection",
                json_output=True,
                metadata={
                    "prompt_name": "quality_assessor.cycle_diagnosis",
                    "response_format": "json",
                    "dossier_sections": {
                        "overall_score": str(overall),
                        "weaknesses": weakness_text,
                        "strengths": strength_text,
                    },
                },
            )
            raw = gateway_result.text
            diagnosis = self._parse_llm_cycle_diagnosis(raw)
            if diagnosis is not None:
                diagnosis["planner"] = dict(
                    gateway_result.metadata.get("planned_call") or {}
                )
                diagnosis["llm_cost_report"] = dict(
                    gateway_result.llm_cost_report or {}
                )
                diagnosis["fallback_path"] = diagnosis["planner"].get("fallback_path")
                diagnosis["llm_gateway"] = dict(gateway_result.metadata or {})
            return diagnosis
        except Exception as exc:
            logger.warning("LLM 循环诊断调用失败: %s", exc)
            return None

    @staticmethod
    def _build_result_summary_for_llm(result: Dict[str, Any]) -> str:
        """将结果字典精简为适合 LLM 上下文窗口的文本摘要。"""
        lines = []
        lines.append(f"phase: {result.get('phase', 'unknown')}")
        lines.append(f"status: {result.get('status', 'unknown')}")

        if result.get("metadata"):
            meta = result["metadata"]
            if isinstance(meta, dict):
                for k in list(meta.keys())[:8]:
                    lines.append(f"metadata.{k}: {meta[k]}")

        results_data = result.get("results") or result.get("outcomes") or {}
        if isinstance(results_data, dict):
            for k in list(results_data.keys())[:6]:
                val = results_data[k]
                val_str = (
                    str(val)[:200]
                    if not isinstance(val, (int, float, bool))
                    else str(val)
                )
                lines.append(f"results.{k}: {val_str}")
        elif isinstance(results_data, list):
            lines.append(f"results: list[{len(results_data)} items]")

        artifacts = result.get("artifacts") or []
        if artifacts:
            lines.append(f"artifacts: {len(artifacts)} items")

        if result.get("error"):
            lines.append(f"error: {str(result['error'])[:200]}")

        return "\n".join(lines)

    @staticmethod
    def _parse_llm_quality_response(raw: str) -> Optional[Dict[str, float]]:
        """从 LLM 原始输出中提取四维分数。"""
        required_keys = {
            "methodological_rigor",
            "evidence_coherence",
            "domain_relevance",
            "reproducibility",
        }
        parsed = _extract_json_from_llm_output(raw)
        if parsed is None:
            return None
        if not required_keys.issubset(parsed.keys()):
            logger.warning(
                "LLM 质量评分缺少必需维度: %s", required_keys - parsed.keys()
            )
            return None

        scores: Dict[str, float] = {}
        for key in required_keys:
            try:
                val = float(parsed[key])
                scores[key] = max(0.0, min(1.0, val))
            except (TypeError, ValueError):
                logger.warning("LLM 质量维度 '%s' 值无效: %s", key, parsed[key])
                return None

        rationale = parsed.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            scores["rationale"] = rationale.strip()
        return scores

    @staticmethod
    def _parse_llm_cycle_diagnosis(raw: str) -> Optional[Dict[str, Any]]:
        """从 LLM 原始输出中提取循环诊断。"""
        parsed = _extract_json_from_llm_output(raw)
        if parsed is None:
            return None
        if "diagnosis" not in parsed:
            return None

        diagnosis: Dict[str, Any] = {
            "diagnosis": str(parsed.get("diagnosis", "")),
            "root_causes": [],
            "priority_improvements": [],
            "confidence": 0.0,
        }
        for key in ("root_causes", "priority_improvements"):
            items = parsed.get(key)
            if isinstance(items, list):
                diagnosis[key] = [
                    str(item).strip() for item in items if str(item).strip()
                ]
        try:
            diagnosis["confidence"] = max(
                0.0, min(1.0, float(parsed.get("confidence", 0.0)))
            )
        except (TypeError, ValueError):
            pass
        return diagnosis

    @staticmethod
    def _compute_llm_overall(llm_assessment: Dict[str, Any]) -> float:
        """从四维 LLM 分数计算加权综合分（等权）。"""
        dimension_keys = [
            "methodological_rigor",
            "evidence_coherence",
            "domain_relevance",
            "reproducibility",
        ]
        values = []
        for key in dimension_keys:
            val = llm_assessment.get(key)
            if isinstance(val, (int, float)):
                values.append(float(val))
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)


# ---------------------------------------------------------------------------
# LLM Prompt 常量
# ---------------------------------------------------------------------------

_QUALITY_SYSTEM_PROMPT = (
    "你是一位中医药研究方法学专家和质量评审员，熟悉 GRADE 证据等级框架、"
    "循证中医药研究 (T/C IATCM 098-2023) 标准。\n"
    "评估时请关注：数据来源可靠性、分析方法合理性、证据链完整性、"
    "中医术语规范性、结论可复现性。\n"
    "请务必以纯 JSON 格式回答，不带多余文字。"
)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _extract_json_from_llm_output(raw: str) -> Optional[Dict[str, Any]]:
    """从 LLM 输出中提取 JSON 对象，支持 ```json``` 围栏。"""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()

    # 尝试提取 ```json ... ``` 围栏
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    continue

    # 直接尝试解析
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 尝试提取第一个 { ... } 块
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None
