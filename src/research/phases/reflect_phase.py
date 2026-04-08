from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

logger = logging.getLogger(__name__)

# LLM 系统提示词
_REFLECT_SYSTEM_PROMPT = (
    "你是一位中医古籍研究方法学专家，擅长对研究循环进行科学化反思。"
    "请基于各阶段质量评分和合规情况，给出具体、可操作的改进建议。"
    "输出严格使用 JSON 格式，包含 reflections (数组) 和 improvement_plan (数组) 两个字段。"
)


class ReflectPhaseMixin:
    """Mixin: reflect 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。

    实现策略:
      1. 使用 QualityAssessor 对循环各阶段产出做质量评估
      2. 若 LLM 可用，将评估摘要送模型生成深度反思
      3. 若 LLM 不可用或调用失败，回退到基于评估数据的规则反思
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_reflect_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        outcomes: List[Dict[str, Any]] = getattr(cycle, "outcomes", None) or []
        quality_assessor = self.pipeline.quality_assessor

        # ---- 1. 获取 LLM 引擎（可选） ----
        llm_engine = self.pipeline.config.get("llm_engine") or self.pipeline.config.get("llm_service")
        has_llm = llm_engine is not None and hasattr(llm_engine, "generate")

        # ---- 2. 基于 QualityAssessor 评估各阶段（LLM 可用时启用深度诊断） ----
        if has_llm:
            cycle_assessment = quality_assessor.assess_cycle_for_reflection_with_llm(outcomes, llm_engine)
        else:
            cycle_assessment = quality_assessor.assess_cycle_for_reflection(outcomes)

        # ---- 3. 构建反思 ----
        reflections = self._build_reflections_from_assessment(cycle_assessment)

        # ---- 4. LLM 增强反思（可选，在评估级诊断之外追加反思级洞察） ----
        llm_enhanced = False
        if has_llm:
            llm_reflection = self._generate_llm_reflection(llm_engine, cycle_assessment, outcomes)
            if llm_reflection:
                reflections.append(llm_reflection)
                llm_enhanced = True

        # ---- 4. 改进计划 ----
        improvement_plan = self._build_improvement_plan(cycle_assessment)

        # ---- 5. SelfLearningEngine 反馈（可选） ----
        learning_summary = self._feed_self_learning(cycle_assessment)

        return {
            "phase": "reflect",
            "reflections": reflections,
            "improvement_plan": improvement_plan,
            "quality_assessment": {
                "overall_cycle_score": cycle_assessment["overall_cycle_score"],
                "weaknesses": cycle_assessment["weaknesses"],
                "strengths": cycle_assessment["strengths"],
                "llm_diagnosis": cycle_assessment.get("llm_diagnosis"),
            },
            "learning_summary": learning_summary,
            "metadata": {
                "reflection_count": len(reflections),
                "plan_items": len(improvement_plan),
                "cycle_quality_score": cycle_assessment["overall_cycle_score"],
                "llm_enhanced": llm_enhanced,
                "assessed_phases": len(cycle_assessment["phase_assessments"]),
                "learning_fed": learning_summary is not None,
            },
        }

    # ------------------------------------------------------------------
    # SelfLearningEngine 反馈
    # ------------------------------------------------------------------

    def _feed_self_learning(self, cycle_assessment: Dict[str, Any]) -> Dict[str, Any] | None:
        """将循环评估结果反馈给 SelfLearningEngine（若可用）。"""
        learning_engine = self.pipeline.config.get("self_learning_engine")
        if learning_engine is None:
            return None
        if not hasattr(learning_engine, "learn_from_cycle_reflection"):
            return None
        try:
            return learning_engine.learn_from_cycle_reflection(cycle_assessment)
        except Exception as exc:
            logger.warning("SelfLearningEngine 反馈失败: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 规则反思构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_reflections_from_assessment(assessment: Dict[str, Any]) -> List[Dict[str, Any]]:
        reflections: List[Dict[str, Any]] = []

        for weakness in assessment.get("weaknesses", []):
            reflections.append({
                "topic": f"{weakness['phase']}阶段质量不足",
                "reflection": (
                    f"{weakness['phase']}阶段综合评分 {weakness['score']:.2f} "
                    f"(GRADE: {weakness['grade']})，存在问题: "
                    + "; ".join(weakness.get("issues", [])[:5])
                ),
                "action": f"在下一轮循环中重点优化{weakness['phase']}阶段的数据完整性与合规性",
                "source": "quality_assessor",
            })

        for strength in assessment.get("strengths", []):
            reflections.append({
                "topic": f"{strength['phase']}阶段表现优秀",
                "reflection": (
                    f"{strength['phase']}阶段综合评分 {strength['score']:.2f} "
                    f"(GRADE: {strength['grade']})，可作为最佳实践推广"
                ),
                "action": f"将{strength['phase']}阶段的方法论沉淀为模板",
                "source": "quality_assessor",
            })

        if not reflections:
            score = assessment.get("overall_cycle_score", 0.0)
            reflections.append({
                "topic": "循环整体评估",
                "reflection": f"循环整体评分 {score:.2f}，各阶段质量均衡，无突出短板",
                "action": "保持当前研究节奏，关注细节优化",
                "source": "quality_assessor",
            })

        return reflections

    # ------------------------------------------------------------------
    # LLM 增强反思
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_llm_reflection(
        llm_engine: Any,
        assessment: Dict[str, Any],
        outcomes: List[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        phase_summary = []
        for pa in assessment.get("phase_assessments", []):
            score = pa["score"]
            phase_summary.append(
                f"- {pa['phase']}: 综合={score.overall_score:.2f}, "
                f"完整性={score.completeness:.2f}, "
                f"一致性={score.consistency:.2f}, "
                f"证据质量={score.evidence_quality:.2f}, "
                f"GRADE={score.grade_level}"
            )

        user_prompt = (
            f"研究循环共执行 {len(outcomes)} 个阶段，各阶段质量评分如下：\n"
            + "\n".join(phase_summary)
            + f"\n\n整体评分: {assessment['overall_cycle_score']:.2f}\n"
            f"薄弱环节: {len(assessment['weaknesses'])} 个\n"
            f"优势环节: {len(assessment['strengths'])} 个\n\n"
            "请基于以上评估数据，给出一条高层反思和关键改进方向。"
            "输出严格 JSON: {\"reflection\": \"...\", \"action\": \"...\"}"
        )

        try:
            raw = llm_engine.generate(user_prompt, _REFLECT_SYSTEM_PROMPT)
            parsed = json.loads(raw)
            return {
                "topic": "LLM 深度反思",
                "reflection": str(parsed.get("reflection", raw)),
                "action": str(parsed.get("action", "")),
                "source": "llm",
            }
        except Exception as exc:
            logger.warning("LLM 反思生成失败，回退规则反思: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 改进计划
    # ------------------------------------------------------------------

    @staticmethod
    def _build_improvement_plan(assessment: Dict[str, Any]) -> List[str]:
        plan: List[str] = []

        for weakness in assessment.get("weaknesses", []):
            issues = weakness.get("issues", [])
            if any("missing required" in i for i in issues):
                plan.append(f"补全{weakness['phase']}阶段的必要字段，提升数据完整性")
            if any("recommended field absent" in i for i in issues):
                plan.append(f"为{weakness['phase']}阶段添加推荐字段（results/metadata/artifacts）")
            if weakness["score"] < 0.4:
                plan.append(f"重新设计{weakness['phase']}阶段的输出规范，当前评分过低")

        overall = assessment.get("overall_cycle_score", 0.0)
        if overall < 0.6:
            plan.append("制定全局质量基线，将循环整体评分提升至 0.6 以上")
        elif overall < 0.8:
            plan.append("优化薄弱阶段，争取循环整体评分达到 0.8（GRADE: high）")

        if not plan:
            plan.append("保持当前质量水平，持续监控各阶段评分稳定性")

        return plan
