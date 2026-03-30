"""3.2 TaskScheduler — concurrent.futures → asyncio 异步任务调度器

设计目标
--------
* 将原有 ``concurrent.futures.ThreadPoolExecutor`` 的 LLM 调用迁移为
  ``asyncio`` 事件循环驱动，让多个 LLM 任务可以在同一事件循环中并发执行，
  避免 GIL 无关的 IO 等待被阻塞在线程排队上。
* ``LLMEngine.generate()`` 是 CPU-bound + 阻塞 I/O 混合调用，不能直接变成
  协程；正确做法是用 ``loop.run_in_executor(ThreadPoolExecutor)`` 将其包装
  成 awaitable，在 asyncio 事件循环内调度但不阻塞事件循环本身。
* 提供同步友好的 ``run_tasks()`` 入口，内部自动管理事件循环，无需调用方
  了解 asyncio。

核心类
------
* :class:`TaskSpec`       — 单个任务描述（callable + args/kwargs + 超时）
* :class:`TaskResult`     — 单个任务执行结果
* :class:`TaskScheduler`  — 调度器主体，管理线程池、事件循环、并发量、超时
* :func:`run_llm_tasks`   — 便捷函数，直接提交一批 LLM generate 调用

并发迁移模式
---------
旧写法 (concurrent.futures)::

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(engine.generate, prompt) for prompt in prompts]
        results = [f.result() for f in as_completed(futures)]

新写法 (TaskScheduler)::

    scheduler = TaskScheduler(max_workers=3)
    tasks = [TaskSpec(fn=engine.generate, args=(prompt,)) for prompt in prompts]
    results = scheduler.run_tasks(tasks)
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_WORKERS = 4
_DEFAULT_TASK_TIMEOUT = 120.0   # 单任务最大等待秒数
_DEFAULT_CONCURRENCY = 8        # asyncio 并发信号量上限


# ─────────────────────────────────────────────────────────────────────────────
# 任务描述与结果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskSpec:
    """描述一个可调度的任务。

    Attributes:
        fn:          同步可调用对象（如 ``engine.generate``）。
        args:        位置参数元组。
        kwargs:      关键字参数字典。
        timeout_sec: 单任务超时秒数。``None`` 使用调度器默认值。
        task_id:     可选标识（用于日志与结果关联）。
    """

    fn: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    timeout_sec: Optional[float] = None
    task_id: str = ""


@dataclass
class TaskResult:
    """单个任务的执行结果。

    Attributes:
        task_id:      与 :class:`TaskSpec` 的 ``task_id`` 对应。
        status:       ``"completed"`` | ``"failed"`` | ``"timeout"``
        value:        任务正常返回值；失败时为 ``None``。
        error:        错误消息；成功时为空字符串。
        duration_sec: 实际耗时（秒）。
    """

    task_id: str
    status: str
    value: Any
    error: str = ""
    duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "value": self.value,
            "error": self.error,
            "duration_sec": round(self.duration_sec, 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# TaskScheduler
# ─────────────────────────────────────────────────────────────────────────────

class TaskScheduler:
    """将同步阻塞任务（如 LLM generate）包装为 asyncio 并发调度。

    Parameters
    ----------
    max_workers:
        底层 ``ThreadPoolExecutor`` 线程数，控制真正并行的 blocking 调用数量。
        对于 LLM 推理，通常设为 CPU / GPU 并发上限（默认 4）。
    max_concurrency:
        asyncio 信号量上限，控制同时等待执行的协程数量（默认 8）。
        可大于 max_workers，等待队列在 asyncio 层面排队而非线程池。
    default_timeout_sec:
        默认单任务超时；可被 :class:`TaskSpec` 的 ``timeout_sec`` 覆盖。
    """

    def __init__(
        self,
        max_workers: int = _DEFAULT_MAX_WORKERS,
        max_concurrency: int = _DEFAULT_CONCURRENCY,
        default_timeout_sec: float = _DEFAULT_TASK_TIMEOUT,
    ):
        self.max_workers = max_workers
        self.max_concurrency = max_concurrency
        self.default_timeout_sec = default_timeout_sec
        self._executor: Optional[ThreadPoolExecutor] = None
        self._task_queue: Optional[asyncio.Queue[TaskSpec]] = None
        self._result_queue: Optional[asyncio.Queue[TaskResult]] = None
        self._workers: List[asyncio.Task[Any]] = []
        self._queue_started: bool = False

    # ── 공共 API ─────────────────────────────────────────────────────────── #

    def run_tasks(
        self,
        tasks: List[TaskSpec],
        *,
        preserve_order: bool = True,
    ) -> List[TaskResult]:
        """同步入口：提交一批任务，阻塞直到全部完成（或超时）。

        Args:
            tasks:          任务列表。
            preserve_order: 为 ``True`` 时返回顺序与 ``tasks`` 顺序一致；
                            为 ``False`` 时按完成顺序返回（更快出结果）。

        Returns:
            ``TaskResult`` 列表。
        """
        if not tasks:
            return []

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 已在事件循环中（如 Jupyter / 嵌套调用）：通过线程执行
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(max_workers=1) as bridge:
                future = bridge.submit(self._run_in_new_loop, tasks, preserve_order)
                return future.result()
        else:
            return asyncio.run(self._schedule(tasks, preserve_order))

    async def run_tasks_async(
        self,
        tasks: List[TaskSpec],
        *,
        preserve_order: bool = True,
    ) -> List[TaskResult]:
        """异步入口（在已有事件循环中直接 await）。"""
        return await self._schedule(tasks, preserve_order)

    async def start_queue(self) -> None:
        """启动异步任务队列 worker。"""
        if self._queue_started:
            return
        self._task_queue = asyncio.Queue()
        self._result_queue = asyncio.Queue()
        self._workers = [
            asyncio.create_task(self._queue_worker(i), name=f"task_scheduler_worker_{i}")
            for i in range(max(1, self.max_workers))
        ]
        self._queue_started = True

    async def submit_task(self, spec: TaskSpec) -> str:
        """向异步任务队列提交任务，返回任务 ID。"""
        if not self._queue_started:
            await self.start_queue()
        assert self._task_queue is not None
        if not spec.task_id:
            spec.task_id = f"queue_{int(time.time() * 1000)}_{id(spec)}"
        await self._task_queue.put(spec)
        return spec.task_id

    async def get_result(self, timeout_sec: Optional[float] = None) -> Optional[TaskResult]:
        """从结果队列获取一条结果；可指定超时。"""
        if not self._queue_started or self._result_queue is None:
            return None
        if timeout_sec is None:
            return await self._result_queue.get()
        try:
            return await asyncio.wait_for(self._result_queue.get(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            return None

    async def join_queue(self) -> None:
        """等待任务队列中已提交任务全部处理完成。"""
        if self._queue_started and self._task_queue is not None:
            await self._task_queue.join()

    async def stop_queue(self) -> None:
        """停止异步任务队列 worker。"""
        if not self._queue_started:
            return
        assert self._task_queue is not None
        for _ in self._workers:
            await self._task_queue.put(TaskSpec(fn=lambda: None, task_id="__shutdown__"))
        await self._task_queue.join()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._queue_started = False
        self._task_queue = None
        self._result_queue = None

    def shutdown(self, wait: bool = True) -> None:
        """释放内部线程池；调度器之后不可再使用。"""
        if self._executor is not None:
            self._executor.shutdown(wait=wait)
            self._executor = None

    # ── 内部实现 ─────────────────────────────────────────────────────────── #

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None or getattr(self._executor, "_shutdown", False):
            self._executor = ThreadPoolExecutor(
                max_workers=self.max_workers,
                thread_name_prefix="task_scheduler",
            )
        return self._executor

    def _run_in_new_loop(
        self, tasks: List[TaskSpec], preserve_order: bool
    ) -> List[TaskResult]:
        return asyncio.run(self._schedule(tasks, preserve_order))

    async def _schedule(
        self, tasks: List[TaskSpec], preserve_order: bool
    ) -> List[TaskResult]:
        semaphore = asyncio.Semaphore(self.max_concurrency)
        loop = asyncio.get_event_loop()
        executor = self._get_executor()

        async def _run_one(index: int, spec: TaskSpec) -> tuple[int, TaskResult]:
            task_id = spec.task_id or f"task_{index}"
            timeout = spec.timeout_sec if spec.timeout_sec is not None else self.default_timeout_sec
            t0 = time.perf_counter()

            async with semaphore:
                try:
                    coro = loop.run_in_executor(
                        executor, _call_spec, spec
                    )
                    value = await asyncio.wait_for(coro, timeout=timeout)
                    duration = time.perf_counter() - t0
                    logger.debug("任务 %s 完成 (%.3fs)", task_id, duration)
                    return index, TaskResult(
                        task_id=task_id,
                        status="completed",
                        value=value,
                        duration_sec=duration,
                    )
                except asyncio.TimeoutError:
                    duration = time.perf_counter() - t0
                    logger.warning("任务 %s 超时 (%.1fs)", task_id, timeout)
                    return index, TaskResult(
                        task_id=task_id,
                        status="timeout",
                        value=None,
                        error=f"超时 ({timeout:.1f}s)",
                        duration_sec=duration,
                    )
                except Exception as exc:
                    duration = time.perf_counter() - t0
                    logger.error("任务 %s 失败: %s", task_id, exc)
                    return index, TaskResult(
                        task_id=task_id,
                        status="failed",
                        value=None,
                        error=str(exc),
                        duration_sec=duration,
                    )

        coroutines = [_run_one(i, spec) for i, spec in enumerate(tasks)]
        indexed_results = await asyncio.gather(*coroutines)

        if preserve_order:
            ordered = sorted(indexed_results, key=lambda x: x[0])
            return [r for _, r in ordered]
        return [r for _, r in indexed_results]

    async def _queue_worker(self, worker_index: int) -> None:
        """后台 worker：持续消费任务队列并写入结果队列。"""
        assert self._task_queue is not None
        assert self._result_queue is not None
        loop = asyncio.get_event_loop()
        executor = self._get_executor()

        while True:
            spec = await self._task_queue.get()
            task_id = spec.task_id or f"queue_worker_{worker_index}"
            if task_id == "__shutdown__":
                self._task_queue.task_done()
                break

            timeout = spec.timeout_sec if spec.timeout_sec is not None else self.default_timeout_sec
            t0 = time.perf_counter()
            try:
                coro = loop.run_in_executor(executor, _call_spec, spec)
                value = await asyncio.wait_for(coro, timeout=timeout)
                result = TaskResult(
                    task_id=task_id,
                    status="completed",
                    value=value,
                    duration_sec=time.perf_counter() - t0,
                )
            except asyncio.TimeoutError:
                result = TaskResult(
                    task_id=task_id,
                    status="timeout",
                    value=None,
                    error=f"超时 ({timeout:.1f}s)",
                    duration_sec=time.perf_counter() - t0,
                )
            except Exception as exc:
                result = TaskResult(
                    task_id=task_id,
                    status="failed",
                    value=None,
                    error=str(exc),
                    duration_sec=time.perf_counter() - t0,
                )

            await self._result_queue.put(result)
            self._task_queue.task_done()


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：LLM 专用便捷函数
# ─────────────────────────────────────────────────────────────────────────────

def run_llm_tasks(
    llm_service: Any,
    prompts: List[str],
    system_prompt: str = "",
    *,
    max_workers: int = _DEFAULT_MAX_WORKERS,
    timeout_sec: float = _DEFAULT_TASK_TIMEOUT,
    task_id_prefix: str = "llm",
) -> List[TaskResult]:
    """便捷函数：并发提交多个 LLM generate 调用。

    示例::

        results = run_llm_tasks(engine, ["问题A", "问题B", "问题C"])
        for r in results:
            if r.status == "completed":
                print(r.value)

    Args:
        llm_service: 任何拥有 ``generate(prompt, system_prompt) -> str`` 的对象。
        prompts:     待推理的 prompt 列表。
        system_prompt: 统一系统提示词（所有任务共用）。
        max_workers: 线程池大小。
        timeout_sec: 单任务超时。
        task_id_prefix: 任务 ID 前缀。
    """
    tasks = [
        TaskSpec(
            fn=llm_service.generate,
            args=(prompt,),
            kwargs={"system_prompt": system_prompt} if system_prompt else {},
            timeout_sec=timeout_sec,
            task_id=f"{task_id_prefix}_{i}",
        )
        for i, prompt in enumerate(prompts)
    ]
    scheduler = TaskScheduler(max_workers=max_workers, default_timeout_sec=timeout_sec)
    try:
        return scheduler.run_tasks(tasks)
    finally:
        scheduler.shutdown(wait=False)


# ─────────────────────────────────────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────────────────────────────────────

def _call_spec(spec: TaskSpec) -> Any:
    """在线程中调用 TaskSpec 描述的函数。"""
    return spec.fn(*spec.args, **spec.kwargs)
