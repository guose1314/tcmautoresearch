"""tests/test_task_scheduler.py — 3.2 TaskScheduler 单元测试"""

import time
import unittest
from unittest.mock import MagicMock

from src.orchestration.task_scheduler import (
    TaskResult,
    TaskScheduler,
    TaskSpec,
    _call_spec,
    run_llm_tasks,
)

# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _echo(x: str) -> str:
    return f"echo:{x}"


def _slow(delay: float, value: str) -> str:
    time.sleep(delay)
    return value


def _failing() -> None:
    raise ValueError("故意失败")


def _add(a: int, *, b: int = 0) -> int:
    return a + b


# ─────────────────────────────────────────────────────────────────────────────
# TaskSpec / TaskResult
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskSpec(unittest.TestCase):
    def test_defaults(self):
        spec = TaskSpec(fn=_echo, args=("hello",))
        self.assertEqual(spec.args, ("hello",))
        self.assertEqual(spec.kwargs, {})
        self.assertIsNone(spec.timeout_sec)
        self.assertEqual(spec.task_id, "")

    def test_full_fields(self):
        spec = TaskSpec(fn=_add, args=(3,), kwargs={"b": 7}, timeout_sec=30.0, task_id="t1")
        self.assertEqual(spec.task_id, "t1")
        self.assertEqual(spec.timeout_sec, 30.0)


class TestTaskResult(unittest.TestCase):
    def test_to_dict(self):
        r = TaskResult(task_id="t1", status="completed", value="ok", duration_sec=0.5)
        d = r.to_dict()
        self.assertEqual(d["task_id"], "t1")
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["value"], "ok")
        self.assertAlmostEqual(d["duration_sec"], 0.5, places=2)

    def test_failed_result(self):
        r = TaskResult(task_id="t2", status="failed", value=None, error="oops")
        self.assertEqual(r.error, "oops")


# ─────────────────────────────────────────────────────────────────────────────
# _call_spec 辅助
# ─────────────────────────────────────────────────────────────────────────────

class TestCallSpec(unittest.TestCase):
    def test_positional(self):
        spec = TaskSpec(fn=_echo, args=("world",))
        self.assertEqual(_call_spec(spec), "echo:world")

    def test_keyword(self):
        spec = TaskSpec(fn=_add, args=(5,), kwargs={"b": 3})
        self.assertEqual(_call_spec(spec), 8)


# ─────────────────────────────────────────────────────────────────────────────
# TaskScheduler.run_tasks — 同步入口
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskSchedulerRunTasks(unittest.TestCase):
    def setUp(self):
        self.scheduler = TaskScheduler(max_workers=2, max_concurrency=4, default_timeout_sec=10.0)

    def tearDown(self):
        self.scheduler.shutdown()

    def test_empty_tasks_returns_empty(self):
        results = self.scheduler.run_tasks([])
        self.assertEqual(results, [])

    def test_single_task_completed(self):
        tasks = [TaskSpec(fn=_echo, args=("hi",), task_id="t0")]
        results = self.scheduler.run_tasks(tasks)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "completed")
        self.assertEqual(results[0].value, "echo:hi")
        self.assertEqual(results[0].task_id, "t0")

    def test_multiple_tasks_all_completed(self):
        tasks = [TaskSpec(fn=_echo, args=(str(i),), task_id=f"t{i}") for i in range(5)]
        results = self.scheduler.run_tasks(tasks)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.status == "completed" for r in results))

    def test_preserve_order_true(self):
        tasks = [TaskSpec(fn=_echo, args=(str(i),), task_id=f"t{i}") for i in range(4)]
        results = self.scheduler.run_tasks(tasks, preserve_order=True)
        for i, r in enumerate(results):
            self.assertEqual(r.task_id, f"t{i}")

    def test_failed_task_captured(self):
        tasks = [
            TaskSpec(fn=_echo, args=("ok",), task_id="good"),
            TaskSpec(fn=_failing, args=(), task_id="bad"),
        ]
        results = self.scheduler.run_tasks(tasks)
        by_id = {r.task_id: r for r in results}
        self.assertEqual(by_id["good"].status, "completed")
        self.assertEqual(by_id["bad"].status, "failed")
        self.assertIn("故意失败", by_id["bad"].error)

    def test_timeout_task_captured(self):
        tasks = [TaskSpec(fn=_slow, args=(2.0, "late"), timeout_sec=0.05, task_id="slow")]
        results = self.scheduler.run_tasks(tasks)
        self.assertEqual(results[0].status, "timeout")
        self.assertIn("超时", results[0].error)

    def test_task_duration_recorded(self):
        tasks = [TaskSpec(fn=_slow, args=(0.05, "x"), task_id="timed")]
        results = self.scheduler.run_tasks(tasks)
        self.assertGreater(results[0].duration_sec, 0.0)

    def test_kwargs_passed_correctly(self):
        tasks = [TaskSpec(fn=_add, args=(10,), kwargs={"b": 20}, task_id="add")]
        results = self.scheduler.run_tasks(tasks)
        self.assertEqual(results[0].value, 30)

    def test_task_id_auto_assigned(self):
        tasks = [TaskSpec(fn=_echo, args=("x",))]  # 无 task_id
        results = self.scheduler.run_tasks(tasks)
        self.assertEqual(results[0].task_id, "task_0")

    def test_mixed_success_and_failure(self):
        tasks = [
            TaskSpec(fn=_echo, args=("a",), task_id="a"),
            TaskSpec(fn=_failing, task_id="fail"),
            TaskSpec(fn=_echo, args=("c",), task_id="c"),
        ]
        results = self.scheduler.run_tasks(tasks)
        statuses = {r.task_id: r.status for r in results}
        self.assertEqual(statuses["a"], "completed")
        self.assertEqual(statuses["fail"], "failed")
        self.assertEqual(statuses["c"], "completed")

    def test_concurrency_respected(self):
        """多任务并发执行时总耗时应远小于串行总时间。"""
        n = 4
        delay = 0.05
        tasks = [TaskSpec(fn=_slow, args=(delay, f"v{i}"), task_id=f"t{i}") for i in range(n)]
        scheduler = TaskScheduler(max_workers=n, max_concurrency=n, default_timeout_sec=10.0)
        t0 = time.perf_counter()
        results = scheduler.run_tasks(tasks)
        elapsed = time.perf_counter() - t0
        scheduler.shutdown()
        # 并行理论耗时约 delay 秒；串行约 n*delay 秒
        self.assertLess(elapsed, n * delay * 0.75)
        self.assertTrue(all(r.status == "completed" for r in results))


# ─────────────────────────────────────────────────────────────────────────────
# TaskScheduler.run_tasks_async — 异步入口
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskSchedulerAsync(unittest.IsolatedAsyncioTestCase):
    async def test_async_single_task(self):
        scheduler = TaskScheduler(max_workers=2)
        tasks = [TaskSpec(fn=_echo, args=("async",), task_id="a0")]
        results = await scheduler.run_tasks_async(tasks)
        scheduler.shutdown()
        self.assertEqual(results[0].status, "completed")
        self.assertEqual(results[0].value, "echo:async")

    async def test_async_multiple_tasks_concurrent(self):
        n = 4
        delay = 0.04
        scheduler = TaskScheduler(max_workers=n, max_concurrency=n)
        tasks = [TaskSpec(fn=_slow, args=(delay, f"v{i}"), task_id=f"a{i}") for i in range(n)]
        t0 = time.perf_counter()
        results = await scheduler.run_tasks_async(tasks)
        elapsed = time.perf_counter() - t0
        scheduler.shutdown()
        self.assertLess(elapsed, n * delay * 0.75)
        self.assertTrue(all(r.status == "completed" for r in results))

    async def test_async_timeout(self):
        scheduler = TaskScheduler(max_workers=2)
        tasks = [TaskSpec(fn=_slow, args=(2.0, "late"), timeout_sec=0.05, task_id="slow")]
        results = await scheduler.run_tasks_async(tasks)
        scheduler.shutdown()
        self.assertEqual(results[0].status, "timeout")

    async def test_async_failure(self):
        scheduler = TaskScheduler(max_workers=2)
        tasks = [TaskSpec(fn=_failing, task_id="fail")]
        results = await scheduler.run_tasks_async(tasks)
        scheduler.shutdown()
        self.assertEqual(results[0].status, "failed")
        self.assertIn("故意失败", results[0].error)


class TestTaskSchedulerQueueMode(unittest.IsolatedAsyncioTestCase):
    async def test_queue_submit_and_get_results(self):
        scheduler = TaskScheduler(max_workers=2, default_timeout_sec=2.0)
        await scheduler.start_queue()
        try:
            t1 = await scheduler.submit_task(TaskSpec(fn=_echo, args=("q1",), task_id="q1"))
            t2 = await scheduler.submit_task(TaskSpec(fn=_echo, args=("q2",), task_id="q2"))
            self.assertEqual(t1, "q1")
            self.assertEqual(t2, "q2")

            await scheduler.join_queue()
            r1 = await scheduler.get_result(timeout_sec=1.0)
            r2 = await scheduler.get_result(timeout_sec=1.0)
            self.assertIsNotNone(r1)
            self.assertIsNotNone(r2)
            assert r1 is not None
            assert r2 is not None
            ids = {r1.task_id, r2.task_id}
            self.assertEqual(ids, {"q1", "q2"})
            self.assertTrue({r1.status, r2.status} <= {"completed"})
        finally:
            await scheduler.stop_queue()
            scheduler.shutdown()

    async def test_queue_timeout_and_failure(self):
        scheduler = TaskScheduler(max_workers=2, default_timeout_sec=0.05)
        await scheduler.start_queue()
        try:
            await scheduler.submit_task(TaskSpec(fn=_slow, args=(0.2, "late"), task_id="slow"))
            await scheduler.submit_task(TaskSpec(fn=_failing, task_id="bad"))
            await scheduler.join_queue()

            results = [
                await scheduler.get_result(timeout_sec=1.0),
                await scheduler.get_result(timeout_sec=1.0),
            ]
            results = [r for r in results if r is not None]
            by_id = {r.task_id: r for r in results}
            self.assertEqual(by_id["slow"].status, "timeout")
            self.assertEqual(by_id["bad"].status, "failed")
        finally:
            await scheduler.stop_queue()
            scheduler.shutdown()

    async def test_get_result_timeout_returns_none(self):
        scheduler = TaskScheduler(max_workers=1)
        await scheduler.start_queue()
        try:
            result = await scheduler.get_result(timeout_sec=0.05)
            self.assertIsNone(result)
        finally:
            await scheduler.stop_queue()
            scheduler.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# run_llm_tasks 便捷函数
# ─────────────────────────────────────────────────────────────────────────────

class TestRunLlmTasks(unittest.TestCase):
    def _make_service(self, delay: float = 0.0):
        svc = MagicMock()
        svc.generate.side_effect = lambda prompt, system_prompt="": f"回答:{prompt}"
        return svc

    def test_basic_llm_batch(self):
        svc = self._make_service()
        prompts = ["问题A", "问题B", "问题C"]
        results = run_llm_tasks(svc, prompts, max_workers=3, timeout_sec=10.0)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.status == "completed" for r in results))
        values = [r.value for r in results]
        self.assertIn("回答:问题A", values)

    def test_system_prompt_forwarded(self):
        svc = MagicMock()
        captured = {}

        def _gen(prompt, system_prompt=""):
            captured["system"] = system_prompt
            return "ok"

        svc.generate.side_effect = _gen
        run_llm_tasks(svc, ["hi"], system_prompt="你是中医专家", max_workers=1)
        self.assertEqual(captured["system"], "你是中医专家")

    def test_task_ids_use_prefix(self):
        svc = self._make_service()
        results = run_llm_tasks(svc, ["q1", "q2"], task_id_prefix="llm_test")
        ids = [r.task_id for r in results]
        self.assertIn("llm_test_0", ids)
        self.assertIn("llm_test_1", ids)

    def test_empty_prompts(self):
        svc = self._make_service()
        results = run_llm_tasks(svc, [])
        self.assertEqual(results, [])

    def test_failing_llm_service(self):
        svc = MagicMock()
        svc.generate.side_effect = RuntimeError("模型崩溃")
        results = run_llm_tasks(svc, ["q1"], max_workers=1, timeout_sec=5.0)
        self.assertEqual(results[0].status, "failed")
        self.assertIn("模型崩溃", results[0].error)

    def test_concurrent_llm_calls(self):
        """多个 LLM 调用并发执行，总耗时应显著少于串行。"""
        delay = 0.04
        n = 4

        def _slow_gen(prompt, system_prompt=""):
            time.sleep(delay)
            return f"回答:{prompt}"

        svc = MagicMock()
        svc.generate.side_effect = _slow_gen
        t0 = time.perf_counter()
        results = run_llm_tasks(svc, [f"q{i}" for i in range(n)], max_workers=n, timeout_sec=10.0)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, n * delay * 0.75)
        self.assertTrue(all(r.status == "completed" for r in results))


# ─────────────────────────────────────────────────────────────────────────────
# TaskScheduler.shutdown
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskSchedulerShutdown(unittest.TestCase):
    def test_shutdown_idempotent(self):
        scheduler = TaskScheduler()
        scheduler.shutdown()
        scheduler.shutdown()  # 第二次不应抛异常

    def test_executor_recreated_after_shutdown(self):
        scheduler = TaskScheduler(max_workers=2)
        # 先触发一次执行使 executor 实例化
        scheduler.run_tasks([TaskSpec(fn=_echo, args=("x",))])
        scheduler.shutdown()
        # 再次提交任务应重建 executor
        results = scheduler.run_tasks([TaskSpec(fn=_echo, args=("y",))])
        self.assertEqual(results[0].status, "completed")
        scheduler.shutdown()


if __name__ == "__main__":
    unittest.main()
