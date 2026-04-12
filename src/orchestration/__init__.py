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

import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "OrchestrationResult": ("src.orchestration.research_orchestrator", "OrchestrationResult"),
    "PhaseOutcome": ("src.orchestration.research_orchestrator", "PhaseOutcome"),
    "ResearchOrchestrator": ("src.orchestration.research_orchestrator", "ResearchOrchestrator"),
    "ResearchRuntimeResult": ("src.orchestration.research_runtime_service", "ResearchRuntimeResult"),
    "ResearchRuntimeService": ("src.orchestration.research_runtime_service", "ResearchRuntimeService"),
    "run_research": ("src.orchestration.research_orchestrator", "run_research"),
    "topic_to_phase_context": ("src.orchestration.research_orchestrator", "topic_to_phase_context"),
    "TaskResult": ("src.orchestration.task_scheduler", "TaskResult"),
    "TaskScheduler": ("src.orchestration.task_scheduler", "TaskScheduler"),
    "TaskSpec": ("src.orchestration.task_scheduler", "TaskSpec"),
    "run_llm_tasks": ("src.orchestration.task_scheduler", "run_llm_tasks"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
