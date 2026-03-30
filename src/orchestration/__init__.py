"""src/orchestration — 研究编排层。

公共导出：

* :class:`ResearchOrchestrator` — 全流程编排器，提供 ``run(topic)`` 入口
* :class:`OrchestrationResult`  — ``run()`` 返回值
* :class:`PhaseOutcome`         — 单阶段摘要
* :func:`topic_to_phase_context`— 主题→阶段 context 自动推导
* :class:`TaskScheduler`        — asyncio 任务调度器（LLM 并发调用）
* :class:`TaskSpec`             — 单任务描述
* :class:`TaskResult`           — 单任务结果
* :func:`run_llm_tasks`         — LLM 并发调用便捷函数
"""

from src.orchestration.research_orchestrator import (
    OrchestrationResult,
    PhaseOutcome,
    ResearchOrchestrator,
    run_research,
    topic_to_phase_context,
)
from src.orchestration.task_scheduler import (
    TaskResult,
    TaskScheduler,
    TaskSpec,
    run_llm_tasks,
)

__all__ = [
    "OrchestrationResult",
    "PhaseOutcome",
    "ResearchOrchestrator",
    "run_research",
    "topic_to_phase_context",
    "TaskResult",
    "TaskScheduler",
    "TaskSpec",
    "run_llm_tasks",
]
