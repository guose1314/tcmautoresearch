"""src/orchestration — 研究编排层。

公共导出（推荐入口）：

* :class:`ResearchRuntimeService` — **唯一推荐的主研究入口**，CLI / Web / API
  均应通过此服务发起研究会话。
* :class:`ResearchRuntimeResult`  — ``ResearchRuntimeService.run()`` 返回值

兼容 / 内部导出（仅供单元测试与内部引用）：

* :class:`ResearchOrchestrator` — 旧版编排器，**已被 ResearchRuntimeService 取代，
  生产代码不应直接实例化此类**。仅保留用于单元测试和内部数据结构引用。
* :class:`OrchestrationResult`  — 编排结果数据结构（RuntimeResult 内部使用）
* :class:`PhaseOutcome`         — 单阶段摘要数据结构
* :func:`topic_to_phase_context`— 主题→阶段 context 自动推导
* :func:`run_research`          — 已弃用函数式入口，内部重定向至 RuntimeService

任务调度：

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
