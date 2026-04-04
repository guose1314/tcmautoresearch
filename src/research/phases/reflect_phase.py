from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline



class ReflectPhaseMixin:
    """Mixin: reflect 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

    def execute_reflect_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        reflections = [
            {
                "topic": "方法论改进",
                "reflection": "实验设计可以更加多样化，增加跨学科方法的应用",
                "action": "在下一轮研究中引入更多样化的实验方法",
            },
            {
                "topic": "数据质量",
                "reflection": "古籍文本的标准化处理仍有改进空间",
                "action": "开发更完善的文本预处理工具",
            },
            {
                "topic": "技术应用",
                "reflection": "AI模型在中医领域应用效果显著，但需要持续优化",
                "action": "加强模型训练和调优",
            },
        ]

        improvement_plan = [
            "优化数据预处理流程",
            "增强模型泛化能力",
            "完善质量控制体系",
            "建立长期跟踪机制",
        ]

        return {
            "phase": "reflect",
            "reflections": reflections,
            "improvement_plan": improvement_plan,
            "metadata": {
                "reflection_count": len(reflections),
                "plan_items": len(improvement_plan),
            },
        }
